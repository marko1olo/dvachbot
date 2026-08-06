import asyncio
import time
import math
from aiogram.filters import Command
from bot_helpers import *
from post_helpers import *
from shared_state import *
from aiogram import Router, F, types
from aiogram.types import Message
from aiogram.exceptions import TelegramForbiddenError
from html import escape as escape_html
from post_helpers import delete_user_posts
from thread_texts import thread_messages
from common.db_pool import db_lock
from common.token_generator import generate_unique_token
from common.database import (
    get_pool, get_post_author_by_copy, get_post_by_num, get_post_copies,
    get_post_info_by_copy, add_or_activate_user, update_user_status,
    set_system_setting, add_reaction_ban, remove_reaction_ban,
    add_spam_word, remove_spam_word, get_or_create_api_token, archive_thread_in_db,
    log_global_event
)

router = Router()

@router.message(Command("say"))
async def cmd_admin_say(message: types.Message, board_id: str | None, stream: str = 'ru'):
    """
    Отправляет сообщение от имени Администрации.
    """
    if not board_id or not is_admin(message.from_user.id, board_id):
        return
    raw_html = message.html_text or getattr(message, 'caption_html_text', None) or ""
    command_prefix = "/say"
    text_to_say = ""
    if raw_html.startswith(command_prefix):
        text_to_say = raw_html[len(command_prefix):].strip()
    elif message.caption and getattr(message, 'caption_html_text', '').startswith(command_prefix):
         text_to_say = getattr(message, 'caption_html_text', '')[len(command_prefix):].strip()
    else:
        text_to_say = raw_html.strip()
    content_type = message.content_type
    file_id = None
    if content_type in ['photo', 'video', 'animation', 'document', 'audio']:
        file_id_obj = getattr(message, content_type)[-1] if content_type == 'photo' else getattr(message, content_type)
        file_id = file_id_obj.file_id
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    if not text_to_say and not file_id:
        err = "Enter text or attach media." if lang == 'en' else ("テキストを入力するかメディアを添付してください。" if lang == 'jp' else "Введите текст или прикрепите медиа.")
        await message.answer(err)
        return
    content = {
        'type': content_type if file_id else 'text',
        'is_system_message': True,
        'archive_allowed': True
    }
    if file_id:
        content['file_id'] = file_id
        content['caption'] = text_to_say
    else:
        content['text'] = text_to_say
    now_dt = datetime.now(UTC)
    pnum = await create_post(
        board_id=board_id,
        author_id=0,
        content=content,
        timestamp=now_dt.timestamp(),
        is_from_site=False, stream=stream
    )
    if pnum:
        header = await format_header(board_id, pnum, 0)
        if lang == 'en':
            admin_title = "ADMINISTRATION"
        elif lang == 'jp':
            admin_title = "管理部"
        else:
            admin_title = "АДМИНИСТРАЦИЯ"
        content['header'] = f"🔴 <b>{admin_title}</b> 🔴\n{header}"
        await update_post_content(pnum, content)
        async with storage_lock:
            messages_storage[pnum] = {
                'author_id': 0, 
                'timestamp': now_dt, 
                'content': content, 
                'board_id': board_id
            }
        b_data = board_data[board_id]
        await enqueue_board_message(board_id, {
            "recipients": b_data['users']['active'],
            "content": content,
            "post_num": pnum,
            "board_id": board_id
        })
        conf_txt = f"✅ Message sent (#{pnum})" if lang == 'en' else (f"✅ 送信完了 (#{pnum})" if lang == 'jp' else f"✅ Сообщение отправлено (#{pnum})")
        sent_conf = await message.answer(conf_txt)
        spawn_task(delete_message_after_delay(sent_conf, 5))
    try: await message.delete()
    except TelegramBadRequest: pass

@router.message(Command("troll"))
async def cmd_troll_toggle(message: Message, board_id: str | None, stream: str = 'ru'):
    if not board_id or not is_admin(message.from_user.id, board_id):
        return
    target_id = None
    if message.reply_to_message:
        target_id = await get_author_id_by_reply(message)
    
    parts = (message.text or message.caption or "").split()
    if not target_id and len(parts) > 1:
        try:
            target_id = int(parts[1])
        except ValueError:
            import traceback; traceback.print_exc()

    if not target_id:
        await message.answer("⚠️ Ответьте на сообщение юзера или укажите его ID: <code>/troll &lt;ID&gt;</code>", parse_mode="HTML")
        return
    b_data = board_data[board_id]
    if 'troll_targets' not in b_data:
        b_data['troll_targets'] = set()
    
    if target_id in b_data['troll_targets']:
        b_data['troll_targets'].remove(target_id)
        await message.answer(f"Shadow-Troll OFF for {target_id}")
    else:
        b_data['troll_targets'].add(target_id)
        await message.answer(f"Shadow-Troll ON for {target_id}")
        
    # Also log global event
    await log_global_event('bot', f"🤡 TROLL: Admin {message.from_user.id} toggled troll for {target_id} on {board_id}")

@router.message(Command("admin"))
async def cmd_admin(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id:
        try: await message.delete()
        except TelegramBadRequest: pass
        return
    if not is_admin(message.from_user.id, board_id):
        lang = 'en' if board_id == 'int' else 'ru'
        contact_url = "https://t.me/voprosy?start=rba30"
        if lang == 'en':
            response_text = "To contact the administration, please use the button below:"
            button_text = "Contact Admin"
        else:
            response_text = "Для связи с админом используйте кнопку ниже:"
            button_text = "Связаться с админом"
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=button_text, url=contact_url)]])
        try:
            await message.answer(response_text, reply_markup=keyboard)
            await message.delete()
        except Exception as e: pass
        return
    b_data = board_data[board_id]
    lang = 'en' if board_id == 'int' else 'ru'
    user_settings = b_data.get('user_settings', {})
    gif_ban_count = sum(1 for s in user_settings.values() if s.get('shadow_gif'))
    sticker_ban_count = sum(1 for s in user_settings.values() if s.get('shadow_sticker'))
    reaction_ban_count = len(b_data.get('reaction_banned_users', set()))
    media_ban_count = sum(1 for s in user_settings.values() if s.get('shadow_media')) # Подсчет
    lie_media_count = sum(1 for s in user_settings.values() if s.get('lie_media'))
    if lang == 'en':
        header_text = f"Admin panel for board {BOARD_CONFIG[board_id]['name']}:"
        memo_text = (
            "<b>🗒️ Command Cheatsheet:</b>\n"
            "<code>/filter ...</code> - Manage spam filter\n"
            f"<code>/togglereactions &lt;id&gt;</code> - Ban reactions ({reaction_ban_count})\n"
            f"<code>/togglegif &lt;id&gt;</code> - Shadow Ban GIFs ({gif_ban_count})\n"
            f"<code>/togglestickers &lt;id&gt;</code> - Shadow Ban Stickers ({sticker_ban_count})\n"
            f"<code>/togglemedia</code> — Бан ВСЕХ медиа ({media_ban_count})\n\n"
            f"<code>/lie &lt;id&gt;</code> - Archive media substitution ({lie_media_count})\n"
            "<code>/reactions</code> (reply) - Show who reacted"
        )
    elif lang == 'jp':
        header_text = f"{BOARD_CONFIG[board_id]['name']} の管理パネル:"
        memo_text = (
            "<b>🗒️ コマンドメモ:</b>\n"
            "<code>/filter ...</code> - スパムフィルタ管理\n"
            f"<code>/togglereactions &lt;id&gt;</code> - リアクション禁止 ({reaction_ban_count})\n"
            f"<code>/togglegif &lt;id&gt;</code> - GIFシャドウバン ({gif_ban_count})\n"
            f"<code>/togglestickers &lt;id&gt;</code> - ステッカーシャドウバン ({sticker_ban_count})\n"
            f"<code>/lie &lt;id&gt;</code> - Archive media substitution ({lie_media_count})\n"
            "<code>/reactions</code> (返信) - リアクションした人を見る"
        )
    else:
        header_text = f"Админка доски {BOARD_CONFIG[board_id]['name']}:"
        memo_text = (
            f"{header_text}\n\n"
            "<code>/ban</code>, <code>/unban</code> — Бан/Разбан\n"
            "<code>/mute [время]</code>, <code>/unmute</code> — Мут\n"
            "<code>/shadowmute [время]</code> — Теневой мут (локальный)\n"
            "<code>/gban</code>, <code>/gunban</code>, <code>/gshadowmute</code> — <b>ГЛОБАЛЬНЫЕ</b> меры\n\n"
            "<code>/del</code> — Удалить пост (и копии)\n"
            "<code>/sdel</code> — Теневое удаление (автор не видит)\n"
            "<code>/pin</code>, <code>/unpin</code> — Глобальный закреп\n\n"
            "<code>/whois [id]</code> — Досье на юзера\n"
            "<code>/id</code> — Узнать ID\n"
            f"<code>/togglegif</code> — Запрет GIF (Всего: {gif_ban_count})\n"
            f"<code>/togglestickers</code> — Запрет стикеров (Всего: {sticker_ban_count})\n\n"
            f"<code>/lie</code> — Подмена медиа архивом (Всего: {lie_media_count})\n\n"
            "<code>/say [текст]</code> — Пост от имени Админа\n"
            "<code>/ans [текст]</code> — Ответ от имени Системы (реплай)\n"
            "<code>/stop</code> — Выключить режимы (Шиза и т.д.)"
        )
    final_text = f"{header_text}\n\n{memo_text}"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data=f"stats_{board_id}"),
         InlineKeyboardButton(text="🤬 Стоп-слова", callback_data=f"filter_list_{board_id}")],
        [InlineKeyboardButton(text="🚫 Ограничения (Баны/Муты)", callback_data=f"restrictions_{board_id}")],
        [InlineKeyboardButton(text="🔒 Локдаун (ВКЛ/ВЫКЛ)", callback_data="admin_menu:lockdown")],
        [InlineKeyboardButton(text="💾 Сохранить Бэкап", callback_data="save_all")],
    ])
    await message.answer(final_text, reply_markup=keyboard, parse_mode="HTML")
    await _safe_delete_user_message(message)

