# -*- coding: utf-8 -*-
"""
bank_engine.py — Bank of Abu / Protected Safe Engine (Банк Абу и Сейф) for DvachBot.
Handles dynamic continuous per-second interest calculations, 3 deposit tiers
(Sych 0.5% flex, Skuf 2.5% 3-day term, MMM Abu 6.0% pyramid), atomic deposits and withdrawals,
robbery safe insulation, fee/penalty calculations, and user bank portfolio summaries.
"""

import json
import logging
import math
import random
import time
from typing import Any, Dict, List, Optional, Tuple

import aiosqlite
from aiogram import F, Router, types, Bot
from aiogram.filters import Command, BaseFilter
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from common.db_pool import db_lock, db_transaction, get_pool
from common.database import (
    add_to_abu_fund,
    add_user_global_balance,
    deduct_user_global_balance,
    get_user_global_balance,
    record_user_transaction,
)

logger = logging.getLogger("bank_engine")

bank_router = Router(name="bank_router")
router = bank_router  # Alias for backward compatibility

# -----------------------------------------------------------------------------
# Banking Tiers Specification
# -----------------------------------------------------------------------------

BANK_TIERS: Dict[str, Dict[str, Any]] = {
    "sych": {
        "id": "sych",
        "name": "📦 Сейф Сыча (Flexible)",
        "short_name": "Сейф Сыча",
        "daily_rate": 0.005,           # 0.5% в сутки (0.005 / 86400 в сек)
        "lockup_seconds": 0,           # Снятие в любой момент
        "withdrawal_fee_pct": 0.01,    # 1.0% комиссия банка на снятие
        "early_penalty_pct": 0.0,
        "default_risk_pct": 0.0,       # 0% риск дефолта
        "default_loss_pct": 0.0,
        "min_deposit": 10.0,
        "desc": "Бессрочный сейф с защитой от грабежей (/rob). Доходность 0.5%/сутки. Снятие в любой момент с комиссией 1%.",
        "icon": "📦",
    },
    "skuf": {
        "id": "skuf",
        "name": "🍺 Депозит Скуфа (3-Day Term)",
        "short_name": "Депозит Скуфа",
        "daily_rate": 0.025,           # 2.5% в сутки (0.025 / 86400 в сек, 7.5% за 3 дня)
        "lockup_seconds": 72 * 3600,   # 72 часа (259 200 сек)
        "withdrawal_fee_pct": 0.0,     # 0% комиссия по истечении срока
        "early_penalty_pct": 0.03,     # Штраф 3% от тела вклада + 100% сгорание процентов при досрочном снятии
        "default_risk_pct": 0.0,       # 0% риск дефолта
        "default_loss_pct": 0.0,
        "min_deposit": 50.0,
        "desc": "Срочный вклад на 3 дня (72ч). Доходность 2.5%/сутки (7.5% за срок). При досрочном снятии: потеря всех % и штраф 3% от тела вклада.",
        "icon": "🍺",
    },
    "mmm_abu": {
        "id": "mmm_abu",
        "name": "🚀 Пирамида МММ Абу (High-Yield)",
        "short_name": "МММ Абу",
        "daily_rate": 0.060,           # 6.0% в сутки (0.060 / 86400 в сек)
        "lockup_seconds": 24 * 3600,   # 24 часа (86 400 сек)
        "withdrawal_fee_pct": 0.0,     # 0% штатная комиссия
        "early_penalty_pct": 0.10,     # Штраф при досрочном снятии (если разрешено)
        "default_risk_pct": 0.03,      # 3% вероятность облавы ОБЭП / дефолта
        "default_loss_pct": 0.50,      # 50% конфискация при дефолте
        "min_deposit": 100.0,
        "desc": "Сверхдоходная пирамида Абу. Доходность 6.0%/сутки. Заморозка 24ч. При выводе 3% шанс облавы ОБЭП с конфискацией 50% депозита.",
        "icon": "🚀",
    },
}

# Маппинг синонимов и алиасов
TIER_ALIASES: Dict[str, str] = {
    "sych": "sych",
    "flexible": "sych",
    "safe_sych": "sych",
    "сыч": "sych",
    "сейф": "sych",
    "skuf": "skuf",
    "term_3d": "skuf",
    "deposit_skuf": "skuf",
    "скуф": "skuf",
    "mmm_abu": "mmm_abu",
    "mmm": "mmm_abu",
    "pyramid": "mmm_abu",
    "ммм": "mmm_abu",
    "пирамида": "mmm_abu",
}


def normalize_tier_id(tier_id: str) -> Optional[str]:
    """
    Нормализует идентификатор тарифа, преобразуя синонимы в канонический tier_id.
    """
    if not tier_id:
        return None
    clean = tier_id.lower().strip()
    return TIER_ALIASES.get(clean)


def get_tier_info(tier_id: str) -> Optional[Dict[str, Any]]:
    """
    Возвращает конфигурацию банковского тарифа.
    """
    canon = normalize_tier_id(tier_id)
    if canon and canon in BANK_TIERS:
        return BANK_TIERS[canon]
    return None


# -----------------------------------------------------------------------------
# User Pending Deposit State Tracking & Amount Parsers
# -----------------------------------------------------------------------------

USER_PENDING_BANK_DEPOSIT: Dict[int, Dict[str, Any]] = {}
PENDING_DEPOSIT_TTL_SEC: float = 300.0  # 5 минут ожидание ввода суммы


def set_user_pending_deposit(user_id: int, tier_id: str, chat_id: int = 0, board_id: str = "b") -> None:
    """Запоминает выбранный пользователем тариф для ввода произвольной суммы из чата."""
    USER_PENDING_BANK_DEPOSIT[user_id] = {
        "tier_id": normalize_tier_id(tier_id) or "sych",
        "chat_id": chat_id,
        "board_id": board_id or "b",
        "expires_at": time.time() + PENDING_DEPOSIT_TTL_SEC,
    }


def get_user_pending_deposit(user_id: int) -> Optional[Dict[str, Any]]:
    """Возвращает активное состояние ожидания ввода суммы, если не истёк TTL."""
    pending = USER_PENDING_BANK_DEPOSIT.get(user_id)
    if not pending:
        return None
    if time.time() > pending.get("expires_at", 0):
        USER_PENDING_BANK_DEPOSIT.pop(user_id, None)
        return None
    return pending


def clear_user_pending_deposit(user_id: int) -> None:
    """Сбрасывает ожидание ввода суммы."""
    USER_PENDING_BANK_DEPOSIT.pop(user_id, None)


