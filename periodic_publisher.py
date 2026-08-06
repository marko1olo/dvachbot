import asyncio
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Any, Callable, Iterable, Sequence

from aiogram import Bot
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramRetryAfter,
)
from aiogram.types import BufferedInputFile, InputMediaPhoto

# We will run the generator in a separate thread so it doesn't block the async loop
from stats_generator import generate_all_charts

logger = logging.getLogger("stats_publisher")

# Channel ID where stats will be published (user can configure this later)
NEWS_CHANNEL_ID = None

MSK_OFFSET = timezone(timedelta(hours=3))

# Telegram allows at most 10 media items per album.
MEDIA_GROUP_MAX_ITEMS = 10

# Broadcast pacing / resilience knobs.
BROADCAST_DELAY_BETWEEN_GROUPS = 0.1
BROADCAST_DELAY_BETWEEN_USERS = 0.2
BROADCAST_SEND_TIMEOUT = 60.0
BROADCAST_MAX_RETRY_AFTER = 300.0
ARCHIVE_UPLOAD_ATTEMPTS = 3
POST_PUBLISH_COOLDOWN = 3600

# matplotlib/pyplot keeps global state, so chart generation must never run twice
# at once (weekly publisher vs. an admin firing /bot_stats).
_chart_generation_lock = asyncio.Lock()

CAPTIONS = [
    "📊 <b>Еженедельная статистика (Часть 1/3)</b> 📊\n\nКлассическая аналитика из глубин базы данных: активность, уникальные шизы, байтеры и форматы общения.\nСмотри графики в альбоме 👇",
    "🧠 <b>Продвинутая Аналитика (Часть 2/3)</b> 🧠\n\nГлубокий разбор: граф социального пузыря, хабы внимания, сессии, циркадные ритмы шизофрении, сентимент и лексический запас.\nСмотри продолжение 👇",
    "🔥 <b>Ритмы и Тепловые Карты (Часть 3/3)</b> 🔥\n\nНовые графики: усредненная тепловая карта час × день за полгода, недельный Ridge-ритм, круговой циферблат активности и GitHub-style календарь за полгода.\nСмотри финал 👇"
]


def caption_for(chunk_idx: int) -> str:
    """Подпись для альбома по его порядковому номеру."""
    if chunk_idx < len(CAPTIONS):
        return CAPTIONS[chunk_idx]
    return f"📊 <b>Статистика Борды (Часть {chunk_idx + 1})</b> 📊"


def build_stats_media_groups(stats_data: dict) -> list:
    """
    Takes raw stats data and groups them into media items for Telegram.
    """
    if not stats_data:
        return []

    groups = []
    current_group = []

    for key, value in stats_data.items():
        if len(current_group) >= MEDIA_GROUP_MAX_ITEMS:
            groups.append(current_group)
            current_group = []
        current_group.append((key, value))

    if current_group:
        groups.append(current_group)

    return groups


def _drain_chart_buffers(images: Sequence[tuple]) -> list[tuple[str, bytes]]:
    """
    Вытягивает байты из BytesIO графиков и закрывает буферы.

    generate_all_charts отдаёт 30 открытых BytesIO. Раньше их только читали
    (buf.read()), из-за чего исходные буферы жили до GC параллельно с копией
    байтов — двойной расход RAM на каждый прогон. Здесь закрываем сразу.

    Дубликаты имён не схлопываем: dict(images) молча терял бы график.
    """
    drained: list[tuple[str, bytes]] = []
    used: set[str] = set()
    dup_counter: dict[str, int] = {}
    for entry in images:
        if not entry or len(entry) != 2:
            logger.warning("Пропущен некорректный элемент графиков: %r", entry)
            continue
        name, buf = entry
        try:
            buf.seek(0)
            payload = buf.read()
        except Exception as e:
            logger.warning("Не удалось прочитать буфер графика %s: %s", name, e)
            continue
        finally:
            try:
                buf.close()
            except Exception:
                import traceback; traceback.print_exc()
        if not payload:
            logger.warning("Пустой буфер графика %s, пропускаю.", name)
            continue

        # Разводим одинаковые имена, чтобы ни один график не потерялся.
        # Проверяем занятость в цикле: с одним счётчиком набор
        # ('a.png', 'a.png', 'a_1.png') давал 'a_1.png' дважды, и dict() в
        # get_stats_media_groups снова терял график — ровно то, от чего эта
        # ветка и защищает.
        if name in used:
            stem, _, ext = str(name).rpartition('.')
            counter = dup_counter.get(name, 0)
            candidate = name
            while candidate in used:
                counter += 1
                candidate = f"{stem}_{counter}.{ext}" if stem else f"{name}_{counter}"
            dup_counter[name] = counter
            name = candidate
        used.add(name)
        drained.append((name, payload))
    return drained