@router.message(Command("lockdown"))
async def cmd_bot_lockdown(message: Message, board_id: str | None):
    if not board_id or not is_admin(message.from_user.id, board_id):
        return
    args = (message.text or message.caption or "").split()
    if len(args) < 2:
        await message.answer("Использование: `/lockdown on` или `/lockdown off`", parse_mode="Markdown")
        return
    enabled = args[1].lower() == "on"
    from common.database import set_system_setting
    await set_system_setting('lockdown_enabled', "true" if enabled else "false")
    status_text = "ВКЛЮЧИЛ" if enabled else "ВЫКЛЮЧИЛ"
    await log_global_event('bot', f"🚨 LOCKDOWN: Админ {message.from_user.id} {status_text} режим бункера")
    await message.answer(f"✅ Режим бункера {'активирован' if enabled else 'деактивирован'} везде.")

@router.message(Command("togglereactions"))
async def cmd_togglereactions(message: types.Message, board_id: str | None, stream: str = 'ru'):

    if not board_id or not is_admin(message.from_user.id, board_id):
        try: await message.delete()
        except TelegramBadRequest: pass
        return
    target_id = None
    if message.reply_to_message:
        target_id = await get_author_id_by_reply(message)
    else:
        parts = (message.text or message.caption or "").split()
        if len(parts) == 2:
            try: target_id = int(parts[1])
            except ValueError: pass
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    if not target_id:
        if lang == 'en':
            usage = "Usage: <code>/togglereactions &lt;user_id&gt;</code> or reply."
        elif lang == 'jp':
            usage = "使用法: <code>/togglereactions &lt;ID&gt;</code> または返信。"
        else:
            usage = "Использование: <code>/togglereactions &lt;user_id&gt;</code> или ответом на сообщение."
        await message.answer(usage, parse_mode="HTML")
        try: await message.delete()
        except TelegramBadRequest: pass
        return
    response_text = ""
    # reaction_banned_users живёт в board_data, а storage_lock охраняет
    # messages_storage — то есть здесь он был ложной зависимостью и при этом
    # удерживался через ЧЕТЫРЕ обращения к БД (add/remove_reaction_ban и два
    # log_global_event). Под локом оставлено только само переключение
    # множества: оно должно быть атомарным, чтобы два админа одновременно не
    # получили противоположные результаты. Запись в БД — уже без лока.
    async with storage_lock:
        banned_set = board_data[board_id].setdefault('reaction_banned_users', set())
        now_allowed = target_id in banned_set
        if now_allowed:
            banned_set.remove(target_id)
        else:
            banned_set.add(target_id)
    if now_allowed:
        await remove_reaction_ban(target_id, board_id)
        await log_global_event('bot', f"🎭 REAC_OK: Админ {message.from_user.id} РАЗРЕШИЛ реакции для {target_id} на /{board_id}/")
        if lang == 'en':
            response_text = f"✅ User <code>{target_id}</code> can now use reactions again."
        elif lang == 'jp':
            response_text = f"✅ ユーザー <code>{target_id}</code> のリアクション禁止を解除しました。"
        else:
            response_text = f"✅ Пользователь <code>{target_id}</code> теперь снова может ставить реакции."
    else:
        await add_reaction_ban(target_id, board_id)
        await log_global_event('bot', f"🎭 REAC_BAN: Админ {message.from_user.id} ЗАПРЕТИЛ реакции для {target_id} на /{board_id}/")
        if lang == 'en':
            response_text = f"🚫 User <code>{target_id}</code> is now banned from using reactions."
        elif lang == 'jp':
            response_text = f"🚫 ユーザー <code>{target_id}</code> のリアクションを禁止しました。"
        else:
            response_text = f"🚫 Пользователю <code>{target_id}</code> теперь запрещено ставить реакции."
    try:
        await message.answer(response_text, parse_mode="HTML")
        await message.delete()
    except (TelegramBadRequest, TelegramForbiddenError):
        import traceback; traceback.print_exc()

@router.message(Command("reactions"))
async def cmd_reactions(message: types.Message, board_id: str | None, stream: str = 'ru'):

    if not board_id or not is_admin(message.from_user.id, board_id):
        try: await message.delete()
        except TelegramBadRequest: pass
        return
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    if not message.reply_to_message:
        if lang == 'en': msg = "Reply to a message to use this: <code>/sdel</code>"
        elif lang == 'jp': msg = "返信して使ってください: <code>/sdel</code>"
        else: msg = "⚠️ Ответьте на сообщение, которое хотите тихо удалить: <code>/sdel</code>"
        await message.answer(msg, parse_mode="HTML")
        try: await message.delete()
        except TelegramBadRequest: pass
        return
    post_num = None
    reactions_data = {}
    async with storage_lock:
        lookup_key = (message.chat.id, message.reply_to_message.message_id)
        post_num = message_to_post.get(lookup_key)
    if not post_num:
        info = await get_post_info_by_copy(message.chat.id, message.reply_to_message.message_id)
        if info: post_num = info[0]
    if post_num:
        if post_num not in messages_storage:
            db_post = await get_post_by_num(post_num)
            if db_post:
                content_dict = db_post['content'] if isinstance(db_post['content'], dict) else {}
                reactions_dict = content_dict.get('reactions', {'users': {}})
                async with storage_lock:
                    messages_storage[post_num] = {
                        'author_id': db_post['author_id'],
                        'timestamp': datetime.fromtimestamp(db_post['timestamp'], UTC) if isinstance(db_post['timestamp'], (int, float)) else db_post['timestamp'],
                        'content': content_dict,
                        'reactions': reactions_dict,
                        'board_id': db_post['board_id'],
                        'thread_id': db_post.get('thread_id')
                    }
        post_data = messages_storage.get(post_num, {})
        reactions_obj = post_data.get('reactions') or post_data.get('content', {}).get('reactions') or {}
        reactions_data = reactions_obj.get('users', {})
    if not post_num:
        if lang == 'en': err = "Post not found in DB."
        elif lang == 'jp': err = "データベースに投稿が見つかりません。"
        else: err = "Не удалось найти этот пост в базе."
        try: await message.answer(err); await message.delete()
        except TelegramBadRequest: pass
        return
    if not reactions_data:
        if lang == 'en': msg = f"Post #{post_num} has no reactions yet."
        elif lang == 'jp': msg = f"投稿 #{post_num} にはまだリアクションがありません。"
        else: msg = f"На пост #{post_num} еще нет реакций."
        try: await message.answer(msg); await message.delete()
        except TelegramBadRequest: pass
        return
    if lang == 'en': header = f"<b>Reactions to post #{post_num}:</b>\n\n"
    elif lang == 'jp': header = f"<b>投稿 #{post_num} へのリアクション:</b>\n\n"
    else: header = f"<b>Реакции на пост #{post_num}:</b>\n\n"
    lines = []
    sorted_reactors = sorted(reactions_data.items())
    MAX_USERS_TO_SHOW = 50
    for user_id, emoji_list in sorted_reactors[:MAX_USERS_TO_SHOW]:
        emojis_str = "".join(emoji_list)
        lines.append(f"• ID <code>{user_id}</code>: {emojis_str}")
    response_text = header + "\n".join(lines)
    if len(sorted_reactors) > MAX_USERS_TO_SHOW:
        diff = len(sorted_reactors) - MAX_USERS_TO_SHOW
        if lang == 'en': footer = f"\n<i>...and {diff} more users.</i>"
        elif lang == 'jp': footer = f"\n<i>...他 {diff} ユーザー。</i>"
        else: footer = f"\n<i>...и еще {diff} пользователей.</i>"
        response_text += footer
    try:
        await message.answer(response_text, parse_mode="HTML")
        await message.delete()
    except (TelegramBadRequest, TelegramForbiddenError):
        import traceback; traceback.print_exc()

