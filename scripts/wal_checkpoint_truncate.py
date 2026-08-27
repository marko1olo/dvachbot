#!/usr/bin/env python3
"""
Utility script to safely checkpoint and truncate SQLite WAL file (dvach_bot.db-wal)
and optionally optimize the database storage.
"""

import os
import sys
import sqlite3
import logging
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("wal_optimizer")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "dvach_bot.db"
WAL_PATH = PROJECT_ROOT / "dvach_bot.db-wal"
SHM_PATH = PROJECT_ROOT / "dvach_bot.db-shm"

def get_file_size_str(p: Path) -> str:
    if not p.exists():
        return "0 B (not present)"
    size = p.stat().st_size
    if size < 1024:
        return f"{size:,} B"
    elif size < 1024 * 1024:
        return f"{size:,} B ({size / 1024:.2f} KB)"
    else:
        return f"{size:,} B ({size / (1024 * 1024):.2f} MB)"

def report_sizes(prefix: str = ""):
    logger.info(f"--- File Sizes {prefix} ---")
    logger.info(f"DB:  {DB_PATH.name} -> {get_file_size_str(DB_PATH)}")
    logger.info(f"WAL: {WAL_PATH.name} -> {get_file_size_str(WAL_PATH)}")
    logger.info(f"SHM: {SHM_PATH.name} -> {get_file_size_str(SHM_PATH)}")

def checkpoint_and_truncate(vacuum: bool = False):
    if not DB_PATH.exists():
        logger.error(f"Database file not found at {DB_PATH}")
        sys.exit(1)

    report_sizes("BEFORE")

    logger.info(f"Connecting to {DB_PATH} with timeout=60s...")
    conn = sqlite3.connect(str(DB_PATH), timeout=60.0)
    try:
        cur = conn.cursor()
        
        # Verify journal mode
        cur.execute("PRAGMA journal_mode;")
        jmode = cur.fetchone()[0]
        logger.info(f"Current journal_mode: {jmode}")

        # Check integrity quick check
        logger.info("Running quick integrity check...")
        cur.execute("PRAGMA quick_check;")
        quick_check_res = cur.fetchall()
        logger.info(f"Quick check result: {quick_check_res}")

        # Execute PRAGMA wal_checkpoint(TRUNCATE)
        logger.info("Executing PRAGMA wal_checkpoint(TRUNCATE)...")
        cur.execute("PRAGMA wal_checkpoint(TRUNCATE);")
        res = cur.fetchone()
        if res:
            busy, log_frames, ckpt_frames = res
            logger.info(f"wal_checkpoint(TRUNCATE) result: busy={busy}, log_frames={log_frames}, checkpointed_frames={ckpt_frames}")
            if busy != 0:
                logger.warning("⚠️ Warning: checkpoint busy flag != 0, another connection might be holding read locks.")

        if vacuum:
            logger.info("Executing VACUUM to reclaim unused pages in main DB...")
            cur.execute("VACUUM;")
            logger.info("VACUUM completed successfully.")

            # Truncate WAL again after VACUUM if needed
            cur.execute("PRAGMA wal_checkpoint(TRUNCATE);")
            logger.info("Post-VACUUM wal_checkpoint(TRUNCATE) executed.")

    finally:
        conn.close()
        logger.info("Connection closed.")

    report_sizes("AFTER")

if __name__ == "__main__":
    do_vacuum = "--vacuum" in sys.argv
    checkpoint_and_truncate(vacuum=do_vacuum)
