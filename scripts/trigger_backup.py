import asyncio
import sys
import os
import logging
from dotenv import load_dotenv

# Configure logging to stdout
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout
)

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv()

from aiogram import Bot
from site_tgach.backup import create_db_backup
from common.db_pool import close_pool

async def main():
    token = os.getenv("FILE_UPLOADER_BOT_TOKEN")
    if not token:
        print("Error: FILE_UPLOADER_BOT_TOKEN is not defined in environment variables.")
        return
    
    print("Initializing bot...")
    bot = Bot(token=token)
    try:
        print("Starting manual database backup dispatch to Telegram...")
        await create_db_backup(bot)
        print("Manual backup process completed.")
    finally:
        print("Closing bot session...")
        await bot.session.close()
        print("Closing database pool...")
        await close_pool()
        print("Done.")

if __name__ == "__main__":
    asyncio.run(main())