def parse_deposit_amount(raw_text: str, wallet_balance: float) -> Optional[float]:
    """
    Парсит произвольный ввод суммы из чата:
    - Числа: 50000, 1000, 150.50, 150,50, "50 000"
    - Сокращения: 50k, 50к, 1.5m, 1.5м
    - Проценты: 25%, 50%, 75%, 100%
    - Ключевые слова: all, все, всё, макс, max, пол, половина, half
    - Валютные суффиксы: 50000 ₪, 1000 руб, 500 шекелей
    Возвращает float > 0 или None при ошибке парсинга.
    """
    if not raw_text or not isinstance(raw_text, str):
        return None

    txt = raw_text.strip().lower()
    # Убираем валютные знаки и слова
    for suffix in ["шекелей", "шекеля", "шекель", "шек", "рублей", "рубля", "руб", "р.", "р", "₪", "$"]:
        txt = txt.replace(suffix, "").strip()

    # Убираем внутренние пробелы (например: "50 000" -> "50000")
    txt = txt.replace(" ", "").replace(",", ".")

    if not txt:
        return None

    # Ключевые слова
    if txt in ("all", "все", "всё", "макс", "max", "весь", "всю"):
        return max(0.0, round(wallet_balance, 2))
    if txt in ("half", "пол", "половина", "половину"):
        return max(0.0, round(wallet_balance * 0.5, 2))
    if txt in ("треть",):
        return max(0.0, round(wallet_balance / 3.0, 2))
    if txt in ("четверть",):
        return max(0.0, round(wallet_balance * 0.25, 2))

    # Проценты
    if txt.endswith("%"):
        try:
            pct_val = float(txt[:-1])
            if pct_val <= 0:
                return None
            return max(0.0, round(wallet_balance * (pct_val / 100.0), 2))
        except ValueError:
            return None

    # k / m суффиксы
    try:
        if txt.endswith("k") or txt.endswith("к"):
            return round(float(txt[:-1]) * 1000.0, 2)
        elif txt.endswith("m") or txt.endswith("м"):
            return round(float(txt[:-1]) * 1000000.0, 2)
        else:
            val = float(txt)
            return round(val, 2) if val > 0 else None
    except ValueError:
        return None


def parse_amount_and_tier(raw_text: str, default_tier: str = "sych") -> Optional[Tuple[str, str]]:
    """
    Проверяет, содержит ли входящее сообщение из чата валидный ввод суммы для депозита,
    и опционально упоминание тарифа (skuf, sych, mmm).
    Возвращает кортеж (amount_str, detected_tier) или None, если текст не является суммой.
    """
    if not raw_text or not isinstance(raw_text, str):
        return None

    text = raw_text.strip()
    if not text or text.startswith("/"):
        return None

    tokens = text.split()
    if len(tokens) > 4:
        return None  # Обычные длинные посты борды игнорируются

    detected_tier = default_tier
    remaining_tokens = []
    ignore_words = {"в", "на", "во", "to", "in", "into"}

    for tok in tokens:
        clean_tok = tok.lower().strip(".,!?:;()[]{}")
        norm_t = normalize_tier_id(clean_tok)
        if norm_t:
            detected_tier = norm_t
        elif clean_tok in ignore_words:
            continue
        else:
            remaining_tokens.append(tok)

    if not remaining_tokens:
        return None

    amt_candidate = " ".join(remaining_tokens)
    # Проверяем, парсится ли кандидат в сумму при тестовом балансе
    test_parsed = parse_deposit_amount(amt_candidate, 1000000.0)
    if test_parsed is None or test_parsed <= 0:
        return None

    return amt_candidate, detected_tier


class PendingBankDepositFilter(BaseFilter):
    """
    Фильтр aiogram для перехвата ввода суммы в чат, когда пользователь
    находится на экране выбора/оформления вклада в Банке Абу.
    Если пользователь не оформляет депозит или ввёл не сумму — возвращает False,
    пропуская сообщение дальше по цепочке роутеров к борде.
    """
    async def __call__(self, message: types.Message) -> bool | dict:
        if not message.text or message.text.startswith("/"):
            return False
        user_id = message.from_user.id if message.from_user else message.chat.id
        pending = get_user_pending_deposit(user_id)
        if not pending:
            return False

        parsed = parse_amount_and_tier(message.text, default_tier=pending.get("tier_id", "sych"))
        if parsed is None:
            return False

        amt_str, detected_tier = parsed
        return {
            "pending_deposit": pending,
            "amount_str": amt_str,
            "detected_tier": detected_tier,
        }


# -----------------------------------------------------------------------------
# Dynamic Continuous Interest Calculator
# -----------------------------------------------------------------------------

def calculate_deposit_state(deposit: Dict[str, Any], current_ts: Optional[float] = None) -> Dict[str, Any]:
    """
    Вычисляет динамическое непрерывное начисление процентов депозита до секунды:
    - principal: тело вклада
    - daily_rate: суточная ставка (например, 0.005 = 0.5%)
    - elapsed_seconds: секунд с момента last_accrual_at
    - instant_accrual = principal * (daily_rate / 86400.0) * elapsed_seconds
    - total_accrued = accrued_interest + instant_accrual
    - total_value = principal + total_accrued
    - is_locked = current_ts < locked_until
    - remaining_lock_sec = max(0, locked_until - current_ts)
    Возвращает словарь с полными актуальными данными.
    """
    now = float(current_ts if current_ts is not None else time.time())

    tier_id = deposit.get("tier_id", "sych")
    tier_info = get_tier_info(tier_id) or BANK_TIERS["sych"]

    principal = float(deposit.get("principal", 0.0))
    daily_rate = float(deposit.get("daily_rate", tier_info["daily_rate"]))
    base_accrued = float(deposit.get("accrued_interest", 0.0))

    last_accrual = float(deposit.get("last_accrual_at") or deposit.get("created_at") or now)
    elapsed_seconds = max(0.0, now - last_accrual)

    rate_per_sec = daily_rate / 86400.0
    instant_accrual = principal * rate_per_sec * elapsed_seconds
    total_accrued = base_accrued + instant_accrual
    total_value = principal + total_accrued

    created_at = float(deposit.get("created_at") or now)
    locked_until = float(deposit.get("locked_until") or created_at)
    is_locked = now < locked_until
    remaining_lock_sec = max(0.0, locked_until - now)

    return {
        "id": deposit.get("id"),
        "user_id": deposit.get("user_id"),
        "board_id": deposit.get("board_id", "b"),
        "tier_id": tier_info["id"],
        "tier_name": tier_info["name"],
        "short_name": tier_info["short_name"],
        "principal": principal,
        "daily_rate": daily_rate,
        "created_at": created_at,
        "locked_until": locked_until,
        "last_accrual_at": last_accrual,
        "accrued_interest": round(total_accrued, 2),
        "total_value": round(total_value, 2),
        "is_locked": is_locked,
        "remaining_lock_sec": int(remaining_lock_sec),
        "elapsed_seconds": int(elapsed_seconds),
        "status": deposit.get("status", "active"),
        "withdrawn_at": deposit.get("withdrawn_at"),
        "withdrawn_amount": deposit.get("withdrawn_amount", 0.0),
    }


# -----------------------------------------------------------------------------
# Atomic Deposit & Withdrawal Operations
# -----------------------------------------------------------------------------

