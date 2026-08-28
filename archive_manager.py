import shared_state
import asyncio
import os
import re
import random
import logging
from datetime import datetime, timezone
import aiohttp
from aiogram import Bot
from aiogram.exceptions import TelegramRetryAfter, TelegramNetworkError, TelegramBadRequest, TelegramForbiddenError
import io
from typing import *

from shared_state import *
from common.config import DATA_DIR
from common.board_config import BOARD_CONFIG
from common.html_utils import escape_html, convert_site_tags_to_telegram
from common.text_utils import sanitize_html, clean_html_tags, generate_poll_text_display, clean_html_for_tg
from common.database import add_channel_copy

logger = logging.getLogger(__name__)

_INACCESSIBLE_CHANNELS: set[int] = set()
_BOT_INACCESSIBLE_CHANNELS: set[tuple[Any, int]] = set()


def _get_bot_key(bot: Any) -> Any:
    if bot is None:
        return 0
    return getattr(bot, 'id', None) or getattr(bot, 'token', None) or id(bot)


def _is_chat_not_found_or_forbidden(e: Exception) -> bool:
    if isinstance(e, TelegramForbiddenError):
        return True
    err_str = str(e).lower()
    return (
        "chat not found" in err_str
        or "channel not found" in err_str
        or "chat_id is empty" in err_str
        or "chat is not accessible" in err_str
        or "chat_not_found" in err_str
        or "bot was blocked" in err_str
        or "bot was kicked" in err_str
        or "bot is not a member" in err_str
        or "not a member of the channel" in err_str
        or "not enough rights to send text messages" in err_str
        or "not enough rights" in err_str
        or "rights to send" in err_str
        or "have no rights to send" in err_str
        or "forbidden" in err_str
        or "peer_id_invalid" in err_str
    )


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


def prepare_telegram_text(text: str, max_len: int = 4096) -> str:
    """
    Безопасно форматирует и обрезает текст для отправки в Telegram:
    - Применяет clean_html_for_tg
    - Если длина превышает max_len, безопасно усекает с запасом под '...' и закрывающие теги
    - Повторно балансирует и закрывает все HTML-теги через clean_html_for_tg
    - Если даже после этого текст превышает max_len, возвращает чистый текст без тегов
    """
    if not text:
        return ""
    cleaned = clean_html_for_tg(text)
    if len(cleaned) <= max_len:
        return cleaned

    cutoff = max(10, max_len - 30)
    truncated = cleaned[:cutoff].rstrip() + "..."
    balanced = clean_html_for_tg(truncated)

    if len(balanced) <= max_len:
        return balanced

    # Фолбэк: голый текст без HTML-тегов, строго обрезанный
    plain = clean_html_tags(text)
    if len(plain) > max_len:
        plain = plain[:max_len - 3] + "..."
    return plain

import io
from aiogram.types import BufferedInputFile, URLInputFile
from common.database import get_file_mirrors, get_file_owner_id, add_file_mirror

