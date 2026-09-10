# -*- coding: utf-8 -*-
"""
whale_economy_engine.py
Milestone 3: Whale Money Sinks & Currency Dilution
- F3.1: High-Level Whale Safes with exponential daily pricing P(n) = 50,000 * 1.5^n and 70% burn to Abu Yacht Fund.
- F3.2: Atomic Auction System (Auctions & AuctionBids) with escrow deduction, instant outbid refund, and anti-sniping.
- F3.3: Super-Wealth Tax (progressive brackets + idle surcharge) and Class Wars (/raid_oligarch).
"""

import asyncio
import json
import math
import random
import time
from typing import Any, Dict, List, Optional, Tuple

import common.config
import common.database
import common.db_pool
from common.database import (
    add_to_abu_fund,
    add_user_global_balance,
    deduct_user_global_balance,
    get_user_global_balance,
    record_user_transaction,
)
from common.db_pool import db_lock, db_transaction


# =============================================================================
# PART 1: WHALE SAFES (F3.1)
# =============================================================================

def calculate_whale_safe_price(n: int) -> int:
    """
    Returns exponential daily price for the n-th Whale Safe:
    P(n) = int(50000 * (1.5 ** n))
    """
    if n < 0:
        n = 0
    return int(50000 * (1.5 ** n))


def roll_whale_safe(active_items: Optional[Dict[str, Any]] = None) -> Tuple[str, str, str, Dict[str, Any], int]:
    """
    Rolls a Whale Safe (Сейф Олигарха).
    Nominal RTP <= 65% <= 85%, Liquid Cash RTP <= 20%.
    P_0 = 50,000 ₪, burns 70% of case cost to abu_yacht_fund.
    Returns: (tier, title, description, payload, base_cash)
    """
    now = int(time.time())
    r = random.random()

    # Tier 4: Mythic Rewards (10% total)
    if r < 0.05:
        # 5% Mythic Status Title
        return (
            "👑 МИФИЧЕСКИЙ СТАТУС",
            "👑 Префикс «Золотой Анон» (на 30 дней)",
            "Золотое сияние ника и легендарный статус во всех тредах на 30 дней!",
            {
                "grant_title": "[👑 Золотой Анон]",
                "title_days": 30
            },
            0
        )
    elif r < 0.10:
        # 5% VIP Pin Voucher
        return (
            "📜 ИМЕННОЙ УКАЗ АБУ",
            "📌 VIP Pin Voucher (Закреп треда)",
            "Ваучер на бесплатный 24-часовой топ-пин любого треда на борде /b/!",
            {
                "vip_pin_voucher": True,
                "pin_vouchers": 1
            },
            0
        )

    # Tier 3: Prestige Gear (25% total -> r < 0.35)
    elif r < 0.225:
        # 12.5% Platinum Monocle (Face)
        is_perm = (random.random() < 0.10)
        dur_h = 0 if is_perm else 720
        title_suffix = " 🌟 [НАВСЕГДА]" if is_perm else " [на 30 дней]"
        tier_str = "🌟 ПРЕСТИЖНЫЙ ШМОТ (НАВСЕГДА)" if is_perm else "⚜️ ПРЕСТИЖНЫЙ ШМОТ (30 ДНЕЙ)"
        return (
            tier_str,
            f"⚜️ Платиновый Монокль{title_suffix}",
            "+50 к Рассудку, бейдж [⚜️ Олигарх] в заголовке постов.",
            {
                "item_id": "face_monocle",
                "is_permanent": is_perm,
                "dur_hours": dur_h,
                "slot": "face"
            },
            0
        )
    elif r < 0.35:
        # 12.5% Padishah Mantle (Torso)
        is_perm = (random.random() < 0.10)
        dur_h = 0 if is_perm else 720
        title_suffix = " 🌟 [НАВСЕГДА]" if is_perm else " [на 30 дней]"
        tier_str = "🌟 ПРЕСТИЖНЫЙ ШМОТ (НАВСЕГДА)" if is_perm else "🦹 ПРЕСТИЖНЫЙ ШМОТ (30 ДНЕЙ)"
        return (
            tier_str,
            f"🦹 Мантия Падишаха{title_suffix}",
            "+45 к Защите, 50% шанс отражения грабежей /rob.",
            {
                "item_id": "body_padishah_mantle",
                "is_permanent": is_perm,
                "dur_hours": dur_h,
                "slot": "torso"
            },
            0
        )

    # Tier 2: Elite Utility Consumables (20% total -> r < 0.55)
    elif r < 0.45:
        # 10% Diplomatic Passport (72 hours)
        return (
            "🛡️ ЭЛИТНЫЙ ИММУНИТЕТ",
            "🛡️ Дипломатический Паспорт (на 72 часа)",
            "100% дипломатический иммунитет от /shoot и /partyvan на 3 суток!",
            {
                "diplomatic_passport_until": now + 72 * 3600,
                "diplomatic_passport": True
            },
            0
        )
    elif r < 0.55:
        # 10% ОБЭП Extinguisher
        return (
            "🧯 ЭЛИТНЫЙ ПРЕДМЕТ",
            "🧯 Огнетушитель ОБЭП",
            "Однократная защита от раскулачивания и классового бунта (/raid_oligarch)!",
            {
                "extinguisher_obep": True,
                "extinguisher_obep_charges": 1
            },
            0
        )

    # Tier 1: Gold Ingot (15% -> r < 0.70)
    elif r < 0.70:
        # 15% Gold Ingot (+15,000 ₪)
        return (
            "🪙 СОКРОВИЩЕ АБУ",
            "🪙 Слиток Золота Абу (+15 000 ₪)",
            "Слиток банковского золота высшей пробы! Продано банку за +15,000 ₪.",
            {
                "gold_ingot": True
            },
            15000
        )

    # Tier 0: Dvach Troll (30% -> r >= 0.70)
    else:
        return (
            "📜 ДВАЧЕВСКИЙ ТРОЛЛИНГ",
            "📜 Сертификат Почётного Лоха (+1 ₪)",
            "Ты слил 50,000 ₪ Абу и получил эту бумажку. Сдано в макулатуру за 1 ₪.",
            {
                "certificate_sucker": True
            },
            1
        )


