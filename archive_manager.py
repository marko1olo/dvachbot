import __main__ as main
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

import io
from aiogram.types import BufferedInputFile, URLInputFile
from common.database import get_file_mirrors, get_file_owner_id, add_file_mirror

async def _download_media_bytes(file_id: str) -> tuple[bytes | None, str]:
    """Downloads file bytes via the owning bot or any active bot in GLOBAL_BOTS."""
    owner_bot = None
    try:
        owner_id = await get_file_owner_id(file_id)
        if owner_id:
            for b in main.GLOBAL_BOTS.values():
                if getattr(b, 'id', None) == owner_id:
                    owner_bot = b
                    break
    except Exception:
        import traceback; traceback.print_exc()

    candidate_bots = []
    if owner_bot:
        candidate_bots.append(owner_bot)
    if hasattr(main, 'GLOBAL_BOTS') and isinstance(main.GLOBAL_BOTS, dict):
        for b in main.GLOBAL_BOTS.values():
            if b not in candidate_bots:
                candidate_bots.append(b)

    for bot_inst in candidate_bots:
        try:
            buf = io.BytesIO()
            await bot_inst.download(file_id, destination=buf)
            buf.seek(0)
            data = buf.read()
            if data:
                return data, "media.dat"
        except Exception:
            continue
    return None, ""

async def _resolve_media_source(sender_bot: Bot, orig_fid: str, media_item: dict = None):
    """
    Resolves the best media input for sender_bot:
    1. Returns tg_shadow file_id if present in FileMirrors.
    2. Returns URLInputFile if catbox/pixhost/HTTP URL mirror exists.
    3. Downloads file via owner bot and returns BufferedInputFile.
    4. Defaults to orig_fid string.
    """
    if not orig_fid:
        return None

    try:
        mirrors = await get_file_mirrors(orig_fid)
        if mirrors:
            if 'tg_shadow' in mirrors and mirrors['tg_shadow']:
                return mirrors['tg_shadow']
            for m_type in ['catbox', 'pixhost', 'huggingface', '0x0', 'imgbb']:
                if m_type in mirrors and mirrors[m_type]:
                    return URLInputFile(mirrors[m_type])
            for m_type, url in mirrors.items():
                if isinstance(url, str) and (url.startswith('http://') or url.startswith('https://')):
                    return URLInputFile(url)
    except Exception as e:
        logger.warning(f"Failed to query file mirrors for {orig_fid}: {e}")

    if media_item:
        for url_key in ['original_url', 'url', 'catbox_url', 'pixhost_url', 'link']:
            u = media_item.get(url_key)
            if u and isinstance(u, str) and u.startswith('http'):
                return URLInputFile(u)

    sender_id = getattr(sender_bot, 'id', None)
    owner_id = await get_file_owner_id(orig_fid)
    if owner_id and sender_id and owner_id != sender_id:
        file_bytes, _ = await _download_media_bytes(orig_fid)
        if file_bytes:
            m_type = (media_item.get('type') if media_item else '') or ''
            ext = 'jpg' if 'photo' in m_type else ('mp4' if 'video' in m_type or 'anim' in m_type else 'dat')
            return BufferedInputFile(file_bytes, filename=f"media.{ext}")

    return orig_fid

async def _send_archive_media_group(sender_bot, channel_id: int, content: dict, header_text: str):
    from aiogram.utils.media_group import MediaGroupBuilder
    media_list = content.get('media', [])
    if not media_list:
        return None, []

    raw_cap = content.get('caption', '')
    converted_cap = convert_site_tags_to_telegram(raw_cap)
    full_caption = f"{header_text}\n\n{sanitize_html(converted_cap)}".strip()
    if len(full_caption) > 1024: full_caption = full_caption[:1021] + "..."

    async def _build_group(force_download=False):
        builder = MediaGroupBuilder()
        for i, media_item in enumerate(media_list):
            orig_fid = media_item.get('file_id') or media_item.get('media') or media_item.get('path') or media_item.get('tg_file_id')
            m_type = str(media_item.get('type') or '').split('.')[-1].lower()
            caption = full_caption if i == 0 else None
            
            if force_download:
                file_bytes, _ = await _download_media_bytes(orig_fid)
                media_src = BufferedInputFile(file_bytes, filename="media.dat") if file_bytes else orig_fid
            else:
                media_src = await _resolve_media_source(sender_bot, orig_fid, media_item)

            if m_type == 'photo': builder.add_photo(media=media_src, caption=caption, parse_mode="HTML")
            elif m_type == 'video': builder.add_video(media=media_src, caption=caption, parse_mode="HTML")
            elif m_type == 'document': builder.add_document(media=media_src, caption=caption, parse_mode="HTML")
            elif m_type == 'audio': builder.add_audio(media=media_src, caption=caption, parse_mode="HTML")
        return builder.build()

    try:
        group = await _build_group(force_download=False)
        sent_msgs = await sender_bot.send_media_group(channel_id, media=group)
    except TelegramBadRequest as e:
        logger.warning(f"⚠️ TelegramBadRequest on media group ({e}). Forcing download fallback...")
        try:
            group = await _build_group(force_download=True)
            sent_msgs = await sender_bot.send_media_group(channel_id, media=group)
        except Exception as ex:
            logger.error(f"❌ Media group fallback failed: {ex}")
            return None, []
    except Exception as e:
        logger.error(f"⚠️ Failed to send archive media group to channel {channel_id}: {e}", exc_info=True)
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
                norm_type = str(sm.content_type).split('.')[-1].lower() if sm.content_type else 'photo'
                new_files_data.append({'type': norm_type, 'file_id': fid})
                orig_fid = media_list[idx].get('file_id') or media_list[idx].get('media')
                if orig_fid: await add_file_mirror(orig_fid, 'tg_shadow', fid)
    return sent_message, new_files_data