@router.message(Command("filter"))
async def cmd_filter(message: types.Message, board_id: str | None, stream: str = 'ru'):

    if not board_id or not is_admin(message.from_user.id, board_id):
        try: await message.delete()
        except TelegramBadRequest: pass
        return
    b_data = board_data[board_id]
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    parts = (message.text or message.caption or "").split(maxsplit=2)
    subcommand = parts[1].lower() if len(parts) > 1 else "help"
    if subcommand == "list":
        spam_words = b_data.get('spam_filter_words', set())
        if not spam_words:
            if lang == 'en': resp = "Filter list is empty."
            elif lang == 'jp': resp = "フィルターリストは空です。"
            else: resp = "Список стоп-слов для этой доски пуст."
        else:
            sorted_words = sorted(list(spam_words))
            word_list = "\n".join([f"• <code>{escape_html(word)}</code>" for word in sorted_words])
            board_name = BOARD_CONFIG[board_id]['name']
            if lang == 'en':
                resp = f"<b>Stop-words on {board_name}:</b>\n\n{word_list}"
            elif lang == 'jp':
                resp = f"<b>{board_name} のNGワード:</b>\n\n{word_list}"
            else:
                resp = f"<b>Текущие стоп-слова на доске {board_name}:</b>\n\n{word_list}"
        await message.answer(resp, parse_mode="HTML")
    elif subcommand == "add":
        if len(parts) < 3 or not parts[2].strip():
            if lang == 'en': txt = "Usage: <code>/filter add &lt;word&gt;</code>"
            elif lang == 'jp': txt = "使用法: <code>/filter add &lt;単語&gt;</code>"
            else: txt = "Использование: <code>/filter add &lt;слово&gt;</code>"
            await message.answer(txt, parse_mode="HTML")
        else:
            word_to_add = parts[2].lower().strip()
            if await add_spam_word(board_id, word_to_add):
                b_data['spam_filter_words'].add(word_to_add)
                if lang == 'en': msg = f"✅ Added '<code>{escape_html(word_to_add)}</code>'."
                elif lang == 'jp': msg = f"✅ '<code>{escape_html(word_to_add)}</code>' を追加しました。"
                else: msg = f"✅ Слово '<code>{escape_html(word_to_add)}</code>' добавлено."
                await message.answer(msg, parse_mode="HTML")
            else:
                await message.answer("❌ DB Error.")
    elif subcommand == "remove":
        if len(parts) < 3 or not parts[2].strip():
            if lang == 'en': txt = "Usage: <code>/filter remove &lt;word&gt;</code>"
            elif lang == 'jp': txt = "使用法: <code>/filter remove &lt;単語&gt;</code>"
            else: txt = "Использование: <code>/filter remove &lt;слово&gt;</code>"
            await message.answer(txt, parse_mode="HTML")
        else:
            word_to_remove = parts[2].lower().strip()
            if await remove_spam_word(board_id, word_to_remove):
                b_data['spam_filter_words'].discard(word_to_remove)
                if lang == 'en': msg = f"🗑 Removed '<code>{escape_html(word_to_remove)}</code>'."
                elif lang == 'jp': msg = f"🗑 '<code>{escape_html(word_to_remove)}</code>' を削除しました。"
                else: msg = f"🗑 Слово '<code>{escape_html(word_to_remove)}</code>' удалено."
                await message.answer(msg, parse_mode="HTML")
            else:
                await message.answer("ℹ️ Word not found.")
    else:
        if lang == 'en':
            usage = (
                "<b>Spam Filter Management:</b>\n"
                "<code>/filter list</code> - Show list\n"
                "<code>/filter add &lt;word&gt;</code> - Add\n"
                "<code>/filter remove &lt;word&gt;</code> - Remove"
            )
        elif lang == 'jp':
            usage = (
                "<b>スパムフィルタ管理:</b>\n"
                "<code>/filter list</code> - リスト表示\n"
                "<code>/filter add &lt;単語&gt;</code> - 追加\n"
                "<code>/filter remove &lt;単語&gt;</code> - 削除"
            )
        else:
            usage = (
                "<b>Управление спам-фильтром:</b>\n"
                "<code>/filter list</code> - Показать текущие стоп-слова\n"
                "<code>/filter add &lt;слово&gt;</code> - Добавить слово\n"
                "<code>/filter remove &lt;слово&gt;</code> - Удалить слово"
            )
        await message.answer(usage, parse_mode="HTML")
    try: await message.delete()
    except TelegramBadRequest: pass

@router.callback_query(F.data == "save_all")
async def admin_save_all(callback: types.CallbackQuery):

    is_any_admin = any(is_admin(callback.from_user.id, b_id) for b_id in BOARDS)
    if not is_any_admin:
        try: await callback.answer("Access denied", show_alert=True)
        except Exception as e: pass
        return
    user_lang = callback.from_user.language_code or 'en'
    is_ru = 'ru' in user_lang or 'uk' in user_lang or 'be' in user_lang
    start_txt = "Запуск внепланового бэкапа БД..." if is_ru else "Starting manual DB backup..."
    try:
        await callback.answer(start_txt)
    except (TelegramBadRequest, TelegramForbiddenError):
        pass
    try:
        db = await get_pool()
        await db.execute("PRAGMA wal_checkpoint(PASSIVE);")
        print("💾 [Manual Backup] WAL Checkpoint выполнен.")
    except Exception as e:
        print(f"⚠️ Ошибка чекпоинта перед бэкапом: {e}")

    success = await git_commit_and_push_db()
    if is_ru:
        response_text = "✅ База данных успешно сохранена в GitHub." if success else "❌ Ошибка при создании бэкапа. См. логи."
    else:
        response_text = "✅ Database successfully pushed to GitHub." if success else "❌ Backup failed. Check logs."
    if isinstance(callback.message, types.Message):
        try:
            await callback.message.edit_text(response_text)
        except TelegramBadRequest:
            await callback.message.answer(response_text)

@router.callback_query(F.data.startswith("stats_"))
async def admin_stats_board(callback: types.CallbackQuery):
    try:
        board_id = callback.data.split("_")[1]
    except IndexError: return
    if not is_admin(callback.from_user.id, board_id):
        try: await callback.answer("Access denied", show_alert=True)
        except Exception as e: pass
        return
    if not isinstance(callback.message, types.Message):
        try: await callback.answer()
        except Exception as e: pass
        return
    b_data = board_data[board_id]
    lang = 'en' if board_id == 'int' else 'ru'
    if lang == 'en':
        stats_text = (
            f"Stats for {BOARD_CONFIG[board_id]['name']}:\n\n"
            f"Active users: {len(b_data['users']['active'])}\n"
            f"Banned: {len(b_data['users']['banned'])}\n"
            f"Queue size: {message_queues[board_id].qsize()}"
        )
        back_txt = "⬅️ Back"
    else:
        stats_text = (
            f"Статистика доски {BOARD_CONFIG[board_id]['name']}:\n\n"
            f"Активных: {len(b_data['users']['active'])}\n"
            f"Забаненных: {len(b_data['users']['banned'])}\n"
            f"В очереди: {message_queues[board_id].qsize()}"
        )
        back_txt = "⬅️ Назад"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=back_txt, callback_data=f"admin_main_{board_id}")]
    ])
    try:
        await callback.message.edit_text(stats_text, reply_markup=keyboard)
    except (TelegramBadRequest, TelegramForbiddenError):
        pass
    try: await callback.answer()
    except TelegramBadRequest: pass