async def buy_whale_safe(db: Any, user_id: int, board_id: str = "b") -> Dict[str, Any]:
    """
    Purchases and opens a Whale Safe for the user.
    - Calculates price P(n) = 50000 * 1.5^n.
    - Burns 70% of case cost directly to abu_yacht_fund.
    - Applies drop rewards and handles duplicate cashback (capped at 15,000 ₪).
    """
    import lootbox_engine
    now = int(time.time())

    async with db_lock:
        async with db_transaction(db):
            # Fetch active_items
            async with db.execute(
                "SELECT active_items FROM Users WHERE user_id = ? AND board_id = ?",
                (user_id, board_id)
            ) as c:
                row = await c.fetchone()
                ai = json.loads(row[0]) if (row and row[0]) else {}

            # Check daily escalation counter reset
            reset_ts = ai.get("whale_safes_reset_ts", 0)
            if now >= reset_ts:
                ai["whale_safes_opened_today"] = 0
                ai["whale_safes_reset_ts"] = now + 86400

            n = ai.get("whale_safes_opened_today", 0)
            price = calculate_whale_safe_price(n)

            # Validate balance
            bal = await get_user_global_balance(db, user_id)
            if bal < price:
                return {
                    "ok": False,
                    "error": f"Недостаточно шекелей для Сейфа Китов #{n+1} (требуется {price:,} ₪, у тебя {int(bal):,} ₪). Цена растёт в 1.5x за каждый открытый сегодня сейф (сегодня открыто: {n}). Сброс счётчика завтра в 00:00 UTC."
                }

            # Deduct price from user
            ok, _ = await deduct_user_global_balance(db, user_id, board_id, price)
            if not ok:
                return {"ok": False, "error": "Ошибка списания средств."}
            await record_user_transaction(db, user_id, -price, 'shop', f'Покупка: Сейф Китов #{n+1}')

            # 70% burn to Abu Yacht Fund
            burn_to_abu = round(price * 0.70, 2)
            await add_to_abu_fund(db, burn_to_abu)

            # Roll safe
            tier, title, desc, payload, base_cash = roll_whale_safe(ai)

            # Apply reward
            ai, final_cash, recycle_note = lootbox_engine.apply_lootbox_reward(
                ai, payload, base_cash, case_type="whale"
            )

            # Award cashback/prize money if any
            if final_cash > 0:
                await add_user_global_balance(db, user_id, board_id, final_cash)
                await record_user_transaction(db, user_id, final_cash, 'shop', f'Награда/кешбэк: {title}')

            # Increment daily open counter
            ai["whale_safes_opened_today"] = n + 1

            # Save state
            await db.execute(
                "UPDATE Users SET active_items = ? WHERE user_id = ? AND board_id = ?",
                (json.dumps(ai), user_id, board_id)
            )

            if ai.get("custom_title") and ai.get("title_expires_at"):
                await db.execute(
                    "UPDATE Users SET custom_prefix = ?, prefix_expires_at = ? WHERE user_id = ?",
                    (ai["custom_title"], ai["title_expires_at"], user_id)
                )

    new_balance = await get_user_global_balance(db, user_id)
    return {
        "ok": True,
        "price": price,
        "burned_to_abu": burn_to_abu,
        "tier": tier,
        "title": title,
        "desc": desc,
        "final_cash": final_cash,
        "recycle_note": recycle_note,
        "new_balance": new_balance,
        "opened_today": n + 1
    }


