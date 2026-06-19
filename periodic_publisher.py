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

async def build_stats_media_group():
    """Generates the stats and builds an aiogram MediaGroup."""
    # Run the synchronous matplotlib generator in a separate thread
    images = await asyncio.to_thread(generate_all_charts)
    
    if not images:
        return None
        
    media_group = []
    
    # First image gets the caption
    caption = (
        "📊 <b>Статистика Борды</b> 📊\n\n"
        "Свежая аналитика из глубин базы данных. "
        "Активность, репрессии, токсичность и многое другое.\n"
        "Смотри графики в альбоме 👇"
    )
    
    for i, (name, buf) in enumerate(images):
        # Aiogram 3 uses BufferedInputFile
        input_file = BufferedInputFile(buf.read(), filename=name)
        if i == 0:
            media_group.append(InputMediaPhoto(media=input_file, caption=caption, parse_mode="HTML"))
        else:
            media_group.append(InputMediaPhoto(media=input_file))
            
    return media_group

async def send_stats_to_user(bot: Bot, chat_id: int):
    """Generates and sends stats directly to a user/admin."""
    await bot.send_message(chat_id, "⏳ <i>Генерирую 10 графиков статистики (это может занять пару секунд)...</i>", parse_mode="HTML")
    try:
        media_group = await build_stats_media_group()
        if media_group:
            await bot.send_media_group(chat_id=chat_id, media=media_group)
        else:
            await bot.send_message(chat_id, "❌ Не удалось собрать данные для статистики.")
    except Exception as e:
        print(f"Error sending stats: {e}")
        await bot.send_message(chat_id, f"❌ Ошибка при генерации статистики: {e}")

async def periodic_stats_publisher(bot: Bot):
    """
    Runs in the background and publishes stats every Sunday at 20:00 MSK.
    """
    while True:
        now_utc = datetime.now(timezone.utc)
        now_msk = now_utc.astimezone(MSK_OFFSET)
        
        # Target: Sunday (weekday == 6), 20:00:00
        # Check if we need to schedule for next week or later today
        days_ahead = 6 - now_msk.weekday()
        if days_ahead < 0 or (days_ahead == 0 and now_msk.hour >= 20):
            days_ahead += 7
            
        target_date = now_msk + timedelta(days=days_ahead)
        target_time = target_date.replace(hour=20, minute=0, second=0, microsecond=0)
        
        sleep_seconds = (target_time - now_msk).total_seconds()
        
        print(f"📊 [STATS PUBLISHER] Следующая публикация статистики запланирована на {target_time.strftime('%Y-%m-%d %H:%M:%S')} MSK (через {sleep_seconds/3600:.1f} часов)")
        
        await asyncio.sleep(sleep_seconds)
        
        # Wake up and publish
        if NEWS_CHANNEL_ID:
            print(f"📊 [STATS PUBLISHER] Генерирую еженедельную статистику для {NEWS_CHANNEL_ID}...")
            try:
                media_group = await build_stats_media_group()
                if media_group:
                    await bot.send_media_group(chat_id=NEWS_CHANNEL_ID, media=media_group)
                    print(f"✅ [STATS PUBLISHER] Успешно опубликовано!")
                else:
                    print("❌ [STATS PUBLISHER] Ошибка: нет данных для графиков.")
            except Exception as e:
                print(f"❌ [STATS PUBLISHER] Ошибка при публикации: {e}")
        else:
            print("⚠️ [STATS PUBLISHER] Канал для новостей не задан (NEWS_CHANNEL_ID is None). Пропускаем публикацию.")
            
        # Sleep an extra hour to avoid double-triggering
        await asyncio.sleep(3600)
