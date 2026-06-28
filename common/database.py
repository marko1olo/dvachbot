from typing import overload
import aiosqlite
"""
This module provides an asynchronous interface for managing a SQLite database 
using aiosqlite. It includes functions for initializing the database schema, 
creating tables, and handling migrations for various entities such as Boards, 
Posts, Users, and more.
Key Features:
- Asynchronous database connection and operations.
- Creation and management of multiple tables with foreign key relationships.
- Support for JSON serialization of specific objects.
- Migration scripts to update the database schema without data loss.
- Indexing for improved query performance.
- Trigger definitions for maintaining full-text search capabilities.
Functions:
- _json_serializer(obj): Custom JSON serializer for non-serializable aiogram objects.
- initialize_database(): Initializes the database, creates tables, and applies migrations.
"""
import asyncio
import sqlite3
from collections import defaultdict
import json
import random
import time
import logging
import re
from enum import Enum
from datetime import datetime, UTC
from typing import Optional, Dict, Any, Tuple, List, Union
from aiogram.types import BufferedInputFile, InputFile
from common.db_pool import get_pool
from common.config import (
    DB_NAME,
    DB_TIMEOUT,
    BOT_COPY_CACHE_POST_LIMIT,
    POST_COPY_RETENTION_DAYS,
    POST_COPY_RETENTION_POSTS,
)
logger = logging.getLogger(__name__)
def _json_serializer(obj):
    """Специальный сериализатор JSON для обработки несериализуемых объектов aiogram и байтов."""
    if isinstance(obj, (BufferedInputFile, InputFile)):
        filename = getattr(obj, 'filename', 'unknown_file')
        return f"<объект файла: {filename}>"
    if isinstance(obj, bytes):
        return f"<бинарные данные: {len(obj)} байт>"
    if isinstance(obj, Enum):
        return obj.value
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")
async def initialize_database():
    try:
        async with aiosqlite.connect(DB_NAME, timeout=30.0, isolation_level=None) as db:
            # Настройки соединения
            await db.execute("PRAGMA busy_timeout = 30000;")
            await db.execute("PRAGMA journal_mode=WAL;")
            await db.execute("PRAGMA synchronous = NORMAL;")
            await db.execute("PRAGMA mmap_size = 268435456;")
            await db.execute("PRAGMA cache_size = -60000;")
            await db.execute("PRAGMA foreign_keys = ON;")
            
            # Начало транзакции для изменения схемы
            await db.execute("BEGIN IMMEDIATE")
            
            await db.execute("""
            CREATE TABLE IF NOT EXISTS Boards (
                board_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                settings TEXT DEFAULT '{}'
            );
            """)
            await db.execute("INSERT OR IGNORE INTO Boards (board_id, name, description) VALUES ('ALL', 'Global System', 'System Board for Global Bans');")
            await db.execute("INSERT OR IGNORE INTO Boards (board_id, name, description) VALUES ('b', 'Random', 'Default User Board');")
            await db.execute("""
            CREATE TABLE IF NOT EXISTS Posts (
                post_num INTEGER PRIMARY KEY AUTOINCREMENT,
                board_id TEXT NOT NULL,
                thread_id TEXT,
                author_id INTEGER NOT NULL,
                reply_to_post_num INTEGER,
                content TEXT NOT NULL,
                timestamp REAL NOT NULL,
                FOREIGN KEY (board_id) REFERENCES Boards(board_id),
                FOREIGN KEY (reply_to_post_num) REFERENCES Posts(post_num) ON DELETE SET NULL
            );
            """)
            await db.execute("CREATE INDEX IF NOT EXISTS idx_posts_board_timestamp ON Posts(board_id, timestamp);")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_posts_thread_id ON Posts(thread_id);")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_posts_board_reply_to ON Posts(board_id, reply_to_post_num);")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_posts_author_id ON Posts(author_id);")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_posts_chat_board_ts ON Posts(board_id, timestamp DESC) WHERE thread_id IS NULL;")
            await db.execute("""
            CREATE TABLE IF NOT EXISTS Users (
                user_id INTEGER NOT NULL,
                board_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                location TEXT NOT NULL DEFAULT 'main',
                api_token TEXT,
                nsfw_spoiler INTEGER DEFAULT 0,
                hidden_words TEXT DEFAULT '[]',
                lie_media INTEGER DEFAULT 0,
                role TEXT DEFAULT 'user',
                balance REAL DEFAULT 0,
                is_verified_b INTEGER DEFAULT 0,
                referrals_count INTEGER DEFAULT 0,
                posts_count INTEGER DEFAULT 0,
                last_failed_amount REAL DEFAULT 0,
                PRIMARY KEY (user_id, board_id),
                FOREIGN KEY (board_id) REFERENCES Boards(board_id)
            );
            """)
            try:
                await db.execute("ALTER TABLE Users ADD COLUMN balance REAL DEFAULT 0;")
                await db.execute("ALTER TABLE Users ADD COLUMN is_verified_b INTEGER DEFAULT 0;")
                await db.execute("ALTER TABLE Users ADD COLUMN reaction_reward_counter INTEGER DEFAULT 0;")
            except aiosqlite.OperationalError: pass
            
            try:
                await db.execute("ALTER TABLE Users ADD COLUMN posts_count INTEGER DEFAULT 0;")
                print("✅ Migrated: Added posts_count to Users.")
            except aiosqlite.OperationalError: pass

            try:
                await db.execute("ALTER TABLE Users ADD COLUMN last_failed_amount REAL DEFAULT 0;")
                print("✅ Migrated: Added last_failed_amount to Users.")
            except aiosqlite.OperationalError: pass
            try:
                await db.execute("ALTER TABLE Users ADD COLUMN api_token TEXT;")
            except aiosqlite.OperationalError: pass
            try:
                await db.execute("ALTER TABLE Users ADD COLUMN nsfw_spoiler INTEGER DEFAULT 0;")
                print("✅ Migrated: Added nsfw_spoiler to Users.")
            except aiosqlite.OperationalError: pass
            try:
                await db.execute("ALTER TABLE Users ADD COLUMN hidden_words TEXT DEFAULT '[]';")
                print("✅ Migrated: Added hidden_words to Users.")
            except aiosqlite.OperationalError: pass
            try:
                await db.execute("ALTER TABLE Users ADD COLUMN shadow_ban_gif INTEGER DEFAULT 0;")
                print("✅ Migrated: Added shadow_ban_gif to Users.")
            except aiosqlite.OperationalError: pass
            try:
                await db.execute("ALTER TABLE Users ADD COLUMN shadow_ban_sticker INTEGER DEFAULT 0;")
                print("✅ Migrated: Added shadow_ban_sticker to Users.")
            except aiosqlite.OperationalError: pass
            try:
                await db.execute("ALTER TABLE Users ADD COLUMN shadow_ban_media INTEGER DEFAULT 0;")
                print("✅ Migrated: Added shadow_ban_media to Users.")
            except aiosqlite.OperationalError: pass
            try:
                await db.execute("ALTER TABLE Users ADD COLUMN lie_media INTEGER DEFAULT 0;")
                print("✅ Migrated: Added lie_media to Users.")
            except aiosqlite.OperationalError: pass
            try:
                await db.execute("ALTER TABLE Users ADD COLUMN role TEXT DEFAULT 'user';")
                print("✅ Migrated: Added role to Users.")
            except aiosqlite.OperationalError: pass
            try:
                await db.execute("ALTER TABLE Boards ADD COLUMN banner_data TEXT DEFAULT '{}';")
                print("✅ Migrated: Added banner_data to Boards.")
            except aiosqlite.OperationalError: pass
            await db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_api_token ON Users(api_token) WHERE api_token IS NOT NULL;")
            try:
                await db.execute("ALTER TABLE Users ADD COLUMN stream TEXT DEFAULT 'ru';")
                print("✅ Migrated: Added 'stream' to Users.")
            except aiosqlite.OperationalError: pass
            try:
                await db.execute("ALTER TABLE Posts ADD COLUMN stream TEXT DEFAULT 'ru';")
                print("✅ Migrated: Added 'stream' to Posts.")
            except aiosqlite.OperationalError: pass
            try:
                await db.execute("ALTER TABLE Threads ADD COLUMN stream TEXT DEFAULT 'ru';")
                print("✅ Migrated: Added 'stream' to Threads.")
            except aiosqlite.OperationalError: pass
            try:
                await db.execute("ALTER TABLE Threads ADD COLUMN is_pinned INTEGER DEFAULT 0;")
                print("✅ Migrated: Added 'is_pinned' to Threads.")
            except aiosqlite.OperationalError: pass
            try:
                await db.execute("ALTER TABLE Threads ADD COLUMN is_endless INTEGER DEFAULT 0;")
                print("✅ Migrated: Added 'is_endless' to Threads.")
            except aiosqlite.OperationalError: pass
            try:
                await db.execute("ALTER TABLE Posts ADD COLUMN is_op_hidden INTEGER DEFAULT 0;")
                print("✅ Migrated: Added 'is_op_hidden' to Posts.")
            except aiosqlite.OperationalError: pass            
            try:
                await db.execute("ALTER TABLE Posts ADD COLUMN ip TEXT;")
                print("✅ Migrated: Added 'ip' column to Posts.")
            except aiosqlite.OperationalError: pass
            await db.execute("CREATE INDEX IF NOT EXISTS idx_users_stream ON Users(board_id, stream);")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_posts_stream ON Posts(board_id, stream);")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_posts_chat_board_stream_ts ON Posts(board_id, stream, timestamp DESC) WHERE thread_id IS NULL;")
            await db.execute("""
            CREATE TABLE IF NOT EXISTS UserAlerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                content TEXT NOT NULL,
                image_url TEXT,
                btn_text TEXT,
                btn_link TEXT,
                target_board TEXT, -- 'all' или конкретная доска
                is_read INTEGER DEFAULT 0,
                created_at REAL NOT NULL,
                read_at REAL
            );
            """)
            await db.execute("CREATE INDEX IF NOT EXISTS idx_alerts_user ON UserAlerts(user_id, is_read);")
            await db.execute("""
            CREATE TABLE IF NOT EXISTS UserReplies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                board_id TEXT NOT NULL,
                thread_id TEXT NOT NULL,
                post_num INTEGER NOT NULL,
                parent_num INTEGER,
                is_read INTEGER DEFAULT 0,
                created_at REAL NOT NULL
            );
            """)
            await db.execute("CREATE INDEX IF NOT EXISTS idx_replies_user_read ON UserReplies(user_id, is_read);")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_replies_created ON UserReplies(created_at);")
            await db.execute("""
            CREATE TABLE IF NOT EXISTS Threads (
                thread_id TEXT PRIMARY KEY,
                board_id TEXT NOT NULL,
                op_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                created_at REAL NOT NULL,
                is_archived INTEGER NOT NULL DEFAULT 0,
                last_updated_at REAL
            );
            """)
            try:
                await db.execute("ALTER TABLE Threads ADD COLUMN stream TEXT DEFAULT 'ru';")
            except aiosqlite.OperationalError: pass
            try:
                await db.execute("ALTER TABLE Threads ADD COLUMN is_pinned INTEGER DEFAULT 0;")
            except aiosqlite.OperationalError: pass
            try:
                await db.execute("ALTER TABLE Threads ADD COLUMN is_endless INTEGER DEFAULT 0;")
            except aiosqlite.OperationalError: pass
            try:
                await db.execute("ALTER TABLE Threads ADD COLUMN thread_num INTEGER DEFAULT 0;")
                print("✅ Migrated: Added 'thread_num' to Threads for performance.")
                await db.execute("UPDATE Threads SET thread_num = CAST(thread_id AS INTEGER) WHERE thread_num = 0;")
                print("✅ Data Migration: Populated 'thread_num' from 'thread_id'.")
            except aiosqlite.OperationalError: pass

            await db.execute("CREATE INDEX IF NOT EXISTS idx_threads_thread_num ON Threads(thread_num);")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_threads_stream ON Threads(board_id, stream);")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_threads_last_updated ON Threads(is_archived, last_updated_at);")
            await db.execute("""
            CREATE TABLE IF NOT EXISTS Mutes (
                user_id INTEGER NOT NULL,
                board_id TEXT NOT NULL,
                mute_type TEXT NOT NULL,
                thread_id TEXT,
                expires_at REAL NOT NULL,
                PRIMARY KEY (user_id, board_id, mute_type, thread_id)
            );
            """)
            await db.execute("""
            CREATE TABLE IF NOT EXISTS PostCopies (
                post_num INTEGER NOT NULL,
                recipient_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                PRIMARY KEY (recipient_id, message_id),
                FOREIGN KEY (post_num) REFERENCES Posts(post_num) ON DELETE CASCADE
            );
            """)
            await db.execute("CREATE INDEX IF NOT EXISTS idx_postcopies_post_num ON PostCopies(post_num);")
            await db.execute("""
            CREATE TABLE IF NOT EXISTS BroadcastQueue (
                post_num INTEGER PRIMARY KEY,
                created_at REAL NOT NULL,
                FOREIGN KEY (post_num) REFERENCES Posts(post_num) ON DELETE CASCADE
            );
            """)
            await db.execute("""
            CREATE TABLE IF NOT EXISTS DeliveryQueue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                board_id TEXT NOT NULL,
                post_num INTEGER NOT NULL,
                recipients TEXT NOT NULL,
                content TEXT NOT NULL,
                delivery_phase TEXT NOT NULL DEFAULT 'passive',
                original_recipients INTEGER NOT NULL DEFAULT 0,
                thread_id TEXT,
                enqueued_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'pending',
                FOREIGN KEY (post_num) REFERENCES Posts(post_num) ON DELETE CASCADE
            );
            """)
            try:
                await db.execute("ALTER TABLE NotificationQueue ADD COLUMN board_id TEXT DEFAULT 'b';")
                print("✅ Migrated: Added 'board_id' to NotificationQueue.")
            except aiosqlite.OperationalError: pass

            try:
                await db.execute("ALTER TABLE NotificationQueue ADD COLUMN thread_id INTEGER;")
                print("✅ Migrated: Added 'thread_id' to NotificationQueue.")
            except aiosqlite.OperationalError: pass

            try:
                await db.execute("ALTER TABLE NotificationQueue ADD COLUMN created_at REAL DEFAULT 0;")
                print("✅ Migrated: Added 'created_at' to NotificationQueue.")
            except aiosqlite.OperationalError: pass
            try:
                await db.execute("ALTER TABLE BroadcastQueue ADD COLUMN is_sent_to_tg INTEGER DEFAULT 0;")
                print("✅ Migrated: Added 'is_sent_to_tg' to BroadcastQueue.")
            except aiosqlite.OperationalError: pass
            await db.execute("CREATE INDEX IF NOT EXISTS idx_broadcastqueue_created_at ON BroadcastQueue(created_at);")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_deliveryqueue_status_board ON DeliveryQueue(status, board_id, id);")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_deliveryqueue_post_phase ON DeliveryQueue(post_num, board_id, delivery_phase, status);")
            await db.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS PostsFTS USING fts5(
                content,
                content='Posts',
                content_rowid='post_num'
            );
            """)
            await db.execute("DROP TRIGGER IF EXISTS trg_posts_fts_insert;")
            await db.execute("DROP TRIGGER IF EXISTS trg_posts_fts_delete;")
            await db.execute("DROP TRIGGER IF EXISTS trg_posts_fts_update;")
            await db.execute("""
            CREATE TRIGGER IF NOT EXISTS trg_posts_fts_insert AFTER INSERT ON Posts BEGIN
                INSERT INTO PostsFTS(rowid, content) VALUES (new.post_num, json_extract(new.content, '$.text'));
            END;
            """)
            
            await db.execute("""
            CREATE TRIGGER IF NOT EXISTS trg_posts_fts_delete AFTER DELETE ON Posts BEGIN
                INSERT INTO PostsFTS(PostsFTS, rowid, content) VALUES('delete', old.post_num, json_extract(old.content, '$.text'));
            END;
            """)
            
            await db.execute("""
            CREATE TRIGGER IF NOT EXISTS trg_posts_fts_update AFTER UPDATE ON Posts BEGIN
                INSERT INTO PostsFTS(PostsFTS, rowid, content) VALUES('delete', old.post_num, json_extract(old.content, '$.text'));
                INSERT INTO PostsFTS(rowid, content) VALUES (new.post_num, json_extract(new.content, '$.text'));
            END;
            """)
            await db.execute("""
            CREATE TABLE IF NOT EXISTS GlobalLogs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL, -- 'bot' или 'site'
                event_text TEXT NOT NULL,
                created_at REAL NOT NULL
            );
            """)
            await db.execute("CREATE INDEX IF NOT EXISTS idx_logs_time ON GlobalLogs(created_at);")
            await db.execute("DROP TRIGGER IF EXISTS posts_after_insert;")
            await db.execute("DROP TRIGGER IF EXISTS posts_after_delete;")
            await db.execute("DROP TRIGGER IF EXISTS posts_after_update;")
            await db.execute("""
            CREATE TABLE IF NOT EXISTS PollVotes (
                post_num INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                option_index INTEGER NOT NULL,
                PRIMARY KEY (post_num, user_id),
                FOREIGN KEY (post_num) REFERENCES Posts(post_num) ON DELETE CASCADE
            );
            """)
            await db.execute("""
            CREATE TABLE IF NOT EXISTS FTSState (
                last_indexed_id INTEGER DEFAULT 0
            );
            """)
            await db.execute("INSERT OR IGNORE INTO FTSState (rowid, last_indexed_id) VALUES (1, 0)")
            try:
                await db.execute("ALTER TABLE Posts ADD COLUMN stream TEXT DEFAULT 'ru';")
                print("✅ Migrated: Added 'stream' to Posts.")
            except aiosqlite.OperationalError: pass
            try:
                await db.execute("ALTER TABLE FileRegistry ADD COLUMN blurhash TEXT;")
                print("✅ Migrated: Added 'blurhash' to FileRegistry.")
            except aiosqlite.OperationalError: pass
            try:
                await db.execute("ALTER TABLE Threads ADD COLUMN stream TEXT DEFAULT 'ru';")
                print("✅ Migrated: Added 'stream' to Threads.")
            except aiosqlite.OperationalError: pass
            try:
                await db.execute("ALTER TABLE Users ADD COLUMN stream TEXT DEFAULT 'ru';")
                print("✅ Migrated: Added 'stream' to Users.")
            except aiosqlite.OperationalError: pass
            try:
                await db.execute("ALTER TABLE Users ADD COLUMN created_at REAL DEFAULT 0;")
                print("✅ Migrated: Added 'created_at' to Users.")
            except aiosqlite.OperationalError: pass
            try:
                await db.execute("ALTER TABLE Boards ADD COLUMN is_approved INTEGER DEFAULT 1;") 
                print("✅ Migrated: Added 'is_approved' to Boards.")
            except aiosqlite.OperationalError: pass
            try:
                await db.execute("ALTER TABLE Boards ADD COLUMN owner_id INTEGER DEFAULT 0;") 
                print("✅ Migrated: Added 'owner_id' to Boards.")
            except aiosqlite.OperationalError: pass
            try:
                await db.execute("ALTER TABLE Posts ADD COLUMN channel_message_id INTEGER;")
                print("✅ Migrated: Added 'channel_message_id' to Posts.")
            except aiosqlite.OperationalError: pass
            await db.execute("""
            CREATE TABLE IF NOT EXISTS ChannelCopies (
                post_num INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                PRIMARY KEY (post_num, channel_id),
                FOREIGN KEY (post_num) REFERENCES Posts(post_num) ON DELETE CASCADE
            );
            """)
            try:
                await db.execute("ALTER TABLE Posts ADD COLUMN report_count INTEGER DEFAULT 0;")
                print("✅ Migrated: Added 'report_count' to Posts.")
            except aiosqlite.OperationalError: pass
            await db.execute("CREATE INDEX IF NOT EXISTS idx_channelcopies_post ON ChannelCopies(post_num);")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_posts_stream ON Posts(board_id, stream);")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_threads_stream ON Threads(board_id, stream);")
            await db.execute("""
            CREATE TABLE IF NOT EXISTS SpamFilterWords (
                board_id TEXT NOT NULL,
                word TEXT NOT NULL,
                PRIMARY KEY (board_id, word)
            );
            """)
            await db.execute("""
            CREATE TABLE IF NOT EXISTS ReactionBans (
                user_id INTEGER NOT NULL,
                board_id TEXT NOT NULL,
                PRIMARY KEY (user_id, board_id)
            );
            """)
            await db.execute("""
            CREATE TABLE IF NOT EXISTS ReactionQueue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                post_num INTEGER NOT NULL,
                emoji TEXT NOT NULL,
                created_at REAL NOT NULL
            );
            """)
            await db.execute("""
            CREATE TABLE IF NOT EXISTS AdminActionQueue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action_type TEXT NOT NULL, -- 'ban', 'unban', 'mute', 'shadow_mute'
                user_id INTEGER NOT NULL,
                board_id TEXT NOT NULL,
                expires_at REAL
            );
            """)

            await db.execute("""
            CREATE TABLE IF NOT EXISTS CrossLinks (
                source_board TEXT NOT NULL,
                source_post INTEGER NOT NULL,
                target_board TEXT NOT NULL,
                target_post INTEGER NOT NULL,
                PRIMARY KEY (source_board, source_post, target_board, target_post)
            );
            """)
            await db.execute("""
            CREATE TABLE IF NOT EXISTS Backlinks (
                target_post_num INTEGER NOT NULL,
                source_post_num INTEGER NOT NULL,
                PRIMARY KEY (target_post_num, source_post_num),
                FOREIGN KEY (target_post_num) REFERENCES Posts(post_num) ON DELETE CASCADE,
                FOREIGN KEY (source_post_num) REFERENCES Posts(post_num) ON DELETE CASCADE
            );
            """)
            await db.execute("CREATE INDEX IF NOT EXISTS idx_backlinks_source ON Backlinks(source_post_num);")
            try:
                await db.execute("ALTER TABLE Threads ADD COLUMN reply_count INTEGER DEFAULT 0;")
                print("✅ Migrated: Added 'reply_count' to Threads.")
                await db.execute("""
                    UPDATE Threads 
                    SET reply_count = (
                        SELECT COUNT(*) - 1 
                        FROM Posts 
                        WHERE Posts.thread_id = Threads.thread_id
                    )
                """)
            except aiosqlite.OperationalError: pass
            try:
                await db.execute("ALTER TABLE Threads ADD COLUMN thread_type TEXT DEFAULT 'default';")
                print("✅ Migrated: Added 'thread_type' to Threads.")
            except aiosqlite.OperationalError: pass

            await db.execute("""
            CREATE TABLE IF NOT EXISTS ThreadUnlocks (
                thread_id TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                PRIMARY KEY (thread_id, user_id)
            );
            """)
            await db.execute("CREATE INDEX IF NOT EXISTS idx_crosslinks_target ON CrossLinks(target_board, target_post);")
            await db.execute("""
            CREATE TABLE IF NOT EXISTS FileOwners (
                file_id TEXT PRIMARY KEY,
                bot_id INTEGER NOT NULL
            );
            """)
            await db.execute("""
            CREATE TABLE IF NOT EXISTS MirrorQueue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id TEXT NOT NULL,
                mirror_type TEXT NOT NULL, -- 'catbox', 'huggingface' и т.д.
                attempts INTEGER DEFAULT 0, -- Сколько раз пробовали
                next_run_at REAL DEFAULT 0, -- Когда пробовать в следующий раз (Unix timestamp)
                UNIQUE(file_id, mirror_type)
            );
            """)
            await db.execute("""
            CREATE TABLE IF NOT EXISTS Bottles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender_id INTEGER NOT NULL,
                recipient_id INTEGER NOT NULL,
                message_text TEXT NOT NULL,
                timestamp REAL NOT NULL,
                is_read INTEGER DEFAULT 0
            );
            """)
            await db.execute("CREATE INDEX IF NOT EXISTS idx_bottles_recipient ON Bottles(recipient_id, is_read);")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_mirror_queue_run ON MirrorQueue(next_run_at);")
            await db.execute("""
            CREATE TABLE IF NOT EXISTS Reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_num INTEGER NOT NULL,
                category TEXT NOT NULL,
                reason TEXT NOT NULL,
                sender_ip_hash TEXT, -- Хэш отправителя (чтобы не спамили)
                status TEXT DEFAULT 'open', -- open, resolved, dismissed
                created_at REAL NOT NULL,
                FOREIGN KEY (post_num) REFERENCES Posts(post_num) ON DELETE CASCADE
            );
            """)
            await db.execute("""
            CREATE TABLE IF NOT EXISTS SpamFilterWords (
                board_id TEXT NOT NULL,
                word TEXT NOT NULL,
                PRIMARY KEY (board_id, word)
            );
            """)
            await db.execute("""
            CREATE TABLE IF NOT EXISTS SystemSettings (
                key TEXT PRIMARY KEY,
                value TEXT
            );
            """)
            await db.execute("""
            CREATE TABLE IF NOT EXISTS ImportRequests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                url TEXT NOT NULL,
                target_board TEXT NOT NULL,
                comment TEXT,
                status TEXT DEFAULT 'pending', -- pending, approved, rejected
                created_at REAL NOT NULL
            );
            """)
            await db.execute("""
            CREATE TABLE IF NOT EXISTS PendingHF (
                file_id TEXT PRIMARY KEY,
                created_at REAL
            );
            """)
            await db.execute("CREATE INDEX IF NOT EXISTS idx_pending_time ON PendingHF(created_at);")
            await db.execute("""
            CREATE TABLE IF NOT EXISTS FileMirrors (
                file_id TEXT NOT NULL,
                mirror_type TEXT NOT NULL, 
                url TEXT NOT NULL,
                PRIMARY KEY (file_id, mirror_type)
            );
            """)
            await db.execute("""
            CREATE TABLE IF NOT EXISTS ModQueue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_num INTEGER NOT NULL,
                file_id TEXT NOT NULL,
                reason TEXT,
                score REAL,
                status TEXT DEFAULT 'pending',
                created_at REAL,
                FOREIGN KEY (post_num) REFERENCES Posts(post_num) ON DELETE CASCADE
            );
            """)
            await db.execute("CREATE INDEX IF NOT EXISTS idx_modqueue_status ON ModQueue(status);")
            await db.execute("""
            CREATE TABLE IF NOT EXISTS NotificationQueue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recipient_id INTEGER NOT NULL,
                source_post_num INTEGER NOT NULL,
                reply_post_num INTEGER NOT NULL,
                board_id TEXT NOT NULL,
                thread_id INTEGER,
                created_at REAL NOT NULL
            );
            """)
            await db.execute("CREATE INDEX IF NOT EXISTS idx_notif_recipient ON NotificationQueue(recipient_id);")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_notif_source_post ON NotificationQueue(source_post_num);")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_filemirrors_file_id ON FileMirrors(file_id);")
            await db.execute("""
            CREATE TABLE IF NOT EXISTS Feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                category TEXT NOT NULL,
                contact TEXT,
                message TEXT NOT NULL,
                created_at REAL NOT NULL,
                is_read INTEGER DEFAULT 0
            );
            """)    
            await db.execute("CREATE INDEX IF NOT EXISTS idx_import_requests_status ON ImportRequests(status, created_at);")
            try:
                await db.execute("ALTER TABLE Posts ADD COLUMN is_shadow INTEGER DEFAULT 0;")
                print("✅ Migrated: Added 'is_shadow' to Posts.")
            except aiosqlite.OperationalError: pass
            await db.execute("CREATE INDEX IF NOT EXISTS idx_posts_shadow ON Posts(is_shadow);")
            await db.execute("""
            CREATE TABLE IF NOT EXISTS FileRegistry (
                sha256 TEXT PRIMARY KEY,
                phash TEXT,
                file_id TEXT NOT NULL,
                thumbnail_id TEXT,
                file_type TEXT,
                created_at REAL
            );
            """)
            await db.execute("CREATE INDEX IF NOT EXISTS idx_files_phash ON FileRegistry(phash);")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_files_file_id ON FileRegistry(file_id);")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_files_created_at ON FileRegistry(created_at);")
            await db.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS FileTagsFTS USING fts5(
                file_id UNINDEXED, 
                tags, 
                content='FileRegistry', 
                content_rowid='rowid'
            );
            """)
            
            await db.execute("""
            CREATE TRIGGER IF NOT EXISTS trg_files_fts_insert AFTER INSERT ON FileRegistry BEGIN
                INSERT INTO FileTagsFTS(rowid, file_id, tags) VALUES (new.rowid, new.file_id, new.tags);
            END;
            """)
            
            await db.execute("""
            CREATE TRIGGER IF NOT EXISTS trg_files_fts_delete AFTER DELETE ON FileRegistry BEGIN
                INSERT INTO FileTagsFTS(FileTagsFTS, rowid, file_id, tags) VALUES('delete', old.rowid, old.file_id, old.tags);
            END;
            """)
            
            await db.execute("""
            CREATE TRIGGER IF NOT EXISTS trg_files_fts_update AFTER UPDATE ON FileRegistry BEGIN
                INSERT INTO FileTagsFTS(FileTagsFTS, rowid, file_id, tags) VALUES('delete', old.rowid, old.file_id, old.tags);
                INSERT INTO FileTagsFTS(rowid, file_id, tags) VALUES (new.rowid, new.file_id, new.tags);
            END;
            """)
            await db.execute("""
            CREATE TABLE IF NOT EXISTS BannedHashes (
                hash_value TEXT PRIMARY KEY, -- SHA256 или pHash
                hash_type TEXT,              -- 'sha256' или 'phash'
                reason TEXT
            );
            """)
            await db.execute("""
            CREATE TABLE IF NOT EXISTS Mutes (
                user_id INTEGER NOT NULL,
                board_id TEXT NOT NULL,
                mute_type TEXT NOT NULL, 
                thread_id TEXT, -- Опционально, если бан только в одном треде
                expires_at REAL NOT NULL,
                PRIMARY KEY (user_id, board_id, mute_type, thread_id)
            );
            """)
            
            await db.execute("""
            CREATE TABLE IF NOT EXISTS ImportQueue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                board_id TEXT NOT NULL,
                original_post_num TEXT,
                reply_to_original TEXT, 
                publish_at REAL NOT NULL,
                content TEXT NOT NULL,
                author_id INTEGER NOT NULL, 
                stream TEXT DEFAULT 'ru',
                is_op INTEGER DEFAULT 0,
                thread_title TEXT,
                created_at REAL NOT NULL
            );
            """)
            await db.execute("CREATE INDEX IF NOT EXISTS idx_import_queue_pub ON ImportQueue(publish_at);")
            
            await db.execute("""
            CREATE TABLE IF NOT EXISTS ImportRefMap (
                task_id TEXT NOT NULL,
                original_post_num TEXT NOT NULL,
                real_post_num INTEGER NOT NULL,
                PRIMARY KEY (task_id, original_post_num)
            );
            """)

            await db.execute("CREATE INDEX IF NOT EXISTS idx_posts_timestamp ON Posts(timestamp);")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_threads_created_at ON Threads(created_at);")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_posts_board_id ON Posts(board_id);")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_reports_status ON Reports(status);")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_posts_num_text ON Posts(CAST(post_num AS TEXT));")
            
            await db.execute("COMMIT")
        print("✅ База данных успешно инициализирована.")
    except Exception as e:
        print(f"⛔ КРИТИЧЕСКАЯ ОШИБКА: Не удалось инициализировать базу данных: {e}")
        import sys
        sys.exit(1)
async def get_or_create_api_token(user_id: int, token_generator_func) -> str:
    """
    Получает существующий API токен или генерирует новый.
    Использует глобальный db_lock и транзакцию IMMEDIATE.
    """
    from common.db_pool import get_pool, db_lock
    
    async with db_lock:
        for attempt in range(10):
            try:
                db = await get_pool()
                await db.execute("BEGIN IMMEDIATE")
                
                # 1. Проверяем существующий
                async with db.execute("SELECT api_token FROM Users WHERE user_id = ? AND api_token IS NOT NULL LIMIT 1", (user_id,)) as cursor:
                    row = await cursor.fetchone()
                
                if row and row[0]:
                    await db.execute("COMMIT")
                    return row[0]
                
                # 2. Генерируем новый (нужна проверка на уникальность)
                # Важно: проверка уникальности должна быть внутри этой же транзакции или 
                # мы доверяем генератору. Здесь генератор внешний, но проверку делаем через БД.
                
                async def check_if_token_exists(token: str) -> bool:
                    # Используем то же соединение db внутри транзакции
                    async with db.execute("SELECT 1 FROM Users WHERE api_token = ? LIMIT 1", (token,)) as c:
                        return await c.fetchone() is not None
                
                new_token = await token_generator_func(check_if_token_exists)
                
                # 3. Обнуляем старые и пишем новый
                await db.execute("UPDATE Users SET api_token = NULL WHERE user_id = ?", (user_id,))
                
                # Убедимся, что юзер существует
                await db.execute(
                    "INSERT OR IGNORE INTO Users (user_id, board_id, created_at) VALUES (?, 'b', ?)", 
                    (user_id, time.time())
                )
                
                await db.execute("UPDATE Users SET api_token = ? WHERE user_id = ? AND board_id = 'b'", (new_token, user_id))
                
                await db.execute("COMMIT")
                return new_token
                
            except sqlite3.OperationalError as e:
                try: await db.execute("ROLLBACK")
                except: pass
                
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    await asyncio.sleep(0.1 * (attempt + 1))
                    continue
                print(f"⛔ Ошибка в get_or_create_api_token: {e}")
                raise e
            except Exception as e:
                try: await db.execute("ROLLBACK")
                except: pass
                print(f"⛔ КРИТИЧЕСКАЯ ОШИБКА в get_or_create_api_token: {e}")
                raise e
    return ""
