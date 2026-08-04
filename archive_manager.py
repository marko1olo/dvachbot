import asyncio
import os
import re
import random
import logging
from datetime import datetime, timezone
import aiohttp
from aiogram import Bot
from aiogram.exceptions import TelegramRetryAfter, TelegramNetworkError, TelegramBadRequest
from typing import *

from shared_state import *
from common.config import DATA_DIR
from common.board_config import BOARD_CONFIG
from common.html_utils import escape_html, convert_site_tags_to_telegram
from common.text_utils import sanitize_html, clean_html_tags, generate_poll_text_display
from common.database import add_channel_copy

logger = logging.getLogger(__name__)


def _build_archive_header(board_id: str, post_num: int, content: dict, lang: str) -> str:
    raw_header = content.get('header', f"Пост №{post_num}")
    header_text = ""
    match = re.search(r'(.*?)(Пост №\d+.*|Post No\.\d+.*|レス番 \d+.*)', raw_header, re.DOTALL | re.IGNORECASE)
    
    if match:
        prefix = match.group(1).strip()
        post_part = match.group(2).strip()
        
        has_letters = bool(re.search(r'[a-zA-Zа-яА-ЯёЁ]', prefix))
        reply_to_num = content.get('reply_to_post')
        reply_suffix = ""
        if reply_to_num:
            reply_suffix = f" (reply to №{reply_to_num})" if lang == 'en' else f" (ответ на №{reply_to_num})"
            
        if prefix and has_letters:
            if prefix.endswith('-'):
                prefix = prefix[:-1].strip()
            header_text = f"<b>/{board_id}/</b> | {post_part}{reply_suffix}\n\n<b>{prefix} :</b>"
        else:
            prefix_with_space = f"{prefix} " if prefix else ""
            header_text = f"{prefix_with_space}<b>/{board_id}/</b> | {post_part}{reply_suffix}"
    else:
        reply_to_num = content.get('reply_to_post')
        reply_suffix = ""
        if reply_to_num:
            reply_suffix = f" (reply to №{reply_to_num})" if lang == 'en' else f" (ответ на №{reply_to_num})"
        header_text = f"<b>/{board_id}/</b> | {raw_header}{reply_suffix}"
    return header_text

async def _send_archive_media_group(sender_bot, channel_id: int, content: dict, header_text: str):
    from aiogram.utils.media_group import MediaGroupBuilder
    from common.database import add_file_mirror
    builder = MediaGroupBuilder()
    raw_cap = content.get('caption', '')
    converted_cap = convert_site_tags_to_telegram(raw_cap)
    full_caption = f"{header_text}\n\n{sanitize_html(converted_cap)}".strip()
    if len(full_caption) > 1024: full_caption = full_caption[:1021] + "..."
    media_list = content.get('media', [])
    if not media_list:
        return None, []
    for i, media_item in enumerate(media_list):
        file_id = media_item.get('file_id') or media_item.get('media')
        m_type = media_item['type']
        caption = full_caption if i == 0 else None
        if m_type == 'photo': builder.add_photo(media=file_id, caption=caption, parse_mode="HTML")
        elif m_type == 'video': builder.add_video(media=file_id, caption=caption, parse_mode="HTML")
        elif m_type == 'document': builder.add_document(media=file_id, caption=caption, parse_mode="HTML")
        elif m_type == 'audio': builder.add_audio(media=file_id, caption=caption, parse_mode="HTML")
    try:
        sent_msgs = await sender_bot.send_media_group(channel_id, media=builder.build())
    except Exception as e:
        logger.error(f"⚠️ Failed to send archive media group to channel {channel_id}: {e}")
        return None, []
    sent_message = None
    new_files_data = []
    if sent_msgs:
        sent_message = sent_msgs[0]
        for idx, sm in enumerate(sent_msgs):
            fid = None
            if sm.photo: fid = sm.photo[-1].file_id
            elif sm.video: fid = sm.video.file_id
            elif sm.document: fid = sm.document.file_id
            elif sm.audio: fid = sm.audio.file_id
            if fid:
                new_files_data.append({'type': sm.content_type, 'file_id': fid})
                orig_fid = media_list[idx].get('file_id') or media_list[idx].get('media')
                if orig_fid: await add_file_mirror(orig_fid, 'tg_shadow', fid)
    return sent_message, new_files_data