# =============================================================================
# PART 2: ATOMIC AUCTION SYSTEM (F3.2)
# =============================================================================

async def ensure_auction_schema(db: Any):
    """Initializes auction tables and indices idempotently."""
    await db.execute("""
    CREATE TABLE IF NOT EXISTS Auctions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lot_type TEXT NOT NULL,
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        start_price REAL NOT NULL,
        min_bid_step REAL NOT NULL,
        current_bid REAL NOT NULL,
        current_winner_id INTEGER,
        current_winner_name TEXT,
        board_id TEXT NOT NULL DEFAULT 'b',
        status TEXT NOT NULL DEFAULT 'active',
        starts_at REAL NOT NULL,
        ends_at REAL NOT NULL,
        anti_snipe_sec INTEGER NOT NULL DEFAULT 300,
        created_at REAL NOT NULL,
        finished_at REAL
    );
    """)
    await db.execute("""
    CREATE INDEX IF NOT EXISTS idx_auctions_status_ends ON Auctions(status, ends_at);
    """)
    await db.execute("""
    CREATE TABLE IF NOT EXISTS AuctionBids (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        auction_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        bid_amount REAL NOT NULL,
        placed_at REAL NOT NULL,
        FOREIGN KEY (auction_id) REFERENCES Auctions(id) ON DELETE CASCADE
    );
    """)
    await db.execute("""
    CREATE INDEX IF NOT EXISTS idx_auction_bids_auc_time ON AuctionBids(auction_id, placed_at DESC);
    """)


async def create_auction(
    db: Any,
    lot_type: str,
    title: str,
    description: str,
    start_price: float,
    min_bid_step: float,
    duration_sec: float,
    board_id: str = "b"
) -> int:
    """
    Creates a new active auction.
    Returns auction_id.
    """
    await ensure_auction_schema(db)
    now = time.time()
    ends_at = now + duration_sec

    async with db_lock:
        async with db_transaction(db):
            cur = await db.execute("""
                INSERT INTO Auctions (
                    lot_type, title, description, start_price, min_bid_step,
                    current_bid, current_winner_id, current_winner_name,
                    board_id, status, starts_at, ends_at, anti_snipe_sec, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, ?, 'active', ?, ?, 300, ?)
            """, (
                lot_type, title, description, float(start_price), float(min_bid_step),
                float(start_price), board_id, now, ends_at, now
            ))
            return cur.lastrowid