async def create_bank_deposit(
    db,
    user_id: int,
    board_id: Optional[str],
    tier_id: str,
    amount: float
) -> Tuple[bool, Optional[Dict[str, Any]], str]:
    """
    Атомарно создает банковский депозит:
    1. Проверяет корректность суммы и минимальный порог тарифа.
    2. Списывает сумму с баланса кошелька пользователя.
    3. Создает запись в BankDeposits.
    4. Записывает транзакцию в UserTransactions.
    Возвращает (success: bool, deposit_dict: Optional[dict], error_msg: str).
    """
    if not isinstance(amount, (int, float)) or math.isnan(amount) or math.isinf(amount) or amount <= 0:
        return False, None, "Сумма депозита должна быть положительным числом больше 0 ₪."

    canon_tier = normalize_tier_id(tier_id)
    if not canon_tier or canon_tier not in BANK_TIERS:
        return False, None, f"Неизвестный банковский тариф: {tier_id}."

    tier_info = BANK_TIERS[canon_tier]
    min_dep = tier_info["min_deposit"]
    if amount < min_dep:
        return False, None, f"Минимальная сумма для тарифа «{tier_info['short_name']}» составляет {min_dep:,.0f} ₪."

    b_id = board_id or "b"
    amount = round(float(amount), 2)
    now = time.time()
    locked_until = now + float(tier_info["lockup_seconds"])

    async with db_transaction(db):
        ok, _ = await deduct_user_global_balance(db, user_id, b_id, amount)
        if not ok:
            cur_bal = await get_user_global_balance(db, user_id)
            return False, None, f"Недостаточно шекелей в кошельке (баланс: {cur_bal:,.0f} ₪, требуется: {amount:,.0f} ₪)."

        cursor = await db.execute(
            """
            INSERT INTO BankDeposits (
                user_id, board_id, tier_id, principal, daily_rate,
                created_at, locked_until, last_accrual_at, accrued_interest, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0.0, 'active')
            """,
            (
                user_id,
                b_id,
                canon_tier,
                amount,
                tier_info["daily_rate"],
                now,
                locked_until,
                now,
            )
        )
        dep_id = cursor.lastrowid

        await record_user_transaction(
            db,
            user_id,
            -amount,
            "bank",
            f"Депозит в Банк Абу: {tier_info['short_name']} (вклад #{dep_id})"
        )

        deposit_record = {
            "id": dep_id,
            "user_id": user_id,
            "board_id": b_id,
            "tier_id": canon_tier,
            "tier_name": tier_info["name"],
            "short_name": tier_info["short_name"],
            "principal": amount,
            "daily_rate": tier_info["daily_rate"],
            "created_at": now,
            "locked_until": locked_until,
            "last_accrual_at": now,
            "accrued_interest": 0.0,
            "total_value": amount,
            "is_locked": now < locked_until,
            "remaining_lock_sec": int(max(0, locked_until - now)),
            "status": "active",
        }

        return True, deposit_record, ""


async def withdraw_bank_deposit(
    db,
    deposit_id: int,
    user_id: int,
    board_id: Optional[str] = None,
    force_early: bool = False,
    random_roll: Optional[float] = None
) -> Tuple[bool, float, float, float, float, bool, str]:
    """
    Атомарно закрывает и выводит банковский депозит:
    - Применяет непрерывный расчет процентов до текущей секунды.
    - Обрабатывает тарифные правила.
    - Зачисляет выплату в кошелек пользователя.
    - Обновляет статус в BankDeposits и логирует в UserTransactions.
    Возвращает:
      (success: bool, payout: float, principal: float, interest_paid: float, fee_or_penalty: float, is_default: bool, error_msg: str)
    """
    b_id = board_id or "b"
    now = time.time()

    async with db_transaction(db):
        async with db.execute(
            """
            SELECT id, user_id, board_id, tier_id, principal, daily_rate,
                   created_at, locked_until, last_accrual_at, accrued_interest, status
            FROM BankDeposits
            WHERE id = ? AND user_id = ?
            """,
            (deposit_id, user_id)
        ) as c:
            row = await c.fetchone()

        if not row:
            return False, 0.0, 0.0, 0.0, 0.0, False, "Депозит не найден."

        dep_raw = {
            "id": row[0],
            "user_id": row[1],
            "board_id": row[2],
            "tier_id": row[3],
            "principal": float(row[4]),
            "daily_rate": float(row[5]),
            "created_at": float(row[6]),
            "locked_until": float(row[7]),
            "last_accrual_at": float(row[8]),
            "accrued_interest": float(row[9]),
            "status": row[10],
        }

        if dep_raw["status"] != "active":
            return False, 0.0, 0.0, 0.0, 0.0, False, f"Депозит уже закрыт (статус: {dep_raw['status']})."

        state = calculate_deposit_state(dep_raw, current_ts=now)
        principal = state["principal"]
        total_accrued = state["accrued_interest"]
        total_value = state["total_value"]
        is_locked = state["is_locked"]
        tier_id = state["tier_id"]
        tier_info = get_tier_info(tier_id) or BANK_TIERS["sych"]

        payout = 0.0
        interest_paid = 0.0
        fee_or_penalty = 0.0
        is_default = False
        final_status = "withdrawn"

        if tier_id == "sych":
            raw_fee = total_value * tier_info["withdrawal_fee_pct"]
            fee_or_penalty = round(raw_fee, 2)
            if fee_or_penalty > total_value:
                fee_or_penalty = total_value
            payout = round(total_value - fee_or_penalty, 2)
            interest_paid = round(total_accrued, 2)
            final_status = "withdrawn"

            if fee_or_penalty > 0:
                await add_to_abu_fund(db, fee_or_penalty, donor_id=user_id, reason=f"Комиссия за снятие вклада Сейф Сыча #{deposit_id}")

        elif tier_id == "skuf":
            if is_locked and not force_early:
                rem_h = int(state["remaining_lock_sec"] / 3600)
                rem_m = int((state["remaining_lock_sec"] % 3600) / 60)
                return False, 0.0, 0.0, 0.0, 0.0, False, (
                    f"Депозит Скуфа заблокирован (осталось {rem_h}ч {rem_m}м). "
                    f"При досрочном снятии все начисленные проценты (+{total_accrued:,.2f} ₪) сгорят, "
                    f"а с тела вклада удержится штраф 3% ({round(principal * 0.03, 2):,.2f} ₪)."
                )

            if is_locked and force_early:
                interest_paid = 0.0
                fee_or_penalty = round(principal * tier_info["early_penalty_pct"], 2)
                payout = round(principal - fee_or_penalty, 2)
                final_status = "broken_early"

                if fee_or_penalty > 0:
                    await add_to_abu_fund(db, fee_or_penalty, donor_id=user_id, reason=f"Штраф за досрочное снятие Депозита Скуфа #{deposit_id}")
            else:
                interest_paid = round(total_accrued, 2)
                fee_or_penalty = 0.0
                payout = round(principal + total_accrued, 2)
                final_status = "withdrawn"

        elif tier_id == "mmm_abu":
            if is_locked and not force_early:
                rem_h = int(state["remaining_lock_sec"] / 3600)
                rem_m = int((state["remaining_lock_sec"] % 3600) / 60)
                return False, 0.0, 0.0, 0.0, 0.0, False, (
                    f"Пирамида МММ Абу заблокирована на 24 часа (осталось {rem_h}ч {rem_m}м). "
                    f"Досрочный вывод не предусмотрен правилами пирамиды."
                )

            if is_locked and force_early:
                interest_paid = 0.0
                fee_or_penalty = round(principal * tier_info["early_penalty_pct"], 2)
                payout = round(principal - fee_or_penalty, 2)
                final_status = "broken_early"

                if fee_or_penalty > 0:
                    await add_to_abu_fund(db, fee_or_penalty, donor_id=user_id, reason=f"Штраф за срыв пирамиды МММ Абу #{deposit_id}")
            else:
                roll = random_roll if random_roll is not None else random.random()
                if roll < tier_info["default_risk_pct"]:
                    is_default = True
                    confiscated = round(total_value * tier_info["default_loss_pct"], 2)
                    fee_or_penalty = confiscated
                    payout = round(total_value - confiscated, 2)
                    interest_paid = max(0.0, round(payout - principal, 2))
                    final_status = "confiscated"

                    if confiscated > 0:
                        await add_to_abu_fund(db, confiscated, donor_id=user_id, reason=f"Облава ОБЭП / Конфискация МММ Абу #{deposit_id}")
                else:
                    interest_paid = round(total_accrued, 2)
                    fee_or_penalty = 0.0
                    payout = round(principal + total_accrued, 2)
                    final_status = "withdrawn"

        if payout > 0:
            await add_user_global_balance(db, user_id, b_id, payout)

        await db.execute(
            """
            UPDATE BankDeposits
            SET status = ?, withdrawn_at = ?, withdrawn_amount = ?, accrued_interest = ?
            WHERE id = ?
            """,
            (final_status, now, payout, total_accrued, deposit_id)
        )

        desc = (
            f"Вывод из Банка Абу: {tier_info['short_name']} (вклад #{deposit_id}"
            + (", ОБЛАВА ОБЭП -50%" if is_default else "")
            + (", ДОСРОЧНО СО ШТРАФОМ" if final_status == "broken_early" else "")
            + ")"
        )
        await record_user_transaction(db, user_id, payout, "bank", desc)

        return True, payout, principal, interest_paid, fee_or_penalty, is_default, ""