async def is_database_migrated() -> bool:
    """
    Проверяет, были ли данные уже мигрированы в БД,
    проверяя наличие записей в таблице Users.
    """
    async with aiosqlite.connect(DB_NAME, timeout=DB_TIMEOUT) as db:
        await db.execute("PRAGMA journal_mode=WAL;")
        await db.execute("PRAGMA mmap_size = 268435456;")
        await db.execute("PRAGMA cache_size = -60000;")
        await db.execute("PRAGMA query_only = 1;")
        async with db.execute("SELECT COUNT(*) FROM Users") as cursor:
            result = await cursor.fetchone()
            return result[0] > 0
async def get_post_info_by_copy(recipient_id: int, message_id: int) -> tuple[int, int] | None:
    """
    Находит (post_num, author_id) оригинального поста по ID копии сообщения.
    """
    from common.db_pool import get_pool, db_lock
    
    async with db_lock:
        try:
            db = await get_pool()
            query = """
                SELECT p.post_num, p.author_id
                FROM Posts p
                JOIN PostCopies pc ON p.post_num = pc.post_num
                WHERE pc.recipient_id = ? AND pc.message_id = ?
            """
            async with db.execute(query, (recipient_id, message_id)) as cursor:
                result = await cursor.fetchone()
                return (result[0], result[1]) if result else None
        except Exception:
            return None
async def load_state_from_db(thread_boards: set) -> dict:
    """
    Загружает полное состояние бота из базы данных SQLite.
    Защищена db_lock для предотвращения конкуренции при старте.
    """
    from collections import defaultdict
    from datetime import datetime, UTC
    import json
    from common.config import DB_POST_LIMIT, BOT_POST_CACHE_LIMIT
    from common.db_pool import get_pool, db_lock
    
    print("🔄 Начало загрузки состояния из базы данных SQLite...")
    state_data = {
        'board_data': defaultdict(lambda: {
            'users': {'active': set(), 'banned': set()},
            'user_settings': defaultdict(lambda: {'nsfw': False, 'hide': set()}),
            'shadow_mutes': {},
            'threads_data': {},
            'user_state': {},
            'board_post_count': 0,
            'active_pin': None,
            'anime_mode': False,
            'zaputin_mode': False,
            'slavaukraine_mode': False,
            'suka_blyat_mode': False,
            'polish_mode': False,
            'warhammer_mode': False,
            'imperial_mode': False,
            'gopnik_mode': False,
            'schizo_mode': False,
            'matrix_mode': False,
            'america_mode': False,
            'holiday_mode': False,
            'oldweb_mode': False,
            'jewish_mode': False,
        }),
        'messages_storage': {},
        'post_to_messages': {},
        'message_to_post': {},
        'post_counter': 0,
    }
    
    async with db_lock:
        try:
            db = await get_pool()
            
            print("  > Загрузка пользователей...")
            try:
                async with db.execute("SELECT user_id, board_id, status, location, nsfw_spoiler, hidden_words, shadow_ban_gif, shadow_ban_sticker, shadow_ban_media, lie_media FROM Users") as cursor:
                    async for row in cursor:
                        user_id, board_id, status, location, nsfw, words_json, s_gif, s_sticker, s_media, s_lie = row
                        if status == 'active':
                            state_data['board_data'][board_id]['users']['active'].add(user_id)
                        elif status == 'banned':
                            state_data['board_data'][board_id]['users']['banned'].add(user_id)
                        if location != 'main':
                            state_data['board_data'][board_id]['user_state'].setdefault(user_id, {})['location'] = location
                        try:
                            h_words = set(json.loads(words_json)) if words_json else set()
                        except (json.JSONDecodeError, TypeError):
                            h_words = set()
                        state_data['board_data'][board_id]['user_settings'][user_id] = {
                            'nsfw': bool(nsfw),
                            'hide': h_words,
                            'shadow_gif': bool(s_gif),       
                            'shadow_sticker': bool(s_sticker),
                            'shadow_media': bool(s_media),
                            'lie_media': bool(s_lie)
                        }
            except Exception:
                # Fallback для старой схемы (на всякий случай)
                async with db.execute("SELECT user_id, board_id, status, location FROM Users") as cursor:
                     async for row in cursor:
                        user_id, board_id, status, location = row
                        if status == 'active':
                            state_data['board_data'][board_id]['users']['active'].add(user_id)
                        elif status == 'banned':
                            state_data['board_data'][board_id]['users']['banned'].add(user_id)
                        if location != 'main':
                            state_data['board_data'][board_id]['user_state'].setdefault(user_id, {})['location'] = location

            print("  > Загрузка настроек досок...")
            async with db.execute("SELECT board_id, settings FROM Boards") as cursor:
                async for row in cursor:
                    b_id, settings_json = row
                    try:
                        if settings_json:
                            settings = json.loads(settings_json)
                            b_data_ref = state_data['board_data'][b_id]
                            if 'active_pin' in settings:
                                b_data_ref['active_pin'] = settings['active_pin']
                            mode_keys = ['anime_mode', 'zaputin_mode', 'slavaukraine_mode', 'suka_blyat_mode', 
                                         'polish_mode', 'warhammer_mode', 'imperial_mode', 'gopnik_mode', 'schizo_mode',
                                         'matrix_mode', 'america_mode', 'holiday_mode', 'oldweb_mode', 'jewish_mode']
                            for mode in mode_keys:
                                if mode in settings:
                                    b_data_ref[mode] = False
                    except: pass

            print("  > Загрузка мутов...")
            async with db.execute("SELECT user_id, board_id, mute_type, expires_at FROM Mutes") as cursor:
                async for row in cursor:
                    user_id, board_id, mute_type, expires_at_ts = row
                    expires_at_dt = datetime.fromtimestamp(expires_at_ts, tz=UTC)
                    if expires_at_dt > datetime.now(UTC):
                        if mute_type == 'shadow':
                            state_data['board_data'][board_id]['shadow_mutes'][user_id] = expires_at_dt
                        elif mute_type == 'mute':
                            state_data['board_data'][board_id]['mutes'][user_id] = expires_at_dt

            print("  > Загрузка тредов...")
            async with db.execute("SELECT thread_id, board_id, op_id, title, created_at, is_archived, stream FROM Threads") as cursor:
                async for row in cursor:
                    thread_id, board_id, op_id, title, created_at_ts, is_archived, stream = row
                    state_data['board_data'][board_id]['threads_data'][thread_id] = {
                        'op_id': op_id,
                        'title': title,
                        'created_at': datetime.fromtimestamp(created_at_ts, tz=UTC).isoformat(),
                        'is_archived': bool(is_archived),
                        'posts': [],         
                        'subscribers': set(), 
                        'stream': stream or 'ru'
                    }
                    user_state_map = state_data['board_data'][board_id]['user_state']
                    for uid, u_state in user_state_map.items():
                        if u_state.get('location') == thread_id:
                            state_data['board_data'][board_id]['threads_data'][thread_id]['subscribers'].add(uid)

            post_cache_limit = max(0, int(BOT_POST_CACHE_LIMIT or 0))
            if post_cache_limit <= 0:
                post_cache_limit = DB_POST_LIMIT

            print(f"  > Загрузка последних {post_cache_limit} постов в RAM-кэш (DB_POST_LIMIT={DB_POST_LIMIT})...")
            max_post_num_loaded = 0
            query_posts = f"""
                SELECT post_num, board_id, thread_id, author_id, content, timestamp, reply_to_post_num 
                FROM Posts 
                ORDER BY post_num DESC 
                LIMIT {post_cache_limit}
            """
            loaded_post_nums = set()
            async with db.execute(query_posts) as cursor:
                async for row in cursor:
                    post_num, board_id, thread_id, author_id, content_str, timestamp_ts, reply_to_post_num = row
                    loaded_post_nums.add(post_num)
                    try:
                        content_data = json.loads(content_str)
                    except: content_data = {}
                    
                    if reply_to_post_num:
                        content_data['reply_to_post'] = reply_to_post_num

                    state_data['messages_storage'][post_num] = {
                        "author_id": author_id,
                        "timestamp": datetime.fromtimestamp(timestamp_ts, tz=UTC),
                        "content": content_data,
                        "board_id": board_id,
                        "thread_id": thread_id,
                        "reply_to_post_num": reply_to_post_num,
                    }
                    
                    if thread_id and board_id in thread_boards:
                        threads_data = state_data['board_data'][board_id]['threads_data']
                        if thread_id in threads_data:
                            threads_data[thread_id]['posts'].insert(0, post_num)
                    
                    if post_num > max_post_num_loaded:
                        max_post_num_loaded = post_num

            async with db.execute("SELECT MAX(post_num) FROM Posts") as cursor:
                result = await cursor.fetchone()
                db_max_post = result[0] if result and result[0] else 0
                state_data['post_counter'] = max(db_max_post, max_post_num_loaded)

            async with db.execute("SELECT board_id, COUNT(*) FROM Posts GROUP BY board_id") as cursor:
                async for row in cursor:
                    board_id, count = row
                    state_data['board_data'][board_id]['board_post_count'] = count

            if thread_boards:
                thread_board_list = list(thread_boards)
                placeholders = ','.join('?' for _ in thread_board_list)
                for thread_board in thread_board_list:
                    for thread_info in state_data['board_data'][thread_board]['threads_data'].values():
                        thread_info['posts'] = []
                print(f"  > Загрузка легких списков постов тредов для досок: {', '.join(thread_board_list)}")
                query_thread_posts = f"""
                    SELECT post_num, board_id, thread_id
                    FROM Posts
                    WHERE thread_id IS NOT NULL
                      AND board_id IN ({placeholders})
                    ORDER BY post_num ASC
                """
                async with db.execute(query_thread_posts, thread_board_list) as cursor:
                    async for row in cursor:
                        post_num, board_id, thread_id = row
                        threads_data = state_data['board_data'][board_id]['threads_data']
                        if thread_id in threads_data:
                            threads_data[thread_id]['posts'].append(post_num)

            copy_cache_limit = max(0, int(BOT_COPY_CACHE_POST_LIMIT or 0))
            copy_cache_post_nums = set()
            if loaded_post_nums and copy_cache_limit:
                copy_cache_post_nums = set(sorted(loaded_post_nums, reverse=True)[:copy_cache_limit])

            print(f"  > Загрузка кэша копий сообщений ({len(copy_cache_post_nums)} из {len(loaded_post_nums)} постов)...")
            if copy_cache_post_nums:
                loaded_post_nums_list = list(copy_cache_post_nums)
                CHUNK_SIZE = 900 
                for i in range(0, len(loaded_post_nums_list), CHUNK_SIZE):
                    chunk = loaded_post_nums_list[i:i + CHUNK_SIZE]
                    placeholders = ','.join('?' for _ in chunk)
                    query_copies = f"SELECT post_num, recipient_id, message_id FROM PostCopies WHERE post_num IN ({placeholders})"
                    async with db.execute(query_copies, chunk) as cursor:
                        async for row in cursor:
                            p_num, rec_id, msg_id = row
                            recipients_for_post = state_data['post_to_messages'].setdefault(p_num, {})
                            existing = recipients_for_post.get(rec_id)
                            if existing is None:
                                recipients_for_post[rec_id] = msg_id
                            elif isinstance(existing, int):
                                recipients_for_post[rec_id] = [existing, msg_id]
                            elif isinstance(existing, list):
                                existing.append(msg_id)
                            state_data['message_to_post'][(rec_id, msg_id)] = p_num
                            
        except Exception as e:
            print(f"⛔ ОШИБКА при загрузке состояния: {e}")
            import traceback
            traceback.print_exc()
            raise e

    print("✅ Состояние успешно загружено.")
    return state_data
async def update_user_settings_db(user_id: int, board_id: str, nsfw: int = None, hidden_words: list = None, 
                                  shadow_gif: int = None, shadow_sticker: int = None, shadow_media: int = None,
                                  lie_media: int = None):
    """
    Обновляет настройки пользователя.
    Использует явные транзакции и глобальный лок.
    """
    from common.db_pool import get_pool, db_lock
    
    async with db_lock:
        for attempt in range(10):
            try:
                db = await get_pool()
                await db.execute("BEGIN IMMEDIATE")
                
                if nsfw is not None:
                    await db.execute("UPDATE Users SET nsfw_spoiler = ? WHERE user_id = ? AND board_id = ?", (nsfw, user_id, board_id))
                if hidden_words is not None:
                    words_json = json.dumps(hidden_words, ensure_ascii=False)
                    await db.execute("UPDATE Users SET hidden_words = ? WHERE user_id = ? AND board_id = ?", (words_json, user_id, board_id))
                if shadow_gif is not None:
                    await db.execute("UPDATE Users SET shadow_ban_gif = ? WHERE user_id = ? AND board_id = ?", (shadow_gif, user_id, board_id))
                if shadow_sticker is not None:
                    await db.execute("UPDATE Users SET shadow_ban_sticker = ? WHERE user_id = ? AND board_id = ?", (shadow_sticker, user_id, board_id))
                if shadow_media is not None:
                    await db.execute("UPDATE Users SET shadow_ban_media = ? WHERE user_id = ? AND board_id = ?", (shadow_media, user_id, board_id))
                if lie_media is not None:
                    await db.execute("UPDATE Users SET lie_media = ? WHERE user_id = ? AND board_id = ?", (lie_media, user_id, board_id))
                
                await db.execute("COMMIT")
                return
            except sqlite3.OperationalError as e:
                try: await db.execute("ROLLBACK")
                except: pass
                
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    await asyncio.sleep(0.1 * (attempt + 1))
                    continue
                print(f"⛔ Ошибка обновления настроек пользователя {user_id}: {e}")
                break
            except Exception as e:
                try: await db.execute("ROLLBACK")
                except: pass
                print(f"⛔ Ошибка обновления настроек пользователя {user_id}: {e}")
                break
async def update_board_settings(board_id: str, updates: dict):
    """
    Умное обновление настроек доски.
    Критически важно использовать транзакцию здесь, так как мы делаем SELECT затем UPDATE.
    """
    from common.db_pool import get_pool, db_lock
    
    async with db_lock:
        for attempt in range(10):
            try:
                db = await get_pool()
                await db.execute("BEGIN IMMEDIATE")
                
                # Читаем внутри транзакции
                async with db.execute("SELECT settings FROM Boards WHERE board_id = ?", (board_id,)) as cursor:
                    row = await cursor.fetchone()
                    current_settings = {}
                    if row and row[0]:
                        try:
                            current_settings = json.loads(row[0])
                        except json.JSONDecodeError:
                            current_settings = {}
                
                current_settings.update(updates)
                settings_json = json.dumps(current_settings)
                
                # Пишем
                await db.execute(
                    "UPDATE Boards SET settings = ? WHERE board_id = ?",
                    (settings_json, board_id)
                )
                
                await db.execute("COMMIT")
                return
            except sqlite3.OperationalError as e:
                try: await db.execute("ROLLBACK")
                except: pass
                
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    await asyncio.sleep(0.1 * (attempt + 1))
                    continue
                break
            except Exception as e:
                try: await db.execute("ROLLBACK")
                except: pass
                print(f"⛔ Ошибка обновления настроек доски {board_id}: {e}")
                break

async def add_or_activate_user(user_id: int, board_id: str):
    """
    Добавляет нового пользователя или активирует существующего.
    Использует явные транзакции и глобальный лок.
    """
    from common.db_pool import get_pool, db_lock
    
    async with db_lock:
        for attempt in range(10):
            try:
                db = await get_pool()
                await db.execute("BEGIN IMMEDIATE")
                
                await db.execute(
                    "INSERT OR IGNORE INTO Users (user_id, board_id) VALUES (?, ?)",
                    (user_id, board_id)
                )
                await db.execute(
                    "UPDATE Users SET status = 'active' WHERE user_id = ? AND board_id = ?",
                    (user_id, board_id)
                )
                
                await db.execute("COMMIT")
                return
            except sqlite3.OperationalError as e:
                try: await db.execute("ROLLBACK")
                except: pass
                
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    await asyncio.sleep(0.1 * (attempt + 1))
                    continue
                break
            except Exception:
                try: await db.execute("ROLLBACK")
                except: pass
                break
async def update_user_status(user_id: int, board_id: str, status: str):
    """
    Обновляет статус пользователя на доске.
    """
    if status not in ['active', 'banned']:
        return
        
    from common.db_pool import get_pool, db_lock
    
    async with db_lock:
        for attempt in range(10):
            try:
                db = await get_pool()
                await db.execute("BEGIN IMMEDIATE")
                
                await db.execute(
                    "INSERT OR IGNORE INTO Users (user_id, board_id) VALUES (?, ?)",
                    (user_id, board_id)
                )
                await db.execute(
                    "UPDATE Users SET status = ? WHERE user_id = ? AND board_id = ?",
                    (status, user_id, board_id)
                )
                
                await db.execute("COMMIT")
                return
            except sqlite3.OperationalError as e:
                try: await db.execute("ROLLBACK")
                except: pass
                
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    await asyncio.sleep(0.1 * (attempt + 1))
                    continue
                break
            except Exception:
                try: await db.execute("ROLLBACK")
                except: pass
                break
async def remove_user_from_board(user_id: int, board_id: str):
    """Обертка для удаления одного пользователя."""
    await remove_users_from_board_batch([user_id], board_id)

async def remove_users_from_board_batch(user_ids: list[int], board_id: str):
    """
    Массовое удаление пользователей с защитой от блокировок БД.
    """
    if not user_ids: return
    
    from common.db_pool import get_pool, db_lock
    
    async with db_lock:
        for attempt in range(10):
            try:
                db = await get_pool()
                await db.execute("BEGIN IMMEDIATE")
                
                placeholders = ','.join('?' for _ in user_ids)
                query = f"DELETE FROM Users WHERE board_id = ? AND user_id IN ({placeholders})"
                params = [board_id] + list(user_ids)
                
                cursor = await db.execute(query, params)
                count = cursor.rowcount
                
                await db.execute("COMMIT")
                
                if count > 0:
                    print(f"  > DB: Удалено {count} пользователей с доски '{board_id}'.")
                return
            except sqlite3.OperationalError as e:
                try: await db.execute("ROLLBACK")
                except: pass
                
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    await asyncio.sleep(0.1 * (attempt + 1))
                    continue
                break
            except Exception:
                try: await db.execute("ROLLBACK")
                except: pass
                break
async def update_shadow_mute(user_id: int, board_id: str, expires_at: float | None):
    """
    Добавляет, обновляет или удаляет теневой мут.
    """
    from common.db_pool import get_pool, db_lock
    
    async with db_lock:
        try:
            db = await get_pool()
            await db.execute("BEGIN IMMEDIATE")
            
            if expires_at and expires_at > datetime.now(UTC).timestamp():
                await db.execute(
                    """
                    INSERT OR REPLACE INTO Mutes (user_id, board_id, mute_type, expires_at, thread_id)
                    VALUES (?, ?, 'shadow', ?, NULL)
                    """,
                    (user_id, board_id, expires_at)
                )
            else:
                await db.execute(
                    "DELETE FROM Mutes WHERE user_id = ? AND board_id = ? AND mute_type = 'shadow'",
                    (user_id, board_id)
                )
            
            await db.execute("COMMIT")
        except Exception as e:
            try: await db.execute("ROLLBACK")
            except: pass
            print(f"⛔ Error updating shadow mute: {e}")
async def create_thread(thread_id: str, board_id: str, op_id: int, title: str, created_at: float, stream: str = 'ru'):
    """
    Создает новую запись о треде в таблице Threads и обновляет локацию.
    """
    from common.db_pool import get_pool, db_lock
    
    async with db_lock:
        try:
            db = await get_pool()
            await db.execute("BEGIN IMMEDIATE")
            
            await db.execute(
                """
                INSERT INTO Threads (thread_id, thread_num, board_id, op_id, title, created_at, last_updated_at, is_archived, stream)
                VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)
                """,
                (thread_id, int(thread_id), board_id, op_id, title, created_at, created_at, stream)
            )
            await db.execute(
                "INSERT OR IGNORE INTO Users (user_id, board_id) VALUES (?, ?)",
                (op_id, board_id)
            )
            await db.execute(
                "UPDATE Users SET location = ? WHERE user_id = ? AND board_id = ?",
                (thread_id, op_id, board_id)
            )
            
            await db.execute("COMMIT")
            return True
        except Exception as e:
            try: await db.execute("ROLLBACK")
            except: pass
            print(f"⛔ КРИТИЧЕСКАЯ ОШИБКА при создании треда в БД: {e}")
            return False
async def update_user_location(user_id: int, board_id: str, location: str):
    """
    Обновляет местоположение пользователя (main или thread_id) на доске.
    """
    from common.db_pool import get_pool, db_lock
    
    async with db_lock:
        for attempt in range(10):
            try:
                db = await get_pool()
                await db.execute("BEGIN IMMEDIATE")
                
                await db.execute(
                    "INSERT OR IGNORE INTO Users (user_id, board_id) VALUES (?, ?)",
                    (user_id, board_id)
                )
                await db.execute(
                    "UPDATE Users SET location = ? WHERE user_id = ? AND board_id = ?",
                    (location, user_id, board_id)
                )
                
                await db.execute("COMMIT")
                return
            except sqlite3.OperationalError as e:
                try: await db.execute("ROLLBACK")
                except: pass
                
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    await asyncio.sleep(0.1 * (attempt + 1))
                    continue
                print(f"Error updating location for user {user_id}: {e}")
                break
            except Exception as e:
                try: await db.execute("ROLLBACK")
                except: pass
                print(f"Error updating location for user {user_id}: {e}")
                break
async def _get_thread_id_for_post(db: aiosqlite.Connection, parent_post_num: int) -> Optional[int]:
    """
    Находит ID треда (thread_id) для поста, на который отвечают.
    ID треда - это номер самого первого ОП-поста в ветке.
    """
    query = "SELECT thread_id FROM Posts WHERE post_num = ? LIMIT 1"
    async with db.execute(query, (parent_post_num,)) as cursor:
        row = await cursor.fetchone()
    return row[0] if row else None
async def create_post(
    author_id: int, 
    board_id: str, 
    content: dict, 
    timestamp: float, 
    reply_to: Optional[int] = None,
    is_shadow_muted: bool = False,
    is_from_site: bool = False, 
    post_mode: str = None, 
    stream: str = 'ru',
    thread_id_from_bot: Optional[str] = None,
    files_metadata: Optional[List[dict]] = None,
    request_id_for_log: str = 'NO_ID',
    file_owners: List[Tuple[str, int]] = None,
    ip: str = None  # <--- ДОБАВЛЕНО
) -> Optional[int]:
    # Локальный импорт, чтобы гарантировать наличие db_lock без правки шапки файла
    from common.db_pool import get_pool, db_lock
    
    local_logger = logging.LoggerAdapter(logging.getLogger(__name__), {'request_id': request_id_for_log})
    content_json = json.dumps(content, default=_json_serializer)
    
    # Глобальный Lock: защищает от состояния гонки между задачами внутри одного процесса бота
    async with db_lock:
        for attempt in range(10):
            try:
                db = await get_pool()
                if not db or not db._running: 
                    return None
                
                # BEGIN IMMEDIATE: Ключевой момент. 
                # Сразу запрашиваем блокировку на запись (Reserved Lock).
                # Если база занята сайтом, мы будем ждать здесь (busy_timeout), а не внутри SELECT.
                # Это предотвращает Deadlock (ситуацию, когда оба процесса прочли и оба ждут записи).
                await db.execute("BEGIN IMMEDIATE")
                
                # Проверка доски (чтение внутри транзакции безопасно)
                async with db.execute("SELECT 1 FROM Boards WHERE board_id = ?", (board_id,)) as c:
                    if not await c.fetchone():
                        await db.execute("INSERT OR IGNORE INTO Boards (board_id, name) VALUES (?, ?)", (board_id, board_id))
                
                valid_reply_to = None
                inherited_thread_id = None
                if reply_to:
                    async with db.execute("SELECT post_num, thread_id FROM Posts WHERE post_num = ?", (reply_to,)) as c:
                        row = await c.fetchone()
                        if row:
                            valid_reply_to = row[0]
                            inherited_thread_id = row[1]
                
                await db.execute(
                    """INSERT OR IGNORE INTO Users 
                       (user_id, board_id, status, location, stream, created_at) 
                       VALUES (?, ?, 'active', 'main', ?, ?)""",
                    (author_id, board_id, stream, time.time())
                )
                
                final_thread_id = thread_id_from_bot
                if is_from_site:
                    if post_mode == 'new_thread':
                        final_thread_id = None
                    elif post_mode == 'reply' and not final_thread_id:
                        final_thread_id = inherited_thread_id
                else:
                    if not final_thread_id and valid_reply_to:
                        final_thread_id = inherited_thread_id
                
                post_query = """
                    INSERT INTO Posts (board_id, author_id, content, timestamp, thread_id, reply_to_post_num, stream, is_shadow, ip)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """
                cursor = await db.execute(
                    post_query,
                    (board_id, author_id, content_json, timestamp, final_thread_id, valid_reply_to, stream, 1 if is_shadow_muted else 0, ip)
                )
                post_num = cursor.lastrowid

                if file_owners:
                    await db.executemany(
                        "INSERT OR IGNORE INTO FileOwners (file_id, bot_id) VALUES (?, ?)",
                        file_owners
                    )

                if is_from_site and post_mode == 'new_thread':
                    await db.execute("UPDATE Posts SET thread_id = ? WHERE post_num = ?", (post_num, post_num))

                if not is_shadow_muted:
                    await db.execute("INSERT INTO BroadcastQueue (post_num, created_at, is_sent_to_tg) VALUES (?, ?, 0)", (post_num, timestamp))

                # Явный коммит транзакции
                await db.execute("COMMIT")
                return post_num
                
            except sqlite3.OperationalError as e:
                # Если транзакция была начата, откатываем её
                try: await db.execute("ROLLBACK")
                except: pass
                
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    # Экспоненциальная задержка при занятой базе
                    wait_time = min(0.1 * (2 ** attempt), 2.0)
                    await asyncio.sleep(wait_time)
                    continue
                return None
            except Exception as e:
                try: await db.execute("ROLLBACK")
                except: pass
                # Логируем ошибку, но не крашим бота
                if 'local_logger' in locals():
                    local_logger.error(f"Error in create_post: {e}")
                else:
                    print(f"Error in create_post: {e}")
                return None
    return None
async def get_user_status(user_id: int, board_id: str) -> Optional[str]:
    """
    Получает статус пользователя.
    """
    from common.db_pool import get_pool, db_lock
    
    async with db_lock:
        for attempt in range(10):
            try:
                db = await get_pool()
                # Глобальный бан
                async with db.execute("SELECT status FROM Users WHERE user_id = ? AND board_id = 'ALL' LIMIT 1", (user_id,)) as cursor:
                    row = await cursor.fetchone()
                    if row and row[0] == 'banned':
                        return 'banned'
                # Локальный бан
                async with db.execute("SELECT status FROM Users WHERE user_id = ? AND board_id = ? LIMIT 1", (user_id, board_id)) as cursor:
                    row = await cursor.fetchone()
                    return row[0] if row else 'active'
            except sqlite3.OperationalError as e:
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    await asyncio.sleep(0.1 * (attempt + 1))
                    continue
                break
            except Exception:
                break
    return 'active'

async def get_shadow_mute_status(user_id: int, board_id: str) -> bool:
    """
    Проверяет теневой бан.
    """
    from common.db_pool import get_pool, db_lock
    
    async with db_lock:
        for attempt in range(10):
            try:
                db = await get_pool()
                query = """
                    SELECT 1 
                    FROM Mutes 
                    WHERE user_id = ? 
                      AND (board_id = ? OR board_id = 'ALL')
                      AND mute_type = 'shadow' 
                      AND expires_at > ?
                    LIMIT 1
                """
                async with db.execute(query, (user_id, board_id, time.time())) as cursor:
                    row = await cursor.fetchone()
                    return row is not None
            except sqlite3.OperationalError as e:
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    await asyncio.sleep(0.1 * (attempt + 1))
                    continue
                break
            except Exception:
                break
    return False
def _process_site_db_row(row):
    """
    Обрабатывает строку из БД. ПУЛЕНЕПРОБИВАЕМАЯ ВЕРСИЯ.
    """
    if row is None:
        return None  # Возвращаем None, если строка пустая
        
    try:
        # Превращаем Row в обычный дикт
        if hasattr(row, '_asdict'):
            post_dict = dict(row._asdict())
        else:
            post_dict = dict(row)

        if 'content' in post_dict and post_dict['content']:
            if isinstance(post_dict['content'], str):
                try:
                    post_dict['content'] = json.loads(post_dict['content'])
                except json.JSONDecodeError:
                    post_dict['content'] = {"text": post_dict['content'], "type": "text"}
            
            if not isinstance(post_dict['content'], dict):
                post_dict['content'] = {"text": str(post_dict['content']), "type": "text"}
            
            if 'type' not in post_dict['content']:
                post_dict['content']['type'] = 'text'
        else:
            post_dict['content'] = {"text": "", "type": "text"}
            
        return post_dict
    except Exception as e:
        print(f"⚠️ Ошибка обработки строки (Post): {e}")
        return None