async def place_auction_bid(
    db: Any,
    auction_id: int,
    user_id: int,
    user_name: str,
    bid_amount: float,
    board_id: str = "b"
) -> Dict[str, Any]:
    """
    Places an auction bid under strict atomic locking and transactions.
    - Validates: bid_amount > 0, not NaN/Inf, bid_amount >= current_bid + min_bid_step.
    - Refunds previous winner 100% of their escrowed bid via add_user_global_balance.
    - Deducts bid_amount from current bidder via deduct_user_global_balance.
    - Updates current_bid, current_winner_id in Auctions and inserts record in AuctionBids.
    - Anti-sniping: If remaining time < 300s, extends ends_at by 300s.
    """
    await ensure_auction_schema(db)

    # 1. Numerical validation
    if bid_amount is None or not isinstance(bid_amount, (int, float)):
        return {"ok": False, "error": "Некорректная сумма ставки."}
    if math.isnan(bid_amount) or math.isinf(bid_amount) or bid_amount <= 0:
        return {"ok": False, "error": "Ставка должна быть положительным конечным числом."}

    now = time.time()

    async with db_lock:
        async with db_transaction(db):
            # 2. Fetch auction
            async with db.execute(
                "SELECT id, lot_type, title, start_price, min_bid_step, current_bid, current_winner_id, ends_at, status, anti_snipe_sec FROM Auctions WHERE id = ?",
                (auction_id,)
            ) as c:
                row = await c.fetchone()

            if not row:
                return {"ok": False, "error": "Аукцион не найден."}

            _, lot_type, title, start_price, min_step, cur_bid, cur_winner, ends_at, status, anti_snipe_sec = row

            if status != "active":
                return {"ok": False, "error": "Аукцион уже завершен или отменен."}

            if now >= ends_at:
                return {"ok": False, "error": "Время аукциона истекло."}

            # Required minimum bid
            if cur_winner is None:
                min_required = max(start_price, cur_bid)
            else:
                min_required = cur_bid + min_step

            if bid_amount < min_required:
                return {
                    "ok": False,
                    "error": f"Слишком маленькая ставка! Минимальная ставка: {min_required:,} ₪ (шаг: +{min_step:,} ₪)."
                }

            if cur_winner == user_id:
                return {"ok": False, "error": "Твоя ставка уже наивысшая!"}

            # Check user balance
            user_bal = await get_user_global_balance(db, user_id)
            if user_bal < bid_amount:
                return {
                    "ok": False,
                    "error": f"Недостаточно шекелей для ставки! Требуется {bid_amount:,} ₪, у тебя {int(user_bal):,} ₪."
                }

            # 3. Refund previous winner 100% of their escrowed bid
            if cur_winner is not None and cur_bid > 0:
                await add_user_global_balance(db, cur_winner, board_id, cur_bid)
                await record_user_transaction(
                    db, cur_winner, cur_bid, 'auction_refund',
                    f'Возврат ставки на аукционе #{auction_id} ({title})'
                )

            # 4. Deduct new bid from current bidder
            ok, _ = await deduct_user_global_balance(db, user_id, board_id, bid_amount)
            if not ok:
                return {"ok": False, "error": "Ошибка списания средств с баланса."}
            await record_user_transaction(
                db, user_id, -bid_amount, 'auction',
                f'Ставка на аукционе #{auction_id} ({title})'
            )

            # 5. Anti-sniping extension
            new_ends_at = ends_at
            if ends_at - now < anti_snipe_sec:
                new_ends_at = now + anti_snipe_sec

            # 6. Update Auctions and insert AuctionBids
            await db.execute("""
                UPDATE Auctions
                SET current_bid = ?, current_winner_id = ?, current_winner_name = ?, ends_at = ?
                WHERE id = ?
            """, (bid_amount, user_id, user_name, new_ends_at, auction_id))

            await db.execute("""
                INSERT INTO AuctionBids (auction_id, user_id, bid_amount, placed_at)
                VALUES (?, ?, ?, ?)
            """, (auction_id, user_id, bid_amount, now))

    return {
        "ok": True,
        "auction_id": auction_id,
        "bid_amount": bid_amount,
        "ends_at": new_ends_at,
        "extended": (new_ends_at > ends_at),
        "previous_winner": cur_winner
    }


