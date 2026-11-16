import pytest
import asyncio
import time
import json
from unittest import mock
from aiogram import types

from extreme_defense_engine import (
    classify_extreme_media,
    register_extreme_strike,
    execute_extreme_lockdown,
    process_file_extreme_defense,
    _EXTREME_STRIKES_CACHE
)

def test_classify_copro():
    # Definite copro
    assert classify_extreme_media("1boy, solo, nudity, penis, feces, scat, mud, masturbation")[0] is True
    assert classify_extreme_media("photo, coprophilia, disgusting, shock")[0] is True
    assert classify_extreme_media("feces, human, defecation, anal")[0] is True

    # Safe / False positive resistance
    assert classify_extreme_media("jazz, scat, singing, vocal, performance")[0] is False
    assert classify_extreme_media("wildlife, nature, animal, dirt, feces, outdoors")[0] is False
    assert classify_extreme_media("toilet, coffee, mug, humor, joke, meme")[0] is False

def test_classify_guro():
    # Definite guro / extreme gore
    assert classify_extreme_media("anime, guro, blood, dark, horror")[0] is True
    assert classify_extreme_media("snuff, crime, torture")[0] is True
    assert classify_extreme_media("dismemberment, severed_head, crime")[0] is True
    assert classify_extreme_media("photo, real_life, gore, wound, corpse, hospital")[0] is True
    assert classify_extreme_media("photo, real_life, decapitation, crime, street")[0] is True
    assert classify_extreme_media("photograph, corpse, dead_body, mutilation")[0] is True

    # Safe / Anime action / Ecchi
    assert classify_extreme_media("anime, 1boy, action, battle, sword, blood, injury")[0] is False
    assert classify_extreme_media("1girl, solo, anime, bikini, breasts, smile")[0] is False
    assert classify_extreme_media("1girl, 1boy, hentai, nude, sex, missionary, cum")[0] is False
    assert classify_extreme_media("cosplay, halloween, costume, jason_voorhees, fake_blood, mask")[0] is False

    # Safe / Political caricatures, cartoons, satire and memes (Zero False Positives)
    # The exact incident from post #587366:
    assert classify_extreme_media("political, meme, anthropomorphic, flag, russia, gore, decapitation, text, digital_art, parody")[0] is False
    assert classify_extreme_media("caricature, satire, drawing, decapitation, politics, humor")[0] is False
    assert classify_extreme_media("wojak, meme, severed_head, funny, cartoon")[0] is False
    assert classify_extreme_media("comic, illustration, sketch, dismemberment, fantasy_battle")[0] is False
    assert classify_extreme_media("editorial_cartoon, political_satire, guillotine, decapitation")[0] is False

