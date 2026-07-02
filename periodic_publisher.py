import asyncio
import io
import time
from datetime import datetime, timezone, timedelta
from aiogram import Bot, types
from aiogram.types import BufferedInputFile, InputMediaPhoto
from aiogram.exceptions import TelegramAPIError

# We will run the generator in a separate thread so it doesn't block the async loop
from stats_generator import generate_all_charts

# Channel ID where stats will be published (user can configure this later)
NEWS_CHANNEL_ID = None

MSK_OFFSET = timezone(timedelta(hours=3))

async def build_stats_media_groups():
    """Generates the stats and builds a list of aiogram MediaGroups (max 10 items each)."""
    images = await asyncio.to_thread(generate_all_charts)
    
    if not images:
        return []
        
    groups = []
    chunk_size = 10
    image_chunks = [images[i:i + chunk_size] for i in range(0, len(images), chunk_size)]
    
    for chunk_idx, chunk in enumerate(image_chunks):
        media_group = []
        if chunk_idx == 0:
            caption = (
                "📊 <b>Статистика Борды (Часть 1/2)</b> 📊\n\n"
                "Классическая аналитика из глубин базы данных: "
                "активность, уникальные шизы, байтеры и форматы общения.\n"
                "Смотри графики в альбоме 👇"
            )
        else:
            caption = (
                "🧠 <b>Продвинутая Аналитика (Часть 2/2)</b> 🧠\n\n"
                "Глубокий разбор: граф социального пузыря, хабы внимания, сессии, "
                "циркадные ритмы шизофрении, сентимент и лексический запас.\n"
                "Смотри продолжение 👇"
            )
            
        for i, (name, buf) in enumerate(chunk):
            input_file = BufferedInputFile(buf.read(), filename=name)
            if i == 0:
                media_group.append(InputMediaPhoto(media=input_file, caption=caption, parse_mode="HTML"))
            else:
                media_group.append(InputMediaPhoto(media=input_file))
        groups.append(media_group)
        
    return groups

async def send_stats_to_user(bot: Bot, chat_id: int):
    """Generates and sends stats directly to a user/admin, and copies them to the archive."""
    await bot.send_message(chat_id, "⏳ <i>Рисую 20 графиков вашей деградации (погоди пару секунд)...</i>", parse_mode="HTML")
    try:
        media_groups = await build_stats_media_groups()
        if media_groups:
            # Send to requesting user/admin
            for media_group in media_groups:
                await bot.send_media_group(chat_id=chat_id, media=media_group)
                await asyncio.sleep(1)
                
            # Send a copy to the Archive Channel if not already there
            import os
            archive_channel_id = int(os.getenv("ARCHIVE_CHANNEL_ID", -1002827087363))
            if chat_id != archive_channel_id:
                try:
                    print(f"📊 Отправляю копию графиков в архивный канал {archive_channel_id}...")
                    for media_group in media_groups:
                        for item in media_group:
                            if hasattr(item.media, 'data') and hasattr(item.media.data, 'seek'):
                                item.media.data.seek(0)
                            elif hasattr(item.media, 'seek'):
                                item.media.seek(0)
                        await bot.send_media_group(chat_id=archive_channel_id, media=media_group)
                        await asyncio.sleep(1)
                except Exception as e:
                    print(f"⚠️ Не удалось скопировать графики в архивный канал: {e}")
        else:
            await bot.send_message(chat_id, "❌ Хуй там плавал, стату собрать не вышло.")
    except Exception as e:
        print(f"Error sending stats: {e}")
        await bot.send_message(chat_id, f"❌ Ошибка при генерации статистики: {e}")

