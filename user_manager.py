import asyncio
import time
import math
from typing import Callable, Awaitable, Optional
from aiogram.filters import Command
from bot_helpers import *
from post_helpers import *
from shared_state import *
from media_utils import _download_image_with_proxy, _resize_image_if_needed
from aiogram import Router, F, types
from aiogram.types import Message, WebAppInfo
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest, TelegramRetryAfter, TelegramAPIError
from deanonymizer import generate_deanon_info
from common.database import get_post_info_by_copy, get_post_by_num, get_post_author_by_copy, get_pool, update_user_settings_db
from common.html_utils import escape_html
from thread_texts import thread_messages
from text_assets import INVITE_TEXTS, INVITE_TEXTS_EN, INVITE_TEXTS_JP, DEANON_COOLDOWN_PHRASES
from common.db_pool import db_lock
import io
from post_helpers import format_header

router = Router()

@router.message(Command("shadowmute"))
async def cmd_shadowmute(message: Message, board_id: str | None, stream: str = 'ru'):
    if not board_id or not is_admin(message.from_user.id, board_id):
        return
    args = (message.text or message.caption or "").split()[1:]
    target_id = None
    duration_str = "24h"
    if message.reply_to_message:
        target_id = await get_author_id_by_reply(message)
        if args:
            duration_str = args[0]
    elif args:
        try:
            target_id = int(args[0])
            if len(args) > 1:
                duration_str = args[1]
        except ValueError:
            runtime_logger.warning(f"Invalid target_id for shadowmute: {args[0]}")
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    if not target_id:
        if lang == 'en':
            usage = "Usage: <code>/shadowmute &lt;user_id&gt; [time]</code> or reply."
        elif lang == 'jp':
            usage = "使用法: <code>/shadowmute &lt;user_id&gt; [時間]</code> または返信。"
        else:
            usage = "Использование: <code>/shadowmute &lt;user_id&gt; [время]</code> или ответом на сообщение."
        await message.answer(usage, parse_mode="HTML")
        return
    try:
        duration_str = duration_str.lower().replace(" ", "")
        if duration_str.endswith("m"): total_seconds, time_str = int(duration_str[:-1]) * 60, f"{int(duration_str[:-1])} мин"
        elif duration_str.endswith("h"): total_seconds, time_str = int(duration_str[:-1]) * 3600, f"{int(duration_str[:-1])} час"
        elif duration_str.endswith("d"): total_seconds, time_str = int(duration_str[:-1]) * 86400, f"{int(duration_str[:-1])} дней"
        else: total_seconds, time_str = int(duration_str) * 60, f"{int(duration_str)} мин"
        total_seconds = min(total_seconds, 2592000)
        expires_dt = datetime.now(UTC) + timedelta(seconds=total_seconds)
        async with storage_lock:
            b_data = board_data[board_id]
            b_data['shadow_mutes'][target_id] = expires_dt
        await update_shadow_mute(target_id, board_id, expires_dt.timestamp())
        await log_global_event('bot', f"👻 SHADOWMUTE: Мод {message.from_user.id} скрыл {target_id} на /{board_id}/ до {expires_dt.strftime('%H:%M:%S')}")
        board_name = BOARD_CONFIG[board_id]['name']
        if lang == 'en':
            msg = f"👻 Shadowmuted user <code>{target_id}</code> for {time_str} on {board_name}."
        elif lang == 'jp':
            msg = f"👻 ユーザー <code>{target_id}</code> を {board_name} で {time_str} シャドウミュートしました。"
        else:
            msg = f"👻 Тихо замучен пользователь <code>{target_id}</code> на {time_str} на доске {board_name}."
        await message.answer(msg, parse_mode="HTML")
    except ValueError:
        err = "❌ Invalid format. Ex: <code>30m</code>, <code>2h</code>" if lang == 'en' else "❌ Неверный формат времени. Примеры: <code>30m</code>, <code>2h</code>, <code>1d</code>"
        await message.answer(err, parse_mode="HTML")
    await message.delete()

@router.message(Command("nsfw"))
async def cmd_nsfw(message: types.Message, board_id: str | None, stream: str = 'ru'):

    if not board_id: return
    args = (message.text or message.caption or "").split()
    user_id = message.from_user.id
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    b_data = board_data[board_id]
    if user_id not in b_data.get('user_settings', {}):
        b_data.setdefault('user_settings', {})[user_id] = {'nsfw': False, 'hide': set()}
    current_status = b_data['user_settings'][user_id]['nsfw']
    if len(args) < 2:
        status_on = "ON"
        status_off = "OFF"
        if lang == 'en':
            msg = f"Current NSFW Spoiler status: <b>{status_on if current_status else status_off}</b>.\nUsage: <code>/nsfw on</code> or <code>/nsfw off</code>"
        elif lang == 'jp':
            msg = f"現在のNSFW設定: <b>{status_on if current_status else status_off}</b>\n使い方: <code>/nsfw on</code> または <code>/nsfw off</code>"
        else:
            msg = f"Текущий статус NSFW спойлера: <b>{status_on if current_status else status_off}</b>.\nИспользование: <code>/nsfw on</code> или <code>/nsfw off</code>"
        await message.answer(msg, parse_mode="HTML")
        return
    action = args[1].lower()
    new_status = None
    if action in ['on', 'enable', '1', 'вкл']:
        new_status = True
    elif action in ['off', 'disable', '0', 'выкл']:
        new_status = False
    if new_status is not None:
        b_data['user_settings'][user_id]['nsfw'] = new_status
        spawn_task(update_user_settings_db(user_id, board_id, nsfw=1 if new_status else 0))
        if lang == 'en':
            reply = "✅ NSFW Spoilers enabled." if new_status else "☑️ NSFW Spoilers disabled."
        elif lang == 'jp':
            reply = "✅ NSFWスポイラーを有効にしました。" if new_status else "☑️ NSFWスポイラーを無効にしました。"
        else:
            reply = "✅ Спойлеры для картинок включены." if new_status else "☑️ Спойлеры для картинок выключены."
        await message.answer(reply)
    else:
        err = "Error: Use 'on' or 'off'." if lang != 'ru' else "Ошибка: Используйте 'on' или 'off'."
        await message.answer(err)

@router.message(Command("settings", "настройки", "настройка", "setting", "options", "prefs", ignore_case=True, ignore_mention=True))
async def cmd_settings(message: types.Message, board_id: str | None, stream: str = 'ru'):
    """
    Открывает меню личных настроек пользователя (/settings).
    """
    if not board_id: return
    user_id = message.from_user.id
    from main import get_personal_menu_keyboard
    text, kb = get_personal_menu_keyboard(board_id, user_id, stream=stream)
    from banner_manager import send_banner_message
    await send_banner_message(
        bot=message.bot,
        chat_id=message.chat.id,
        caption=text,
        reply_markup=kb,
        category="start",
        parse_mode="HTML"
    )
    try:
        await message.delete()
    except Exception:
        pass

@router.message(Command("slop", "roast", "roasts", "слоп", "нейрослоп", ignore_case=True, ignore_mention=True))
async def cmd_toggle_ai_slop(message: types.Message, board_id: str | None, stream: str = 'ru'):
    """
    Команда быстрого включения/выключения AI-роастов и нейрослопа (/slop on / off / hide / show).
    """
    if not board_id: return
    args = (message.text or message.caption or "").split()
    user_id = message.from_user.id
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    b_data = board_data[board_id]
    if user_id not in b_data.get('user_settings', {}):
        b_data.setdefault('user_settings', {})[user_id] = {'nsfw': False, 'hide': set(), 'disable_ai_roasts': False, 'hide_ai_slop': False}
    current_status = bool(b_data['user_settings'][user_id].get('disable_ai_roasts') or b_data['user_settings'][user_id].get('hide_ai_slop'))
    if len(args) < 2:
        status_str = ("Скрыт 🚫" if current_status else "Включен 👁") if lang == 'ru' else ("Hidden 🚫" if current_status else "Enabled 👁")
        if lang == 'en':
            msg = f"Current AI Roasts / Slop filter status: <b>{status_str}</b>.\nUsage: <code>/slop hide</code> (or <code>/slop on</code>) / <code>/slop show</code> (or <code>/slop off</code>)"
        elif lang == 'jp':
            msg = f"現在のAI煽り・スロップ設定: <b>{status_str}</b>\n使い方: <code>/slop hide</code> または <code>/slop show</code>"
        else:
            msg = f"Текущий статус фильтра AI-разъёбов / нейрослопа: <b>{status_str}</b>.\nИспользование: <code>/slop hide</code> (скрыть) или <code>/slop show</code> (показывать)"
        await message.answer(msg, parse_mode="HTML")
        return
    action = args[1].lower()
    new_status = None
    if action in ['on', 'enable', 'hide', '1', 'вкл', 'скрыть', 'disable_roasts', 'mute']:
        new_status = True
    elif action in ['off', 'disable', 'show', '0', 'выкл', 'показать', 'enable_roasts', 'unmute']:
        new_status = False
    if new_status is not None:
        b_data['user_settings'][user_id]['disable_ai_roasts'] = new_status
        b_data['user_settings'][user_id]['hide_ai_slop'] = new_status
        spawn_task(update_user_settings_db(user_id, board_id, disable_ai_roasts=1 if new_status else 0, hide_ai_slop=1 if new_status else 0))
        if lang == 'en':
            reply = "🚫 AI Roasts and Neuro-Slop are now hidden." if new_status else "👁 AI Roasts and Neuro-Slop are now enabled."
        elif lang == 'jp':
            reply = "🚫 AI煽り・スロップを非表示にしました。" if new_status else "👁 AI煽り・スロップを表示します。"
        else:
            reply = "🚫 AI-разъёбы и нейрослоп теперь скрыты." if new_status else "👁 AI-разъёбы и нейрослоп теперь включены."
        await message.answer(reply)
    else:
        err = "Error: Use 'hide' / 'on' or 'show' / 'off'." if lang != 'ru' else "Ошибка: Используйте 'hide' / 'on' или 'show' / 'off'."
        await message.answer(err)