@pytest.mark.asyncio
async def test_strike_accumulation_and_lockdown(isolated_test_db):
    db = isolated_test_db
    author_id = 99887766
    board_id = 'b'

    # Insert user into isolated DB
    await db.execute(
        "INSERT INTO Users (user_id, board_id, role, shadow_ban_media) VALUES (?, ?, 'user', 0)",
        (author_id, board_id)
    )
    # Insert two posts by this user
    await db.execute(
        "INSERT INTO Posts (post_num, board_id, author_id, timestamp, content) VALUES (7001, 'b', ?, ?, '{\"type\": \"photo\"}')",
        (author_id, time.time() - 100)
    )
    await db.execute(
        "INSERT INTO PostFiles (post_num, file_type, original_file_id) VALUES (7001, 'photo', 'file_bad_1')"
    )
    await db.execute(
        "INSERT INTO Posts (post_num, board_id, author_id, timestamp, content) VALUES (7002, 'b', ?, ?, '{\"type\": \"photo\"}')",
        (author_id, time.time() - 50)
    )
    await db.execute(
        "INSERT INTO PostFiles (post_num, file_type, original_file_id) VALUES (7002, 'photo', 'file_bad_2')"
    )
    await db.commit()

    # Clear memory cache for author
    _EXTREME_STRIKES_CACHE.pop(author_id, None)

    bot_mock = mock.AsyncMock()
    bot_mock.send_message = mock.AsyncMock()

    # Strike 1: First bad media
    res1 = await process_file_extreme_defense(
        bot=bot_mock,
        file_id='file_bad_1',
        tags='1boy, adult, nudity, feces, scat, mud, masturbation',
        description='copro',
        post_num=7001,
        author_id=author_id,
        board_id=board_id
    )
    assert res1 is True

    # User should NOT be locked down yet on Strike 1
    async with db.execute("SELECT shadow_ban_media FROM Users WHERE user_id = ?", (author_id,)) as cur:
        row = await cur.fetchone()
        assert row[0] == 0  # not yet banned

    # Strike 2: Second bad media
    res2 = await process_file_extreme_defense(
        bot=bot_mock,
        file_id='file_bad_2',
        tags='anime, guro, dismemberment, horror',
        description='guro',
        post_num=7002,
        author_id=author_id,
        board_id=board_id
    )
    assert res2 is True

    # On Strike >= 2, lockdown MUST be triggered:
    # 1. shadow_ban_media == 1
    async with db.execute("SELECT shadow_ban_media FROM Users WHERE user_id = ?", (author_id,)) as cur:
        row = await cur.fetchone()
        assert row[0] == 1  # Media toggle banned!

    # 2. Shadowmute recorded in Mutes
    async with db.execute("SELECT COUNT(*) FROM Mutes WHERE user_id = ? AND mute_type = 'shadow'", (author_id,)) as cur:
        mutes_count = (await cur.fetchone())[0]
        assert mutes_count >= 1

@pytest.mark.asyncio
async def test_delete_user_posts_foreign_key_safety(isolated_test_db):
    """
    Верифицирует, что delete_user_posts удаляет посты с PostFiles, PostCopies,
    ChannelCopies и т.д. БЕЗ ошибки FOREIGN KEY constraint failed.
    """
    import main
    from main import delete_user_posts

    db = isolated_test_db
    author_id = 11223344
    board_id = 'b'

    # Создаем посты и привязанные дочерние записи
    for p_num in [8001, 8002]:
        await db.execute(
            "INSERT INTO Posts (post_num, board_id, author_id, timestamp, content) VALUES (?, 'b', ?, ?, '{}')",
            (p_num, author_id, time.time() - 60)
        )
        await db.execute(
            "INSERT INTO PostFiles (post_num, file_type, original_file_id) VALUES (?, 'photo', ?)",
            (p_num, f"fid_{p_num}")
        )
        await db.execute(
            "INSERT INTO PostCopies (post_num, recipient_id, message_id) VALUES (?, 999, ?)",
            (p_num, p_num + 1000)
        )
        await db.execute(
            "INSERT INTO ChannelCopies (post_num, channel_id, message_id) VALUES (?, -100123, ?)",
            (p_num, p_num + 2000)
        )
        await db.execute(
            "INSERT INTO BroadcastQueue (post_num, created_at) VALUES (?, ?)",
            (p_num, time.time())
        )
    await db.commit()

    bot_mock = mock.AsyncMock()

    # Удаляем посты за 60 минут с замоканным get_pool
    with mock.patch.object(main, "get_pool", mock.AsyncMock(return_value=db)):
        deleted_count = await delete_user_posts(bot_mock, author_id, 60, board_id)
        assert deleted_count == 2

    # Проверяем, что в базе всё вычищено
    async with db.execute("SELECT COUNT(*) FROM Posts WHERE author_id = ?", (author_id,)) as cur:
        assert (await cur.fetchone())[0] == 0

    async with db.execute("SELECT COUNT(*) FROM PostFiles WHERE post_num IN (8001, 8002)") as cur:
        assert (await cur.fetchone())[0] == 0

