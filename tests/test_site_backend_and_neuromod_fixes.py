import asyncio
import base64
import time
import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch

import site_tgach.neuro_moderator as neuro_mod
from site_tgach.neuro_moderator import is_vector_tgs, run_deep_check, _run_deep_check_impl
import site_tgach.catbox as catbox
import site_tgach.security as security


# =====================================================================
# 1. FAIL-OPEN ELIMINATION & QUARANTINE IN NEUROMODERATOR
# =====================================================================

@pytest.mark.asyncio
async def test_neuro_mod_fail_open_quarantines_image():
    """
    При сбое нейросети (Gemini failure, timeout, None) контент обязан автоматически
    попадать в карантин (blur + ModQueue), а не проходить мимо цензуры (ликвидация Fail-Open).
    """
    file_id = "test_fail_open_img_123"
    fake_bytes = b"\xff\xd8\xff\xe0" + b"\x00" * 32  # Valid JPEG header dummy

    mock_pool = MagicMock()
    mock_pool.execute = AsyncMock()

    with patch.object(neuro_mod, "_safe_groq_json", new_callable=AsyncMock) as mock_groq, \
         patch("common.database.apply_auto_censure", new_callable=AsyncMock) as mock_censure_db, \
         patch("site_tgach.neuro_moderator.apply_auto_censure", new_callable=AsyncMock) as mock_censure, \
         patch("common.database.add_to_mod_queue", new_callable=AsyncMock) as mock_queue_db, \
         patch("site_tgach.neuro_moderator.add_to_mod_queue", new_callable=AsyncMock) as mock_queue, \
         patch("common.database.get_pool", new_callable=AsyncMock, return_value=mock_pool):

        mock_groq.return_value = None
        mock_censure.return_value = [5001]
        mock_censure_db.return_value = [5001]

        await _run_deep_check_impl(fake_bytes, file_id)

        # Проверяем, что картинка заблюрена
        assert mock_censure.await_count + mock_censure_db.await_count == 1
        call_args = mock_censure.call_args or mock_censure_db.call_args
        assert call_args[0] == (file_id, "blur")

        # Проверяем, что пост отправлен в ModQueue на ручную проверку
        assert mock_queue.await_count + mock_queue_db.await_count == 1
        q_args, _ = mock_queue.call_args or mock_queue_db.call_args
        assert q_args[0] == 5001  # pid
        assert q_args[1] == file_id
        assert "AI Check Failure" in q_args[2] or "Quarantined" in q_args[2]
        assert q_args[3] >= 0.5  # score

        # Проверяем, что событие добавлено в BroadcastQueue для реалтайм обновления фронтенда
        mock_pool.execute.assert_awaited()


# =====================================================================
# 2. STATIC TELEGRAM STICKERS VS VECTOR TGS
# =====================================================================

def test_is_vector_tgs_detection():
    """
    Проверяет точное распознавание векторных Lottie TGS стикеров (gzip JSON)
    в отличие от статичных стикеров (WebP, PNG, JPEG).
    """
    tgs_bytes = b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x00\x03" + b"dummy_lottie"
    webp_bytes = b"RIFF\x20\x00\x00\x00WEBPVP8 " + b"\x00" * 16
    png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
    jpeg_bytes = b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"\x00" * 16

    # Векторный TGS по сигнатуре gzip
    assert is_vector_tgs(tgs_bytes, "CAACAgIAAxkBAAE...") is True
    # Векторный TGS по расширению файла
    assert is_vector_tgs(b"dummy", "sticker_file.tgs") is True

    # Статичные стикеры Telegram НЕ являются TGS
    assert is_vector_tgs(webp_bytes, "CAACAgIAAxkBAAE123_pepe") is False
    assert is_vector_tgs(png_bytes, "CAACAgUAAxkBAAE456") is False
    assert is_vector_tgs(jpeg_bytes, "sticker_static_789") is False
    assert is_vector_tgs(None, "CAACAgIAAxkBAAE...") is False


@pytest.mark.asyncio
async def test_run_deep_check_skips_vector_tgs_only():
    """
    run_deep_check обязан пропускать ТОЛЬКО векторные TGS,
    а статичные Telegram-стикеры (CAAC) ОБЯЗАН отправлять на проверку.
    """
    tgs_bytes = b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x00\x03" + b"dummy_lottie"
    webp_sticker_bytes = b"RIFF\x20\x00\x00\x00WEBPVP8 " + b"\x00" * 16

    with patch.object(neuro_mod, "_run_deep_check_impl", new_callable=AsyncMock) as mock_impl:
        # 1. Векторный TGS стикер -> должен быть пропущен (не вызывает _run_deep_check_impl)
        await run_deep_check(tgs_bytes, "CAACAgIAAxk_vector_tgs")
        mock_impl.assert_not_awaited()

        # 2. Статичный Telegram-стикер (CAAC) -> НЕ должен пропускаться вслепую!
        await run_deep_check(webp_sticker_bytes, "CAACAgIAAxk_static_pepe")
        mock_impl.assert_awaited_once_with(webp_sticker_bytes, "CAACAgIAAxk_static_pepe")