async def _send_archive_single_media(sender_bot, channel_id: int, content: dict, content_type: str, header_text: str):
    from common.database import add_file_mirror
    orig_fid = content.get('file_id')
    if not orig_fid:
        return None, []
    raw_cap = content.get('caption', '')
    converted_cap = convert_site_tags_to_telegram(raw_cap)
    caption = f"{header_text}\n\n{sanitize_html(converted_cap)}".strip()
    if len(caption) > 1024: caption = caption[:1021] + "..."
    ct_str = str(content_type).split('.')[-1].lower()
    common_args = {"chat_id": channel_id, "caption": caption, "parse_mode": "HTML"}
    sent_message = None
    try:
        if ct_str == 'photo': sent_message = await sender_bot.send_photo(photo=orig_fid, **common_args)
        elif ct_str == 'video': sent_message = await sender_bot.send_video(video=orig_fid, **common_args)
        elif ct_str == 'animation': sent_message = await sender_bot.send_animation(animation=orig_fid, **common_args)
        elif ct_str == 'document': sent_message = await sender_bot.send_document(document=orig_fid, **common_args)
        elif ct_str == 'audio': sent_message = await sender_bot.send_audio(audio=orig_fid, **common_args)
        elif ct_str == 'voice': sent_message = await sender_bot.send_voice(voice=orig_fid, **common_args)
        elif ct_str == 'sticker':
            await sender_bot.send_sticker(channel_id, sticker=orig_fid)
            sent_message = await sender_bot.send_message(channel_id, header_text, parse_mode="HTML")
        elif ct_str == 'video_note':
            await sender_bot.send_video_note(channel_id, video_note=orig_fid)
            sent_message = await sender_bot.send_message(channel_id, header_text, parse_mode="HTML")
    except Exception as e:
        logger.error(f"⚠️ Failed to send single archive media ({ct_str}) to channel {channel_id}: {e}")
        return None, []
    new_files_data = []
    if sent_message:
        fid = None
        if sent_message.photo: fid = sent_message.photo[-1].file_id
        elif sent_message.video: fid = sent_message.video.file_id
        elif sent_message.animation: fid = sent_message.animation.file_id
        elif sent_message.document: fid = sent_message.document.file_id
        elif sent_message.audio: fid = sent_message.audio.file_id
        elif sent_message.voice: fid = sent_message.voice.file_id
        if fid:
            new_files_data.append(fid)
            await add_file_mirror(orig_fid, 'tg_shadow', fid)
    return sent_message, new_files_data

async def _send_archive_media(sender_bot, channel_id: int, content: dict, content_type: str, text_to_send: str, header_text: str):
    for attempt in range(3):
        try:
            sent_message = None
            new_files_data = []
            if text_to_send:
                sent_message = await sender_bot.send_message(
                    chat_id=channel_id,
                    text=text_to_send,
                    parse_mode="HTML",
                    disable_web_page_preview=True
                )
            elif content_type == 'media_group':
                sent_message, new_files_data = await _send_archive_media_group(sender_bot, channel_id, content, header_text)
                if sent_message is None and not new_files_data:
                    break
            else:
                sent_message, new_files_data = await _send_archive_single_media(sender_bot, channel_id, content, content_type, header_text)
            return sent_message, new_files_data
        except (TelegramNetworkError, asyncio.TimeoutError, aiohttp.ClientError):
            if attempt < 2: await asyncio.sleep(2)
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after + 1)
        except Exception:
            break
    return None, []

def _format_archive_text_content(content: dict, header_text: str) -> str | None:
    content_type = content.get("type", "text")
    if content_type != 'text':
        return None

    text_content = convert_site_tags_to_telegram(content.get('text', ''))
    if 'poll_data' in content:
        poll_text = generate_poll_text_display(content['poll_data'])
        text_content = f"{text_content}\n\n{poll_text}".strip()

    final_text = f"{header_text}\n\n{text_content}"
    if len(final_text) > 4096:
        final_text = final_text[:4093] + "..."
    return final_text