@router.message(Command("hide"))
async def cmd_hide(message: types.Message, board_id: str | None, stream: str = 'ru'):

    if not board_id: return
    args = (message.text or message.caption or "").split()
    user_id = message.from_user.id
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    b_data = board_data[board_id]
    if user_id not in b_data.get('user_settings', {}):
        b_data.setdefault('user_settings', {})[user_id] = {'nsfw': False, 'hide': set(), 'disable_ai_roasts': False, 'hide_ai_slop': False}
    
    settings = b_data['user_settings'][user_id]
    raw_hide = settings.get('hide', set())
    if not isinstance(raw_hide, set):
        raw_hide = set(raw_hide) if raw_hide else set()
    user_hide_set = {str(w).strip().lower() for w in raw_hide if str(w).strip()}
    settings['hide'] = user_hide_set

    if len(args) < 2:
        if lang == 'en':
            help_text = (
                "<b>Hide Words Management:</b>\n"
                "/hide list - Show hidden words\n"
                "/hide add &lt;word&gt; - Add word to filter\n"
                "/hide remove &lt;word&gt; - Remove word"
            )
        elif lang == 'jp':
            help_text = (
                "<b>NGワード管理:</b>\n"
                "/hide list - リストを表示\n"
                "/hide add <単語> - 追加\n"
                "/hide remove <単語> - 削除"
            )
        else:
            help_text = (
                "<b>Управление скрытием слов:</b>\n"
                "/hide list - Список скрытых слов\n"
                "/hide add <слово> - Добавить слово\n"
                "/hide remove <слово> - Убрать слово"
            )
        await message.answer(help_text, parse_mode="HTML")
        return
    action = args[1].lower()
    if action == 'list':
        if not user_hide_set:
            if lang == 'en': txt = "Your hidden words list is empty."
            elif lang == 'jp': txt = "NGワードリストは空です。"
            else: txt = "Ваш список скрытых слов пуст."
            await message.answer(txt)
        else:
            sorted_words = sorted(list(user_hide_set))
            words_str = ", ".join([f"<code>{escape_html(w)}</code>" for w in sorted_words])
            if lang == 'en': header = f"🚫 <b>Hidden words ({len(sorted_words)}):</b>"
            elif lang == 'jp': header = f"🚫 <b>NGワード ({len(sorted_words)}):</b>"
            else: header = f"🚫 <b>Скрытые слова ({len(sorted_words)}):</b>"
            await message.answer(f"{header}\n{words_str}", parse_mode="HTML")
    elif action == 'add':
        word_part = (message.text or message.caption or "").split(maxsplit=2)
        if len(word_part) < 3 or not word_part[2].strip():
             err = "Usage: /hide add &lt;word&gt;"
             await message.answer(err)
             return
        word = word_part[2].strip().lower()
        if len(word) < 2:
            if lang == 'en': err = "Word too short."
            elif lang == 'jp': err = "単語が短すぎます。"
            else: err = "Слово слишком короткое."
            await message.answer(err)
            return
        if word not in user_hide_set and len(user_hide_set) >= 60:
            if lang == 'en': msg = "🚫 Limit exceeded! Max 60 hidden words allowed."
            elif lang == 'jp': msg = "🚫 制限を超えました！最大60語までです。"
            else: msg = "🚫 Лимит превышен! Максимум 60 скрытых слов."
            await message.answer(msg, parse_mode="HTML")
            return
        user_hide_set.add(word)
        spawn_task(update_user_settings_db(user_id, board_id, hidden_words=sorted(list(user_hide_set))))
        if lang == 'en': msg = f"✅ Word '<b>{escape_html(word)}</b>' added to hidden list."
        elif lang == 'jp': msg = f"✅ '<b>{escape_html(word)}</b>' をリストに追加しました。"
        else: msg = f"✅ Слово '<b>{escape_html(word)}</b>' добавлено в скрытые."
        await message.answer(msg, parse_mode="HTML")
    elif action in ('remove', 'del', 'delete', 'rm'):
        word_part = (message.text or message.caption or "").split(maxsplit=2)
        if len(word_part) < 3 or not word_part[2].strip():
             await message.answer("Usage: /hide remove &lt;word&gt;")
             return
        word = word_part[2].strip().lower()
        if word in user_hide_set:
            user_hide_set.discard(word)
            spawn_task(update_user_settings_db(user_id, board_id, hidden_words=sorted(list(user_hide_set))))
            if lang == 'en': msg = f"🗑 Word '<b>{escape_html(word)}</b>' removed from list."
            elif lang == 'jp': msg = f"🗑 '<b>{escape_html(word)}</b>' を削除しました。"
            else: msg = f"🗑 Слово '<b>{escape_html(word)}</b>' удалено из списка."
            await message.answer(msg, parse_mode="HTML")
        else:
            user_hide_set.discard(word)
            spawn_task(update_user_settings_db(user_id, board_id, hidden_words=sorted(list(user_hide_set))))
            if lang == 'en': msg = "Word not found in your list."
            elif lang == 'jp': msg = "リストに見つかりません。"
            else: msg = "Слово не найдено в вашем списке."
            await message.answer(msg)

@router.message(Command("unshadowmute"))
async def cmd_unshadowmute(message: types.Message, board_id: str | None, stream: str = 'ru'):
    """
    Единый обработчик снятия теневого бана.
    - Админ: Снимает теневой бан с пользователя на всей доске.
    - ОП треда: Снимает локальный теневой бан внутри треда.
    """
    if not board_id: return
    user_id = message.from_user.id
    is_adm = is_admin(user_id, board_id)
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    b_data = board_data[board_id]
    if not is_adm:
        if board_id not in THREAD_BOARDS: 
            try: await message.delete()
            except Exception as e: pass
            return
        user_s = b_data.get('user_state', {}).get(user_id, {})
        location = user_s.get('location', 'main')
        if location == 'main':
            await message.delete()
            return
        thread_info = b_data.get('threads_data', {}).get(location)
        if not thread_info or thread_info.get('op_id') != user_id:
            await message.delete()
            return
        now_ts = time.time()
        if now_ts - user_s.get('last_op_command_ts', 0) < OP_COMMAND_COOLDOWN:
            await message.delete()
            return
        user_s['last_op_command_ts'] = now_ts
        if not message.reply_to_message:
            await message.delete()
            return
        target_id = None
        target_id = await get_author_id_by_reply(message)
        if not target_id:
            await message.delete()
            return
        local_shadow_mutes = thread_info.get('local_shadow_mutes', {})
        if target_id in local_shadow_mutes:
            del local_shadow_mutes[target_id]
            phrases = thread_messages.get(lang, {}).get('op_unmute_success', ["Unmuted."])
            response_text = random.choice(phrases)
            await message.answer(f"👻 (shadow) {response_text}", parse_mode=None)
        await message.delete()
        return
    target_id = None
    if message.reply_to_message:
        target_id = await get_author_id_by_reply(message)
    else:
        parts = (message.text or message.caption or "").split()
        if len(parts) == 2:
            try: target_id = int(parts[1])
            except ValueError: pass
    if not target_id:
        if lang == 'en':
            msg = "Usage: <code>/unshadowmute &lt;id&gt;</code> or reply."
        elif lang == 'jp':
            msg = "使用法: <code>/unshadowmute &lt;ID&gt;</code> または返信。"
        else:
            msg = "Использование: <code>/unshadowmute &lt;id&gt;</code> или ответом на сообщение."
        await message.answer(msg, parse_mode="HTML")
        return
    was_muted = False
    async with storage_lock:
        if target_id in b_data['shadow_mutes']:
            del b_data['shadow_mutes'][target_id]
            was_muted = True
    await update_shadow_mute(target_id, board_id, 0)
    if was_muted:
        if lang == 'en':
            resp = f"👻 User <code>{target_id}</code> un-shadowmuted."
        elif lang == 'jp':
            resp = f"👻 ユーザー <code>{target_id}</code> のシャドウミュートを解除しました。"
        else:
            resp = f"👻 С пользователя <code>{target_id}</code> снят теневой мут."
        await message.answer(resp, parse_mode="HTML")
    else:
        if lang == 'en':
            resp = f"User <code>{target_id}</code> was not shadowmuted."
        elif lang == 'jp':
            resp = f"ユーザー <code>{target_id}</code> はシャドウミュートされていません。"
        else:
            resp = f"Пользователь <code>{target_id}</code> не был в теневом муте."
        await message.answer(resp, parse_mode="HTML")
    try:
        await message.delete()
    except TelegramBadRequest:
        pass
    except Exception as e:
        runtime_logger.warning(f"cmd_unshadowmute message.delete failed: {e}")

@router.message(Command("invite"))
async def cmd_invite(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id: return
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    board_username = BOARD_CONFIG[board_id]['username']
    site_url = f"https://tgach.top/{board_id}/"

    if lang == 'en':
        source_list = INVITE_TEXTS_EN
        pic_btn = "🖼 Generate Picture + QR"
    elif lang == 'jp':
        source_list = INVITE_TEXTS_JP
        pic_btn = "🖼 QR画像作成"
    else:
        source_list = INVITE_TEXTS
        pic_btn = "🖼 Картинка с QR"
    invite_text_raw = random.choice(source_list)
    invite_text = invite_text_raw.replace("@dvach_chatbot", board_username).replace("@tgchan_chatbot", board_username)
    
    if lang == 'en':
        header = "📨 <b>Invite text for this board:</b>"
        footer = "<i>Just copy and send</i>"
        site_btn = "🌐 Web Version"
    elif lang == 'jp':
        header = "📨 <b>この板の招待用テキスト:</b>"
        footer = "<i>コピーして送信してください</i>"
        site_btn = "🌐 ウェブ版"
    else:
        header = "📨 <b>Текст для приглашения анонов на эту доску:</b>"
        footer = "<i>Просто скопируй и отправь</i>"
        site_btn = "🌐 Веб-версия"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=site_btn, url=site_url),
            InlineKeyboardButton(text=pic_btn, callback_data=f"gen_invite_pic:{board_id}")
        ]
    ])

    await message.answer(
        f"{header}\n\n<code>{escape_html(invite_text)}</code>\n\n{footer}",
        parse_mode="HTML",
        reply_markup=keyboard
    )
    try:
        await message.delete()
    except Exception:
        pass

@router.message(Command("invite_pic", "picinvite", "invitepic"))
async def cmd_invite_pic(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id: return
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    board_username = BOARD_CONFIG[board_id]['username']
    site_url = f"https://tgach.top/{board_id}/"

    if lang == 'en':
        source_list = INVITE_TEXTS_EN
        caption_header = "📨 <b>Graphic invite for this board:</b>"
        site_btn = "🌐 Web Version"
    elif lang == 'jp':
        source_list = INVITE_TEXTS_JP
        caption_header = "📨 <b>この板の画像招待状:</b>"
        site_btn = "🌐 ウェブ版"
    else:
        source_list = INVITE_TEXTS
        caption_header = "🖼 <b>Картинка-приглашение с QR-кодом:</b>"
        site_btn = "🌐 Веб-версия"

    invite_text_raw = random.choice(source_list)
    invite_text = invite_text_raw.replace("@dvach_chatbot", board_username).replace("@tgchan_chatbot", board_username)

    from invite_image_generator import generate_invite_image_async
    from aiogram.types import BufferedInputFile

    try:
        buf = await generate_invite_image_async(board_id=board_id, bot_username=board_username, custom_text=invite_text)
        input_file = BufferedInputFile(buf.getvalue(), filename=f"invite_{board_id}.jpg")
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=site_btn, url=site_url)]
        ])
        await message.answer_photo(
            photo=input_file,
            caption=f"{caption_header}\n\n<code>{escape_html(invite_text)}</code>",
            parse_mode="HTML",
            reply_markup=keyboard
        )
    except Exception as e:
        runtime_logger.error(f"cmd_invite_pic error: {e}")
        await message.answer(f"<code>{escape_html(invite_text)}</code>", parse_mode="HTML")
    finally:
        try:
            await message.delete()
        except Exception:
            pass

@router.callback_query(F.data.startswith("gen_invite_pic:"))
async def callback_gen_invite_pic(callback: types.CallbackQuery, board_id: str | None = None, stream: str = 'ru'):
    target_board = callback.data.split(":", 1)[1] if ":" in callback.data else (board_id or "b")
    board_username = BOARD_CONFIG.get(target_board, {}).get('username', '@dvach_chatbot')
    lang = stream if ENABLE_MULTILANG else ('en' if target_board == 'int' else 'ru')
    site_url = f"https://tgach.top/{target_board}/"

    if lang == 'en':
        source_list = INVITE_TEXTS_EN
        caption_header = "📨 <b>Graphic invite for this board:</b>"
        site_btn = "🌐 Web Version"
    elif lang == 'jp':
        source_list = INVITE_TEXTS_JP
        caption_header = "📨 <b>この板の画像招待状:</b>"
        site_btn = "🌐 ウェブ版"
    else:
        source_list = INVITE_TEXTS
        caption_header = "🖼 <b>Картинка-приглашение с QR-кодом:</b>"
        site_btn = "🌐 Веб-версия"

    invite_text_raw = random.choice(source_list)
    invite_text = invite_text_raw.replace("@dvach_chatbot", board_username).replace("@tgchan_chatbot", board_username)

    from invite_image_generator import generate_invite_image_async
    from aiogram.types import BufferedInputFile

    try:
        await callback.answer("Генерирую картинку...")
    except Exception:
        pass

    try:
        buf = await generate_invite_image_async(board_id=target_board, bot_username=board_username, custom_text=invite_text)
        input_file = BufferedInputFile(buf.getvalue(), filename=f"invite_{target_board}.jpg")
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=site_btn, url=site_url)]
        ])
        await callback.message.answer_photo(
            photo=input_file,
            caption=f"{caption_header}\n\n<code>{escape_html(invite_text)}</code>",
            parse_mode="HTML",
            reply_markup=keyboard
        )
    except Exception as e:
        runtime_logger.error(f"callback_gen_invite_pic error: {e}")