async def _download_media_bytes(file_id: str) -> tuple[bytes | None, str]:
    """Downloads file bytes via HTTP URL, file mirrors, or any active bot in GLOBAL_BOTS."""
    if not file_id:
        return None, ""

    # If file_id is already an HTTP URL, download directly
    if str(file_id).startswith(("http://", "https://")):
        try:
            import httpx
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                resp = await client.get(file_id)
                if resp.status_code == 200 and resp.content:
                    return resp.content, "media.dat"
        except Exception as http_err:
            logger.debug(f"HTTP download failed for {file_id}: {http_err}")

    # Check FileMirrors for external URL mirrors
    try:
        mirrors = await get_file_mirrors(file_id)
        if mirrors:
            for m_type in ['catbox', 'pixhost', 'huggingface', '0x0', 'imgbb']:
                m_url = mirrors.get(m_type)
                if m_url and isinstance(m_url, str) and m_url.startswith(("http://", "https://")):
                    try:
                        import httpx
                        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                            resp = await client.get(m_url)
                            if resp.status_code == 200 and resp.content:
                                return resp.content, "media.dat"
                    except Exception:
                        continue
    except Exception:
        pass

    owner_bot = None
    try:
        owner_id = await get_file_owner_id(file_id)
        if owner_id and isinstance(shared_state.GLOBAL_BOTS, dict):
            for b in shared_state.GLOBAL_BOTS.values():
                if getattr(b, 'id', None) == owner_id:
                    owner_bot = b
                    break
    except Exception:
        pass

    candidate_bots = []
    if owner_bot:
        candidate_bots.append(owner_bot)
    if isinstance(shared_state.GLOBAL_BOTS, dict):
        for b in shared_state.GLOBAL_BOTS.values():
            if b not in candidate_bots:
                candidate_bots.append(b)

    for bot_inst in candidate_bots[:10]:
        try:
            buf = io.BytesIO()
            await asyncio.wait_for(bot_inst.download(file_id, destination=buf), timeout=12.0)
            buf.seek(0)
            data = buf.read()
            if data:
                return data, "media.dat"
        except (asyncio.TimeoutError, TelegramBadRequest, TelegramForbiddenError, TelegramNetworkError):
            continue
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
        if media_item and isinstance(media_item, dict):
            if media_item.get('voice_bytes'):
                return BufferedInputFile(media_item['voice_bytes'], filename="cyberchad_roast.ogg")
            if media_item.get('image_bytes'):
                return BufferedInputFile(media_item['image_bytes'], filename="image.jpg")
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
    full_caption = prepare_telegram_text(f"{header_text}\n\n{sanitize_html(converted_cap)}".strip(), max_len=1024)

    async def _build_group(force_download=False):
        builder = MediaGroupBuilder()
        for i, media_item in enumerate(media_list):
            orig_fid = media_item.get('file_id') or media_item.get('media') or media_item.get('path') or media_item.get('tg_file_id')
            if not orig_fid:
                continue
            m_type = str(media_item.get('type') or '').split('.')[-1].lower()
            caption = full_caption if i == 0 else None
            
            if force_download:
                file_bytes, _ = await _download_media_bytes(orig_fid)
                media_src = BufferedInputFile(file_bytes, filename="media.dat") if file_bytes else orig_fid
            else:
                media_src = await _resolve_media_source(sender_bot, orig_fid, media_item)

            if not media_src:
                continue

            if m_type == 'photo': builder.add_photo(media=media_src, caption=caption, parse_mode="HTML")
            elif m_type == 'video': builder.add_video(media=media_src, caption=caption, parse_mode="HTML")
            elif m_type == 'document': builder.add_document(media=media_src, caption=caption, parse_mode="HTML")
            elif m_type == 'audio': builder.add_audio(media=media_src, caption=caption, parse_mode="HTML")
        return builder.build()

    async def _send_text_fallback():
        safe_msg = prepare_telegram_text(f"{header_text}\n\n{sanitize_html(converted_cap)}".strip(), max_len=4096)
        try:
            return await sender_bot.send_message(channel_id, safe_msg, parse_mode="HTML", request_timeout=30)
        except TelegramBadRequest as tbe:
            logger.warning(f"Media group text fallback HTML error ({tbe}), trying plain text...")
            plain_txt = clean_html_tags(f"{header_text}\n\n{converted_cap}")[:4090]
            try:
                return await sender_bot.send_message(channel_id, plain_txt, parse_mode=None, request_timeout=30)
            except Exception:
                return None
        except Exception:
            return None

    try:
        group = await _build_group(force_download=False)
        sent_msgs = await sender_bot.send_media_group(channel_id, media=group, request_timeout=60)
    except TelegramBadRequest as e:
        if _is_chat_not_found_or_forbidden(e):
            bot_key = _get_bot_key(sender_bot)
            _BOT_INACCESSIBLE_CHANNELS.add((bot_key, channel_id))
            logger.warning(f"⚠️ [Archive] Bot {bot_key} cannot access channel {channel_id} on media group ({e}).")
            return None, []
        logger.warning(f"⚠️ TelegramBadRequest on media group ({e}). Forcing download fallback...")
        try:
            group = await _build_group(force_download=True)
            sent_msgs = await sender_bot.send_media_group(channel_id, media=group, request_timeout=60)
        except TelegramRetryAfter:
            raise
        except Exception as ex:
            if _is_chat_not_found_or_forbidden(ex):
                bot_key = _get_bot_key(sender_bot)
                _BOT_INACCESSIBLE_CHANNELS.add((bot_key, channel_id))
                logger.warning(f"⚠️ [Archive] Bot {bot_key} cannot access channel {channel_id} on media group fallback ({ex}).")
                return None, []
            logger.error(f"❌ Media group fallback failed: {ex}. Sending as text...")
            msg = await _send_text_fallback()
            return msg, []
    except TelegramForbiddenError as e:
        bot_key = _get_bot_key(sender_bot)
        _BOT_INACCESSIBLE_CHANNELS.add((bot_key, channel_id))
        logger.warning(f"⚠️ [Archive] Bot {bot_key} forbidden on media group for channel {channel_id} ({e}).")
        return None, []
    except TelegramRetryAfter:
        raise
    except (TelegramNetworkError, asyncio.TimeoutError) as net_err:
        logger.warning(f"⚠️ Archive media group timeout to channel {channel_id}: {net_err}. Sending text fallback...")
        msg = await _send_text_fallback()
        return msg, []
    except Exception as e:
        if _is_chat_not_found_or_forbidden(e):
            bot_key = _get_bot_key(sender_bot)
            _BOT_INACCESSIBLE_CHANNELS.add((bot_key, channel_id))
            logger.warning(f"⚠️ [Archive] Bot {bot_key} cannot access channel {channel_id} ({e}).")
            return None, []
        logger.error(f"⚠️ Failed to send archive media group to channel {channel_id}: {e}")
        msg = await _send_text_fallback()
        return msg, []

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
    if not orig_fid and not content.get('voice_bytes') and not content.get('image_bytes'):
        return None, []
    raw_cap = content.get('caption', '')
    converted_cap = convert_site_tags_to_telegram(raw_cap)
    raw_full_cap = f"{header_text}\n\n{sanitize_html(converted_cap)}".strip()
    caption = prepare_telegram_text(raw_full_cap, max_len=1024)
    ct_str = str(content_type).split('.')[-1].lower()
    common_args = {"chat_id": channel_id, "caption": caption, "parse_mode": "HTML", "request_timeout": 60}
    
    media_source = await _resolve_media_source(sender_bot, orig_fid, content)
    if not media_source:
        if content.get('voice_bytes'):
            media_source = BufferedInputFile(content['voice_bytes'], filename="cyberchad_roast.ogg")
        elif content.get('image_bytes'):
            media_source = BufferedInputFile(content['image_bytes'], filename="image.jpg")
    if not media_source:
        return None, []

    async def _do_send(src):
        if ct_str == 'photo': return await sender_bot.send_photo(photo=src, **common_args)
        elif ct_str == 'video': return await sender_bot.send_video(video=src, **common_args)
        elif ct_str == 'animation': return await sender_bot.send_animation(animation=src, **common_args)
        elif ct_str == 'document': return await sender_bot.send_document(document=src, **common_args)
        elif ct_str == 'audio': return await sender_bot.send_audio(audio=src, **common_args)
        elif ct_str == 'voice': return await sender_bot.send_voice(voice=src, **common_args)
        elif ct_str == 'sticker':
            await sender_bot.send_sticker(channel_id, sticker=src, request_timeout=60)
            return await sender_bot.send_message(channel_id, prepare_telegram_text(header_text, max_len=4096), parse_mode="HTML", request_timeout=30)
        elif ct_str == 'video_note':
            await sender_bot.send_video_note(channel_id, video_note=src, request_timeout=60)
            return await sender_bot.send_message(channel_id, prepare_telegram_text(header_text, max_len=4096), parse_mode="HTML", request_timeout=30)
        return None

    async def _send_single_text_fallback():
        safe_msg = prepare_telegram_text(raw_full_cap if raw_full_cap else caption, max_len=4096)
        try:
            return await sender_bot.send_message(channel_id, safe_msg, parse_mode="HTML", request_timeout=30)
        except TelegramBadRequest as tbe:
            logger.warning(f"Single media text fallback HTML error ({tbe}), trying plain text...")
            plain_txt = clean_html_tags(raw_full_cap if raw_full_cap else caption)[:4090]
            try:
                return await sender_bot.send_message(channel_id, plain_txt, parse_mode=None, request_timeout=30)
            except Exception:
                return None
        except Exception:
            return None

    sent_message = None
    try:
        sent_message = await _do_send(media_source)
    except TelegramBadRequest as e:
        if _is_chat_not_found_or_forbidden(e):
            bot_key = _get_bot_key(sender_bot)
            _BOT_INACCESSIBLE_CHANNELS.add((bot_key, channel_id))
            logger.warning(f"⚠️ [Archive] Bot {bot_key} cannot access channel {channel_id} ({e}).")
            return None, []
        err_str = str(e).lower()
        if "can't parse entities" in err_str or "find end tag" in err_str:
            common_args["parse_mode"] = None
            common_args["caption"] = clean_html_tags(caption)
            try:
                sent_message = await _do_send(media_source)
            except Exception:
                pass
        if not sent_message:
            logger.warning(f"⚠️ TelegramBadRequest sending {ct_str} ({e}). Downloading file buffer fallback...")
            file_bytes, filename = (await _download_media_bytes(orig_fid)) if orig_fid else (None, "")
            if file_bytes:
                try:
                    sent_message = await _do_send(BufferedInputFile(file_bytes, filename=filename))
                except TelegramBadRequest as be:
                    if _is_chat_not_found_or_forbidden(be):
                        bot_key = _get_bot_key(sender_bot)
                        _BOT_INACCESSIBLE_CHANNELS.add((bot_key, channel_id))
                        logger.warning(f"⚠️ [Archive] Bot {bot_key} cannot access channel {channel_id} on buffer send ({be}).")
                        return None, []
                    b_err_str = str(be).lower()
                    if "can't parse entities" in b_err_str or "find end tag" in b_err_str:
                        common_args["parse_mode"] = None
                        common_args["caption"] = clean_html_tags(caption)
                        sent_message = await _do_send(BufferedInputFile(file_bytes, filename=filename))
                    else:
                        raise
                except TelegramRetryAfter:
                    raise
                except Exception as ex:
                    if _is_chat_not_found_or_forbidden(ex):
                        bot_key = _get_bot_key(sender_bot)
                        _BOT_INACCESSIBLE_CHANNELS.add((bot_key, channel_id))
                        return None, []
                    logger.warning(f"Single media fallback failed for {orig_fid}: {ex}")
                    msg = await _send_single_text_fallback()
                    return msg, []
            else:
                msg = await _send_single_text_fallback()
                return msg, []
    except TelegramForbiddenError as e:
        bot_key = _get_bot_key(sender_bot)
        _BOT_INACCESSIBLE_CHANNELS.add((bot_key, channel_id))
        logger.warning(f"⚠️ [Archive] Bot {bot_key} forbidden on single media for channel {channel_id} ({e}).")
        return None, []
    except TelegramRetryAfter:
        raise
    except (TelegramNetworkError, asyncio.TimeoutError) as net_err:
        logger.warning(f"⚠️ Single archive media timeout to {channel_id}: {net_err}. Sending text fallback...")
        msg = await _send_single_text_fallback()
        return msg, []
    except Exception as e:
        if _is_chat_not_found_or_forbidden(e):
            bot_key = _get_bot_key(sender_bot)
            _BOT_INACCESSIBLE_CHANNELS.add((bot_key, channel_id))
            logger.warning(f"⚠️ [Archive] Bot {bot_key} cannot access channel {channel_id} ({e}).")
            return None, []
        logger.warning(f"⚠️ Failed to send single archive media ({ct_str}) to channel {channel_id}: {e}")
        msg = await _send_single_text_fallback()
        return msg, []

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
            if orig_fid:
                await add_file_mirror(orig_fid, 'tg_shadow', fid)
    return sent_message, new_files_data