async def get_op_posts_for_board(
    board_id: Union[str, List[str]], 
    sort_by: str = "new", 
    page: int = 1, 
    page_size: int = 10,
    stream: str = 'ru',
    observer_id: int = None,
    ignore_pin: bool = False,
    reply_limit: int = 3
) -> list:
    from common.db_pool import get_pool, db_lock
    
    offset = (page - 1) * page_size
    async with db_lock:
        for attempt in range(3):
            try:
                db = await get_pool()
                op_posts = []
                pin_clause = "MAX(IFNULL(t.is_pinned, 0)) DESC," if not ignore_pin else ""
                
                # Общая часть для WHERE
                params = []
                viewer_id = observer_id if observer_id else -1
                where_clause = f"""
                    WHERE p.reply_to_post_num IS NULL 
                    AND t.thread_id IS NOT NULL 
                    AND (IFNULL(p.is_shadow, 0) = 0 OR p.author_id = {viewer_id})
                """
                if board_id:
                    if isinstance(board_id, list):
                        placeholders = ','.join('?' for _ in board_id)
                        where_clause += f" AND p.board_id IN ({placeholders})"
                        params.extend(board_id)
                    else:
                        where_clause += " AND p.board_id = ?"
                        params.append(board_id)
                
                check_board_str = board_id[0] if isinstance(board_id, list) and board_id else board_id
                if check_board_str != 'int':
                    where_clause += " AND (p.stream = ? OR p.stream IS NULL)"
                    params.append(stream)

                if sort_by == "random":
                    ids_query = f"""
                        SELECT p.post_num
                        FROM Posts p
                        LEFT JOIN Threads t ON p.post_num = t.thread_num
                        {where_clause}
                        GROUP BY p.post_num
                    """
                    
                    target_ids_pool = []
                    async with db.execute(ids_query, params) as cursor:
                        async for row in cursor:
                            target_ids_pool.append(row[0])
                    
                    if not target_ids_pool: return []
                    
                    seed_val = int(time.time() / 600)
                    rng = random.Random(seed_val)
                    rng.shuffle(target_ids_pool)
                    
                    target_ids = target_ids_pool[offset : offset + page_size]
                
                else: # bump или new
                    if sort_by == "bump":
                        order_clause = f"ORDER BY {pin_clause} MIN(IFNULL(t.is_archived, 0)) ASC, MAX(IFNULL(t.last_updated_at, p.timestamp)) DESC, p.post_num DESC"
                    else:
                        order_clause = f"ORDER BY {pin_clause} p.timestamp DESC, p.post_num DESC"
                    
                    limit_params = [page_size, offset]
                    ids_query = f"""
                        SELECT p.post_num
                        FROM Posts p
                        LEFT JOIN Threads t ON p.post_num = t.thread_num
                        {where_clause}
                        GROUP BY p.post_num
                        {order_clause}
                        LIMIT ? OFFSET ?
                    """
                    
                    target_ids = []
                    async with db.execute(ids_query, params + limit_params) as cursor:
                        async for row in cursor:
                            val = row['post_num'] if hasattr(row, 'keys') else row[0]
                            target_ids.append(val)
                
                if not target_ids:
                    return []
                
                id_placeholders = ','.join('?' for _ in target_ids)
                data_query = f"""
                    SELECT 
                        p.post_num, p.board_id, p.thread_id, p.content, p.timestamp, p.author_id, p.stream, p.is_shadow,
                        MAX(t.is_archived) as is_archived, 
                        MAX(t.is_pinned) as is_pinned,
                        MAX(t.thread_type) as thread_type,
                        MAX(t.is_endless) as is_endless
                    FROM Posts p
                    LEFT JOIN Threads t ON p.post_num = t.thread_num
                    WHERE p.post_num IN ({id_placeholders})
                    GROUP BY p.post_num
                """
                posts_map = {} 
                real_thread_id_map = {} 
                
                async with db.execute(data_query, target_ids) as cursor:
                    columns = [desc[0] for desc in cursor.description]
                    async for row in cursor:
                        if hasattr(row, 'keys'):
                            pd = dict(row)
                        else:
                            pd = dict(zip(columns, row))
                        pid = int(pd.pop('post_num'))
                        raw_tid = pd.get('thread_id')
                        if raw_tid:
                            clean_tid_str = str(raw_tid).strip()
                            real_thread_id_map[clean_tid_str] = pid
                            if clean_tid_str.isdigit():
                                real_thread_id_map[int(clean_tid_str)] = pid
                        
                        try:
                            pd['id'] = pid
                            pd['content'] = json.loads(pd['content'])
                            pd['is_archived'] = bool(pd.get('is_archived', 0))
                            pd['is_pinned'] = bool(pd.get('is_pinned', 0))
                            pd['is_endless'] = bool(pd.get('is_endless', 0))
                            pd['reply_count'] = 0
                            pd['anon_count'] = 1
                            pd['latest_replies'] = []
                            posts_map[pid] = pd
                        except: 
                            continue
                            
                for pid in target_ids:
                    if pid in posts_map:
                        op_posts.append(posts_map[pid])
                        
                all_possible_thread_ids = list(real_thread_id_map.keys())
                all_possible_thread_ids.extend(target_ids)
                valid_tids_str = [f"'{str(x)}'" for x in all_possible_thread_ids if x]
                
                if valid_tids_str:
                    in_clause = ",".join(valid_tids_str)
                    replies_fetch_query = f"""
                        SELECT post_num, board_id, thread_id, reply_to_post_num, author_id, content, timestamp
                        FROM Posts
                        WHERE (
                            thread_id IN ({in_clause}) 
                            OR reply_to_post_num IN ({id_placeholders})
                        )
                        AND (IFNULL(is_shadow, 0) = 0 OR author_id = {viewer_id})
                        ORDER BY post_num ASC
                    """
                    async with db.execute(replies_fetch_query, target_ids) as cursor:
                        rep_columns = [desc[0] for desc in cursor.description]
                        async for row in cursor:
                            try:
                                if hasattr(row, 'keys'): r_data = row
                                else: r_data = dict(zip(rep_columns, row))
                                p_num = int(r_data['post_num'])
                                if p_num in posts_map: continue
                                t_id_raw = r_data['thread_id']
                                r_to_raw = r_data['reply_to_post_num']
                                parent_id = None
                                if t_id_raw:
                                    if t_id_raw in real_thread_id_map: parent_id = real_thread_id_map[t_id_raw]
                                    else:
                                        t_str = str(t_id_raw).strip()
                                        if t_str in real_thread_id_map: parent_id = real_thread_id_map[t_str]
                                if parent_id is None and r_to_raw:
                                    try:
                                        rid = int(str(r_to_raw).strip())
                                        if rid in posts_map: parent_id = rid
                                    except: pass
                                if parent_id is not None:
                                    target = posts_map[parent_id]
                                    target['reply_count'] += 1
                                    if '_authors' not in target: target['_authors'] = {target['author_id']}
                                    target['_authors'].add(r_data['author_id'])
                                    reply_obj = {
                                        'id': p_num,
                                        'board_id': r_data['board_id'],
                                        'thread_id': r_data['thread_id'],
                                        'content': json.loads(r_data['content']),
                                        'timestamp': r_data['timestamp'],
                                        'author_id': r_data['author_id']
                                    }
                                    if '_all_replies' not in target: target['_all_replies'] = []
                                    target['_all_replies'].append(reply_obj)
                            except Exception: continue
                            
                for post in op_posts:
                    if '_authors' in post: post['anon_count'] = len(post.pop('_authors'))
                    if '_all_replies' in post:
                        all_reps = post.pop('_all_replies')
                        post['latest_replies'] = all_reps[-reply_limit:]
                return op_posts
                
            except Exception as e:
                if attempt < 2:
                    await asyncio.sleep(0.2 * (attempt + 1))
                    continue
                else:
                    print(f"⛔ Error in get_op_posts_for_board after 3 attempts: {e}")
                    return []
    return []
async def get_thread_by_op_post(op_post_num: int, current_user_id: int = None):
    from common.db_pool import get_pool, db_lock
    
    # --- ФАЗА 1: СБОР ДАННЫХ (БЛОКИРУЮЩАЯ, НО БЫСТРАЯ) ---
    raw_op_data = None
    raw_replies_data = []
    raw_crosslinks_data = []
    
    for attempt in range(10):
        try:
            async with db_lock:
                db = await get_pool()
                
                # 1. Забираем ОП-пост
                op_post_query = """
                    SELECT p.post_num, p.content, p.timestamp, p.author_id, p.board_id, 
                           p.reply_to_post_num, p.is_shadow, p.is_op_hidden,
                           t.is_endless, t.is_pinned
                    FROM Posts p
                    LEFT JOIN Threads t ON p.post_num = t.thread_num
                    WHERE p.post_num = ?
                """
                async with db.execute(op_post_query, (op_post_num,)) as cursor:
                    row = await cursor.fetchone()
                    if row:
                        cols = [d[0] for d in cursor.description]
                        if hasattr(row, 'keys'):
                            raw_op_data = dict(row)
                        else:
                            raw_op_data = dict(zip(cols, row))

                if not raw_op_data:
                    return None
                
                if raw_op_data['is_shadow'] and raw_op_data['author_id'] != current_user_id:
                    return None

                # 2. Забираем ответы
                viewer_id = current_user_id if current_user_id else -1
                replies_query = """
                    SELECT post_num, content, timestamp, author_id, board_id, reply_to_post_num, is_shadow, is_op_hidden
                    FROM Posts 
                    WHERE thread_id = ? 
                      AND post_num != ?
                      AND (is_shadow = 0 OR author_id = ?)
                    ORDER BY timestamp ASC
                """
                raw_replies_data = []
                async with db.execute(replies_query, (str(op_post_num), op_post_num, viewer_id)) as cursor:
                    rep_cols = [d[0] for d in cursor.description]
                    async for row in cursor:
                        if hasattr(row, 'keys'):
                            rd = dict(row)
                        else:
                            rd = dict(zip(rep_cols, row))
                        raw_replies_data.append(rd)

                # 3. Забираем CrossLinks
                all_ids = [raw_op_data['post_num']] + [r['post_num'] for r in raw_replies_data]
                
                raw_crosslinks_data = []
                if all_ids:
                    placeholders = ','.join('?' for _ in all_ids)
                    board_id = raw_op_data['board_id']
                    
                    q_links = f"""
                        SELECT source_board, source_post, target_post 
                        FROM CrossLinks 
                        WHERE target_board = ? AND target_post IN ({placeholders})
                    """
                    params = [board_id] + all_ids
                    async with db.execute(q_links, params) as cursor:
                        async for row in cursor:
                            raw_crosslinks_data.append(row)
            break 
        except sqlite3.OperationalError as e:
            if "locked" in str(e).lower() or "busy" in str(e).lower():
                await asyncio.sleep(0.1 * (attempt + 1))
                if attempt == 9:
                    print(f"Error in get_thread_by_op_post (DB Phase) after retries: {e}")
                    return None
                continue
            print(f"Error in get_thread_by_op_post (DB Phase): {e}")
            return None
        except Exception as e:
            print(f"Error in get_thread_by_op_post (DB Phase): {e}")
            return None

    # --- ФАЗА 2: ОБРАБОТКА ДАННЫХ (БЕЗ БЛОКИРОВКИ) ---
    try:
        op_post = raw_op_data
        op_post['id'] = op_post['post_num']
        try:
            op_post['content'] = json.loads(op_post['content'])
        except:
            op_post['content'] = {"text": "", "type": "text"}
        op_post['thread_id'] = op_post['id']
        
        if current_user_id:
            op_post['is_op_yours'] = (op_post['author_id'] == current_user_id)

        # Обработка ответов
        replies = []
        for rd in raw_replies_data:
            try:
                rd['id'] = rd['post_num']
                try:
                    rd['content'] = json.loads(rd['content'])
                except:
                    rd['content'] = {"text": "", "type": "text"}
                rd['thread_id'] = op_post_num
                if current_user_id:
                    rd['is_yours'] = (rd['author_id'] == current_user_id)
                    rd['is_by_op'] = (rd['author_id'] == op_post['author_id'])
                replies.append(rd)
            except: continue

        all_posts = [op_post] + replies
        backlinks_map = defaultdict(set)
        thread_ids = set(p['id'] for p in all_posts)
        
        for p in all_posts:
            if p.get('reply_to_post_num') and p['reply_to_post_num'] in thread_ids:
                backlinks_map[p['reply_to_post_num']].add(p['id'])
    
            txt = p.get('content', {}).get('text', '')
            if txt:
                refs = re.findall(r'(?:>>|&gt;&gt;)(\d+)', txt)
                for ref in refs:
                    rid = int(ref)
                    if rid in thread_ids and rid != p['id']:
                        backlinks_map[rid].add(p['id'])

        for p in all_posts:
            p['backlinks'] = sorted(list(backlinks_map[p['id']])) if p['id'] in backlinks_map else []
        links_map = defaultdict(list)
        for row in raw_crosslinks_data:
            s_board, s_post, t_post = row
            links_map[t_post].append({'board': s_board, 'post': s_post})
        
        for p in all_posts:
            if p['id'] in links_map:
                p['external_links'] = links_map[p['id']]

        return op_post, replies

    except Exception as e:
        print(f"Error in get_thread_by_op_post (Processing Phase): {e}")
        return None
async def is_thread_archived(thread_op_num: int) -> bool:
    """
    Проверяет, архивирован ли тред или удален.
    Использует цикл попыток для защиты от блокировок БД.
    """
    from common.db_pool import get_pool, db_lock
    
    async with db_lock:
        for attempt in range(10):
            try:
                db = await get_pool()
                query = "SELECT is_archived FROM Threads WHERE thread_num = ? LIMIT 1"
                async with db.execute(query, (thread_op_num,)) as cursor:
                    row = await cursor.fetchone()
                if row:
                    return bool(row[0])
                return True # Если записи нет, считаем архивным/удаленным
            except sqlite3.OperationalError as e:
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    await asyncio.sleep(0.1 * (attempt + 1))
                    continue
                break
            except Exception:
                break
    return True

async def get_chat_posts_for_board(board_id: str, offset: int = 0, stream: str = 'ru', observer_id: int = None) -> list:
    from common.db_pool import get_pool, db_lock
    
    async with db_lock:
        try:
            db = await get_pool()
            db.row_factory = aiosqlite.Row
            viewer_id = observer_id if observer_id is not None else -1
            
            stream_clause = "AND stream = ?" if board_id != 'int' else ""
            params = [board_id]
            if board_id != 'int':
                params.append(stream)
            params.append(offset)
            
            query = f"""
                SELECT post_num, content, timestamp, author_id, board_id, reply_to_post_num, stream
                FROM Posts 
                WHERE board_id = ? 
                AND thread_id IS NULL 
                AND (IFNULL(is_shadow, 0) = 0 OR author_id = {viewer_id})
                {stream_clause}
                ORDER BY timestamp DESC 
                LIMIT 50 OFFSET ?
            """
            posts = []
            async with db.execute(query, params) as cursor:
                columns = [desc[0] for desc in cursor.description]
                async for row in cursor:
                    if hasattr(row, 'keys'):
                        post_data = dict(row)
                    else:
                        post_data = dict(zip(columns, row))
                    post_data['id'] = post_data['post_num']
                    try:
                        post_data['content'] = json.loads(post_data['content'])
                    except: 
                        post_data['content'] = {'text': '', 'type': 'text'}
                    post_data['backlinks'] = []
                    posts.append(post_data)
            
            posts_map = {p['id']: p for p in posts}
            
            for p in posts:
                refs = set()
                if p.get('reply_to_post_num'):
                    refs.add(p['reply_to_post_num'])
                text = p.get('content', {}).get('text', '')
                if text:
                    found = re.findall(r'(?:>>|&gt;&gt;)(\d+)', text)
                    for f in found:
                        refs.add(int(f))
                for ref_id in refs:
                    if ref_id in posts_map:
                        if p['id'] not in posts_map[ref_id]['backlinks']:
                            posts_map[ref_id]['backlinks'].append(p['id'])
            for p in posts:
                p['backlinks'].sort()
            return posts
        except Exception as e:
            print(f"Error in get_chat_posts_for_board: {e}")
            return []
        finally:
            if 'db' in locals() and db:
                db.row_factory = None
async def get_post_by_num(post_num: int) -> Optional[Dict[str, Any]]:
    """
    Получает пост по номеру.
    Использует цикл попыток для обхода блокировок базы данных.
    """
    from common.db_pool import get_pool, db_lock
    
    async with db_lock:
        for attempt in range(10):
            try:
                db = await get_pool()
                async with db.execute("SELECT * FROM Posts WHERE post_num = ? LIMIT 1", (post_num,)) as cursor:
                    row = await cursor.fetchone()
                    if row is None:
                        return None
                    
                    # Безопасное извлечение данных без изменения db.row_factory
                    cols = [d[0] for d in cursor.description]
                    row_data = dict(zip(cols, row))
                
                post_data = _process_site_db_row(row_data)
                if post_data and 'post_num' in post_data:
                    post_data['id'] = post_data['post_num']
                return post_data
                
            except sqlite3.OperationalError as e:
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    await asyncio.sleep(0.1 * (attempt + 1))
                    continue
                break
            except Exception:
                break
    return None
async def get_thread_op_by_post_num(post_num: int) -> Optional[int]:
    from common.db_pool import get_pool, db_lock
    
    async with db_lock:
        for attempt in range(10):
            try:
                db = await get_pool()
                query = "SELECT thread_id, reply_to_post_num FROM Posts WHERE post_num = ? LIMIT 1"
                async with db.execute(query, (post_num,)) as cursor:
                    row = await cursor.fetchone()
                    if row:
                        thread_id, reply_to = row
                        if thread_id:
                            return thread_id
                        if reply_to is None:
                            return post_num
                    return None
            except sqlite3.OperationalError as e:
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    await asyncio.sleep(0.1 * (attempt + 1))
                    continue
                break
            except Exception:
                break
    return None
async def get_post_count_in_thread(thread_op_num: int) -> int:
    from common.db_pool import get_pool, db_lock
    
    async with db_lock:
        for attempt in range(10):
            try:
                db = await get_pool()
                query = "SELECT COUNT(*) FROM Posts WHERE thread_id = ? AND IFNULL(is_shadow, 0) = 0"
                async with db.execute(query, (str(thread_op_num),)) as cursor:
                    row = await cursor.fetchone()
                    return row[0] if row else 0
            except sqlite3.OperationalError as e:
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    await asyncio.sleep(0.1 * (attempt + 1))
                    continue
                break
            except Exception:
                break
    return 0
async def archive_thread_in_db(thread_op_num: int):
    """
    Помечает тред как архивный.
    """
    from common.db_pool import get_pool, db_lock
    
    async with db_lock:
        for attempt in range(10):
            try:
                db = await get_pool()
                await db.execute("BEGIN IMMEDIATE")
                
                await db.execute("UPDATE Threads SET is_archived = 1 WHERE thread_num = ?", (thread_op_num,))
                
                await db.execute("COMMIT")
                return
            except sqlite3.OperationalError as e:
                try: await db.execute("ROLLBACK")
                except: pass
                
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    await asyncio.sleep(0.1 * (attempt + 1))
                    continue
                print(f"⚠️ Error archiving thread {thread_op_num}: {e}")
                break
            except Exception as e:
                try: await db.execute("ROLLBACK")
                except: pass
                print(f"⚠️ Error archiving thread {thread_op_num}: {e}")
                break
async def create_thread_entry(
    thread_op_num: int, 
    board_id: str, 
    op_id: int, 
    title: str, 
    timestamp: float,
    stream: str = 'ru',
    thread_type: str = 'default'
) -> bool:
    """
    Создает ПОЛНУЮ запись для нового треда (используется сайтом/импортером).
    """
    from common.db_pool import get_pool, db_lock
    
    async with db_lock:
        for attempt in range(10):
            try:
                db = await get_pool()
                await db.execute("BEGIN IMMEDIATE")
                
                # Обновляем пост (делаем его ОП-постом)
                await db.execute("UPDATE Posts SET thread_id = ? WHERE post_num = ?", (thread_op_num, thread_op_num))
                
                # Создаем запись о треде
                await db.execute(
                    """
                    INSERT OR IGNORE INTO Threads 
                    (thread_id, thread_num, board_id, op_id, title, created_at, last_updated_at, is_archived, stream, thread_type) 
                    VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
                    """,
                    (thread_op_num, thread_op_num, board_id, op_id, title, timestamp, timestamp, stream, thread_type)
                )
                
                if thread_type != 'default':
                     await db.execute("INSERT OR IGNORE INTO ThreadUnlocks (thread_id, user_id) VALUES (?, ?)", (thread_op_num, op_id))
                     
                await db.execute("COMMIT")
                return True
                
            except sqlite3.OperationalError as e:
                try: await db.execute("ROLLBACK")
                except: pass
                
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    await asyncio.sleep(0.1 * (attempt + 1))
                    continue
                print(f"Критическая ошибка при создании записи для треда #{thread_op_num}: {e}")
                break
            except Exception as e:
                try: await db.execute("ROLLBACK")
                except: pass
                print(f"Критическая ошибка при создании записи для треда #{thread_op_num}: {e}")
                break
            
    return False
async def process_mentions_and_notify(source_post_num: int, board_id: str, text: str, author_id: int, reply_to_ui: int = None):
    """
    Парсит текст на наличие ссылок >>12345 и создает уведомления.
    """
    mentions = set(re.findall(r'(?:>>|&gt;&gt;)(\d+)', text))
    if reply_to_ui:
        mentions.add(str(reply_to_ui))
    if not mentions:
        return

    from common.db_pool import get_pool, db_lock
    
    params = list(mentions)
    params.append(board_id)
    placeholders = ','.join('?' for _ in mentions)
    current_time = time.time()

    async with db_lock:
        for attempt in range(10):
            try:
                db = await get_pool()
                await db.execute("BEGIN IMMEDIATE")
                
                notifications_to_insert = []
                
                # 1. Находим получателей
                query = f"SELECT post_num, author_id, thread_id FROM Posts WHERE post_num IN ({placeholders}) AND board_id = ?"
                async with db.execute(query, params) as cursor:
                    async for row in cursor:
                        ref_post_num, recipient_id, thread_id = row
                        if recipient_id > 0 and recipient_id != author_id:
                            # FIX: Если thread_id is None (чат), используем ID поста, на который отвечаем (ref_post_num)
                            effective_tid = thread_id if thread_id is not None else ref_post_num
                            notifications_to_insert.append((
                                recipient_id, 
                                source_post_num, 
                                ref_post_num, 
                                board_id, 
                                effective_tid,
                                current_time
                            ))
                if notifications_to_insert:
                    await db.executemany(
                        """INSERT INTO NotificationQueue 
                           (recipient_id, source_post_num, reply_post_num, board_id, thread_id, created_at) 
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        notifications_to_insert
                    )
                    site_notifs = [
                        (r_id, board_id, str(t_id), src_num, rep_num, 0, current_time)
                        for (r_id, src_num, rep_num, _, t_id, _) in notifications_to_insert
                    ]
                    await db.executemany(
                        """INSERT INTO UserReplies 
                           (user_id, board_id, thread_id, post_num, parent_num, is_read, created_at) 
                           VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        site_notifs
                    )
                
                await db.execute("COMMIT")
                return

            except sqlite3.OperationalError as e:
                try: await db.execute("ROLLBACK")
                except: pass
                
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    await asyncio.sleep(0.1 * (attempt + 1))
                    continue
                print(f"⛔ Error processing mentions: {e}")
                break
            except Exception as e:
                try: await db.execute("ROLLBACK")
                except: pass
                print(f"⛔ Error processing mentions: {e}")
                break
async def get_user_posts_from_list(user_id: int, post_nums: List[int]) -> List[int]:
    if not post_nums: return []
    db = await get_pool()
    try:
        placeholders = ','.join('?' for _ in post_nums)
        query = f"SELECT post_num FROM Posts WHERE author_id = ? AND post_num IN ({placeholders})"
        params = [user_id] + post_nums
        async with db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]
    except Exception:
        return []
async def delete_post_by_num(post_num: int) -> bool:
    """
    Атомарно удаляет пост или весь тред.
    """
    from common.db_pool import get_pool, db_lock
    
    post_id_str = str(post_num)
    post_id_int = int(post_num)
    
    async with db_lock:
        for attempt in range(10):
            try:
                db = await get_pool()
                # Сначала BEGIN IMMEDIATE, потом чтение
                await db.execute("BEGIN IMMEDIATE")
                
                # Проверяем, тред ли это
                async with db.execute("SELECT 1 FROM Threads WHERE thread_id = ? LIMIT 1", (post_id_str,)) as cursor:
                    is_thread = await cursor.fetchone() is not None
                
                if is_thread:
                    print(f"🗑️ [DB] Удаление ТРЕДА #{post_num}...")
                    await db.execute("DELETE FROM Threads WHERE thread_id = ?", (post_id_str,))
                    await db.execute("DELETE FROM Posts WHERE thread_id = ?", (post_id_str,))
                    await db.execute("DELETE FROM UserReplies WHERE thread_id = ?", (post_id_str,))
                    # Мгновенная очистка кэша тредов
                    for b in _THREAD_CACHE:
                        if post_id_str in _THREAD_CACHE[b]: _THREAD_CACHE[b].remove(post_id_str)
                else:
                    print(f"🗑️ [DB] Удаление ПОСТА #{post_num}...")
                    await db.execute("DELETE FROM Posts WHERE post_num = ?", (post_id_int,))
                    await db.execute("DELETE FROM UserReplies WHERE post_num = ? OR parent_num = ?", (post_id_int, post_id_int))
                
                # Мгновенная очистка медиа-кэша (удаляем все вхождения этого поста)
                for b in _VIDEO_CACHE:
                    _VIDEO_CACHE[b] = [item for item in _VIDEO_CACHE[b] if item[0] != post_id_int]
                for b in _IMAGE_CACHE:
                    _IMAGE_CACHE[b] = [item for item in _IMAGE_CACHE[b] if item[0] != post_id_int]
                
                await db.execute("COMMIT")
                return True
                
            except sqlite3.OperationalError as e:
                try: await db.execute("ROLLBACK")
                except: pass
                
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    await asyncio.sleep(0.1 * (attempt + 1))
                    continue
                print(f"⛔ КРИТИЧЕСКАЯ ОШИБКА при удалении #{post_num}: {e}")
                break
            except Exception as e:
                try: await db.execute("ROLLBACK")
                except: pass
                print(f"⛔ КРИТИЧЕСКАЯ ОШИБКА при удалении #{post_num}: {e}")
                break
            
    return False
async def ban_user_on_board(user_id: int, board_id: str) -> bool:
    """
    Устанавливает статус 'banned' для пользователя на указанной доске.
    """
    from common.db_pool import get_pool, db_lock
    
    async with db_lock:
        for attempt in range(10):
            try:
                db = await get_pool()
                await db.execute("BEGIN IMMEDIATE")
                
                await db.execute(
                    "INSERT OR IGNORE INTO Users (user_id, board_id) VALUES (?, ?)",
                    (user_id, board_id)
                )
                await db.execute(
                    "UPDATE Users SET status = ? WHERE user_id = ? AND board_id = ?",
                    ("banned", user_id, board_id)
                )
                
                await db.execute("COMMIT")
                return True
                
            except sqlite3.OperationalError as e:
                try: await db.execute("ROLLBACK")
                except: pass
                
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    await asyncio.sleep(0.1 * (attempt + 1))
                    continue
                print(f"Критическая ошибка при бане user #{user_id} на доске {board_id}: {e}")
                break
            except Exception as e:
                try: await db.execute("ROLLBACK")
                except: pass
                print(f"Критическая ошибка при бане user #{user_id} на доске {board_id}: {e}")
                break
            
    return False
async def update_post_content(post_num: int, content: dict):
    """
    Обновляет поле content для существующего поста в базе данных.
    Добавлен механизм retries и явные транзакции (BEGIN IMMEDIATE).
    """
    from common.db_pool import get_pool, db_lock
    content_json = json.dumps(content, default=_json_serializer)
    
    async with db_lock:
        for attempt in range(10):
            try:
                db = await get_pool()
                await db.execute("BEGIN IMMEDIATE")
                
                await db.execute(
                    "UPDATE Posts SET content = ? WHERE post_num = ?",
                    (content_json, post_num)
                )
                
                await db.execute("COMMIT")
                return
            except sqlite3.OperationalError as e:
                try: await db.execute("ROLLBACK")
                except: pass
                
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    await asyncio.sleep(0.1 * (attempt + 1))
                    continue
                print(f"⛔ КРИТИЧЕСКАЯ ОШИБКА при обновлении контента поста #{post_num}: {e}")
                break
            except Exception as e:
                try: await db.execute("ROLLBACK")
                except: pass
                print(f"⛔ КРИТИЧЕСКАЯ ОШИБКА при обновлении контента поста #{post_num}: {e}")
                break
async def add_post_copies(post_num: int, copies_data: list[tuple[int, int]]):
    """
    Сохраняет информацию об отправленных копиях поста в базу данных.
    """
    if not copies_data:
        return
        
    from common.db_pool import get_pool, db_lock
    
    data_to_insert = [(post_num, recipient_id, msg_id) for recipient_id, msg_id in copies_data]
    
    async with db_lock:
        for attempt in range(10):
            try:
                db = await get_pool()
                await db.execute("BEGIN IMMEDIATE")
                
                await db.executemany(
                    "INSERT OR IGNORE INTO PostCopies (post_num, recipient_id, message_id) VALUES (?, ?, ?)",
                    data_to_insert
                )
                
                await db.execute("COMMIT")
                return
            except sqlite3.OperationalError as e:
                try: await db.execute("ROLLBACK")
                except: pass
                
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    await asyncio.sleep(0.1 * (attempt + 1))
                    continue
                print(f"⛔ КРИТИЧЕСКАЯ ОШИБКА при сохранении копий поста #{post_num} в БД: {e}")
                break
            except Exception as e:
                try: await db.execute("ROLLBACK")
                except: pass
                print(f"⛔ КРИТИЧЕСКАЯ ОШИБКА при сохранении копий поста #{post_num} в БД: {e}")
                break
async def get_post_author_by_copy(recipient_id: int, message_id: int) -> int | None:
    """
    Находит ID автора оригинального поста по ID копии сообщения.
    """
    from common.db_pool import get_pool, db_lock
    
    async with db_lock:
        try:
            db = await get_pool()
            query = """
                SELECT p.author_id
                FROM Posts p
                JOIN PostCopies pc ON p.post_num = pc.post_num
                WHERE pc.recipient_id = ? AND pc.message_id = ?
            """
            async with db.execute(query, (recipient_id, message_id)) as cursor:
                result = await cursor.fetchone()
                return result[0] if result else None
        except Exception:
            return None
@overload
async def get_post_copies(post_num: int) -> list[tuple[int, int]]: ...

@overload
async def get_post_copies(post_num: list[int]) -> dict[int, list[tuple[int, int]]]: ...

async def get_post_copies(post_num: int | list[int]) -> list[tuple[int, int]] | dict[int, list[tuple[int, int]]]:
    """
    Возвращает список всех копий для указанного поста,
    либо словарь со списками копий для нескольких постов.
    """
    from common.db_pool import get_pool, db_lock
    
    if isinstance(post_num, list):
        if not post_num:
            return {}
        async with db_lock:
            try:
                db = await get_pool()
                placeholders = ','.join('?' for _ in post_num)
                query = f"SELECT post_num, recipient_id, message_id FROM PostCopies WHERE post_num IN ({placeholders})"

                result = {num: [] for num in post_num}
                async with db.execute(query, post_num) as cursor:
                    rows = await cursor.fetchall()
                    for p_num, recipient_id, message_id in rows:
                        result[p_num].append((recipient_id, message_id))
                return result
            except Exception:
                return {num: [] for num in post_num}

    async with db_lock:
        try:
            db = await get_pool()
            query = "SELECT recipient_id, message_id FROM PostCopies WHERE post_num = ?"
            async with db.execute(query, (post_num,)) as cursor:
                return await cursor.fetchall()
        except Exception:
            return []
async def upsert_delivery_queue_item(
    board_id: str,
    post_num: int,
    recipients: list[int],
    content: dict,
    delivery_phase: str = "passive",
    original_recipients: int = 0,
    thread_id: str | None = None,
    enqueued_at: float | None = None,
) -> int | None:
    """
    Stores one durable delivery phase. This is intentionally coarse-grained:
    PostCopies remains the source of truth for already delivered recipients.
    """
    from common.db_pool import get_pool, db_lock

    try:
        clean_recipients = sorted({int(uid) for uid in recipients if int(uid) > 0})
    except Exception:
        return None
    if not clean_recipients:
        return None
    try:
        recipients_json = json.dumps(clean_recipients, ensure_ascii=False, separators=(",", ":"))
        content_json = json.dumps(content, default=_json_serializer, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError) as e:
        print(f"⚠️ DeliveryQueue serialize failed for #{post_num}: {type(e).__name__}: {e}")
        return None

    now = time.time()
    created_at = float(enqueued_at or now)
    phase = str(delivery_phase or "passive")
    async with db_lock:
        for attempt in range(10):
            try:
                db = await get_pool()
                await db.execute("BEGIN IMMEDIATE")
                query = """
                    SELECT id
                    FROM DeliveryQueue
                    WHERE status = 'pending'
                      AND board_id = ?
                      AND post_num = ?
                      AND delivery_phase = ?
                    ORDER BY id
                    LIMIT 1
                """
                async with db.execute(query, (board_id, post_num, phase)) as cursor:
                    row = await cursor.fetchone()
                if row:
                    item_id = int(row[0])
                    await db.execute(
                        """
                        UPDATE DeliveryQueue
                        SET recipients = ?,
                            content = ?,
                            original_recipients = ?,
                            thread_id = ?,
                            enqueued_at = ?,
                            updated_at = ?,
                            attempts = attempts + 1,
                            status = 'pending'
                        WHERE id = ?
                        """,
                        (
                            recipients_json,
                            content_json,
                            int(original_recipients or len(clean_recipients)),
                            str(thread_id) if thread_id is not None else None,
                            created_at,
                            now,
                            item_id,
                        ),
                    )
                else:
                    cursor = await db.execute(
                        """
                        INSERT INTO DeliveryQueue (
                            board_id, post_num, recipients, content, delivery_phase,
                            original_recipients, thread_id, enqueued_at, updated_at,
                            attempts, status
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 'pending')
                        """,
                        (
                            board_id,
                            int(post_num),
                            recipients_json,
                            content_json,
                            phase,
                            int(original_recipients or len(clean_recipients)),
                            str(thread_id) if thread_id is not None else None,
                            created_at,
                            now,
                        ),
                    )
                    item_id = int(cursor.lastrowid)
                await db.execute("COMMIT")
                return item_id
            except sqlite3.OperationalError as e:
                try: await db.execute("ROLLBACK")
                except: pass
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    await asyncio.sleep(0.1 * (attempt + 1))
                    continue
                print(f"⚠️ DeliveryQueue upsert failed for #{post_num}: {e}")
                break
            except Exception as e:
                try: await db.execute("ROLLBACK")
                except: pass
                print(f"⚠️ DeliveryQueue upsert failed for #{post_num}: {type(e).__name__}: {e}")
                break
    return None