@pytest.mark.asyncio
async def test_cmd_wipe_routing(isolated_test_db):
    """
    Проверяет, что /wipe работает для админа даже если board_id=None (в ЛС бота)
    и корректно разрешает board_id и автора из номера поста.
    """
    import main
    from main import cmd_wipe
    from common.config import ADMIN_IDS

    db = isolated_test_db
    admin_id = next(iter(ADMIN_IDS))

    # Создаем пост в isolated_test_db
    await db.execute(
        "INSERT INTO Posts (post_num, board_id, author_id, timestamp, content) VALUES (9001, 'b', 55555, ?, '{}')",
        (time.time(),)
    )
    await db.commit()

    msg = mock.AsyncMock(spec=types.Message)
    msg.from_user = mock.MagicMock(id=admin_id)
    msg.reply_to_message = None
    msg.text = "/wipe 9001 30m"
    msg.caption = None
    msg.answer = mock.AsyncMock()
    msg.delete = mock.AsyncMock()

    with mock.patch.object(main, "get_pool", mock.AsyncMock(return_value=db)):
        # Вызываем с board_id=None (как в ЛС)
        await cmd_wipe(msg, board_id=None, stream='ru')

    assert msg.answer.called
    reply_args = msg.answer.call_args[0][0]
    # Должен сформировать подтверждение вайпа на /b/ с кнопками
    assert "Вайп:" in reply_args or "Wipe" in reply_args
    assert "/b/" in reply_args

@pytest.mark.asyncio
async def test_cmd_sdel_routing(isolated_test_db):
    """
    Проверяет, что /sdel работает по номеру поста без обязательного reply
    и для админа при board_id=None.
    """
    import main
    from main import cmd_sdel
    from common.config import ADMIN_IDS

    db = isolated_test_db
    admin_id = next(iter(ADMIN_IDS))

    await db.execute(
        "INSERT INTO Posts (post_num, board_id, author_id, timestamp, content, is_shadow) VALUES (9002, 'b', 66666, ?, '{}', 0)",
        (time.time(),)
    )
    await db.execute(
        "INSERT INTO PostCopies (post_num, recipient_id, message_id) VALUES (9002, 77777, 100)",
    )
    await db.commit()

    msg = mock.AsyncMock(spec=types.Message)
    msg.from_user = mock.MagicMock(id=admin_id)
    msg.reply_to_message = None
    msg.text = "/sdel 9002"
    msg.caption = None
    msg.answer = mock.AsyncMock()
    msg.delete = mock.AsyncMock()
    msg.bot = mock.AsyncMock()
    msg.bot.delete_message = mock.AsyncMock(return_value=True)

    with mock.patch.object(main, "get_pool", mock.AsyncMock(return_value=db)):
        await cmd_sdel(msg, board_id=None, stream='ru')

    assert msg.answer.called
    # В БД пост должен стать is_shadow=1
    async with db.execute("SELECT is_shadow FROM Posts WHERE post_num = 9002") as cur:
        row = await cur.fetchone()
        assert row[0] == 1