async def _update_archive_post_content(post_num: int, content: dict, content_type: str, new_files_data: list, sender_bot_id: int):
    from common.database import register_file_owner, update_post_content
    new_content = content.copy()
    if content_type == 'media_group':
        new_content['media'] = new_files_data
        for f_info in new_files_data:
            await register_file_owner(f_info['file_id'], sender_bot_id)
    else:
        new_content['file_id'] = new_files_data[0]
        await register_file_owner(new_files_data[0], sender_bot_id)
    await update_post_content(post_num, new_content)

async def post_archive_to_channel(bots: dict[str, Bot], file_path: str, board_id: str, thread_info: dict) -> None:

    bot_instance = bots.get(ARCHIVE_POSTING_BOT_ID)
    if not bot_instance:
        print(f"⛔ Ошибка: бот для постинга архивов ('{ARCHIVE_POSTING_BOT_ID}') не найден в списке активных ботов.")
        try:
            os.remove(file_path)
        except OSError: pass
        return
    try:
        from aiogram.types import FSInputFile
        title = escape_html(thread_info.get('title', 'Без названия'))
        board_name = BOARD_CONFIG.get(board_id, {}).get('name', board_id)
        caption = (
            f"🗂 <b>Тред заархивирован</b>\n\n"
            f"<b>Доска:</b> {board_name}\n"
            f"<b>Заголовок:</b> {title}"
        )
        document = FSInputFile(file_path)
        await bot_instance.send_document(
            chat_id=ARCHIVE_CHANNEL_ID,
            document=document,
            caption=caption,
            parse_mode="HTML"
        )
        print(f"✅ Архив треда '{title}' отправлен в канал {ARCHIVE_CHANNEL_ID}.")
    except Exception as e:
        print(f"⛔ Не удалось отправить архив в канал {ARCHIVE_CHANNEL_ID}: {e}")
    finally:
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                print(f"🗑️ Временный файл архива удален: {file_path}")
        except Exception as e:
            print(f"⚠️ Не удалось удалить временный файл {file_path}: {e}")

def _sync_generate_thread_archive(board_id: str, thread_id: str, thread_info: dict, posts_data: list[dict]) -> str | None:
    """
    Синхронная, потокобезопасная функция для генерации HTML-архива.
    Работает только с переданными ей данными постов.
    """
    try:
        title = escape_html(thread_info.get('title', 'Без названия'))
        filepath = os.path.join(DATA_DIR, f"archive_{board_id}_{thread_id}.html")
        html_style = """
        <style>
            body { font-family: sans-serif; background-color: #f0f0f0; color: #333; line-height: 1.6; margin: 20px; }
            .container { max-width: 800px; margin: auto; background-color: #fff; padding: 20px; border-radius: 5px; box-shadow: 0 0 10px rgba(0,0,0,0.1); }
            h1 { color: #d00; border-bottom: 2px solid #ccc; padding-bottom: 10px; }
            .post { border: 1px solid #ddd; padding: 10px; margin-bottom: 15px; border-radius: 4px; background-color: #fafafa; }
            .post-header { font-size: 0.9em; color: #888; margin-bottom: 10px; }
            .post-header b { color: #d00; }
            .post-content { white-space: pre-wrap; word-wrap: break-word; }
            .greentext { color: #789922; }
            .reply-link { color: #d00; text-decoration: none; }
        </style>
        """
        html_parts = [
            '<!DOCTYPE html>\n', '<html lang="ru">\n', '<head>\n', '    <meta charset="UTF-8">\n',
            f'    <title>Архив треда: {title}</title>\n', f'    {html_style}\n', '</head>\n',
            '<body>\n', '    <div class="container">\n', f'        <h1>{title}</h1>\n'
        ]
        for post_data in posts_data:
            content = post_data.get('content', {})
            post_num = content.get('post_num', 'N/A')
            timestamp_str = post_data.get('timestamp', '')
            try:
                timestamp_dt = datetime.fromisoformat(timestamp_str)
                timestamp_formatted = timestamp_dt.strftime('%Y-%m-%d %H:%M:%S timezone.utc')
            except (ValueError, TypeError):
                timestamp_formatted = "N/A"
            post_body = ""
            if content.get('type') == 'text':
                text = clean_html_tags(content.get('text', ''))
                lines = text.split('\n')
                formatted_lines = []
                for line in lines:
                    safe_line = escape_html(line)
                    if safe_line.strip().startswith('&gt;'):
                        formatted_lines.append(f'<span class="greentext">{safe_line}</span>')
                    else:
                        formatted_lines.append(safe_line)
                post_body = "<br>".join(formatted_lines)
            elif content.get('type') in ['photo', 'video', 'animation', 'document', 'audio']:
                media_type_map = {'photo': 'Изображение', 'video': 'Видео', 'animation': 'GIF', 'document': 'Документ', 'audio': 'Аудио'}
                media_type = media_type_map.get(content.get('type'), 'Медиа')
                caption = escape_html(clean_html_tags(content.get('caption', '')))
                post_body = f"<b>[{media_type}]</b><br>{caption}"
            else:
                 post_body = f"<i>[{content.get('type', 'Системное сообщение')}]</i>"
            reply_to = content.get('reply_to_post')
            reply_html = f'<a href="#{reply_to}" class="reply-link">&gt;&gt;{reply_to}</a><br>' if reply_to else ""
            html_parts.append(
                f'        <div class="post" id="{post_num}">\n'
                '            <div class="post-header">\n'
                f'                <b>Пост №{post_num}</b> - {timestamp_formatted}\n'
                '            </div>\n'
                '            <div class="post-content">\n'
                f'                {reply_html}{post_body}\n'
                '            </div>\n'
                '        </div>\n'
            )
        html_parts.extend(['    </div>\n', '</body>\n', '</html>\n'])
        final_html_content = "".join(html_parts)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(final_html_content)
        print(f"✅ [{board_id}] Архив для треда {thread_id} сохранен в {filepath}")
        return filepath
    except Exception as e:
        import traceback
        print(f"⛔ [{board_id}] Ошибка генерации архива для треда {thread_id}: {e}\n{traceback.format_exc()}")
        return None