async def get_stats_media_groups():
    """Generates the stats and builds a list of aiogram MediaGroups (max 10 items each)."""
    async with _chart_generation_lock:
        images = await asyncio.to_thread(generate_all_charts)

    if not images:
        return []

    stats_data = dict(_drain_chart_buffers(images))
    image_chunks = build_stats_media_groups(stats_data)

    groups = []

    for chunk_idx, chunk in enumerate(image_chunks):
        media_group = []
        caption = caption_for(chunk_idx)

        for i, (name, payload) in enumerate(chunk):
            input_file = BufferedInputFile(payload, filename=name)
            if i == 0:
                media_group.append(InputMediaPhoto(media=input_file, caption=caption, parse_mode="HTML"))
            else:
                media_group.append(InputMediaPhoto(media=input_file))
        groups.append(media_group)

    return groups


async def _send_media_group_resilient(
    bot: Bot,
    chat_id: int,
    media: list,
    *,
    attempts: int = ARCHIVE_UPLOAD_ATTEMPTS,
    context: str = "",
):
    """
    Отправляет альбом, переживая flood-wait и сетевые сбои.

    Возвращает список Message при успехе, None если доставка невозможна
    (пользователь заблокировал бота / чат недоступен / лимит попыток исчерпан).
    Никогда не поднимает исключение наружу — один упавший получатель не должен
    ронять всю недельную публикацию.
    """
    for attempt in range(1, attempts + 1):
        try:
            return await asyncio.wait_for(
                bot.send_media_group(chat_id=chat_id, media=media),
                timeout=BROADCAST_SEND_TIMEOUT,
            )
        except TelegramRetryAfter as e:
            delay = min(float(getattr(e, "retry_after", 5) or 5) + 1.0, BROADCAST_MAX_RETRY_AFTER)
            logger.warning("Flood-wait %ss на %s (%s), попытка %s/%s", delay, chat_id, context, attempt, attempts)
            await asyncio.sleep(delay)
        except TelegramForbiddenError:
            # Заблокировал бота / удалил чат — ретраить бессмысленно.
            return None
        except TelegramBadRequest as e:
            logger.warning("BadRequest на %s (%s): %s", chat_id, context, e)
            return None
        except (TelegramNetworkError, asyncio.TimeoutError) as e:
            logger.warning("Сетевой сбой на %s (%s): %s, попытка %s/%s",
                           chat_id, context, type(e).__name__, attempt, attempts)
            await asyncio.sleep(min(2 ** attempt, 30))
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning("Неожиданная ошибка отправки на %s (%s): %s: %s",
                           chat_id, context, type(e).__name__, e)
            return None
    return None


def _apply_album_caption(media_group: Sequence[Any], chunk_idx: int) -> None:
    """
    Ставит подпись на первый элемент альбома.

    Терпит элементы, которым нельзя присвоить caption/parse_mode: раньше один
    некорректный элемент ронял AttributeError, который ловил внешний
    except Exception — и ни один альбом не уходил, включая копию в архив.
    Лучше отправить альбом без подписи, чем потерять всю публикацию.
    """
    if not media_group:
        return
    first = media_group[0]
    try:
        first.caption = caption_for(chunk_idx)
        first.parse_mode = "HTML"
    except (AttributeError, TypeError, ValueError) as e:
        logger.warning("Не удалось проставить подпись для части %s (%s): %s",
                       chunk_idx + 1, type(first).__name__, e)


def _rewind_media_group(media_group: Iterable[InputMediaPhoto]) -> None:
    """
    Перематывает файловые буферы перед повторной загрузкой того же альбома.

    Для BufferedInputFile это no-op (media.data — обычные bytes, aiogram отдаёт
    их заново), но объект может прийти и как файловый поток.
    """
    for item in media_group:
        media = getattr(item, "media", None)
        data = getattr(media, "data", None)
        if hasattr(data, "seek"):
            try:
                data.seek(0)
            except Exception:
                import traceback; traceback.print_exc()
        elif hasattr(media, "seek"):
            try:
                media.seek(0)
            except Exception:
                import traceback; traceback.print_exc()