async def delete_delivery_queue_item(item_id: int) -> bool:
    from common.db_pool import get_pool, db_lock

    if not item_id:
        return False
    async with db_lock:
        for attempt in range(10):
            try:
                db = await get_pool()
                await db.execute("BEGIN IMMEDIATE")
                await db.execute("DELETE FROM DeliveryQueue WHERE id = ?", (int(item_id),))
                await db.execute("COMMIT")
                return True
            except sqlite3.OperationalError as e:
                try: await db.execute("ROLLBACK")
                except: pass
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    await asyncio.sleep(0.1 * (attempt + 1))
                    continue
                print(f"⚠️ DeliveryQueue delete failed id={item_id}: {e}")
                break
            except Exception as e:
                try: await db.execute("ROLLBACK")
                except: pass
                print(f"⚠️ DeliveryQueue delete failed id={item_id}: {type(e).__name__}: {e}")
                break
    return False
async def get_pending_delivery_queue_items(limit: int = 500) -> list[dict]:
    from common.db_pool import get_pool, db_lock

    safe_limit = max(1, min(int(limit or 500), 5000))
    async with db_lock:
        try:
            db = await get_pool()
            query = """
                SELECT id, board_id, post_num, recipients, content, delivery_phase,
                       original_recipients, thread_id, enqueued_at, updated_at, attempts
                FROM DeliveryQueue
                WHERE status = 'pending'
                ORDER BY id
                LIMIT ?
            """
            async with db.execute(query, (safe_limit,)) as cursor:
                rows = await cursor.fetchall()
        except Exception as e:
            print(f"⚠️ DeliveryQueue restore read failed: {type(e).__name__}: {e}")
            return []
    items = []
    for row in rows:
        try:
            recipients = json.loads(row[3])
            content = json.loads(row[4])
            items.append(
                {
                    "id": int(row[0]),
                    "board_id": row[1],
                    "post_num": int(row[2]),
                    "recipients": [int(uid) for uid in recipients],
                    "content": content,
                    "delivery_phase": row[5],
                    "original_recipients": int(row[6] or 0),
                    "thread_id": row[7],
                    "enqueued_at": float(row[8] or time.time()),
                    "updated_at": float(row[9] or 0),
                    "attempts": int(row[10] or 0),
                }
            )
        except Exception as e:
            print(f"⚠️ DeliveryQueue row decode failed id={row[0] if row else '?'}: {type(e).__name__}: {e}")
    return items
async def get_posts_from_broadcast_queue(last_timestamp: float) -> tuple[list[dict], float]:
    """
    Извлекает все посты из очереди.
    Исправлена ошибка с dict(row).
    """
    db = await get_pool()
    try:
        query = "SELECT post_num, created_at FROM BroadcastQueue WHERE created_at > ?"
        async with db.execute(query, (last_timestamp,)) as cursor:
            rows = await cursor.fetchall() 
        if not rows:
            return [], last_timestamp
        post_nums = [row[0] for row in rows]
        max_created_at = max(row[1] for row in rows)
        placeholders = ','.join('?' for _ in post_nums)
        posts_query = f"SELECT * FROM Posts WHERE post_num IN ({placeholders}) ORDER BY timestamp ASC"
        processed_posts = []
        async with db.execute(posts_query, post_nums) as cursor:
            columns = [description[0] for description in cursor.description]
            posts_data = await cursor.fetchall()
            for post_row in posts_data:
                post_dict = dict(zip(columns, post_row))
                if 'post_num' not in post_dict: continue
                try:
                    if isinstance(post_dict.get('content'), str):
                        post_dict['content'] = json.loads(post_dict['content'])
                    processed_posts.append(post_dict)
                except (json.JSONDecodeError, TypeError):
                    continue
        return processed_posts, max_created_at
    except Exception as e:
        print(f"⛔ ОШИБКА в get_posts_from_broadcast_queue: {e}")
        return [], last_timestamp
async def get_post_for_broadcast(post_num: int) -> Optional[Dict[str, Any]]:
    """
    Получает полные данные поста для WebSocket.
    Использует цикл попыток при блокировке базы.
    """
    from common.db_pool import get_pool, db_lock
    
    async with db_lock:
        for attempt in range(10):
            try:
                db = await get_pool()
                query = """
                    SELECT p.*, 
                           t.title as thread_title, t.is_endless, t.is_pinned, t.is_archived, t.thread_type,
                           (SELECT COUNT(*) - 1 FROM Posts WHERE thread_id = t.thread_id) as reply_count,
                           (SELECT COUNT(DISTINCT author_id) FROM Posts WHERE thread_id = p.thread_id OR (p.thread_id IS NULL AND post_num = p.post_num)) as anon_count
                    FROM Posts p
                    LEFT JOIN Threads t ON (CASE WHEN p.thread_id IS NOT NULL THEN p.thread_id ELSE CAST(p.post_num AS TEXT) END) = t.thread_id
                    WHERE p.post_num = ? AND IFNULL(p.is_shadow, 0) = 0
                    LIMIT 1
                """
                async with db.execute(query, (post_num,)) as cursor:
                    row = await cursor.fetchone()
                    if not row:
                        return None
                    
                    cols = [d[0] for d in cursor.description]
                    post_dict = dict(zip(cols, row))
                
                post_dict['id'] = post_dict.pop('post_num')
                post_dict['is_op_post'] = str(post_dict.get('thread_id')) == str(post_dict.get('id'))
                
                try:
                    if isinstance(post_dict.get('content'), str):
                        post_dict['content'] = json.loads(post_dict['content'])
                except (json.JSONDecodeError, TypeError):
                    post_dict['content'] = {'text': '[Ошибка данных]', 'type': 'text'}
                    
                return post_dict
                
            except sqlite3.OperationalError as e:
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    await asyncio.sleep(0.1 * (attempt + 1))
                    continue
                break
            except Exception:
                break
    return None
async def cleanup_broadcast_queue(retention_hours: int = 1):
    """
    Удаляет старые записи из BroadcastQueue.
    """
    from common.db_pool import get_pool, db_lock
    cutoff_timestamp = time.time() - (retention_hours * 3600)
    
    async with db_lock:
        for attempt in range(10):
            try:
                db = await get_pool()
                await db.execute("BEGIN IMMEDIATE")
                
                await db.execute("DELETE FROM BroadcastQueue WHERE created_at < ?", (cutoff_timestamp,))
                
                await db.execute("COMMIT")
                return
            except sqlite3.OperationalError as e:
                try: await db.execute("ROLLBACK")
                except: pass
                
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    await asyncio.sleep(0.5 * (attempt + 1))
                    continue
                print(f"⛔ ОШИБКА в cleanup_broadcast_queue: {e}.")
                break
            except Exception as e:
                try: await db.execute("ROLLBACK")
                except: pass
                print(f"⛔ ОШИБКА в cleanup_broadcast_queue: {e}.")
                break
async def get_and_clear_broadcast_queue() -> list[dict]:
    """
    Атомарно извлекает новые посты для бота.
    Статус отправки выставляется отдельно через mark_broadcast_posts_sent()
    только после того, как бот смог обработать запись.
    """
    from common.db_pool import get_pool, db_lock
    
    async with db_lock:
        for attempt in range(10):
            try:
                db = await get_pool()
                await db.execute("BEGIN IMMEDIATE")
                
                # 1. Читаем ID
                async with db.execute("SELECT post_num FROM BroadcastQueue WHERE is_sent_to_tg = 0") as cursor:
                    rows = await cursor.fetchall()
                
                if not rows:
                    await db.execute("COMMIT")
                    return []
                    
                post_nums = [row[0] for row in rows]
                placeholders = ','.join('?' for _ in post_nums)
                
                # 2. Читаем контент постов
                post_query = f"SELECT * FROM Posts WHERE post_num IN ({placeholders})"
                # Используем execute напрямую, так как мы внутри транзакции
                async with db.execute(post_query, post_nums) as post_cursor:
                    columns = [description[0] for description in post_cursor.description]
                    posts_data = await post_cursor.fetchall()
                
                await db.execute("COMMIT")
                
                # Обработка данных (уже вне транзакции, в памяти)
                processed_posts = []
                for post_row in posts_data:
                    post_dict = dict(zip(columns, post_row))
                    try:
                        if isinstance(post_dict.get('content'), str):
                            post_dict['content'] = json.loads(post_dict['content'])
                    except (json.JSONDecodeError, TypeError):
                        post_dict['content'] = {}
                        post_dict['_broadcast_decode_failed'] = True
                    processed_posts.append(post_dict)
                        
                return processed_posts

            except sqlite3.OperationalError as e:
                try: await db.execute("ROLLBACK")
                except: pass
                
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    await asyncio.sleep(0.1 * (attempt + 1))
                    continue
                print(f"⛔ ОШИБКА в get_and_clear_broadcast_queue: {e}")
                break
            except Exception as e:
                try: await db.execute("ROLLBACK")
                except: pass
                print(f"⛔ ОШИБКА в get_and_clear_broadcast_queue: {e}")
                break
            
    return []

async def mark_broadcast_posts_sent(post_nums: list[int] | tuple[int, ...] | set[int]) -> int:
    """Marks broadcast rows as handed off to the bot delivery queue."""
    from common.db_pool import get_pool, db_lock

    clean_post_nums = sorted({int(post_num) for post_num in post_nums if post_num})
    if not clean_post_nums:
        return 0

    async with db_lock:
        for attempt in range(10):
            try:
                db = await get_pool()
                placeholders = ','.join('?' for _ in clean_post_nums)
                cursor = await db.execute(
                    f"UPDATE BroadcastQueue SET is_sent_to_tg = 1 WHERE post_num IN ({placeholders})",
                    clean_post_nums,
                )
                await db.commit()
                return int(cursor.rowcount or 0)
            except sqlite3.OperationalError as e:
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    await asyncio.sleep(0.1 * (attempt + 1))
                    continue
                print(f"⛔ ОШИБКА в mark_broadcast_posts_sent: {e}")
                break
            except Exception as e:
                print(f"⛔ ОШИБКА в mark_broadcast_posts_sent: {e}")
                break
    return 0
async def get_user_by_token(token: str) -> Optional[dict]:
    """
    Находит пользователя по его API токену.
    """
    from common.db_pool import get_pool, db_lock
    
    async with db_lock:
        for attempt in range(10):
            try:
                db = await get_pool()
                async with db.execute("SELECT user_id FROM Users WHERE api_token = ? LIMIT 1", (token,)) as cursor:
                    row = await cursor.fetchone()
                    if not row:
                        return None
                    
                    cols = [d[0] for d in cursor.description]
                    return dict(zip(cols, row))
            except sqlite3.OperationalError as e:
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    await asyncio.sleep(0.1 * (attempt + 1))
                    continue
                break
            except Exception:
                break
    return None
def _process_search_row(row: aiosqlite.Row) -> Optional[Dict[str, Any]]:
    """Вспомогательная функция для обработки строки из БД для поиска."""
    if not row: return None
    try:
        post_dict = dict(row)
        post_dict['id'] = post_dict.pop('post_num')
        raw_content = post_dict.get('content')
        if isinstance(raw_content, str):
            try:
                post_dict['content'] = json.loads(raw_content)
            except json.JSONDecodeError:
                post_dict['content'] = {"text": raw_content, "type": "text"}
        elif not isinstance(raw_content, dict):
             post_dict['content'] = {"text": "", "type": "text"}
        post_dict['reply_to_post_num'] = row['reply_to_post_num']
        return post_dict
    except Exception:
        return None
async def search_posts(query: str, board_id: Optional[str] = None, limit: int = 50, observer_id: Optional[int] = None, only_archived: bool = False) -> list[dict]:
    """
    Выполняет полнотекстовый поиск.
    """
    from common.db_pool import get_pool, db_lock
    
    async with db_lock:
        try:
            db = await get_pool()
            db.row_factory = aiosqlite.Row
            sanitized_query = query.replace('"', '""')
            final_query = f'"{sanitized_query}"'

            viewer_id = observer_id if observer_id is not None else -1
            
            if only_archived:
                sql_query = f"""
                    SELECT p.* FROM Posts p
                    JOIN PostsFTS fts ON p.post_num = fts.rowid
                    JOIN Threads t ON p.thread_id = t.thread_id
                    WHERE fts.content MATCH ? 
                      AND p.thread_id IS NOT NULL 
                      AND t.is_archived = 1
                      AND (IFNULL(p.is_shadow, 0) = 0 OR p.author_id = {viewer_id})
                """
            else:
                sql_query = f"""
                    SELECT p.* FROM Posts p
                    JOIN PostsFTS fts ON p.post_num = fts.rowid
                    WHERE fts.content MATCH ? 
                      AND p.thread_id IS NOT NULL 
                      AND (IFNULL(p.is_shadow, 0) = 0 OR p.author_id = {viewer_id})
                """
            params = [final_query]
            if board_id:
                sql_query += " AND p.board_id = ?"
                params.append(board_id)
            sql_query += " ORDER BY bm25(PostsFTS) LIMIT ?"
            params.append(limit)
            
            async with db.execute(sql_query, params) as cursor:
                rows = await cursor.fetchall()
                cols = [d[0] for d in cursor.description]
            
            results = []
            for row in rows:
                if hasattr(row, 'keys'):
                    row_data = row
                else:
                    row_data = dict(zip(cols, row))
                post = _process_search_row(row_data)
                if post:
                    results.append(post)
            return results
        except Exception as e:
            print(f"⛔ ОШИБКА в search_posts: {e}.")
            return []
        finally:
            if 'db' in locals() and db:
                db.row_factory = None
def cleanup_old_posts_from_db(limit: int = 50000):
    CHAT_COPIES_LIMIT = 5000
    SHADOW_LIFETIME = 24 * 3600
    ARCHIVED_THREAD_LIFETIME = 30 * 24 * 3600
    POST_COPY_RETENTION_SECONDS = max(2 * 24 * 3600, int(POST_COPY_RETENTION_DAYS or 30) * 24 * 3600)
    POST_COPY_RETENTION_LIMIT = max(1000, int(POST_COPY_RETENTION_POSTS or 12000))
    LOGS_LIFETIME = 14 * 24 * 3600
    ALERTS_LIFETIME = 14 * 24 * 3600
    EPHEMERAL_BOARDS = ('thread', 'test') 
    EPHEMERAL_LIMIT = 500
    
    def delete_in_chunks(con, table, where_clause, params, chunk_size=100):
        total_deleted = 0
        con.execute("PRAGMA busy_timeout = 5000;")
        
        while True:
            # Используем IMMEDIATE транзакцию даже в синхронном коде
            try:
                con.execute("BEGIN IMMEDIATE")
                query = f"DELETE FROM {table} WHERE rowid IN (SELECT rowid FROM {table} WHERE {where_clause} LIMIT {chunk_size})"
                cur = con.execute(query, params)
                count = cur.rowcount
                con.execute("COMMIT")
                
                total_deleted += count
                if count < chunk_size:
                    break
                
                # Даем передышку другим процессам
                time.sleep(0.1)
                
            except sqlite3.OperationalError as e:
                try: con.execute("ROLLBACK")
                except: pass
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    time.sleep(1) 
                    continue
                raise e
            except Exception:
                try: con.execute("ROLLBACK")
                except: pass
                break
                
        return total_deleted

    try:
        # isolation_level=None для соответствия архитектуре
        with sqlite3.connect(DB_NAME, timeout=30.0, isolation_level=None) as con:
            con.execute("PRAGMA journal_mode=WAL;")
            con.execute("PRAGMA synchronous = NORMAL;")
            con.execute("PRAGMA foreign_keys = ON;")
            
            # 1. Telegram copy retention. PostCopies are required for real Telegram replies.
            # Keep a bounded rolling window by age and by global post distance; RAM hydration is capped separately.
            copy_cutoff = time.time() - POST_COPY_RETENTION_SECONDS
            row = con.execute(
                "SELECT post_num FROM Posts ORDER BY post_num DESC LIMIT 1 OFFSET ?",
                (POST_COPY_RETENTION_LIMIT,)
            ).fetchone()
            copy_floor_post_num = row[0] if row else 0
            copy_where = "post_num IN (SELECT post_num FROM Posts WHERE timestamp < ? AND post_num < ?)"
            delete_in_chunks(con, "PostCopies", copy_where, (copy_cutoff, copy_floor_post_num))
            delete_in_chunks(con, "ChannelCopies", copy_where, (copy_cutoff, copy_floor_post_num))

            # 2. Логи и алерты
            logs_cutoff = time.time() - LOGS_LIFETIME
            delete_in_chunks(con, "GlobalLogs", "created_at < ?", (logs_cutoff,))
            delete_in_chunks(con, "UserAlerts", "created_at < ?", (time.time() - ALERTS_LIFETIME,))
            replies_cutoff = time.time() - (8 * 24 * 3600)
            delete_in_chunks(con, "UserReplies", "created_at < ?", (replies_cutoff,))
            try:
                con.execute("BEGIN IMMEDIATE")
                hf_cutoff = time.time() - (24 * 3600)
                con.execute("DELETE FROM PendingHF WHERE created_at < ?", (hf_cutoff,))
                hf_orphan_cutoff = time.time() - 3600
                con.execute("""
                    DELETE FROM PendingHF 
                    WHERE created_at < ? 
                    AND file_id NOT IN (SELECT file_id FROM FileRegistry)
                """, (hf_orphan_cutoff,))
                con.execute("DELETE FROM Bottles WHERE timestamp < ?", (logs_cutoff,))
                con.execute("DELETE FROM ImportRequests WHERE created_at < ? AND status != 'pending'", (logs_cutoff,))
                con.execute("DELETE FROM Reports WHERE created_at < ? AND status != 'open'", (logs_cutoff,))
                con.execute("COMMIT")
            except:
                try: con.execute("ROLLBACK")
                except: pass

            # 3. Теневые посты
            shadow_cutoff = time.time() - SHADOW_LIFETIME
            delete_in_chunks(con, "Posts", "is_shadow = 1 AND timestamp < ?", (shadow_cutoff,))

            # 4. Очистка сирот (Orphans)
            cleanup_targets = [
                ("PostCopies", "post_num"), ("ChannelCopies", "post_num"),
                ("BroadcastQueue", "post_num"), ("NotificationQueue", "source_post_num"),
                ("NotificationQueue", "reply_post_num"), ("Reports", "post_num"),
                ("ModQueue", "post_num"), ("PollVotes", "post_num")
            ]
            for table, col in cleanup_targets:
                try:
                    where_fast = f"NOT EXISTS (SELECT 1 FROM Posts WHERE Posts.post_num = {table}.{col})"
                    delete_in_chunks(con, table, where_fast, ())
                except: pass

            # 5. Эфемельные доски
            for board in EPHEMERAL_BOARDS:
                try:
                    row = con.execute(
                        "SELECT post_num FROM Posts WHERE board_id = ? ORDER BY post_num DESC LIMIT 1 OFFSET ?", 
                        (board, EPHEMERAL_LIMIT)
                    ).fetchone()
                    
                    if row:
                        threshold_id = row[0]
                        deleted = delete_in_chunks(
                            con, "Posts", 
                            "board_id = ? AND post_num < ? AND thread_id IS NULL", 
                            (board, threshold_id)
                        )
                        if deleted > 0:
                            print(f"  > Ephemeral cleanup /{board}/: removed {deleted} old posts.")
                except Exception as e:
                    print(f"⚠️ Error cleaning ephemeral board {board}: {e}")

            # 6. Очистка архива тредов
            archive_cutoff = time.time() - ARCHIVED_THREAD_LIFETIME
            tids = [r[0] for r in con.execute("SELECT thread_id FROM Threads WHERE is_archived = 1 AND last_updated_at < ?", (archive_cutoff,)).fetchall()]
            
            if tids:
                chunk_size = 50
                for i in range(0, len(tids), chunk_size):
                    chunk = tids[i:i + chunk_size]
                    placeholders = ",".join("?" * len(chunk))
                    try:
                        con.execute("BEGIN IMMEDIATE")
                        con.execute(f"DELETE FROM Posts WHERE thread_id IN ({placeholders})", chunk)
                        con.execute(f"DELETE FROM Threads WHERE thread_id IN ({placeholders})", chunk)
                        con.execute("COMMIT")
                        time.sleep(0.05)
                    except:
                        try: con.execute("ROLLBACK")
                        except: pass
                print(f"  > Archive: deleted {len(tids)} old threads.")

            # 7. Очистка карты импорта (удаляем маппинг для завершенных задач)
            # Если task_id больше нет в ImportQueue, значит все посты опубликованы, и карта больше не нужна.
            try:
                con.execute("BEGIN IMMEDIATE")
                con.execute("DELETE FROM ImportRefMap WHERE task_id NOT IN (SELECT DISTINCT task_id FROM ImportQueue)")
                deleted_maps = con.total_changes
                con.execute("COMMIT")
                if deleted_maps > 0:
                    print(f"  > Import Cleanup: Cleared {deleted_maps} outdated reference maps.")
            except:
                try: con.execute("ROLLBACK")
                except: pass

    except Exception as e:
        print(f"⛔ DB Cleanup Critical Error: {e}")
async def add_spam_word(board_id: str, word: str) -> bool:
    """
    Добавляет новое стоп-слово для доски в БД.
    """
    from common.db_pool import get_pool, db_lock
    
    async with db_lock:
        for attempt in range(10):
            try:
                db = await get_pool()
                await db.execute("BEGIN IMMEDIATE")
                
                await db.execute(
                    "INSERT OR IGNORE INTO SpamFilterWords (board_id, word) VALUES (?, ?)",
                    (board_id, word.lower())
                )
                
                await db.execute("COMMIT")
                return True
            except sqlite3.OperationalError as e:
                try: await db.execute("ROLLBACK")
                except: pass
                
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    await asyncio.sleep(0.1 * (attempt + 1))
                    continue
                break
            except Exception as e:
                try: await db.execute("ROLLBACK")
                except: pass
                print(f"⛔ ОШИБКА при добавлении стоп-слова в БД: {e}")
                break
    return False

async def remove_spam_word(board_id: str, word: str) -> bool:
    """
    Удаляет стоп-слово для доски из БД.
    """
    from common.db_pool import get_pool, db_lock
    
    async with db_lock:
        for attempt in range(10):
            try:
                db = await get_pool()
                await db.execute("BEGIN IMMEDIATE")
                
                cursor = await db.execute(
                    "DELETE FROM SpamFilterWords WHERE board_id = ? AND word = ?",
                    (board_id, word.lower())
                )
                count = cursor.rowcount
                
                await db.execute("COMMIT")
                return count > 0
            except sqlite3.OperationalError as e:
                try: await db.execute("ROLLBACK")
                except: pass
                
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    await asyncio.sleep(0.1 * (attempt + 1))
                    continue
                break
            except Exception as e:
                try: await db.execute("ROLLBACK")
                except: pass
                print(f"⛔ ОШИБКА при удалении стоп-слова из БД: {e}")
                break
    return False
async def add_reaction_ban(user_id: int, board_id: str):
    """Добавляет пользователя в список забаненных по реакциям для доски."""
    from common.db_pool import get_pool, db_lock
    
    async with db_lock:
        for attempt in range(10):
            try:
                db = await get_pool()
                await db.execute("BEGIN IMMEDIATE")
                
                await db.execute(
                    "INSERT OR IGNORE INTO ReactionBans (user_id, board_id) VALUES (?, ?)",
                    (user_id, board_id)
                )
                
                await db.execute("COMMIT")
                return
            except sqlite3.OperationalError as e:
                try: await db.execute("ROLLBACK")
                except: pass
                
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    await asyncio.sleep(0.1 * (attempt + 1))
                    continue
                print(f"⛔ ОШИБКА при добавлении бана на реакции в БД: {e}")
                break
            except Exception as e:
                try: await db.execute("ROLLBACK")
                except: pass
                print(f"⛔ ОШИБКА при добавлении бана на реакции в БД: {e}")
                break

async def remove_reaction_ban(user_id: int, board_id: str):
    """Удаляет пользователя из списка забаненных по реакциям для доски."""
    from common.db_pool import get_pool, db_lock
    
    async with db_lock:
        for attempt in range(10):
            try:
                db = await get_pool()
                await db.execute("BEGIN IMMEDIATE")
                
                await db.execute(
                    "DELETE FROM ReactionBans WHERE user_id = ? AND board_id = ?",
                    (user_id, board_id)
                )
                
                await db.execute("COMMIT")
                return
            except sqlite3.OperationalError as e:
                try: await db.execute("ROLLBACK")
                except: pass
                
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    await asyncio.sleep(0.1 * (attempt + 1))
                    continue
                print(f"⛔ ОШИБКА при удалении бана на реакции из БД: {e}")
                break
            except Exception as e:
                try: await db.execute("ROLLBACK")
                except: pass
                print(f"⛔ ОШИБКА при удалении бана на реакции из БД: {e}")
                break
async def load_all_reaction_bans() -> Dict[str, set]:
    """
    Загружает все баны на реакции из БД.
    """
    from common.db_pool import get_pool, db_lock
    from collections import defaultdict
    
    reaction_bans_map = defaultdict(set)
    async with db_lock:
        try:
            db = await get_pool()
            async with db.execute("SELECT user_id, board_id FROM ReactionBans") as cursor:
                async for row in cursor:
                    user_id, board_id = row
                    reaction_bans_map[board_id].add(user_id)
            print(f"  > DB: Загружено банов на реакции: {sum(len(s) for s in reaction_bans_map.values())} шт.")
            return reaction_bans_map
        except Exception as e:
            print(f"⛔ ОШИБКА при загрузке банов на реакции из БД: {e}")
            return defaultdict(set)
async def update_post_thread_id(post_num: int, thread_id: int):
    from common.db_pool import get_pool, db_lock
    
    async with db_lock:
        for attempt in range(10):
            try:
                db = await get_pool()
                await db.execute("BEGIN IMMEDIATE")
                
                await db.execute(
                    "UPDATE Posts SET thread_id = ? WHERE post_num = ?",
                    (thread_id, post_num)
                )
                
                await db.execute("COMMIT")
                return
            except sqlite3.OperationalError as e:
                try: await db.execute("ROLLBACK")
                except: pass
                
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    await asyncio.sleep(0.1 * (attempt + 1))
                    continue
                break
            except Exception:
                try: await db.execute("ROLLBACK")
                except: pass
                break
async def add_reaction_to_queue(user_id: int, post_num: int, emoji: str):
    """
    Добавляет запрос на реакцию в очередь в БД.
    """
    from common.db_pool import get_pool, db_lock
    
    async with db_lock:
        for attempt in range(10):
            try:
                db = await get_pool()
                await db.execute("BEGIN IMMEDIATE")
                
                await db.execute(
                    "INSERT INTO ReactionQueue (user_id, post_num, emoji, created_at) VALUES (?, ?, ?, ?)",
                    (user_id, post_num, emoji, time.time())
                )
                
                await db.execute("COMMIT")
                return True
            except sqlite3.OperationalError as e:
                try: await db.execute("ROLLBACK")
                except: pass
                
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    await asyncio.sleep(0.1 * (attempt + 1))
                    continue
                print(f"⛔ ОШИБКА при добавлении реакции в очередь: {e}")
                break
            except Exception as e:
                try: await db.execute("ROLLBACK")
                except: pass
                print(f"⛔ ОШИБКА при добавлении реакции в очередь: {e}")
                break
    return False

async def get_and_clear_reaction_queue() -> list[dict]:
    """
    Атомарно извлекает все реакции из очереди и очищает ее.
    """
    from common.db_pool import get_pool, db_lock
    
    async with db_lock:
        for attempt in range(10):
            try:
                db = await get_pool()
                await db.execute("BEGIN IMMEDIATE")
                
                async with db.execute("SELECT id, user_id, post_num, emoji FROM ReactionQueue;") as cursor:
                    rows = await cursor.fetchall()
                    cols = [d[0] for d in cursor.description]
                
                if not rows:
                    await db.execute("COMMIT")
                    return []
                
                result_data = []
                ids_to_delete = []
                for row in rows:
                    d = dict(zip(cols, row))
                    result_data.append(d)
                    ids_to_delete.append(d["id"])
                    
                if ids_to_delete:
                    placeholders = ','.join('?' for _ in ids_to_delete)
                    await db.execute(f"DELETE FROM ReactionQueue WHERE id IN ({placeholders});", ids_to_delete)
                    
                await db.execute("COMMIT")
                return result_data
                
            except sqlite3.OperationalError as e:
                try: await db.execute("ROLLBACK")
                except: pass
                
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    await asyncio.sleep(0.1 * (attempt + 1))
                    continue
                print(f"⛔ ОШИБКА в get_and_clear_reaction_queue: {e}.")
                break
            except Exception as e:
                try: await db.execute("ROLLBACK")
                except: pass
                print(f"⛔ ОШИБКА в get_and_clear_reaction_queue: {e}.")
                break
    return []
_VIDEO_CACHE: Dict[str, List[Tuple[int, int]]] = defaultdict(list)
_IMAGE_CACHE: Dict[str, List[Tuple[int, int]]] = defaultdict(list)
_THREAD_CACHE: Dict[str, List[str]] = defaultdict(list)

_LAST_MAX_POST_NUM = 0
_LAST_CACHE_UPDATE = 0

_RANDOM_VIDEO_TYPES = {'video', 'animation', 'video_note', 'gif'}
_RANDOM_IMAGE_TYPES = {'image', 'photo', 'sticker'}
_RANDOM_VIDEO_EXTS = ('.mp4', '.webm', '.mov', '.mkv')
_RANDOM_IMAGE_EXTS = ('.jpg', '.jpeg', '.png', '.webp', '.gif')

def _random_media_class(raw_type: str | None, item: dict) -> str | None:
    ftype = str(raw_type or '').lower()
    if ftype in _RANDOM_VIDEO_TYPES:
        return 'video'
    if ftype in _RANDOM_IMAGE_TYPES:
        return 'image'
    if ftype != 'document':
        return None
    filename = str(item.get('filename') or item.get('file_name') or item.get('name') or '').lower()
    mime = str(item.get('mime_type') or item.get('mime') or '').lower()
    if mime.startswith('video/') or filename.endswith(_RANDOM_VIDEO_EXTS):
        return 'video'
    if mime.startswith('image/') or filename.endswith(_RANDOM_IMAGE_EXTS):
        return 'image'
    return None

def _make_random_file_entry(item: dict, fallback_type: str | None = None) -> dict | None:
    if not isinstance(item, dict):
        return None
    file_id = (
        item.get('original_file_id')
        or item.get('file_id')
        or item.get('media')
    )
    if not file_id or not isinstance(file_id, str) or file_id.startswith('<'):
        return None
    media_class = _random_media_class(item.get('type') or fallback_type, item)
    if not media_class:
        return None
    filename = item.get('filename') or item.get('file_name') or item.get('name')
    if not filename:
        ext = 'mp4' if media_class == 'video' else ('webp' if (item.get('type') == 'sticker') else 'jpg')
        prefix = 'vid' if media_class == 'video' else 'img'
        filename = f"{prefix}_{file_id[:8]}.{ext}"
    return {
        **item,
        'type': media_class,
        'source_type': item.get('source_type') or item.get('type') or fallback_type,
        'original_file_id': file_id,
        'thumbnail_file_id': item.get('thumbnail_file_id') or item.get('thumb_file_id') or item.get('file_id'),
        'filename': filename,
    }

def _extract_random_media_files(content: dict | str | None) -> list[dict]:
    if isinstance(content, str):
        try:
            content = json.loads(content)
        except Exception:
            return []
    if not isinstance(content, dict):
        return []

    files = content.get('files')
    if isinstance(files, list):
        return [entry for entry in (_make_random_file_entry(f) for f in files) if entry]

    if content.get('type') == 'media_group' and isinstance(content.get('media'), list):
        return [entry for entry in (_make_random_file_entry(item) for item in content['media']) if entry]

    if content.get('file_id'):
        entry = _make_random_file_entry(content, fallback_type=content.get('type'))
        return [entry] if entry else []

    return []

def _append_random_media_to_caches(
    video_cache: Dict[str, List[Tuple[int, int]]],
    image_cache: Dict[str, List[Tuple[int, int]]],
    board_id: str,
    post_num: int,
    content: dict | str,
) -> int:
    files = _extract_random_media_files(content)
    if not files:
        return 0
    added = 0
    for idx, f in enumerate(files):
        ftype = f.get('type')
        if ftype == 'video':
            video_cache[board_id].append((post_num, idx))
            added += 1
        elif ftype == 'image':
            image_cache[board_id].append((post_num, idx))
            added += 1
    return added

