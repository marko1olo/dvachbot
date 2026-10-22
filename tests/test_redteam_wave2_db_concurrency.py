import asyncio
import math
import random
import pytest
import aiosqlite
from common.db_pool import db_transaction, LazyLock, safe_begin_immediate, safe_commit, safe_rollback
from common.database import (
    add_user_global_balance,
    deduct_user_global_balance,
    transfer_user_balance,
    get_user_global_balance,
    get_abu_fund_total,
    record_user_transaction,
    get_user_recent_transactions,
    record_user_daily_limit,
    get_user_daily_limit,
    cleanup_old_user_daily_limits,
    record_user_immunity,
    add_music_roast,
    apply_regular_mute,
    remove_regular_mute,
    lift_ban,
    lift_shadow_ban,
    update_shadow_mute,
    remove_users_from_board_batch,
    mark_replies_read,
    get_file_details_batch,
    get_blurhashes_batch,
    get_poll_results_batch,
    get_mirrors_batch,
    get_failed_files_batch,
    get_posts_by_file_ids,
    get_user_posts_from_list,
    get_thread_ids_for_posts,
    toggle_post_censorship,
)


@pytest.mark.asyncio
async def test_balance_mutators_validation(isolated_test_db):
    """
    Проверяет строгую валидацию входных параметров balance mutators:
    отрицательные числа, NaN, Inf, некорректные user_id, нулевые операции.
    """
    db = isolated_test_db

    # 1. Начальный баланс должен быть 0.0
    bal = await get_user_global_balance(db, 1001)
    assert bal == 0.0

    # 2. Некорректные user_id
    assert await add_user_global_balance(db, 0, "b", 500) == 0.0
    assert await add_user_global_balance(db, -10, "b", 500) == 0.0
    ok, new_bal = await deduct_user_global_balance(db, 0, "b", 500)
    assert not ok and new_bal == 0.0
    ok, new_bal = await deduct_user_global_balance(db, -5, "b", 500)
    assert not ok and new_bal == 0.0

    # 3. add_user_global_balance: отрицательные, ноль, NaN, Inf
    assert await add_user_global_balance(db, 1001, "b", -100) == 0.0
    assert await add_user_global_balance(db, 1001, "b", 0) == 0.0
    assert await add_user_global_balance(db, 1001, "b", float("nan")) == 0.0
    assert await add_user_global_balance(db, 1001, "b", float("inf")) == 0.0
    assert await add_user_global_balance(db, 1001, "b", float("-inf")) == 0.0
    assert await get_user_global_balance(db, 1001) == 0.0

    # 4. Успешное начисление
    bal = await add_user_global_balance(db, 1001, "b", 250.50)
    assert bal == 250.50
    assert await get_user_global_balance(db, 1001) == 250.50

    # 5. deduct_user_global_balance: отрицательные, ноль, NaN, Inf
    ok, b = await deduct_user_global_balance(db, 1001, "b", -50)
    assert not ok and b == 250.50
    ok, b = await deduct_user_global_balance(db, 1001, "b", float("nan"))
    assert not ok and b == 250.50
    ok, b = await deduct_user_global_balance(db, 1001, "b", float("inf"))
    assert not ok and b == 250.50

    # Списание 0 — валидный no-op
    ok, b = await deduct_user_global_balance(db, 1001, "b", 0)
    assert ok and b == 250.50

    # Списание больше баланса
    ok, b = await deduct_user_global_balance(db, 1001, "b", 1000)
    assert not ok and b == 250.50