@pytest.mark.asyncio
async def test_admin_commands_pm_safety(isolated_test_db):
    """
    Проверяет, что команды админа (/whois, /gunban, /lockdown) не падают
    и не блокируются, когда админ вызывает их в ЛС (board_id=None).
    """
    import main
    from main import cmd_whois, cmd_gunban, cmd_bot_lockdown
    from common.config import ADMIN_IDS

    db = isolated_test_db
    admin_id = next(iter(ADMIN_IDS))

    # /whois in PM
    msg_whois = mock.AsyncMock(spec=types.Message)
    msg_whois.from_user = mock.MagicMock(id=admin_id)
    msg_whois.reply_to_message = None
    msg_whois.text = "/whois 12345"
    msg_whois.caption = None
    msg_whois.answer = mock.AsyncMock()
    msg_whois.delete = mock.AsyncMock()

    with mock.patch.object(main, "get_pool", mock.AsyncMock(return_value=db)):
        await cmd_whois(msg_whois, board_id=None, stream='ru')
    assert msg_whois.answer.called

    # /gunban in PM
    msg_gunban = mock.AsyncMock(spec=types.Message)
    msg_gunban.from_user = mock.MagicMock(id=admin_id)
    msg_gunban.reply_to_message = None
    msg_gunban.text = "/gunban 12345"
    msg_gunban.caption = None
    status_mock = mock.AsyncMock()
    msg_gunban.answer = mock.AsyncMock(return_value=status_mock)
    msg_gunban.delete = mock.AsyncMock()

    with mock.patch.object(main, "get_pool", mock.AsyncMock(return_value=db)):
        await cmd_gunban(msg_gunban, board_id=None, stream='ru')
    assert msg_gunban.answer.called

    # /lockdown in PM
    msg_lock = mock.AsyncMock(spec=types.Message)
    msg_lock.from_user = mock.MagicMock(id=admin_id)
    msg_lock.text = "/lockdown on"
    msg_lock.caption = None
    msg_lock.answer = mock.AsyncMock()

    with mock.patch.object(main, "get_pool", mock.AsyncMock(return_value=db)):
        await cmd_bot_lockdown(msg_lock, board_id=None)
    assert msg_lock.answer.called
    assert "активирован" in msg_lock.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_auto_lockdown_15min_wipe_window_preserves_old_posts(isolated_test_db):
    """
    Верифицирует, что при автоматическом локдауне:
    1. delete_user_posts вызывается с окном 15 минут (а не 1440).
    2. Посты нарушителя старше 15 минут (например, 30 минут назад) НЕ удаляются.
    3. Свежие посты нарушителя (<15 минут назад) и зафиксированные offending_post_nums удаляются.
    4. Текст алерта админам содержит указание на 15-минутное окно зачистки.
    """
    db = isolated_test_db
    author_id = 44556677
    board_id = 'b'
    now = time.time()

    # Вставляем пользователя
    await db.execute(
        "INSERT INTO Users (user_id, board_id, role, shadow_ban_media) VALUES (?, ?, 'user', 0)",
        (author_id, board_id)
    )

    # Пост 1: Старый нормальный пост (30 минут назад = now - 1800) -> ДОЛЖЕН ОСТАТЬСЯ
    await db.execute(
        "INSERT INTO Posts (post_num, board_id, author_id, timestamp, content) VALUES (7101, 'b', ?, ?, '{}')",
        (author_id, now - 1800)
    )
    # Пост 2: Свежий нормальный пост (10 минут назад = now - 600) -> ДОЛЖЕН БЫТЬ УДАЛЕН АВТО-ВАЙПОМ 15М
    await db.execute(
        "INSERT INTO Posts (post_num, board_id, author_id, timestamp, content) VALUES (7102, 'b', ?, ?, '{}')",
        (author_id, now - 600)
    )
    # Пост 3: Свежий шок-пост (2 минуты назад = now - 120) -> ШОК-ПОСТ (offending) -> ДОЛЖЕН БЫТЬ УДАЛЕН
    await db.execute(
        "INSERT INTO Posts (post_num, board_id, author_id, timestamp, content) VALUES (7103, 'b', ?, ?, '{}')",
        (author_id, now - 120)
    )
    # Пост 4: Свежий шок-пост (30 секунд назад = now - 30) -> ШОК-ПОСТ (offending) -> ДОЛЖЕН БЫТЬ УДАЛЕН
    await db.execute(
        "INSERT INTO Posts (post_num, board_id, author_id, timestamp, content) VALUES (7104, 'b', ?, ?, '{}')",
        (author_id, now - 30)
    )
    await db.commit()

    bot_mock = mock.AsyncMock()
    bot_mock.send_message = mock.AsyncMock()

    deleted_calls = []
    async def fake_delete_user_posts(bot, user_id, time_period_minutes, b_id):
        deleted_calls.append({
            "user_id": user_id,
            "minutes": time_period_minutes,
            "board_id": b_id
        })
        threshold = time.time() - (time_period_minutes * 60)
        async with db.execute("SELECT post_num FROM Posts WHERE author_id = ? AND timestamp >= ?", (user_id, threshold)) as cur:
            rows = await cur.fetchall()
        p_nums = [r[0] for r in rows]
        if p_nums:
            placeholders = ",".join("?" for _ in p_nums)
            await db.execute(f"DELETE FROM Posts WHERE post_num IN ({placeholders})", p_nums)
            await db.commit()
        return len(p_nums)

    async def fake_delete_single_post(p_num, bot):
        await db.execute("DELETE FROM Posts WHERE post_num = ?", (p_num,))
        await db.commit()
        return 1

    import main
    with mock.patch("extreme_defense_engine.get_pool", return_value=db), \
         mock.patch.object(main, "delete_user_posts", side_effect=fake_delete_user_posts), \
         mock.patch.object(main, "delete_single_post", side_effect=fake_delete_single_post), \
         mock.patch("post_helpers.delete_user_posts", side_effect=fake_delete_user_posts), \
         mock.patch("post_helpers.delete_single_post", side_effect=fake_delete_single_post):

        await execute_extreme_lockdown(
            bot=bot_mock,
            author_id=author_id,
            board_id=board_id,
            category="COPRO",
            reason="Explicit copro tags",
            offending_post_nums=[7103, 7104]
        )

    # 1. Проверяем вызов delete_user_posts: ровно 15 минут, board_id='all'
    assert len(deleted_calls) == 1
    assert deleted_calls[0]["minutes"] == 15
    assert deleted_calls[0]["user_id"] == author_id
    assert deleted_calls[0]["board_id"] == 'all'

    # 2. Проверяем состояние постов в БД:
    # Пост 7101 (30 минут назад) СОХРАНЕН!
    async with db.execute("SELECT post_num FROM Posts WHERE post_num = 7101") as cur:
        assert (await cur.fetchone()) is not None

    # Посты 7102, 7103, 7104 УДАЛЕНЫ!
    async with db.execute("SELECT post_num FROM Posts WHERE post_num IN (7102, 7103, 7104)") as cur:
        assert (await cur.fetchall()) == []

    # 3. Проверяем текст алерта админам
    assert bot_mock.send_message.called
    sent_alert_text = bot_mock.send_message.call_args[0][1]
    assert "15 минут" in sent_alert_text
    assert "старше 15 минут сохранены" in sent_alert_text