# -----------------------------------------------------------------------------
# Portfolio Summary & Analytics
# -----------------------------------------------------------------------------

async def get_user_bank_summary(db, user_id: int) -> Tuple[float, float, List[Dict[str, Any]]]:
    """
    Возвращает сводку по активным банковским депозитам пользователя:
    (total_principal: float, total_accrued: float, deposits: List[Dict[str, Any]])
    Каждый депозит динамически пересчитан на текущую секунду.
    """
    now = time.time()
    query = """
        SELECT id, user_id, board_id, tier_id, principal, daily_rate,
               created_at, locked_until, last_accrual_at, accrued_interest, status
        FROM BankDeposits
        WHERE user_id = ? AND status = 'active'
        ORDER BY created_at DESC
    """
    deposits: List[Dict[str, Any]] = []
    total_principal = 0.0
    total_accrued = 0.0

    async with db.execute(query, (user_id,)) as c:
        rows = await c.fetchall()
        for r in rows:
            raw = {
                "id": r[0],
                "user_id": r[1],
                "board_id": r[2],
                "tier_id": r[3],
                "principal": float(r[4]),
                "daily_rate": float(r[5]),
                "created_at": float(r[6]),
                "locked_until": float(r[7]),
                "last_accrual_at": float(r[8]),
                "accrued_interest": float(r[9]),
                "status": r[10],
            }
            state = calculate_deposit_state(raw, current_ts=now)
            deposits.append(state)
            total_principal += state["principal"]
            total_accrued += state["accrued_interest"]

    return round(total_principal, 2), round(total_accrued, 2), deposits


# -----------------------------------------------------------------------------
# UI Builders & Keyboards
# -----------------------------------------------------------------------------

def build_bank_dashboard_view(
    wallet_balance: float,
    total_principal: float,
    total_accrued: float,
    deposits: List[Dict[str, Any]]
) -> Tuple[str, InlineKeyboardMarkup]:
    """Генерирует текст и клавиатуру главного экрана Банка Абу."""
    total_bank = round(total_principal + total_accrued, 2)
    total_wealth = round(wallet_balance + total_bank, 2)

    lines = [
        "🏦 <b>БАНК АБУ — ЗАЩИЩЕННЫЙ СЕЙФ</b>\n",
        f"💰 <b>Кошелек на руках:</b> <code>{wallet_balance:,.2f} ₪</code> <i>(уязвим для /rob)</i>",
        f"🔒 <b>Вклады в сейфе:</b> <code>{total_principal:,.2f} ₪</code> 🛡️ <b>(ЗАЩИЩЕНО)</b>",
        f"📈 <b>Накопленные %:</b> <code>+{total_accrued:,.2f} ₪</code>",
        f"💵 <b>Всего в Банке:</b> <code>{total_bank:,.2f} ₪</code>",
        f"💎 <b>Общий капитал:</b> <code>{total_wealth:,.2f} ₪</code>\n",
        "<code>────────────────────────</code>",
        "📊 <b>ТВОИ ДЕПОЗИТЫ:</b>",
    ]

    if not deposits:
        lines.append("<i>У тебя нет активных вкладов. Шекели в кошельке не приносят доход и могут быть украдены!</i>")
    else:
        for idx, d in enumerate(deposits, 1):
            lock_txt = ""
            if d["is_locked"]:
                rem_h = int(d["remaining_lock_sec"] / 3600)
                rem_m = int((d["remaining_lock_sec"] % 3600) / 60)
                lock_txt = f" 🔒 <i>(блок {rem_h}ч {rem_m}м)</i>"
            else:
                lock_txt = " 🔓 <i>(доступен к выводу)</i>"

            tier_icon = BANK_TIERS.get(d["tier_id"], {}).get("icon", "📦")
            lines.append(
                f"{idx}. {tier_icon} <b>{d['short_name']}</b>: "
                f"<code>{d['principal']:,.0f} ₪</code> (+{d['accrued_interest']:,.2f} ₪){lock_txt}"
            )

    text = "\n".join(lines)

    kb = [
        [
            InlineKeyboardButton(text="📥 Внести вклад", callback_data="bank_deposit_menu"),
            InlineKeyboardButton(text="📤 Снять шекели", callback_data="bank_withdraw_menu"),
        ],
        [
            InlineKeyboardButton(text="🔄 Обновить проценты", callback_data="bank_refresh"),
        ],
        [
            InlineKeyboardButton(text="🛒 В Барахолку (/market)", callback_data="market_main_hub"),
            InlineKeyboardButton(text="🏬 Торговый Хаб (/shop)", callback_data="shop_main_hub"),
        ]
    ]

    return text, InlineKeyboardMarkup(inline_keyboard=kb)