async def refresh_random_indexes():
    global _VIDEO_CACHE, _IMAGE_CACHE, _THREAD_CACHE, _LAST_MAX_POST_NUM, _LAST_CACHE_UPDATE
    
    from common.db_pool import get_pool, db_lock
    
    try:
        db = await get_pool()
        async with db.execute("SELECT MAX(post_num) FROM Posts") as cursor:
            row = await cursor.fetchone()
            current_max = row[0] if row and row[0] else 0
            
        if current_max == _LAST_MAX_POST_NUM and (_VIDEO_CACHE or _IMAGE_CACHE or _THREAD_CACHE):
            return
            
    except Exception:
        pass

    async with db_lock:
        try:
            start_time = time.time()
            db = await get_pool()
            
            new_video_cache = defaultdict(list)
            new_image_cache = defaultdict(list)
            new_thread_cache = defaultdict(list)
            can_increment = (
                _LAST_MAX_POST_NUM > 0
                and current_max >= _LAST_MAX_POST_NUM
                and (_VIDEO_CACHE or _IMAGE_CACHE or _THREAD_CACHE)
            )

            if can_increment:
                added_media = 0
                query = """
                    SELECT board_id, post_num, content
                    FROM Posts
                    WHERE post_num > ?
                      AND post_num <= ?
                      AND IFNULL(is_shadow, 0) = 0
                      AND (
                        json_extract(content, '$.files') IS NOT NULL
                        OR json_extract(content, '$.media') IS NOT NULL
                        OR json_extract(content, '$.file_id') IS NOT NULL
                      )
                """
                async with db.execute(query, (_LAST_MAX_POST_NUM, current_max)) as cursor:
                    async for row in cursor:
                        bid, pid, content_str = row
                        try:
                            added_media += _append_random_media_to_caches(_VIDEO_CACHE, _IMAGE_CACHE, bid, pid, content_str)
                        except Exception:
                            continue

                query_threads = """
                    SELECT p.board_id, p.thread_id
                    FROM Posts p
                    JOIN Threads t ON p.post_num = t.thread_num
                    WHERE p.post_num > ?
                      AND p.post_num <= ?
                      AND t.is_archived = 0
                      AND IFNULL(p.is_shadow, 0) = 0
                """
                async with db.execute(query_threads, (_LAST_MAX_POST_NUM, current_max)) as cursor:
                    async for row in cursor:
                        _THREAD_CACHE[row[0]].append(str(row[1]))

                _LAST_MAX_POST_NUM = current_max
                _LAST_CACHE_UPDATE = time.time()
                print(f"Random Cache Incremental Updated: +{added_media} media, max={current_max}")
                return
            
            query = """
                SELECT board_id, post_num, content 
                FROM Posts 
                WHERE IFNULL(is_shadow, 0) = 0
                  AND (
                    json_extract(content, '$.files') IS NOT NULL
                    OR json_extract(content, '$.media') IS NOT NULL
                    OR json_extract(content, '$.file_id') IS NOT NULL
                  )
            """
            
            async with db.execute(query) as cursor:
                async for row in cursor:
                    bid, pid, content_str = row
                    try:
                        _append_random_media_to_caches(new_video_cache, new_image_cache, bid, pid, content_str)
                                
                    except: continue

            query_threads = """
                SELECT p.board_id, p.thread_id 
                FROM Posts p
                JOIN Threads t ON p.post_num = t.thread_num
                WHERE t.is_archived = 0
                AND IFNULL(p.is_shadow, 0) = 0
            """
            async with db.execute(query_threads) as cursor:
                async for row in cursor:
                    new_thread_cache[row[0]].append(str(row[1]))

            _VIDEO_CACHE = new_video_cache
            _IMAGE_CACHE = new_image_cache
            _THREAD_CACHE = new_thread_cache
            
            _LAST_MAX_POST_NUM = current_max
            _LAST_CACHE_UPDATE = time.time()
            
            print(f"Random Cache Updated: V:{sum(len(x) for x in _VIDEO_CACHE.values())} I:{sum(len(x) for x in _IMAGE_CACHE.values())}")
            
        except Exception as e:
            print(f"Error updating random indexes: {e}")

async def _get_random_media_item(cache_dict: Dict[str, List[Tuple[int, int]]], allowed_boards: List[str] = None, media_kind: str | None = None):
    if not cache_dict:
        await refresh_random_indexes()
        if media_kind == 'video':
            cache_dict = _VIDEO_CACHE
        elif media_kind == 'image':
            cache_dict = _IMAGE_CACHE
        if not cache_dict: return None

    if allowed_boards:
        valid_boards = [b for b in allowed_boards if b in cache_dict and cache_dict[b]]
    else:
        valid_boards = [b for b in cache_dict.keys() if cache_dict[b]]
        
    if not valid_boards:
        return None

    total_count = sum(len(cache_dict[b]) for b in valid_boards)
    if total_count == 0: return None
    
    target_idx = random.randint(0, total_count - 1)
    
    chosen_pair = None
    current_idx = 0
    
    for b in valid_boards:
        count = len(cache_dict[b])
        if target_idx < current_idx + count:
            inner_idx = target_idx - current_idx
            chosen_pair = cache_dict[b][inner_idx]
            break
        current_idx += count
        
    if not chosen_pair: return None

    pid, file_idx = chosen_pair
    for _ in range(5):
        post = await get_post_by_num(pid)
        
        if post and 'content' in post:
            files = _extract_random_media_files(post['content'])
            if file_idx < len(files):
                post['content']['files'] = files
                post['_selected_file_index'] = file_idx
                return post
        for c in [_VIDEO_CACHE, _IMAGE_CACHE]:
            if pid in c:
                del c[pid]
            else: 
                for b in c:
                    c[b] = [item for item in c[b] if item[0] != pid]
        total_count = sum(len(cache_dict[b]) for b in valid_boards)
        if total_count == 0: break
        target_idx = random.randint(0, total_count - 1)
        curr = 0
        for b in valid_boards:
            if target_idx < curr + len(cache_dict[b]):
                chosen_pair = cache_dict[b][target_idx - curr]
                pid, file_idx = chosen_pair
                break
            curr += len(cache_dict[b])

    return None
    
async def get_random_video_post(allowed_boards: List[str] = None):
    return await _get_random_media_item(_VIDEO_CACHE, allowed_boards, media_kind='video')

async def get_random_image_post(allowed_boards: List[str] = None):
    return await _get_random_media_item(_IMAGE_CACHE, allowed_boards, media_kind='image')

async def update_thread_last_updated(thread_op_num: int, timestamp: float):
    """
    Обновляет время последнего ответа (last_updated_at) для треда.
    """
    from common.db_pool import get_pool, db_lock
    
    async with db_lock:
        for attempt in range(10):
            try:
                db = await get_pool()
                await db.execute("BEGIN IMMEDIATE")
                await db.execute(
                    "UPDATE Threads SET last_updated_at = ? WHERE thread_id = ? AND is_archived = 0",
                    (timestamp, str(thread_op_num))
                )
                await db.execute("COMMIT")
                return
            except sqlite3.OperationalError as e:
                try: await db.execute("ROLLBACK")
                except: pass
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    await asyncio.sleep(0.1 * (attempt + 1))
                    continue
                print(f"⛔ ОШИБКА при обновлении времени треда #{thread_op_num}: {e}")
                break
            except Exception as e:
                try: await db.execute("ROLLBACK")
                except: pass
                print(f"⛔ ОШИБКА при обновлении времени треда #{thread_op_num}: {e}")
                break
async def get_thread_ids_for_posts(post_nums: List[int]) -> Dict[int, int]:
    """
    Для списка номеров постов возвращает словарь {post_num: thread_id}.
    """
    if not post_nums:
        return {}
    db = await get_pool()
    placeholders = ','.join('?' for _ in post_nums)
    query = f"SELECT post_num, thread_id FROM Posts WHERE post_num IN ({placeholders})"
    thread_map = {}
    try:
        async with db.execute(query, post_nums) as cursor:
            async for row in cursor:
                post_num, thread_id = row
                if thread_id:
                    thread_map[post_num] = thread_id
        return thread_map
    except Exception as e:
        print(f"⛔ ОШИБКА в get_thread_ids_for_posts: {e}")
        return {}
async def get_all_media_from_thread(thread_op_num: int) -> List[Dict]:
    """
    Извлекает все посты с файлами из указанного треда.
    Возвращает список словарей, каждый из которых содержит post_num и content.
    """
    db = await get_pool()
    media_posts = []
    try:
        db.row_factory = aiosqlite.Row
        query = """
            SELECT post_num, content
            FROM Posts
            WHERE thread_id = ? 
              AND json_extract(content, '$.files') IS NOT NULL
              AND IFNULL(is_shadow, 0) = 0
            ORDER BY post_num ASC
        """
        async with db.execute(query, (thread_op_num,)) as cursor:
            cols = [d[0] for d in cursor.description]
            async for row in cursor:
                if hasattr(row, 'keys'):
                    post_data = dict(row)
                else:
                    post_data = dict(zip(cols, row))
                try:
                    post_data['content'] = json.loads(post_data['content'])
                    if post_data['content'].get('files'):
                        media_posts.append(post_data)
                except (json.JSONDecodeError, TypeError):
                    continue
        return media_posts
    except Exception as e:
        print(f"⛔ ОШИБКА в get_all_media_from_thread: {e}")
        return []
    finally:
        db.row_factory = None
async def sync_boards_with_config(board_config: dict):
    """
    Синхронизирует доски из конфига с БД.
    """
    if not board_config:
        return

    from common.db_pool import get_pool, db_lock

    async with db_lock:
        for attempt in range(10):
            try:
                db = await get_pool()
                await db.execute("BEGIN IMMEDIATE")

                # Оптимизация: используем генератор напрямую в executemany, чтобы избежать N+1 execute
                # и лишних аллокаций памяти (по сравнению с циклом for ... append).
                await db.executemany(
                    """
                    INSERT INTO Boards (board_id, name, description) VALUES (?, ?, ?)
                    ON CONFLICT(board_id) DO UPDATE SET
                        name = excluded.name,
                        description = excluded.description
                    """,
                    (
                        (
                            board_id,
                            info.get("name", "Unnamed Board"),
                            json.dumps(info.get("description", ""), ensure_ascii=False) if isinstance(info.get("description", ""), dict) else info.get("description", "")
                        )
                        for board_id, info in board_config.items()
                    )
                )

                await db.execute("COMMIT")
                print(f"✅ Синхронизация досок с БД завершена. Проверено {len(board_config)} досок.")
                return
            except sqlite3.OperationalError as e:
                try: await db.execute("ROLLBACK")
                except: pass
                
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    await asyncio.sleep(0.5 * (attempt + 1))
                    continue
                print(f"⛔ ОШИБКА при синхронизации досок с БД: {e}")
                break
            except Exception as e:
                try: await db.execute("ROLLBACK")
                except: pass
                print(f"⛔ ОШИБКА при синхронизации досок с БД: {e}")
                break
async def create_bottle(sender_id: int, recipient_id: int, message: str) -> bool:
    from common.db_pool import get_pool, db_lock
    
    async with db_lock:
        for attempt in range(10):
            try:
                db = await get_pool()
                await db.execute("BEGIN IMMEDIATE")
                
                await db.execute(
                    "INSERT INTO Bottles (sender_id, recipient_id, message_text, timestamp) VALUES (?, ?, ?, ?)",
                    (sender_id, recipient_id, message, time.time())
                )
                
                await db.execute("COMMIT")
                return True
            except sqlite3.OperationalError as e:
                try: await db.execute("ROLLBACK")
                except: pass
                
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    await asyncio.sleep(0.1 * (attempt + 1))
                    continue
                break
            except Exception as e:
                try: await db.execute("ROLLBACK")
                except: pass
                print(f"DB Error creating bottle: {e}")
                break
    return False

async def read_and_delete_bottle(user_id: int) -> dict | None:
    from common.db_pool import get_pool, db_lock
    
    async with db_lock:
        for attempt in range(10):
            try:
                db = await get_pool()
                await db.execute("BEGIN IMMEDIATE")
                
                # Читаем внутри транзакции
                find_query = "SELECT id, message_text FROM Bottles WHERE recipient_id = ? AND is_read = 0 ORDER BY timestamp ASC LIMIT 1"
                async with db.execute(find_query, (user_id,)) as cursor:
                    bottle_data = await cursor.fetchone()
                
                if not bottle_data:
                    await db.execute("COMMIT")
                    return None
                    
                bottle_id, message_text = bottle_data
                await db.execute("DELETE FROM Bottles WHERE id = ?", (bottle_id,))
                
                await db.execute("COMMIT")
                return {"message": message_text}
            except sqlite3.OperationalError as e:
                try: await db.execute("ROLLBACK")
                except: pass
                
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    await asyncio.sleep(0.1 * (attempt + 1))
                    continue
                break
            except Exception:
                try: await db.execute("ROLLBACK")
                except: pass
                break
    return None
async def get_unread_bottle_count(user_id: int) -> int:
    """Считает количество непрочитанных бутылок для пользователя."""
    db = await get_pool()
    query = "SELECT COUNT(id) FROM Bottles WHERE recipient_id = ? AND is_read = 0"
    async with db.execute(query, (user_id,)) as cursor:
        result = await cursor.fetchone()
        return result[0] if result else 0
async def apply_auto_censure(file_id: str, action: str) -> list[int]:
    """
    Применяет автоматическую цензуру (blur или shadow) ко всем постам, содержащим file_id.
    Возвращает список ID затронутых постов.
    """
    from common.db_pool import get_pool, db_lock
    
    affected_posts = []
    
    async with db_lock:
        for attempt in range(10):
            try:
                db = await get_pool()
                await db.execute("BEGIN IMMEDIATE")
                
                # Ищем посты, содержащие file_id в JSON
                query = "SELECT post_num, content, is_shadow FROM Posts WHERE instr(content, ?) > 0"
                async with db.execute(query, (file_id,)) as cursor:
                    rows = await cursor.fetchall()
                
                if not rows:
                    await db.execute("COMMIT")
                    return []

                for row in rows:
                    post_num, content_str, is_shadow = row
                    needs_update = False
                    try:
                        content = json.loads(content_str)
                    except:
                        continue

                    # Логика действий
                    if action == 'shadow':
                        if not is_shadow:
                            await db.execute("UPDATE Posts SET is_shadow = 1 WHERE post_num = ?", (post_num,))
                            needs_update = True
                            
                    elif action == 'blur':
                        # Ставим флаг цензуры в JSON, если его нет
                        if not content.get('is_censored'):
                            content['is_censored'] = True
                            new_json = json.dumps(content, default=_json_serializer)
                            await db.execute("UPDATE Posts SET content = ? WHERE post_num = ?", (new_json, post_num))
                            needs_update = True
                    
                    if needs_update:
                        affected_posts.append(post_num)

                await db.execute("COMMIT")
                return affected_posts

            except sqlite3.OperationalError as e:
                try: await db.execute("ROLLBACK")
                except: pass
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    await asyncio.sleep(0.2 * (attempt + 1))
                    continue
                print(f"⚠️ Auto-Censure DB Error: {e}")
                break
            except Exception as e:
                try: await db.execute("ROLLBACK")
                except: pass
                print(f"⚠️ Auto-Censure DB Error: {e}")
                break
                
    return []
async def get_recent_tags_summary(limit_files: int = 2000, top_n: int = 100) -> list[tuple[str, int]]:
    """
    Собирает статистику по тегам из последних limit_files файлов.
    Нужно для SEO-облака тегов. Не грузит всю БД.
    """
    from common.db_pool import get_pool, db_lock
    from collections import Counter
    
    # Кэшируем результат на уровне базы или приложения, чтобы не дергать часто
    # Но здесь просто быстрый селект
    
    tags_counter = Counter()
    
    try:
        db = await get_pool()
        # Берем только файлы, у которых есть теги
        query = """
            SELECT tags FROM FileRegistry 
            WHERE tags IS NOT NULL AND tags != '' 
            ORDER BY created_at DESC 
            LIMIT ?
        """
        
        # Чтение без лока, так как это аналитика и не требует строгой консистентности
        async with db.execute(query, (limit_files,)) as cursor:
            async for row in cursor:
                raw_tags = row[0]
                if not raw_tags: continue
                # Разбиваем, чистим, считаем
                for t in raw_tags.split(','):
                    t_clean = t.strip().lower()
                    if len(t_clean) > 2: # Игнорируем мусор
                        tags_counter[t_clean] += 1
                        
        # Возвращаем топ-N тегов: [('anime', 150), ('webm', 120), ...]
        return tags_counter.most_common(top_n)
        
    except Exception as e:
        print(f"⛔ Error getting recent tags: {e}")
        return []
async def get_banned_users(board_id: str) -> list[dict]:
    """Возвращает список забаненных (обычный бан). Безопасная версия."""
    db = await get_pool()
    query = "SELECT user_id FROM Users WHERE board_id = ? AND status = 'banned'"
    async with db.execute(query, (board_id,)) as cursor:
        rows = await cursor.fetchall()
        return [{"user_id": row[0]} for row in rows]
async def get_shadow_muted_users(board_id: str) -> list[dict]:
    """Возвращает список теневых банов. Безопасная версия."""
    db = await get_pool()
    query = "SELECT user_id, expires_at FROM Mutes WHERE board_id = ? AND mute_type = 'shadow' AND expires_at > ?"
    async with db.execute(query, (board_id, time.time())) as cursor:
        rows = await cursor.fetchall()
        return [{"user_id": row[0], "expires_at": row[1]} for row in rows]
async def lift_ban(user_id: int, board_id: str):
    """Снимает обычный бан (ставит статус active)."""
    from common.db_pool import get_pool, db_lock
    
    async with db_lock:
        for attempt in range(10):
            try:
                db = await get_pool()
                await db.execute("BEGIN IMMEDIATE")
                
                await db.execute("UPDATE Users SET status = 'active' WHERE user_id = ? AND board_id = ?", (user_id, board_id))
                
                await db.execute("COMMIT")
                return
            except sqlite3.OperationalError as e:
                try: await db.execute("ROLLBACK")
                except: pass
                
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    await asyncio.sleep(0.1 * (attempt + 1))
                    continue
                print(f"⛔ Error lifting ban: {e}")
                break
            except Exception as e:
                try: await db.execute("ROLLBACK")
                except: pass
                print(f"⛔ Error lifting ban: {e}")
                break

async def lift_shadow_ban(user_id: int, board_id: str):
    """Снимает теневой бан."""
    from common.db_pool import get_pool, db_lock
    
    async with db_lock:
        for attempt in range(10):
            try:
                db = await get_pool()
                await db.execute("BEGIN IMMEDIATE")
                
                await db.execute("DELETE FROM Mutes WHERE user_id = ? AND board_id = ? AND mute_type = 'shadow'", (user_id, board_id))
                
                await db.execute("COMMIT")
                return
            except sqlite3.OperationalError as e:
                try: await db.execute("ROLLBACK")
                except: pass
                
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    await asyncio.sleep(0.1 * (attempt + 1))
                    continue
                print(f"⛔ Error lifting shadow ban: {e}")
                break
            except Exception as e:
                try: await db.execute("ROLLBACK")
                except: pass
                print(f"⛔ Error lifting shadow ban: {e}")
                break

async def apply_regular_mute(user_id: int, board_id: str, duration_seconds: int):
    """
    Применяет обычный мут пользователю.
    """
    expires_at = time.time() + duration_seconds
    from common.db_pool import get_pool, db_lock
    
    async with db_lock:
        for attempt in range(10):
            try:
                db = await get_pool()
                await db.execute("BEGIN IMMEDIATE")
                
                await db.execute(
                    "DELETE FROM Mutes WHERE user_id = ? AND board_id = ? AND mute_type = 'mute'",
                    (user_id, board_id)
                )
                await db.execute(
                    "INSERT INTO Mutes (user_id, board_id, mute_type, expires_at) VALUES (?, ?, 'mute', ?)",
                    (user_id, board_id, expires_at)
                )
                
                await db.execute("COMMIT")
                return True
            except sqlite3.OperationalError as e:
                try: await db.execute("ROLLBACK")
                except: pass
                
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    await asyncio.sleep(0.1 * (attempt + 1))
                    continue
                print(f"⛔ DB Error applying regular mute: {e}")
                break
            except Exception as e:
                try: await db.execute("ROLLBACK")
                except: pass
                print(f"⛔ DB Error applying regular mute: {e}")
                break
    return False
async def remove_regular_mute(user_id: int, board_id: str):
    """
    Удаляет обычный мут из базы данных.
    """
    from common.db_pool import get_pool, db_lock
    
    async with db_lock:
        for attempt in range(10):
            try:
                db = await get_pool()
                await db.execute("BEGIN IMMEDIATE")
                
                await db.execute(
                    "DELETE FROM Mutes WHERE user_id = ? AND board_id = ? AND mute_type = 'mute'",
                    (user_id, board_id)
                )
                
                await db.execute("COMMIT")
                return
            except sqlite3.OperationalError as e:
                try: await db.execute("ROLLBACK")
                except: pass
                
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    await asyncio.sleep(0.1 * (attempt + 1))
                    continue
                print(f"⛔ DB Error removing regular mute: {e}")
                break
            except Exception as e:
                try: await db.execute("ROLLBACK")
                except: pass
                print(f"⛔ DB Error removing regular mute: {e}")
                break
async def get_board_media_posts(board_id: str, page: int = 1, page_size: int = 20, stream: str = 'ru', observer_id: Optional[int] = None) -> list:
    """
    Получает посты с доски с файлами.
    ИЗОЛЯЦИЯ: Фильтр по stream + Фильтр теневых банов (is_shadow) с учетом наблюдателя.
    """
    offset = (page - 1) * page_size
    db = await get_pool()
    viewer_id = observer_id if observer_id is not None else -1
    try:
        query = f"""
            SELECT post_num, board_id, thread_id, content, timestamp, author_id
            FROM Posts 
            WHERE board_id = ? 
              AND stream = ?
              AND (IFNULL(is_shadow, 0) = 0 OR author_id = {viewer_id})
              AND json_extract(content, '$.files') IS NOT NULL
              AND json_array_length(json_extract(content, '$.files')) > 0
            ORDER BY timestamp DESC
            LIMIT ? OFFSET ?
        """        
        posts = []
        async with db.execute(query, (board_id, stream, page_size, offset)) as cursor:
            cols = [d[0] for d in cursor.description]
            async for row in cursor:
                if hasattr(row, 'keys'):
                    post_data = dict(row)
                else:
                    post_data = dict(zip(cols, row))
                
                try:
                    post_data['id'] = post_data.pop('post_num')
                    posts.append(post_data)
                except Exception:
                    continue
        return posts
    except Exception as e:
        print(f"⛔ Error in get_board_media_posts: {e}")
        return []
async def get_max_post_num() -> int:
    from common.db_pool import get_pool, db_lock
    async with db_lock:
        try:
            db = await get_pool()
            async with db.execute("SELECT MAX(post_num) FROM Posts") as cursor:
                row = await cursor.fetchone()
                return row[0] if row and row[0] else 0
        except:
            return 0
async def get_random_active_thread() -> Optional[tuple[str, str]]:
    """
    Возвращает случайный живой тред (board_id, thread_id).
    """
    if not _THREAD_CACHE or (time.time() - _LAST_CACHE_UPDATE > 1800):
        await refresh_random_indexes()
        
    if not _THREAD_CACHE:
        return None
    valid_boards = [b for b in _THREAD_CACHE.keys() if _THREAD_CACHE[b]]
    if not valid_boards: return None

    total_count = sum(len(_THREAD_CACHE[b]) for b in valid_boards)
    if total_count == 0: return None
    
    target_idx = random.randint(0, total_count - 1)
    
    current_idx = 0
    for b in valid_boards:
        count = len(_THREAD_CACHE[b])
        if target_idx < current_idx + count:
            inner_idx = target_idx - current_idx
            thread_id = _THREAD_CACHE[b][inner_idx]
            return (b, thread_id)
        current_idx += count
        
    return None
async def get_random_file_from_db() -> dict | None:
    """
    Возвращает случайный файл (картинку) для функции picrandom.
    Использует новый кэш изображений.
    """
    # Используем общий механизм выборки для картинок
    post = await _get_random_media_item(_IMAGE_CACHE)
    
    if post and 'content' in post and 'files' in post['content']:
        files = post['content']['files']
        # _get_random_media_item уже выбрала конкретный файл по взвешенному рандому
        idx = post.get('_selected_file_index')
        
        if idx is not None and 0 <= idx < len(files):
            return files[idx]
            
    return None
async def set_user_role(user_id: int, role: str):
    if role not in ['admin', 'mod', 'user']: return
    from common.db_pool import get_pool, db_lock
    
    async with db_lock:
        for attempt in range(10):
            try:
                db = await get_pool()
                await db.execute("BEGIN IMMEDIATE")
                
                await db.execute("UPDATE Users SET role = ? WHERE user_id = ?", (role, user_id))
                await db.execute("INSERT OR IGNORE INTO Users (user_id, board_id, role) VALUES (?, 'b', ?)", (user_id, role))
                
                await db.execute("COMMIT")
                return
            except sqlite3.OperationalError as e:
                try: await db.execute("ROLLBACK")
                except: pass
                
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    await asyncio.sleep(0.1 * (attempt + 1))
                    continue
                break
            except Exception:
                try: await db.execute("ROLLBACK")
                except: pass
                break
async def get_user_role(user_id: int) -> str:
    """Получает роль пользователя (берем максимальную, если есть коллизии)."""
    db = await get_pool()
    async with db.execute("SELECT role FROM Users WHERE user_id = ? LIMIT 1", (user_id,)) as cursor:
        row = await cursor.fetchone()
        return row[0] if row else 'user'