@router.message(Command("queues"))
async def cmd_check_queues(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id or not is_admin(message.from_user.id, board_id): return
    from common.database import get_system_queue_counts
    db_stats = await get_system_queue_counts()
    import __main__ as main
    runtime_snapshot = main._collect_runtime_snapshot()
    queues = runtime_snapshot.get("queues", {})
    delivery_priority = runtime_snapshot.get("delivery_priority", {})
    recipients_snapshot = runtime_snapshot.get("recipients", {})
    anime_media_snapshot = runtime_snapshot.get("anime_media", {})
    durable_delivery_snapshot = runtime_snapshot.get("durable_delivery", {})
    mode_punchup_snapshot = runtime_snapshot.get("mode_punchup", {})
    mode_punchup_stats = mode_punchup_snapshot.get("stats", {})
    contextual_snapshot = runtime_snapshot.get("contextual_replies", {})
    contextual_stats = contextual_snapshot.get("stats", {})
    reply_coverage = runtime_snapshot.get("reply_coverage", {})
    ram_queue_size = message_queues[board_id].qsize()
    top_queue = ", ".join(f"{b}:{n}" for b, n in queues.get("top", [])) or "empty"
    priority_by_board = delivery_priority.get("by_board", {})
    board_delivery = runtime_snapshot.get("delivery", {}).get(board_id, {})
    last_delivery = board_delivery.get("last") or {}
    live_queue_info = queues.get("age_by_board", {}).get(board_id, {})
    live_current = queues.get("in_flight", {}).get(board_id, {})
    live_queue_text = (
        f"oldest {live_queue_info.get('oldest_age_sec', 0)}s "
        f"avg {live_queue_info.get('avg_age_sec', 0)}s "
        f"post #{live_queue_info.get('oldest_post', '-')}"
    )
    live_current_text = (
        f"#{live_current.get('post_num')} {live_current.get('phase', 'full')} "
        f"run {live_current.get('run_sec')}s age {live_current.get('age_sec')}s "
        f"rec {live_current.get('recipients', '-')}/{live_current.get('original_recipients', '-')}"
        if live_current else "none"
    )
    board_reply_coverage = reply_coverage.get("by_board", {}).get(board_id, {})
    reply_coverage_text = (
        f"all {reply_coverage.get('copy_posts', 0)} posts/{reply_coverage.get('total_copies', 0)} copies "
        f"span {reply_coverage.get('min_post', '-')}-{reply_coverage.get('max_post', '-')} "
        f"gap {reply_coverage.get('gap_from_latest', '-')}; "
        f"{board_id} {board_reply_coverage.get('copy_posts', 0)} posts "
        f"{board_reply_coverage.get('min_post', '-')}-{board_reply_coverage.get('max_post', '-')}"
    )
    if last_delivery:
        last_age = last_delivery.get("post_age_sec")
        last_age_text = f" age {round(last_age, 1)}s" if last_age is not None else ""
        last_delivery_text = (
            f"#{last_delivery.get('post_num')} "
            f"{last_delivery.get('phase', 'full')} "
            f"{last_delivery.get('success')}/{last_delivery.get('phase_recipients', last_delivery.get('recipients'))}"
            f"/{last_delivery.get('original_recipients', last_delivery.get('recipients'))} "
            f"{last_delivery.get('seconds')}s "
            f"{last_age_text} "
            f"def {last_delivery.get('deferred_recipients', 0)} "
            f"prio {last_delivery.get('priority_recipients')} "
            f"retry {last_delivery.get('retries')}"
        )
    else:
        last_delivery_text = "none"
    memory = runtime_snapshot.get("memory", {})
    text = (
        f"📊 <b>Состояние очередей:</b>\n\n"
        f"🚀 <b>RAM (Рассылка):</b> {ram_queue_size}\n"
        f"🧵 <b>RAM total/top:</b> {queues.get('total', 0)} | <code>{escape_html(top_queue)}</code>\n"
        f"⏳ <b>Live age/current:</b> <code>{escape_html(live_queue_text)} | {escape_html(live_current_text)}</code>\n"
        f"👥 <b>Telegram recipients:</b> {recipients_snapshot.get('telegram_active_by_board', {}).get(board_id, '?')} on /{board_id}/; all {recipients_snapshot.get('telegram_active_total', '?')}\n"
        f"↩️ <b>Reply copies:</b> <code>{escape_html(reply_coverage_text)}</code>\n"
        f"⚡ <b>Priority active:</b> {priority_by_board.get(board_id, 0)} / {delivery_priority.get('total_weekly_active', 0)} за {delivery_priority.get('days', WEEKLY_ACTIVE_DAYS)}d split={delivery_priority.get('split_fanout')} slice={delivery_priority.get('passive_slice_size')}/{delivery_priority.get('passive_media_slice_size')} pressure>={delivery_priority.get('pressure_slice_age_sec')}s:{delivery_priority.get('pressure_passive_slice_size')}/{delivery_priority.get('pressure_passive_media_slice_size')} priority_budget={delivery_priority.get('priority_phase_budget_sec')}s passive_budget={delivery_priority.get('passive_phase_budget_sec')}s guard={delivery_priority.get('delivery_phase_guard_sec')}s preempt={delivery_priority.get('passive_max_preemptions')} chunk={delivery_priority.get('delivery_initial_chunk_size')}/{delivery_priority.get('delivery_min_chunk_size')} uid_timeout={delivery_priority.get('delivery_per_recipient_timeout_sec')}s uid_retries={delivery_priority.get('delivery_max_recipient_retries')}\n"
        f"🧷 <b>Durable delivery:</b> enabled={durable_delivery_snapshot.get('enabled')} DB pending={db_stats.get('delivery', 0)} saved={durable_delivery_snapshot.get('persisted', 0)} fail={durable_delivery_snapshot.get('persist_failed', 0)} restored={durable_delivery_snapshot.get('restored_items', 0)}/{durable_delivery_snapshot.get('restored_recipients', 0)} deleted={durable_delivery_snapshot.get('deleted', 0)}\n"
        f"🖼 <b>Anime media:</b> conc={anime_media_snapshot.get('concurrency')} b_max={anime_media_snapshot.get('b_max_stacked_images')} url={anime_media_snapshot.get('url_parallel')}x/{anime_media_snapshot.get('url_timeout_sec')}s total={anime_media_snapshot.get('url_total_sec')}s dl={anime_media_snapshot.get('download_parallel')}x/{anime_media_snapshot.get('download_timeout_sec')}s\n"
        f"🎭 <b>Mode punch-up:</b> runtime={mode_punchup_snapshot.get('runtime_enabled')} shed={mode_punchup_snapshot.get('queue_shed_sec')}s calls={mode_punchup_stats.get('calls', 0)} skip_load={mode_punchup_stats.get('skipped_load', 0)}\n"
        f"💬 <b>Context replies:</b> enabled={contextual_snapshot.get('enabled')} groups={contextual_snapshot.get('groups_ru')} tracked={contextual_snapshot.get('tracked_users')} sent={contextual_stats.get('sent', 0)} skip_cd/daily={contextual_stats.get('skipped_cooldown', 0)}/{contextual_stats.get('skipped_daily_limit', 0)} cd={contextual_snapshot.get('cooldown_sec')}s limit={contextual_snapshot.get('daily_limit')}\n"
        f"📨 <b>Last delivery:</b> <code>{escape_html(last_delivery_text)}</code> avg/max <code>{board_delivery.get('avg_sec', 0)} / {board_delivery.get('max_sec', 0)}s</code>\n"
        f"💾 <b>DB (Broadcast):</b> {db_stats.get('broadcast', 0)}\n"
        f"🔔 <b>DB (Уведомления):</b> {db_stats.get('notif', 0)}\n"
        f"🪞 <b>DB (Зеркала файлов):</b> {db_stats.get('mirror', 0)}\n"
        f"👮 <b>DB (Модерация):</b> {db_stats.get('mod', 0)}\n"
        f"🧠 <b>RSS/private:</b> {memory.get('rss_mb', '?')} / {memory.get('private_mb', '?')} MB"
    )
    await message.answer(text, parse_mode="HTML")

@router.message(Command("whisper"))
async def cmd_whisper(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id: return
    try: await message.delete()
    except Exception as e: pass
    if not message.reply_to_message:
        await message.answer("❌ Используй /whisper в ответ на сообщение, автору которого хочешь прошептать.")
        return
    parts = (message.text or message.caption or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("❌ Использование: <code>/whisper &lt;текст&gt;</code>", parse_mode="HTML")
        return
    text = parts[1]
    
    target_id = await get_author_id_by_reply(message)
    if not target_id:
        await message.answer("❌ Не удалось найти автора оригинального сообщения.")
        return
        
    if target_id == message.from_user.id:
        await message.answer("❌ Зачем шептать самому себе?")
        return

    # Send to target
    delivered = False
    max_retries = 2
    for attempt in range(max_retries):
        try:
            await message.bot.send_message(
                target_id, 
                f"🤫 <b>Тебе анонимно шепчут в /{board_id}/:</b>\n<i>{escape_html(text)}</i>", 
                parse_mode="HTML"
            )
            delivered = True
            break
        except TelegramForbiddenError:
            runtime_logger.warning(f"Whisper send target {target_id} blocked bot on {board_id}")
            try:
                import __main__ as main
                if hasattr(main, 'purge_users_from_board_ram'):
                    await main.purge_users_from_board_ram(board_id, [target_id])
                if board_id in board_data and 'users' in board_data[board_id]:
                    board_data[board_id]['users']['active'].discard(target_id)
                await remove_user_from_board(target_id, board_id)
            except Exception as purge_err:
                runtime_logger.warning(f"Failed to purge blocked whisper user {target_id}: {purge_err}")
            break
        except TelegramRetryAfter as e:
            delay = float(getattr(e, "retry_after", 5) or 5) + 1.0
            runtime_logger.warning(f"Whisper TelegramRetryAfter {delay}s for target {target_id}")
            await asyncio.sleep(delay)
        except TelegramBadRequest as e:
            runtime_logger.warning(f"Whisper TelegramBadRequest for target {target_id}: {e}")
            break
        except Exception as e:
            runtime_logger.error(f"Whisper send failed: {e}", exc_info=True)
            break

    if not delivered:
        await message.answer("❌ Не удалось доставить шёпот (пользователь не запустил бота или заблокировал его).")
        
    if delivered:
        # Send to admin
        admins = BOARD_CONFIG.get(board_id, {}).get('admins', set())
        sender_nick = generate_anon_name(message.from_user.id)
        target_nick = generate_anon_name(target_id)
        for admin_id in admins:
            try:
                await message.bot.send_message(
                    admin_id,
                    f"🕵️‍♂️ <b>(ЭТО СЕКРЕТ) Шёпот в /{board_id}/:</b>\nОт: <code>{sender_nick}</code>\nКому: <code>{target_nick}</code>\nТекст: <i>{escape_html(text)}</i>",
                    parse_mode="HTML"
                )
            except TelegramForbiddenError:
                runtime_logger.warning(f"Admin {admin_id} blocked bot on {board_id} during whisper notify")
            except TelegramBadRequest as e:
                runtime_logger.warning(f"Admin whisper notify TelegramBadRequest for {admin_id}: {e}")
            except TelegramRetryAfter as e:
                await asyncio.sleep(float(getattr(e, "retry_after", 5) or 5))
            except Exception as e:
                runtime_logger.warning(f"Admin whisper notify failed for {admin_id}: {e}")

@router.message(Command("redact"))
async def cmd_redact(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id: return
    try: await message.delete()
    except TelegramBadRequest: pass
    except Exception as e: runtime_logger.warning(f"cmd_redact message.delete failed: {e}")
    if not message.reply_to_message:
        await message.answer("❌ Используй /redact в ответ на свое сообщение.")
        return

    key = (message.chat.id, message.reply_to_message.message_id)
    post_num = message_to_post.get(key)
    if not post_num:
        info = await get_post_info_by_copy(message.chat.id, message.reply_to_message.message_id)
        if info: post_num = info[0]
        
    if not post_num:
        await message.answer("❌ Не найдено в базе.")
        return
        
    target_id = await get_author_id_by_reply(message)
    if target_id != message.from_user.id:
        await message.answer("❌ Ты не можешь редактировать чужие сообщения!")
        return

    msg_status = await message.answer("⏳ Удаляем контент из всех копий...")
    
    # Get board_id of the post
    post_board = None
    if post_num in messages_storage:
        post_board = messages_storage[post_num].get('board_id')
    if not post_board:
        from common.db_pool import db_lock
        db = await get_pool()
        async with db_lock:
            async with db.execute("SELECT board_id FROM Posts WHERE post_num = ?", (post_num,)) as c:
                row = await c.fetchone()
                if row:
                    post_board = row[0]
    if not post_board:
        post_board = board_id

    # Get all user copies
    db_copies = await get_post_copies(post_num)
    success_count = 0
    for rec_id, msg_id in db_copies:
        try:
            # Используем правильного бота доски для ЛС
            target_bot = GLOBAL_BOTS.get(post_board) or message.bot
            try:
                await target_bot.edit_message_text(
                    chat_id=rec_id,
                    message_id=msg_id,
                    text="<b>[ДАННЫЕ УДАЛЕНЫ АВТОРОМ]</b>",
                    parse_mode="HTML"
                )
            except TelegramBadRequest as e:
                err_str = str(e).lower()
                if "message is not modified" in err_str:
                    pass
                elif "there is no text in the message" in err_str or "message to edit not found" not in err_str:
                    try:
                        await target_bot.edit_message_caption(
                            chat_id=rec_id,
                            message_id=msg_id,
                            caption="<b>[ДАННЫЕ УДАЛЕНЫ АВТОРОМ]</b>",
                            parse_mode="HTML"
                        )
                    except Exception as e:
                        runtime_logger.warning(f"Caption edit error: {e}")
            success_count += 1
            await asyncio.sleep(0.04)
        except Exception as e:
            runtime_logger.warning(f"Message edit error: {e}")

    # Get and update all channel copies (mirrors)
    from common.database import get_all_channel_copies
    channel_copies = await get_all_channel_copies(post_num)
    if channel_copies:
        target_bot = GLOBAL_BOTS.get(post_board) or message.bot
        for chan_id, msg_id in channel_copies:
            try:
                try:
                    await target_bot.edit_message_text(
                        chat_id=chan_id,
                        message_id=msg_id,
                        text="<b>[ДАННЫЕ УДАЛЕНЫ АВТОРОМ]</b>",
                        parse_mode="HTML"
                    )
                except TelegramBadRequest as e:
                    err_str = str(e).lower()
                    if "message is not modified" in err_str:
                        pass
                    elif "there is no text in the message" in err_str or "message to edit not found" not in err_str:
                        try:
                            await target_bot.edit_message_caption(
                                chat_id=chan_id,
                                message_id=msg_id,
                                caption="<b>[ДАННЫЕ УДАЛЕНЫ АВТОРОМ]</b>",
                                parse_mode="HTML"
                            )
                        except Exception as e:
                            runtime_logger.warning(f"Caption edit error in channel copy: {e}")
                success_count += 1
                await asyncio.sleep(0.04)
            except Exception as e:
                runtime_logger.warning(f"Message edit error in channel copy: {e}")

    async with storage_lock:
        if post_num in messages_storage:
            content_dict = messages_storage[post_num].get('content', {})
            if 'text' in content_dict:
                content_dict['text'] = "[ДАННЫЕ УДАЛЕНЫ АВТОРОМ]"
            if 'caption' in content_dict:
                content_dict['caption'] = "[ДАННЫЕ УДАЛЕНЫ АВТОРОМ]"
                
    # Update SQLite explicitly using the database connection
    try:
        from common.database import update_post_content
        content_dict = {}
        if post_num in messages_storage:
            content_dict = messages_storage[post_num].get('content', {})
        else:
            content_dict = {"type": "text", "text": "[ДАННЫЕ УДАЛЕНЫ АВТОРОМ]"}
        await update_post_content(post_num, content_dict)
    except Exception as e:
        runtime_logger.warning(f"Could not update db text for redact: {e}")
    
    try: await msg_status.delete()
    except Exception as e: pass
    
    st_msg = await message.answer(f"✅ Успешно удалено у {success_count} пользователей/зеркал.")
    await asyncio.sleep(4)
    try: await st_msg.delete()
    except Exception as e: pass

@router.message(Command("board_stats", "board_info", "bstats"))
async def cmd_board_stats(message: types.Message, board_id: str | None, stream: str = 'ru'):

    try: spawn_task(delete_message_after_delay(message, 5))
    except Exception as e: runtime_logger.warning(f"Failed to spawn delete_message task: {e}")

    if not board_id: return
    user_id = message.from_user.id
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    INFO_CMD_COOLDOWN = 30
    # storage_lock убран: кулдаун в board_data, исключение даёт info_cmd_lock.
    async with info_cmd_lock:
        b_data = board_data[board_id]
        current_time = time.time()
        last_usage = b_data.get('last_info_command_time', {}).get(user_id, 0)
        on_cooldown = current_time - last_usage < INFO_CMD_COOLDOWN
        if not on_cooldown:
            b_data.setdefault('last_info_command_time', {})[user_id] = current_time
    if on_cooldown:
        try: await message.delete()
        except Exception as e: pass
        return
    b_data = board_data[board_id]
    
    wait_txt = "📊 Собираю статистику, вычисляю активность..." if lang != 'en' else "📊 Gathering statistics..."
    wait_msg = await message.answer(wait_txt)
    real_users_active = [uid for uid in b_data['users']['active'] if uid > 0]
    total_users_on_board = len(real_users_active)
    total_posts_on_board = b_data.get('board_post_count', 0)
    total_users_global = 0
    seen_users = set()
    for bid in BOARDS:
        for uid in board_data[bid]['users']['active']:
            if uid > 0: seen_users.add(uid)
    total_users_global = len(seen_users)
    board_name = BOARD_CONFIG[board_id]['name']
    if lang == 'en':
        stats_text = (f"📊 Board Statistics {board_name}:\n\n"
                      f"👥 Anons on this board: {total_users_on_board}\n"
                      f"👥 Total anons in TGACH: {total_users_global}\n"
                      f"📨 Posts on this board: {total_posts_on_board}\n"
                      f"📈 Total posts in TGACH: {state['post_counter']}")
    elif lang == 'jp':
        stats_text = (f"📊 {board_name} の統計:\n\n"
                      f"👥 この板のアノン: {total_users_on_board}\n"
                      f"👥 全アノン数: {total_users_global}\n"
                      f"📨 この板のレス数: {total_posts_on_board}\n"
                      f"📈 総レス数: {state['post_counter']}")
    else:
        stats_text = (f"📊 Статистика доски {board_name}:\n\n"
                      f"👥 Анонимов на доске: {total_users_on_board}\n"
                      f"👥 Всего анонов в Тгаче: {total_users_global}\n"
                      f"📨 Постов на доске: {total_posts_on_board}\n"
                      f"📈 Всего постов в тгаче: {state['post_counter']}")
    try:
        await message.answer(stats_text, parse_mode="HTML")
    except Exception as e: pass
    try: await wait_msg.delete()
    except Exception as e: pass

@router.message(Command("global_top", "gtop"))
async def cmd_global_top(message: types.Message, board_id: str | None, stream: str = 'ru'):
    try: spawn_task(delete_message_after_delay(message, 5))
    except Exception as e: runtime_logger.warning(f"Failed to spawn delete_message task: {e}")

    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    
    wait_txt = "🏆 Анализирую базу данных для построения топов..." if lang != 'en' else "🏆 Computing leaderboards..."
    wait_msg = await message.answer(wait_txt)
    
    top_posters = []
    top_rich = []
    
    try:
        async with db_lock:
            db = await get_pool()
            # Top 10 by posts
            q_posts = "SELECT author_id, COUNT(*) as cnt FROM Posts GROUP BY author_id ORDER BY cnt DESC LIMIT 10"
            async with db.execute(q_posts) as cursor:
                rows = await cursor.fetchall()
                for r in rows:
                    if r[0]: top_posters.append((r[0], r[1]))
            
            # Top 10 by balance
            q_rich = "SELECT user_id, SUM(balance) as bal FROM Users GROUP BY user_id ORDER BY bal DESC LIMIT 10"
            async with db.execute(q_rich) as cursor:
                rows = await cursor.fetchall()
                for r in rows:
                    if r[0]: top_rich.append((r[0], r[1]))
    except Exception as e:
        print(f"Error fetching top: {e}")
        return

    def format_table(data_list, value_suffix=""):
        lines = []
        for i, (uid, val) in enumerate(data_list, 1):
            name = generate_anon_name(uid)
            val_str = f"{int(val)}{value_suffix}"
            lines.append(f"{i:2}. {name:<25} | {val_str:>8}")
        return "\n".join(lines) if lines else "Empty"

    if lang == 'en':
        header = "🏆 <b>TGACH LEADERBOARD</b> 🏆"
        cat1 = "📝 <b>Top 10 Shitposters</b>"
        cat2 = "💰 <b>Top 10 Richest</b>"
    elif lang == 'jp':
        header = "🏆 <b>TGちゃん ランキング</b> 🏆"
        cat1 = "📝 <b>トップ10 レス数</b>"
        cat2 = "💰 <b>トップ10 富豪</b>"
    else:
        header = "🏆 <b>ДОСКА ПОЧЕТА ТГАЧА</b> 🏆"
        cat1 = "📝 <b>Топ-10 Щитпостеров (посты)</b>"
        cat2 = "💰 <b>Топ-10 Богачей (баланс)</b>"

    text = f"{header}\n\n"
    text += f"{cat1}\n<pre>{format_table(top_posters)}</pre>\n\n"
    text += f"{cat2}\n<pre>{format_table(top_rich, ' ₽')}</pre>"
    
    try:
        await wait_msg.delete()
        await message.answer(text, parse_mode="HTML")
    except Exception as e: pass

@router.message(Command("anime", "nya", "kawai", "kawaii"))
async def cmd_anime(message: types.Message, board_id: str | None, stream: str = 'ru'):

    try: spawn_task(delete_message_after_delay(message, 5))
    except Exception as e: runtime_logger.warning(f"Failed to spawn delete_message task: {e}")

    if not board_id: return
    b_data = board_data[board_id]
    if not await check_cooldown(message, board_id):
        return
    activation_phrases = [
        "にゃあ～！アニメモードがアクティベートされました！\n\n^_^",
        "お兄ちゃん、大変！アニメモードの時間だよ！ UWU",
        "アニメの力がこのチャットに満ちています！(ﾉ´ヮ´)ﾉ*:･ﾟ✧",
        "『プロジェクトA』発動！これよりチャットはアキハバラ自治区となる！",
        "このチャットは「人間」をやめるぞ！ジョジョーーッ！\n\nア ニ メ モ ー ド だ！",
        "君も... 見えるのか？『チャットのスタンド』が...！アニメモード発動！",
        "チャットの皆さん、聞いてください！私、魔法少女になっちゃった！\n\nアニメモード、オン！",
        "三百年の孤独に、光が射した… アニメモードの時間だ。",
        "異世界転生したらチャットが全部日本語になっていた件。\n\nアニメモード、スタート！",
        "🌸 お前はもう死んでいる... АНИМЕ РЕЖИМ: OMAE WA MOU SHINDEIRU!",
        "✧･ﾟ: *✧･ﾟ♡ ВКЛЮЧАЕМ КАВАЙНЫЙ АД! ♡･ﾟ✧*:･ﾟ✧",
        "⚡ 千 本 桜 ⚡ НЯ!",
        "ばか！へんたい！すけべ！アニメモードの時間なんだからね！",
        "アニメモード、発動！みんなで一緒にカワイイを叫ぼう！",
        "アニメモードが始まったよ！みんな、準備はいい？",
        "アニメモード、オン！さあ、みんなで楽しい時間を過ごそう！",
        "アニメモード、発動！みんなで一緒にカワイイを叫ぼう！"
    ]
    activation_text = random.choice(activation_phrases)
    now_dt = datetime.now(UTC)
    content = {
        "type": "text",
        "text": activation_text,
        "is_system_message": True,
        "archive_allowed": True
    }
    pnum = await create_post(
        board_id=board_id,
        author_id=0,
        content=content,
        timestamp=now_dt.timestamp(),
        is_from_site=False, stream=stream
    )
    if not pnum:
        print(f"⛔ [{board_id}] КРИТИЧЕСКАЯ ОШИБКА: не удалось создать пост в БД для активации режима anime.")
        try:
            await message.delete()
        except TelegramBadRequest: pass
        return
    header = await format_header(board_id, pnum)
    header = f"### 管理者 ###\n{header}"
    content['header'] = header
    await update_post_content(pnum, content)
    async with storage_lock:
        messages_storage[pnum] = {
            'author_id': 0,
            'timestamp': now_dt,
            'content': content,
            'board_id': board_id
        }
    await enqueue_board_message(board_id, {
        "recipients": b_data['users']['active'],
        "content": content,
        "post_num": pnum,
    })
    await _activate_mode(board_id, 'anime_mode')
    disable_task = spawn_task(disable_mode_after_delay(330, board_id, 'anime_mode'))
    b_data['active_mode_task'] = disable_task
    try:
        await message.delete()
    except TelegramBadRequest:
        pass
    except Exception as e:
        runtime_logger.warning(f"Failed to delete message in cmd_anime: {e}")

async def check_anime_cmd_cooldown(message: types.Message, board_id: str) -> bool:
    current_time = time.time()
    async with anime_cmd_lock:
        cooldown_is_active = False
        async with storage_lock:
            b_data = board_data[board_id]
            last_usage = b_data.get('last_anime_cmd_time', 0)
            if current_time - last_usage < ANIME_CMD_COOLDOWN:
                cooldown_is_active = True
            else:
                b_data['last_anime_cmd_time'] = current_time
        if cooldown_is_active:
            cooldown_msg = random.choice(ANIME_CMD_COOLDOWN_PHRASES)
            try:
                sent_msg = await message.answer(cooldown_msg)
                spawn_task(delete_message_after_delay(sent_msg, 15))
            except Exception as e:
                runtime_logger.warning(f"Failed to send anime cooldown message: {e}")
            try:
                await message.delete()
            except TelegramBadRequest:
                pass
            except Exception as e:
                runtime_logger.warning(f"Failed to delete message during anime cooldown: {e}")
            return False
        return True

async def _run_bounded_anime_url_fetches(
    fetcher_tasks: list[Callable[[], Awaitable[Optional[str]]]],
    board_id: str,
    user_id: int,
    source: str,
) -> list[tuple[int, Optional[str] | BaseException]]:
    sem = asyncio.Semaphore(ANIME_URL_FETCH_PARALLEL)

    async def run_one(index: int, fetcher: Callable[[], Awaitable[Optional[str]]]):
        async with sem:
            started = time.time()
            try:
                return index, await asyncio.wait_for(fetcher(), timeout=ANIME_URL_FETCH_TIMEOUT_SEC)
            except asyncio.TimeoutError:
                runtime_logger.warning(
                    "anime_url_fetch_timeout %s",
                    json.dumps(
                        {
                            "ts": round(time.time(), 3),
                            "board_id": board_id,
                            "user_id": user_id,
                            "source": source,
                            "index": index,
                            "timeout_sec": ANIME_URL_FETCH_TIMEOUT_SEC,
                            "elapsed_sec": round(time.time() - started, 3),
                        },
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                )
                return index, None
            except Exception as exc:
                return index, exc

    tasks = [spawn_task(run_one(i, fetcher)) for i, fetcher in enumerate(fetcher_tasks)]
    done, pending = await asyncio.wait(tasks, timeout=ANIME_URL_FETCH_TOTAL_SEC)
    if pending:
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        runtime_logger.warning(
            "anime_url_fetch_total_timeout %s",
            json.dumps(
                {
                    "ts": round(time.time(), 3),
                    "board_id": board_id,
                    "user_id": user_id,
                    "source": source,
                    "pending": len(pending),
                    "total": len(tasks),
                    "timeout_sec": ANIME_URL_FETCH_TOTAL_SEC,
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        )
    results: list[tuple[int, Optional[str] | BaseException]] = [
        (i, None) for i in range(len(fetcher_tasks))
    ]
    for task in done:
        try:
            index, result = task.result()
            if 0 <= index < len(results):
                results[index] = (index, result)
        except BaseException as exc:
            if not isinstance(exc, asyncio.CancelledError):
                runtime_logger.warning(
                    "anime_url_fetch_task_error %s",
                    json.dumps(
                        {
                            "ts": round(time.time(), 3),
                            "board_id": board_id,
                            "user_id": user_id,
                            "source": source,
                            "error": type(exc).__name__,
                        },
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                )
    return results

async def _run_bounded_anime_downloads(
    urls: list[str],
    board_id: str,
    user_id: int,
    source: str,
) -> list[tuple[int, str, tuple[bytes, int] | BaseException | None]]:
    sem = asyncio.Semaphore(ANIME_DOWNLOAD_PARALLEL)

    async def run_one(index: int, url: str):
        async with sem:
            started = time.time()
            try:
                result = await asyncio.wait_for(
                    _download_image_with_proxy(url, timeout=int(ANIME_DOWNLOAD_TIMEOUT_SEC)),
                    timeout=ANIME_DOWNLOAD_TIMEOUT_SEC + 5,
                )
                return index, url, result
            except asyncio.TimeoutError:
                runtime_logger.warning(
                    "anime_download_timeout %s",
                    json.dumps(
                        {
                            "ts": round(time.time(), 3),
                            "board_id": board_id,
                            "user_id": user_id,
                            "source": source,
                            "index": index,
                            "timeout_sec": ANIME_DOWNLOAD_TIMEOUT_SEC,
                            "elapsed_sec": round(time.time() - started, 3),
                        },
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                )
                return index, url, None
            except Exception as exc:
                return index, url, exc

    tasks = [spawn_task(run_one(i, url)) for i, url in enumerate(urls)]
    done, pending = await asyncio.wait(tasks, timeout=ANIME_DOWNLOAD_TOTAL_SEC)
    if pending:
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        runtime_logger.warning(
            "anime_download_total_timeout %s",
            json.dumps(
                {
                    "ts": round(time.time(), 3),
                    "board_id": board_id,
                    "user_id": user_id,
                    "source": source,
                    "pending": len(pending),
                    "total": len(tasks),
                    "timeout_sec": ANIME_DOWNLOAD_TOTAL_SEC,
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        )
    results: list[tuple[int, str, tuple[bytes, int] | BaseException | None]] = [
        (i, url, None) for i, url in enumerate(urls)
    ]
    for task in done:
        try:
            _index, url, result = task.result()
            if 0 <= _index < len(results):
                results[_index] = (_index, url, result)
        except BaseException as exc:
            if not isinstance(exc, asyncio.CancelledError):
                runtime_logger.warning(
                    "anime_download_task_error %s",
                    json.dumps(
                        {
                            "ts": round(time.time(), 3),
                            "board_id": board_id,
                            "user_id": user_id,
                            "source": source,
                            "error": type(exc).__name__,
                        },
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                )
    return results

async def _collect_stacked_anime_downloads(
    fetcher_tasks: list[Callable[[], Awaitable[Optional[str]]]],
    board_id: str,
    user_id: int,
    source: str,
) -> list[tuple[bytes, str, str]]:
    successful_by_slot: dict[int, tuple[bytes, str, str]] = {}
    retry_slots = list(range(len(fetcher_tasks)))
    loop = asyncio.get_running_loop()

    for round_index in range(ANIME_REFILL_ROUNDS + 1):
        if not retry_slots:
            break
        round_source = source if round_index == 0 else f"{source}:refill{round_index}"
        round_fetchers = [fetcher_tasks[slot] for slot in retry_slots]
        url_results = await _run_bounded_anime_url_fetches(round_fetchers, board_id, user_id, round_source)

        urls: list[str] = []
        url_slots: list[int] = []
        next_slots: list[int] = []
        for local_index, result in url_results:
            if local_index >= len(retry_slots):
                continue
            slot = retry_slots[local_index]
            if isinstance(result, str) and result.startswith("http"):
                urls.append(result)
                url_slots.append(slot)
            else:
                next_slots.append(slot)

        if urls:
            download_results = await _run_bounded_anime_downloads(urls, board_id, user_id, round_source)
            for local_index, orig_url, res in download_results:
                if local_index >= len(url_slots):
                    continue
                slot = url_slots[local_index]
                if isinstance(res, tuple) and res[0]:
                    image_bytes = res[0]
                    try:
                        ext = orig_url.split('.')[-1].split('?')[0].lower()
                        if len(ext) > 4:
                            ext = 'jpg'
                    except Exception as e:
                        ext = 'jpg'
                    processed_bytes = await loop.run_in_executor(None, _resize_image_if_needed, image_bytes)
                    real_type = detect_media_type(processed_bytes, orig_url)
                    successful_by_slot[slot] = (processed_bytes, real_type, ext)
                else:
                    if isinstance(res, Exception):
                        print(f"⚠️ Ошибка при скачивании изображения: {res}")
                    next_slots.append(slot)

        retry_slots = [slot for slot in dict.fromkeys(next_slots) if slot not in successful_by_slot]
        if retry_slots and round_index < ANIME_REFILL_ROUNDS:
            runtime_logger.warning(
                "anime_media_refill %s",
                json.dumps(
                    {
                        "ts": round(time.time(), 3),
                        "board_id": board_id,
                        "user_id": user_id,
                        "source": source,
                        "round": round_index + 1,
                        "missing": len(retry_slots),
                        "target": len(fetcher_tasks),
                        "ready": len(successful_by_slot),
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            )
            print(f"[{board_id}] Добираю картинки: готово {len(successful_by_slot)}/{len(fetcher_tasks)}, осталось {len(retry_slots)}.")

    return [successful_by_slot[slot] for slot in sorted(successful_by_slot)]

async def _publish_anime_post(message: types.Message, board_id: str, user_id: int, content: dict, stream: str, num_downloads: int):
    b_data = board_data[board_id]
    is_shadow_muted = (user_id in b_data['shadow_mutes'] and
                       b_data['shadow_mutes'][user_id] > datetime.now(UTC))

    if is_shadow_muted:
        await process_shadow_reject(ShadowRejectContext(
            bot=message.bot,
            board_id=board_id,
            user_id=user_id,
            content=content,
            reply_to_post=None,
            stream=stream
        ))
        post_num = 0
    else:
        post_num = await process_new_post(NewPostParams(
            bot_instance=message.bot,
            board_id=board_id,
            user_id=user_id,
            content=content,
            reply_to_post=None,
            is_shadow_muted=False,
            stream=stream
        ))

    if post_num is not None:
        success_phrase = random.choice(ANIME_CMD_SUCCESS_PHRASES)
        sent_notification = await message.bot.send_message(
            chat_id=message.chat.id,
            text=f"{success_phrase} (+{num_downloads})"
        )
        spawn_task(delete_message_after_delay(sent_notification, 15))

async def _process_stacked_anime_command(
    message: types.Message,
    board_id: str,
    fetcher_tasks: list[Callable[[], Awaitable[Optional[str]]]],
    caption: str,
    stream: str = 'ru'
):
    """
    Универсальный обработчик для "стакающихся" аниме-команд.
    """
    working_msg = None
    gate_acquired = False
    try:
        if not await check_anime_cmd_cooldown(message, board_id):
            return
        user_id = message.from_user.id
        b_data = board_data[board_id]
        if user_id in b_data['users']['banned'] or \
           (b_data['mutes'].get(user_id) and b_data['mutes'][user_id] > datetime.now(UTC)):
            try: await message.delete()
            except TelegramBadRequest: pass
            return
        try: await message.delete()
        except TelegramBadRequest: pass
        searching_phrase = random.choice(ANIME_CMD_SEARCHING_PHRASES)
        working_msg = await message.bot.send_message(message.chat.id, searching_phrase)
        gate_wait_started = time.time()
        await anime_media_gate.acquire()
        gate_acquired = True
        gate_wait_sec = time.time() - gate_wait_started
        if gate_wait_sec > 0.05:
            runtime_logger.warning(
                "anime_media_wait %s",
                json.dumps(
                    {
                        "ts": round(time.time(), 3),
                        "board_id": board_id,
                        "user_id": user_id,
                        "wait_sec": round(gate_wait_sec, 3),
                        "concurrency": ANIME_MEDIA_CONCURRENCY,
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            )
        print(f"[{board_id}] Шаг 1: Запускаю {len(fetcher_tasks)} задач на получение URL для user {user_id}...")
        successful_downloads = await _collect_stacked_anime_downloads(fetcher_tasks, board_id, user_id, "command")
        if not successful_downloads:
            raise ValueError("Не удалось скачать ни одного изображения.")
            
        content = _prepare_anime_content(successful_downloads, caption)

        await _publish_anime_post(message, board_id, user_id, content, stream, len(successful_downloads))
    except ValueError as e:
        print(f"[{board_id}] Не удалось обработать команду для user {user_id}: {e}")
        fail_text = "Не удалось получить контент. API недоступны или лимит исчерпан."
        error_msg = await message.bot.send_message(message.chat.id, fail_text)
        spawn_task(delete_message_after_delay(error_msg, 10))
    finally:
        if gate_acquired:
            anime_media_gate.release()
        if working_msg:
            try: await working_msg.delete()
            except TelegramBadRequest: pass

@router.message(Command("deanon"))
async def cmd_deanon(message: Message, board_id: str | None, stream: str = 'ru'):
    if not board_id: return
    current_time = time.time()
    # storage_lock убран: кулдаун в board_data, исключение даёт deanon_lock.
    async with deanon_lock:
        b_data = board_data[board_id]
        on_cooldown = current_time - b_data.get('last_deanon_time', 0) < DEANON_COOLDOWN
        if not on_cooldown:
            b_data['last_deanon_time'] = current_time
    if on_cooldown:
        cooldown_msg = random.choice(DEANON_COOLDOWN_PHRASES)
        try:
            sent_msg = await message.answer(cooldown_msg)
            spawn_task(delete_message_after_delay(sent_msg, 5))
        except Exception as e: pass
        await _safe_delete_user_message(message)
        return
    lang = 'en' if board_id == 'int' else 'ru'
    if not message.reply_to_message:
        reply_text = "👀 Reply to a message to de-anonymize!" if lang == 'en' else "⚠️ Ответьте на анонимное сообщение юзера, чтобы попытаться узнать автора: <code>/deanon</code>"
        await message.answer(reply_text, parse_mode="HTML")
        await _safe_delete_user_message(message)
        return
    user_id = message.from_user.id
    b_data = board_data[board_id] # Переопределение b_data для ясности
    user_location = 'main'
    if board_id in THREAD_BOARDS:
        user_location = b_data.get('user_state', {}).get(user_id, {}).get('location', 'main')
    original_author_id = None
    target_post = None
    original_author_id = await get_author_id_by_reply(message)
    async with storage_lock:
        target_chat_id = message.reply_to_message.chat.id
        target_mid = message.reply_to_message.message_id
        target_post = message_to_post.get((target_chat_id, target_mid))
    if not original_author_id:
        reply_text = "🚫 Could not find the post to de-anonymize..." if lang == 'en' else "🚫 Не удалось найти пост для деанона..."
        await message.answer(reply_text)
        await _safe_delete_user_message(message)
        return
    if original_author_id == 0:
        reply_text = "⚠️ System messages cannot be de-anonymized." if lang == 'en' else "⚠️ Системные сообщения нельзя деанонить."
        await message.answer(reply_text)
        await _safe_delete_user_message(message)
        return
    deanon_text = generate_deanon_info(lang=lang)
    header_text_prefix = "### DEANON ###" if lang == 'en' else "### ДЕАНОН ###"
    now_dt = datetime.now(UTC)
    async def create_and_send_deanon_post(thread_id_override=None):
        content = {"type": "text", "text": deanon_text, "reply_to_post": target_post, "is_system_message": True}
        pnum = await create_post(
            board_id=board_id,
            author_id=0,
            content=content,
            timestamp=now_dt.timestamp(),
            is_from_site=False, stream=stream,
            thread_id_from_bot=thread_id_override
        )
        if not pnum:
            print(f"⛔ [{board_id}] КРИТИЧЕСКАЯ ОШИБКА: не удалось создать пост в БД для /deanon.")
            return
        header_text = await format_header(board_id, pnum)
        content['header'] = f"{header_text_prefix}\n{header_text}"
        content['post_num'] = pnum
        await update_post_content(pnum, content)
        async with storage_lock:
            messages_storage[pnum] = {'author_id': 0, 'timestamp': now_dt, 'content': content, 'board_id': board_id, 'thread_id': thread_id_override}
            if thread_id_override:
                thread_info = b_data.get('threads_data', {}).get(thread_id_override)
                if thread_info:
                    thread_info['last_activity_at'] = time.time()
        recipients = None
        if thread_id_override:
            thread_info = b_data.get('threads_data', {}).get(thread_id_override)
            if thread_info:
                recipients = thread_info.get('subscribers', set())
        else:
            recipients = b_data.get('users', {}).get('active', set())
        if recipients:
            await enqueue_board_message(board_id, {
                "recipients": recipients, "content": content, "post_num": pnum,
                "board_id": board_id, "thread_id": thread_id_override
            })
    if board_id in THREAD_BOARDS and user_location != 'main':
        thread_id = user_location
        thread_info = b_data.get('threads_data', {}).get(thread_id)
        if thread_info and not thread_info.get('is_archived'):
            await create_and_send_deanon_post(thread_id_override=thread_id)
        else: # Если тред не найден, постим на главную
             await create_and_send_deanon_post()
    else:
        await create_and_send_deanon_post()
    await _safe_delete_user_message(message)

@router.message(Command("zaputin", "z", "zov", "putin"))
async def cmd_zaputin(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id: return
    if board_id == 'int':
        try:
            await message.delete()
        except Exception as e: pass
        return
    b_data = board_data[board_id]
    if not await check_cooldown(message, board_id):
        return
    activation_phrases = [
        "🇷🇺 СЛАВА РОССИИ! ПУТИН - НАШ ПРЕЗИДЕНТ! 🇷🇺\n\nАктивирован режим кремлеботов! Все несогласные будут приравнены к пидорасам и укронацистам!",
        "ВНИМАНИЕ! АКТИВИРОВАН ПРОТОКОЛ 'КРЕМЛЬ'! 🇷🇺 Работаем, братья! За нами Путин и Сталинград!",
        "ТРИКОЛОР ПОДНЯТ! 🇷🇺 В чате включен режим патриотизма. Кто не с нами - тот под нами! РОССИЯ!",
        "НАЧИНАЕМ СПЕЦОПЕРАЦИЮ! 🇷🇺 Цель: денацификация чата. Потерь нет! Слава России!",
        "🇷🇺 РЕЖИМ 'РУССКИЙ МИР' АКТИВИРОВАН! 🇷🇺 От Калининграда до Владивостока - мы великая страна! ZOV",
        "ЗА ВДВ! 🇷🇺 В чате высадился русский десант. НАТО сосать! С нами Бог!",
        "ПАТРИОТИЧЕСКИЙ РЕЖИМ ВКЛЮЧЕН! 🇷🇺 Можем повторить! На Берлин! Деды воевали!",
        "🇷🇺 АКТИВИРОВАН РЕЖИМ 'БЕЗГРАНИЧНАЯ ЛЮБОВЬ К РОДИНЕ'! 🇷🇺 Гордимся страной, верим в президента!",
        "ТОВАРИЩ ПОЛКОВНИК РАЗРЕШИЛ! 🇷🇺 Включаем режим '15 рублей'. Все на защиту Родины!",
        "🇷🇺 ЗА ПУТІНА! ЗА ДЕДОВ! РЕЖИМ 'БАЛТИЙСКИЙ ШТУРМ' АКТИВИРОВАН!",
        "🚨 ТРЕВОГА! В ЧАТЕ ЗАМЕЧЕНА ЛИБЕРДА! ВКЛЮЧАЕМ ПРОТОКОЛ 'ЧВК ВАГНЕР'",
        "🧨 ПОДРЫВНАЯ АКТИВНОСТЬ В ЧАТЕ! Включаем режим 'АРМАТА'. За Родину!",
        "🪆 МАТРЁШКА РАСКРЫЛАСЬ! Режим имперского величия активирован! ZА ПУТИНА!",
        "☢️ ЯДЕРНЫЙ ПРОТОКОЛ АКТИВИРОВАН! Готовим гиперзвуковые ракеты по целям!",
        "🦅 ОРЕШНИК ЗАПУЩЕН! Режим патриотизма включен. Крым наш!",
        "🐻 МЕДВЕДЬ ПРОСНУЛСЯ! Режим ядерного троллинга активирован! ZOV ZOV ZOV",
        "🇷🇺 РОССИЯ! СВЯЩЕННАЯ НАША ДЕРЖАВА! 🇷🇺 В чате включен патриотический режим. Хохлы, сосать!",
        "🇷🇺 В ЧАТЕ АКТИВИРОВАН РЕЖИМ 'ZА ПУТИНА'! 🇷🇺 Кто не скачет - тот москаль!",
        "🇷🇺 ВКЛЮЧАЕМ РЕЖИМ 'РОССИЯ ВПЕРЁД'! 🇷🇺 Слава великой стране! С нами Бог и Путин!",
        "ГОЙДА, БРАТЦЫ! 🇷🇺 Активирован режим державности! Либерахам приготовиться к анальным карам!",
        "🇷🇺 В ЧАТ ВРЫВАЕТСЯ РУССКИЙ МЕДВЕДЬ! 🐻 Всем сосать, мы здесь власть! Запад загнивает!",
        "АКТИВИРОВАН ПРОТОКОЛ 'СКРЕПЫ'! 🙏 Переходим на православный мат и традиционные ценности!",
        "ПО ЦЕНТРАМ ПРИНЯТИЯ РЕШЕНИЙ... ОГОНЬ! 🔥 Патриотический угар объявляется открытым!",
        "АХМАТ-СИЛА! 💪 В чат заходят дон. Несогласные - извиняются на камеру дон."
    ]
    activation_text = random.choice(activation_phrases)
    now_dt = datetime.now(UTC)
    content = {
        "type": "text",
        "text": activation_text,
        "is_system_message": True,
        "archive_allowed": True
    }
    pnum = await create_post(
        board_id=board_id,
        author_id=0,
        content=content,
        timestamp=now_dt.timestamp(),
        is_from_site=False, stream=stream
    )
    if not pnum:
        print(f"⛔ [{board_id}] КРИТИЧЕСКАЯ ОШИБКА: не удалось создать пост в БД для активации режима zaputin.")
        try:
            await message.delete()
        except TelegramBadRequest: pass
        return
    header = await format_header(board_id, pnum)
    header = f"### Админ ###\n{header}"
    content['header'] = header
    await update_post_content(pnum, content)
    async with storage_lock:
        messages_storage[pnum] = {
            'author_id': 0,
            'timestamp': now_dt,
            'content': content,
            'board_id': board_id
        }
    await enqueue_board_message(board_id, {
        "recipients": b_data['users']['active'],
        "content": content,
        "post_num": pnum,
    })
    await _activate_mode(board_id, 'zaputin_mode')
    disable_task = spawn_task(disable_mode_after_delay(309, board_id, 'zaputin_mode'))
    b_data['active_mode_task'] = disable_task
    try:
        await message.delete()
    except TelegramBadRequest:
        pass

@router.message(Command("app"))
async def cmd_app(message: types.Message, board_id: str | None, stream: str = 'ru'):
    """
    Отправляет кнопку для открытия веб-приложения (сайта).
    """
    if not board_id: return
    WEBAPP_URL = "https://tgach.top" 
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    if lang == 'en':
        text = "Click the button below to open the TGACH web interface:"
        btn_text = "Open Web App"
    elif lang == 'jp':
        text = "下のボタンをクリックしてTGちゃんのWebインターフェースを開きます:"
        btn_text = "Webアプリを開く"
    else:
        text = "Нажмите на кнопку ниже, чтобы открыть веб-интерфейс ТГАЧ:"
        btn_text = "Открыть веб-приложение"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=btn_text, web_app=WebAppInfo(url=WEBAPP_URL))]
    ])
    await message.answer(text, reply_markup=keyboard)

@router.message(Command("suka_blyat"))
async def cmd_suka_blyat(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id: return
    if board_id == 'int':
        try:
            await message.delete()
        except Exception as e: pass
        return
    b_data = board_data[board_id]
    user_id = message.from_user.id
    if (user_id in b_data['shadow_mutes'] and b_data['shadow_mutes'][user_id] > datetime.now(UTC)) or \
       (user_id in b_data['mutes'] and b_data['mutes'][user_id] > datetime.now(UTC)):
        try:
            await message.delete()
        except (TelegramBadRequest, TelegramForbiddenError):
            pass
        return
    if not await check_cooldown(message, board_id):
        return
    activation_phrases = [
        "💢💢💢 Активирован режим СУКА БЛЯТЬ! 💢💢💢\n\nВсех нахуй разъебало!",
        "БЛЯЯЯЯЯТЬ! 💥 РЕЖИМ АГРЕССИИ ВКЛЮЧЕН! ПИЗДА ВСЕМУ!",
        "ВЫ ЧЕ, ОХУЕЛИ?! 💢 Включаю режим 'сука блять', готовьтесь, пидорасы!",
        "ЗАЕБАЛО ВСЁ НАХУЙ! 💥 Переходим в режим тотальной ненависти. СУКА!",
        "💥 ТРЕЩИНА НАХУЙ! Режим 'ХУЙ ПОЛЕЗЕШЬ' активирован!",
        "🧨 ПИЗДЕЦ НАСТУПИЛ! ВКЛЮЧАЕМ РЕЖИМ ХУЕСОСАНИЯ! ААА БЛЯЯЯТЬ!",
        "🔞 ЁБАНЫЙ В РОТ! Режим агрессивного аутизма включен! СУКА!",
        "🤬 ПИЗДОС НА МАКАРОС! Режим 'БАТЯ В ЯРОСТИ'! ВСЕМ ПИЗДАНУТЬСЯ!",
        "А НУ БЛЯТЬ СУКИ СЮДА ПОДОШЛИ! 💢 Режим 'бати в ярости' активирован!",
        "СУКАААААА! 💥 Пиздец, как меня все бесит! Включаю протокол 'РАЗЪЕБАТЬ'.",
        "ЩА БУДЕТ МЯСО! 🔪🔪🔪 Режим 'сука блять' активирован. Нытикам здесь не место!",
        "ЕБАНЫЙ ТЫ НАХУЙ! 💢💢💢 С этого момента говорим только матом. Поняли, уебаны?",
        "ТАК, БЛЯТЬ! 💥 Слушать мою команду! Режим 'СУКА БЛЯТЬ' активен. Вольно, бляди!",
        "💢 ДА ТЫ ЁБНУТЫЙ? РЕЖИМ 'ХУЙ ПОЛЕЗЕШЬ' АКТИВИРОВАН!",
        "🐗 СВИНОПАС ВЫШЕЛ НА ТРОПУ ВОЙНЫ! ВКЛЮЧАЕМ РЕЖИМ ХУЕСОСАНИЯ!",
        "🔞 ПИЗДЕЦ НАСТУПИЛ! ВСЕМ ПИЗДАНУТЬСЯ В УГОЛ! АААА БЛЯЯЯТЬ!",
        "ПОШЛИ НАХУЙ! 💥 ВСЕ ПОШЛИ НАХУЙ! Режим ярости включен, суки!",
        "🤬 СУКА БЛЯТЬ! РЕЖИМ 'БАТЯ В ЯРОСТИ' АКТИВИРОВАН! ВСЕМ ПИЗДАНУТЬСЯ!",
        "ЩА БУДЕТ МЯСО! 🔪 Режим 'сука блять' активирован. Нытикам здесь не место!"
    ]
    activation_text = random.choice(activation_phrases)
    now_dt = datetime.now(UTC)
    content = {
        "type": "text",
        "text": activation_text,
        "is_system_message": True,
        "archive_allowed": True
    }
    pnum = await create_post(
        board_id=board_id,
        author_id=0,
        content=content,
        timestamp=now_dt.timestamp(),
        is_from_site=False, stream=stream
    )
    if not pnum:
        print(f"⛔ [{board_id}] КРИТИЧЕСКАЯ ОШИБКА: не удалось создать пост в БД для активации режима suka_blyat.")
        try:
            await message.delete()
        except TelegramBadRequest: pass
        return
    header = await format_header(board_id, pnum)
    header = f"### Админ ###\n{header}"
    content['header'] = header
    await update_post_content(pnum, content)
    async with storage_lock:
        messages_storage[pnum] = {
            'author_id': 0,
            'timestamp': now_dt,
            'content': content,
            'board_id': board_id
        }
    await enqueue_board_message(board_id, {
        "recipients": b_data['users']['active'],
        "content": content,
        "post_num": pnum,
    })
    await _activate_mode(board_id, 'suka_blyat_mode')
    disable_task = spawn_task(disable_mode_after_delay(303, board_id, 'suka_blyat_mode'))
    b_data['active_mode_task'] = disable_task
    try:
        await message.delete()
    except TelegramBadRequest:
        pass

@router.message(Command("roll", "roulette", "ruletka", "rulet", "fortune", "фортуна"))
async def cmd_roll(message: types.Message, board_id: str | None, stream: str = 'ru'):

    try: spawn_task(delete_message_after_delay(message, 5))
    except Exception as e: runtime_logger.warning(f"Failed to spawn delete_message task: {e}")

    if not board_id: 
        try: await message.delete()
        except TelegramBadRequest: pass
        return
    user_id = message.from_user.id
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    # storage_lock здесь был ложной зависимостью: он защищает messages_storage /
    # post_to_messages / message_to_post, а кулдаун лежит в board_data, к
    # которому 111 из 146 обращений в этом файле идут вообще без него.
    # Взаимное исключение уже даёт roulette_lock. Внутри лока нет ни одного
    # await, поэтому проверка и запись времени атомарны; ответ юзеру ушёл
    # наружу, чтобы flood-wait не держал лок рулетки.
    async with roulette_lock:
        b_data = board_data[board_id]
        current_time = time.time()
        last_usage = b_data.get('last_roll_time', {}).get(user_id, 0)
        on_cooldown = current_time - last_usage < 60
        if not on_cooldown:
            b_data.setdefault('last_roll_time', {})[user_id] = current_time
    if on_cooldown:
        if lang == 'en': cooldown_msg = "⏳ Roulette is on cooldown!"
        elif lang == 'jp': cooldown_msg = "⏳ ルーレットはクールダウン中です！"
        else: cooldown_msg = random.choice(ROULETTE_COOLDOWN_PHRASES)
        try:
            sent_msg = await message.answer(cooldown_msg)
            spawn_task(delete_message_after_delay(sent_msg, 5))
        except (TelegramBadRequest, TelegramForbiddenError): pass
        try: await message.delete()
        except TelegramBadRequest: pass
        return
    if not ROULETTE_EVENTS:
        if lang == 'en': error_text = "Roulette data is not loaded."
        elif lang == 'jp': error_text = "ルーレットデータが読み込まれていません。"
        else: error_text = "Данные рулетки не загружены."
        try: await message.answer(error_text)
        except (TelegramBadRequest, TelegramForbiddenError): pass
        return
    working_msg = None
    try:
        if lang == 'en': work_txt = "⏳ Spinning the wheel..."
        elif lang == 'jp': work_txt = "⏳ ルーレットを回しています..."
        else: work_txt = "⏳ Кручу барабан..."
        working_msg = await message.answer(work_txt)
        event = get_random_event(ROULETTE_EVENTS)
        if not event:
            raise ValueError("Failed to get random event.")
        event_id = event.get('id', '???')
        event_desc_plain = event.get('description', '...')
        text_for_image = f"[{event_id}]\n\n{event_desc_plain}"
        loop = asyncio.get_running_loop()
        image_bytes = await loop.run_in_executor(None, generate_wipe_image, text_for_image)
        if image_bytes:
            photo = types.BufferedInputFile(image_bytes, filename="roll_result.png")
            caption_header = random.choice(ROULETTE_RESULT_PHRASES) # Пока оставим общие
            await message.answer_photo(photo, caption=caption_header)
        else:
            print(f"⚠️ [cmd_roll] Image generation failed. Sending text.")
            result_header = random.choice(ROULETTE_RESULT_PHRASES)
            event_desc_html = escape_html(event_desc_plain)
            result_text = f"{result_header}\n\n<b>[{event_id}]</b> {event_desc_html}"
            await message.answer(result_text, parse_mode="HTML")
    except Exception as e:
        print(f"⛔ Ошибка в cmd_roll: {e}")
        if lang == 'en': err = "Error during roulette spin."
        elif lang == 'jp': err = "ルーレット中にエラーが発生しました。"
        else: err = "Произошла ошибка при выполнении ролла."
        try: await message.answer(err)
        except (TelegramBadRequest, TelegramForbiddenError): pass
    finally:
        if working_msg:
            try: await working_msg.delete()
            except TelegramBadRequest: pass
        try: await message.delete()
        except TelegramBadRequest: pass

@router.message(Command("report", "mods", "admin", "moderator"))
async def cmd_report(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id: return
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    
    try: spawn_task(delete_message_after_delay(message, 5))
    except Exception as e: runtime_logger.warning(f"Failed to spawn delete_message task: {e}")

    if not message.reply_to_message:
        msg = "⚠️ Ответьте на подозрительное сообщение командой <code>/report</code>, чтобы позвать модераторов."
        if lang == 'en': msg = "⚠️ Reply to a suspicious message with <code>/report</code> to alert moderators."
        elif lang == 'jp': msg = "⚠️ 違反報告するメッセージに返信して <code>/report</code> を送信してください。"
        await message.answer(msg, parse_mode="HTML")
        return

    reported_msg = message.reply_to_message
    
    # Send confirmation to user
    confirm_msg = "✅ Репорт отправлен модераторам. Спасибо!"
    if lang == 'en': confirm_msg = "✅ Report sent to moderators. Thank you!"
    elif lang == 'jp': confirm_msg = "✅ モデレーターに報告しました。ありがとうございます！"
    
    sent_confirm = await message.answer(confirm_msg)
    try: spawn_task(delete_message_after_delay(sent_confirm, 10))
    except Exception as e: runtime_logger.warning(f"Failed to spawn delete_message task: {e}")

    # Get author id of reported message
    author_id = None
    author_id = await get_author_id_by_reply(message)
    if not author_id:
        author_id = "0"
    
    chat_id = message.chat.id
    msg_id = reported_msg.message_id
    
    # Build inline keyboard for admins
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.button(text="Удалить пост", callback_data=f"rep:del:{author_id}:{chat_id}:{msg_id}")
    builder.button(text="Бан 1ч", callback_data=f"rep:ban1:{author_id}:{chat_id}:{msg_id}")
    builder.button(text="Бан 24ч", callback_data=f"rep:ban24:{author_id}:{chat_id}:{msg_id}")
    builder.button(text="Игнор", callback_data=f"rep:ign:{author_id}:{chat_id}:{msg_id}")
    builder.adjust(1, 2, 1)

    admins = BOARD_CONFIG.get(board_id, {}).get('admins', set())
    report_text = f"🚨 <b>Новый РЕПОРТ в /{board_id}/</b>\n"
    report_text += f"От кого: <code>{message.from_user.id}</code>\n"
    report_text += f"На кого: <code>{author_id}</code>\n"
    report_text += f"Текст: <i>{escape_html(reported_msg.text or reported_msg.caption or '<медиа>')}</i>"
    
    for admin_id in admins:
        try:
            await message.bot.send_message(
                admin_id,
                report_text,
                reply_markup=builder.as_markup(),
                parse_mode="HTML"
            )
        except Exception as e:
            import traceback; traceback.print_exc()

@router.callback_query(F.data.startswith("rep:"))
async def process_report_action(callback: types.CallbackQuery, board_id: str | None):
    if not board_id or not is_admin(callback.from_user.id, board_id):
        await callback.answer("У вас нет прав.", show_alert=True)
        return
        
    parts = callback.data.split(":")
    action = parts[1]
    author_id = parts[2]
    chat_id = parts[3]
    msg_id = parts[4]
    
    admin_id = callback.from_user.id
    
    if action == "ign":
        await callback.message.edit_text(callback.message.html_text + "\n\n<i>❌ Проигнорировано модератором.</i>", parse_mode="HTML")
        await callback.answer("Жалоба отклонена")
        return
        
    if action == "del":
        try:
            await callback.bot.delete_message(chat_id=int(chat_id), message_id=int(msg_id))
        except Exception as e:
            import traceback; traceback.print_exc()
        await callback.message.edit_text(callback.message.html_text + "\n\n<i>🗑 Пост удален модератором.</i>", parse_mode="HTML")
        await callback.answer("Пост удален")
        return
        
    if action.startswith("ban"):
        if author_id == "0":
            await callback.answer("ID автора неизвестен, невозможно забанить.", show_alert=True)
            return
            
        target_id = int(author_id)
        duration_hours = 1 if action == "ban1" else 24
        
        async with storage_lock:
            b_data = board_data[board_id]
            b_data.setdefault('bans', {})[target_id] = time.time() + (duration_hours * 3600)
            
        deleted_posts = await delete_user_posts(callback.bot, target_id, 10, board_id)
        await log_global_event('bot', f"🚨 BAN: Мод {admin_id} забанил по репорту {target_id} на {duration_hours}ч в /{board_id}/ (удалено {deleted_posts} копий)")
        
        # Also try to delete the specific reported message just in case
        try:
            await callback.bot.delete_message(chat_id=int(chat_id), message_id=int(msg_id))
        except Exception as e:
            import traceback; traceback.print_exc()
            
        await callback.message.edit_text(callback.message.html_text + f"\n\n<i>🔨 Автор забанен на {duration_hours}ч модератором.</i>", parse_mode="HTML")
        await callback.answer(f"Пользователь забанен на {duration_hours}ч")

@router.callback_query(F.data.startswith("help:"))
async def process_help_menu(callback: types.CallbackQuery, board_id: str | None, stream: str = 'ru'):
    if not board_id: return
    cat = callback.data.split(":")[1]
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    b_data = board_data[board_id]
    
    if cat == "main":
        text_map = b_data.get('start_message_map', {})
        text = text_map.get(lang, b_data.get('start_message_text', "Help info missing."))
    elif cat == "mod":
        if lang == 'en': text = "<b>🛠 Moderation:</b>\n<code>/admin</code> - Admin Panel\n<code>/ban &lt;id&gt;</code> - Ban user\n<code>/mute &lt;id&gt;</code> - Mute user\n<code>/wipe &lt;id&gt;</code> - Delete messages"
        elif lang == 'jp': text = "<b>🛠 モデレーション:</b>\n<code>/admin</code> - 管理パネル\n<code>/ban &lt;id&gt;</code> - バン\n<code>/mute &lt;id&gt;</code> - ミュート\n<code>/wipe &lt;id&gt;</code> - メッセージ削除"
        else: text = "<b>🛠 Модерация:</b>\n<code>/admin</code> - Панель управления\n<code>/ban &lt;id&gt;</code> - Бан\n<code>/mute &lt;id&gt;</code> - Мут\n<code>/wipe &lt;id&gt;</code> - Очистка"
    elif cat == "fun":
        if lang == 'en': text = "<b>🎲 Fun:</b>\n<code>/roll</code> - Roulette / fate\n<code>/fortune</code> - Fortune roll\n<code>/quote</code> - Random post\n<code>/wordcloud</code> - Word cloud\n<code>/passport</code> - Profile\n<code>/my_stats</code> - Personal stats card\n<code>/stats</code> - Activity charts"
        elif lang == 'jp': text = "<b>🎲 遊び:</b>\n<code>/roll</code> - ルーレット\n<code>/wordcloud</code> - ワードクラウド\n<code>/passport</code> - プロフ\n<code>/schizo</code> - 統合失調症モード"
        else: text = "<b>🎲 Развлечения:</b>\n<code>/roll</code> — Рулетка судьбы\n<code>/fortune</code> — То же что roll (алиас)\n<code>/quote</code> — Случайный пост с борды\n<code>/wordcloud</code> — Облако слов\n<code>/passport</code> — Паспорт анона\n<code>/my_stats</code> — Персональная карта статистики\n<code>/stats</code> — Тепловые карты активности"
    elif cat == "settings":
        if lang == 'en': text = "<b>⚙️ Settings:</b>\n<code>/nsfw</code> - NSFW Spoilers\n<code>/hide</code> - Word filter\n<code>/togglegif</code> - Hide GIFs"
        elif lang == 'jp': text = "<b>⚙️ 設定:</b>\n<code>/nsfw</code> - NSFW スポイラー\n<code>/hide</code> - 単語フィルター\n<code>/togglegif</code> - GIF非表示"
        else: text = "<b>⚙️ Настройки:</b>\n<code>/nsfw</code> - Спойлеры на NSFW\n<code>/hide</code> - Фильтр слов\n<code>/togglegif</code> - Скрыть гифки"
    elif cat == "chat":
        if lang == 'en': text = "<b>💬 Chat:</b>\n<code>/whisper</code> - Secret reply\n<code>/ans</code> - Anonymous reply\n<code>/report</code> - Report post"
        elif lang == 'jp': text = "<b>💬 チャット:</b>\n<code>/whisper</code> - 秘密の返信\n<code>/ans</code> - 匿名返信\n<code>/report</code> - 通報する"
        else: text = "<b>💬 Общение:</b>\n<code>/whisper</code> - Шепот\n<code>/ans</code> - Анонимный ответ\n<code>/report</code> - Пожаловаться"
        
    elif cat == "economy":
        if lang == 'en':
            text = (
                "<b>💰 Economy:</b>\n"
                "<code>/wallet</code> — Balance &amp; transactions\n"
                "<code>/daily</code> — Daily bonus (75 RUB + streak)\n"
                "<code>/shop</code> — Shadow Shop\n"
                "<code>/top</code> — Richest anons leaderboard\n"
                "<code>/duel 200</code> — Challenge anon, 50/50 bet\n"
                "<code>/duel accept</code> — Accept active duel"
            )
        else:
            text = (
                "<b>💰 Экономика:</b>\n"
                "<code>/wallet</code> — Баланс и операции\n"
                "<code>/daily</code> — Ежедневный бонус (75 RUB + серия)\n"
                "<code>/shop</code> — Теневой Магазин\n"
                "<code>/top</code> — Топ богачей (анонимно, только хэши)\n"
                "<code>/duel 200</code> — Дуэль на ставку (50/50 рандом)\n"
                "<code>/duel accept</code> — Принять активный вызов"
            )

    elif cat == "boards":
        from help_text import get_help_hub_page
        text = get_help_hub_page("boards", lang=lang)
    elif cat in ["chat", "economy", "media", "ai", "modes", "actions", "settings", "all"]:
        from help_text import get_help_hub_page
        text = get_help_hub_page(cat, lang=lang)
    else:
        from help_text import get_help_hub_page
        text = get_help_hub_page(cat, lang=lang)

    kb = get_help_keyboard(cat, board_id, stream)
    try:
        if callback.message.photo:
            await callback.message.edit_caption(caption=text, reply_markup=kb, parse_mode="HTML")
        else:
            await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML", disable_web_page_preview=True)
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e).lower():
            runtime_logger.warning(f"process_help_menu edit_text TelegramBadRequest: {e}")
            try:
                from banner_manager import send_banner_message
                await callback.message.delete()
                await send_banner_message(
                    bot=callback.message.bot,
                    chat_id=callback.message.chat.id,
                    caption=text,
                    reply_markup=kb,
                    category="start",
                    parse_mode="HTML"
                )
            except Exception as e2:
                runtime_logger.warning(f"process_help_menu banner fallback failed: {e2}")
    except Exception as e:
        runtime_logger.warning(f"process_help_menu edit_text failed: {e}")
        try:
            from banner_manager import send_banner_message
            await callback.message.delete()
            await send_banner_message(
                bot=callback.message.bot,
                chat_id=callback.message.chat.id,
                caption=text,
                reply_markup=kb,
                category="start",
                parse_mode="HTML"
            )
        except Exception:
            pass
    await callback.answer()

try:
    from wordcloud import WordCloud
    HAS_WORDCLOUD = True
except ImportError:
    HAS_WORDCLOUD = False

try:
    import matplotlib
    GRAPH_LIBS_AVAILABLE = True
except ImportError:
    GRAPH_LIBS_AVAILABLE = False

@router.message(Command("wordcloud", "words", "облако"))
async def cmd_wordcloud(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id: return
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    
    try: spawn_task(delete_message_after_delay(message, 5))
    except Exception as e: runtime_logger.warning(f"Failed to spawn delete_message task: {e}")
    
    if not HAS_WORDCLOUD or not GRAPH_LIBS_AVAILABLE:
        await message.answer("❌ Компоненты WordCloud или Matplotlib не установлены.")
        return
    
    wait_msg = "⏳ Собираю слова за последние 24 часа..."
    if lang == 'en': wait_msg = "⏳ Gathering words for the last 24 hours..."
    elif lang == 'jp': wait_msg = "⏳ 過去24時間の単語を収集中..."
    
    status_message = await message.answer(wait_msg)
    
    try:
        from common.db_pool import db_lock
        db = await get_pool()
        
        # 24 hours ago
        target_timestamp = time.time() - 86400
        
        async with db_lock:
            rows = await db.execute(
                "SELECT content FROM Posts WHERE board_id = ? AND timestamp > ?",
                (board_id, target_timestamp)
            )
            posts = await rows.fetchall()
        
        def process_posts(posts_list):
            text_corpus = ""
            for row in posts_list:
                try:
                    content_dict = json.loads(row[0])
                    text = ""
                    if content_dict.get('type') == 'text':
                        text = content_dict.get('text', '')
                    elif content_dict.get('type') in ['photo', 'video', 'animation', 'document']:
                        text = content_dict.get('caption', '')

                    if text:
                        # Remove HTML tags
                        text = re.sub(r'<[^>]+>', ' ', text)
                        # Remove URLs
                        text = re.sub(r'http[s]?://\S+', ' ', text)
                        text_corpus += text + " "
                except Exception as e:
                    continue

            words = re.findall(r'[а-яА-Яa-zA-Z]{3,}', text_corpus.lower())
            return " ".join([w for w in words if w not in STOP_WORDS])

        final_text = await asyncio.to_thread(process_posts, posts)
        
        if not final_text.strip():
            await status_message.edit_text("❌ Хуй там плавал, а не облако слов. Вы нафлудили слишком мало текста за сутки.")
            return

        def generate_image(txt):
            wc = WordCloud(
                width=1000, height=600, 
                background_color='black', 
                colormap='viridis',
                max_words=150,
                collocations=False
            )
            wc.generate(txt)
            
            img_io = io.BytesIO()
            wc.to_image().save(img_io, 'PNG')
            img_io.seek(0)
            return img_io

        img_io = await asyncio.to_thread(generate_image, final_text)
        
        caption = f"☁️ <b>Облако слов /{board_id}/ за 24 часа</b>"
        if lang == 'en': caption = f"☁️ <b>Word Cloud /{board_id}/ (24h)</b>"
        elif lang == 'jp': caption = f"☁️ <b>ワードクラウド /{board_id}/ (24h)</b>"
        
        await message.answer_photo(
            photo=types.BufferedInputFile(img_io.read(), filename="wordcloud.png"),
            caption=caption,
            parse_mode="HTML"
        )
        await status_message.delete()
        
    except Exception as e:
        runtime_logger.exception(f"Error generating wordcloud: {e}")
        try:
            await status_message.edit_text(f"Произошла ошибка при генерации облака слов: {e}", parse_mode=None)
        except Exception:
            pass