@router.callback_query(F.data.startswith("restrictions_"))
async def admin_restrictions_board(callback: types.CallbackQuery, board_id: str | None, stream: str = 'ru'): # Добавлены аргументы board_id и stream

    if not board_id:
        try:
            board_id = callback.data.split("_")[1]
        except IndexError: return
    if not is_admin(callback.from_user.id, board_id):
        await callback.answer("Отказано в доступе", show_alert=True)
        return
    if not isinstance(callback.message, types.Message):
        await callback.answer()
        return
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    b_data = board_data[board_id]
    now = datetime.now(UTC)
    text_parts = [f"<b>Список ограничений на доске {BOARD_CONFIG[board_id]['name']}:</b>"]
    banned_users = b_data['users']['banned']
    if banned_users:
        banned_list = "\n".join([f"  • ID <code>{uid}</code>" for uid in sorted(list(banned_users))])
        if lang == 'en': header = "\n<u>🚫 Banned forever:</u>"
        elif lang == 'jp': header = "\n<u>🚫 永久BAN:</u>"
        else: header = "\n<u>🚫 Забанены навсегда:</u>"
        text_parts.append(f"{header}\n{banned_list}")
    active_mutes = {uid: expiry for uid, expiry in b_data['mutes'].items() if expiry > now}
    if active_mutes:
        mute_lines = []
        for uid, expiry in sorted(active_mutes.items(), key=lambda item: item[1]):
            remaining = expiry - now
            hours, remainder = divmod(remaining.total_seconds(), 3600)
            minutes, _ = divmod(remainder, 60)
            time_left_str = f"{int(hours)}ч {int(minutes)}м"
            mute_lines.append(f"  • ID <code>{uid}</code> (осталось: {time_left_str})")
        mutes_list = "\n".join(mute_lines)
        if lang == 'en': header = "\n<u>🔇 Muted:</u>"
        elif lang == 'jp': header = "\n<u>🔇 ミュート中:</u>"
        else: header = "\n<u>🔇 В муте:</u>"
        text_parts.append(f"{header}\n{mutes_list}")
    active_shadow_mutes = {uid: expiry for uid, expiry in b_data['shadow_mutes'].items() if expiry > now}
    if active_shadow_mutes:
        shadow_mute_lines = []
        for uid, expiry in sorted(active_shadow_mutes.items(), key=lambda item: item[1]):
            remaining = expiry - now
            hours, remainder = divmod(remaining.total_seconds(), 3600)
            minutes, _ = divmod(remainder, 60)
            time_left_str = f"{int(hours)}ч {int(minutes)}м"
            shadow_mute_lines.append(f"  • ID <code>{uid}</code> (осталось: {time_left_str})")
        shadow_mutes_list = "\n".join(shadow_mute_lines)
        text_parts.append(f"\n<u>👻 Полный теневой мут:</u>\n{shadow_mutes_list}")
    gif_banned_users = []
    user_settings = b_data.get('user_settings', {})
    for uid, settings in user_settings.items():
        if settings.get('shadow_gif'):
            gif_banned_users.append(uid)
    if gif_banned_users:
        gif_list = "\n".join([f"  • ID <code>{uid}</code>" for uid in sorted(gif_banned_users)])
        text_parts.append(f"\n<u>👾 Теневой бан GIF:</u>\n{gif_list}")
    sticker_banned_users = []
    for uid, settings in user_settings.items():
        if settings.get('shadow_sticker'):
            sticker_banned_users.append(uid)
    if sticker_banned_users:
        sticker_list = "\n".join([f"  • ID <code>{uid}</code>" for uid in sorted(sticker_banned_users)])
        text_parts.append(f"\n<u>🃏 Теневой бан Стикеров:</u>\n{sticker_list}")
    media_banned_users = []
    for uid, settings in user_settings.items():
        if settings.get('shadow_media'):
            media_banned_users.append(uid)
    if media_banned_users:
        media_list = "\n".join([f"  • ID <code>{uid}</code>" for uid in sorted(media_banned_users)])
        text_parts.append(f"\n<u>🔇 Теневой бан Медиа (только текст):</u>\n{media_list}")
    lie_media_users = []
    for uid, settings in user_settings.items():
        if settings.get('lie_media'):
            lie_media_users.append(uid)
    if lie_media_users:
        lie_list = "\n".join([f"  • ID <code>{uid}</code>" for uid in sorted(lie_media_users)])
        text_parts.append(f"\n<u>🎭 Archive media substitution:</u>\n{lie_list}")
    if len(text_parts) == 1:
        final_text = f"На доске {BOARD_CONFIG[board_id]['name']} нет активных ограничений."
    else:
        final_text = "\n".join(text_parts)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад в меню", callback_data=f"admin_main_{board_id}")]
    ])
    try:
        await callback.message.edit_text(final_text, parse_mode="HTML", reply_markup=keyboard)
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            print(f"Ошибка обновления списка ограничений: {e}")
    await callback.answer()

@router.callback_query(F.data.startswith("filter_list_"))
async def admin_filter_list(callback: types.CallbackQuery):

    try:
        board_id = callback.data.split("_")[-1]
    except IndexError: return
    if not is_admin(callback.from_user.id, board_id):
        try: await callback.answer("Access denied", show_alert=True)
        except Exception as e: pass
        return
    b_data = board_data[board_id]
    spam_words = b_data.get('spam_filter_words', set())
    lang = 'en' if board_id == 'int' else 'ru'
    if lang == 'en':
        header = f"<b>🤬 Stop-words ({len(spam_words)}):</b>"
        instr = (
            "\n\n<b>📝 How to manage:</b>\n"
            "• Add: <code>/filter add word</code>\n"
            "• Del: <code>/filter remove word</code>\n"
            "<i>(Write commands in chat)</i>"
        )
        empty_txt = "\n\n<i>List is empty. Filter disabled.</i>"
        back_txt = "⬅️ Back"
    else:
        header = f"<b>🤬 Фильтр стоп-слов ({len(spam_words)} шт):</b>"
        instr = (
            "\n\n<b>📝 Как управлять:</b>\n"
            "• Добавить: <code>/filter add слово</code>\n"
            "• Удалить: <code>/filter remove слово</code>\n"
            "<i>(Писать команды в чат)</i>"
        )
        empty_txt = "\n\n<i>Список пуст. Фильтр отключен.</i>"
        back_txt = "⬅️ Назад в меню"
    if not spam_words:
        list_text = empty_txt
    else:
        sorted_words = sorted(list(spam_words))
        words_display = ", ".join([f"<code>{escape_html(w)}</code>" for w in sorted_words])
        list_text = f"\n\n{words_display}"
    final_text = f"{header}{list_text}{instr}"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=back_txt, callback_data=f"admin_main_{board_id}")]
    ])
    try:
        await callback.message.edit_text(final_text, parse_mode="HTML", reply_markup=keyboard)
    except (TelegramBadRequest, TelegramForbiddenError): 
        pass
    try: await callback.answer()
    except TelegramBadRequest: pass

@router.callback_query(F.data.startswith("reaction_bans_"))
async def admin_reaction_bans(callback: types.CallbackQuery):

    try:
        board_id = callback.data.split("_")[-1]
    except IndexError: return
    if not is_admin(callback.from_user.id, board_id):
        try: await callback.answer("Access denied", show_alert=True)
        except Exception as e: pass
        return
    b_data = board_data[board_id]
    lang = 'en' if board_id == 'int' else 'ru'
    banned_users = b_data.get('reaction_banned_users', set())
    board_name = BOARD_CONFIG[board_id]['name']
    if not banned_users:
        if lang == 'en':
            response_text = f"No users are banned from reacting on {board_name}."
        elif lang == 'jp':
            response_text = f"{board_name} でリアクション禁止のユーザーはいません。"
        else:
            response_text = f"На доске {board_name} нет пользователей с запретом на реакции."
    else:
        sorted_banned = sorted(list(banned_users))
        user_list = "\n".join([f"  • ID <code>{uid}</code>" for uid in sorted_banned])
        if lang == 'en':
            response_text = f"<b>🚫 Users banned from reacting on {board_name}:</b>\n\n{user_list}"
        elif lang == 'jp':
            response_text = f"<b>🚫 {board_name} でリアクション禁止のユーザー:</b>\n\n{user_list}"
        else:
            response_text = f"<b>🚫 Пользователи с запретом на реакции на доске {board_name}:</b>\n\n{user_list}"
    back_txt = "⬅️ Back" if lang == 'en' else ("⬅️ 戻る" if lang == 'jp' else "⬅️ Назад в меню")
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=back_txt, callback_data=f"admin_main_{board_id}")]
    ])
    try:
        await callback.message.edit_text(response_text, parse_mode="HTML", reply_markup=keyboard)
    except (TelegramBadRequest, TelegramForbiddenError): 
        pass
    try: await callback.answer()
    except TelegramBadRequest: pass