async def create_alert(user_id: int, content: str, image_url: str = None, btn_text: str = None, btn_link: str = None, target_board: str = 'all'):
    from common.db_pool import get_pool, db_lock
    
    async with db_lock:
        try:
            db = await get_pool()
            await db.execute("BEGIN IMMEDIATE")
            
            await db.execute(
                """INSERT INTO UserAlerts (user_id, content, image_url, btn_text, btn_link, target_board, created_at) 
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (user_id, content, image_url, btn_text, btn_link, target_board, time.time())
            )
            
            await db.execute("COMMIT")
        except Exception as e:
            try: await db.execute("ROLLBACK")
            except: pass
            print(f"Error creating alert: {e}")
async def get_pending_alerts(user_id: int, current_board: str) -> list[dict]:
    """Получает непрочитанные алерты для пользователя."""
    db = await get_pool()
    query = """
        SELECT id, user_id, content, image_url, btn_text, btn_link, target_board, is_read, created_at 
        FROM UserAlerts 
        WHERE user_id = ? AND is_read = 0 
        AND (target_board = 'all' OR target_board = ?)
    """
    async with db.execute(query, (user_id, current_board)) as cursor:
        rows = await cursor.fetchall()
        return [
            {
                "id": r[0], "user_id": r[1], "content": r[2], 
                "image_url": r[3], "btn_text": r[4], "btn_link": r[5],
                "target_board": r[6], "is_read": r[7], "created_at": r[8]
            } 
            for r in rows
        ]
async def mark_alert_read(alert_id: int):
    from common.db_pool import get_pool, db_lock
    
    async with db_lock:
        for attempt in range(10):
            try:
                db = await get_pool()
                await db.execute("BEGIN IMMEDIATE")
                
                await db.execute("UPDATE UserAlerts SET is_read = 1, read_at = ? WHERE id = ?", (time.time(), alert_id))
                
                await db.execute("COMMIT")
                return
            except sqlite3.OperationalError as e:
                try: await db.execute("ROLLBACK")
                except: pass
                
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    await asyncio.sleep(0.1 * (attempt + 1))
                    continue
                break
            except Exception:
                try: await db.execute("ROLLBACK")
                except: pass
                break

async def get_all_alerts_for_admin(limit: int = 50) -> list[dict]:
    """Получает историю алертов для админки."""
    db = await get_pool()
    query = """
        SELECT id, user_id, content, image_url, btn_text, btn_link, target_board, is_read, created_at 
        FROM UserAlerts 
        ORDER BY created_at DESC LIMIT ?
    """
    async with db.execute(query, (limit,)) as cursor:
        rows = await cursor.fetchall()
        return [
            {
                "id": r[0], "user_id": r[1], "content": r[2], 
                "image_url": r[3], "btn_text": r[4], "btn_link": r[5],
                "target_board": r[6], "is_read": r[7], "created_at": r[8]
            } 
            for r in rows
        ]
async def register_file_owner(file_id: str, bot_id: int):
    """
    Регистрирует владельца файла.
    """
    if not file_id or not bot_id: return
    
    from common.db_pool import get_pool, db_lock
    
    async with db_lock:
        for attempt in range(20):
            try:
                db = await get_pool()
                await db.execute("BEGIN IMMEDIATE")
                
                await db.execute("INSERT OR IGNORE INTO FileOwners (file_id, bot_id) VALUES (?, ?)", (file_id, bot_id))
                
                await db.execute("COMMIT")
                return 
            except sqlite3.OperationalError as e:
                try: await db.execute("ROLLBACK")
                except: pass
                
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    await asyncio.sleep(0.2 * (attempt + 1))
                    continue
                break
            except Exception:
                try: await db.execute("ROLLBACK")
                except: pass
                break

async def register_new_file(sha256: str, phash: str, file_id: str, thumb_id: str, ftype: str, blurhash: str = None):
    """
    Регистрирует новый файл.
    """
    from common.db_pool import get_pool, db_lock
    
    async with db_lock:
        for attempt in range(20):
            try:
                db = await get_pool()
                await db.execute("BEGIN IMMEDIATE")
                
                await db.execute(
                    "INSERT OR IGNORE INTO FileRegistry (sha256, phash, file_id, thumbnail_id, file_type, created_at, blurhash) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (sha256, phash, file_id, thumb_id, ftype, time.time(), blurhash)
                )
                
                await db.execute("COMMIT")
                return
            except sqlite3.OperationalError as e:
                try: await db.execute("ROLLBACK")
                except: pass
                
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    await asyncio.sleep(0.2 * (attempt + 1))
                    continue
                break
            except Exception:
                try: await db.execute("ROLLBACK")
                except: pass
                break
async def get_file_owner_id(file_id: str) -> int | None:
    """Возвращает ID бота, который загрузил этот файл."""
    db = await get_pool()
    try:
        async with db.execute("SELECT bot_id FROM FileOwners WHERE file_id = ?", (file_id,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None
    except Exception:
        return None
async def delete_posts_in_thread_after(thread_id: str, post_num_start: int):
    """
    Удаляет все посты в треде, начиная с указанного номера (включительно).
    """
    from common.db_pool import get_pool, db_lock
    
    # Если пытаются удалить с ОП-поста, вызываем обычное удаление
    if str(post_num_start) == str(thread_id):
        # delete_post_by_num уже адаптирован и использует лок
        await delete_post_by_num(post_num_start)
        return True

    async with db_lock:
        for attempt in range(10):
            try:
                db = await get_pool()
                await db.execute("BEGIN IMMEDIATE")
                
                await db.execute(
                    "DELETE FROM Posts WHERE thread_id = ? AND post_num >= ?",
                    (str(thread_id), post_num_start)
                )
                
                # Обновляем last_updated_at треда на время последнего живого поста
                async with db.execute("SELECT timestamp FROM Posts WHERE thread_id = ? ORDER BY post_num DESC LIMIT 1", (str(thread_id),)) as cursor:
                    row = await cursor.fetchone()
                    if row:
                        await db.execute("UPDATE Threads SET last_updated_at = ? WHERE thread_num = ?", (row[0], int(thread_id)))
                
                await db.execute("COMMIT")
                return True
            except sqlite3.OperationalError as e:
                try: await db.execute("ROLLBACK")
                except: pass
                
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    await asyncio.sleep(0.1 * (attempt + 1))
                    continue
                print(f"⛔ Error deleting posts after {post_num_start}: {e}")
                break
            except Exception as e:
                try: await db.execute("ROLLBACK")
                except: pass
                print(f"⛔ Error deleting posts after {post_num_start}: {e}")
                break
    return False
async def get_all_active_subscribers(board_id: str) -> list[int]:
    """Возвращает список ID всех пользователей со статусом active для конкретной доски."""
    db = await get_pool()
    try:
        query = "SELECT user_id FROM Users WHERE board_id = ? AND status = 'active'"
        async with db.execute(query, (board_id,)) as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]
    except Exception as e:
        print(f"⛔ ОШИБКА get_all_active_subscribers: {e}")
        return []
async def get_weekly_active_users(board_id: str, days: int = 7) -> set[int]:
    """Return users who wrote at least one visible post on a board during the last N days."""
    if days <= 0:
        return set()
    db = await get_pool()
    cutoff = time.time() - days * 86400
    users: set[int] = set()
    queries = (
        """
            SELECT DISTINCT author_id
            FROM Posts
            WHERE board_id = ?
              AND timestamp >= ?
              AND author_id > 0
              AND IFNULL(is_shadow, 0) = 0
        """,
        """
            SELECT DISTINCT author_id
            FROM Posts
            WHERE board_id = ?
              AND timestamp >= ?
              AND author_id > 0
        """,
    )
    for idx, query in enumerate(queries):
        try:
            async with db.execute(query, (board_id, cutoff)) as cursor:
                async for row in cursor:
                    uid = row[0]
                    if isinstance(uid, int) and uid > 0:
                        users.add(uid)
            return users
        except sqlite3.OperationalError as e:
            if idx == 0 and "is_shadow" in str(e).lower():
                users.clear()
                continue
            print(f"get_weekly_active_users error: {e}")
            return set()
        except Exception as e:
            print(f"get_weekly_active_users error: {e}")
            return set()
    return users
async def set_user_stream(user_id: int, board_id: str, stream: str):
    if stream not in ['ru', 'en', 'jp']:
        stream = 'ru'
    from common.db_pool import get_pool, db_lock
        
    async with db_lock:
        for attempt in range(10):
            try:
                db = await get_pool()
                await db.execute("BEGIN IMMEDIATE")
                
                await db.execute(
                    "INSERT OR IGNORE INTO Users (user_id, board_id) VALUES (?, ?)",
                    (user_id, board_id)
                )
                await db.execute(
                    "UPDATE Users SET stream = ? WHERE user_id = ? AND board_id = ?",
                    (stream, user_id, board_id)
                )
                
                await db.execute("COMMIT")
                return
            except sqlite3.OperationalError as e:
                try: await db.execute("ROLLBACK")
                except: pass
                
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    await asyncio.sleep(0.1 * (attempt + 1))
                    continue
                break
            except Exception:
                try: await db.execute("ROLLBACK")
                except: pass
                break
async def get_user_stream(user_id: int, board_id: str) -> str:
    """
    Получает текущий поток пользователя.
    Если не задан или ошибка — возвращает 'ru'.
    """
    db = await get_pool()
    try:
        async with db.execute("SELECT stream FROM Users WHERE user_id = ? AND board_id = ?", (user_id, board_id)) as cursor:
            row = await cursor.fetchone()
            if row and row[0]:
                return row[0]
            return 'ru'
    except Exception:
        return 'ru'
async def get_stream_active_users(board_id: str, stream: str) -> set[int]:
    """
    Возвращает ID активных пользователей КОНКРЕТНОГО потока.
    Нужно для рассылки.
    """
    db = await get_pool()
    users = set()
    try:
        query = "SELECT user_id FROM Users WHERE board_id = ? AND status = 'active' AND stream = ?"
        async with db.execute(query, (board_id, stream)) as cursor:
            async for row in cursor:
                users.add(row[0])
        return users
    except Exception:
        return set()
async def get_archived_threads(page: int = 1, page_size: int = 20) -> list:
    from common.db_pool import get_pool, db_lock
    offset = (page - 1) * page_size
    
    async with db_lock:
        try:
            db = await get_pool()
            db.row_factory = aiosqlite.Row
            query = """
                SELECT p.post_num, p.thread_id, p.board_id, p.content, p.timestamp, p.author_id, t.is_archived, p.stream, t.is_pinned
                FROM Posts p
                JOIN Threads t ON p.post_num = t.thread_num
                WHERE t.is_archived = 1 AND IFNULL(p.is_shadow, 0) = 0
                ORDER BY t.last_updated_at DESC
                LIMIT ? OFFSET ?
            """
            op_posts = []
            async with db.execute(query, (page_size, offset)) as cursor:
                cols = [d[0] for d in cursor.description]
                async for row in cursor:
                    if hasattr(row, 'keys'):
                        post_data = dict(row)
                    else:
                        post_data = dict(zip(cols, row))
                    try:
                        post_data['id'] = post_data.pop('post_num')
                        post_data['content'] = json.loads(post_data['content'])
                        op_posts.append(post_data)
                    except Exception:
                        continue
            
            if op_posts:
                thread_ids = [str(p['id']) for p in op_posts]
                placeholders = ','.join('?' for _ in thread_ids)
                stats_query = f"""
                    SELECT thread_id, COUNT(*) as reply_cnt
                    FROM Posts
                    WHERE thread_id IN ({placeholders}) AND IFNULL(is_shadow, 0) = 0
                    GROUP BY thread_id
                """
                stats_map = {}
                async with db.execute(stats_query, thread_ids) as cursor:
                    async for row in cursor:
                        stats_map[int(row['thread_id'])] = row['reply_cnt'] - 1
                for post in op_posts:
                    post['reply_count'] = stats_map.get(post['id'], 0)
            return op_posts
        except Exception as e:
            print(f"Error getting archived threads: {e}")
            return []
        finally:
            if 'db' in locals() and db:
                db.row_factory = None
async def get_global_chat_posts(page: int = 1, page_size: int = 50) -> list:
    from common.db_pool import get_pool, db_lock
    offset = (page - 1) * page_size
    
    async with db_lock:
        try:
            db = await get_pool()
            db.row_factory = aiosqlite.Row
            query = """
                SELECT post_num, board_id, content, timestamp, author_id, reply_to_post_num
                FROM Posts 
                WHERE (thread_id IS NULL OR thread_id != CAST(post_num AS TEXT))
                  AND IFNULL(is_shadow, 0) = 0
                ORDER BY timestamp DESC 
                LIMIT ? OFFSET ?
            """
            posts = []
            async with db.execute(query, (page_size, offset)) as cursor:
                cols = [d[0] for d in cursor.description]
                async for row in cursor:
                    if hasattr(row, 'keys'):
                        post_data = dict(row)
                    else:
                        post_data = dict(zip(cols, row))
                    try:
                        post_data['id'] = post_data.pop('post_num')
                        post_data['content'] = json.loads(post_data['content'])
                        post_data['backlinks'] = [] 
                        posts.append(post_data)
                    except Exception:
                        continue
            
            posts_map = {p['id']: p for p in posts}
            for p in posts:
                refs = set()
                if p.get('reply_to_post_num'):
                    refs.add(p['reply_to_post_num'])
                text = p.get('content', {}).get('text', '')
                if text:
                    found = re.findall(r'(?:>>|&gt;&gt;)(\d+)', text)
                    for f in found:
                        refs.add(int(f))
                for ref_id in refs:
                    if ref_id in posts_map:
                        if p['id'] not in posts_map[ref_id]['backlinks']:
                            posts_map[ref_id]['backlinks'].append(p['id'])
            
            for p in posts:
                p['backlinks'].sort()
            return posts
        except Exception as e:
            print(f"Error getting global archive chat: {e}")
            return []
        finally:
            if 'db' in locals() and db:
                db.row_factory = None
async def restore_thread_from_archive(thread_id: str):
    """
    Восстанавливает тред из архива (делает доступным для постинга).
    """
    from common.db_pool import get_pool, db_lock
    
    async with db_lock:
        for attempt in range(10):
            try:
                db = await get_pool()
                await db.execute("BEGIN IMMEDIATE")
                
                await db.execute(
                    "UPDATE Threads SET is_archived = 0, last_updated_at = ? WHERE thread_num = ?",
                    (time.time(), int(thread_id))
                )
                
                await db.execute("COMMIT")
                return True
            except sqlite3.OperationalError as e:
                try: await db.execute("ROLLBACK")
                except: pass
                
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    await asyncio.sleep(0.1 * (attempt + 1))
                    continue
                break
            except Exception:
                try: await db.execute("ROLLBACK")
                except: pass
                break
    return False
async def create_report(post_num: int, category: str, reason: str, sender_ip_hash: str) -> bool:
    """
    Создает жалобу на пост.
    """
    from common.db_pool import get_pool, db_lock
    
    async with db_lock:
        for attempt in range(10):
            try:
                db = await get_pool()
                await db.execute("BEGIN IMMEDIATE")
                
                # Проверка дубликатов (чтение внутри транзакции)
                async with db.execute(
                    "SELECT 1 FROM Reports WHERE post_num = ? AND sender_ip_hash = ?", 
                    (post_num, sender_ip_hash)
                ) as cursor:
                    if await cursor.fetchone():
                        await db.execute("COMMIT")
                        return False
                
                # Создание репорта
                await db.execute(
                    "INSERT INTO Reports (post_num, category, reason, sender_ip_hash, created_at) VALUES (?, ?, ?, ?, ?)",
                    (post_num, category, reason, sender_ip_hash, time.time())
                )
                
                # Обновление счетчика у поста
                await db.execute("UPDATE Posts SET report_count = report_count + 1 WHERE post_num = ?", (post_num,))
                
                await db.execute("COMMIT")
                return True
                
            except sqlite3.OperationalError as e:
                try: await db.execute("ROLLBACK")
                except: pass
                
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    await asyncio.sleep(0.1 * (attempt + 1))
                    continue
                print(f"⛔ Error creating report: {e}")
                break
            except Exception as e:
                try: await db.execute("ROLLBACK")
                except: pass
                print(f"⛔ Error creating report: {e}")
                break
            
    return False
async def get_active_reports(limit: int = 50) -> list[dict]:
    """Получает список активных (незакрытых) жалоб."""
    db = await get_pool()
    query = """
        SELECT r.id, r.post_num, r.category, r.reason, r.created_at, 
               p.content, p.board_id, p.author_id 
        FROM Reports r
        LEFT JOIN Posts p ON r.post_num = p.post_num
        WHERE r.status = 'open'
        ORDER BY r.created_at DESC
        LIMIT ?
    """
    try:
        async with db.execute(query, (limit,)) as cursor:
            rows = await cursor.fetchall()
            cols = [d[0] for d in cursor.description]
        results = []
        for row in rows:
            if hasattr(row, 'keys'):
                d = dict(row)
            else:
                d = dict(zip(cols, row))
            if d['content']:
                try:
                    d['content'] = json.loads(d['content'])
                except: pass
            else:
                d['content'] = {'text': '[Пост удален]', 'type': 'text'}
            results.append(d)
        return results
    finally:
        db.row_factory = None
async def resolve_report(report_id: int, resolution: str):
    """
    Закрывает жалобу (resolution: 'resolved' или 'dismissed').
    """
    from common.db_pool import get_pool, db_lock
    
    async with db_lock:
        for attempt in range(10):
            try:
                db = await get_pool()
                await db.execute("BEGIN IMMEDIATE")
                
                await db.execute("UPDATE Reports SET status = ? WHERE id = ?", (resolution, report_id))
                
                await db.execute("COMMIT")
                return
            except sqlite3.OperationalError as e:
                try: await db.execute("ROLLBACK")
                except: pass
                
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    await asyncio.sleep(0.1 * (attempt + 1))
                    continue
                print(f"⚠️ Ошибка при разрешении репорта: {e}")
                break
            except Exception as e:
                try: await db.execute("ROLLBACK")
                except: pass
                print(f"⚠️ Ошибка при разрешении репорта: {e}")
                break
async def toggle_thread_pin(thread_id: str, pinned: bool):
    from common.db_pool import get_pool, db_lock
    async with db_lock:
        try:
            db = await get_pool()
            await db.execute("BEGIN IMMEDIATE")
            await db.execute(
                "UPDATE Threads SET is_pinned = ? WHERE thread_num = ?",
                (1 if pinned else 0, int(thread_id))
            )
            await db.execute("COMMIT")
            return True
        except Exception as e:
            try: await db.execute("ROLLBACK")
            except: pass
            print(f"Error toggling pin for {thread_id}: {e}")
            return False
async def load_all_spam_words() -> Dict[str, set]:
    """
    Загружает все стоп-слова из БД и группирует их по board_id.
    """
    from common.db_pool import get_pool, db_lock
    from collections import defaultdict
    
    spam_words_map = defaultdict(set)
    async with db_lock:
        try:
            db = await get_pool()
            async with db.execute("SELECT board_id, word FROM SpamFilterWords") as cursor:
                async for row in cursor:
                    board_id, word = row
                    spam_words_map[board_id].add(word)
            print(f"  > DB: Загружено стоп-слов для спам-фильтра: {sum(len(s) for s in spam_words_map.values())} шт.")
            return spam_words_map
        except Exception as e:
            print(f"⛔ ОШИБКА при загрузке стоп-слов из БД: {e}")
            return defaultdict(set)
async def set_system_setting(key: str, value: str):
    """
    Устанавливает системную настройку.
    """
    from common.db_pool import get_pool, db_lock
    
    async with db_lock:
        for attempt in range(10):
            try:
                db = await get_pool()
                await db.execute("BEGIN IMMEDIATE")
                
                await db.execute("INSERT OR REPLACE INTO SystemSettings (key, value) VALUES (?, ?)", (key, value))
                
                await db.execute("COMMIT")
                return
            except sqlite3.OperationalError as e:
                try: await db.execute("ROLLBACK")
                except: pass
                
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    await asyncio.sleep(0.1 * (attempt + 1))
                    continue
                break
            except Exception:
                try: await db.execute("ROLLBACK")
                except: pass
                break
async def get_system_setting(key: str) -> str:
    db = await get_pool()
    try:
        async with db.execute("SELECT value FROM SystemSettings WHERE key = ?", (key,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else ""
    except Exception:
        return ""
async def create_board(board_id: str, name: str, description: str, owner_id: int, approved: int = 0) -> bool:
    from common.db_pool import get_pool, db_lock
    
    async with db_lock:
        for attempt in range(10):
            try:
                db = await get_pool()
                await db.execute("BEGIN IMMEDIATE")
                
                await db.execute(
                    "INSERT INTO Boards (board_id, name, description, owner_id, is_approved) VALUES (?, ?, ?, ?, ?)",
                    (board_id, name, description, owner_id, approved)
                )
                
                await db.execute("COMMIT")
                return True
            except sqlite3.OperationalError as e:
                try: await db.execute("ROLLBACK")
                except: pass
                
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    await asyncio.sleep(0.1 * (attempt + 1))
                    continue
                break
            except Exception as e:
                try: await db.execute("ROLLBACK")
                except: pass
                print(f"⚠️ Board creation error: {e}")
                break
    return False

async def approve_board(board_id: str):
    from common.db_pool import get_pool, db_lock
    
    async with db_lock:
        for attempt in range(10):
            try:
                db = await get_pool()
                await db.execute("BEGIN IMMEDIATE")
                
                await db.execute("UPDATE Boards SET is_approved = 1 WHERE board_id = ?", (board_id,))
                
                await db.execute("COMMIT")
                return
            except sqlite3.OperationalError as e:
                try: await db.execute("ROLLBACK")
                except: pass
                
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    await asyncio.sleep(0.1 * (attempt + 1))
                    continue
                break
            except Exception:
                try: await db.execute("ROLLBACK")
                except: pass
                break

async def delete_board(board_id: str):
    from common.db_pool import get_pool, db_lock
    
    async with db_lock:
        for attempt in range(10):
            try:
                db = await get_pool()
                await db.execute("BEGIN IMMEDIATE")
                
                await db.execute("DELETE FROM Boards WHERE board_id = ?", (board_id,))
                await db.execute("DELETE FROM Posts WHERE board_id = ?", (board_id,))
                
                await db.execute("COMMIT")
                return
            except sqlite3.OperationalError as e:
                try: await db.execute("ROLLBACK")
                except: pass
                
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    await asyncio.sleep(0.1 * (attempt + 1))
                    continue
                break
            except Exception:
                try: await db.execute("ROLLBACK")
                except: pass
                break
async def toggle_op_hidden(post_num: int, hide: bool) -> bool:
    from common.db_pool import get_pool, db_lock
    
    async with db_lock:
        for attempt in range(10):
            try:
                db = await get_pool()
                await db.execute("BEGIN IMMEDIATE")
                
                await db.execute(
                    "UPDATE Posts SET is_op_hidden = ? WHERE post_num = ?",
                    (1 if hide else 0, post_num)
                )
                
                await db.execute("COMMIT")
                return True
            except sqlite3.OperationalError as e:
                try: await db.execute("ROLLBACK")
                except: pass
                
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    await asyncio.sleep(0.1 * (attempt + 1))
                    continue
                print(f"Error toggling OP hide for {post_num}: {e}")
                break
            except Exception as e:
                try: await db.execute("ROLLBACK")
                except: pass
                print(f"Error toggling OP hide for {post_num}: {e}")
                break
    return False
async def get_all_boards_for_admin() -> list[dict]:
    """Возвращает ВСЕ доски (и активные, и ждущие)."""
    db = await get_pool()
    try:
        async with db.execute("SELECT * FROM Boards ORDER BY is_approved ASC, board_id ASC") as cursor:
            rows = await cursor.fetchall()
            cols = [d[0] for d in cursor.description]
            results = []
            for r in rows:
                if hasattr(r, 'keys'):
                    post_dict = dict(r)
                else:
                    post_dict = dict(zip(cols, r))
                results.append(post_dict)
            return results
    except Exception as e:
        print(f"Error getting boards: {e}")
        return []
async def create_import_request(user_id: int, url: str, board_id: str, comment: str) -> bool:
    from common.db_pool import get_pool, db_lock
    
    async with db_lock:
        for attempt in range(10):
            try:
                db = await get_pool()
                await db.execute("BEGIN IMMEDIATE")
                
                await db.execute(
                    "INSERT INTO ImportRequests (user_id, url, target_board, comment, created_at) VALUES (?, ?, ?, ?, ?)",
                    (user_id, url, board_id, comment, time.time())
                )
                
                await db.execute("COMMIT")
                return True
            except sqlite3.OperationalError as e:
                try: await db.execute("ROLLBACK")
                except: pass
                
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    await asyncio.sleep(0.1 * (attempt + 1))
                    continue
                break
            except Exception:
                try: await db.execute("ROLLBACK")
                except: pass
                break
    return False

async def update_import_request_status(request_id: int, status: str):
    from common.db_pool import get_pool, db_lock
    
    async with db_lock:
        for attempt in range(10):
            try:
                db = await get_pool()
                await db.execute("BEGIN IMMEDIATE")
                
                await db.execute("UPDATE ImportRequests SET status = ? WHERE id = ?", (status, request_id))
                
                await db.execute("COMMIT")
                return
            except sqlite3.OperationalError as e:
                try: await db.execute("ROLLBACK")
                except: pass
                
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    await asyncio.sleep(0.1 * (attempt + 1))
                    continue
                break
            except Exception:
                try: await db.execute("ROLLBACK")
                except: pass
                break
async def get_pending_import_requests() -> list[dict]:
    db = await get_pool()
    try:
        async with db.execute("SELECT * FROM ImportRequests WHERE status = 'pending' ORDER BY created_at ASC") as cursor:
            rows = await cursor.fetchall()
            cols = [d[0] for d in cursor.description]
            results = []
            for r in rows:
                if hasattr(r, 'keys'):
                    results.append(dict(r))
                else:
                    results.append(dict(zip(cols, r)))
            return results
    except Exception as e:
        print(f"Error getting import requests: {e}")
        return []
async def create_feedback(user_id: int, category: str, contact: str, message: str) -> bool:
    from common.db_pool import get_pool, db_lock
    
    async with db_lock:
        for attempt in range(10):
            try:
                db = await get_pool()
                await db.execute("BEGIN IMMEDIATE")
                
                await db.execute(
                    "INSERT INTO Feedback (user_id, category, contact, message, created_at) VALUES (?, ?, ?, ?, ?)",
                    (user_id, category, contact, message, time.time())
                )
                
                await db.execute("COMMIT")
                return True
            except sqlite3.OperationalError as e:
                try: await db.execute("ROLLBACK")
                except: pass
                
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    await asyncio.sleep(0.1 * (attempt + 1))
                    continue
                break
            except Exception as e:
                try: await db.execute("ROLLBACK")
                except: pass
                print(f"⚠️ Error creating feedback: {e}")
                break
    return False
async def get_all_feedback(limit: int = 50) -> list[dict]:
    """Получает последние сообщения обратной связи."""
    db = await get_pool()
    try:
        async with db.execute("SELECT * FROM Feedback ORDER BY created_at DESC LIMIT ?", (limit,)) as cursor:
            rows = await cursor.fetchall()
            cols = [d[0] for d in cursor.description]
            results = []
            for r in rows:
                if hasattr(r, 'keys'):
                    results.append(dict(r))
                else:
                    results.append(dict(zip(cols, r)))
            return results
    except Exception as e:
        print(f"Error getting feedback: {e}")
        return []

async def get_unread_feedback_count() -> int:
    """Возвращает кол-во непрочитанных писем."""
    db = await get_pool()
    try:
        async with db.execute("SELECT COUNT(*) FROM Feedback WHERE is_read = 0") as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0
    except: return 0

async def mark_feedback_read(item_id: int):
    """Помечает сообщение фидбека прочитанным."""
    from common.db_pool import get_pool, db_lock
    async with db_lock:
        try:
            db = await get_pool()
            await db.execute("BEGIN IMMEDIATE")
            await db.execute("UPDATE Feedback SET is_read = 1 WHERE id = ?", (item_id,))
            await db.execute("COMMIT")
        except Exception:
            try: await db.execute("ROLLBACK")
            except: pass
async def get_post_details_for_admin(post_num: int) -> dict | None:
    db = await get_pool()
    try:
        query_main = """
            SELECT 
                p.post_num, p.thread_id, p.board_id, p.content, p.timestamp, p.author_id, p.is_shadow,
                u.created_at as user_created_at,
                (SELECT COUNT(*) FROM Posts WHERE author_id = p.author_id) as total_posts
            FROM Posts p
            LEFT JOIN Users u ON p.author_id = u.user_id AND u.board_id = 'b'
            WHERE p.post_num = ?
        """
        async with db.execute(query_main, (post_num,)) as cursor:
            row = await cursor.fetchone()
            main_cols = [d[0] for d in cursor.description]
        if not row: return None
        if hasattr(row, 'keys'):
            data = dict(row)
        else:
            data = dict(zip(main_cols, row))
        try:
            data['content'] = json.loads(data['content'])
        except: 
            data['content'] = {"text": "Error parsing"}
        author_id = data['author_id']
        query_history = """
            SELECT post_num, board_id, content, timestamp 
            FROM Posts 
            WHERE author_id = ? 
            ORDER BY timestamp DESC 
            LIMIT 30
        """
        history = []
        async with db.execute(query_history, (author_id,)) as cursor:
            hist_cols = [d[0] for d in cursor.description]
            async for h_row in cursor:
                if hasattr(h_row, 'keys'):
                    h_item = dict(h_row)
                else:
                    h_item = dict(zip(hist_cols, h_row))
                try:
                    cnt = json.loads(h_item['content'])
                    preview = ""
                    if cnt.get('files'):
                        preview += f"[Файл: {cnt['files'][0]['type']}] "
                    text = cnt.get('text', '')
                    preview += text[:50] + "..." if len(text) > 50 else text
                    h_item['preview'] = preview
                except:
                    h_item['preview'] = "[Ошибка данных]"
                if 'content' in h_item: del h_item['content']
                history.append(h_item)
        
        data['history'] = history
        return data
    except Exception as e:
        print(f"Admin Inspect Error: {e}")
        return None
async def shadow_wipe_user(user_id: int, board_id: str = None) -> int:
    from common.db_pool import get_pool, db_lock
    
    async with db_lock:
        for attempt in range(10):
            try:
                db = await get_pool()
                await db.execute("BEGIN IMMEDIATE")
                
                if board_id and board_id != 'ALL':
                    cursor = await db.execute("UPDATE Posts SET is_shadow = 1 WHERE author_id = ? AND board_id = ?", (user_id, board_id))
                else:
                    cursor = await db.execute("UPDATE Posts SET is_shadow = 1 WHERE author_id = ?", (user_id,))
                
                row_count = cursor.rowcount
                await db.execute("COMMIT")
                return row_count
            except sqlite3.OperationalError as e:
                try: await db.execute("ROLLBACK")
                except: pass
                
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    await asyncio.sleep(0.1 * (attempt + 1))
                    continue
                break
            except Exception:
                try: await db.execute("ROLLBACK")
                except: pass
                break
    return 0
async def add_channel_copy(post_num: int, channel_id: int, message_id: int):
    from common.db_pool import get_pool, db_lock
    
    async with db_lock:
        for attempt in range(15):
            try:
                db = await get_pool()
                await db.execute("BEGIN IMMEDIATE")
                
                await db.execute(
                    "INSERT OR IGNORE INTO ChannelCopies (post_num, channel_id, message_id) VALUES (?, ?, ?)",
                    (post_num, channel_id, message_id)
                )
                
                await db.execute("COMMIT")
                return
            except sqlite3.OperationalError as e:
                try: await db.execute("ROLLBACK")
                except: pass
                
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    await asyncio.sleep(0.1 * (attempt + 1))
                    continue
                break
            except Exception:
                try: await db.execute("ROLLBACK")
                except: pass
                break

async def set_channel_message_id(post_num: int, message_id: int):
    from common.db_pool import get_pool, db_lock
    
    async with db_lock:
        for attempt in range(10):
            try:
                db = await get_pool()
                await db.execute("BEGIN IMMEDIATE")
                
                await db.execute(
                    "UPDATE Posts SET channel_message_id = ? WHERE post_num = ?",
                    (message_id, post_num)
                )
                
                await db.execute("COMMIT")
                return
            except sqlite3.OperationalError as e:
                try: await db.execute("ROLLBACK")
                except: pass
                
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    await asyncio.sleep(0.1 * (attempt + 1))
                    continue
                print(f"⚠️ Ошибка сохранения channel_message_id для #{post_num}: {e}")
                break
            except Exception as e:
                try: await db.execute("ROLLBACK")
                except: pass
                print(f"⚠️ Ошибка сохранения channel_message_id для #{post_num}: {e}")
                break

_BANNED_PHASH_CACHE = set()
_BANNED_CACHE_TIMESTAMP = 0
async def check_phash_ban(phash_str: str) -> bool:
    """
    Проверяет pHash на похожесть с забаненными.
    """
    if not phash_str: return False
    
    global _BANNED_PHASH_CACHE, _BANNED_CACHE_TIMESTAMP
    from common.db_pool import get_pool, db_lock
    
    # Обновляем кэш раз в 10 минут
    if time.time() - _BANNED_CACHE_TIMESTAMP > 600:
        async with db_lock:
            try:
                db = await get_pool()
                async with db.execute("SELECT hash_value FROM BannedHashes WHERE hash_type = 'phash'") as cursor:
                    rows = await cursor.fetchall()
                    _BANNED_PHASH_CACHE = {r[0] for r in rows}
                    _BANNED_CACHE_TIMESTAMP = time.time()
            except: pass
            
    if phash_str in _BANNED_PHASH_CACHE:
        return True
        
    return False
async def get_banned_files_list(limit: int = 100) -> list[dict]:
    """
    Возвращает список забаненных хешей + пример картинки (file_id) для превью.
    """
    db = await get_pool()
    query = """
        SELECT b.hash_value, b.hash_type, b.reason, 
               (SELECT file_id FROM FileRegistry f 
                WHERE (b.hash_type='sha256' AND f.sha256=b.hash_value) 
                   OR (b.hash_type='phash' AND f.phash=b.hash_value) 
                LIMIT 1) as example_file_id
        FROM BannedHashes b
        LIMIT ?
    """
    try:
        async with db.execute(query, (limit,)) as cursor:
            rows = await cursor.fetchall()
            cols = [d[0] for d in cursor.description]
            results = []
            for r in rows:
                if hasattr(r, 'keys'):
                    results.append(dict(r))
                else:
                    results.append(dict(zip(cols, r)))
            return results
    except Exception as e:
        print(f"Error getting banned files: {e}")
        return []
async def get_duplicate_counts(file_ids: list[str]) -> dict:
    """
    Возвращает словарь {file_id: count}.
    """
    if not file_ids: return {}
    
    from common.db_pool import get_pool, db_lock
    
    placeholders = ','.join('?' for _ in file_ids)
    # Используем self-join или subquery, это может быть долго, поэтому лок обязателен
    query = f"""
        SELECT f.file_id, counts.total
        FROM FileRegistry f
        JOIN (
            SELECT phash, COUNT(*) as total
            FROM FileRegistry
            WHERE phash IN (SELECT phash FROM FileRegistry WHERE file_id IN ({placeholders}))
            GROUP BY phash
            HAVING total > 1
        ) counts ON f.phash = counts.phash
        WHERE f.file_id IN ({placeholders})
    """
    
    counts = {}
    async with db_lock:
        try:
            db = await get_pool()
            # Передаем параметры дважды, так как они используются в двух местах запроса (IN clause)
            async with db.execute(query, file_ids + file_ids) as cursor:
                async for row in cursor:
                    counts[row[0]] = row[1]
        except Exception as e:
            print(f"⚠️ Dup check error: {e}")
            
    return counts
async def get_recent_posts_global(limit: int = 20) -> list[dict]:
    """Возвращает последние N постов со всех досок для Live Feed."""
    from common.db_pool import get_pool, db_lock
    
    async with db_lock:
        try:
            db = await get_pool()
            db.row_factory = aiosqlite.Row
            query = """
                SELECT post_num, board_id, thread_id, content, timestamp, author_id
                FROM Posts 
                ORDER BY timestamp DESC 
                LIMIT ?
            """
            posts = []
            async with db.execute(query, (limit,)) as cursor:
                cols = [d[0] for d in cursor.description]
                async for row in cursor:
                    if hasattr(row, 'keys'):
                        post_data = dict(row)
                    else:
                        post_data = dict(zip(cols, row))
                    
                    try:
                        post_data['id'] = post_data.pop('post_num')
                        if isinstance(post_data['content'], str):
                            post_data['content'] = json.loads(post_data['content'])
                        elif not isinstance(post_data['content'], dict):
                             post_data['content'] = {'text': '', 'type': 'text'}
                        posts.append(post_data)
                    except Exception:
                        continue
            return posts
        except Exception as e:
            print(f"⛔ Error in get_recent_posts_global: {e}")
            return []
        finally:
            if 'db' in locals() and db:
                db.row_factory = None
async def get_global_feed_posts(
    board_ids: Union[str, List[str], None], 
    page: int = 1, 
    page_size: int = 20,
    stream: str = 'ru',
    observer_id: int = None,
    include_chat: bool = True,
    sort_by: str = 'new'
) -> list:
    from common.db_pool import get_pool, db_lock
    
    offset = (page - 1) * page_size
    viewer_id = observer_id if observer_id else -1
    
    async with db_lock:
        try:
            db = await get_pool()
            db.row_factory = aiosqlite.Row
            
            where_clauses = [
                f"(IFNULL(p.is_shadow, 0) = 0 OR p.author_id = {viewer_id})",
                "(p.stream = ? OR p.stream IS NULL)"
            ]
            
            if not include_chat:
                where_clauses.append("p.thread_id IS NOT NULL")
            params = [stream]
            
            if board_ids:
                if isinstance(board_ids, list) and len(board_ids) > 0:
                    placeholders = ','.join('?' for _ in board_ids)
                    where_clauses.append(f"p.board_id IN ({placeholders})")
                    params.extend(board_ids)
                elif isinstance(board_ids, str):
                    where_clauses.append("p.board_id = ?")
                    params.append(board_ids)
            
            where_str = " AND ".join(where_clauses)
            
            if sort_by == 'random':
                ids_query = f"SELECT p.post_num FROM Posts p WHERE {where_str}"
                
                all_ids = []
                async with db.execute(ids_query, params) as cursor:
                    async for row in cursor:
                        all_ids.append(row['post_num'])
                
                if not all_ids:
                    return []

                seed_val = int(time.time() / 600)
                rng = random.Random(seed_val)
                rng.shuffle(all_ids)
                
                target_ids = all_ids[offset : offset + page_size]
                
                if not target_ids:
                    return []
                
                placeholders_in = ','.join('?' for _ in target_ids)
                
                query = f"""
                    SELECT 
                        p.post_num, p.board_id, p.thread_id, p.content, p.timestamp, p.author_id, p.stream, p.is_shadow,
                        p.reply_to_post_num,
                        t.title as thread_title
                    FROM Posts p
                    LEFT JOIN Threads t ON p.thread_id = t.thread_id
                    WHERE p.post_num IN ({placeholders_in})
                """
                query_params = target_ids
                
            else:
                query = f"""
                    SELECT 
                        p.post_num, p.board_id, p.thread_id, p.content, p.timestamp, p.author_id, p.stream, p.is_shadow,
                        p.reply_to_post_num,
                        t.title as thread_title
                    FROM Posts p
                    LEFT JOIN Threads t ON p.thread_id = t.thread_id
                    WHERE {where_str}
                    ORDER BY p.timestamp DESC
                    LIMIT ? OFFSET ?
                """
                query_params = params + [page_size, offset]

            posts_unordered = []
            async with db.execute(query, query_params) as cursor:
                cols = [d[0] for d in cursor.description]
                async for row in cursor:
                    if hasattr(row, 'keys'):
                        post_data = dict(row)
                    else:
                        post_data = dict(zip(cols, row))
                
                    try:
                        post_data['id'] = post_data.pop('post_num')
                        if isinstance(post_data['content'], str):
                            post_data['content'] = json.loads(post_data['content'])
                        elif not isinstance(post_data['content'], dict):
                            post_data['content'] = {'text': '', 'type': 'text'}
                        post_data['is_feed_mode'] = True
                        posts_unordered.append(post_data)
                    except Exception:
                        continue
            
            if sort_by == 'random':
                posts_map = {p['id']: p for p in posts_unordered}
                posts = []
                for pid in target_ids:
                    if pid in posts_map:
                        posts.append(posts_map[pid])
            else:
                posts = posts_unordered
                        
            return posts

        except Exception as e:
            print(f"Error in get_global_feed_posts: {e}")
            return []
        finally:
            if 'db' in locals() and db:
                db.row_factory = None
async def get_full_user_info(user_id: int) -> Optional[Dict[str, Any]]:
    """Возвращает полное досье на пользователя по ID."""
    from common.db_pool import get_pool, db_lock
    
    info = {
        "user_id": user_id,
        "first_seen": 0,
        "total_posts": 0,
        "boards": [], 
        "active_bans": [],
        "last_posts": [],
        "global_role": "user"
    }
    
    async with db_lock:
        try:
            db = await get_pool()
            async with db.execute("SELECT board_id, status, role, created_at FROM Users WHERE user_id = ? ORDER BY created_at ASC", (user_id,)) as cursor:
                rows = await cursor.fetchall()
                if rows:
                    info["first_seen"] = rows[0][3] or 0
                    roles = [r[2] for r in rows if r[2]]
                    if "admin" in roles: info["global_role"] = "admin"
                    elif "mod" in roles: info["global_role"] = "mod"
                    elif "janitor" in roles: info["global_role"] = "janitor"
                    
                    for r in rows:
                        info["boards"].append({
                            "board_id": r[0],
                            "status": r[1],
                            "role": r[2] or "user"
                        })
            async with db.execute("SELECT COUNT(*) FROM Posts WHERE author_id = ?", (user_id,)) as cursor:
                row = await cursor.fetchone()
                info["total_posts"] = row[0] if row else 0
            db.row_factory = aiosqlite.Row
            query = "SELECT post_num, board_id, content, timestamp FROM Posts WHERE author_id = ? ORDER BY timestamp DESC LIMIT 20"
            async with db.execute(query, (user_id,)) as cursor:
                cols = [d[0] for d in cursor.description]
                async for row in cursor:
                    if hasattr(row, 'keys'): pd = dict(row)
                    else: pd = dict(zip(cols, row))
                    
                    try:
                        if isinstance(pd['content'], str):
                            pd['content'] = json.loads(pd['content'])
                        pd['id'] = pd.pop('post_num')
                    except: pass
                    info["last_posts"].append(pd)
            db.row_factory = None
            async with db.execute("SELECT board_id, mute_type, expires_at FROM Mutes WHERE user_id = ? AND expires_at > ?", (user_id, time.time())) as cursor:
                async for row in cursor:
                    info["active_bans"].append({
                        "board_id": row[0],
                        "type": row[1],
                        "expires_at": row[2]
                    })
            
            return info

        except Exception as e:
            print(f"⛔ Error in get_full_user_info: {e}")
            return None
async def remove_users_from_board_batch(user_ids: list[int], board_id: str):
    """
    Массово удаляет список пользователей с доски с защитой от блокировок.
    """
    if not user_ids: return
    
    from common.db_pool import get_pool, db_lock
    
    async with db_lock:
        for attempt in range(10):
            try:
                db = await get_pool()
                await db.execute("BEGIN IMMEDIATE")
                
                placeholders = ','.join('?' for _ in user_ids)
                query = f"DELETE FROM Users WHERE board_id = ? AND user_id IN ({placeholders})"
                params = [board_id] + list(user_ids)
                
                cursor = await db.execute(query, params)
                count = cursor.rowcount
                
                await db.execute("COMMIT")
                
                if count > 0:
                    print(f"  > DB: Удалено {count} пользователей с доски '{board_id}'.")
                return
            except sqlite3.OperationalError as e:
                try: await db.execute("ROLLBACK")
                except: pass
                
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    await asyncio.sleep(0.1 * (attempt + 1))
                    continue
                break
            except Exception:
                try: await db.execute("ROLLBACK")
                except: pass
                break
async def ban_hash(value: str, type: str, reason: str):
    from common.db_pool import get_pool, db_lock
    # При сбросе кэша в глобальной области видимости может потребоваться импорт или доступ к переменной модуля
    # Здесь предполагаем, что _BANNED_CACHE_TIMESTAMP доступна или будет обновлена при следующем чтении
    
    async with db_lock:
        for attempt in range(10):
            try:
                db = await get_pool()
                await db.execute("BEGIN IMMEDIATE")
                
                await db.execute(
                    "INSERT OR REPLACE INTO BannedHashes (hash_value, hash_type, reason) VALUES (?, ?, ?)", 
                    (value, type, reason)
                )
                
                await db.execute("COMMIT")
                return
            except sqlite3.OperationalError as e:
                try: await db.execute("ROLLBACK")
                except: pass
                
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    await asyncio.sleep(0.1 * (attempt + 1))
                    continue
                print(f"⛔ Ошибка при бане хеша {value}: {e}")
                break
            except Exception as e:
                try: await db.execute("ROLLBACK")
                except: pass
                print(f"⛔ Ошибка при бане хеша {value}: {e}")
                break

async def unban_hash(hash_value: str):
    from common.db_pool import get_pool, db_lock
    
    async with db_lock:
        for attempt in range(10):
            try:
                db = await get_pool()
                await db.execute("BEGIN IMMEDIATE")
                
                await db.execute("DELETE FROM BannedHashes WHERE hash_value = ?", (hash_value,))
                
                await db.execute("COMMIT")
                return
            except sqlite3.OperationalError as e:
                try: await db.execute("ROLLBACK")
                except: pass
                
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    await asyncio.sleep(0.1 * (attempt + 1))
                    continue
                break
            except Exception:
                try: await db.execute("ROLLBACK")
                except: pass
                break
async def get_all_channel_copies(post_num: int) -> list[tuple[int, int]]:
    """
    Возвращает список всех мест, где лежит этот пост в каналах.
    """
    from common.db_pool import get_pool, db_lock
    
    async with db_lock:
        try:
            db = await get_pool()
            async with db.execute("SELECT channel_id, message_id FROM ChannelCopies WHERE post_num = ?", (post_num,)) as cursor:
                return await cursor.fetchall()
        except Exception:
            return []
async def cleanup_shadow_posts_db(hours: int = 24):
    """
    Удаляет старые теневые посты порциями, чтобы не блокировать БД надолго.
    """
    from common.db_pool import get_pool, db_lock
    cutoff = time.time() - (hours * 3600)
    chunk_size = 500  # Удаляем по 500 штук за раз
    total_deleted = 0
    
    # Внешний цикл для порционной обработки
    while True:
        async with db_lock:
            # Цикл попыток для одной транзакции
            transaction_success = False
            deleted_in_chunk = 0
            
            for attempt in range(10):
                try:
                    db = await get_pool()
                    await db.execute("BEGIN IMMEDIATE")
                    
                    # 1. Находим ID кандидатов на удаление (LIMIT)
                    # Используем подзапрос для получения ID, чтобы удалить связанные треды и посты
                    # SQLite delete limit эмулируется через WHERE rowid IN (SELECT ... LIMIT N)
                    
                    ids_to_delete = []
                    async with db.execute(
                        "SELECT post_num FROM Posts WHERE is_shadow = 1 AND timestamp < ? LIMIT ?", 
                        (cutoff, chunk_size)
                    ) as cursor:
                        rows = await cursor.fetchall()
                        ids_to_delete = [r[0] for r in rows]
                    
                    if not ids_to_delete:
                        await db.execute("COMMIT")
                        transaction_success = True
                        break # Больше нечего удалять
                        
                    placeholders = ','.join('?' for _ in ids_to_delete)
                    
                    # 2. Удаляем треды, если эти посты были ОП-постами
                    # Преобразуем int ID в строки для thread_id
                    thread_ids = [str(x) for x in ids_to_delete]
                    t_placeholders = ','.join('?' for _ in thread_ids)
                    
                    await db.execute(
                        f"DELETE FROM Threads WHERE thread_id IN ({t_placeholders})", 
                        thread_ids
                    )
                    
                    # 3. Удаляем сами посты
                    cursor = await db.execute(
                        f"DELETE FROM Posts WHERE post_num IN ({placeholders})", 
                        ids_to_delete
                    )
                    deleted_in_chunk = cursor.rowcount
                    
                    await db.execute("COMMIT")
                    transaction_success = True
                    break
                    
                except sqlite3.OperationalError as e:
                    try: await db.execute("ROLLBACK")
                    except: pass
                    
                    if "locked" in str(e).lower() or "busy" in str(e).lower():
                        await asyncio.sleep(0.2 * (attempt + 1))
                        continue
                    print(f"⚠️ Shadow cleanup DB error: {e}")
                    return # Критическая ошибка, выходим
                except Exception as e:
                    try: await db.execute("ROLLBACK")
                    except: pass
                    print(f"⚠️ Shadow cleanup critical error: {e}")
                    return

        # Если в этой итерации ничего не удалили - значит, закончили
        if transaction_success:
            if deleted_in_chunk == 0:
                break
            
            total_deleted += deleted_in_chunk
            # ВАЖНО: Пауза между транзакциями, чтобы дать другим записать данные
            await asyncio.sleep(0.5) 
        else:
            # Если транзакция не прошла после всех попыток
            break

    if total_deleted > 0:
        print(f"🧹 Shadow Cleanup: Удалено {total_deleted} старых теневых постов (порциями).")
async def get_detailed_statistics() -> dict:
    from common.db_pool import get_pool, db_lock
    from common.board_config import BOARD_CONFIG
    
    now = time.time()
    day_ago = now - 86400
    week_ago = now - 604800
    hour_ago = now - 3600
    stats = {}
    
    async with db_lock:
        try:
            db = await get_pool()
            for board_id in BOARD_CONFIG:
                stats[board_id] = {
                    "total_threads": 0, "threads_24h": 0, "threads_7d": 0,
                    "total_posts": 0, "posts_24h": 0, "posts_7d": 0, "posts_1h": 0,
                    "top_threads": []
                }
            async with db.execute("""
                SELECT board_id, 
                       COUNT(*) as total,
                       SUM(CASE WHEN timestamp > ? THEN 1 ELSE 0 END) as p24h,
                       SUM(CASE WHEN timestamp > ? THEN 1 ELSE 0 END) as p7d,
                       SUM(CASE WHEN timestamp > ? THEN 1 ELSE 0 END) as p1h
                FROM Posts
                WHERE IFNULL(is_shadow, 0) = 0
                GROUP BY board_id
            """, (day_ago, week_ago, hour_ago)) as cursor:
                async for row in cursor:
                    bid = row[0]
                    if bid in stats:
                        stats[bid]["total_posts"] = row[1]
                        stats[bid]["posts_24h"] = row[2] or 0
                        stats[bid]["posts_7d"] = row[3] or 0
                        stats[bid]["posts_1h"] = row[4] or 0
            
            async with db.execute("""
                SELECT board_id,
                       COUNT(*) as total,
                       SUM(CASE WHEN created_at > ? THEN 1 ELSE 0 END) as t24h,
                       SUM(CASE WHEN created_at > ? THEN 1 ELSE 0 END) as t7d
                FROM Threads
                GROUP BY board_id
            """, (day_ago, week_ago)) as cursor:
                async for row in cursor:
                    bid = row[0]
                    if bid in stats:
                        stats[bid]["total_threads"] = row[1]
                        stats[bid]["threads_24h"] = row[2] or 0
                        stats[bid]["threads_7d"] = row[3] or 0
            
            for bid in stats.keys():
                async with db.execute("""
                    SELECT thread_id, title, last_updated_at 
                    FROM Threads 
                    WHERE board_id = ? AND is_archived = 0
                    ORDER BY last_updated_at DESC 
                    LIMIT 5
                """, (bid,)) as cursor:
                    async for row in cursor:
                        title = row[1] if row[1] else "Без названия"
                        short_title = (title[:28] + '..') if len(title) > 30 else title
                        stats[bid]["top_threads"].append({
                            "id": row[0],
                            "title": short_title,
                            "ts": row[2]
                        })
            return stats
        except Exception as e:
            print(f"⛔ Stats error: {e}")
            return {}
async def process_cross_links(source_board: str, source_post: int, text: str, stream: str = 'ru'):
    import re
    refs = re.findall(r'(?:>>|&gt;&gt;)/([a-z0-9]+)/(\d+)', text or "")
    if not refs: return
    
    potential_targets = set()
    for t_board, t_post in refs:
        if t_board == source_board: continue
        potential_targets.add(int(t_post))
    if not potential_targets: return

    from common.db_pool import get_pool, db_lock
    async with db_lock:
        for attempt in range(10):
            try:
                db = await get_pool()
                valid_targets = set()
                placeholders = ','.join('?' for _ in potential_targets)
                query = f"SELECT post_num FROM Posts WHERE post_num IN ({placeholders}) AND stream = ?"
                params = list(potential_targets) + [stream]
                
                async with db.execute(query, params) as cursor:
                    async for row in cursor:
                        valid_targets.add(row[0])
                
                await db.execute("BEGIN IMMEDIATE")
                links_to_insert = []
                for target_board, target_post_str in set(refs):
                    target_post = int(target_post_str)
                    if target_post in valid_targets:
                        links_to_insert.append((source_board, source_post, target_board, target_post))
                
                if links_to_insert:
                    await db.executemany(
                        "INSERT OR IGNORE INTO CrossLinks (source_board, source_post, target_board, target_post) VALUES (?, ?, ?, ?)",
                        links_to_insert
                    )
                await db.execute("COMMIT")
                return
            except sqlite3.OperationalError as e:
                try: await db.execute("ROLLBACK")
                except: pass
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    await asyncio.sleep(0.1 * (attempt + 1))
                    continue
                break
            except Exception:
                try: await db.execute("ROLLBACK")
                except: pass
                break
async def process_backlinks(source_post_num: int, text: str, reply_to_int: Optional[int] = None):
    import re
    refs = set(re.findall(r'(?:>>|&gt;&gt;)(\d+)', text))
    
    if reply_to_int:
        refs.add(str(reply_to_int))
        
    if str(source_post_num) in refs:
        refs.remove(str(source_post_num))
        
    if not refs: return

    from common.db_pool import get_pool, db_lock

    # Используем глобальный лок для записи
    async with db_lock:
        for attempt in range(10):
            try:
                db = await get_pool()
                
                # 1. Проверяем существование целевых постов (Foreign Key Constraint)
                valid_targets = set()
                params = list(refs)
                placeholders = ','.join('?' for _ in params)
                
                # Читаем существующие ID (можно без транзакции, если WAL, но мы уже под локом)
                async with db.execute(f"SELECT post_num FROM Posts WHERE post_num IN ({placeholders})", params) as cursor:
                    async for row in cursor:
                        valid_targets.add(row[0])
                
                if not valid_targets:
                    return

                # 2. Вставка
                await db.execute("BEGIN IMMEDIATE")
                
                links_to_insert = [(target, source_post_num) for target in valid_targets]
                await db.executemany(
                    "INSERT OR IGNORE INTO Backlinks (target_post_num, source_post_num) VALUES (?, ?)",
                    links_to_insert
                )
                
                await db.execute("COMMIT")
                return

            except sqlite3.OperationalError as e:
                try: await db.execute("ROLLBACK")
                except: pass
                
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    await asyncio.sleep(0.1 * (attempt + 1))
                    continue
                print(f"⚠️ Backlink Insert Error for #{source_post_num}: {e}")
                break
            except Exception as e:
                try: await db.execute("ROLLBACK")
                except: pass
                print(f"⚠️ Backlink Insert Error for #{source_post_num}: {e}")
                break
async def get_cross_links_for_thread(board_id: str, post_nums: list) -> dict:
    """
    Получает внешние ответы для пачки постов за ОДИН запрос.
    Возвращает: { target_post_id: [ {board, post}, ... ] }
    """
    if not post_nums: return {}
    db = await get_pool()
    placeholders = ','.join('?' for _ in post_nums)
    query = f"""
        SELECT source_board, source_post, target_post 
        FROM CrossLinks 
        WHERE target_board = ? AND target_post IN ({placeholders})
    """
    links_map = defaultdict(list)
    try:
        params = [board_id] + post_nums
        async with db.execute(query, params) as cursor:
            async for row in cursor:
                s_board, s_post, t_post = row
                links_map[t_post].append({'board': s_board, 'post': s_post})
        return links_map
    except Exception as e:
        print(f"⚠️ CrossLink Read Error: {e}")
        return {}
async def find_post_by_file_id(file_id_substring: str) -> dict | None:
    """
    Ищет пост, в контенте которого встречается указанный ID файла (или его часть).
    """
    db = await get_pool()
    try:
        # Ищем подстроку в поле content (там JSON).
        # file_id в телеграме длинный, ищем точное вхождение строки
        query = """
            SELECT post_num, board_id, author_id, content, timestamp 
            FROM Posts 
            WHERE instr(content, ?) > 0
            ORDER BY timestamp DESC 
            LIMIT 1
        """
        search_pattern = file_id_substring
        
        async with db.execute(query, (search_pattern,)) as cursor:
            row = await cursor.fetchone()
            
        if row:
            return {
                'id': row[0],
                'board_id': row[1],
                'author_id': row[2],
                'content': json.loads(row[3]) if isinstance(row[3], str) else row[3],
                'timestamp': row[4]
            }
        return None
    except Exception as e:
        print(f"⛔ Ошибка поиска файла в БД: {e}")
        return None
    
async def get_activity_history(days: int = 7) -> dict:
    """Возвращает количество постов по дням за последние N дней."""
    db = await get_pool()
    try:
        # SQLite: strftime('%Y-%m-%d', datetime(timestamp, 'unixepoch'))
        query = """
            SELECT date(datetime(timestamp, 'unixepoch')) as d, COUNT(*) 
            FROM Posts 
            WHERE timestamp > ?
            GROUP BY d
            ORDER BY d ASC
        """
        start_ts = time.time() - (days * 86400)
        async with db.execute(query, (start_ts,)) as cursor:
            rows = await cursor.fetchall()
            return {r[0]: r[1] for r in rows}
    except Exception as e:
        print(f"Stats error: {e}")
        return {}
async def get_newspaper_data(date_str: str) -> dict:
    import datetime
    from common.db_pool import get_pool
    db = await get_pool()
    db.row_factory = aiosqlite.Row
    try:
        dt = datetime.datetime.strptime(date_str, "%Y-%m-%d")
        start_ts = dt.timestamp()
        end_ts = start_ts + 86400
    except Exception:
        return {}
        
    res = {
        "date": date_str,
        "total_posts": 0,
        "active_authors": 0,
        "new_threads_count": 0,
        "top_threads": [],
        "longest_posts": [],
        "recent_media": []
    }
    
    try:
        # 1. Total posts
        async with db.execute("SELECT COUNT(*) FROM Posts WHERE timestamp BETWEEN ? AND ? AND IFNULL(is_shadow, 0) = 0", (start_ts, end_ts)) as cursor:
            row = await cursor.fetchone()
            if row: res["total_posts"] = row[0]
            
        # 2. Active authors
        async with db.execute("SELECT COUNT(DISTINCT author_id) FROM Posts WHERE timestamp BETWEEN ? AND ? AND author_id != 0 AND IFNULL(is_shadow, 0) = 0", (start_ts, end_ts)) as cursor:
            row = await cursor.fetchone()
            if row: res["active_authors"] = row[0]
            
        # 3. New threads count
        async with db.execute("SELECT COUNT(*) FROM Threads WHERE created_at BETWEEN ? AND ?", (start_ts, end_ts)) as cursor:
            row = await cursor.fetchone()
            if row: res["new_threads_count"] = row[0]
            
        # 4. Top threads by posts in this day
        query_threads = """
            SELECT p.thread_id, p.board_id, t.title, COUNT(p.post_num) as cnt
            FROM Posts p
            JOIN Threads t ON p.thread_id = t.thread_id
            WHERE p.timestamp BETWEEN ? AND ? AND p.thread_id IS NOT NULL AND IFNULL(p.is_shadow, 0) = 0
            GROUP BY p.thread_id ORDER BY cnt DESC LIMIT 5
        """
        async with db.execute(query_threads, (start_ts, end_ts)) as cursor:
            rows = await cursor.fetchall()
            for r in rows:
                res["top_threads"].append({
                    "thread_id": r["thread_id"],
                    "board_id": r["board_id"],
                    "title": r["title"] or "Без названия",
                    "posts_count": r["cnt"]
                })
                
        # 5. Longest posts (slang columns)
        query_longest = """
            SELECT p.post_num, p.board_id, p.thread_id, p.content, p.author_id, p.timestamp
            FROM Posts p
            WHERE p.timestamp BETWEEN ? AND ? AND IFNULL(p.is_shadow, 0) = 0 AND length(p.content) > 30
            ORDER BY length(p.content) DESC LIMIT 8
        """
        async with db.execute(query_longest, (start_ts, end_ts)) as cursor:
            rows = await cursor.fetchall()
            for r in rows:
                res["longest_posts"].append({
                    "post_num": r["post_num"],
                    "board_id": r["board_id"],
                    "thread_id": r["thread_id"],
                    "content": r["content"],
                    "author_id": r["author_id"],
                    "timestamp": r["timestamp"]
                })
                
        return res
    except Exception as e:
        print(f"Newspaper data error: {e}")
        return res
    finally:
        db.row_factory = None

async def get_top_active_threads(hours: int = 8, limit: int = 10):
    """Находит треды с наибольшим количеством новых постов за период. Скрывает активность shadow-постов."""
    db = await get_pool()
    cutoff = time.time() - (hours * 3600)
    query = """
        SELECT 
            p.thread_id, 
            p.board_id, 
            t.title, 
            COUNT(p.post_num) as posts_count
        FROM Posts p
        JOIN Threads t ON p.thread_id = t.thread_id
        WHERE p.timestamp > ? 
          AND p.thread_id IS NOT NULL 
          AND IFNULL(p.is_shadow, 0) = 0
        GROUP BY p.thread_id
        ORDER BY posts_count DESC
        LIMIT ?
    """
    try:
        async with db.execute(query, (cutoff, limit)) as cursor:
            rows = await cursor.fetchall()
            return [
                {
                    'thread_id': r[0],
                    'board_id': r[1],
                    'title': r[2],
                    'posts_count': r[3]
                } for r in rows
            ]
    except Exception as e:
        print(f"Error fetching top threads: {e}")
        return []
async def get_updates_since(board_id: str, since_ts: float) -> list[dict]:
    """Для поллинга: возвращает посты, созданные после since_ts. Скрывает shadow-посты."""
    from common.db_pool import get_pool, db_lock
    
    async with db_lock:
        try:
            db = await get_pool()
            db.row_factory = aiosqlite.Row
            query = """
                SELECT * FROM Posts 
                WHERE board_id = ? AND timestamp > ? AND IFNULL(is_shadow, 0) = 0
                ORDER BY timestamp ASC LIMIT 50
            """
            posts = []
            async with db.execute(query, (board_id, since_ts)) as cursor:
                cols = [d[0] for d in cursor.description]
                async for row in cursor:
                    if hasattr(row, 'keys'):
                        post_dict = dict(row)
                    else:
                        post_dict = dict(zip(cols, row))

                    post_dict['id'] = post_dict.pop('post_num')
                    try:
                        post_dict['content'] = json.loads(post_dict['content'])
                        posts.append(post_dict)
                    except: continue
            return posts
        except Exception as e:
            print(f"Error in get_updates_since: {e}")
            return []
        finally:
            if 'db' in locals() and db:
                db.row_factory = None

async def add_file_mirror(file_id: str, mirror_type: str, url: str):
    """
    Добавляет зеркало для файла.
    """
    from common.db_pool import get_pool, db_lock
    
    async with db_lock:
        for attempt in range(10):
            try:
                db = await get_pool()
                await db.execute("BEGIN IMMEDIATE")
                
                await db.execute(
                    "INSERT OR IGNORE INTO FileMirrors (file_id, mirror_type, url) VALUES (?, ?, ?)",
                    (file_id, mirror_type, url)
                )
                
                await db.execute("COMMIT")
                return
            except sqlite3.OperationalError as e:
                try: await db.execute("ROLLBACK")
                except: pass
                
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    await asyncio.sleep(0.1 * (attempt + 1))
                    continue
                break
            except Exception:
                try: await db.execute("ROLLBACK")
                except: pass
                break
async def register_file_owners_batch(conn: aiosqlite.Connection, owner_pairs: list[tuple[str, int]]):
    """
    Массовая регистрация владельцев файлов.
    Принимает УЖЕ открытое соединение.
    ВАЖНО: Вызывающий код обязан обеспечить транзакцию (BEGIN/COMMIT) или блокировку, 
    если conn - это общее соединение.
    """
    if not owner_pairs:
        return
        
    # В этой функции мы не делаем BEGIN/COMMIT, так как предполагается, 
    # что она часть большей транзакции. 
    # Но мы добавляем retry на уровне execute для надежности.
    
    for attempt in range(10):
        try:
            await conn.executemany(
                "INSERT OR IGNORE INTO FileOwners (file_id, bot_id) VALUES (?, ?)",
                owner_pairs
            )
            return
        except sqlite3.OperationalError as e:
            if "locked" in str(e).lower() and attempt < 9:
                await asyncio.sleep(0.1 * (attempt + 1))
                continue
            print(f"⚠️ Error in batch registration: {e}")
            raise e
        except Exception as e:
            print(f"⚠️ Error in batch registration: {e}")
            raise e
async def cleanup_notification_queue(retention_hours: int = 48):
    """
    Удаляет записи из NotificationQueue, которые старше указанного количества часов.
    """
    from common.db_pool import get_pool, db_lock
    cutoff_timestamp = time.time() - (retention_hours * 3600)
    
    async with db_lock:
        for attempt in range(10):
            try:
                db = await get_pool()
                await db.execute("BEGIN IMMEDIATE")
                
                cursor = await db.execute("DELETE FROM NotificationQueue WHERE created_at < ?", (cutoff_timestamp,))
                deleted_count = cursor.rowcount
                
                await db.execute("COMMIT")
                
                if deleted_count > 0:
                    print(f"🧹 Очистка БД: Удалено {deleted_count} устаревших уведомлений.")
                return
            except sqlite3.OperationalError as e:
                try: await db.execute("ROLLBACK")
                except: pass
                
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    await asyncio.sleep(0.5 * (attempt + 1))
                    continue
                break
            except Exception:
                try: await db.execute("ROLLBACK")
                except: pass
                break
async def log_global_event(source: str, text: str):
    """
    Записывает событие в единую базу логов.
    """
    from common.db_pool import get_pool, db_lock
    
    async with db_lock:
        for attempt in range(10):
            try:
                db = await get_pool()
                await db.execute("BEGIN IMMEDIATE")
                
                await db.execute(
                    "INSERT INTO GlobalLogs (source, event_text, created_at) VALUES (?, ?, ?)",
                    (source, text, time.time())
                )
                
                await db.execute("COMMIT")
                return
            except sqlite3.OperationalError as e:
                try: await db.execute("ROLLBACK")
                except: pass
                
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    await asyncio.sleep(0.1 * (attempt + 1))
                    continue
                print(f"⛔ Ошибка записи лога: {e}")
                break
            except Exception as e:
                try: await db.execute("ROLLBACK")
                except: pass
                print(f"⛔ Ошибка записи лога: {e}")
                break
async def add_to_mod_queue(post_num: int, file_id: str, reason: str, score: float):
    """
    Добавляет пост в очередь на ручную проверку.
    """
    from common.db_pool import get_pool, db_lock
    
    async with db_lock:
        for attempt in range(10):
            try:
                db = await get_pool()
                await db.execute("BEGIN IMMEDIATE")
                
                # Проверяем, нет ли уже этого поста в очереди
                async with db.execute("SELECT 1 FROM ModQueue WHERE post_num = ?", (post_num,)) as cursor:
                    if await cursor.fetchone(): 
                        await db.execute("COMMIT")
                        return

                await db.execute(
                    "INSERT INTO ModQueue (post_num, file_id, reason, score, created_at) VALUES (?, ?, ?, ?, ?)",
                    (post_num, file_id, reason, score, time.time())
                )
                
                await db.execute("COMMIT")
                return
            except sqlite3.OperationalError as e:
                try: await db.execute("ROLLBACK")
                except: pass
                
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    await asyncio.sleep(0.1 * (attempt + 1))
                    continue
                print(f"⚠️ ModQueue add error: {e}")
                break
            except Exception as e:
                try: await db.execute("ROLLBACK")
                except: pass
                print(f"⚠️ ModQueue add error: {e}")
                break

async def get_mod_queue() -> list[dict]:
    """Возвращает список подозрительных постов."""
    db = await get_pool()
    query = """
        SELECT mq.id, mq.post_num, mq.reason, mq.score, mq.created_at, 
               p.content, p.board_id, p.author_id
        FROM ModQueue mq
        JOIN Posts p ON mq.post_num = p.post_num
        WHERE mq.status = 'pending'
        ORDER BY mq.score DESC
    """
    try:
        async with db.execute(query) as cursor:
            rows = await cursor.fetchall()
            cols = [d[0] for d in cursor.description]
        results = []
        for row in rows:
            if hasattr(row, 'keys'):
                d = dict(row)
            else:
                d = dict(zip(cols, row))
            try:
                d['content'] = json.loads(d['content'])
                thumb = ""
                if d['content'].get('files'):
                    for f in d['content']['files']:
                        if f.get('thumbnail_url'): thumb = f['thumbnail_url']
                        elif f.get('original_url'): thumb = f['original_url']
                        break
                d['thumb_url'] = thumb
            except: 
                d['thumb_url'] = ""
            results.append(d)
        return results
    finally:
        db.row_factory = None
async def get_file_details_batch(file_ids: list[str]) -> dict:
    """
    По списку file_id возвращает словарь с деталями.
    """
    if not file_ids:
        return {}
    
    from common.db_pool import get_pool, db_lock
    
    placeholders = ','.join('?' for _ in file_ids)
    query = f"SELECT file_id, file_type, sha256 FROM FileRegistry WHERE file_id IN ({placeholders})"
    details_map = {}

    async with db_lock:
        for attempt in range(5):
            try:
                db = await get_pool()
                async with db.execute(query, file_ids) as cursor:
                    async for row in cursor:
                        fid, ftype, sha = row
                        ext = 'dat'
                        if ftype in ['image', 'photo', 'sticker']:
                            ext = 'jpg'
                        elif ftype in ['video', 'gif', 'animation', 'video_note']:
                            ext = 'mp4'
                        elif ftype in ['audio', 'voice']:
                            ext = 'ogg'
                        
                        details_map[fid] = {
                            "type": ftype,
                            "filename": f"{sha[:16]}.{ext}" if sha else f"{fid}.{ext}"
                        }
                return details_map
            except sqlite3.OperationalError as e:
                if "locked" in str(e).lower():
                    await asyncio.sleep(0.2 * (attempt + 1))
                    continue
                break
            except Exception as e:
                logger.error(f"Error in get_file_details_batch: {e}")
                break
    return {}
async def get_blurhashes_batch(file_ids: list[str]) -> dict:
    """
    Возвращает {file_id: blurhash}.
    """
    if not file_ids: return {}
    from common.db_pool import get_pool, db_lock
    
    placeholders = ','.join('?' for _ in file_ids)
    query = f"SELECT file_id, blurhash FROM FileRegistry WHERE file_id IN ({placeholders}) AND blurhash IS NOT NULL"
    res = {}
    
    async with db_lock:
        try:
            db = await get_pool()
            async with db.execute(query, file_ids) as cursor:
                async for row in cursor:
                    if row[1]: res[row[0]] = row[1]
        except: pass
    return res
async def resolve_mod_queue(item_id: int):
    """
    Убирает из очереди (например, админ одобрил или удалил).
    """
    from common.db_pool import get_pool, db_lock
    
    async with db_lock:
        for attempt in range(10):
            try:
                db = await get_pool()
                await db.execute("BEGIN IMMEDIATE")
                
                await db.execute("UPDATE ModQueue SET status = 'resolved' WHERE id = ?", (item_id,))
                
                await db.execute("COMMIT")
                return
            except sqlite3.OperationalError as e:
                try: await db.execute("ROLLBACK")
                except: pass
                
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    await asyncio.sleep(0.1 * (attempt + 1))
                    continue
                break
            except Exception:
                try: await db.execute("ROLLBACK")
                except: pass
                break
async def get_file_mirrors(file_id: str) -> dict:
    from common.db_pool import get_pool, db_lock
    mirrors = {}
    async with db_lock:
        try:
            db = await get_pool()
            async with db.execute("SELECT mirror_type, url FROM FileMirrors WHERE file_id = ?", (file_id,)) as cursor:
                async for row in cursor:
                    mirrors[row[0]] = row[1]
            return mirrors
        except Exception:
            return {}

async def check_file_deduplication(sha256: str):
    from common.db_pool import get_pool, db_lock
    
    async with db_lock:
        try:
            db = await get_pool()
            async with db.execute("SELECT reason FROM BannedHashes WHERE hash_value = ?", (sha256,)) as cursor:
                if await cursor.fetchone():
                    return {"banned": True, "reason": "SHA256 Ban"}
            
            query = """
                SELECT
                    fr.file_id,
                    fr.thumbnail_id,
                    fr.file_type,
                    fr.phash,
                    fr.blurhash,
                    fo.bot_id AS owner_bot_id,
                    tfo.bot_id AS thumbnail_owner_bot_id
                FROM FileRegistry fr
                LEFT JOIN FileOwners fo ON fo.file_id = fr.file_id
                LEFT JOIN FileOwners tfo ON tfo.file_id = fr.thumbnail_id
                WHERE fr.sha256 = ?
                LIMIT 1
            """
            async with db.execute(query, (sha256,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    return {
                        "banned": False,
                        "found": True,
                        "original_file_id": row[0],
                        "thumbnail_file_id": row[1],
                        "type": row[2],
                        "phash": row[3],
                        "blurhash": row[4],
                        "owner_bot_id": row[5],
                        "thumbnail_owner_bot_id": row[6],
                    }
        except Exception as e:
            print(f"⚠️ Deduplication error: {e}")
        return None
async def move_thread_to_board(thread_id: str, new_board_id: str):
    """
    Переносит тред и все его посты в другую доску.
    """
    from common.db_pool import get_pool, db_lock
    
    async with db_lock:
        for attempt in range(10):
            try:
                db = await get_pool()
                await db.execute("BEGIN IMMEDIATE")
                
                # 1. Проверяем, существует ли тред
                async with db.execute("SELECT 1 FROM Threads WHERE thread_num = ?", (int(thread_id),)) as cursor:
                    if not await cursor.fetchone():
                        await db.execute("COMMIT")
                        return False

                # 2. Обновляем таблицу Threads
                await db.execute("UPDATE Threads SET board_id = ? WHERE thread_num = ?", (new_board_id, int(thread_id)))

                # 3. Обновляем таблицу Posts
                await db.execute("UPDATE Posts SET board_id = ? WHERE thread_id = ? OR post_num = ?", 
                                 (new_board_id, thread_id, thread_id))
                
                await db.execute("COMMIT")
                return True
                
            except sqlite3.OperationalError as e:
                try: await db.execute("ROLLBACK")
                except: pass
                
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    await asyncio.sleep(0.1 * (attempt + 1))
                    continue
                print(f"⛔ Error moving thread {thread_id}: {e}")
                break
            except Exception as e:
                try: await db.execute("ROLLBACK")
                except: pass
                print(f"⛔ Error moving thread {thread_id}: {e}")
                break
            
    return False
async def get_and_clear_admin_actions() -> list[dict]:
    """
    Забирает и очищает очередь админ-действий. 
    Использует BEGIN IMMEDIATE для защиты от дедлоков.
    """
    from common.db_pool import get_pool, db_lock
    
    async with db_lock:
        for attempt in range(10):
            try:
                db = await get_pool()
                await db.execute("BEGIN IMMEDIATE")
                
                # 1. Читаем действия
                async with db.execute("SELECT id, action_type, user_id, board_id, expires_at FROM AdminActionQueue") as cursor:
                    rows = await cursor.fetchall()
                
                if not rows:
                    await db.execute("COMMIT")
                    return []
                
                # 2. Очищаем очередь (удаляем всё, что прочитали)
                ids = [r[0] for r in rows]
                placeholders = ','.join('?' for _ in ids)
                await db.execute(f"DELETE FROM AdminActionQueue WHERE id IN ({placeholders})", ids)
                
                await db.execute("COMMIT")
                
                return [{"type": r[1], "user_id": r[2], "board_id": r[3], "expires": r[4]} for r in rows]
                
            except sqlite3.OperationalError as e:
                try: await db.execute("ROLLBACK")
                except: pass
                
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    await asyncio.sleep(0.1 * (attempt + 1))
                    continue
                break
            except Exception:
                try: await db.execute("ROLLBACK")
                except: pass
                break
    return []
async def get_channel_message_id(post_num: int) -> int | None:
    """
    Получает ID сообщения в канале.
    """
    from common.db_pool import get_pool, db_lock
    
    async with db_lock:
        try:
            db = await get_pool()
            async with db.execute("SELECT channel_message_id FROM Posts WHERE post_num = ?", (post_num,)) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else None
        except Exception:
            return None
async def add_to_hf_queue(file_id: str):
    from common.db_pool import get_pool, db_lock
    
    async with db_lock:
        for attempt in range(10):
            try:
                db = await get_pool()
                await db.execute("BEGIN IMMEDIATE")
                
                # ПРАВКА: Если файл уже в очереди, обновляем его время, чтобы он прыгнул в начало (LIFO)
                await db.execute("""
                    INSERT INTO PendingHF (file_id, created_at) 
                    VALUES (?, ?)
                    ON CONFLICT(file_id) DO UPDATE SET created_at = excluded.created_at
                """, (file_id, time.time()))
                
                await db.execute("COMMIT")
                return
            except sqlite3.OperationalError as e:
                try: await db.execute("ROLLBACK")
                except: pass
                
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    await asyncio.sleep(0.1 * (attempt + 1))
                    continue
                break
            except Exception:
                try: await db.execute("ROLLBACK")
                except: pass
                break

async def remove_from_hf_queue(file_ids: list[str]):
    if not file_ids: return
    from common.db_pool import get_pool, db_lock
    placeholders = ','.join('?' for _ in file_ids)
    
    async with db_lock:
        for attempt in range(20):
            try:
                db = await get_pool()
                await db.execute("BEGIN IMMEDIATE")
                
                await db.execute(f"DELETE FROM PendingHF WHERE file_id IN ({placeholders})", file_ids)
                
                await db.execute("COMMIT")
                return
            except sqlite3.OperationalError as e:
                try: await db.execute("ROLLBACK")
                except: pass
                
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    await asyncio.sleep(0.5 * (attempt + 1))
                    continue
                break
            except Exception:
                try: await db.execute("ROLLBACK")
                except: pass
                logging.error(f"❌ HF Queue critical delete error.")
                break
async def add_to_mirror_queue(file_id: str, mirror_type: str):
    """
    Добавляет задачу на создание зеркала в очередь.
    """
    from common.db_pool import get_pool, db_lock
    
    async with db_lock:
        for attempt in range(10):
            try:
                db = await get_pool()
                await db.execute("BEGIN IMMEDIATE")
                
                # ПРАВКА: При повторном добавлении сбрасываем попытки и ставим текущее время
                # Duplicate requests must not reset retry backoff.
                await db.execute("""
                    INSERT INTO MirrorQueue (file_id, mirror_type, next_run_at, attempts)
                    VALUES (?, ?, ?, 0)
                    ON CONFLICT(file_id, mirror_type) DO NOTHING
                """, (file_id, mirror_type, time.time()))
                
                await db.execute("COMMIT")
                return
            except sqlite3.OperationalError as e:
                try: await db.execute("ROLLBACK")
                except: pass
                
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    await asyncio.sleep(0.1 * (attempt + 1))
                    continue
                break
            except Exception:
                try: await db.execute("ROLLBACK")
                except: pass
                break
async def add_post_to_random_cache(post_data: dict):
    global _LAST_MAX_POST_NUM
    
    pid = post_data.get('id') or post_data.get('post_num')
    bid = post_data.get('board_id')
    if not pid or not bid: return
    
    pid_int = int(pid)
    for c in [_VIDEO_CACHE, _IMAGE_CACHE]:
        for b in c:
            c[b] = [item for item in c[b] if item[0] != pid_int]
    content = post_data.get('content', {})
    files = _extract_random_media_files(content)
    is_op = post_data.get('thread_id') == pid or not post_data.get('thread_id')

    if not pid or not bid: return
    if pid > _LAST_MAX_POST_NUM:
        _LAST_MAX_POST_NUM = pid
    for idx, f in enumerate(files):
        ftype = f.get('type')
        if ftype == 'video':
            _VIDEO_CACHE[bid].append((pid, idx))
        elif ftype == 'image':
            _IMAGE_CACHE[bid].append((pid, idx))

    # Если это ОП-пост, добавляем в кэш тредов
    if is_op:
        _THREAD_CACHE[bid].append(str(pid))
async def get_pending_mirror_tasks(limit: int = 10) -> list[dict]:
    """Берет задачи, время которых пришло."""
    db = await get_pool()
    now = time.time()
    try:
        # ПРАВКА: Сортировка по ID DESC, чтобы свежедобавленные задачи шли первыми
        async with db.execute(
            "SELECT * FROM MirrorQueue WHERE next_run_at <= ? ORDER BY id DESC LIMIT ?", 
            (now, limit)
        ) as cursor:
            rows = await cursor.fetchall()
            cols = [d[0] for d in cursor.description]
            results = []
            for r in rows:
                if hasattr(r, 'keys'):
                    results.append(dict(r))
                else:
                    results.append(dict(zip(cols, r)))
            return results
    except Exception as e:
        print(f"Mirror queue error: {e}")
        return []
async def reschedule_mirror_task(task_id: int, attempt: int):
    """
    Откладывает задачу на потом.
    """
    from common.db_pool import get_pool, db_lock
    delay = min(300 * (2 ** attempt), 3600)
    next_time = time.time() + delay
    
    async with db_lock:
        for try_idx in range(10):
            try:
                db = await get_pool()
                await db.execute("BEGIN IMMEDIATE")
                
                await db.execute(
                    "UPDATE MirrorQueue SET attempts = ?, next_run_at = ? WHERE id = ?",
                    (attempt + 1, next_time, task_id)
                )
                
                await db.execute("COMMIT")
                return
            except sqlite3.OperationalError as e:
                try: await db.execute("ROLLBACK")
                except: pass
                
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    await asyncio.sleep(0.1 * (try_idx + 1))
                    continue
                print(f"⚠️ DB Error rescheduling mirror task: {e}")
                break
            except Exception as e:
                try: await db.execute("ROLLBACK")
                except: pass
                print(f"⚠️ DB Error rescheduling mirror task: {e}")
                break
async def get_system_queue_counts() -> dict:
    """Возвращает размеры всех системных очередей для мониторинга."""
    db = await get_pool()
    stats = {}
    try:
        async with db.execute("SELECT COUNT(*) FROM MirrorQueue") as c:
            stats['mirror'] = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM NotificationQueue") as c:
            stats['notif'] = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM ModQueue WHERE status='pending'") as c:
            stats['mod'] = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM BroadcastQueue") as c:
            stats['broadcast'] = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM DeliveryQueue WHERE status='pending'") as c:
            stats['delivery'] = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM ImportRequests WHERE status='pending'") as c:
            stats['import'] = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM ImportQueue") as c:
            stats['import_sim'] = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM FileRegistry WHERE file_type IN ('image', 'photo') AND (tags IS NULL OR tags = '')") as c:
            stats['tagging'] = (await c.fetchone())[0]
            
    except Exception as e:
        print(f"Stats Error: {e}")
        return {'mirror': 0, 'notif': 0, 'mod': 0, 'broadcast': 0, 'delivery': 0, 'import': 0, 'tagging': 0, 'import_sim': 0}
    return stats
async def get_reply_coverage_stats() -> dict:
    """Return admin-grade coverage facts for Telegram reply copy rows."""
    db = await get_pool()
    stats = {
        "total_copies": 0,
        "copy_posts": 0,
        "min_post": None,
        "max_post": None,
        "latest_post": None,
        "copy_span_posts": 0,
        "gap_from_latest": None,
        "by_board": {},
    }
    try:
        async with db.execute(
            "SELECT COUNT(*), COUNT(DISTINCT post_num), MIN(post_num), MAX(post_num) FROM PostCopies"
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                stats["total_copies"] = row[0] or 0
                stats["copy_posts"] = row[1] or 0
                stats["min_post"] = row[2]
                stats["max_post"] = row[3]
        async with db.execute("SELECT MAX(post_num) FROM Posts") as cursor:
            row = await cursor.fetchone()
            stats["latest_post"] = row[0] if row else None
        if stats["min_post"] is not None and stats["max_post"] is not None:
            stats["copy_span_posts"] = max(0, int(stats["max_post"]) - int(stats["min_post"]) + 1)
        if stats["latest_post"] is not None and stats["max_post"] is not None:
            stats["gap_from_latest"] = max(0, int(stats["latest_post"]) - int(stats["max_post"]))
        query = """
            SELECT p.board_id, COUNT(DISTINCT pc.post_num), MIN(pc.post_num), MAX(pc.post_num)
            FROM PostCopies pc
            JOIN Posts p ON p.post_num = pc.post_num
            GROUP BY p.board_id
        """
        async with db.execute(query) as cursor:
            rows = await cursor.fetchall()
        stats["by_board"] = {
            row[0]: {
                "copy_posts": row[1] or 0,
                "min_post": row[2],
                "max_post": row[3],
            }
            for row in rows
        }
    except Exception as e:
        print(f"Reply coverage stats error: {e}")
    return stats
async def toggle_thread_endless(thread_id: str, endless: bool):
    """
    Переключает режим бесконечного треда.
    """
    from common.db_pool import get_pool, db_lock
    
    async with db_lock:
        for attempt in range(10):
            try:
                db = await get_pool()
                await db.execute("BEGIN IMMEDIATE")
                
                await db.execute(
                    "UPDATE Threads SET is_endless = ? WHERE thread_num = ?",
                    (1 if endless else 0, int(thread_id))
                )
                if endless:
                    await db.execute("UPDATE Threads SET is_archived = 0 WHERE thread_num = ?", (int(thread_id),))
                
                await db.execute("COMMIT")
                return True
            except sqlite3.OperationalError as e:
                try: await db.execute("ROLLBACK")
                except: pass
                
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    await asyncio.sleep(0.1 * (attempt + 1))
                    continue
                break
            except Exception as e:
                try: await db.execute("ROLLBACK")
                except: pass
                print(f"Error toggling endless for {thread_id}: {e}")
                break
    return False
async def trim_thread_posts(thread_id: str, max_posts: int = 1000):
    """
    Атомарно удаляет старые посты, оставляя только N последних.
    """
    from common.db_pool import get_pool, db_lock
    
    async with db_lock:
        for attempt in range(10):
            try:
                db = await get_pool()
                await db.execute("BEGIN IMMEDIATE")
                
                op_id_int = int(thread_id) 
                
                query = """
                    DELETE FROM Posts
                    WHERE thread_id = ?
                      AND post_num != ?
                      AND post_num NOT IN (
                          SELECT post_num FROM Posts
                          WHERE thread_id = ?
                          ORDER BY timestamp DESC
                          LIMIT ?
                      )
                """
                
                cursor = await db.execute(query, (thread_id, op_id_int, thread_id, max_posts))
                count = cursor.rowcount
                
                await db.execute("COMMIT")
                
                if count > 0:
                    print(f"✂️ Trimmed thread {thread_id}: deleted {count} old posts (Atomic).")
                return

            except sqlite3.OperationalError as e:
                try: await db.execute("ROLLBACK")
                except: pass
                
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    await asyncio.sleep(0.1 * (attempt + 1))
                    continue
                print(f"Error trimming thread {thread_id}: {e}")
                break
            except Exception as e:
                try: await db.execute("ROLLBACK")
                except: pass
                print(f"Error trimming thread {thread_id}: {e}")
                break
async def remove_mirror_task(task_id: int):
    """
    Удаляет выполненную задачу.
    """
    from common.db_pool import get_pool, db_lock
    
    async with db_lock:
        for attempt in range(15):
            try:
                db = await get_pool()
                await db.execute("BEGIN IMMEDIATE")
                
                await db.execute("DELETE FROM MirrorQueue WHERE id = ?", (task_id,))
                
                await db.execute("COMMIT")
                return
            except sqlite3.OperationalError as e:
                try: await db.execute("ROLLBACK")
                except: pass
                
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    await asyncio.sleep(0.2 * (attempt + 1))
                    continue
                break
            except Exception:
                try: await db.execute("ROLLBACK")
                except: pass
                break
async def get_hf_queue_batch(limit: int = 50) -> list[str]:
    """
    Берет пачку самых старых файлов из очереди.
    Защищено db_lock для безопасного чтения.
    """
    from common.db_pool import get_pool, db_lock
    
    async with db_lock:
        for attempt in range(5):
            try:
                db = await get_pool()
                # ПРАВКА: Сортировка DESC (новые первыми)
                async with db.execute("SELECT file_id FROM PendingHF ORDER BY created_at DESC LIMIT ?", (limit,)) as cursor:
                    rows = await cursor.fetchall()
                    return [row[0] for row in rows]
            except Exception as e:
                # Чтение редко падает, но на случай разрыва соединения
                print(f"HF Queue read error: {e}")
                await asyncio.sleep(1)
    return []

async def get_queue_stats() -> tuple[int, float]:
    """
    Возвращает (кол-во файлов, время самого старого).
    """
    from common.db_pool import get_pool, db_lock
    
    async with db_lock:
        try:
            db = await get_pool()
            async with db.execute("SELECT COUNT(*), MIN(created_at) FROM PendingHF") as cursor:
                row = await cursor.fetchone()
                count = row[0] or 0
                oldest = row[1] or 0
                return count, oldest
        except:
            return 0, 0
    
async def add_reply_to_notification_queue(source_post_num: int, reply_post_num: int, board_id: str, thread_id: int, reply_author_id: int):
    """
    Проверяет, кому нужно отправить уведомление, и ставит его в очередь.
    """
    from common.db_pool import get_pool, db_lock
    
    async with db_lock:
        for attempt in range(10):
            try:
                db = await get_pool()
                await db.execute("BEGIN IMMEDIATE")
                
                # Проверяем автора оригинала (чтение внутри цикла транзакции)
                async with db.execute("SELECT author_id FROM Posts WHERE post_num = ?", (source_post_num,)) as cursor:
                    row = await cursor.fetchone()
                    if not row:
                        await db.execute("COMMIT")
                        return
                    original_author_id = row[0]
                
                if original_author_id > 0 and original_author_id != reply_author_id:
                    curr_time = time.time()

                    # FIX: Если thread_id is None, используем ID родительского поста
                    effective_thread_id = str(thread_id) if thread_id else str(source_post_num)

                    await db.execute(
                        """INSERT INTO NotificationQueue 
                           (recipient_id, source_post_num, reply_post_num, board_id, thread_id, created_at) 
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        (original_author_id, source_post_num, reply_post_num, board_id, effective_thread_id, curr_time)
                    )
                    
                    await db.execute(
                        """INSERT INTO UserReplies 
                           (user_id, board_id, thread_id, post_num, parent_num, is_read, created_at) 
                           VALUES (?, ?, ?, ?, ?, 0, ?)""",
                        (original_author_id, board_id, effective_thread_id, source_post_num, reply_post_num, curr_time)
                    )
                
                await db.execute("COMMIT")
                return

            except sqlite3.OperationalError as e:
                try: await db.execute("ROLLBACK")
                except: pass
                
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    await asyncio.sleep(0.1 * (attempt + 1))
                    continue
                print(f"⚠️ Ошибка добавления уведомления: {e}")
                break
            except Exception as e:
                try: await db.execute("ROLLBACK")
                except: pass
                print(f"⚠️ Ошибка добавления уведомления: {e}")
                break