async def _send_archive_single_media(sender_bot, channel_id: int, content: dict, content_type: str, header_text: str):
    orig_fid = content.get('file_id')
    if not orig_fid and content.get('files'):
        files = content.get('files')
        if isinstance(files, list) and files:
            first_f = files[0]
            if isinstance(first_f, dict):
                orig_fid = first_f.get('file_id') or first_f.get('tg_file_id') or first_f.get('path') or first_f.get('file_path')
            elif isinstance(first_f, str):
                orig_fid = first_f
    if not orig_fid and content.get('media'):
        media = content.get('media')
        if isinstance(media, list) and media:
            first_m = media[0]
            if isinstance(first_m, dict):
                orig_fid = first_m.get('file_id') or first_m.get('tg_file_id')
            elif isinstance(first_m, str):
                orig_fid = first_m
    if not orig_fid:
        return None, []
    raw_cap = content.get('caption', '')
    converted_cap = convert_site_tags_to_telegram(raw_cap)
    caption = f"{header_text}\n\n{sanitize_html(converted_cap)}".strip()
    if len(caption) > 1024: caption = caption[:1021] + "..."
    ct_str = str(content_type).split('.')[-1].lower()
    common_args = {"chat_id": channel_id, "caption": caption, "parse_mode": "HTML"}
    
    media_source = await _resolve_media_source(sender_bot, orig_fid, content)

    async def _do_send(src):
        if ct_str == 'photo': return await sender_bot.send_photo(photo=src, **common_args)
        elif ct_str == 'video': return await sender_bot.send_video(video=src, **common_args)
        elif ct_str == 'animation': return await sender_bot.send_animation(animation=src, **common_args)
        elif ct_str == 'document': return await sender_bot.send_document(document=src, **common_args)
        elif ct_str == 'audio': return await sender_bot.send_audio(audio=src, **common_args)
        elif ct_str == 'voice': return await sender_bot.send_voice(voice=src, **common_args)
        elif ct_str == 'sticker':
            await sender_bot.send_sticker(channel_id, sticker=src)
            return await sender_bot.send_message(channel_id, header_text, parse_mode="HTML")
        elif ct_str == 'video_note':
            await sender_bot.send_video_note(channel_id, video_note=src)
            return await sender_bot.send_message(channel_id, header_text, parse_mode="HTML")
        return None

    sent_message = None
    try:
        sent_message = await _do_send(media_source)
    except TelegramBadRequest as e:
        logger.warning(f"⚠️ TelegramBadRequest sending {ct_str} ({e}). Downloading file buffer fallback...")
        file_bytes, filename = await _download_media_bytes(orig_fid)
        if file_bytes:
            try:
                sent_message = await _do_send(BufferedInputFile(file_bytes, filename=filename))
            except Exception as ex:
                logger.error(f"❌ Single media fallback failed for {orig_fid}: {ex}")
                return None, []
        else:
            return None, []
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
            ct_str = str(content_type).split('.')[-1].lower()
            has_media = bool(
                content.get('file_id') 
                or content.get('media') 
                or content.get('files') 
                or ct_str in ('photo', 'video', 'animation', 'document', 'audio', 'voice', 'sticker', 'video_note', 'media_group')
            )
            if ct_str == 'media_group':
                sent_message, new_files_data = await _send_archive_media_group(sender_bot, channel_id, content, header_text)
                if sent_message is None and not new_files_data:
                    sent_message, new_files_data = await _send_archive_single_media(sender_bot, channel_id, content, content_type, header_text)
            elif has_media:
                sent_message, new_files_data = await _send_archive_single_media(sender_bot, channel_id, content, content_type, header_text)
            else:
                sent_message = await sender_bot.send_message(
                    chat_id=channel_id,
                    text=text_to_send,
                    parse_mode="HTML",
                    disable_web_page_preview=True
                )
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

    bot_instance = bots.get(main.ARCHIVE_POSTING_BOT_ID)
    if not bot_instance:
        print(f"⛔ Ошибка: бот для постинга архивов ('{main.ARCHIVE_POSTING_BOT_ID}') не найден в списке активных ботов.")
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
            chat_id=main.ARCHIVE_CHANNEL_ID,
            document=document,
            caption=caption,
            parse_mode="HTML"
        )
        print(f"✅ Архив треда '{title}' отправлен в канал {main.ARCHIVE_CHANNEL_ID}.")
    except Exception as e:
        print(f"⛔ Не удалось отправить архив в канал {main.ARCHIVE_CHANNEL_ID}: {e}")
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
    async with main.storage_lock:
        post_nums = thread_info.get('posts', [])
        for post_num in post_nums:
            post_data = main.messages_storage.get(post_num)
            if post_data:
                data_copy = {
                    'content': post_data.get('content', {}).copy(),
                    'timestamp': post_data.get('timestamp', datetime.now(timezone.utc)).isoformat()
                }
                posts_data_copy.append(data_copy)
    loop = asyncio.get_running_loop()
    filepath = await loop.run_in_executor(
        main.save_executor,
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
    try:
        bot_instance = bots.get(board_id)
        archive_bot = bot_instance if board_id in AUTHORIZED_ARCHIVE_BOTS else GLOBAL_BOTS.get(ARCHIVE_POSTING_BOT_ID)
        
        if not archive_bot:
            print("⛔ Ошибка: бот для постинга архивов не найден.")
            return

        config = SPECIAL_NUMERALS_CONFIG.get(level, {'label': 'Get', 'emojis': ('🎯',)})
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
                if not file_id and content.get('files'):
                    files = content.get('files')
                    if isinstance(files, list) and files and isinstance(files[0], dict):
                        file_id = files[0].get('file_id') or files[0].get('tg_file_id')
                if content_type_str == 'media_group' or not file_id:
                    media_list = content.get('media', []) or content.get('files', [])
                    if media_list and isinstance(media_list[0], dict):
                        file_id = media_list[0].get('file_id') or media_list[0].get('tg_file_id')
                        content_type_str = media_list[0].get('type', content_type_str or 'photo')

                final_caption = caption_text[:1021] + "..." if len(caption_text) > 1024 else caption_text
                
                # Явная обработка каждого типа, чтобы избежать ошибок с аргументами
                if content_type_str == 'photo' and file_id:
                    await archive_bot.send_photo(ARCHIVE_CHANNEL_ID, file_id, caption=final_caption)
                elif content_type_str == 'video' and file_id:
                    await archive_bot.send_video(ARCHIVE_CHANNEL_ID, file_id, caption=final_caption)
                elif content_type_str == 'animation' and file_id:
                    await archive_bot.send_animation(ARCHIVE_CHANNEL_ID, file_id, caption=final_caption)
                elif content_type_str == 'document' and file_id:
                    await archive_bot.send_document(ARCHIVE_CHANNEL_ID, file_id, caption=final_caption)
                elif content_type_str == 'audio' and file_id:
                    await archive_bot.send_audio(ARCHIVE_CHANNEL_ID, file_id, caption=final_caption)
                elif content_type_str == 'voice' and file_id:
                    await archive_bot.send_voice(ARCHIVE_CHANNEL_ID, file_id)
                    await archive_bot.send_message(ARCHIVE_CHANNEL_ID, final_caption, disable_web_page_preview=True)
                elif content_type_str == 'sticker' and file_id:
                    await archive_bot.send_sticker(ARCHIVE_CHANNEL_ID, file_id)
                    await archive_bot.send_message(ARCHIVE_CHANNEL_ID, final_caption, disable_web_page_preview=True)
                elif content_type_str == 'video_note' and file_id:
                    await archive_bot.send_video_note(ARCHIVE_CHANNEL_ID, file_id)
                    await archive_bot.send_message(ARCHIVE_CHANNEL_ID, final_caption, disable_web_page_preview=True)
                else: # Если это текст или медиа без file_id
                    final_text_for_message = caption_text[:4093] + "..." if len(caption_text) > 4096 else caption_text
                    await archive_bot.send_message(ARCHIVE_CHANNEL_ID, final_text_for_message, parse_mode="HTML", disable_web_page_preview=True)
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

    check_post = await get_post_by_num(post_num)
    if not check_post:
        return
    archive_bot = GLOBAL_BOTS.get(ARCHIVE_POSTING_BOT_ID)
    sender_bot = bot_instance if board_id in AUTHORIZED_ARCHIVE_BOTS else archive_bot
    if not sender_bot:
        return
    sender_bot_id = getattr(sender_bot, 'id', 0)
    lang = 'en' if board_id == 'int' else 'ru'

    header_text = _build_archive_header(board_id, post_num, content, lang)
    
    content_type = content.get("type", "text")
    text_to_send = _format_archive_text_content(content, header_text) or header_text
    
    db_updated = False
    for channel_id in MIRROR_CHANNELS:
        if not channel_id or channel_id == 0:
            continue
        sent_message, new_files_data = await _send_archive_media(sender_bot, channel_id, content, content_type, text_to_send, header_text)
        if sent_message:
            try:
                await add_channel_copy(post_num, channel_id, sent_message.message_id)
                if not db_updated and new_files_data:
                    await _update_archive_post_content(post_num, content, content_type, new_files_data, sender_bot_id)
                    db_updated = True
            except Exception:
                import traceback; traceback.print_exc()
