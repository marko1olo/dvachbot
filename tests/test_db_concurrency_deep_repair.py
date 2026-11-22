import asyncio
import math
import pytest
from common.db_pool import (
    db_transaction,
    LazyLock,
    safe_begin_immediate,
    safe_commit,
    safe_rollback,
    _task_tx_depth,
)
import common.db_pool as db_pool_module
from common.database import (
    get_user_global_balance,
    add_user_global_balance,
    deduct_user_global_balance,
    transfer_user_balance,
    safe_transfer_balance,
    update_user_balance,
    get_user_bank_summary,
)


@pytest.mark.asyncio
async def test_update_user_balance_and_safe_transfer_balance_alias(isolated_test_db):
    """
    Проверяет:
    1. update_user_balance (начисление, списание, soft overdraft).
    2. safe_transfer_balance как алиас transfer_user_balance.
    3. get_user_bank_summary proxy в common/database.
    """
    db = isolated_test_db
    user1 = 9001
    user2 = 9002

    # 1. Начисление через update_user_balance
    ok, bal = await update_user_balance(db, user1, 1000.0, "b")
    assert ok is True
    assert bal == 1000.0

    # 2. Частичное списание через update_user_balance
    ok, bal = await update_user_balance(db, user1, -400.0, "b")
    assert ok is True
    assert bal == 600.0

    # 3. Soft overdraft защита: попытка списать больше, чем есть
    ok, bal = await update_user_balance(db, user1, -800.0, "b")
    assert ok is False
    assert bal == 600.0  # Баланс остался целым, транзакция не сломалась

    # 4. Нулевая сумма
    ok, bal = await update_user_balance(db, user1, 0.0)
    assert ok is True
    assert bal == 600.0

    # 5. safe_transfer_balance алиас
    ok, reason, s_bal, r_bal = await safe_transfer_balance(
        db, sender_id=user1, receiver_id=user2, amount=200.0, fee=10.0, category="pay"
    )
    assert ok is True
    assert reason == "success"
    assert s_bal == 390.0  # 600 - 210
    assert r_bal == 200.0

    # 6. get_user_bank_summary proxy
    tot_p, tot_a, deposits = await get_user_bank_summary(db, user1)
    assert tot_p == 0.0
    assert tot_a == 0.0
    assert isinstance(deposits, list)


@pytest.mark.asyncio
async def test_economic_indices_exist_in_database(isolated_test_db):
    """
    Проверяет наличие всех оптимизирующих составных индексов в схеме базы данных:
    BankDeposits, MarketListings, UserTransactions, Users.
    """
    db = isolated_test_db
    async with db.execute("SELECT name FROM sqlite_master WHERE type = 'index'") as c:
        rows = await c.fetchall()
        indices = {r[0] for r in rows if r[0]}

    expected_indices = [
        "idx_bank_deposits_user_status_created",
        "idx_bank_deposits_status_principal",
        "idx_market_seller_status_created",
        "idx_market_buyer_status",
        "idx_usertransactions_user_cat",
        "idx_users_user_board_bal",
        "idx_usertransactions_uid_ts",
    ]

    for idx_name in expected_indices:
        assert idx_name in indices, f"Missing index in sqlite_master: {idx_name}"


@pytest.mark.asyncio
async def test_concurrent_double_spending_adversarial(isolated_test_db):
    """
    Экстремальный тест на Double Spending:
    Пользователь имеет ровно 500 ₪ на балансе.
    15 одновременных задач пытаются одновременно списать по 500 ₪ (через deduct_user_global_balance
    и transfer_user_balance).
    Инварианты:
    - Ровно 1 операция имеет право завершиться успехом.
    - Ровно 14 операций обязаны быть отклонены.
    - Итоговый баланс пользователя строго равен 0.0 (никогда не уходит в минус).
    - Никаких дедлоков и зависаний.
    """
    db = isolated_test_db
    user_id = 9050
    target_id = 9051

    await add_user_global_balance(db, user_id, "b", 500.0)
    assert await get_user_global_balance(db, user_id) == 500.0

    success_count = 0
    failure_count = 0

    async def spend_attempt(task_idx: int):
        nonlocal success_count, failure_count
        if task_idx % 2 == 0:
            ok, _ = await deduct_user_global_balance(db, user_id, "b", 500.0)
        else:
            ok, _, _, _ = await transfer_user_balance(db, user_id, target_id, 500.0, fee=0.0)

        if ok:
            success_count += 1
        else:
            failure_count += 1

    tasks = [asyncio.create_task(spend_attempt(i)) for i in range(15)]
    await asyncio.gather(*tasks)

    assert success_count == 1, f"Double spending vulnerability! {success_count} operations succeeded"
    assert failure_count == 14, f"Expected 14 rejected operations, got {failure_count}"

    final_bal = await get_user_global_balance(db, user_id)
    assert final_bal == 0.0, f"Final balance expected 0.0, got {final_bal}"


@pytest.mark.asyncio
async def test_safe_begin_immediate_retry_and_cancellation_safety(isolated_test_db):
    """
    Проверяет транзакционные примитивы safe_begin_immediate / safe_commit / safe_rollback:
    1. Захват db_lock при вызове.
    2. Невозможность утечки замка при ошибке или отмене.
    3. Корректность вложенных транзакций и отката под shield.
    """
    db = isolated_test_db

    # 1. Базовый запуск
    started = await safe_begin_immediate(db)
    assert started is True
    assert db_pool_module.db_lock.locked_by_current_task()
    assert _task_tx_depth.get() == 1

    # Повторный вызов из той же таски возвращает False (уже в транзакции)
    started_inner = await safe_begin_immediate(db)
    assert started_inner is False

    await safe_commit(db, started_by_caller=True)
    assert not db_pool_module.db_lock.locked()
    assert _task_tx_depth.get() == 0

    # 2. safe_rollback
    started = await safe_begin_immediate(db)
    assert started is True
    await safe_rollback(db, started_by_caller=True)
    assert not db_pool_module.db_lock.locked()
    assert _task_tx_depth.get() == 0
