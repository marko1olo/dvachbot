import asyncio
import os
import pytest
import aiosqlite
import json
from common.db_pool import db_transaction, safe_begin_immediate, safe_commit, safe_rollback, LazyLock
from common.database import deduct_user_global_balance, add_user_global_balance

async def _init_test_db(db_path: str):
    db = await aiosqlite.connect(db_path, isolation_level=None)
    await db.execute("""
        CREATE TABLE Users (
            user_id INTEGER,
            board_id TEXT,
            balance REAL DEFAULT 0,
            active_items TEXT DEFAULT '{}',
            status TEXT DEFAULT 'active',
            is_verified_b INTEGER DEFAULT 0,
            posts_count INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, board_id)
        )
    """)
    await db.execute("""
        CREATE TABLE Posts (
            post_num INTEGER PRIMARY KEY,
            author_id INTEGER,
            board_id TEXT,
            content TEXT,
            timestamp REAL
        )
    """)
    await db.execute("""
        CREATE TABLE PostCopies (
            post_num INTEGER,
            recipient_id INTEGER,
            message_id INTEGER,
            PRIMARY KEY (post_num, recipient_id)
        )
    """)
    await db.execute("""
        CREATE TABLE DeliveryQueue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            board_id TEXT,
            post_num INTEGER,
            recipients TEXT,
            content TEXT,
            delivery_phase TEXT,
            original_recipients INTEGER,
            thread_id TEXT,
            enqueued_at REAL,
            updated_at REAL,
            attempts INTEGER,
            status TEXT
        )
    """)
    return db


@pytest.mark.asyncio
async def test_db_transaction_basic_commit(tmp_path):
    db_path = str(tmp_path / "test1.db")
    db = await _init_test_db(db_path)
    try:
        async with db_transaction(db):
            await db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (1, 'b', 100.0)")
        
        async with db.execute("SELECT balance FROM Users WHERE user_id = 1") as cursor:
            row = await cursor.fetchone()
            assert row is not None
            assert row[0] == 100.0
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_db_transaction_rollback_on_error(tmp_path):
    db_path = str(tmp_path / "test2.db")
    db = await _init_test_db(db_path)
    try:
        try:
            async with db_transaction(db):
                await db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (2, 'b', 50.0)")
                raise RuntimeError("Simulated crash")
        except RuntimeError:
            pass
            
        async with db.execute("SELECT balance FROM Users WHERE user_id = 2") as cursor:
            row = await cursor.fetchone()
            assert row is None
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_db_transaction_nested_savepoints(tmp_path):
    db_path = str(tmp_path / "test3.db")
    db = await _init_test_db(db_path)
    try:
        async with db_transaction(db):
            await db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (3, 'b', 100.0)")
            
            # Nested transaction level 1
            async with db_transaction(db):
                await db.execute("UPDATE Users SET balance = 200.0 WHERE user_id = 3")
                
                # Nested transaction level 2 (which fails and rolls back only its level)
                try:
                    async with db_transaction(db):
                        await db.execute("UPDATE Users SET balance = 999.0 WHERE user_id = 3")
                        raise ValueError("Nested failure")
                except ValueError:
                    pass
                    
        async with db.execute("SELECT balance FROM Users WHERE user_id = 3") as cursor:
            row = await cursor.fetchone()
            assert row is not None
            assert row[0] == 200.0
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_balance_deduct_and_add_atomicity(tmp_path):
    db_path = str(tmp_path / "test4.db")
    db = await _init_test_db(db_path)
    try:
        # Setup initial balance
        await add_user_global_balance(db, 10, 'b', 500.0)
        
        ok, new_bal = await deduct_user_global_balance(db, 10, 'b', 200.0)
        assert ok is True
        assert new_bal == 300.0
        
        # Overdraw test
        ok, new_bal = await deduct_user_global_balance(db, 10, 'b', 1000.0)
        assert ok is False
        assert new_bal == 300.0
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_concurrent_transactions_stress(tmp_path):
    db_path = str(tmp_path / "test5.db")
    db = await _init_test_db(db_path)
    try:
        # Initialize 10 users with 100 balance
        for i in range(1, 11):
            await add_user_global_balance(db, i, 'b', 100.0)
            
        async def worker_transfer(from_u, to_u, amount):
            async with db_transaction(db):
                ok, _ = await deduct_user_global_balance(db, from_u, 'b', amount)
                if ok:
                    await add_user_global_balance(db, to_u, 'b', amount)
                    
        tasks = []
        for _ in range(30):
            tasks.append(worker_transfer(1, 2, 2.0))
            tasks.append(worker_transfer(2, 3, 1.0))
            tasks.append(worker_transfer(3, 1, 1.0))
            
        await asyncio.gather(*tasks)
        
        # Total money in system must remain constant (1000.0)
        async with db.execute("SELECT SUM(balance) FROM Users") as cursor:
            row = await cursor.fetchone()
            assert abs(row[0] - 1000.0) < 1e-4
    finally:
        await db.close()