async def archive_thread(bots: dict[str, Bot], board_id: str, thread_id: str, thread_info: dict):

    posts_data_copy = []
    async with storage_lock:
        post_nums = thread_info.get('posts', [])
        for post_num in post_nums:
            post_data = messages_storage.get(post_num)
            if post_data:
                data_copy = {
                    'content': post_data.get('content', {}).copy(),
                    'timestamp': post_data.get('timestamp', datetime.now(timezone.utc)).isoformat()
                }
                posts_data_copy.append(data_copy)
    loop = asyncio.get_running_loop()
    filepath = await loop.run_in_executor(
        save_executor,
        _sync_generate_thread_archive,
        board_id, thread_id, thread_info, posts_data_copy
    )
    if filepath:
        await post_archive_to_channel(bots, filepath, board_id, thread_info)
    try:
        from common.database import archive_thread_in_db
        await archive_thread_in_db(int(thread_id))
    except Exception as e:
        print(f"❌ Ошибка при архивации треда #{thread_id} в БД: {e}")

def _site_file_send_type(file_info: dict) -> str | None:
    raw_type = str(file_info.get("type") or "").split(".")[-1].lower()
    filename = str(file_info.get("filename") or "").lower()
    if raw_type in {"image", "photo", "picture"}:
        return "photo"
    if raw_type in {"video", "video_note"}:
        return "video"
    if raw_type in {"gif", "animation"}:
        return "animation"
    if raw_type in {"audio", "voice"}:
        return "audio" if raw_type == "audio" else "voice"
    if raw_type in {"document", "file"}:
        return "document"
    if raw_type == "sticker":
        return "document"
    if filename.endswith((".jpg", ".jpeg", ".png")):
        return "photo"
    if filename.endswith((".mp4", ".mov", ".mkv", ".webm")):
        return "video" if not filename.endswith(".webm") else "document"
    if filename.endswith(".gif"):
        return "animation"
    if filename.endswith((".mp3", ".wav", ".ogg", ".opus")):
        return "audio"
    return "document"