async def get_and_clear_notification_queue() -> list[dict]:
    """
    Забирает все уведомления и очищает таблицу.
    """
    from common.db_pool import get_pool, db_lock
    
    async with db_lock:
        for attempt in range(10):
            try:
                db = await get_pool()
                await db.execute("BEGIN IMMEDIATE")
                
                # 1. Забираем ID и данные уведомлений
                async with db.execute("SELECT id, recipient_id, source_post_num, reply_post_num, board_id, thread_id FROM NotificationQueue") as cursor:
                    rows = await cursor.fetchall()
                
                if not rows:
                    await db.execute("COMMIT")
                    return []
                
                # 2. Удаляем обработанные записи
                ids_to_delete = [row[0] for row in rows]
                placeholders = ','.join('?' for _ in ids_to_delete)
                await db.execute(f"DELETE FROM NotificationQueue WHERE id IN ({placeholders})", ids_to_delete)
                
                await db.execute("COMMIT")
                
                # 3. Возвращаем результат
                return [
                    {
                        "recipient_id": r[1],
                        "source_post_num": r[2],
                        "reply_post_num": r[3],
                        "board_id": r[4],
                        "thread_id": r[5]
                    } for r in rows
                ]
                
            except sqlite3.OperationalError as e:
                try: await db.execute("ROLLBACK")
                except: pass
                
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    await asyncio.sleep(0.1 * (attempt + 1))
                    continue
                print(f"⛔ Ошибка в get_and_clear_notification_queue: {e}")
                break
            except Exception as e:
                try: await db.execute("ROLLBACK")
                except: pass
                print(f"⛔ Ошибка в get_and_clear_notification_queue: {e}")
                break
            
    return []