@router.callback_query(F.data.startswith("admin_main_"))
async def admin_back_to_main(callback: types.CallbackQuery):

    try:
        board_id = callback.data.split("_")[2]
    except IndexError: return
    if not is_admin(callback.from_user.id, board_id):
        try: await callback.answer("Нет прав", show_alert=True)
        except Exception as e: pass
        return
    b_data = board_data[board_id]
    lang = 'en' if board_id == 'int' else 'ru'
    user_settings = b_data.get('user_settings', {})
    gif_ban_count = sum(1 for s in user_settings.values() if s.get('shadow_gif'))
    sticker_ban_count = sum(1 for s in user_settings.values() if s.get('shadow_sticker'))
    reaction_ban_count = len(b_data.get('reaction_banned_users', set()))
    media_ban_count = sum(1 for s in user_settings.values() if s.get('shadow_media'))
    lie_media_count = sum(1 for s in user_settings.values() if s.get('lie_media'))
    board_name = BOARD_CONFIG[board_id]['name']
    if lang == 'en':
        header_text = f"Admin panel for board {board_name}:"
        memo_text = (
            "<b>🗒️ Command Cheatsheet:</b>\n"
            "<code>/filter ...</code> - Manage spam filter\n"
            f"<code>/togglereactions &lt;id&gt;</code> - Ban reactions ({reaction_ban_count})\n"
            f"<code>/togglegif &lt;id&gt;</code> - Shadow Ban GIFs ({gif_ban_count})\n"
            f"<code>/togglestickers &lt;id&gt;</code> - Shadow Ban Stickers ({sticker_ban_count})\n"
            f"<code>/togglemedia &lt;id&gt;</code> - Shadow Ban Media ({media_ban_count})\n"
            f"<code>/lie &lt;id&gt;</code> - Archive media substitution ({lie_media_count})\n"
            "<code>/reactions</code> (reply) - Show who reacted"
        )
        btn_stats = "📊 Stats"
        btn_filter = "🤬 Filter"
        btn_restr = "🚫 Restrictions"
        btn_backup = "💾 Backup"
    elif lang == 'jp': # На всякий случай
        header_text = f"{board_name} 管理パネル:"
        memo_text = (
            "<b>🗒️ コマンド:</b>\n"
            "<code>/filter ...</code> - フィルタ管理\n"
            f"<code>/togglereactions &lt;id&gt;</code> - リアクション禁止 ({reaction_ban_count})\n"
            f"<code>/togglegif &lt;id&gt;</code> - GIF禁止 ({gif_ban_count})\n"
            f"<code>/togglestickers &lt;id&gt;</code> - スタンプ禁止 ({sticker_ban_count})\n"
            f"<code>/togglemedia &lt;id&gt;</code> - メディア禁止 ({media_ban_count})\n"
            f"<code>/lie &lt;id&gt;</code> - Archive media substitution ({lie_media_count})\n"
            "<code>/reactions</code> (返信) - リアクションした人を見る"
        )
        btn_stats = "📊 統計"
        btn_filter = "🤬 フィルタ"
        btn_restr = "🚫 制限"
        btn_backup = "💾 保存"
    else:
        header_text = f"Админка доски {board_name}:"
        memo_text = (
            f"{header_text}\n\n"
            "<code>/ban</code>, <code>/unban</code> — Бан/Разбан\n"
            "<code>/mute [время]</code>, <code>/unmute</code> — Мут\n"
            "<code>/shadowmute [время]</code> — Теневой мут\n"
            "<code>/gban</code>, <code>/gunban</code> — ГЛОБАЛЬНО\n\n"
            "<code>/del</code>, <code>/sdel</code> — Удаление\n"
            "<code>/pin</code>, <code>/unpin</code> — Закреп\n\n"
            "<code>/whois [id]</code> — Досье\n"
            f"<code>/togglegif</code> — Бан GIF ({gif_ban_count})\n"
            f"<code>/togglestickers</code> — Бан стикеров ({sticker_ban_count})\n\n"
            f"<code>/lie</code> — Подмена медиа архивом ({lie_media_count})\n\n"
            "<code>/say</code>, <code>/ans</code> — Ответы\n"
            "<code>/stop</code> — Стоп режимы"
        )
        btn_stats = "📊 Статистика"
        btn_filter = "🤬 Стоп-слова"
        btn_restr = "🚫 Ограничения (Баны/Муты)"
        btn_backup = "💾 Сохранить Бэкап"
    final_text = f"{header_text}\n\n{memo_text}"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=btn_stats, callback_data=f"stats_{board_id}"),
         InlineKeyboardButton(text=btn_filter, callback_data=f"filter_list_{board_id}")],
        [InlineKeyboardButton(text=btn_restr, callback_data=f"restrictions_{board_id}")],
        [InlineKeyboardButton(text=btn_backup, callback_data="save_all")],
    ])
    try:
        await callback.message.edit_text(final_text, reply_markup=keyboard, parse_mode="HTML")
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e).lower():
             print(f"Admin menu update error: {e}")
    try:
        await callback.answer()
    except (TelegramBadRequest, TelegramForbiddenError):
        pass

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

@router.message(Command("id"))
async def cmd_get_id(message: types.Message, board_id: str | None, stream: str = 'ru'):

    if not board_id: return
    if not is_admin(message.from_user.id, board_id):
        await message.delete()
        return
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    target_id = message.from_user.id
    if lang == 'en': info_header = "🆔 <b>Info about you:</b>\n\n"
    elif lang == 'jp': info_header = "🆔 <b>あなたについて:</b>\n\n"
    else: info_header = "🆔 <b>Информация о вас:</b>\n\n"
    if message.reply_to_message:
        replied_author_id = None
        replied_author_id = await get_author_id_by_reply(message)
        if replied_author_id == 0:
            msg = "ℹ️ System message (bot)." if lang == 'en' else ("ℹ️ システムメッセージ（ボット）。" if lang == 'jp' else "ℹ️ Вы ответили на системное сообщение (автор: бот).")
            await message.answer(msg)
            await message.delete()
            return
        if replied_author_id:
            target_id = replied_author_id
            if lang == 'en': info_header = "🆔 <b>User Info:</b>\n\n"
            elif lang == 'jp': info_header = "🆔 <b>ユーザー情報:</b>\n\n"
            else: info_header = "🆔 <b>Информация о пользователе:</b>\n\n"
    try:
        user_chat_info = await message.bot.get_chat(target_id)
        info = info_header
        info += f"ID: <code>{target_id}</code>\n"
        if user_chat_info.first_name:
            name_lbl = "Name" if lang == 'en' else ("名前" if lang == 'jp' else "Имя")
            info += f"{name_lbl}: {escape_html(user_chat_info.first_name)}\n"
        if user_chat_info.last_name:
            sname_lbl = "Surname" if lang == 'en' else ("名字" if lang == 'jp' else "Фамилия")
            info += f"{sname_lbl}: {escape_html(user_chat_info.last_name)}\n"
        if user_chat_info.username:
            info += f"Username: @{user_chat_info.username}\n"
        b_data = board_data[board_id]
        status_lbl = f"Status on {BOARD_CONFIG[board_id]['name']}" if lang == 'en' else (f"{BOARD_CONFIG[board_id]['name']} でのステータス" if lang == 'jp' else f"Статус на доске {BOARD_CONFIG[board_id]['name']}")
        if target_id in b_data['users']['banned']:
            info += f"\n⛔️ {status_lbl}: BANNED"
        elif target_id in b_data['users']['active']:
            info += f"\n✅ {status_lbl}: Active"
        else:
            info += f"\nℹ️ {status_lbl}: Inactive"
        await message.answer(info, parse_mode="HTML")
    except (TelegramBadRequest, TelegramForbiddenError) as e:
        msg = f"User ID: <code>{target_id}</code>" if lang == 'en' else (f"ユーザーID: <code>{target_id}</code>" if lang == 'jp' else f"ID пользователя: <code>{target_id}</code>")
        await message.answer(msg, parse_mode="HTML")
    except Exception as e:
        msg = f"User ID: <code>{target_id}</code>" if lang == 'en' else (f"ユーザーID: <code>{target_id}</code>" if lang == 'jp' else f"ID пользователя: <code>{target_id}</code>")
        await message.answer(msg, parse_mode="HTML")
    try:
        await message.delete()
    except (TelegramBadRequest, TelegramForbiddenError):
        pass