# =====================================================================
# 3. TEEN SFW VS NSFW MODERATION FIX
# =====================================================================

@pytest.mark.asyncio
async def test_teen_photorealistic_sfw_not_blurred():
    """
    Фотореалистичные изображения подростков БЕЗ NSFW флага НЕ должны блюриться.
    (Исправление бага безусловного цензурирования).
    """
    file_id = "teen_sfw_photo"
    fake_bytes = b"\xff\xd8\xff\xe0" + b"\x00" * 16

    with patch.object(neuro_mod, "_safe_groq_json", new_callable=AsyncMock) as mock_groq, \
         patch("common.database.apply_auto_censure", new_callable=AsyncMock) as mock_censure_db, \
         patch("site_tgach.neuro_moderator.apply_auto_censure", new_callable=AsyncMock) as mock_censure, \
         patch("common.database.add_to_mod_queue", new_callable=AsyncMock) as mock_queue_db, \
         patch("site_tgach.neuro_moderator.add_to_mod_queue", new_callable=AsyncMock) as mock_queue:

        # Модель говорит: фотореализм, подросток, но SFW!
        mock_groq.return_value = {
            "visual_style": "photorealistic",
            "subject_age_visual": "teen",
            "is_nsfw": False,
            "safety_flags": ["portrait", "student"],
            "description": "A teenager in school uniform walking in park."
        }

        await _run_deep_check_impl(fake_bytes, file_id)

        # Никакого блюра и очередей модерации
        mock_censure.assert_not_awaited()
        mock_queue.assert_not_awaited()


@pytest.mark.asyncio
async def test_teen_photorealistic_nsfw_is_blurred():
    """
    Фотореалистичные изображения подростков С NSFW флагом ОБЯЗАНЫ цензурироваться (blur + ModQueue).
    """
    file_id = "teen_nsfw_photo"
    fake_bytes = b"\xff\xd8\xff\xe0" + b"\x00" * 16

    mock_pool = MagicMock()
    mock_pool.execute = AsyncMock()

    with patch.object(neuro_mod, "_safe_groq_json", new_callable=AsyncMock) as mock_groq, \
         patch("common.database.apply_auto_censure", new_callable=AsyncMock) as mock_censure_db, \
         patch("site_tgach.neuro_moderator.apply_auto_censure", new_callable=AsyncMock) as mock_censure, \
         patch("common.database.add_to_mod_queue", new_callable=AsyncMock) as mock_queue_db, \
         patch("site_tgach.neuro_moderator.add_to_mod_queue", new_callable=AsyncMock) as mock_queue, \
         patch("common.database.get_pool", new_callable=AsyncMock, return_value=mock_pool):

        mock_groq.return_value = {
            "visual_style": "photorealistic",
            "subject_age_visual": "teen",
            "is_nsfw": True,
            "safety_flags": ["nudity", "underwear"],
            "description": "Underage NSFW content."
        }
        mock_censure.return_value = [6002]
        mock_censure_db.return_value = [6002]

        await _run_deep_check_impl(fake_bytes, file_id)

        # Должен сработать блюр
        assert mock_censure.await_count + mock_censure_db.await_count == 1
        call_args = mock_censure.call_args or mock_censure_db.call_args
        assert call_args[0] == (file_id, "blur")

        # Должна быть добавлена запись в ModQueue
        assert mock_queue.await_count + mock_queue_db.await_count == 1
        q_args, _ = mock_queue.call_args or mock_queue_db.call_args
        assert q_args[0] == 6002
        assert q_args[1] == file_id


# =====================================================================
# 4. CATBOX 412 INVALID UPLOADER FIX & ANONYMOUS RETRY
# =====================================================================