@pytest.mark.asyncio
async def test_real_delete_user_posts_15min_window(isolated_test_db):
    """
    Интеграционный тест: проверяет реальный SQL в _delete_user_posts_from_db / delete_user_posts,
    подтверждая, что посты старше 15 минут не затрагиваются, а посты младше 15 минут удаляются.
    """
    import main
    from main import delete_user_posts

    db = isolated_test_db
    author_id = 88990011
    now = time.time()

    # Пост 1: 30 минут назад (now - 1800)
    await db.execute(
        "INSERT INTO Posts (post_num, board_id, author_id, timestamp, content) VALUES (7201, 'b', ?, ?, '{}')",
        (author_id, now - 1800)
    )
    # Пост 2: 10 минут назад (now - 600)
    await db.execute(
        "INSERT INTO Posts (post_num, board_id, author_id, timestamp, content) VALUES (7202, 'b', ?, ?, '{}')",
        (author_id, now - 600)
    )
    # Пост 3: 2 минуты назад (now - 120)
    await db.execute(
        "INSERT INTO Posts (post_num, board_id, author_id, timestamp, content) VALUES (7203, 'b', ?, ?, '{}')",
        (author_id, now - 120)
    )
    await db.commit()

    bot_mock = mock.AsyncMock()

    with mock.patch.object(main, "get_pool", mock.AsyncMock(return_value=db)), \
         mock.patch("main._delete_posts_from_channels", new=mock.AsyncMock()), \
         mock.patch("main._delete_posts_from_pm_api", new=mock.AsyncMock()):

        deleted = await delete_user_posts(bot_mock, author_id, 15, 'all')
        assert deleted == 2

    # Пост 7201 (30 минут назад) остался в БД
    async with db.execute("SELECT post_num FROM Posts WHERE post_num = 7201") as cur:
        assert (await cur.fetchone()) is not None

    # Посты 7202 и 7203 (младше 15 минут) удалены
    async with db.execute("SELECT post_num FROM Posts WHERE post_num IN (7202, 7203)") as cur:
        assert (await cur.fetchall()) == []