def build_deposit_tiers_kb() -> InlineKeyboardMarkup:
    """Клавиатура выбора тарифа для нового депозита."""
    kb = [
        [
            InlineKeyboardButton(text="📦 Сейф Сыча (0.5%/день, Flex)", callback_data="bank_deposit_tier:sych"),
        ],
        [
            InlineKeyboardButton(text="🍺 Депозит Скуфа (2.5%/день, 72ч)", callback_data="bank_deposit_tier:skuf"),
        ],
        [
            InlineKeyboardButton(text="🚀 МММ Абу (6.0%/день, 24ч)", callback_data="bank_deposit_tier:mmm_abu"),
        ],
        [
            InlineKeyboardButton(text="⬅️ Назад в Банк", callback_data="bank_main_hub"),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)


def build_deposit_presets_kb(tier_id: str, wallet_balance: float) -> Tuple[str, InlineKeyboardMarkup]:
    """Генерирует экран пресетов суммы депозита для выбранного тарифа."""
    tier_info = BANK_TIERS.get(tier_id, BANK_TIERS["sych"])
    min_dep = tier_info["min_deposit"]

    p25 = max(min_dep, round(wallet_balance * 0.25, 2))
    p50 = max(min_dep, round(wallet_balance * 0.50, 2))
    p100 = max(min_dep, round(wallet_balance, 2))

    text = (
        f"{tier_info['icon']} <b>ОФОРМЛЕНИЕ ВКЛАДА: {tier_info['name']}</b>\n\n"
        f"📝 <i>{tier_info['desc']}</i>\n\n"
        f"💰 <b>Твой баланс в кошельке:</b> <code>{wallet_balance:,.2f} ₪</code>\n"
        f"💵 <b>Минимальный депозит:</b> <code>{min_dep:,.0f} ₪</code>\n\n"
        f"💬 <b>Напиши любую сумму сообщением прямо в чат</b> (например: <code>50000</code>, <code>25k</code>, <code>все</code>)\n"
        f"или нажми на процент / готовую кнопку ниже:"
    )

    kb_rows = [
        [
            InlineKeyboardButton(text=f"25% ({p25:,.0f} ₪)", callback_data=f"bank_do_deposit:{tier_id}:{p25}"),
            InlineKeyboardButton(text=f"50% ({p50:,.0f} ₪)", callback_data=f"bank_do_deposit:{tier_id}:{p50}"),
            InlineKeyboardButton(text=f"100% ({p100:,.0f} ₪)", callback_data=f"bank_do_deposit:{tier_id}:{p100}"),
        ],
        [
            InlineKeyboardButton(text="100 ₪", callback_data=f"bank_do_deposit:{tier_id}:100"),
            InlineKeyboardButton(text="500 ₪", callback_data=f"bank_do_deposit:{tier_id}:500"),
            InlineKeyboardButton(text="1000 ₪", callback_data=f"bank_do_deposit:{tier_id}:1000"),
            InlineKeyboardButton(text="5000 ₪", callback_data=f"bank_do_deposit:{tier_id}:5000"),
        ],
        [
            InlineKeyboardButton(text="⬅️ Выбор тарифа", callback_data="bank_deposit_menu"),
            InlineKeyboardButton(text="🏦 Главная Банка", callback_data="bank_main_hub"),
        ]
    ]

    return text, InlineKeyboardMarkup(inline_keyboard=kb_rows)


async def _render_bank_view(
    target: types.Message | types.CallbackQuery,
    text: str,
    kb: InlineKeyboardMarkup,
    category: str = "wallet"
):
    """Универсально отображает или обновляет представление Банка."""
    try:
        if isinstance(target, types.CallbackQuery):
            if target.message.caption is not None or target.message.photo:
                await target.message.edit_caption(caption=text, reply_markup=kb, parse_mode="HTML")
            elif target.message.text is not None:
                await target.message.edit_text(text=text, reply_markup=kb, parse_mode="HTML")
            else:
                from banner_manager import send_banner_message
                await send_banner_message(bot=target.bot, chat_id=target.message.chat.id, caption=text, reply_markup=kb, category=category, parse_mode="HTML")
        else:
            from banner_manager import send_banner_message
            await send_banner_message(bot=target.bot, chat_id=target.chat.id, caption=text, reply_markup=kb, category=category, parse_mode="HTML")
            try:
                await target.delete()
            except Exception:
                pass
    except Exception:
        try:
            if isinstance(target, types.CallbackQuery):
                await target.message.answer(text=text, reply_markup=kb, parse_mode="HTML")
            else:
                await target.answer(text=text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            pass


# -----------------------------------------------------------------------------
# Telegram Command Handlers
# -----------------------------------------------------------------------------

@bank_router.message(Command("bank", "банк", "сейф", "safe", ignore_case=True, ignore_mention=True))
async def cmd_bank(message: types.Message, board_id: str | None = None, stream: str = 'ru') -> None:
    """Главный дашборд Банка Абу и Сейфа."""
    b_id = board_id or "b"
    user_id = message.from_user.id if message.from_user else message.chat.id
    db = await get_pool()

    wallet_balance = await get_user_global_balance(db, user_id)
    total_principal, total_accrued, deposits = await get_user_bank_summary(db, user_id)

    text, kb = build_bank_dashboard_view(wallet_balance, total_principal, total_accrued, deposits)
    await _render_bank_view(message, text, kb, category="wallet")


@bank_router.message(Command("deposit", "вклад", "депозит", ignore_case=True, ignore_mention=True))
async def cmd_deposit(message: types.Message, board_id: str | None = None, stream: str = 'ru') -> None:
    """Команда открытия депозита или вызов визарда тарифов."""
    b_id = board_id or "b"
    user_id = message.from_user.id if message.from_user else message.chat.id
    db = await get_pool()

    parts = (message.text or "").split()[1:]

    # Если переданы аргументы: /deposit [сумма] [тариф]
    if parts:
        raw_amt = parts[0].lower().replace("к", "k").replace("₪", "").replace(",", ".")
        raw_tier = parts[1] if len(parts) > 1 else "sych"

        wallet_balance = await get_user_global_balance(db, user_id)

        if raw_amt in ("all", "все", "всё"):
            amount = wallet_balance
        elif raw_amt in ("half", "пол", "половина"):
            amount = round(wallet_balance / 2.0, 2)
        else:
            try:
                if raw_amt.endswith("k"):
                    amount = float(raw_amt[:-1]) * 1000
                elif raw_amt.endswith("m"):
                    amount = float(raw_amt[:-1]) * 1000000
                else:
                    amount = float(raw_amt)
            except ValueError:
                await message.answer("❌ Неверный формат суммы. Пример: <code>/deposit 500 skuf</code>", parse_mode="HTML")
                return

        canon_tier = normalize_tier_id(raw_tier) or "sych"
        ok, dep, err = await create_bank_deposit(db, user_id, b_id, canon_tier, amount)

        if not ok:
            await message.answer(f"❌ Ошибка открытия вклада: {err}", parse_mode="HTML")
            return

        tier_info = BANK_TIERS[canon_tier]
        resp = (
            f"🎉 <b>ВКЛАД УСПЕШНО ОФОРМЛЕН!</b>\n\n"
            f"🏦 <b>Тариф:</b> {tier_info['name']}\n"
            f"💵 <b>Сумма:</b> <code>{dep['principal']:,.2f} ₪</code>\n"
            f"📈 <b>Доходность:</b> <code>{tier_info['daily_rate'] * 100:.1f}% в сутки</code>\n"
            f"🛡️ <i>Средства надежно спрятаны в сейф и недосягаемы для грабителей (/rob)!</i>"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏦 В Банк Абу", callback_data="bank_main_hub")],
        ])
        await message.answer(resp, reply_markup=kb, parse_mode="HTML")
        return

    # Интерактивный режим: выбор тарифа
    set_user_pending_deposit(user_id, "sych", chat_id=message.chat.id, board_id=b_id)
    text = (
        "🏦 <b>ОФОРМЛЕНИЕ ВКЛАДА В БАНК АБУ</b>\n\n"
        "Выбери один из доступных тарифов для надежного сохранения и преумножения шекелей:\n\n"
        "1. 📦 <b>Сейф Сыча (0.5%/сутки)</b> — бессрочный, вывод в любой момент (1% комиссия)\n"
        "2. 🍺 <b>Депозит Скуфа (2.5%/сутки)</b> — заморозка 72ч (7.5% за срок), 0% комиссия\n"
        "3. 🚀 <b>Пирамида МММ Абу (6.0%/сутки)</b> — заморозка 24ч, 3% риск облавы ОБЭП (-50%)\n\n"
        "<i>Нажми на нужный тариф ниже или просто отправь сумму сообщением в чат:</i>"
    )
    kb = build_deposit_tiers_kb()
    await _render_bank_view(message, text, kb, category="wallet")


@bank_router.message(Command("withdraw", "снять", "вывод", ignore_case=True, ignore_mention=True))
async def cmd_withdraw(message: types.Message, board_id: str | None = None, stream: str = 'ru') -> None:
    """Команда снятия депозита или интерактивное меню вывода."""
    b_id = board_id or "b"
    user_id = message.from_user.id if message.from_user else message.chat.id
    db = await get_pool()

    parts = (message.text or "").split()[1:]

    # Если передан номер депозита: /withdraw <deposit_id>
    if parts and parts[0].isdigit():
        deposit_id = int(parts[0])
        total_p, total_a, deposits = await get_user_bank_summary(db, user_id)
        target_dep = next((d for d in deposits if d["id"] == deposit_id), None)

        if not target_dep:
            await message.answer("❌ Депозит с таким номером не найден среди активных.", parse_mode="HTML")
            return

        if target_dep["is_locked"]:
            # Показываем предупреждение о досрочном снятии
            penalty_val = round(target_dep["principal"] * (0.03 if target_dep["tier_id"] == "skuf" else 0.10), 2)
            payout_val = round(target_dep["principal"] - penalty_val, 2)
            rem_h = int(target_dep["remaining_lock_sec"] / 3600)
            rem_m = int((target_dep["remaining_lock_sec"] % 3600) / 60)

            warn_text = (
                f"⚠️ <b>ВНИМАНИЕ! ДОСРОЧНОЕ СНЯТИЕ ВКЛАДА #{deposit_id}</b>\n\n"
                f"Тариф: <b>{target_dep['tier_name']}</b>\n"
                f"Вклад заблокирован еще на <b>{rem_h}ч {rem_m}м</b>.\n\n"
                f"При досрочном выводе:\n"
                f"• Сгорят ВСЕ начисленные проценты: <b>+{target_dep['accrued_interest']:,.2f} ₪</b>\n"
                f"• Штраф: <b>-{penalty_val:,.2f} ₪</b>\n"
                f"• Вы получите на руки: <b>{payout_val:,.2f} ₪</b>\n\n"
                f"Вы действительно хотите сорвать вклад?"
            )
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⚠️ Да, снять со штрафом", callback_data=f"bank_withdraw_confirm:{deposit_id}")],
                [InlineKeyboardButton(text="❌ Отмена", callback_data="bank_main_hub")],
            ])
            await message.answer(warn_text, reply_markup=kb, parse_mode="HTML")
            return

        # Штатный вывод
        ok, payout, principal, interest, fee, is_default, err = await withdraw_bank_deposit(db, deposit_id, user_id, b_id)
        if not ok:
            await message.answer(f"❌ Ошибка вывода: {err}", parse_mode="HTML")
            return

        resp = (
            f"💵 <b>ВЫВОД ИЗ БАНКА АБУ ВЫПОЛНЕН!</b>\n\n"
            f"💰 <b>Зачислено в кошелек:</b> <code>+{payout:,.2f} ₪</code>\n"
            f"📦 <b>Тело вклада:</b> <code>{principal:,.2f} ₪</code>\n"
            f"📈 <b>Выплаченные проценты:</b> <code>+{interest:,.2f} ₪</code>\n"
            f"🏛 <b>Удержано (комиссия/штраф):</b> <code>{fee:,.2f} ₪</code>"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏦 В Банк Абу", callback_data="bank_main_hub")],
        ])
        await message.answer(resp, reply_markup=kb, parse_mode="HTML")
        return

    # Интерактивное меню вывода
    total_p, total_a, deposits = await get_user_bank_summary(db, user_id)
    if not deposits:
        await message.answer("❌ У вас нет активных вкладов для вывода.", parse_mode="HTML")
        return

    lines = ["📤 <b>ВЫБЕРИТЕ ДЕПОЗИТ ДЛЯ ВЫВОДА:</b>\n"]
    kb_rows = []
    for d in deposits:
        lock_status = "🔒 (досрочно)" if d["is_locked"] else "🔓 (готов)"
        lines.append(f"• Вклад <b>#{d['id']}</b> ({d['short_name']}): <code>{d['total_value']:,.2f} ₪</code> {lock_status}")
        kb_rows.append([
            InlineKeyboardButton(
                text=f"📤 Снять #{d['id']} ({d['total_value']:,.0f} ₪) {lock_status}",
                callback_data=f"bank_withdraw_sel:{d['id']}"
            )
        ])

    kb_rows.append([InlineKeyboardButton(text="⬅️ Назад в Банк", callback_data="bank_main_hub")])
    await message.answer("\n".join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows), parse_mode="HTML")