async def _send_archive_media(sender_bot, channel_id: int, content: dict, content_type: str, text_to_send: str, header_text: str):
    bot_key = _get_bot_key(sender_bot)
    if (bot_key, channel_id) in _BOT_INACCESSIBLE_CHANNELS:
        return None, []

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
                if sent_message is None and not new_files_data and (bot_key, channel_id) not in _BOT_INACCESSIBLE_CHANNELS:
                    sent_message, new_files_data = await _send_archive_single_media(sender_bot, channel_id, content, content_type, header_text)
            elif has_media:
                sent_message, new_files_data = await _send_archive_single_media(sender_bot, channel_id, content, content_type, header_text)
                if sent_message is None and not new_files_data and (bot_key, channel_id) not in _BOT_INACCESSIBLE_CHANNELS:
                    try:
                        safe_to_send = prepare_telegram_text(text_to_send, max_len=4096)
                        sent_message = await sender_bot.send_message(
                            chat_id=channel_id,
                            text=safe_to_send,
                            parse_mode="HTML",
                            disable_web_page_preview=True,
                            request_timeout=30
                        )
                    except Exception:
                        pass
            else:
                try:
                    safe_to_send = prepare_telegram_text(text_to_send, max_len=4096)
                    sent_message = await sender_bot.send_message(
                        chat_id=channel_id,
                        text=safe_to_send,
                        parse_mode="HTML",
                        disable_web_page_preview=True,
                        request_timeout=30
                    )
                except TelegramBadRequest as parse_err:
                    if _is_chat_not_found_or_forbidden(parse_err):
                        _BOT_INACCESSIBLE_CHANNELS.add((bot_key, channel_id))
                        return None, []
                    err_msg = str(parse_err).lower()
                    if "can't parse entities" in err_msg or "find end tag" in err_msg or "tag" in err_msg or "too long" in err_msg:
                        logger.warning(f"Archive text HTML rejected for {channel_id}, falling back to plain text: {parse_err}")
                        plain_txt = clean_html_tags(text_to_send)
                        if len(plain_txt) > 4096:
                            plain_txt = plain_txt[:4090] + "..."
                        sent_message = await sender_bot.send_message(
                            chat_id=channel_id,
                            text=plain_txt,
                            parse_mode=None,
                            disable_web_page_preview=True,
                            request_timeout=30
                        )
                    else:
                        raise
            return sent_message, new_files_data
        except (TelegramNetworkError, asyncio.TimeoutError, aiohttp.ClientError):
            if attempt < 2: await asyncio.sleep(2)
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after + 1)
        except TelegramForbiddenError as e:
            _BOT_INACCESSIBLE_CHANNELS.add((bot_key, channel_id))
            logger.warning(f"⚠️ [Archive] Bot {bot_key} forbidden on channel {channel_id}: {e}.")
            break
        except TelegramBadRequest as e:
            if _is_chat_not_found_or_forbidden(e):
                _BOT_INACCESSIBLE_CHANNELS.add((bot_key, channel_id))
                logger.warning(f"⚠️ [Archive] Bot {bot_key} cannot access channel {channel_id} ({e}).")
                break
            err_msg = str(e).lower()
            if "can't parse entities" in err_msg or "find end tag" in err_msg or "tag" in err_msg or "too long" in err_msg:
                try:
                    plain_text = clean_html_tags(text_to_send or "")
                    if len(plain_text) > 4096:
                        plain_text = plain_text[:4090] + "..."
                    sent_message = await sender_bot.send_message(
                        chat_id=channel_id,
                        text=plain_text,
                        parse_mode=None,
                        disable_web_page_preview=True,
                        request_timeout=30
                    )
                    return sent_message, new_files_data
                except Exception as ex2:
                    if _is_chat_not_found_or_forbidden(ex2):
                        _BOT_INACCESSIBLE_CHANNELS.add((bot_key, channel_id))
                        break
            logger.warning(f"Archive TelegramBadRequest ({channel_id}): {e}")
            break
        except Exception as e:
            if _is_chat_not_found_or_forbidden(e):
                _BOT_INACCESSIBLE_CHANNELS.add((bot_key, channel_id))
                logger.warning(f"⚠️ [Archive] Bot {bot_key} cannot access channel {channel_id} ({e}).")
                break
            logger.warning(f"Archive media sending error on attempt {attempt}: {e}")
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

    final_text = f"{header_text}\n\n{text_content}".strip()
    return prepare_telegram_text(final_text, max_len=4096)