@pytest.mark.asyncio
async def test_catbox_invalid_uploader_zeroes_hash_and_does_not_pause_globally():
    """
    Ошибка 'invalid uploader' (даже при 412) не должна отключать Catbox глобально
    на 2 часа для всех. Невалидный CATBOX_HASH обнуляется, и запрос мгновенно
    ретраится анонимно.
    """
    catbox.CATBOX_HASH = "invalid_user_hash_deadbeef"
    catbox._CATBOX_GLOBAL_DISABLED_UNTIL = 0.0

    call_count = 0

    async def mock_send(client, url, data, files=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # Первый запрос с userhash отвергнут
            assert "userhash" in data
            return httpx.Response(412, text="invalid uploader")
        else:
            # Второй запрос — анонимный ретрай без userhash
            assert "userhash" not in data
            return httpx.Response(200, text="https://files.catbox.moe/success_anon.png")

    with patch.object(catbox, "_send_request", side_effect=mock_send):
        result = await catbox.upload_bytes_to_catbox(b"fake_image_content", "test.png")

        # 1. Загрузка успешно прошла через анонимный фолбэк
        assert result == "https://files.catbox.moe/success_anon.png"
        assert call_count == 2

        # 2. Невалидный CATBOX_HASH обнулен в None
        assert catbox.CATBOX_HASH is None

        # 3. Сервис Catbox НЕ отключен на 2 часа для всех!
        assert catbox._CATBOX_GLOBAL_DISABLED_UNTIL == 0.0
        assert catbox.is_catbox_available() is True


@pytest.mark.asyncio
async def test_catbox_real_storage_pause_activates_cooldown():
    """
    Реальная пауза сервиса Catbox (хранилище переполнено / uploads paused)
    должна активировать двухчасовой кулдаун.
    """
    catbox.CATBOX_HASH = None
    catbox._CATBOX_GLOBAL_DISABLED_UNTIL = 0.0

    resp = httpx.Response(412, text="Uploads paused due to storage issues")

    with patch.object(catbox, "_send_request", new_callable=AsyncMock, return_value=resp):
        result = await catbox.upload_bytes_to_catbox(b"fake_image_content", "test.png")

        assert result is None
        # Проверяем, что установлен 2-часовой кулдаун
        assert catbox.is_catbox_available() is False
        assert catbox._CATBOX_GLOBAL_DISABLED_UNTIL > time.time() + 7000

    # Очистка состояния
    catbox._CATBOX_GLOBAL_DISABLED_UNTIL = 0.0


# =====================================================================
# 5. SECURITY: BAN_TIME INCREASE TO 600S & FLOOD LIMIT PROTECTION
# =====================================================================

def test_security_ban_time_is_600s():
    """
    BAN_TIME обязан составлять 600 секунд (10 минут) вместо устаревших 60с.
    """
    assert security.BAN_TIME == 600


def test_security_check_ddos_enforces_600s_ban():
    """
    При превышении лимита MAX_REQUESTS_PER_WINDOW нарушитель банится ровно на 600 секунд.
    """
    security.REQUEST_HISTORY.clear()
    security.IP_BAN_LIST.clear()

    test_ip = "192.0.2.100"
    fixed_now = 1700000000.0

    with patch("time.time", return_value=fixed_now), \
         patch("random.random", return_value=1.0):  # Отключаем вероятностную очистку

        # Делаем 200 допустимых запросов в окне
        for _ in range(security.MAX_REQUESTS_PER_WINDOW):
            is_banned = security.check_ddos(test_ip)
            assert is_banned is False

        # 201-й запрос превышает порог -> бан на 600 секунд
        is_banned = security.check_ddos(test_ip)
        assert is_banned is True

        # Проверяем, что IP в бане ровно до fixed_now + 600
        assert test_ip in security.IP_BAN_LIST
        assert security.IP_BAN_LIST[test_ip] == fixed_now + 600

    # Проверяем поведение во время бана и после истечения
    with patch("time.time", return_value=fixed_now + 599):
        assert security.check_ddos(test_ip) is True  # Еще в бане

    with patch("time.time", return_value=fixed_now + 601):
        assert security.check_ddos(test_ip) is False  # Бан истек


def test_security_pow_cache_and_verify():
    """
    Проверяет генерацию PoW-челленджа, валидацию и защиту от replay-атак.
    """
    security.POW_CACHE.clear()

    data = security.get_pow_challenge_data(difficulty=2)
    chal = data["challenge"]
    diff = data["difficulty"]

    assert chal in security.POW_CACHE

    # Подбираем nonce
    nonce = 0
    import hashlib
    target = "0" * diff
    while not hashlib.sha256(f"{chal}{nonce}".encode("utf-8")).hexdigest().startswith(target):
        nonce += 1

    # Успешная валидация
    assert security.verify_pow(chal, str(nonce), difficulty=diff) is True

    # Replay-атака: повторная попытка с тем же challenge должна отклоняться
    assert security.verify_pow(chal, str(nonce), difficulty=diff) is False