async def finish_active_auctions(db: Any) -> List[Dict[str, Any]]:
    """
    Checks for ended auctions, marks status = 'finished',
    burns 100% of winning bids to abu_yacht_fund, and awards rewards.
    Returns list of processed auction records.
    """
    await ensure_auction_schema(db)
    now = time.time()
    finished_list = []

    async with db_lock:
        async with db_transaction(db):
            async with db.execute("""
                SELECT id, lot_type, title, description, current_bid, current_winner_id, current_winner_name, board_id
                FROM Auctions
                WHERE status = 'active' AND ends_at <= ?
            """, (now,)) as c:
                ended_auctions = await c.fetchall()

            for row in ended_auctions:
                auc_id, lot_type, title, desc, winning_bid, winner_id, winner_name, board_id = row

                await db.execute("""
                    UPDATE Auctions SET status = 'finished', finished_at = ? WHERE id = ?
                """, (now, auc_id))

                if winner_id is not None and winning_bid > 0:
                    # 1. 100% Burn to Abu Yacht Fund
                    await add_to_abu_fund(db, winning_bid)

                    # 2. Award Reward
                    if lot_type == "custom_role":
                        # Award custom title prefix for 30 days
                        exp = int(now + 30 * 86400)
                        prefix_title = desc.strip() if desc.startswith("[") else f"[{desc.strip()}]"
                        await db.execute("""
                            UPDATE Users SET custom_prefix = ?, prefix_expires_at = ? WHERE user_id = ?
                        """, (prefix_title, exp, winner_id))

                    elif lot_type == "board_pin":
                        # Award VIP pin voucher in active_items
                        async with db.execute(
                            "SELECT active_items FROM Users WHERE user_id = ? AND board_id = ?",
                            (winner_id, board_id)
                        ) as sc:
                            srow = await sc.fetchone()
                            ai = json.loads(srow[0]) if (srow and srow[0]) else {}
                        ai["vip_pin_voucher"] = True
                        ai["pin_vouchers"] = ai.get("pin_vouchers", 0) + 1
                        await db.execute(
                            "UPDATE Users SET active_items = ? WHERE user_id = ? AND board_id = ?",
                            (json.dumps(ai), winner_id, board_id)
                        )

                    elif lot_type == "custom_badge":
                        # Award custom badge in active_items
                        async with db.execute(
                            "SELECT active_items FROM Users WHERE user_id = ? AND board_id = ?",
                            (winner_id, board_id)
                        ) as sc:
                            srow = await sc.fetchone()
                            ai = json.loads(srow[0]) if (srow and srow[0]) else {}
                        ai["custom_badge"] = title
                        await db.execute(
                            "UPDATE Users SET active_items = ? WHERE user_id = ? AND board_id = ?",
                            (json.dumps(ai), winner_id, board_id)
                        )

                    finished_list.append({
                        "auction_id": auc_id,
                        "lot_type": lot_type,
                        "title": title,
                        "winning_bid": winning_bid,
                        "winner_id": winner_id,
                        "winner_name": winner_name
                    })

    return finished_list