async def post_special_num_to_channel(bots: dict[str, Bot], board_id: str, post_num: int, level: int, content: dict, author_id: int):
    """
    (ИСПРАВЛЕННАЯ ВЕРСИЯ 3.0)
    Отправляет уведомление о "счастливом" посте в канал архивов.
    Надежно обрабатывает все типы медиа, отправляя сам файл, а не плейсхолдер.
    """
    import main as _main
    _AUTHORIZED_ARCHIVE_BOTS = getattr(_main, 'AUTHORIZED_ARCHIVE_BOTS', set())
    _ARCHIVE_POSTING_BOT_ID = getattr(_main, 'ARCHIVE_POSTING_BOT_ID', None)
    _SPECIAL_NUMERALS_CONFIG = getattr(_main, 'SPECIAL_NUMERALS_CONFIG', {})
    _ARCHIVE_CHANNEL_ID = getattr(_main, 'ARCHIVE_CHANNEL_ID', None)
    try:
        bot_instance = bots.get(board_id)
        archive_bot = bot_instance if board_id in _AUTHORIZED_ARCHIVE_BOTS else GLOBAL_BOTS.get(_ARCHIVE_POSTING_BOT_ID)
        
        if not archive_bot:
            print("⛔ Ошибка: бот для постинга архивов не найден.")
            return

        config = _SPECIAL_NUMERALS_CONFIG.get(level, {'label': 'Get', 'emojis': ('🎯',)})
        emoji = random.choice(config['emojis'])
        label = config['label'].upper()
        board_name = BOARD_CONFIG.get(board_id, {}).get('name', board_id)
        
        header = f"{emoji} <b>{label} #{post_num}</b> {emoji}\n\n<b>Доска:</b> {board_name}\n"
        text_content = content.get('text') or content.get('caption') or ''
        
        caption_text = f"{header}\n{text_content}"
        content_type_str = str(content.get("type", "")).split('.')[-1].lower()

        max_attempts = 5
        delay = 3.0
        
        for attempt in range(max_attempts):
            try:
                # --- НАЧАЛО ИСПРАВЛЕНИЙ (Надежная отправка медиа) ---
                file_id = content.get('file_id')
                if content_type_str == 'media_group':
                    media_list = content.get('media', [])
                    if media_list and media_list[0]:
                        file_id = media_list[0].get('file_id')
                        content_type_str = media_list[0].get('type', 'photo')

                final_caption = caption_text[:1021] + "..." if len(caption_text) > 1024 else caption_text
                
                # Явная обработка каждого типа, чтобы избежать ошибок с аргументами
                if content_type_str == 'photo' and file_id:
                    await archive_bot.send_photo(_ARCHIVE_CHANNEL_ID, file_id, caption=final_caption)
                elif content_type_str == 'video' and file_id:
                    await archive_bot.send_video(_ARCHIVE_CHANNEL_ID, file_id, caption=final_caption)
                elif content_type_str == 'animation' and file_id:
                    await archive_bot.send_animation(_ARCHIVE_CHANNEL_ID, file_id, caption=final_caption)
                elif content_type_str == 'document' and file_id:
                    await archive_bot.send_document(_ARCHIVE_CHANNEL_ID, file_id, caption=final_caption)
                elif content_type_str == 'audio' and file_id:
                    await archive_bot.send_audio(_ARCHIVE_CHANNEL_ID, file_id, caption=final_caption)
                elif content_type_str == 'voice' and file_id:
                    await archive_bot.send_voice(_ARCHIVE_CHANNEL_ID, file_id)
                    await archive_bot.send_message(_ARCHIVE_CHANNEL_ID, final_caption, disable_web_page_preview=True)
                elif content_type_str == 'sticker' and file_id:
                    await archive_bot.send_sticker(_ARCHIVE_CHANNEL_ID, file_id)
                    await archive_bot.send_message(_ARCHIVE_CHANNEL_ID, final_caption, disable_web_page_preview=True)
                elif content_type_str == 'video_note' and file_id:
                    await archive_bot.send_video_note(_ARCHIVE_CHANNEL_ID, file_id)
                    await archive_bot.send_message(_ARCHIVE_CHANNEL_ID, final_caption, disable_web_page_preview=True)
                else: # Если это текст или медиа без file_id
                    final_text_for_message = caption_text[:4093] + "..." if len(caption_text) > 4096 else caption_text
                    await archive_bot.send_message(_ARCHIVE_CHANNEL_ID, final_text_for_message, parse_mode="HTML", disable_web_page_preview=True)
                # --- КОНЕЦ ИСПРАВЛЕНИЙ ---
                
                print(f"✅ Уведомление о счастливом посте #{post_num} ({label}) отправлено в канал.")
                return 

            except TelegramRetryAfter as e:
                wait_time = e.retry_after + 1
                print(f"⚠️ API Limit on happy post #{post_num}. Waiting {wait_time}s...")
                await asyncio.sleep(wait_time)
            except (TelegramNetworkError, asyncio.TimeoutError, aiohttp.ClientError) as e:
                if attempt < max_attempts - 1:
                    print(f"🌐 Network error on happy post #{post_num} (try {attempt + 1}). Retrying in {delay:.1f}s...")
                    await asyncio.sleep(delay)
                    delay *= 1.5
                else:
                    raise e
            except TelegramBadRequest as e:
                print(f"❌ BadRequest on happy post #{post_num}: {e}. No retry.")
                # Если медиа не отправилось, пробуем отправить как текст
                try:
                    final_text_for_message = caption_text[:4093] + "..." if len(caption_text) > 4096 else caption_text
                    await archive_bot.send_message(_ARCHIVE_CHANNEL_ID, final_text_for_message, parse_mode="HTML", disable_web_page_preview=True)
                    print(f"✅ Уведомление о счастливом посте #{post_num} отправлено как текст после ошибки медиа.")
                except Exception as final_e:
                    print(f"❌ Финальная попытка отправки текста для #{post_num} также провалилась: {final_e}")
                return # Выходим в любом случае после BadRequest
    except Exception as e:
        import traceback
        print(f"⛔ Не удалось отправить счастливый пост #{post_num} в канал после всех попыток: {e}\n{traceback.format_exc()}")