async def save_poll_vote_db(post_num: int, user_id: int, option_index: int) -> bool:
    """
    Атомарная запись голоса.
    """
    from common.db_pool import get_pool, db_lock
    
    async with db_lock:
        for attempt in range(10):
            try:
                db = await get_pool()
                await db.execute("BEGIN IMMEDIATE")
                
                await db.execute(
                    "INSERT INTO PollVotes (post_num, user_id, option_index) VALUES (?, ?, ?)",
                    (post_num, user_id, option_index)
                )
                
                await db.execute("COMMIT")
                return True
                
            except sqlite3.IntegrityError:
                try: await db.execute("ROLLBACK")
                except: pass
                # Пользователь уже голосовал — это нормальное поведение, не ошибка.
                return False
                
            except sqlite3.OperationalError as e:
                try: await db.execute("ROLLBACK")
                except: pass
                
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    await asyncio.sleep(0.1 * (attempt + 1))
                    continue
                print(f"Poll Vote DB Error: {e}")
                break
                
            except Exception as e:
                try: await db.execute("ROLLBACK")
                except: pass
                print(f"Poll Vote Error: {e}")
                break
            
    return False

async def get_poll_results(post_num: int) -> dict:
    """Собирает результаты голосования."""
    db = await get_pool()
    results = {} # {option_index: count}
    try:
        query = "SELECT option_index, COUNT(*) FROM PollVotes WHERE post_num = ? GROUP BY option_index"
        async with db.execute(query, (post_num,)) as cursor:
            async for row in cursor:
                results[str(row[0])] = row[1]
    except: pass
    return results
async def get_file_tags(file_id: str) -> list[str]:
    """Возвращает список тегов для файла."""
    from common.db_pool import get_pool, db_lock
    
    async with db_lock:
        try:
            db = await get_pool()
            async with db.execute("SELECT tags FROM FileRegistry WHERE file_id = ?", (file_id,)) as cursor:
                row = await cursor.fetchone()
                if row and row[0]:
                    return [t.strip() for t in row[0].split(',') if t.strip()]
        except Exception:
            pass
    return []

async def search_files_by_tags(tags: list[str], limit: int = 50, offset: int = 0) -> list[dict]:
    if not tags: return []
    
    from common.db_pool import get_pool, db_lock
    
    search_terms = []
    for t in tags:
        cleaned = "".join(ch for ch in t if ch.isalnum() or ch in " ")
        cleaned = cleaned.strip().replace('"', '""')
        if not cleaned: continue
        
        search_terms.append(f'"{cleaned}"*')
        
        words = cleaned.split()
        if len(words) > 1:
            for w in words:
                if len(w) > 2:
                    search_terms.append(f'{w}*')
            
    if not search_terms: return []
    
    unique_terms = list(set(search_terms))
    fts_query = " OR ".join(unique_terms)
    
    query = f"""
        SELECT file_id, bm25(FileTagsFTS) as score, tags
        FROM FileTagsFTS
        WHERE FileTagsFTS MATCH ?
        ORDER BY score ASC
        LIMIT ? OFFSET ?
    """
    
    results = []
    async with db_lock:
        try:
            db = await get_pool()
            async with db.execute(query, (fts_query, limit, offset)) as cursor:
                async for row in cursor:
                    results.append({
                        "file_id": row[0],
                        "score": row[1],
                        "tags": row[2]
                    })
        except Exception as e:
            print(f"Tag search error: {e}")
        
    return results
async def get_mirrors_batch(file_ids: list[str]) -> dict:
    if not file_ids: return {}
    db = await get_pool()
    placeholders = ','.join('?' for _ in file_ids)
    query = f"SELECT file_id, mirror_type, url FROM FileMirrors WHERE file_id IN ({placeholders})"
    res = defaultdict(dict)
    try:
        async with db.execute(query, file_ids) as cursor:
            async for row in cursor:
                res[row[0]][row[1]] = row[2]
    except: pass
    return res
async def get_posts_by_file_ids(file_ids: list[str]) -> list[dict]:
    """
    Находит посты, содержащие указанные файлы.
    """
    if not file_ids: 
        return []
        
    from common.db_pool import get_pool, db_lock
    
    clauses = []
    params = []
    for fid in file_ids:
        clauses.append("instr(content, ?) > 0")
        params.append(fid)
        
    where_clause = " OR ".join(clauses)
    query = f"SELECT * FROM Posts WHERE ({where_clause}) AND IFNULL(is_shadow, 0) = 0"

    async with db_lock:
        try:
            db = await get_pool()
            db.row_factory = aiosqlite.Row
            async with db.execute(query, params) as cursor:
                rows = await cursor.fetchall()
                cols = [d[0] for d in cursor.description]
                results = []
                for r in rows:
                    if hasattr(r, 'keys'):
                        results.append(dict(r))
                    else:
                        results.append(dict(zip(cols, r)))
                return results
        except Exception as e:
            print(f"Error in get_posts_by_file_ids: {e}")
            return []
        finally:
            if 'db' in locals() and db:
                db.row_factory = None
async def get_thread_type_and_unlock_status(thread_id: str, user_id: int) -> tuple[str, bool]:
    """
    Возвращает (тип_треда, имеет_ли_юзер_анлок).
    Использует цикл попыток при блокировке базы.
    """
    from common.db_pool import get_pool, db_lock
    
    async with db_lock:
        for attempt in range(10):
            try:
                db = await get_pool()
                async with db.execute("SELECT thread_type FROM Threads WHERE thread_num = ? LIMIT 1", (int(thread_id),)) as cursor:
                    row = await cursor.fetchone()
                    if not row:
                        return 'default', False
                    t_type = row[0] or 'default'
                    
                if t_type == 'default':
                    return 'default', True
                    
                async with db.execute("SELECT 1 FROM ThreadUnlocks WHERE thread_id = ? AND user_id = ? LIMIT 1", (thread_id, user_id)) as cursor:
                    is_unlocked = await cursor.fetchone() is not None
                    
                return t_type, is_unlocked
            except sqlite3.OperationalError as e:
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    await asyncio.sleep(0.1 * (attempt + 1))
                    continue
                break
            except Exception:
                break
    return 'default', False

async def get_unread_replies_count(user_id: int) -> int:
    """Возвращает количество непрочитанных ответов."""
    db = await get_pool()
    try:
        async with db.execute("SELECT COUNT(*) FROM UserReplies WHERE user_id = ? AND is_read = 0", (user_id,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0
    except: return 0

async def get_user_replies(user_id: int, limit: int = 20, offset: int = 0) -> list[dict]:
    """Возвращает список ответов с подгрузкой контента поста. Скрывает shadow-ответы."""
    db = await get_pool()
    try:
        query = """
            SELECT r.id, r.board_id, r.thread_id, r.post_num, r.parent_num, r.is_read, r.created_at,
                   p.content
            FROM UserReplies r
            LEFT JOIN Posts p ON r.post_num = p.post_num
            WHERE r.user_id = ? 
              AND IFNULL(p.is_shadow, 0) = 0
            ORDER BY r.created_at DESC
            LIMIT ? OFFSET ?
        """
        async with db.execute(query, (user_id, limit, offset)) as cursor:
            rows = await cursor.fetchall()
            
        results = []
        for r in rows:
            preview_text = ""
            has_file = False
            
            if r[7] is None:
                preview_text = "[Пост удален]"
            else:
                try:
                    content = json.loads(r[7])
                    preview_text = content.get("text", "")[:100] if content.get("text") else "[Медиа]"
                    has_file = bool(content.get("files"))
                except: 
                    preview_text = "[Ошибка данных]"
            
            results.append({
                "id": r[0],
                "board_id": r[1],
                "thread_id": r[2],
                "post_num": r[3],
                "parent_num": r[4],
                "is_read": bool(r[5]),
                "created_at": r[6],
                "preview": preview_text,
                "has_file": has_file
            })
        return results
    except Exception as e:
        print(f"Error fetching replies: {e}")
        return []

async def mark_replies_read(user_id: int, reply_ids: list[int] = None):
    """Помечает ответы как прочитанные. Если ids не передан - все."""
    from common.db_pool import get_pool, db_lock
    async with db_lock:
        try:
            db = await get_pool()
            await db.execute("BEGIN IMMEDIATE")
            if reply_ids:
                placeholders = ','.join('?' for _ in reply_ids)
                await db.execute(f"UPDATE UserReplies SET is_read = 1 WHERE user_id = ? AND id IN ({placeholders})", [user_id] + reply_ids)
            else:
                await db.execute("UPDATE UserReplies SET is_read = 1 WHERE user_id = ?", (user_id,))
            await db.execute("COMMIT")
        except Exception:
            try: await db.execute("ROLLBACK")
            except: pass
async def get_posts_batch(post_nums: List[int]) -> List[dict]:
    """
    Возвращает полные данные постов по списку ID.
    """
    if not post_nums: return []
    
    from common.db_pool import get_pool, db_lock
    
    target_nums = sorted(list(set(post_nums)), reverse=True)[:142]
    placeholders = ','.join('?' for _ in target_nums)
    query = f"""
        SELECT * FROM Posts 
        WHERE post_num IN ({placeholders})
        ORDER BY timestamp DESC
    """
    
    async with db_lock:
        try:
            db = await get_pool()
            db.row_factory = aiosqlite.Row
            async with db.execute(query, target_nums) as cursor:
                rows = await cursor.fetchall()
                cols = [d[0] for d in cursor.description]
            posts = []
            for row in rows:
                try:
                    if hasattr(row, 'keys'):
                        p = dict(row)
                    else:
                        p = dict(zip(cols, row))
                    p['id'] = p['post_num']
                    if isinstance(p['content'], str):
                        p['content'] = json.loads(p['content'])
                    elif not isinstance(p['content'], dict):
                        p['content'] = {'text': '', 'files': []}
                    posts.append(p)
                except Exception:
                    continue            
            return posts
        except Exception as e:
            logger.error(f"Error in get_posts_batch: {e}")
            return []
        finally:
            if 'db' in locals() and db:
                db.row_factory = None

async def toggle_post_censorship(post_num: int) -> bool:
    """
    Переключает флаг цензуры (блюра) для поста.
    """
    from common.db_pool import get_pool, db_lock
    
    async with db_lock:
        for attempt in range(10):
            try:
                db = await get_pool()
                await db.execute("BEGIN IMMEDIATE")
                
                async with db.execute("SELECT content FROM Posts WHERE post_num = ?", (post_num,)) as cursor:
                    row = await cursor.fetchone()
                
                if not row:
                    await db.execute("COMMIT")
                    return False
                
                try:
                    content = json.loads(row[0])
                except:
                    content = {"text": "", "type": "text"}
                
                # Переключение флага
                current_state = content.get('is_censored', False)
                new_state = not current_state
                content['is_censored'] = new_state
                
                new_json = json.dumps(content, default=_json_serializer)
                
                await db.execute("UPDATE Posts SET content = ? WHERE post_num = ?", (new_json, post_num))
                await db.execute("COMMIT")
                return new_state
                
            except sqlite3.OperationalError as e:
                try: await db.execute("ROLLBACK")
                except: pass
                
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    await asyncio.sleep(0.1 * (attempt + 1))
                    continue
                break
            except Exception as e:
                try: await db.execute("ROLLBACK")
                except: pass
                print(f"Error toggling censorship: {e}")
                break
    return False

def get_db_connection():
    """
    Возвращает контекстный менеджер подключения для изолированных задач.
    Включает WAL и isolation_level=None для ручного управления транзакциями.
    """
    class SafeConnection:
        def __init__(self):
            self.conn = None
        async def __aenter__(self):
            self.conn = await aiosqlite.connect(DB_NAME, timeout=60.0, isolation_level=None)
            await self.conn.execute("PRAGMA busy_timeout = 60000;")
            await self.conn.execute("PRAGMA journal_mode=WAL;")
            await self.conn.execute("PRAGMA synchronous = NORMAL;")
            await self.conn.execute("PRAGMA temp_store = MEMORY;")
            await self.conn.execute("PRAGMA mmap_size = 268435456;")
            await self.conn.execute("PRAGMA cache_size = -60000;")
            await self.conn.execute("PRAGMA foreign_keys = ON;")
            return self.conn
            
        async def __aexit__(self, exc_type, exc, tb):
            if self.conn:
                await self.conn.close()
            
    return SafeConnection()