# -----------------------------------------------------------------------------
# Telegram Callback Query Handlers
# -----------------------------------------------------------------------------

@bank_router.callback_query(F.data.in_(["bank_main_hub", "bank_view"]))
async def cb_bank_hub(callback: types.CallbackQuery, board_id: str | None = None):
    """Главный экран Банка по колбэку."""
    clear_user_pending_deposit(callback.from_user.id)
    b_id = board_id or "b"
    user_id = callback.from_user.id
    db = await get_pool()

    wallet_balance = await get_user_global_balance(db, user_id)
    total_principal, total_accrued, deposits = await get_user_bank_summary(db, user_id)

    text, kb = build_bank_dashboard_view(wallet_balance, total_principal, total_accrued, deposits)
    await _render_bank_view(callback, text, kb, category="wallet")
    await callback.answer()


@bank_router.callback_query(F.data == "bank_refresh")
async def cb_bank_refresh(callback: types.CallbackQuery, board_id: str | None = None):
    """Обновление начисленных процентов на лету в режиме реального времени."""
    b_id = board_id or "b"
    user_id = callback.from_user.id
    db = await get_pool()

    wallet_balance = await get_user_global_balance(db, user_id)
    total_principal, total_accrued, deposits = await get_user_bank_summary(db, user_id)

    text, kb = build_bank_dashboard_view(wallet_balance, total_principal, total_accrued, deposits)
    await _render_bank_view(callback, text, kb, category="wallet")
    await callback.answer("🔄 Проценты пересчитаны!", show_alert=False)