@router.message(Command("ban"))
async def cmd_ban(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id or not is_admin(message.from_user.id, board_id): return
    target_id = None
    if message.reply_to_message:
        target_id = await get_author_id_by_reply(message)
    parts = (message.text or message.caption or "").split()
    if len(parts) == 2:
        try: target_id = int(parts[1])
        except ValueError: pass
    if not target_id:
        await message.answer("Нужно ответить на сообщение или указать ID: <code>/ban &lt;id&gt;</code>", parse_mode="HTML")
        return

    anon_name = generate_anon_name(target_id)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔥 Да, сжечь!", callback_data=f"admin_action:ban:{target_id}:{board_id}:0"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="admin_action:cancel:0:0:0")
        ]
    ])
    await message.answer(f"⚠️ Вы уверены, что хотите забанить <b>{anon_name}</b> (ID: <code>{target_id}</code>) и снести его последние посты?", parse_mode="HTML", reply_markup=kb)
    try: await message.delete()
    except Exception as e: pass

async def execute_ban(bot, message, target_id: int, board_id: str, admin_id: int):
    deleted_posts = await delete_user_posts(bot, target_id, 5, board_id)
    await log_global_event('bot', f"🔨 BAN: Мод {admin_id} забанил {target_id} на /{board_id}/ (удалено {deleted_posts} пст)")
    async with storage_lock:
        b_data = board_data[board_id]
        b_data['users']['banned'].add(target_id)
        b_data['users']['active'].discard(target_id)
        caches_to_clean = [
            b_data['last_activity'], b_data['last_texts'], b_data['last_stickers'],
            b_data['last_animations'], b_data['last_audios'], b_data['spam_violations'],
            b_data['spam_tracker'], b_data['last_user_msgs'], b_data['message_counter'],
            b_data['user_state'], b_data['mutes'], b_data['shadow_mutes']
        ]
        if 'user_settings' in b_data:
             b_data['user_settings'].pop(target_id, None)
        for cache in caches_to_clean:
            cache.pop(target_id, None)
    await update_user_status(target_id, board_id, 'banned')
    lang = 'en' if board_id == 'int' else 'ru'
    board_name = BOARD_CONFIG[board_id]['name']
    anon_name = generate_anon_name(target_id)
    if lang == 'en':
        response_text = f"✅ Faggot <b>{anon_name}</b> has been banned from {board_name}.\nDeleted posts: {deleted_posts}"
    else:
        response_text = f"✅ Хуесос <b>{anon_name}</b> забанен на доске {board_name}\nУдалено его постов: {deleted_posts}"
    await message.edit_text(response_text, parse_mode="HTML")
    await send_moderation_notice(target_id, "ban", board_id, deleted_posts=deleted_posts)

@router.message(Command("wipe"))
async def cmd_wipe(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id or not is_admin(message.from_user.id, board_id): return
    command_args = (message.text or message.caption or "").split()[1:]
    target_id = None
    duration_str = "1h" 
    if message.reply_to_message:
        target_id = await get_author_id_by_reply(message)
        if command_args: duration_str = command_args[0]
    elif command_args:
        try:
            target_id = int(command_args[0])
            if len(command_args) > 1: duration_str = command_args[1]
        except Exception as e:
            if message.reply_to_message:
                duration_str = command_args[0]
                target_id = await get_author_id_by_reply(message)
            else:
                await message.answer("❌ Invalid User ID.")
                return
    if not target_id:
        await message.answer("Usage: <code>/wipe &lt;id&gt; [time]</code>", parse_mode="HTML")
        return
        
    duration_str = duration_str.lower().replace(" ", "")
    if duration_str.endswith("m"): minutes = int(duration_str[:-1])
    elif duration_str.endswith("h"): minutes = int(duration_str[:-1]) * 60
    elif duration_str.endswith("d"): minutes = int(duration_str[:-1]) * 60 * 24
    else:
        try: minutes = int(duration_str)
        except Exception as e: minutes = 60

    anon_name = generate_anon_name(target_id)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔥 Да, сжечь!", callback_data=f"admin_action:wipe:{target_id}:{board_id}:{minutes}"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="admin_action:cancel:0:0:0")
        ]
    ])
    await message.answer(f"⚠️ Вы уверены, что хотите вайпнуть посты <b>{anon_name}</b> (ID: <code>{target_id}</code>) за последние {minutes} минут?", parse_mode="HTML", reply_markup=kb)
    try: await message.delete()
    except Exception as e: pass

async def execute_wipe(bot, message, target_id: int, board_id: str, admin_id: int, minutes: int):
    try: await message.edit_text("⏳ Сжигаю посты (процесс запущен, может занять несколько минут)...", parse_mode="HTML")
    except Exception as e: pass
    deleted_count = await delete_user_posts(bot, target_id, minutes, board_id)
    await log_global_event('bot', f"🧹 WIPE: Мод {admin_id} удалил {deleted_count} постов юзера {target_id} на /{board_id}/ (глубина {minutes}м)")
    anon_name = generate_anon_name(target_id)
    lang = 'en' if board_id == 'int' else 'ru'
    if lang == 'en':
        text = f"🧹 Posts by <b>{anon_name}</b> in the last {minutes}m were wiped.\nTotal deleted: {deleted_count}"
    else:
        text = f"🧹 Посты от <b>{anon_name}</b> за {minutes}м удалены.\nСнесено: {deleted_count}"
    await message.edit_text(text, parse_mode="HTML")

@router.callback_query(F.data.startswith("admin_action:"))
async def on_admin_action(callback: types.CallbackQuery):
    parts = callback.data.split(":")
    action = parts[1]
    
    if action == "cancel":
        await callback.message.delete()
        try: await callback.answer("Отменено")
        except Exception as e: pass
        return
        
    target_id = int(parts[2])
    board_id = parts[3]
    admin_id = callback.from_user.id
    
    if not is_admin(admin_id, board_id):
        await callback.answer("Нет прав", show_alert=True)
        return
        
    if action == "ban":
        await callback.answer("Баним...")
        await execute_ban(callback.bot, callback.message, target_id, board_id, admin_id)
    elif action == "wipe":
        minutes = int(parts[4])
        await callback.answer("Вайпаем...")
        await execute_wipe(callback.bot, callback.message, target_id, board_id, admin_id, minutes)

@router.message(Command("restrict_anime"))
async def cmd_restrict_anime(message: Message, board_id: str | None, stream: str = 'ru'):
    if not board_id or not is_admin(message.from_user.id, board_id):
        return

    target_id = None
    args = (message.text or message.caption or "").split()
    if message.reply_to_message:
        target_id = await get_author_id_by_reply(message)
    elif len(args) > 1 and args[1].isdecimal():
        # isdecimal, не isdigit — см. пояснение в cmd_random_media
        target_id = int(args[1])

    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')

    if not target_id:
        msg = "Usage: <code>/restrict_anime &lt;id&gt;</code> or reply." if lang != 'ru' else "Использование: <code>/restrict_anime &lt;id&gt;</code> или ответ на сообщение."
        await message.answer(msg, parse_mode="HTML")
        return

    b_data = board_data[board_id]
    async with storage_lock:
        if target_id in b_data['anime_strict_limits']:
            b_data['anime_strict_limits'].remove(target_id)
            action_log = "REMOVED FROM STRICT LIMITS"
            if lang == 'en':
                res = f"✅ User <code>{target_id}</code> removed from strict anime limits."
            elif lang == 'jp':
                res = f"✅ ユーザー <code>{target_id}</code> のアニメリミットを解除しました。"
            else:
                res = f"✅ С пользователя <code>{target_id}</code> снято жесткое ограничение на аниме."
        else:
            b_data['anime_strict_limits'].add(target_id)
            action_log = "ADDED TO STRICT LIMITS (10/day)"
            if lang == 'en':
                res = f"🚫 User <code>{target_id}</code> now restricted to 10 anime images per 24h."
            elif lang == 'jp':
                res = f"🚫 ユーザー <code>{target_id}</code> に1日10枚の制限をかけました。"
            else:
                res = f"🚫 Пользователю <code>{target_id}</code> установлено ограничение: 10 картинок в сутки."

    await log_global_event('bot', f"🛡️ ANIME_LIMIT: Админ {message.from_user.id} {action_log} для {target_id} на /{board_id}/")
    await message.answer(res, parse_mode="HTML")
    try:
        await message.delete()
    except (TelegramBadRequest, TelegramForbiddenError, Exception):
        pass