async def send_stats_to_user(bot: Bot, chat_id: int):
    """Generates and sends stats directly to a user/admin, and copies them to the archive."""
    await bot.send_message(chat_id, "⏳ <i>Рисую 30 графиков вашей деградации (погоди пару секунд)...</i>", parse_mode="HTML")
    try:
        media_groups = await get_stats_media_groups()
        if not media_groups:
            await bot.send_message(chat_id, "❌ Хуй там плавал, стату собрать не вышло.")
            return

        for idx, media_group in enumerate(media_groups):
            if not media_group:
                continue
            _apply_album_caption(media_group, idx)
            await _send_media_group_resilient(bot, chat_id, media_group, context=f"part{idx + 1}")
            await asyncio.sleep(1)

        # Send a copy to the Archive Channel if not already there
        archive_channel_id = int(os.getenv("ARCHIVE_CHANNEL_ID", -1002827087363))
        if chat_id != archive_channel_id:
            print(f"📊 Отправляю копию графиков в архивный канал {archive_channel_id}...")
            for idx, media_group in enumerate(media_groups):
                if not media_group:
                    continue
                _rewind_media_group(media_group)
                await _send_media_group_resilient(
                    bot, archive_channel_id, media_group, context=f"archive-part{idx + 1}"
                )
                await asyncio.sleep(1)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.exception("send_stats_to_user failed")
        try:
            await bot.send_message(chat_id, f"❌ Ошибка при генерации статистики: {e}")
        except Exception:
            import traceback; traceback.print_exc()


def _seconds_until_next_sunday_2000(now_msk: datetime) -> tuple[datetime, float]:
    """Возвращает (целевое время MSK, сколько секунд спать) до ближайшего вс 20:00."""
    days_ahead = 6 - now_msk.weekday()  # Monday==0 ... Sunday==6
    if days_ahead < 0 or (days_ahead == 0 and now_msk.hour >= 20):
        days_ahead += 7
    target_time = (now_msk + timedelta(days=days_ahead)).replace(
        hour=20, minute=0, second=0, microsecond=0
    )
    return target_time, max(0.0, (target_time - now_msk).total_seconds())


def _snapshot_active_users(active_users_getter: Callable[[], Any]) -> list[int]:
    """
    Снимает СТАБИЛЬНУЮ копию списка получателей.

    Геттер отдаёт живой set из board_data, который хендлеры мутируют на каждом
    входящем посте. Итерирование его напрямую во время многоминутной рассылки
    роняло весь паблишер через "Set changed size during iteration".
    """
    try:
        raw = active_users_getter()
    except Exception:
        logger.exception("active_users_getter failed")
        return []
    if not raw:
        return []
    try:
        candidates = list(raw)  # копия снимается здесь, до первого await
    except RuntimeError:
        # Множество изменилось прямо во время копирования — повторяем один раз.
        try:
            candidates = list(raw)
        except Exception:
            logger.exception("не удалось снять снапшот активных пользователей")
            return []
    return [uid for uid in candidates if isinstance(uid, int) and not isinstance(uid, bool) and uid > 0]


def _build_file_id_media_group(file_ids: Sequence[str], group_idx: int) -> list[InputMediaPhoto]:
    """Собирает альбом из уже загруженных file_id (без повторной заливки байтов)."""
    caption = caption_for(group_idx)
    return [
        InputMediaPhoto(media=file_id, caption=caption, parse_mode="HTML") if i == 0
        else InputMediaPhoto(media=file_id)
        for i, file_id in enumerate(file_ids)
    ]


async def _upload_to_archive(archive_bot: Bot, archive_channel_id: int, media_groups: list) -> list[list[str]]:
    """Заливает альбомы в архивный канал и возвращает file_id для дешёвой пересылки."""
    uploaded_groups_file_ids: list[list[str]] = []
    for group_idx, media_group in enumerate(media_groups):
        _rewind_media_group(media_group)
        messages = await _send_media_group_resilient(
            archive_bot, archive_channel_id, media_group, context=f"archive-part{group_idx + 1}"
        )
        if not messages:
            logger.warning("Не удалось залить часть %s в архив, пропускаю её в рассылке.", group_idx + 1)
            continue
        group_file_ids = [m.photo[-1].file_id for m in messages if m.photo]
        if group_file_ids:
            uploaded_groups_file_ids.append(group_file_ids)
        await asyncio.sleep(1)
    return uploaded_groups_file_ids