@bank_router.callback_query(F.data == "bank_deposit_menu")
async def cb_bank_deposit_menu(callback: types.CallbackQuery, board_id: str | None = None):
    """Меню выбора тарифа депозита."""
    set_user_pending_deposit(callback.from_user.id, "sych", chat_id=callback.message.chat.id, board_id=board_id or "b")
    text = (
        "🏦 <b>ОФОРМЛЕНИЕ ВКЛАДА В БАНК АБУ</b>\n\n"
        "Выбери один из доступных тарифов для надежного сохранения и преумножения шекелей:\n\n"
        "1. 📦 <b>Сейф Сыча (0.5%/сутки)</b> — бессрочный, вывод в любой момент (1% комиссия)\n"
        "2. 🍺 <b>Депозит Скуфа (2.5%/сутки)</b> — заморозка 72ч (7.5% за срок), 0% комиссия\n"
        "3. 🚀 <b>Пирамида МММ Абу (6.0%/сутки)</b> — заморозка 24ч, 3% риск облавы ОБЭП (-50%)\n\n"
        "<i>Нажми на нужный тариф ниже или напиши сумму сообщением прямо в чат:</i>"
    )
    kb = build_deposit_tiers_kb()
    await _render_bank_view(callback, text, kb, category="wallet")
    await callback.answer()


@bank_router.callback_query(F.data.startswith("bank_deposit_tier:") | F.data.startswith("bank_sel_tier_"))
async def cb_bank_deposit_tier(callback: types.CallbackQuery, board_id: str | None = None):
    """Экран выбора суммы и готовых пресетов для выбранного тарифа."""
    raw = callback.data
    tier_id = raw.split(":", 1)[1] if ":" in raw else raw.replace("bank_sel_tier_", "")
    set_user_pending_deposit(callback.from_user.id, tier_id, chat_id=callback.message.chat.id, board_id=board_id or "b")

    db = await get_pool()
    user_id = callback.from_user.id
    wallet_balance = await get_user_global_balance(db, user_id)

    text, kb = build_deposit_presets_kb(tier_id, wallet_balance)
    await _render_bank_view(callback, text, kb, category="wallet")
    await callback.answer()


@bank_router.callback_query(F.data.startswith("bank_do_deposit:") | F.data.startswith("bank_dep_"))
async def cb_bank_do_deposit(callback: types.CallbackQuery, board_id: str | None = None):
    """Исполнение создания депозита по нажатию пресета."""
    clear_user_pending_deposit(callback.from_user.id)
    b_id = board_id or "b"
    user_id = callback.from_user.id
    raw = callback.data

    if ":" in raw:
        parts = raw.split(":")
        tier_id = parts[1]
        amount = float(parts[2])
    else:
        # Backward-compatibility format bank_dep_{tier}_{amt}
        raw_clean = raw.replace("bank_dep_", "")
        parts = raw_clean.rsplit("_", 1)
        tier_id = parts[0]
        amt_str = parts[1]
        db_temp = await get_pool()
        w_bal = await get_user_global_balance(db_temp, user_id)
        if amt_str == "all":
            amount = w_bal
        elif amt_str == "half":
            amount = round(w_bal / 2.0, 2)
        else:
            amount = float(amt_str)

    db = await get_pool()
    ok, dep, err = await create_bank_deposit(db, user_id, b_id, tier_id, amount)

    if not ok:
        await callback.answer(f"❌ {err}", show_alert=True)
        return

    tier_info = BANK_TIERS.get(dep["tier_id"], BANK_TIERS["sych"])
    text = (
        f"🎉 <b>ВКЛАД УСПЕШНО ОФОРМЛЕН!</b>\n\n"
        f"🏦 <b>Тариф:</b> {tier_info['name']}\n"
        f"💵 <b>Сумма:</b> <code>{dep['principal']:,.2f} ₪</code>\n"
        f"📈 <b>Доходность:</b> <code>{tier_info['daily_rate'] * 100:.1f}% в сутки</code>\n"
        f"🛡️ <i>Средства изолированы в сейфе и защищены от грабежей (/rob)!</i>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏦 В Банк Абу", callback_data="bank_main_hub")],
    ])
    await _render_bank_view(callback, text, kb, category="wallet")
    await callback.answer("✅ Вклад успешно открыт!", show_alert=False)