@router.message(Command("shadowmute_threads"))
async def cmd_shadowmute_threads(message: Message, board_id: str | None, stream: str = 'ru'):

    if not board_id or not is_admin(message.from_user.id, board_id) or board_id not in THREAD_BOARDS:
        await message.delete()
        return
    args = (message.text or message.caption or "").split()[1:]
    target_id = None
    duration_str = "10m" 
    if message.reply_to_message:
        target_id = await get_author_id_by_reply(message)
        if args: duration_str = args[0]
    elif args:
        try:
            target_id = int(args[0])
            if len(args) > 1: duration_str = args[1]
        except ValueError: pass
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    if not target_id:
        if lang == 'en':
            usage = "Usage: <code>/shadowmute_threads &lt;user_id&gt; [time]</code> or reply."
        elif lang == 'jp':
            usage = "使用法: <code>/shadowmute_threads &lt;user_id&gt; [時間]</code> または返信。"
        else:
            usage = "Использование: <code>/shadowmute_threads &lt;user_id&gt; [время]</code> или ответ на сообщение."
        await message.answer(usage, parse_mode="HTML")
        return
    try:
        duration_str = duration_str.lower().replace(" ", "")
        if duration_str.endswith("m"): total_seconds, time_str = int(duration_str[:-1]) * 60, f"{int(duration_str[:-1])} мин"
        elif duration_str.endswith("h"): total_seconds, time_str = int(duration_str[:-1]) * 3600, f"{int(duration_str[:-1])} час"
        elif duration_str.endswith("d"): total_seconds, time_str = int(duration_str[:-1]) * 86400, f"{int(duration_str[:-1])} дней"
        else: total_seconds, time_str = int(duration_str) * 60, f"{int(duration_str)} мин"
    except (ValueError, AttributeError):
        await message.answer("❌ Error format. Ex: 10m, 2h, 1d" if lang == 'en' else "❌ Неверный формат. Примеры: 10m, 2h, 1d")
        await message.delete()
        return
    expires_ts = time.time() + total_seconds
    b_data = board_data[board_id]
    threads_data = b_data.get('threads_data', {})
    for thread_info in threads_data.values():
        thread_info.setdefault('local_shadow_mutes', {})[target_id] = expires_ts
    phrases = thread_messages.get(lang, {}).get('shadowmute_threads_success', ["Shadowmuted in threads."])
    response_text = random.choice(phrases).format(
        user_id=target_id, 
        duration=str(int(total_seconds / 60))
    )
    await message.answer(response_text)
    await message.delete()

@router.message(Command("deletethread", "delthread", "delete_thread"))
async def cmd_delete_thread(message: Message, board_id: str | None, stream: str = 'ru'):
    """
    Удаляет тред: помечает архивным в БД и вычищает из RAM.

    Команда объявлена в админском меню (setup_bot_commands), а рабочая
    delete_thread_atomic существовала без единого вызова — админ видел
    /deletethread в меню, но она ничего не делала. Здесь связаны обе части:
    archive_thread_in_db даёт персистентность (иначе тред вернулся бы после
    рестарта из таблицы Threads), delete_thread_atomic убирает его из памяти
    и возвращает читателей на главную.
    """
    if not board_id or not is_admin(message.from_user.id, board_id) or board_id not in THREAD_BOARDS:
        try:
            await message.delete()
        except TelegramBadRequest:
            import traceback; traceback.print_exc()
        return

    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    args = (message.text or message.caption or "").split()[1:]
    b_data = board_data[board_id]
    threads_data = b_data.get('threads_data', {})

    # Без аргумента удаляем тред, в котором админ сейчас находится.
    thread_id = args[0].lstrip('#') if args else None
    if not thread_id:
        location = b_data.get('user_state', {}).get(message.from_user.id, {}).get('location', 'main')
        if location and location != 'main':
            thread_id = str(location)

    if not thread_id:
        if lang == 'en':
            usage = "Usage: <code>/deletethread &lt;thread_id&gt;</code>, or run it inside the thread."
        elif lang == 'jp':
            usage = "使用法: <code>/deletethread &lt;thread_id&gt;</code>、またはスレッド内で実行。"
        else:
            usage = "Использование: <code>/deletethread &lt;id треда&gt;</code>, либо вызови внутри треда."
        await message.answer(usage, parse_mode="HTML")
        return

    thread_info = threads_data.get(thread_id)
    if not thread_info:
        if lang == 'en':
            not_found = f"❌ Thread <code>{escape_html(thread_id)}</code> not found on this board."
        elif lang == 'jp':
            not_found = f"❌ スレッド <code>{escape_html(thread_id)}</code> はこの板に存在しません。"
        else:
            not_found = f"❌ Тред <code>{escape_html(thread_id)}</code> не найден на этой доске."
        await message.answer(not_found, parse_mode="HTML")
        return

    title = thread_info.get('title') or thread_id
    posts_count = len(thread_info.get('posts', []))

    # Сначала персистентно: если упадём после очистки RAM, тред не должен
    # «воскреснуть» активным при следующем старте.
    try:
        from common.database import archive_thread_in_db
        await archive_thread_in_db(int(thread_id))
    except (TypeError, ValueError):
        print(f"⚠️ [/deletethread] thread_id '{thread_id}' не приводится к int, пропускаю запись в БД.")
    except Exception as e:
        print(f"⛔ [/deletethread] Не удалось архивировать тред #{thread_id} в БД: {e}")
        if lang == 'en':
            await message.answer("❌ DB error, thread left untouched.")
        else:
            await message.answer("❌ Ошибка БД, тред не тронут.")
        return

    await delete_thread_atomic(
        message.bot, board_id, thread_id,
        notify_users=True, initiator_id=message.from_user.id
    )

    if lang == 'en':
        done = f"🗑 Thread <b>{escape_html(str(title))}</b> (<code>{escape_html(thread_id)}</code>) deleted, {posts_count} posts purged."
    elif lang == 'jp':
        done = f"🗑 スレッド <b>{escape_html(str(title))}</b> (<code>{escape_html(thread_id)}</code>) を削除しました（{posts_count} レス）。"
    else:
        done = f"🗑 Тред <b>{escape_html(str(title))}</b> (<code>{escape_html(thread_id)}</code>) удалён, вычищено постов: {posts_count}."
    await message.answer(done, parse_mode="HTML")
    try:
        await message.delete()
    except (TelegramBadRequest, TelegramForbiddenError):
        pass

@router.message(Command("sdel", "swipe"))
async def cmd_sdel(message: types.Message, board_id: str | None, stream: str = 'ru'):
    """
    "Теневое" удаление поста. Удаляет все копии сообщения, кроме
    копии у автора оригинального поста. Доступно только админам.
    """
    if not board_id or not is_admin(message.from_user.id, board_id):
        try: await message.delete()
        except TelegramBadRequest: pass
        return
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    if not message.reply_to_message:
        if lang == 'en': msg = "Reply to a message to use this: <code>/sdel</code>"
        elif lang == 'jp': msg = "返信して使ってください: <code>/sdel</code>"
        else: msg = "⚠️ Ответьте на сообщение, которое хотите тихо удалить: <code>/sdel</code>"
        await message.answer(msg, parse_mode="HTML")
        await message.delete()
        return
    post_info = await get_post_info_by_copy(message.chat.id, message.reply_to_message.message_id)
    if not post_info:
        err = "Post not found in DB." if lang == 'en' else "Не удалось найти исходный пост в базе данных."
        await message.answer(err)
        await message.delete()
        return
    post_num, author_id = post_info
    all_copies = await get_post_copies(post_num)
    if not all_copies:
        err = f"No copies found for #{post_num}." if lang == 'en' else f"Не найдено отправленных копий для поста #{post_num}."
        await message.answer(err)
        await message.delete()
        return
    wait_txt = "🧹 Сношу посты этого юзера..." if lang != 'en' else "🧹 Wiping posts..."
    wait_msg = await message.answer(wait_txt)
    tasks = []
    for recipient_id, message_id in all_copies:
        if recipient_id != author_id:
            task = message.bot.delete_message(recipient_id, message_id)
            tasks.append(task)
    results = await asyncio.gather(*tasks, return_exceptions=True)
    deleted_count = sum(1 for res in results if res is True)
    await log_global_event('bot', f"👻 SDEL: Админ {message.from_user.id} скрытно удалил пост #{post_num} на /{board_id}/ (удалено {deleted_count} копий)")
    if lang == 'en':
        report = f"👻 Post #{post_num} shadow deleted.\nRemoved copies: {deleted_count} of {len(all_copies) - 1}."
    elif lang == 'jp':
        report = f"👻 投稿 #{post_num} をシャドウ削除しました。\n削除数: {deleted_count} / {len(all_copies) - 1}."
    else:
        report = f"👻 Пост #{post_num} был 'теневым' образом удален.\nУдалено копий: {deleted_count} из {len(all_copies) - 1}."
    try: await wait_msg.delete()
    except Exception as e: pass
    await message.answer(report)
    try:
        await message.delete()
    except (TelegramBadRequest, TelegramForbiddenError):
        pass