async def _update_archive_post_content(post_num: int, content: dict, content_type: str, new_files_data: list, sender_bot_id: int):
    from common.database import register_file_owner, update_post_content
    new_content = content.copy()
    new_content.pop('voice_bytes', None)
    new_content.pop('image_bytes', None)
    if content_type == 'media_group':
        new_content['media'] = new_files_data
        for f_info in new_files_data:
            await register_file_owner(f_info['file_id'], sender_bot_id)
    else:
        new_content['file_id'] = new_files_data[0]
        await register_file_owner(new_files_data[0], sender_bot_id)
    await update_post_content(post_num, new_content)

async def post_archive_to_channel(bots: dict[str, Bot], file_path: str, board_id: str, thread_info: dict) -> None:
    if not ARCHIVE_CHANNEL_ID or ARCHIVE_CHANNEL_ID == 0:
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except OSError:
            pass
        return

    g_bots = getattr(shared_state, 'GLOBAL_BOTS', {}) or {}
    candidate_bots = []
    if bots:
        if bots.get(shared_state.ARCHIVE_POSTING_BOT_ID):
            candidate_bots.append(bots[shared_state.ARCHIVE_POSTING_BOT_ID])
        if bots.get('b') and bots['b'] not in candidate_bots:
            candidate_bots.append(bots['b'])
        if bots.get(board_id) and bots[board_id] not in candidate_bots:
            candidate_bots.append(bots[board_id])
        for b in bots.values():
            if b not in candidate_bots:
                candidate_bots.append(b)
    if g_bots:
        if g_bots.get(shared_state.ARCHIVE_POSTING_BOT_ID) and g_bots[shared_state.ARCHIVE_POSTING_BOT_ID] not in candidate_bots:
            candidate_bots.append(g_bots[shared_state.ARCHIVE_POSTING_BOT_ID])
        if g_bots.get('b') and g_bots['b'] not in candidate_bots:
            candidate_bots.append(g_bots['b'])
        for b in g_bots.values():
            if b not in candidate_bots:
                candidate_bots.append(b)

    if not candidate_bots:
        print(f"⛔ Ошибка: бот для постинга архивов не найден в списке активных ботов.")
        try:
            if os.path.exists(file_path):
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
        sent = False
        for bot_instance in candidate_bots:
            bot_key = _get_bot_key(bot_instance)
            if (bot_key, ARCHIVE_CHANNEL_ID) in _BOT_INACCESSIBLE_CHANNELS:
                continue
            try:
                document = FSInputFile(file_path)
                await bot_instance.send_document(
                    chat_id=ARCHIVE_CHANNEL_ID,
                    document=document,
                    caption=caption,
                    parse_mode="HTML",
                    request_timeout=60
                )
                sent = True
                print(f"✅ Архив треда '{title}' отправлен в канал {ARCHIVE_CHANNEL_ID}.")
                break
            except Exception as e:
                if _is_chat_not_found_or_forbidden(e):
                    _BOT_INACCESSIBLE_CHANNELS.add((bot_key, ARCHIVE_CHANNEL_ID))
                    logger.warning(f"⚠️ [Archive] Bot {bot_key} cannot send thread archive to channel {ARCHIVE_CHANNEL_ID}: {e}")
                else:
                    logger.warning(f"⚠️ Failed to send archive with bot {bot_key}: {e}")
        if not sent:
            print(f"⛔ Не удалось отправить архив треда '{title}' в канал {ARCHIVE_CHANNEL_ID} всеми доступными ботами.")
    except Exception as e:
        print(f"⛔ Критическая ошибка при отправке архива треда в канал: {e}")
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
    async with shared_state.storage_lock:
        post_nums = thread_info.get('posts', [])
        for post_num in post_nums:
            post_data = shared_state.messages_storage.get(post_num)
            if post_data:
                data_copy = {
                    'content': post_data.get('content', {}).copy(),
                    'timestamp': post_data.get('timestamp', datetime.now(timezone.utc)).isoformat()
                }
                posts_data_copy.append(data_copy)
    loop = asyncio.get_running_loop()
    filepath = await loop.run_in_executor(
        shared_state.save_executor,
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

def _site_public_url(path: str | None) -> str | None:
    """Convert a relative site file path like /files/... to a full public URL."""
    if not path:
        return None
    url = str(path).strip()
    if not url:
        return None
    if url.startswith(("http://", "https://")):
        return url
    from common.config import SITE_PUBLIC_BASE_URL
    return SITE_PUBLIC_BASE_URL + url if url.startswith("/") else SITE_PUBLIC_BASE_URL + "/" + url


def _site_file_source(file_info: dict, prefer_url: bool = False) -> str | None:
    file_id = file_info.get("original_file_id") or file_info.get("file_id") or file_info.get("media")
    if isinstance(file_id, str) and file_id.startswith("shadowbanned"):
        file_id = None
    public_url = _site_public_url(file_info.get("original_url") or file_info.get("thumbnail_url"))
    source = public_url if prefer_url else file_id
    if not source:
        source = file_id or public_url
    return str(source) if source else None


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
    Отправляет уведомление о "счастливом" посте (гет/квадрипл/пентипл и т.д.) в канал архивов/новостей.
    Надежно обрабатывает все типы медиа, экранирует HTML и сохраняет связку копии в БД.
    """
    if not ARCHIVE_CHANNEL_ID or ARCHIVE_CHANNEL_ID == 0 or ARCHIVE_CHANNEL_ID in _INACCESSIBLE_CHANNELS:
        return
    try:
        g_bots = getattr(shared_state, 'GLOBAL_BOTS', {}) or {}
        candidate_bots = []
        if bots:
            if board_id in AUTHORIZED_ARCHIVE_BOTS and bots.get(board_id):
                candidate_bots.append(bots[board_id])
            if bots.get(ARCHIVE_POSTING_BOT_ID) and bots[ARCHIVE_POSTING_BOT_ID] not in candidate_bots:
                candidate_bots.append(bots[ARCHIVE_POSTING_BOT_ID])
            if bots.get('b') and bots['b'] not in candidate_bots:
                candidate_bots.append(bots['b'])
            for b in bots.values():
                if b not in candidate_bots:
                    candidate_bots.append(b)
        if g_bots:
            if board_id in AUTHORIZED_ARCHIVE_BOTS and g_bots.get(board_id) and g_bots[board_id] not in candidate_bots:
                candidate_bots.append(g_bots[board_id])
            if g_bots.get(ARCHIVE_POSTING_BOT_ID) and g_bots[ARCHIVE_POSTING_BOT_ID] not in candidate_bots:
                candidate_bots.append(g_bots[ARCHIVE_POSTING_BOT_ID])
            if g_bots.get('b') and g_bots['b'] not in candidate_bots:
                candidate_bots.append(g_bots['b'])
            for b in g_bots.values():
                if b not in candidate_bots:
                    candidate_bots.append(b)

        if not candidate_bots:
            print(f"⛔ Ошибка [post_special_num_to_channel]: боты для постинга в канал архивов не найдены для поста #{post_num}.")
            return

        config = SPECIAL_NUMERALS_CONFIG.get(level, {'label': 'Get', 'emojis': ('🎯',)})
        emoji = random.choice(config['emojis'])
        label = config['label'].upper()
        board_name = BOARD_CONFIG.get(board_id, {}).get('name', board_id)

        header = f"{emoji} <b>{label} #{post_num}</b> {emoji}\n\n<b>Доска:</b> {board_name}\n"
        text_content = content.get('text') or content.get('caption') or ''
        safe_text = sanitize_html(text_content) if text_content else ''

        caption_text = f"{header}\n{safe_text}".strip() if safe_text else header.strip()
        content_type_str = str(content.get("type", "")).split('.')[-1].lower()

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

        final_caption = prepare_telegram_text(caption_text, max_len=1024)
        final_text_for_message = prepare_telegram_text(caption_text, max_len=4096)

        sent_msg = None
        for archive_bot in candidate_bots:
            bot_key = _get_bot_key(archive_bot)
            if (bot_key, ARCHIVE_CHANNEL_ID) in _BOT_INACCESSIBLE_CHANNELS:
                continue
            for attempt in range(3):
                try:
                    if content_type_str == 'photo' and file_id:
                        sent_msg = await archive_bot.send_photo(ARCHIVE_CHANNEL_ID, file_id, caption=final_caption, parse_mode="HTML")
                    elif content_type_str == 'video' and file_id:
                        sent_msg = await archive_bot.send_video(ARCHIVE_CHANNEL_ID, file_id, caption=final_caption, parse_mode="HTML")
                    elif content_type_str == 'animation' and file_id:
                        sent_msg = await archive_bot.send_animation(ARCHIVE_CHANNEL_ID, file_id, caption=final_caption, parse_mode="HTML")
                    elif content_type_str == 'document' and file_id:
                        sent_msg = await archive_bot.send_document(ARCHIVE_CHANNEL_ID, file_id, caption=final_caption, parse_mode="HTML")
                    elif content_type_str == 'audio' and file_id:
                        sent_msg = await archive_bot.send_audio(ARCHIVE_CHANNEL_ID, file_id, caption=final_caption, parse_mode="HTML")
                    elif content_type_str == 'voice' and file_id:
                        await archive_bot.send_voice(ARCHIVE_CHANNEL_ID, file_id)
                        sent_msg = await archive_bot.send_message(ARCHIVE_CHANNEL_ID, final_caption, parse_mode="HTML", disable_web_page_preview=True)
                    elif content_type_str == 'sticker' and file_id:
                        await archive_bot.send_sticker(ARCHIVE_CHANNEL_ID, file_id)
                        sent_msg = await archive_bot.send_message(ARCHIVE_CHANNEL_ID, final_caption, parse_mode="HTML", disable_web_page_preview=True)
                    elif content_type_str == 'video_note' and file_id:
                        await archive_bot.send_video_note(ARCHIVE_CHANNEL_ID, file_id)
                        sent_msg = await archive_bot.send_message(ARCHIVE_CHANNEL_ID, final_caption, parse_mode="HTML", disable_web_page_preview=True)
                    else:
                        sent_msg = await archive_bot.send_message(ARCHIVE_CHANNEL_ID, final_text_for_message, parse_mode="HTML", disable_web_page_preview=True)

                    if sent_msg:
                        try:
                            from common.database import add_channel_copy
                            await add_channel_copy(post_num, ARCHIVE_CHANNEL_ID, sent_msg.message_id)
                        except Exception:
                            pass
                        print(f"✅ Уведомление о счастливом посте #{post_num} ({label}) отправлено в канал.")
                        return

                except (TelegramForbiddenError, TelegramBadRequest) as e:
                    if _is_chat_not_found_or_forbidden(e):
                        _BOT_INACCESSIBLE_CHANNELS.add((bot_key, ARCHIVE_CHANNEL_ID))
                        break
                    err_msg = str(e).lower()
                    if "can't parse entities" in err_msg or "find end tag" in err_msg or "tag" in err_msg:
                        try:
                            plain_txt = clean_html_tags(caption_text)
                            if len(plain_txt) > 4096:
                                plain_txt = plain_txt[:4090] + "..."
                            sent_msg = await archive_bot.send_message(ARCHIVE_CHANNEL_ID, plain_txt, parse_mode=None, disable_web_page_preview=True)
                            if sent_msg:
                                try:
                                    from common.database import add_channel_copy
                                    await add_channel_copy(post_num, ARCHIVE_CHANNEL_ID, sent_msg.message_id)
                                except Exception:
                                    pass
                                return
                        except Exception as ex_text:
                            if _is_chat_not_found_or_forbidden(ex_text):
                                _BOT_INACCESSIBLE_CHANNELS.add((bot_key, ARCHIVE_CHANNEL_ID))
                                break
                    break
                except TelegramRetryAfter as e:
                    await asyncio.sleep(e.retry_after + 1)
                except (TelegramNetworkError, asyncio.TimeoutError, aiohttp.ClientError):
                    if attempt < 2:
                        await asyncio.sleep(1.0)
                except Exception as e:
                    if _is_chat_not_found_or_forbidden(e):
                        _BOT_INACCESSIBLE_CHANNELS.add((bot_key, ARCHIVE_CHANNEL_ID))
                        break
                    logger.warning(f"Happy post #{post_num} attempt error: {e}")
                    break
    except Exception as e:
        import traceback
        print(f"⛔ Не удалось отправить счастливый пост #{post_num} в канал: {e}\n{traceback.format_exc()}")

async def _forward_post_to_realtime_archive(bot_instance: Bot, board_id: str, post_num: int, content: dict, is_shadow_muted: bool, stream: str = 'ru'):
    if is_shadow_muted:
        return
    from common.database import get_post_by_num

    check_post = await get_post_by_num(post_num)
    if not check_post:
        async with storage_lock:
            if post_num not in messages_storage:
                return

    g_bots = getattr(shared_state, 'GLOBAL_BOTS', {}) or {}
    archive_bot = g_bots.get(ARCHIVE_POSTING_BOT_ID) or g_bots.get('b')
    primary_bot = bot_instance if (board_id in AUTHORIZED_ARCHIVE_BOTS and bot_instance) else (archive_bot or bot_instance or g_bots.get('b'))

    all_bots = []
    for b in [primary_bot, archive_bot, g_bots.get('b'), bot_instance] + list(g_bots.values()):
        if b and b not in all_bots:
            all_bots.append(b)

    if not all_bots:
        logger.warning(f"⚠️ [Archive] Нет доступных ботов для отправки поста #{post_num} в архив.")
        return

    sender_bot_id = getattr(all_bots[0], 'id', 0)
    lang = 'en' if board_id == 'int' else 'ru'

    header_text = _build_archive_header(board_id, post_num, content, lang)
    content_type = content.get("type", "text")
    text_to_send = _format_archive_text_content(content, header_text) or header_text

    db_updated = False
    for channel_id in MIRROR_CHANNELS:
        if not channel_id or channel_id == 0 or channel_id in _INACCESSIBLE_CHANNELS:
            continue
        try:
            from common.database import get_pool
            db = await get_pool()
            async with db.execute("SELECT 1 FROM ChannelCopies WHERE post_num = ? AND channel_id = ? LIMIT 1", (post_num, channel_id)) as cur:
                if await cur.fetchone():
                    continue
        except Exception:
            pass

        sent_message = None
        new_files_data = []
        for try_bot in all_bots:
            bot_key = _get_bot_key(try_bot)
            if (bot_key, channel_id) in _BOT_INACCESSIBLE_CHANNELS:
                continue
            sent_message, new_files_data = await _send_archive_media(try_bot, channel_id, content, content_type, text_to_send, header_text)
            if sent_message is not None:
                sender_bot_id = getattr(try_bot, 'id', sender_bot_id)
                break

        if sent_message:
            try:
                await add_channel_copy(post_num, channel_id, sent_message.message_id)
                if not db_updated and new_files_data:
                    await _update_archive_post_content(post_num, content, content_type, new_files_data, sender_bot_id)
                    db_updated = True
            except Exception:
                pass
        else:
            logger.warning(f"⚠️ [Archive] Пост #{post_num} не удалось доставить в канал {channel_id} — все боты ({len(all_bots)}) недоступны или не имеют доступа.")

