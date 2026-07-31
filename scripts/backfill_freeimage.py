"""
Backfill FreeImage mirrors for all registered image files.
Persistent loop - runs until killed.
Usage: python scripts/backfill_freeimage.py
"""
import asyncio
import os
import sys
import sqlite3
import tempfile
import time
import httpx
import platform

sys.stdout.reconfigure(encoding='utf-8')
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from common.bot_pool import global_bot_pool
from common.database import add_file_mirror, get_file_owner_id
from site_tgach.freeimage import upload_file_to_freeimage
from site_tgach.mirror_worker import _resolve_file_bot, _find_msg_info
from site_tgach.mtproto_client import download_file_mtproto

PROXY_URL = os.getenv("PROXY_URL")
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'dvach_bot.db')
BATCH_SIZE = 20
SLEEP_BETWEEN_FILES = 1.5   # seconds between uploads to avoid rate limits
SLEEP_ON_EMPTY = 60         # seconds to sleep when no files need mirroring
MAX_FILE_MB = 32             # freeimage.host limit

SUPPORTED_TYPES = {'image', 'photo'}
SUPPORTED_EXT = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff'}


def flush_print(msg):
    print(msg, flush=True)
    sys.stdout.flush()


async def download_file_http(token, file_path_tg, dest_path):
    url = f"https://api.telegram.org/file/bot{token}/{file_path_tg}"
    try:
        transport = httpx.AsyncHTTPTransport(local_address="0.0.0.0")
        async with httpx.AsyncClient(timeout=120.0, verify=False, transport=transport) as client:
            async with client.stream("GET", url) as r:
                if r.status_code == 200:
                    with open(dest_path, 'wb') as f:
                        async for chunk in r.aiter_bytes():
                            f.write(chunk)
                    return True
    except Exception:
        pass
    return False


async def main():
    flush_print("[RUN] Starting FreeImage Backfill Script (Persistent Loop Edition)...")

    from common.bot_pool import global_bot_pool
    from common.config import BOT_TOKENS
    await global_bot_pool.init_pool(BOT_TOKENS)
    
    try:
        from common.db_pool import create_pool
        await create_pool()
    except Exception:
        pass

    while True:
        try:
            db = sqlite3.connect(DB_PATH)
            c = db.cursor()
            # Find files without freeimage mirror (only images)
            c.execute("""
                SELECT r.file_id, r.file_type 
                FROM FileRegistry r
                LEFT JOIN FileMirrors m ON r.file_id = m.file_id AND m.mirror_type = 'freeimage'
                WHERE r.file_type IN ('image', 'photo', 'animation')
                  AND m.file_id IS NULL
                LIMIT ?
            """, (BATCH_SIZE,))
            rows = c.fetchall()
            db.close()

            if not rows:
                flush_print(f"[SUCCESS] No missing mirrors for FreeImage. Sleeping for {SLEEP_ON_EMPTY} seconds...")
                await asyncio.sleep(SLEEP_ON_EMPTY)
                continue

            flush_print(f"[INFO] Found {len(rows)} files without freeimage mirrors. Starting batch processing...")
            success_count = skipped_count = failed_count = 0

            for idx, (file_id, file_type) in enumerate(rows):
                flush_print(f"\n[LOOP] [{idx+1}/{len(rows)}] Processing {file_id[:15]}... (type={file_type})")

                try:
                    owner_id = await get_file_owner_id(file_id)
                    bot, _ = _resolve_file_bot(owner_id)
                    if not bot:
                        flush_print(f"[WARN] No active bot for {file_id[:15]}. Skipping.")
                        skipped_count += 1
                        continue

                    # Get file info from Telegram
                    try:
                        file_info = await asyncio.wait_for(bot.get_file(file_id), timeout=30.0)
                    except asyncio.TimeoutError:
                        flush_print(f"[ERROR] bot.get_file timeout for {file_id[:15]}")
                        skipped_count += 1
                        continue

                    file_path_tg = getattr(file_info, 'file_path', None)
                    file_size = getattr(file_info, 'file_size', 0) or 0
                    
                    if file_size > MAX_FILE_MB * 1024 * 1024:
                        flush_print(f"[SKIP] File too large ({file_size/1024/1024:.1f} MB). Skipping.")
                        skipped_count += 1
                        continue

                    ext = '.jpg'
                    if file_path_tg:
                        _, e = os.path.splitext(file_path_tg)
                        if e.lower() in SUPPORTED_EXT:
                            ext = e.lower()

                    # Create temp file
                    fd, lpath = tempfile.mkstemp(prefix='freeimage_bf_', suffix=ext)
                    os.close(fd)

                    try:
                        downloaded = False

                        # Try MTProto first
                        msg_info = await _find_msg_info(file_id)
                        if msg_info:
                            c_id, m_id, _ = msg_info
                            flush_print(f"[INFO] Downloading via MTProto...")
                            try:
                                if await asyncio.wait_for(
                                    download_file_mtproto(bot.token, file_info.file_id, lpath, c_id, m_id),
                                    timeout=120.0
                                ):
                                    flush_print(f"[SUCCESS] MTProto download success!")
                                    downloaded = True
                            except asyncio.TimeoutError:
                                flush_print(f"[WARN] MTProto download timeout.")

                        # HTTP fallback
                        if not downloaded and file_path_tg:
                            flush_print(f"[WARN] MTProto failed/timeout. Trying HTTP Fallback...")
                            try:
                                if await asyncio.wait_for(
                                    download_file_http(bot.token, file_path_tg, lpath),
                                    timeout=120.0
                                ):
                                    flush_print(f"[SUCCESS] HTTP download success!")
                                    downloaded = True
                            except asyncio.TimeoutError:
                                flush_print(f"[WARN] HTTP download timeout.")

                        if not downloaded:
                            flush_print(f"[ERROR] All download attempts failed.")
                            failed_count += 1
                            continue

                        if os.path.getsize(lpath) == 0:
                            flush_print(f"[ERROR] Downloaded file is empty (0 bytes). Skipping.")
                            failed_count += 1
                            continue

                        # Upload to FreeImage
                        flush_print(f"[INFO] Uploading to FreeImage ({os.path.getsize(lpath)} bytes)...")
                        link = await upload_file_to_freeimage(lpath)
                        if link:
                            await add_file_mirror(file_id, 'freeimage', link)
                            flush_print(f"[SUCCESS] Mirrored to FreeImage: {link}")
                            success_count += 1
                        else:
                            flush_print(f"[ERROR] FreeImage upload failed.")
                            failed_count += 1

                        await asyncio.sleep(SLEEP_BETWEEN_FILES)

                    finally:
                        if os.path.exists(lpath):
                            try:
                                os.remove(lpath)
                            except Exception:
                                pass

                except Exception as e:
                    flush_print(f"[FATAL] Error processing {file_id[:15]}: {e}")
                    failed_count += 1

            flush_print(f"\n[BATCH FINISHED] Success: {success_count} | Skipped: {skipped_count} | Failed: {failed_count}")

        except Exception as e:
            flush_print(f"[LOOP ERROR] {e}")
            await asyncio.sleep(30)


if __name__ == '__main__':
    if platform.system() == 'Windows':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(main())