async def _forward_post_to_realtime_archive(bot_instance: Bot, board_id: str, post_num: int, content: dict, is_shadow_muted: bool, stream: str = 'ru'):
    if is_shadow_muted:
        return
    from common.database import get_post_by_num
    import main as _main
    _ARCHIVE_POSTING_BOT_ID = getattr(_main, 'ARCHIVE_POSTING_BOT_ID', None)
    _AUTHORIZED_ARCHIVE_BOTS = getattr(_main, 'AUTHORIZED_ARCHIVE_BOTS', set())
    _MIRROR_CHANNELS = getattr(_main, 'MIRROR_CHANNELS', [])
    _build_archive_header = getattr(_main, '_build_archive_header', None)
    _fmt_archive_text = getattr(_main, '_format_archive_text_content', None)
    _send_archive_media = getattr(_main, '_send_archive_media', None)
    _update_archive_post_content = getattr(_main, '_update_archive_post_content', None)

    check_post = await get_post_by_num(post_num)
    if not check_post:
        return
    archive_bot = GLOBAL_BOTS.get(_ARCHIVE_POSTING_BOT_ID)
    sender_bot = bot_instance if board_id in _AUTHORIZED_ARCHIVE_BOTS else archive_bot
    if not sender_bot:
        return
    sender_bot_id = getattr(sender_bot, 'id', 0)
    lang = 'en' if board_id == 'int' else 'ru'

    header_text = _build_archive_header(board_id, post_num, content, lang) if _build_archive_header else ''
    
    content_type = content.get("type", "text")
    text_to_send = _fmt_archive_text(content, header_text) if _fmt_archive_text else header_text
    
    db_updated = False
    for channel_id in _MIRROR_CHANNELS:
        if not channel_id or channel_id == 0:
            continue
        if not _send_archive_media:
            continue
        sent_message, new_files_data = await _send_archive_media(sender_bot, channel_id, content, content_type, text_to_send, header_text)
        if sent_message:
            try:
                await add_channel_copy(post_num, channel_id, sent_message.message_id)
                if not db_updated and new_files_data and _update_archive_post_content:
                    await _update_archive_post_content(post_num, content, content_type, new_files_data, sender_bot_id)
                    db_updated = True
            except Exception:
                pass
