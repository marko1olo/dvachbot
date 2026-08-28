import asyncio
import sqlite3
import json
import os
import sys
import logging
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramRetryAfter, TelegramBadRequest

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'C:\Users\danat\Desktop\dvachbot')

from common.board_config import BOARD_CONFIG
from shared_state import MIRROR_CHANNELS, AUTHORIZED_ARCHIVE_BOTS, ARCHIVE_POSTING_BOT_ID
import archive_manager

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

async def run_archive_backfill(start_post_num: int = 492000, max_posts: int = 1000):
    print(f"=== Starting Archive Backfill (from #{start_post_num}, max={max_posts}) ===")
    
    # 1. Initialize bots
    bots = {}
    default_props = DefaultBotProperties(parse_mode="HTML")
    for bid, conf in BOARD_CONFIG.items():
        tok = conf.get("token")
        if tok:
            bots[bid] = Bot(token=tok, default=default_props)
    
    # Setup archive_manager.GLOBAL_BOTS
    archive_manager.GLOBAL_BOTS = bots
    bot_b = bots.get('b')
    
    conn = sqlite3.connect(r'C:\Users\danat\Desktop\dvachbot\dvach_bot.db')
    c = conn.cursor()

    primary_channel = MIRROR_CHANNELS[0]

    c.execute("""
        SELECT p.post_num, p.board_id, p.content, p.is_shadow, p.is_shadow_reject
        FROM Posts p
        LEFT JOIN ChannelCopies cc ON p.post_num = cc.post_num AND cc.channel_id = ?
        WHERE cc.post_num IS NULL
          AND p.post_num >= ?
          AND (p.is_shadow IS NULL OR p.is_shadow = 0)
          AND (p.is_shadow_reject IS NULL OR p.is_shadow_reject = 0)
        ORDER BY p.post_num ASC
        LIMIT ?
    """, (primary_channel, start_post_num, max_posts))

    missing_posts = c.fetchall()
    total = len(missing_posts)
    print(f"Found {total} unarchived posts to backfill.")

    if total == 0:
        print("Nothing to backfill. All posts are already in archive!")
        for b in bots.values(): await b.session.close()
        conn.close()
        return

    success_count = 0
    fail_count = 0

    for idx, row in enumerate(missing_posts, 1):
        pnum, bid, cnt_str, is_sh, is_sr = row
        try:
            content = json.loads(cnt_str) if cnt_str else {}
        except Exception:
            content = {}

        if content.get('archive_skip') and not content.get('archive_allowed'):
            continue

        # Double check deduplication in DB
        c.execute("SELECT 1 FROM ChannelCopies WHERE post_num = ? AND channel_id = ?", (pnum, primary_channel))
        if c.fetchone():
            continue

        sender_bot = bots.get(bid) or bot_b or bots.get('test')
        if not sender_bot:
            print(f"[{idx}/{total}] ❌ No bot available for /{bid}/")
            fail_count += 1
            continue

        lang = 'en' if bid == 'int' else 'ru'
        header_text = archive_manager._build_archive_header(bid, pnum, content, lang)
        content_type = content.get("type", "text")
        text_to_send = archive_manager._format_archive_text_content(content, header_text) or header_text

        sent_any = False
        for ch_id in MIRROR_CHANNELS:
            if not ch_id or ch_id == 0: continue
            sent_msg = None
            try:
                sent_msg, new_files = await archive_manager._send_archive_media(
                    sender_bot, ch_id, content, content_type, text_to_send, header_text
                )
            except TelegramRetryAfter as tra:
                print(f"Rate limited, sleeping {tra.retry_after + 1}s...")
                await asyncio.sleep(tra.retry_after + 1)
                try:
                    sent_msg, new_files = await archive_manager._send_archive_media(
                        sender_bot, ch_id, content, content_type, text_to_send, header_text
                    )
                except Exception:
                    sent_msg = None
            except Exception as e:
                sent_msg = None
            
            # Fallback to main board bot 'b' if needed
            if not sent_msg and bot_b and bot_b != sender_bot:
                try:
                    sent_msg, new_files = await archive_manager._send_archive_media(
                        bot_b, ch_id, content, content_type, text_to_send, header_text
                    )
                except Exception:
                    sent_msg = None

            if sent_msg:
                sent_any = True
                try:
                    c.execute(
                        "INSERT OR IGNORE INTO ChannelCopies (post_num, channel_id, message_id) VALUES (?, ?, ?)",
                        (pnum, ch_id, sent_msg.message_id)
                    )
                    conn.commit()
                except Exception as e:
                    print(f"DB insert error: {e}")

        if sent_any:
            success_count += 1
            if idx % 10 == 0 or idx == total or content_type != 'text':
                print(f"[{idx}/{total}] ✅ Post #{pnum} [/{bid}/] ({content_type}) -> Archived!")
        else:
            fail_count += 1
            print(f"[{idx}/{total}] ⚠️ Post #{pnum} [/{bid}/] ({content_type}) -> Failed to send")

        # Pacing
        await asyncio.sleep(0.15)

    print(f"\n=== BACKFILL COMPLETE ===")
    print(f"Total processed: {total} | Successfully archived: {success_count} | Failed/Skipped: {fail_count}")

    for b in bots.values():
        await b.session.close()
    conn.close()

if __name__ == '__main__':
    start_num = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 492000
    asyncio.run(run_archive_backfill(start_post_num=start_num))