@bank_router.callback_query(F.data == "bank_withdraw_menu")
async def cb_bank_withdraw_menu(callback: types.CallbackQuery, board_id: str | None = None):
    """Список депозитов, доступных для вывода."""
    clear_user_pending_deposit(callback.from_user.id)
    b_id = board_id or "b"
    user_id = callback.from_user.id
    db = await get_pool()

    total_p, total_a, deposits = await get_user_bank_summary(db, user_id)

    if not deposits:
        await callback.answer("У вас нет активных вкладов для вывода.", show_alert=True)
        return

    lines = [
        "📤 <b>СНЯТИЕ ШЕКЕЛЕЙ ИЗ БАНКА АБУ</b>\n",
        "Нажмите на нужный депозит для вывода:\n",
    ]
    kb_rows = []
    for d in deposits:
        lock_txt = "🔒 (досрочно)" if d["is_locked"] else "🔓 (готов)"
        lines.append(f"• Вклад <b>#{d['id']}</b> ({d['short_name']}): <code>{d['total_value']:,.2f} ₪</code> {lock_txt}")
        kb_rows.append([
            InlineKeyboardButton(
                text=f"📤 #{d['id']} {d['short_name']} ({d['total_value']:,.0f} ₪) {lock_txt}",
                callback_data=f"bank_withdraw_sel:{d['id']}"
            )
        ])

    kb_rows.append([InlineKeyboardButton(text="⬅️ Назад в Банк", callback_data="bank_main_hub")])
    await _render_bank_view(callback, "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=kb_rows), category="wallet")
    await callback.answer()


@bank_router.callback_query(F.data.startswith("bank_withdraw_sel:"))
async def cb_bank_withdraw_sel(callback: types.CallbackQuery, board_id: str | None = None):
    """Обработка выбора депозита для вывода (проверка блокировки и штрафов)."""
    b_id = board_id or "b"
    user_id = callback.from_user.id
    dep_id = int(callback.data.split(":", 1)[1])

    db = await get_pool()
    total_p, total_a, deposits = await get_user_bank_summary(db, user_id)
    target_dep = next((d for d in deposits if d["id"] == dep_id), None)

    if not target_dep:
        await callback.answer("❌ Депозит не найден.", show_alert=True)
        return

    if target_dep["is_locked"]:
        penalty_pct = 0.03 if target_dep["tier_id"] == "skuf" else 0.10
        penalty_val = round(target_dep["principal"] * penalty_pct, 2)
        payout_val = round(target_dep["principal"] - penalty_val, 2)
        rem_h = int(target_dep["remaining_lock_sec"] / 3600)
        rem_m = int((target_dep["remaining_lock_sec"] % 3600) / 60)

        warn_text = (
            f"⚠️ <b>ВНИМАНИЕ! ДОСРОЧНОЕ СНЯТИЕ ВКЛАДА #{dep_id}</b>\n\n"
            f"Тариф: <b>{target_dep['tier_name']}</b>\n"
            f"Вклад заблокирован еще на <b>{rem_h}ч {rem_m}м</b>.\n\n"
            f"При досрочном выводе:\n"
            f"• Сгорят ВСЕ начисленные проценты: <b>+{target_dep['accrued_interest']:,.2f} ₪</b>\n"
            f"• Штраф ({int(penalty_pct*100)}%): <b>-{penalty_val:,.2f} ₪</b>\n"
            f"• Вы получите на руки: <b>{payout_val:,.2f} ₪</b>\n\n"
            f"Вы действительно хотите сорвать вклад?"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⚠️ Да, снять со штрафом", callback_data=f"bank_withdraw_confirm:{dep_id}")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="bank_withdraw_menu")],
        ])
        await _render_bank_view(callback, warn_text, kb, category="wallet")
        await callback.answer()
        return

    # Разблокированный депозит — выводим
    ok, payout, principal, interest, fee, is_default, err = await withdraw_bank_deposit(db, dep_id, user_id, b_id)
    if not ok:
        await callback.answer(f"❌ {err}", show_alert=True)
        return

    default_note = "\n🚨 <b>ОБЛАВА ОБЭП!</b> 50% суммы конфисковано в пользу государства." if is_default else ""
    resp = (
        f"💵 <b>ВЫВОД ИЗ БАНКА АБУ ВЫПОЛНЕН!</b>{default_note}\n\n"
        f"💰 <b>Зачислено в кошелек:</b> <code>+{payout:,.2f} ₪</code>\n"
        f"📦 <b>Тело вклада:</b> <code>{principal:,.2f} ₪</code>\n"
        f"📈 <b>Начисленные проценты:</b> <code>+{interest:,.2f} ₪</code>\n"
        f"🏛 <b>Комиссия / сбор:</b> <code>{fee:,.2f} ₪</code>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏦 В Банк Абу", callback_data="bank_main_hub")],
    ])
    await _render_bank_view(callback, resp, kb, category="wallet")
    await callback.answer("✅ Шекели зачислены в кошелек!", show_alert=False)


@bank_router.callback_query(F.data.startswith("bank_withdraw_confirm:"))
async def cb_bank_withdraw_confirm(callback: types.CallbackQuery, board_id: str | None = None):
    """Подтвержденное досрочное снятие депозита со штрафом."""
    b_id = board_id or "b"
    user_id = callback.from_user.id
    dep_id = int(callback.data.split(":", 1)[1])

    db = await get_pool()
    ok, payout, principal, interest, penalty, is_default, err = await withdraw_bank_deposit(
        db, dep_id, user_id, b_id, force_early=True
    )

    if not ok:
        await callback.answer(f"❌ {err}", show_alert=True)
        return

    resp = (
        f"⚠️ <b>ВКЛАД #{dep_id} ДОСРОЧНО ЗАКРЫТ СО ШТРАФОМ</b>\n\n"
        f"💰 <b>Выплачено на баланс:</b> <code>+{payout:,.2f} ₪</code>\n"
        f"💸 <b>Удержан штраф в Фонд Абу:</b> <code>-{penalty:,.2f} ₪</code>\n"
        f"🔥 <i>Все начисленные проценты аннулированы.</i>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏦 В Банк Абу", callback_data="bank_main_hub")],
    ])
    await _render_bank_view(callback, resp, kb, category="wallet")
    await callback.answer("✅ Досрочный вывод завершен", show_alert=False)


# -----------------------------------------------------------------------------
# Direct Chat Message Deposit Handler
# -----------------------------------------------------------------------------

@bank_router.message(PendingBankDepositFilter())
async def handle_chat_deposit_amount(
    message: types.Message,
    pending_deposit: dict,
    amount_str: str,
    detected_tier: str,
    board_id: str | None = None,
    stream: str = 'ru'
) -> None:
    """
    Обрабатывает ввод произвольной суммы сообщением прямо в чат, когда пользователь
    находится на экране оформления вклада (вместо мелких кнопок и процентов).
    """
    user_id = message.from_user.id if message.from_user else message.chat.id
    b_id = board_id or pending_deposit.get("board_id") or "b"
    db = await get_pool()

    wallet_balance = await get_user_global_balance(db, user_id)
    amount = parse_deposit_amount(amount_str, wallet_balance)

    canon_tier = normalize_tier_id(detected_tier) or pending_deposit.get("tier_id") or "sych"
    tier_info = BANK_TIERS.get(canon_tier, BANK_TIERS["sych"])

    if amount is None or amount <= 0:
        await message.answer(
            "❌ <b>Неверный формат суммы вклада.</b>\n"
            "Напиши число (например: <code>50000</code> или <code>25k</code>) или выбери готовую кнопку с процентом.",
            parse_mode="HTML"
        )
        return

    if amount > wallet_balance:
        await message.answer(
            f"❌ <b>Недостаточно средств в кошельке!</b>\n\n"
            f"💵 Запрошено внести: <code>{amount:,.2f} ₪</code>\n"
            f"💰 Доступно в кошельке: <code>{wallet_balance:,.2f} ₪</code>\n\n"
            f"<i>Напиши меньшую сумму или отправь <code>все</code> для внесения всего остатка.</i>",
            parse_mode="HTML"
        )
        return

    if amount < tier_info["min_deposit"]:
        await message.answer(
            f"❌ <b>Сумма меньше минимального депозита!</b>\n\n"
            f"💵 Минимальный вклад для тарифа <b>{tier_info['name']}</b>: <code>{tier_info['min_deposit']:,.0f} ₪</code>\n"
            f"Ты указал: <code>{amount:,.2f} ₪</code>",
            parse_mode="HTML"
        )
        return

    ok, dep, err = await create_bank_deposit(db, user_id, b_id, canon_tier, amount)

    if not ok:
        await message.answer(f"❌ <b>Ошибка оформления вклада:</b> {err}", parse_mode="HTML")
        return

    clear_user_pending_deposit(user_id)

    resp = (
        f"🎉 <b>ВКЛАД УСПЕШНО ОФОРМЛЕН!</b>\n\n"
        f"🏦 <b>Тариф:</b> {tier_info['name']}\n"
        f"💵 <b>Внесено:</b> <code>{dep['principal']:,.2f} ₪</code>\n"
        f"📈 <b>Доходность:</b> <code>{tier_info['daily_rate'] * 100:.1f}% в сутки</code>\n"
        f"🛡️ <i>Шекели изолированы в сейфе и защищены от грабежей (/rob)!</i>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏦 В Банк Абу", callback_data="bank_main_hub")],
    ])
    await message.answer(resp, reply_markup=kb, parse_mode="HTML")