@router.message(Command("unban"))
async def cmd_unban(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id or not is_admin(message.from_user.id, board_id):
        return
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    target_id = None
    if message.reply_to_message:
        target_id = await get_author_id_by_reply(message)
    
    args = (message.text or message.caption or "").split()
    if len(args) >= 2:
        try:
            target_id = int(args[1])
        except ValueError:
            import traceback; traceback.print_exc()
            
    if target_id is None:
        if lang == 'en': usage = "Usage: <code>/unban &lt;user_id&gt;</code> or reply to user message."
        elif lang == 'jp': usage = "使用法: <code>/unban &lt;user_id&gt;</code> またはユーザーメッセージに返信します。"
        else: usage = "Использование: <code>/unban &lt;user_id&gt;</code> или ответ на сообщение пользователя."
        await message.answer(usage, parse_mode="HTML")
        try: await message.delete()
        except Exception as e: pass
        return
        
    unbanned = False
    async with storage_lock:
        b_data = board_data[board_id]
        if target_id in b_data['users']['banned']:
            b_data['users']['banned'].discard(target_id)
            b_data['users']['active'].add(target_id)
            unbanned = True
            
    board_name = BOARD_CONFIG[board_id]['name']
    if unbanned:
        await add_or_activate_user(target_id, board_id) 
        if lang == 'en': msg = f"User {target_id} unbanned on {board_name}."
        elif lang == 'jp': msg = f"ユーザー {target_id} のBANを解除しました ({board_name})。"
        else: msg = f"Пользователь {target_id} разбанен на доске {board_name}."
        await message.answer(msg)
    else:
        if lang == 'en': msg = f"User {target_id} was not banned."
        elif lang == 'jp': msg = f"ユーザー {target_id} はBANされていません。"
        else: msg = f"Пользователь {target_id} не был забанен на этой доске."
        await message.answer(msg)
    try: await message.delete()
    except Exception as e: pass

@router.message(Command("del"))
async def cmd_del(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id: return
    user_id = message.from_user.id
    admin_status = is_admin(user_id, board_id)
    is_janitor = False
    janitor_deletes_left = 0
    active_items = {}
    db = None
    if not admin_status:
        import json
        import time
        db = await get_pool()
        async with db.execute(
            "SELECT active_items FROM Users WHERE user_id = ? AND board_id = ?", (user_id, board_id)
        ) as c:
            row = await c.fetchone()
            ai_str = row[0] if row and row[0] else "{}"
        try:
            active_items = json.loads(ai_str)
        except Exception:
            active_items = {}
        janitor_until = active_items.get("janitor_until", 0)
        janitor_deletes_left = active_items.get("janitor_deletes_left", 0)
        if janitor_until > time.time() and janitor_deletes_left > 0:
            is_janitor = True
    if not admin_status and not is_janitor:
        return
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    if not message.reply_to_message:
        msg = "Reply to a message: <code>/del</code>" if lang == 'en' else               ("返信して使ってください: <code>/del</code>" if lang == 'jp' else                "⚠️ Ответьте на сообщение, которое хотите удалить: <code>/del</code>")
        await message.answer(msg, parse_mode="HTML")
        return
    post_num = None
    async with storage_lock:
        key = (message.chat.id, message.reply_to_message.message_id)
        post_num = message_to_post.get(key)
    if not post_num:
        info = await get_post_info_by_copy(message.chat.id, message.reply_to_message.message_id)
        if info: post_num = info[0]
    if post_num is None:
        err = "Post not found." if lang == 'en' else               ("投稿が見つかりません。" if lang == 'jp' else                "Не нашёл этот пост (возможно, он слишком старый или удалён).")
        await message.answer(err)
        return
    if is_janitor:
        import json
        if not db:
            db = await get_pool()
        janitor_deletes_left -= 1
        active_items["janitor_deletes_left"] = janitor_deletes_left
        async with db_lock:
            await db.execute(
                "UPDATE Users SET active_items = ? WHERE user_id = ? AND board_id = ?",
                (json.dumps(active_items), user_id, board_id)
            )
            await db.commit()
    deleted_count = await delete_single_post(post_num, message.bot)
    role_str = "Админ" if admin_status else "Дворник"
    await log_global_event('bot', f"🗑️ DEL: {role_str} {user_id} удалил пост #{post_num} на /{board_id}/ (и {deleted_count} копий)")
    if lang == 'en':
        resp = f"🗑 Post #{post_num} deleted ({deleted_count} copies)."
        if is_janitor:
            resp += f" 🧹 Janitor Ticket: {janitor_deletes_left} deletes remaining."
    elif lang == 'jp':
        resp = f"🗑 投稿 #{post_num} とコピー ({deleted_count}件) を削除しました。"
        if is_janitor:
            resp += f" 🧹 掃除員チケット: 残り {janitor_deletes_left} 回。"
    else:
        resp = f"🗑 Пост №{post_num} и копии ({deleted_count}) удалены."
        if is_janitor:
            resp += f" 🧹 Удалено как Дворник (по Билету). Осталось: {janitor_deletes_left} удалений."
    await message.answer(resp)
    try: await message.delete()
    except Exception as e: pass

@router.message(Command("token"))
async def cmd_token(message: types.Message, board_id: str | None, stream: str = 'ru'):
    """
    Генерирует или показывает пользователю его персональный токен для входа на сайт.
    """
    if not board_id: return
    user_id = message.from_user.id
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    try:
        token = await get_or_create_api_token(user_id, generate_unique_token)
        WEBAPP_URL_DISPLAY = "https://tgach.top" 
        if lang == 'en':
            response_text = (
                "🔑 **Your personal token for website access:**\n\n"
                f"Use it to log in on {WEBAPP_URL_DISPLAY}. **Do not share it with anyone.**\n\n"
                "Tap the token below to copy it:"
            )
        elif lang == 'jp':
            response_text = (
                "🔑 **ウェブサイトアクセスのための個人トークン:**\n\n"
                f"{WEBAPP_URL_DISPLAY} でログインするために使用します。**他人には教えないでください。**\n\n"
                "下のトークンをタップしてコピー:"
            )
        else:
            response_text = (
                "🔑 **Ваш токен для входа на сайт ТГАЧа:**\n\n"
                f"Используйте его для входа на {WEBAPP_URL_DISPLAY}.\n**Никому его не показывайте.**\n\n"
                "Нажмите на токен ниже, чтобы скопировать его:"
            )
        token_display = f"<code>{token}</code>"
        await message.answer(response_text, parse_mode="HTML")
        await message.answer(token_display, parse_mode="HTML")
    except Exception as e:
        print(f"⛔ Критическая ошибка при генерации токена для user {user_id}: {e}")
        if lang == 'en': error = "An error occurred while creating the token."
        elif lang == 'jp': error = "トークンの作成中にエラーが発生しました。"
        else: error = "Произошла ошибка при создании токена."
        await message.answer(error)
    try:
        await message.delete()
    except (TelegramBadRequest, TelegramForbiddenError):
        pass

@router.callback_query(F.data.startswith("admin_menu:"))
async def process_admin_menu(callback: types.CallbackQuery, board_id: str | None, stream: str = 'ru'):
    if not board_id or not is_admin(callback.from_user.id, board_id):
        await callback.answer("У вас нет прав.", show_alert=True)
        return
        
    action = callback.data.split(":")[1]
    b_data = board_data[board_id]
    
    if action == "lockdown":
        from common.database import set_system_setting
        is_lockdown = b_data.get('lockdown', False)
        # toggle it
        new_val = not is_lockdown
        b_data['lockdown'] = new_val
        await set_system_setting('lockdown_enabled', "true" if new_val else "false")
        
        # update keyboard
        # we can just answer it for now
        status = "ВКЛЮЧЕН" if new_val else "ВЫКЛЮЧЕН"
        await callback.answer(f"Локдаун {status}", show_alert=True)