@pytest.mark.asyncio
async def test_deduct_multiboard_atomicity_and_rollback(isolated_test_db):
    """
    Проверяет списание баланса с нескольких досок и атомарный откат
    при невозможности списать требуемую сумму целиком.
    """
    db = isolated_test_db
    user_id = 2001

    await db.execute("INSERT OR IGNORE INTO Boards (board_id, name, description) VALUES ('news', 'News', 'News board')")

    # Задаем баланс на доске 'b' = 40, на 'news' = 60 (итого 100)
    await add_user_global_balance(db, user_id, "b", 40.0)
    await add_user_global_balance(db, user_id, "news", 60.0)
    assert await get_user_global_balance(db, user_id) == 100.0

    # Списываем 70 с доски 'b'. Должно списать 40 с 'b' и 30 с 'news'.
    ok, new_bal = await deduct_user_global_balance(db, user_id, "b", 70.0)
    assert ok is True
    assert round(new_bal, 2) == 30.0

    # Проверяем балансы по доскам
    async with db.execute("SELECT board_id, balance FROM Users WHERE user_id = ?", (user_id,)) as c:
        rows = dict(await c.fetchall())
    assert rows.get("b", 0.0) == 0.0
    assert round(rows.get("news", 0.0), 2) == 30.0

    # Попытка списать 50 (при остатке 30)
    ok, cur_bal = await deduct_user_global_balance(db, user_id, "b", 50.0)
    assert ok is False
    assert round(cur_bal, 2) == 30.0

    # Балансы не должны были измениться (никакого частичного списания!)
    async with db.execute("SELECT board_id, balance FROM Users WHERE user_id = ?", (user_id,)) as c:
        rows_after = dict(await c.fetchall())
    assert rows_after.get("b", 0.0) == 0.0
    assert round(rows_after.get("news", 0.0), 2) == 30.0


@pytest.mark.asyncio
async def test_transfer_user_balance_validation_and_atomicity(isolated_test_db):
    """
    Проверяет transfer_user_balance:
    - запрет переводов самому себе
    - проверка валидности сумм и комиссий
    - запрет перевода при нехватке средств (учитывая fee)
    - корректное атомарное начисление получателю, списание у отправителя, пополнение Фонда Абу
    - записи в UserTransactions
    """
    db = isolated_test_db
    sender_id = 3001
    receiver_id = 3002

    await add_user_global_balance(db, sender_id, "b", 500.0)
    await add_user_global_balance(db, receiver_id, "b", 50.0)

    abu_start = await get_abu_fund_total(db)

    # 1. Самоперевод запрещен
    ok, reason, s_bal, r_bal = await transfer_user_balance(db, sender_id, sender_id, 100.0)
    assert ok is False
    assert reason == "self_transfer_forbidden"
    assert s_bal == 500.0

    # 2. Невалидные суммы
    for bad_amt in [-10, 0, float("nan"), float("inf")]:
        ok, reason, _, _ = await transfer_user_balance(db, sender_id, receiver_id, bad_amt)
        assert ok is False
        assert reason == "invalid_amount"

    # 3. Невалидные комиссии
    for bad_fee in [-5, float("nan"), float("inf")]:
        ok, reason, _, _ = await transfer_user_balance(db, sender_id, receiver_id, 100.0, fee=bad_fee)
        assert ok is False
        assert reason == "invalid_fee"

    # 4. Нехватка средств с учетом комиссии (баланс 500, попытка перевести 490 с комиссией 25 -> 515 > 500)
    ok, reason, s_bal, r_bal = await transfer_user_balance(db, sender_id, receiver_id, 490.0, fee=25.0)
    assert ok is False
    assert reason == "insufficient_funds"
    assert s_bal == 500.0
    assert r_bal == 50.0

    # 5. Успешный перевод с комиссией: 200 + fee 10
    ok, reason, new_s_bal, new_r_bal = await transfer_user_balance(
        db,
        sender_id=sender_id,
        receiver_id=receiver_id,
        amount=200.0,
        board_id="b",
        fee=10.0,
        category="pay",
        description="Тестовый перевод шекелей"
    )
    assert ok is True
    assert reason == "success"
    assert round(new_s_bal, 2) == 290.0  # 500 - 210
    assert round(new_r_bal, 2) == 250.0  # 50 + 200

    # Проверяем пополнение фонда Абу
    abu_end = await get_abu_fund_total(db)
    assert round(abu_end - abu_start, 2) == 10.0

    # Проверяем леджер транзакций
    s_txs = await get_user_recent_transactions(db, sender_id, limit=5)
    r_txs = await get_user_recent_transactions(db, receiver_id, limit=5)
    assert len(s_txs) >= 1
    assert len(r_txs) >= 1
    assert s_txs[0]["amount"] == -210.0
    assert r_txs[0]["amount"] == 200.0


