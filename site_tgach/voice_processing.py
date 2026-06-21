import asyncio
from common.task_manager import spawn_task
import hashlib
from aiogram import Bot
from aiogram.types import BufferedInputFile
from fastapi import UploadFile, HTTPException
from common.database import check_file_deduplication, register_new_file
# Импортируем нашу прокачанную функцию с "Двойным ударом"
from site_tgach.image_processing import _upload_mirrors_task

async def process_and_upload_voice(
    file: UploadFile, 
    max_size_bytes: int, 
    bot: Bot, 
    channel_id: int
) -> dict:
    """
    Загружает аудиофайл с дедупликацией и надежным зеркалированием.
    """
    file_size = 0
    if hasattr(file, 'size') and file.size:
        file_size = file.size
    else:
        await file.seek(0, 2)
        file_size = file.file.tell()
        await file.seek(0)
    
    if file_size > max_size_bytes:
        raise HTTPException(status_code=413, detail="File too large")
        
    file_content = await file.read()
    filename = file.filename or "voice.ogg"
    
    # 1. Проверка дубликатов (SHA256)
    sha256_hash = hashlib.sha256(file_content).hexdigest()
    dedup = await check_file_deduplication(sha256_hash)
    
    if dedup:
        if dedup.get("banned"):
            raise HTTPException(status_code=400, detail="Banned file")
        if dedup.get("found"):
            return {
                "type": dedup['type'],
                "original_file_id": dedup['original_file_id'],
                "thumbnail_file_id": None,
                "filename": filename,
                "sha256": sha256_hash,
                "dedup_found": True,
                "owner_bot_id": dedup.get("owner_bot_id"),
                "thumbnail_owner_bot_id": dedup.get("thumbnail_owner_bot_id"),
            }

    # 2. Загрузка в Telegram
    input_file = BufferedInputFile(file_content, filename=filename)
    result_data = {}
    
    try:
        # Попытка 1: Как голосовое (Voice)
        message = await bot.send_voice(chat_id=channel_id, voice=input_file)
        result_data = {
            'type': 'voice', 
            'original_file_id': message.voice.file_id,
            'thumbnail_file_id': None,
            'mime_type': message.voice.mime_type,
            'duration': message.voice.duration,
            'filename': filename
        }
    except Exception:
        # Попытка 2: Как документ (Document)
        input_file_fallback = BufferedInputFile(file_content, filename=filename)
        try:
            message = await bot.send_document(chat_id=channel_id, document=input_file_fallback)
            result_data = {
                'type': 'audio', 
                'original_file_id': message.document.file_id,
                'thumbnail_file_id': None,
                'mime_type': message.document.mime_type,
                'filename': filename
            }
        except Exception as e:
            print(f"⛔ VOICE UPLOAD FAILED: {e}")
            raise HTTPException(status_code=500, detail="Upload failed")

    # 3. Регистрация в БД
    try:
        await register_new_file(
            sha256_hash, 
            None, # phash для аудио не считаем
            result_data['original_file_id'], 
            None, 
            result_data['type'], 
            None
        )
    except Exception as e:
        print(f"DB Register error (Voice): {e}")

    # 4. Фоновое зеркалирование (С поддержкой больших файлов >19МБ)
    spawn_task(_upload_mirrors_task(
        bot, 
        result_data['original_file_id'], 
        file_bytes=file_content, 
        filename=filename,
        related_id=None
    ))

    return result_data