async def get_active_auctions(db: Any, board_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Returns list of active auctions.
    """
    await ensure_auction_schema(db)
    now = time.time()
    query = """
        SELECT id, lot_type, title, description, start_price, min_bid_step,
               current_bid, current_winner_id, current_winner_name,
               board_id, starts_at, ends_at, anti_snipe_sec
        FROM Auctions
        WHERE status = 'active' AND ends_at > ?
    """
    params: List[Any] = [now]
    if board_id:
        query += " AND board_id = ?"
        params.append(board_id)
    query += " ORDER BY ends_at ASC"

    async with db_lock:
        async with db.execute(query, tuple(params)) as c:
            rows = await c.fetchall()

    auctions = []
    for r in rows:
        auctions.append({
            "id": r[0],
            "lot_type": r[1],
            "title": r[2],
            "description": r[3],
            "start_price": r[4],
            "min_bid_step": r[5],
            "current_bid": r[6],
            "current_winner_id": r[7],
            "current_winner_name": r[8],
            "board_id": r[9],
            "starts_at": r[10],
            "ends_at": r[11],
            "anti_snipe_sec": r[12],
            "time_left": max(0, int(r[11] - now)),
        })
    return auctions


# =============================================================================
# PART 3: SUPER-WEALTH TAX & CLASS WARS (F3.3)
# =============================================================================

def calculate_wealth_tax(balance: float, idle_hours: float = 0.0) -> float:
    """
    Progressive super-wealth tax with idle surcharge:
    - <= 5,000 ₪: 0%
    - 5,001 - 50,000 ₪: 0.3% / day
    - 50,001 - 500,000 ₪: 1.0% / day
    - 500,001 - 5,000,000 ₪: 2.5% / day
    - > 5,000,000 ₪: 5.0% / day
    - Idle surcharge: 1.5x multiplier if balance > 500,000 and idle_hours >= 72.0.
    """
    if not isinstance(balance, (int, float)) or balance <= 5000:
        return 0.0

    if balance <= 50000:
        rate = 0.003
    elif balance <= 500000:
        rate = 0.010
    elif balance <= 5000000:
        rate = 0.025
    else:
        rate = 0.050

    if balance > 500000 and idle_hours >= 72.0:
        rate *= 1.5

    return round(balance * rate, 2)


async def process_daily_wealth_tax(db: Any) -> Dict[str, Any]:
    """
    Runs daily across all users with balance > 5,000 ₪.
    Calculates tax with idle hours assessment, deducts from user global balance,
    and transfers 100% of collected tax to abu_yacht_fund.
    """
    now = time.time()
    affected_count = 0
    total_tax_collected = 0.0
    details = []

    async with db_lock:
        async with db_transaction(db):
            # Fetch users with balance > 5000
            async with db.execute("""
                SELECT user_id, SUM(balance) as total_bal
                FROM Users
                GROUP BY user_id
                HAVING total_bal > 5000
            """) as c:
                rich_users = await c.fetchall()

            for row in rich_users:
                uid = row[0]
                bal = float(row[1] or 0.0)

                # Check idle hours from Posts table if available
                idle_hours = 0.0
                try:
                    async with db.execute(
                        "SELECT MAX(timestamp) FROM Posts WHERE author_id = ?",
                        (uid,)
                    ) as pc:
                        p_row = await pc.fetchone()
                        if p_row and p_row[0]:
                            idle_hours = max(0.0, (now - float(p_row[0])) / 3600.0)
                        else:
                            idle_hours = 100.0  # Inactive user with 0 posts
                except Exception:
                    idle_hours = 0.0

                tax = calculate_wealth_tax(bal, idle_hours=idle_hours)
                if tax <= 0:
                    continue

                ok, _ = await deduct_user_global_balance(db, uid, "b", tax)
                if ok:
                    affected_count += 1
                    total_tax_collected += tax
                    await record_user_transaction(
                        db, uid, -tax, 'tax',
                        f'Налог Абу на богатство ({tax:,} ₪)'
                    )
                    details.append({"user_id": uid, "tax": tax, "balance_before": bal})

            if total_tax_collected > 0:
                await add_to_abu_fund(db, total_tax_collected)

    return {
        "affected_users": affected_count,
        "total_tax_collected": total_tax_collected,
        "details": details
    }


async def execute_oligarch_raid(
    db: Any,
    voter_ids: List[int],
    target_id: Optional[int] = None,
    board_id: str = "b"
) -> Dict[str, Any]:
    """
    Executes a collaborative proletarian raid (/raid_oligarch).
    - Requires exactly 5 qualified proletarian voters (balance < 5,000 ₪, posts >= 25).
    - Identifies top oligarch (highest balance) if target_id not specified.
    - Checks oligarch defensive gear (extinguisher_obep / diplomatic_passport).
    - Confiscates 10% of target balance (capped at 200,000 ₪).
    - Burns 70% to abu_yacht_fund, distributes remaining 30% equally among the 5 proletarian voters.
    - Sterilizes money from M0 permanently.
    """
    now = time.time()

    # 1. Validate qualified proletarian voters
    unique_voters = list(dict.fromkeys(voter_ids))
    qualified_voters = []

    for vid in unique_voters:
        bal = await get_user_global_balance(db, vid)
        # Check posts count from Users table
        async with db.execute(
            "SELECT COALESCE(MAX(posts_count), 0) FROM Users WHERE user_id = ?",
            (vid,)
        ) as c:
            p_row = await c.fetchone()
            posts = p_row[0] if p_row else 0

        # Fallback to Posts table count if Users.posts_count is not populated
        if posts < 25:
            try:
                async with db.execute(
                    "SELECT COUNT(*) FROM Posts WHERE author_id = ?",
                    (vid,)
                ) as pc:
                    pc_row = await pc.fetchone()
                    posts = max(posts, pc_row[0] if pc_row else 0)
            except Exception:
                pass

        if bal < 5000 and posts >= 25:
            qualified_voters.append(vid)

    if len(qualified_voters) < 5:
        return {
            "ok": False,
            "error": f"Недостаточно квалифицированных рабочих! Требуется 5 пролетариев (баланс < 5,000 ₪, постов >= 25), собрано: {len(qualified_voters)}."
        }

    # Select exactly 5 qualified voters
    selected_5_workers = qualified_voters[:5]

    async with db_lock:
        async with db_transaction(db):
            # 2. Identify target oligarch
            if target_id is None:
                async with db.execute("""
                    SELECT user_id, SUM(balance) as total_bal
                    FROM Users
                    GROUP BY user_id
                    ORDER BY total_bal DESC
                    LIMIT 1
                """) as c:
                    top_row = await c.fetchone()
                    if not top_row or (top_row[1] or 0.0) <= 5000:
                        return {"ok": False, "error": "На борде нет олигархов для раскулачивания!"}
                    target_id = top_row[0]

            oligarch_bal = await get_user_global_balance(db, target_id)
            if oligarch_bal <= 5000:
                return {"ok": False, "error": "Цель не является олигархом (баланс <= 5 000 ₪)."}

            # 3. Check target defensive gear in active_items
            async with db.execute(
                "SELECT active_items FROM Users WHERE user_id = ? AND board_id = ?",
                (target_id, board_id)
            ) as c:
                row = await c.fetchone()
                ai = json.loads(row[0]) if (row and row[0]) else {}

            # Defense A: Diplomatic Passport (blocks raid completely)
            if ai.get("diplomatic_passport_until", 0) > now or ai.get("diplomatic_passport"):
                return {
                    "ok": False,
                    "blocked": True,
                    "error": "🛡️ Олигарх предъявил Дипломатический Паспорт! Рейд ОБЭП заблокирован дипломатическим иммунитетом."
                }

            # Defense B: ОБЭП Extinguisher (consumes 1 charge and blocks raid)
            if ai.get("extinguisher_obep"):
                charges = ai.get("extinguisher_obep_charges", 1) - 1
                if charges <= 0:
                    ai.pop("extinguisher_obep", None)
                    ai.pop("extinguisher_obep_charges", None)
                else:
                    ai["extinguisher_obep_charges"] = charges

                await db.execute(
                    "UPDATE Users SET active_items = ? WHERE user_id = ? AND board_id = ?",
                    (json.dumps(ai), target_id, board_id)
                )
                return {
                    "ok": False,
                    "blocked": True,
                    "error": "🧯 Олигарх применил Огнетушитель ОБЭП! Раскулачивание успешно потушено, заряд огнетушителя израсходован."
                }

            # 4. Confiscation calculations (10% capped at 200,000 ₪)
            confiscated = min(round(oligarch_bal * 0.10, 2), 200000.0)
            burn_to_abu = round(confiscated * 0.70, 2)
            distribute_total = round(confiscated * 0.30, 2)
            per_worker = round(distribute_total / 5.0, 2)

            # Deduct from oligarch
            ok, _ = await deduct_user_global_balance(db, target_id, board_id, confiscated)
            if not ok:
                return {"ok": False, "error": "Ошибка списания средств у олигарха."}

            await record_user_transaction(
                db, target_id, -confiscated, 'confiscation',
                f'Раскулачивание ОБЭП (/raid_oligarch) работягами'
            )

            # 70% Burn to Abu Yacht Fund
            await add_to_abu_fund(db, burn_to_abu)

            # 30% Distribute equally to the 5 workers
            for vid in selected_5_workers:
                await add_user_global_balance(db, vid, board_id, per_worker)
                await record_user_transaction(
                    db, vid, per_worker, 'raid_reward',
                    f'Доля от раскулачивания олигарха #{target_id} (/raid_oligarch)'
                )

    return {
        "ok": True,
        "target_id": target_id,
        "confiscated": confiscated,
        "burned_to_abu": burn_to_abu,
        "distributed_total": distribute_total,
        "per_voter": per_worker,
        "voters": selected_5_workers
    }