async def periodic_stats_publisher(bots: dict, active_users_getter):
    """
    Runs in the background and publishes stats every Sunday at 20:00 MSK.
    Sends to the archive channel and broadcasts to all active users on board /b/.
    """
    import os
    ARCHIVE_CHANNEL_ID = int(os.getenv("ARCHIVE_CHANNEL_ID", -1002827087363))
    
    while True:
        now_utc = datetime.now(timezone.utc)
        now_msk = now_utc.astimezone(MSK_OFFSET)
        
        # Target: Sunday (weekday == 6), 20:00:00
        days_ahead = 6 - now_msk.weekday()
        if days_ahead < 0 or (days_ahead == 0 and now_msk.hour >= 20):
            days_ahead += 7
            
        target_date = now_msk + timedelta(days=days_ahead)
        target_time = target_date.replace(hour=20, minute=0, second=0, microsecond=0)
        
        sleep_seconds = (target_time - now_msk).total_seconds()
        
        print(f"📊 [STATS PUBLISHER] Следующая публикация статистики запланирована на {target_time.strftime('%Y-%m-%d %H:%M:%S')} MSK (через {sleep_seconds/3600:.1f} часов)")
        
        await asyncio.sleep(sleep_seconds)
        
        # Wake up and publish
        print("📊 [STATS PUBLISHER] Время публикации статистики! Генерирую графики...")
        try:
            media_groups = await build_stats_media_groups()
            if media_groups:
                archive_bot = bots.get('test') or bots.get('b') or next(iter(bots.values()))
                
                # 1. Send to ARCHIVE_CHANNEL_ID (collect file_ids to avoid uploading multiple times)
                print(f"📊 [STATS PUBLISHER] Отправляю графики в архивный канал {ARCHIVE_CHANNEL_ID}...")
                uploaded_groups_file_ids = []
                for group_idx, media_group in enumerate(media_groups):
                    messages = await archive_bot.send_media_group(chat_id=ARCHIVE_CHANNEL_ID, media=media_group)
                    group_file_ids = [m.photo[-1].file_id for m in messages if m.photo]
                    uploaded_groups_file_ids.append(group_file_ids)
                    await asyncio.sleep(1)
                
                print("✅ [STATS PUBLISHER] Графики успешно отправлены в архивный канал.")
                
                # 2. Broadcast to all active users on board /b/
                active_users = active_users_getter()
                b_bot = bots.get('b') or next(iter(bots.values()))
                
                if b_bot and active_users and uploaded_groups_file_ids:
                    print(f"📊 [STATS PUBLISHER] Рассылаю графики {len(active_users)} активным пользователям /b/...")
                    
                    caption_part1 = (
                        "📊 <b>Еженедельная статистика (Часть 1/2)</b> 📊\n\n"
                        "Смотри графики в альбоме 👇"
                    )
                    caption_part2 = (
                        "🧠 <b>Еженедельная статистика (Часть 2/2)</b> 🧠\n\n"
                        "Смотри продолжение 👇"
                    )
                    
                    for user_id in active_users:
                        try:
                            for group_idx, file_ids in enumerate(uploaded_groups_file_ids):
                                user_media_group = []
                                caption = caption_part1 if group_idx == 0 else caption_part2
                                for i, file_id in enumerate(file_ids):
                                    if i == 0:
                                        user_media_group.append(InputMediaPhoto(media=file_id, caption=caption, parse_mode="HTML"))
                                    else:
                                        user_media_group.append(InputMediaPhoto(media=file_id))
                                await b_bot.send_media_group(chat_id=user_id, media=user_media_group)
                                await asyncio.sleep(0.1)
                            await asyncio.sleep(0.2)
                        except Exception as e:
                            print(f"⚠️ [STATS PUBLISHER] Ошибка отправки пользователю {user_id}: {e}")
                            
                print(f"✅ [STATS PUBLISHER] Еженедельная публикация статистики завершена!")
            else:
                print("❌ [STATS PUBLISHER] Ошибка: нет данных для графиков.")
        except Exception as e:
            print(f"❌ [STATS PUBLISHER] Ошибка при публикации: {e}")
            
        # Sleep an extra hour to avoid double-triggering
        await asyncio.sleep(3600)