async def _broadcast_to_users(b_bot: Bot, recipients: Sequence[int], uploaded_groups_file_ids: list[list[str]]) -> tuple[int, int]:
    """Рассылает готовые альбомы. Возвращает (доставлено, не доставлено)."""
    prebuilt = [
        _build_file_id_media_group(file_ids, idx)
        for idx, file_ids in enumerate(uploaded_groups_file_ids)
    ]
    delivered = 0
    failed = 0
    for user_id in recipients:
        user_ok = True
        for group_idx, media_group in enumerate(prebuilt):
            result = await _send_media_group_resilient(
                b_bot, user_id, media_group, context=f"broadcast-part{group_idx + 1}"
            )
            if result is None:
                user_ok = False
                break  # заблокировал бота или чат мёртв — не долбим остальными частями
            await asyncio.sleep(BROADCAST_DELAY_BETWEEN_GROUPS)
        if user_ok:
            delivered += 1
        else:
            failed += 1
        await asyncio.sleep(BROADCAST_DELAY_BETWEEN_USERS)
    return delivered, failed


async def periodic_stats_publisher(bots: dict, active_users_getter):
    """
    Runs in the background and publishes stats every Sunday at 20:00 MSK.
    Sends to the archive channel and broadcasts to all active users on board /b/.
    """
    ARCHIVE_CHANNEL_ID = int(os.getenv("ARCHIVE_CHANNEL_ID", -1002827087363))

    while True:
        now_msk = datetime.now(timezone.utc).astimezone(MSK_OFFSET)
        target_time, sleep_seconds = _seconds_until_next_sunday_2000(now_msk)

        print(f"📊 [STATS PUBLISHER] Следующая публикация статистики запланирована на "
              f"{target_time.strftime('%Y-%m-%d %H:%M:%S')} MSK (через {sleep_seconds / 3600:.1f} часов)")

        await asyncio.sleep(sleep_seconds)

        # Wake up and publish
        print("📊 [STATS PUBLISHER] Время публикации статистики! Генерирую графики...")
        try:
            if not bots:
                print("❌ [STATS PUBLISHER] Нет ни одного бота, пропускаю публикацию.")
                await asyncio.sleep(POST_PUBLISH_COOLDOWN)
                continue

            media_groups = await get_stats_media_groups()
            if not media_groups:
                print("❌ [STATS PUBLISHER] Ошибка: нет данных для графиков.")
                await asyncio.sleep(POST_PUBLISH_COOLDOWN)
                continue

            archive_bot = bots.get('test') or bots.get('b') or next(iter(bots.values()))

            # 1. Send to ARCHIVE_CHANNEL_ID (collect file_ids to avoid uploading multiple times)
            print(f"📊 [STATS PUBLISHER] Отправляю графики в архивный канал {ARCHIVE_CHANNEL_ID}...")
            uploaded_groups_file_ids = await _upload_to_archive(archive_bot, ARCHIVE_CHANNEL_ID, media_groups)

            if not uploaded_groups_file_ids:
                print("❌ [STATS PUBLISHER] Ни одна часть не залилась в архив, рассылка отменена.")
                await asyncio.sleep(POST_PUBLISH_COOLDOWN)
                continue

            print(f"✅ [STATS PUBLISHER] Графики успешно отправлены в архивный канал "
                  f"({len(uploaded_groups_file_ids)} частей).")

            # Освобождаем ~30 PNG из RAM: дальше рассылаем по file_id.
            media_groups.clear()

            # 2. Broadcast to all active users on board /b/
            recipients = _snapshot_active_users(active_users_getter)
            b_bot = bots.get('b') or next(iter(bots.values()))

            if b_bot and recipients:
                print(f"📊 [STATS PUBLISHER] Рассылаю графики {len(recipients)} активным пользователям /b/...")
                delivered, failed = await _broadcast_to_users(b_bot, recipients, uploaded_groups_file_ids)
                print(f"✅ [STATS PUBLISHER] Рассылка завершена: доставлено {delivered}, не доставлено {failed}.")
            else:
                print("ℹ️ [STATS PUBLISHER] Активных получателей нет, рассылка пропущена.")

            print("✅ [STATS PUBLISHER] Еженедельная публикация статистики завершена!")
        except asyncio.CancelledError:
            print("ℹ️ [STATS PUBLISHER] Задача остановлена.")
            raise
        except Exception as e:
            logger.exception("periodic_stats_publisher failed")
            print(f"❌ [STATS PUBLISHER] Ошибка при публикации: {e}")

        # Sleep an extra hour to avoid double-triggering
        await asyncio.sleep(POST_PUBLISH_COOLDOWN)