@pytest.mark.asyncio
async def test_concurrent_transfers_wealth_conservation(isolated_test_db):
    """
    Стресс-тест конкурентных параллельных переводов:
    10 пользователей с 1000 шекелей каждый (всего 10,000 шекелей).
    Множество одновременных транзакций переводов с комиссией.
    Закон сохранения капитала: sum(balances) + abu_fund == 10,000 на всех этапах.
    Отсутствие дедлоков и гонок!
    """
    db = isolated_test_db
    num_users = 8
    initial_balance = 1000.0
    users = [4000 + i for i in range(num_users)]

    for uid in users:
        await add_user_global_balance(db, uid, "b", initial_balance)

    total_wealth_initial = num_users * initial_balance
    abu_initial = await get_abu_fund_total(db)

    async def random_transfer():
        for _ in range(5):
            u1, u2 = random.sample(users, 2)
            amt = random.uniform(10.0, 50.0)
            fee = round(amt * 0.05, 2)
            await transfer_user_balance(db, u1, u2, amt, fee=fee)
            await asyncio.sleep(0.001)

    tasks = [asyncio.create_task(random_transfer()) for _ in range(12)]
    await asyncio.gather(*tasks)

    # Проверяем балансы всех пользователей
    total_balances = sum([await get_user_global_balance(db, uid) for uid in users])
    abu_final = await get_abu_fund_total(db)
    abu_collected = abu_final - abu_initial

    total_current = round(total_balances + abu_collected, 2)
    assert total_current == total_wealth_initial, f"Leak detected! Expected {total_wealth_initial}, got {total_current}"


@pytest.mark.asyncio
async def test_elimination_of_raw_commits_in_nested_transactions(isolated_test_db):
    """
    Проверяет, что функции (record_user_daily_limit, cleanup_old_user_daily_limits,
    record_user_immunity, add_music_roast) больше не вызывают сырой db.commit().
    При вызове внутри объемлющей транзакции, закончившейся ошибкой,
    их результаты ДОЛЖНЫ быть полностью откатаны!
    """
    db = isolated_test_db
    user_id = 5001

    try:
        async with db_transaction(db):
            await record_user_daily_limit(db, user_id, "safe", day_date="2026-10-22", increment=3)
            await record_user_immunity(db, user_id, "partyvan", 9999999999.0)
            await add_music_roast(db, user_id, "b", 123, "Artist", "Title", 10, "Great", "Roast")

            # Имитируем сбой внешней транзакции
            raise RuntimeError("Forced transaction failure")
    except RuntimeError:
        pass

    # Все изменения должны быть откатаны!
    limit_val = await get_user_daily_limit(db, user_id, "safe", day_date="2026-10-22")
    assert limit_val == 0, f"Expected 0 daily limit after rollback, got {limit_val}"

    async with db.execute("SELECT expires_at FROM UserImmunity WHERE user_id = ? AND immunity_type = 'partyvan'", (user_id,)) as c:
        row = await c.fetchone()
        assert row is None, "UserImmunity was prematurely committed and survived rollback!"

    async with db.execute("SELECT score FROM MusicRoasts WHERE user_id = ?", (user_id,)) as c:
        row = await c.fetchone()
        assert row is None, "MusicRoasts was prematurely committed and survived rollback!"


