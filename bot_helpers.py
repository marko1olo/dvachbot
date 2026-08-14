import asyncio
from shared_state import *
from aiogram import types
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest
from common.task_manager import spawn_task

import random
from datetime import datetime, timezone
UTC = timezone.utc
from post_helpers import create_post, format_header
from common.database import delete_post_by_num

from common.database import update_board_settings
from post_helpers import update_post_content

async def _activate_mode(board_id: str, mode_to_enable: str):
    """
    Активирует режим. Не трогает закрепы и другие настройки.
    """
    all_modes = MODE_FLAGS
    async with storage_lock:
        b_data = board_data[board_id]
        if b_data.get('active_mode_task') and not b_data['active_mode_task'].done():
            b_data['active_mode_task'].cancel()
        for mode in all_modes:
            b_data[mode] = (mode == mode_to_enable)
        b_data['last_mode_activation'] = datetime.now(UTC)
    settings_updates = {mode: (mode == mode_to_enable) for mode in all_modes}
    await update_board_settings(board_id, settings_updates)
    print(f"DB: [{board_id}] Режим {mode_to_enable} активирован.")

async def check_cooldown(message: Message, board_id: str) -> bool:

    if board_id == 'trash':
        return True # Для доски-мусорки кулдауна нет, всегда разрешаем
    b_data = board_data[board_id]
    last_activation = b_data.get('last_mode_activation')
    if last_activation is None:
        return True
    elapsed = (datetime.now(UTC) - last_activation).total_seconds()
    if elapsed < MODE_COOLDOWN:
        time_left = MODE_COOLDOWN - elapsed
        minutes = int(time_left // 60)
        seconds = int(time_left % 60)
        lang = 'en' if board_id == 'int' else 'ru'
        if lang == 'en':
            phrases = [
                "⏳ Hey faggot, slow down! Modes on this board can be switched once per hour.\nWait for: {minutes} minutes {seconds} seconds.",
                "⌛️ Cool down, cowboy. The mode switch is on cooldown.\nTime left: {minutes}m {seconds}s.",
                "⛔️ You're switching modes too often, cunt. Wait another {minutes} minutes {seconds} seconds.",
                "⚠️ Wait, I need to rest. You can switch modes in {minutes}m {seconds}s."
            ]
        else:
            phrases = [
                "⏳ Эй пидор, не спеши! Режимы на этой доске можно включать раз в час.\nЖди еще: {minutes} минут {seconds} секунд\n\nА пока посиди в углу и подумай о своем поведении.",
                "⌛️ Остынь, ковбой. Кулдаун на смену режима еще не прошел.\nОсталось: {minutes}м {seconds}с.",
                "⛔️ Слишком часто меняешь режимы, заебал. Подожди еще {minutes} минут {seconds} секунд.",
                "⚠️ Подожди, я отдохну. Режимы можно будет переключить через {minutes}м {seconds}с.",
                "💤 Пора отдохнуть с режимами, не мешай мне. Я устал.",
                "О, боже, как же я устал от этих режимов. Иди отдохни."
            ]
        text = random.choice(phrases).format(minutes=minutes, seconds=seconds)
        try:
            sent_msg = await message.answer(text, parse_mode="HTML")
            spawn_task(delete_message_after_delay(sent_msg, 11))
        except Exception:
            import traceback; traceback.print_exc()
        try:
            await message.delete()
        except TelegramBadRequest:
            import traceback; traceback.print_exc()     
        return False
    return True

async def disable_mode_after_delay(delay: int, board_id: str, mode_to_disable: str):
    """
    Универсальная функция для отключения любого режима по таймеру.
    """
    await asyncio.sleep(delay)
    stream = 'en' if board_id == 'int' else 'ru'
    all_modes = MODE_FLAGS
    try:
        import main
        mode_end_dict = getattr(main, 'MODE_END_PHRASES', {})
    except Exception:
        mode_end_dict = {}
    phrases = mode_end_dict.get(mode_to_disable, ["Режим отключен."])
    end_text = random.choice(phrases) if isinstance(phrases, list) else "Режим отключен."
    now_dt = datetime.now(UTC)
    content = {"type": "text", "text": end_text, "is_system_message": True, "archive_allowed": True}
    pnum = await create_post(
        board_id=board_id, 
        author_id=0, 
        content=content, 
        timestamp=now_dt.timestamp(), 
        is_from_site=False, 
        stream=stream 
    )
    if not pnum: return
    recipients = None
    # Под локом только то, что он и должен охранять. Проверка «режим ещё
    # активен» и сброс флагов остаются АТОМАРНЫМИ — иначе две задачи отключения
    # одного режима отработали бы дважды. А delete_post_by_num и format_header
    # это обращения к БД: раньше они выполнялись УДЕРЖИВАЯ storage_lock, то есть
    # фоновая задача блокировала доставку и реакции на всех досках на время
    # двух запросов к базе.
    async with storage_lock:
        b_data = board_data[board_id]
        mode_was_active = bool(b_data.get(mode_to_disable, False))
        if mode_was_active:
            for mode in all_modes:
                b_data[mode] = False
            b_data['active_mode_task'] = None
            recipients = b_data['users']['active']
    if not mode_was_active:
        await delete_post_by_num(pnum)
        return
    header = await format_header(board_id, pnum)
    prefix = "### ADMIN ###" if board_id == 'int' else "### Админ ###"
    content['header'] = f"{prefix}\n{header}"
    async with storage_lock:
        messages_storage[pnum] = {'author_id': 0, 'timestamp': now_dt, 'content': content, 'board_id': board_id}
    settings_updates = {mode: False for mode in all_modes}
    await update_board_settings(board_id, settings_updates)
    await update_post_content(pnum, content)
    if recipients:
        from delivery_manager import enqueue_board_message
        await enqueue_board_message(board_id, {"recipients": recipients, "content": content, "post_num": pnum, "board_id": board_id})

async def delete_message_after_delay(message: types.Message, delay: int):

    try:
        await asyncio.sleep(delay)
        await asyncio.wait_for(message.delete(), timeout=15.0)
    except asyncio.CancelledError:
        import traceback; traceback.print_exc()
    except asyncio.TimeoutError:
        print(f"⚠️ Таймаут при удалении сообщения {message.message_id} в чате {message.chat.id}")
    except Exception as e:
        if "message to delete not found" not in str(e).lower():
            print(f"🔥 Непредвиденная ошибка в delete_message_after_delay: {type(e).__name__}: {e}")

async def send_moderation_notice(user_id: int, action: str, board_id: str, duration: str = None, deleted_posts: int = 0, stream: str = 'ru'):

    b_data = board_data[board_id]
    if not b_data['users']['active']:
        return
    lang = 'en' if board_id == 'int' else 'ru'
    text = ""
    if action == "ban":
        if lang == 'en':
            ban_phrases = [
                f"🚨 A faggot has been banned for spam. RIP.",
                f"☠️ Another spammer bites the dust. Good riddance.",
                f"🔨 The ban hammer has spoken. A degenerate was removed.",
                f"✈️ Sent a spammer on a one-way trip to hell."
            ]
        elif lang == 'jp':
            ban_phrases = [
                f"🚨 ホモ野郎がスパムでBANされたぞ。ナムアミダブツ。",
                f"☠️ またスパム野郎が塵になった。せいせいするぜ。",
                f"🔨 BANハンマーが下された。変質者が一人消えたな。",
                f"✈️ スパム野郎を地獄への片道旅行に送り出したぞ。"
            ]
        else:
            ban_phrases = [
                f"🚨 Хуесос был забанен за спам. Помянем.",
                f"☠️ Мир стал чище, еще один спамер отлетел в бан.",
                f"🔨 Банхаммер опустился на голову очередного дегенерата.",
                f"✈️ Отправили спамера в увлекательное путешествие нахуй!",
            ]
        text = random.choice(ban_phrases)
        #spawn_task(log_global_event('bot', f"🔨 {board_id.upper()}: {text} (User: {user_id})"))
    elif action == "mute":
        if lang == 'en':
            mute_phrases = [
                f"🔇 A loudmouth has been muted for a while.",
                f"🤫 Someone's got a timeout. Let's enjoy the silence.",
                f"🤐 Put a sock in it! A user has been temporarily silenced.",
                f"⌛️ A faggot is in the penalty box for a bit."
            ]
        elif lang == 'jp':
            mute_phrases = [
                f"🔇 クソうるさい奴をしばらく黙らせたぞ。",
                f"🤫 タイムアウトだ。静寂を楽しもうぜ。",
                f"🤐 靴下でも詰めとけ！ユーザーが一時的にミュートされた。",
                f"⌛️ ホモ野郎はお仕置き部屋行きだ。"
            ]
        else:
            mute_phrases = [
                f"🔇 Пидораса замутили ненадолго.",
                f"🤫 Наслаждаемся тишиной, хуеглот временно не может писать.",
                f"Молчание - золото. Пидор будет тихим.",
                f"🤐 Анон отправлен в угол подумать о своем поведении.",
                f"⌛️ Пидору выписали временный запрет на открытие рта.",
                f"🕒 Пидор будет молчать до лучших времен.",
                f"На время он будет тихим, как мышь. Ожидаем его возвращения."
            ]
        text = random.choice(mute_phrases)
    else:
        return
    now_dt = datetime.now(UTC)
    content = {
        'type': 'text',
        'text': text,
        'is_system_message': True
    }
    post_num = await create_post(
        board_id=board_id,
        author_id=0,
        content=content,
        timestamp=now_dt.timestamp(),
        is_from_site=False, stream=stream
    )
    if not post_num:
        print(f"⛔ [{board_id}] Не удалось создать пост в БД для send_moderation_notice.")
        return
    header = await format_header(board_id, post_num)
    header = f"### Админ ###\n{header}"
    content['header'] = header
    await update_post_content(post_num, content)
    async with storage_lock:
        messages_storage[post_num] = {
            'author_id': 0,
            'timestamp': now_dt,
            'content': content,
            'board_id': board_id
        }
    from delivery_manager import enqueue_board_message
    await enqueue_board_message(board_id, {
        "recipients": b_data["users"]["active"],
        "content": content,
        "post_num": post_num,
        "board_id": board_id
    })

async def process_shadow_reject(ctx: ShadowRejectContext):

    """
    Эмулирует успешную публикацию поста, но отправляет его ТОЛЬКО автору.
    Не пишет в БД, не увеличивает счетчики.
    """
    shadow_key = (ctx.board_id, ctx.user_id)
    current_floor = state['post_counter'] + random.randint(1, 3)
    last_fake_post_num = shadow_fake_post_counters.get(shadow_key, 0)
    fake_post_num = max(current_floor, last_fake_post_num + random.randint(1, 3))
    shadow_fake_post_counters[shadow_key] = fake_post_num
    header_text = await format_header(ctx.board_id, fake_post_num, ctx.user_id, stream=ctx.stream)
    user_content = ctx.content.copy()
    user_content['header'] = header_text
    user_content['post_num'] = fake_post_num
    user_content['is_shadow_reject'] = True
    user_content['reply_to_post'] = ctx.reply_to_post
    await asyncio.sleep(random.uniform(0.5, 1.5))
    await send_message_to_users(BroadcastConfig(
        bot_instance=ctx.bot,
        board_id=ctx.board_id,
        recipients={ctx.user_id}, # Только автор!
        content=user_content,
        reply_info=None
    ))
    print(f"👻 [SHADOW] Теневой отброс медиа от {ctx.user_id} на доске {ctx.board_id}")

def detect_media_type(data: bytes, url: str) -> str:
    """
    Определяет тип медиа (photo/video/animation) по заголовку файла или URL.
    """
    header = data[:12]
    url_lower = url.lower()
    if b'ftyp' in header or header.startswith(b'\x1A\x45\xDF\xA3'):
        return 'video'
    if header.startswith(b'GIF8'):
        return 'animation'
    if url_lower.endswith('.mp4') or url_lower.endswith('.webm') or url_lower.endswith('.mov'):
        return 'video'
    if url_lower.endswith('.gif'):
        return 'animation'
    return 'photo'

async def _safe_delete_user_message(message: types.Message):
    try:
        if (datetime.now(UTC) - message.date).total_seconds() < 48 * 3600:
            await message.delete()
    except TelegramBadRequest:
        import traceback; traceback.print_exc()

NICK_PREFIXES = ["Базированный", "Всратый", "Мамкин", "Поехавший", "Соевый", "Диванный", "Опущенный", "Гойский", "Толстый", "Порватый", "Латентный", "Просветленный", "Элитный", "Подпивасный", "Двачевский", "Педальный", "Токсичный", "Кринжовый", "Аутичный", "Думерский", "Рядовой", "Школьный", "Отбитый", "Метаироничный", "Скрытый", "Сигма", "Альфа", "Омега", "Сажный", "Вайбовый", "Копиумный", "Попущенный", "Лютый", "Абсолютный", "Печальный", "Нищуковский", "Душный", "Шизоидный", "Паленый", "Забивной", "Плюшевый", "Астральный", "Комнатный"]
NICK_SUFFIXES = ["Битард", "Скуф", "Шиз", "Анон", "Ньюфаг", "Олдфаг", "Омеган", "Шитпостер", "Сыч", "Двачер", "Чухан", "Куколд", "Нормис", "Гигачад", "Подпивас", "Зумер", "Бумер", "Сояк", "Инцел", "Думер", "Говноед", "Симп", "Чмоня", "Байтер", "Ноулайфер", "Тролль", "Моралфаг", "Альтушка", "Масик", "Школьник", "Дед", "Хиккан", "Скуфидон", "Терпила", "Вахтер", "Тентакль", "Мыслитель", "Философ", "Дворник", "Эрудит", "Чел"]

def generate_anon_name(user_id: int) -> str:
    if not user_id: return "Анонимус"
    rng = random.Random(user_id)
    prefix = rng.choice(NICK_PREFIXES)
    suffix = rng.choice(NICK_SUFFIXES)
    return f"{prefix}-{suffix} (#{str(user_id)[-4:]})"

async def git_commit_and_push_db() -> bool:

    if not GITHUB_TOKEN:
        print("⚠️ GITHUB_TOKEN не настроен, бэкап в облако невозможен.")
        return False
    asyncio.get_running_loop()
    return False # await loop.run_in_executor(git_executor, sync_git_operations_db, GITHUB_TOKEN)

def is_admin(uid: int, board_id: str) -> bool:

    if not board_id:
        return False
    from site_tgach.admin_config import ADMIN_IDS
    if uid in ADMIN_IDS:
        return True
    from common.board_config import BOARD_CONFIG
    bconf = BOARD_CONFIG.get(board_id, {})
    admins = bconf.get('admins', [])
    return uid in admins


async def send_moderation_notice(user_id: int, action: str, board_id: str, duration: str = None, deleted_posts: int = 0, stream: str = 'ru'):

    b_data = board_data[board_id]
    if not b_data['users']['active']:
        return
    lang = 'en' if board_id == 'int' else 'ru'
    text = ""
    if action == "ban":
        if lang == 'en':
            ban_phrases = [
                f"🚨 A faggot has been banned for spam. RIP.",
                f"☠️ Another spammer bites the dust. Good riddance.",
                f"🔨 The ban hammer has spoken. A degenerate was removed.",
                f"✈️ Sent a spammer on a one-way trip to hell."
            ]
        elif lang == 'jp':
            ban_phrases = [
                f"🚨 ホモ野郎がスパムでBANされたぞ。ナムアミダブツ。",
                f"☠️ またスパム野郎が塵になった。せいせいするぜ。",
                f"🔨 BANハンマーが下された。変質者が一人消えたな。",
                f"✈️ スパム野郎を地獄への片道旅行に送り出したぞ。"
            ]
        else:
            ban_phrases = [
                f"🚨 Хуесос был забанен за спам. Помянем.",
                f"☠️ Мир стал чище, еще один спамер отлетел в бан.",
                f"🔨 Банхаммер опустился на голову очередного дегенерата.",
                f"✈️ Отправили спамера в увлекательное путешествие нахуй!",
            ]
        text = random.choice(ban_phrases)
        spawn_task(log_global_event('bot', f"🔨 {board_id.upper()}: {text} (User: {user_id})"))
    elif action == "mute":
        if lang == 'en':
            mute_phrases = [
                f"🔇 A loudmouth has been muted for a while.",
                f"🤫 Someone's got a timeout. Let's enjoy the silence.",
                f"🤐 Put a sock in it! A user has been temporarily silenced.",
                f"⌛️ A faggot is in the penalty box for a bit."
            ]
        elif lang == 'jp':
            mute_phrases = [
                f"🔇 クソうるさい奴をしばらく黙らせたぞ。",
                f"🤫 タイムアウトだ。静寂を楽しもうぜ。",
                f"🤐 靴下でも詰めとけ！ユーザーが一時的にミュートされた。",
                f"⌛️ ホモ野郎はお仕置き部屋行きだ。"
            ]
        else:
            mute_phrases = [
                f"🔇 Пидораса замутили ненадолго.",
                f"🤫 Наслаждаемся тишиной, хуеглот временно не может писать.",
                f"Молчание - золото. Пидор будет тихим.",
                f"🤐 Анон отправлен в угол подумать о своем поведении.",
                f"⌛️ Пидору выписали временный запрет на открытие рта.",
                f"🕒 Пидор будет молчать до лучших времен.",
                f"На время он будет тихим, как мышь. Ожидаем его возвращения."
            ]
        text = random.choice(mute_phrases)
    else:
        return
    now_dt = datetime.now(UTC)
    content = {
        'type': 'text',
        'text': text,
        'is_system_message': True
    }
    post_num = await create_post(
        board_id=board_id,
        author_id=0,
        content=content,
        timestamp=now_dt.timestamp(),
        is_from_site=False, stream=stream
    )
    if not post_num:
        print(f"⛔ [{board_id}] Не удалось создать пост в БД для send_moderation_notice.")
        return
    header = await format_header(board_id, post_num)
    header = f"### Админ ###\n{header}"
    content['header'] = header
    await update_post_content(post_num, content)
    async with storage_lock:
        messages_storage[post_num] = {
            'author_id': 0,
            'timestamp': now_dt,
            'content': content,
            'board_id': board_id
        }
    from delivery_manager import enqueue_board_message
    await enqueue_board_message(board_id, {
        "recipients": b_data["users"]["active"],
        "content": content,
        "post_num": post_num,
        "board_id": board_id
    })

async def process_shadow_reject(ctx: ShadowRejectContext):

    """
    Эмулирует успешную публикацию поста, но отправляет его ТОЛЬКО автору.
    Не пишет в БД, не увеличивает счетчики.
    """
    shadow_key = (ctx.board_id, ctx.user_id)
    current_floor = state['post_counter'] + random.randint(1, 3)
    last_fake_post_num = shadow_fake_post_counters.get(shadow_key, 0)
    fake_post_num = max(current_floor, last_fake_post_num + random.randint(1, 3))
    shadow_fake_post_counters[shadow_key] = fake_post_num
    header_text = await format_header(ctx.board_id, fake_post_num, ctx.user_id, stream=ctx.stream)
    user_content = ctx.content.copy()
    user_content['header'] = header_text
    user_content['post_num'] = fake_post_num
    user_content['is_shadow_reject'] = True
    user_content['reply_to_post'] = ctx.reply_to_post
    await asyncio.sleep(random.uniform(0.5, 1.5))
    await send_message_to_users(BroadcastConfig(
        bot_instance=ctx.bot,
        board_id=ctx.board_id,
        recipients={ctx.user_id}, # Только автор!
        content=user_content,
        reply_info=None
    ))
    print(f"👻 [SHADOW] Теневой отброс медиа от {ctx.user_id} на доске {ctx.board_id}")

def detect_media_type(data: bytes, url: str) -> str:
    """
    Определяет тип медиа (photo/video/animation) по заголовку файла или URL.
    """
    header = data[:12]
    url_lower = url.lower()
    if b'ftyp' in header or header.startswith(b'\x1A\x45\xDF\xA3'):
        return 'video'
    if header.startswith(b'GIF8'):
        return 'animation'
    if url_lower.endswith('.mp4') or url_lower.endswith('.webm') or url_lower.endswith('.mov'):
        return 'video'
    if url_lower.endswith('.gif'):
        return 'animation'
    return 'photo'

def _prepare_anime_content(successful_downloads: list, caption: str) -> dict:
    from aiogram.types import BufferedInputFile
    content = {}
    if len(successful_downloads) == 1:
        ibytes, mtype, ext = successful_downloads[0]
        input_file = BufferedInputFile(ibytes, filename=f"file.{ext}")
        content = {'type': mtype, 'media': input_file, 'caption': caption}
        if mtype == 'video' or mtype == 'animation':
             content = {'type': mtype, 'file_id': input_file, 'caption': caption}
        else:
             content = {'type': mtype, 'image_bytes': ibytes, 'caption': caption}
    else:
        media_items = []
        for ibytes, mtype, ext in successful_downloads:
            tg_type = 'video' if mtype in ['video', 'animation'] else 'photo'
            input_file = BufferedInputFile(ibytes, filename=f"file.{ext}")
            media_items.append({'type': tg_type, 'media': input_file})

        content = {'type': 'media_group', 'media': media_items, 'caption': caption}
    return content

async def _safe_delete_user_message(message: types.Message):
    try:
        if (datetime.now(UTC) - message.date).total_seconds() < 48 * 3600:
            await message.delete()
    except TelegramBadRequest:
        import traceback; traceback.print_exc()

async def git_commit_and_push_db() -> bool:

    if not GITHUB_TOKEN:
        print("⚠️ GITHUB_TOKEN не настроен, бэкап в облако невозможен.")
        return False
    asyncio.get_running_loop()
    return False # await loop.run_in_executor(git_executor, sync_git_operations_db, GITHUB_TOKEN)

async def get_author_id_by_reply(msg: types.Message) -> int | None:
    if not msg.reply_to_message:
        return None
    target_chat_id = msg.reply_to_message.chat.id
    reply_mid = msg.reply_to_message.message_id
    lookup_key = (target_chat_id, reply_mid)
    async with storage_lock:
        post_num = message_to_post.get(lookup_key)
        if post_num and post_num in messages_storage:
            return messages_storage[post_num].get("author_id")
    if not post_num:
        info = await get_post_info_by_copy(target_chat_id, reply_mid)
        if info:
            post_num = info[0]
    if post_num:
        db_post = await get_post_by_num(post_num)
        if db_post and 'author_id' in db_post:
            return db_post['author_id']
    db_author_id = await get_post_author_by_copy(target_chat_id, reply_mid)
    if db_author_id is not None:
        return db_author_id
    return None

def get_help_keyboard(category: str, board_id: str, stream: str = 'ru') -> InlineKeyboardMarkup:
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    
    if category == "main":
        if lang == 'en':
            builder.button(text="🛠 Moderation", callback_data="help:mod")
            builder.button(text="🎲 Fun", callback_data="help:fun")
            builder.button(text="⚙️ Settings", callback_data="help:settings")
            builder.button(text="💬 Chat", callback_data="help:chat")
            builder.button(text="💰 Economy", callback_data="help:economy")
        elif lang == 'jp':
            builder.button(text="🛠 モデレーション", callback_data="help:mod")
            builder.button(text="🎲 遊び", callback_data="help:fun")
            builder.button(text="⚙️ 設定", callback_data="help:settings")
            builder.button(text="💬 チャット", callback_data="help:chat")
            builder.button(text="💰 経済", callback_data="help:economy")
        else:
            builder.button(text="🛠 Модерация", callback_data="help:mod")
            builder.button(text="🎲 Развлечения", callback_data="help:fun")
            builder.button(text="⚙️ Настройки", callback_data="help:settings")
            builder.button(text="💬 Общение", callback_data="help:chat")
            builder.button(text="💰 Экономика", callback_data="help:economy")
        builder.adjust(2, 2, 1)
    else:
        btn_back = "⬅️ Back" if lang == 'en' else ("⬅️ 戻る" if lang == 'jp' else "⬅️ Назад")
        builder.button(text=btn_back, callback_data="help:main")
        builder.adjust(1)
    return builder.as_markup()

from typing import Tuple, Optional
from aiogram.types import Message
def _get_msg_content_and_type(msg: Message) -> Tuple[Optional[str], Optional[str]]:
    if msg.content_type == 'text':
        return msg.text, 'text'
    elif msg.content_type == 'sticker':
        return msg.sticker.file_id, 'sticker'
    elif msg.content_type == 'animation':
        return msg.animation.file_id, 'animation'
    elif msg.content_type == 'audio':
        return None, 'audio'
    elif msg.content_type in ['photo', 'video', 'document'] and msg.caption:
        return msg.caption, 'text'
    return None, None