@pytest.mark.asyncio
async def test_moderation_atomic_transactions_and_nesting(isolated_test_db):
    """
    Проверяет, что функции модерации (lift_ban, lift_shadow_ban, apply_regular_mute,
    remove_regular_mute, update_shadow_mute) поддерживают вложенные транзакции (savepoints)
    и не выбрасывают 'cannot start a transaction within a transaction'.
    """
    db = isolated_test_db
    user_id = 6001
    board_id = "b"

    # Создаем пользователя со статусом banned
    await db.execute("INSERT OR REPLACE INTO Users (user_id, board_id, status) VALUES (?, ?, 'banned')", (user_id, board_id))

    # Вызываем внутри объемлющей транзакции
    async with db_transaction(db):
        await lift_ban(user_id, board_id)
        await apply_regular_mute(user_id, board_id, duration_seconds=3600, reason="test")

    # Проверяем фиксацию
    async with db.execute("SELECT status FROM Users WHERE user_id = ? AND board_id = ?", (user_id, board_id)) as c:
        row = await c.fetchone()
        assert row[0] == "active"

    async with db.execute("SELECT expires_at, reason FROM Mutes WHERE user_id = ? AND board_id = ? AND mute_type = 'mute'", (user_id, board_id)) as c:
        row = await c.fetchone()
        assert row is not None
        assert row[1] == "test"

    # Теперь проверяем откат вложенной модерации
    try:
        async with db_transaction(db):
            await remove_regular_mute(user_id, board_id)
            raise RuntimeError("Moderation rollback trigger")
    except RuntimeError:
        pass

    # Мут должен остаться на месте!
    async with db.execute("SELECT expires_at FROM Mutes WHERE user_id = ? AND board_id = ? AND mute_type = 'mute'", (user_id, board_id)) as c:
        row = await c.fetchone()
        assert row is not None, "Regular mute was deleted despite rollback!"


@pytest.mark.asyncio
async def test_in_clause_chunking_massive_dataset(isolated_test_db):
    """
    Проверяет, что функции с IN (...) запросами безопасно обрабатывают
    массивы параметров больше лимита SQLite (2500+ элементов)
    без OperationalError: too many SQL variables.
    """
    db = isolated_test_db
    batch_size = 2500
    user_ids = [700000 + i for i in range(batch_size)]
    file_ids = [f"file_hash_test_{i}" for i in range(batch_size)]
    post_nums = [800000 + i for i in range(batch_size)]

    # 1. remove_users_from_board_batch
    # Вставляем часть пользователей
    await db.executemany("INSERT INTO Users (user_id, board_id) VALUES (?, 'b')", [(uid,) for uid in user_ids[:50]])
    await remove_users_from_board_batch(user_ids, "b")
    async with db.execute("SELECT COUNT(*) FROM Users WHERE board_id = 'b' AND user_id >= 700000") as c:
        count = (await c.fetchone())[0]
        assert count == 0

    # 2. mark_replies_read
    reply_ids = list(range(1, batch_size + 1))
    await mark_replies_read(user_id=1, reply_ids=reply_ids)

    # 3. get_file_details_batch & get_blurhashes_batch
    details = await get_file_details_batch(file_ids)
    assert isinstance(details, dict)

    blurhashes = await get_blurhashes_batch(file_ids)
    assert isinstance(blurhashes, dict)

    # 4. get_poll_results_batch
    poll_results = await get_poll_results_batch(post_nums)
    assert isinstance(poll_results, dict)

    # 5. get_mirrors_batch & get_failed_files_batch
    mirrors = await get_mirrors_batch(file_ids)
    assert isinstance(mirrors, dict)

    failed = await get_failed_files_batch(file_ids)
    assert isinstance(failed, set)

    # 6. get_user_posts_from_list & get_thread_ids_for_posts
    u_posts = await get_user_posts_from_list(1, post_nums)
    assert isinstance(u_posts, list)

    t_map = await get_thread_ids_for_posts(post_nums)
    assert isinstance(t_map, dict)

    # 7. toggle_post_censorship
    c_res = await toggle_post_censorship(post_nums[:100])
    assert isinstance(c_res, dict)


@pytest.mark.asyncio
async def test_safe_begin_immediate_and_safe_commit_lock_safety(isolated_test_db):
    """
    Проверяет, что safe_begin_immediate гарантирует захват db_lock,
    предотвращает гонки, а safe_commit / safe_rollback не ломают вложенные контексты.
    """
    db = isolated_test_db

    # Вызов safe_begin_immediate без предварительного захвата замка
    started = await safe_begin_immediate(db)
    assert started is True
    # Проверяем, что db_lock теперь захвачен текущей задачей
    assert LazyLock.is_owned_by_current_task(common_db_pool_lock := __import__('common.db_pool', fromlist=['db_lock']).db_lock)

    # Повторный вызов не должен падать с cannot start transaction
    started_nested = await safe_begin_immediate(db)
    assert started_nested is False

    await safe_commit(db, started_by_caller=True)

    # safe_rollback при отсутствии транзакции безопасен
    await safe_rollback(db, started_by_caller=True)
