# -*- coding: utf-8 -*-
"""
dice_duel_engine.py — High-Performance PvP Dice Duel (Кости / Дайс-Дуэль на Шекели) for ТГАЧ
=============================================================================================
Features:
- Pure Custom Fair 2d6 / 3d6 RNG Engine (NO native Telegram send_dice!).
- Authentic Unicode dice faces: ⚀ ⚁ ⚂ ⚃ ⚄ ⚅ with combo detection (Doubles, Triples, Snake Eyes, etc.).
- Animated suspenseful rolling frames with round-by-round and sudden-death overtime support.
- Full Escrow balance integration with atomic database locks and transaction logging.
- Authentic 2ch imageboard broadcast via process_new_post with greentext and payout notices.
- Deep integration into /casino, /duel, and /help menus with interactive inline lobbies.
"""

import time
import asyncio
import random
import secrets
from typing import Dict, Optional, Tuple, Any, List
from aiogram import types, F, Dispatcher, Router
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

import shared_state
from common.db_pool import get_pool, db_lock
from common.database import (
    get_user_global_balance,
    add_user_global_balance,
    deduct_user_global_balance,
    add_to_abu_fund,
    record_user_transaction
)
from common.anon_identity import get_anon_id

# -----------------------------------------------------------------------------
# Configuration Constants
# -----------------------------------------------------------------------------
MIN_DICE_BET = 50
MAX_DICE_BET = 50_000_000
DICE_CHALLENGE_TIMEOUT_SEC = 120.0
DICE_TURN_TIMEOUT_SEC = 45.0
DICE_RAKE_PERCENT = 0.05  # 5% house rake to Abu fund
DICE_TIE_RAKE_PERCENT = 0.02  # 2% nominal rake on tied refund

# Unicode Dice Glyphs
DICE_GLYPHS = {
    1: "⚀",
    2: "⚁",
    3: "⚂",
    4: "⚃",
    5: "⚄",
    6: "⚅"
}

# -----------------------------------------------------------------------------
# In-Memory State & Concurrency Locks
# -----------------------------------------------------------------------------
active_dice_games: Dict[str, Dict[str, Any]] = {}
user_active_dice_game: Dict[int, str] = {}
dice_engine_lock = asyncio.Lock()


# -----------------------------------------------------------------------------
# Core Dice Mathematics & RNG Logic
# -----------------------------------------------------------------------------
def generate_game_id() -> str:
    """Generates a unique identifier for a dice duel session."""
    return f"dice_{int(time.time()*1000)}_{secrets.randbelow(900) + 100}"


def roll_single_die() -> int:
    """Cryptographically secure single 6-sided die roll (1-6)."""
    return secrets.randbelow(6) + 1


def roll_dice_set(num_dice: int = 2) -> List[int]:
    """Rolls N fair 6-sided dice."""
    return [roll_single_die() for _ in range(num_dice)]


def format_dice_visual(dice: List[int]) -> str:
    """Formats list of dice values into unicode representation: [ ⚄ ⚅ ] (11)."""
    if not dice:
        return "[ 🎲 🎲 ]"
    glyphs = " ".join(DICE_GLYPHS.get(d, "🎲") for d in dice)
    total = sum(dice)
    return f"<b>[ {glyphs} ]</b> (<code>{total}</code>)"


def evaluate_roll_combo(dice: List[int]) -> Tuple[int, str, str]:
    """
    Evaluates dice roll score and flavor combo commentary.
    Returns: (total_score, combo_title, flavor_desc)
    """
    if not dice:
        return 0, "Пусто", "Кости не брошены"
    total = sum(dice)
    n = len(dice)

    if n == 2:
        d1, d2 = dice[0], dice[1]
        if d1 == d2 == 6:
            return total, "👑 ДУБЛЬ ШЕСТЁРОК (12)", "Абсолютный куш! Чистая база и максимальный разнос!"
        if d1 == d2 == 1:
            return total, "🐍 ЗМЕИНЫЕ ГЛАЗКИ (2)", "Критический фейл! Глаза змеи смотрят прямо в душу сыча."
        if d1 == d2:
            return total, f"🎲 ДУБЛЬ ({d1}+{d2})", f"Синхронный дубль на {DICE_GLYPHS.get(d1, '')}! Удача благоволит."
        if total == 11:
            return total, "🔥 ПОЧТИ МАКСИМУМ (11)", "Мощнейший бросок, кости раскалились докрасна!"
        if total == 3:
            return total, "💩 ПОДЛИВА (3)", "Хуже некуда, одна нога на параше."
        if total >= 8:
            return total, f"✨ ХОРОШИЙ БРОСОК ({total})", "Уверенная сумма очков на сукне."
        return total, f"🎲 ОБЫЧНЫЙ БРОСОК ({total})", "Рядовой результат в подпольной костильне."

    elif n == 3:
        if dice[0] == dice[1] == dice[2] == 6:
            return total, "👑 ТРИ ШЕСТЁРКИ (18)", "ДЬЯВОЛЬСКИЙ ТРИПЛ! Казна Абу трещит по швам!"
        if dice[0] == dice[1] == dice[2] == 1:
            return total, "💀 ТРИ ЕДИНИЦЫ (3)", "Тотальное фиаско! Судьба втоптала в грязь."
        if len(set(dice)) == 1:
            return total, f"💎 ТРИПЛ НА {dice[0]} ({total})", "Редчайшая комбинация трех одинаковых костей!"
        if total >= 15:
            return total, f"🔥 БОЛЬШОЙ КУШ ({total})", "Сокрушительный результат 3d6!"
        if total <= 6:
            return total, f"💩 НИЗКИЙ БРОСОК ({total})", "Грустная сумма, пахнет проигрышем."
        return total, f"🎲 СУММА 3d6 ({total})", "Кости легли как предначертано."

    return total, f"🎲 СУММА ({total})", "Результат зафиксирован."


# -----------------------------------------------------------------------------
# Keyboards & Interactive UI Components
# -----------------------------------------------------------------------------
def get_dice_challenge_keyboard(game_id: str) -> InlineKeyboardMarkup:
    """Keyboard attached to the public challenge message."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⚔️ Принять вызов на кости!", callback_data=f"dice_accept:{game_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"dice_decline:{game_id}")
        ]
    ])


def get_dice_roll_keyboard(game_id: str, active_player_id: int) -> InlineKeyboardMarkup:
    """Keyboard displayed during active rolling turns."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🎲 Бросить кости!", callback_data=f"dice_roll:{game_id}")
        ],
        [
            InlineKeyboardButton(text="🏳️ Сдаться", callback_data=f"dice_surrender:{game_id}")
        ]
    ])


def get_dice_finished_keyboard(game_id: str, bet: int) -> InlineKeyboardMarkup:
    """Keyboard displayed when a game finishes."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=f"🔄 Реванш ({bet:,} ₪)", callback_data=f"dice_rematch:{game_id}"),
            InlineKeyboardButton(text="🎰 Меню Казино", callback_data="cas:hub")
        ]
    ])


def format_dice_bet_amount(amount: int) -> str:
    if amount >= 1_000_000:
        if amount % 1_000_000 == 0:
            return f"{amount // 1_000_000}M ₪"
        return f"{amount / 1_000_000:.1f}M ₪"
    elif amount >= 1000:
        if amount % 1000 == 0:
            return f"{amount // 1000}k ₪"
        return f"{amount / 1000:.1f}k ₪"
    return f"{amount} ₪"


def get_adaptive_dice_bet_presets(balance: int, current_bet: int = 100) -> List[int]:
    """Generates affordable bet presets based on player's current balance."""
    ALL_PRESETS = [50, 100, 250, 500, 1000, 2500, 5000, 10000, 25000, 50000, 100000, 250000, 500000, 1000000]
    eff_bal = max(0, int(balance))
    if eff_bal < MIN_DICE_BET:
        return [MIN_DICE_BET]
    affordable = [p for p in ALL_PRESETS if p <= eff_bal and p <= MAX_DICE_BET]
    if not affordable:
        return [max(MIN_DICE_BET, min(eff_bal, MAX_DICE_BET))]
    if len(affordable) <= 5:
        return affordable
    indices = [0, len(affordable) // 4, len(affordable) // 2, (len(affordable) * 3) // 4, len(affordable) - 1]
    return sorted(list(set(affordable[i] for i in indices)))


def get_dice_lobby_keyboard(balance: int = 1000, current_bet: int = 100, target_id: int = 0) -> InlineKeyboardMarkup:
    """Interactive quick lobby keyboard for /casino or /duel menu."""
    current_bet = max(MIN_DICE_BET, min(MAX_DICE_BET, current_bet))
    presets = get_adaptive_dice_bet_presets(balance, current_bet)
    t_tag = f":{target_id}" if target_id else ":0"
    preset_row = [
        InlineKeyboardButton(text=format_dice_bet_amount(p), callback_data=f"dice_lobby_bet:{p}{t_tag}")
        for p in presets
    ]

    half_bet = max(MIN_DICE_BET, current_bet // 2)
    double_bet = min(MAX_DICE_BET, min(int(balance), current_bet * 2)) if balance >= current_bet * 2 else current_bet
    max_bet = max(MIN_DICE_BET, min(MAX_DICE_BET, int(balance)))
    ctrl_row = [
        InlineKeyboardButton(text="/2", callback_data=f"dice_lobby_bet:{half_bet}{t_tag}"),
        InlineKeyboardButton(text="x2", callback_data=f"dice_lobby_bet:{double_bet}{t_tag}"),
        InlineKeyboardButton(text="💰 ВА-БАНК", callback_data=f"dice_lobby_bet:{max_bet}{t_tag}"),
    ]

    buttons = [
        [
            InlineKeyboardButton(text=f"🎲 Дуэль 2d6 ({format_dice_bet_amount(current_bet)})", callback_data=f"dice_create_fast:2d6:{current_bet}{t_tag}"),
            InlineKeyboardButton(text=f"🔥 Дуэль 3d6 ({format_dice_bet_amount(current_bet)})", callback_data=f"dice_create_fast:3d6:{current_bet}{t_tag}")
        ],
        preset_row,
        ctrl_row,
        [
            InlineKeyboardButton(text="⚔️ Меню Дуэлей (/duel)", callback_data="menu_duel"),
            InlineKeyboardButton(text="🔙 Меню Казино", callback_data="cas:hub")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# -----------------------------------------------------------------------------
# Public Board Broadcast via process_new_post
# -----------------------------------------------------------------------------
async def broadcast_dice_announcement(bot, board_id: str, text: str):
    """
    Asynchronously broadcasts finished duel outcome to the board feed via process_new_post.
    """
    try:
        from post_processor import process_new_post
        import shared_state
        params = shared_state.NewPostParams(
            bot_instance=bot,
            board_id=board_id,
            user_id=0,
            content={'type': 'text', 'text': text, 'is_system_message': True, 'archive_allowed': True},
            reply_to_post=None,
            is_shadow_muted=False,
            stream='ru'
        )
        await process_new_post(params)
    except Exception as e:
        shared_state.runtime_logger.warning(f"Failed to broadcast dice duel post: {e}")


async def send_pvp_direct_notification(bot: Any, user_id: int, text: str) -> bool:
    """
    Safely sends a private notification DM to a user on Telegram with full error suppression.
    """
    if not bot or not user_id:
        return False
    try:
        await bot.send_message(
            chat_id=user_id,
            text=text,
            parse_mode="HTML"
        )
        return True
    except (TelegramForbiddenError, TelegramBadRequest) as e:
        shared_state.runtime_logger.debug(f"Direct notification suppressed for user {user_id}: {e}")
        return False
    except Exception as e:
        shared_state.runtime_logger.warning(f"Direct notification failed for user {user_id}: {e}")
        return False


# -----------------------------------------------------------------------------
# Session Lifecycle Handlers
# -----------------------------------------------------------------------------
async def create_dice_challenge(
    board_id: str,
    challenger_id: int,
    bet: int,
    target_id: Optional[int] = None,
    num_dice: int = 2
) -> Tuple[bool, str, Optional[str]]:
    """
    Creates a new PvP Dice challenge with bet escrow verification.
    """
    if bet < MIN_DICE_BET:
        return False, f"❌ Минимальная ставка в Дайс-Дуэль: <b>{MIN_DICE_BET} ₪</b>.", None
    if bet > MAX_DICE_BET:
        return False, f"❌ Максимальная ставка в Дайс-Дуэль: <b>{MAX_DICE_BET:,} ₪</b>.", None

    db = await get_pool()
    async with db_lock:
        bal = await get_user_global_balance(db, challenger_id)
    
    if bal < bet:
        return False, f"❌ Недостаточно шекелей! Ставка: <b>{bet:,} ₪</b>, на балансе: <b>{int(bal):,} ₪</b>.", None

    async with dice_engine_lock:
        if challenger_id in user_active_dice_game:
            old_gid = user_active_dice_game[challenger_id]
            if old_gid in active_dice_games and not active_dice_games[old_gid].get("finished"):
                return False, "⚠️ У тебя уже есть активная партия в кости! Заверши её или дождись таймаута.", None

        game_id = generate_game_id()
        active_dice_games[game_id] = {
            "game_id": game_id,
            "board_id": board_id,
            "player_1": challenger_id,
            "player_2": target_id,
            "target_id": target_id,
            "bet": bet,
            "num_dice": num_dice,
            "round": 1,
            "state": "pending",
            "p1_rolls": {},   # round_num -> List[int]
            "p2_rolls": {},   # round_num -> List[int]
            "current_turn": None,
            "turn_deadline_ts": time.time() + DICE_CHALLENGE_TIMEOUT_SEC,
            "created_ts": time.time(),
            "finished": False,
            "chat_id": None,
            "msg_id": None
        }
        user_active_dice_game[challenger_id] = game_id

    return True, "✅ Вызов на кости создан!", game_id


async def accept_dice_challenge(
    game_id: str,
    acceptor_id: int
) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """
    Accepts pending challenge, performs atomic escrow deduction for both players,
    and initializes the first rolling turn.
    """
    async with dice_engine_lock:
        game = active_dice_games.get(game_id)
        if not game:
            return False, "❌ Игра не найдена или время вызова истекло.", None
        if game["state"] not in ("pending",):
            return False, "❌ Этот вызов уже принят или закрыт!", None
        if game["player_1"] == acceptor_id:
            return False, "❌ Нельзя играть в кости с самим собой, шизофреник.", None
        if game.get("target_id") and game["target_id"] != acceptor_id:
            return False, "❌ Этот вызов адресован персонально другому анону!", None
        # Prevent acceptor from joining two games simultaneously
        existing_gid = user_active_dice_game.get(acceptor_id)
        if existing_gid and existing_gid in active_dice_games and not active_dice_games[existing_gid].get("finished"):
            return False, "⚠️ У тебя уже есть активная партия в кости! Заверши её или дождись таймаута.", None

        bet = game["bet"]
        board_id = game["board_id"]
        challenger_id = game["player_1"]
        # Mark 'accepting' immediately to prevent double-accept race condition
        game["state"] = "accepting"

    def _rollback_state():
        g = active_dice_games.get(game_id)
        if g and g.get("state") == "accepting":
            g["state"] = "pending"

    db = await get_pool()
    async with db_lock:
        bal_c = await get_user_global_balance(db, challenger_id)
        bal_a = await get_user_global_balance(db, acceptor_id)

        if bal_c < bet:
            async with dice_engine_lock: _rollback_state()
            return False, "❌ У создателя вызова уже не хватает шекелей на балансе!", None
        if bal_a < bet:
            async with dice_engine_lock: _rollback_state()
            return False, f"❌ У тебя не хватает шекелей! Ставка: <b>{bet:,} ₪</b>, твой баланс: <b>{int(bal_a):,} ₪</b>.", None

        # Atomic Escrow deduction with safe rollback
        ok_c, _ = await deduct_user_global_balance(db, challenger_id, board_id, bet)
        ok_a, _ = await deduct_user_global_balance(db, acceptor_id, board_id, bet)

        if not (ok_c and ok_a):
            if ok_c:
                await add_user_global_balance(db, challenger_id, board_id, bet)
            if ok_a:
                await add_user_global_balance(db, acceptor_id, board_id, bet)
            async with dice_engine_lock: _rollback_state()
            return False, "❌ Ошибка списания средств. У одного из игроков изменился баланс.", None

        await record_user_transaction(db, challenger_id, -bet, 'dice_duel', f'Ставка в Дайс-Дуэль #{game_id}')
        await record_user_transaction(db, acceptor_id, -bet, 'dice_duel', f'Ставка в Дайс-Дуэль #{game_id}')

    async with dice_engine_lock:
        game["player_2"] = acceptor_id
        game["state"] = "playing"
        # First turn is randomized
        game["current_turn"] = challenger_id if secrets.randbelow(2) == 0 else acceptor_id
        game["turn_deadline_ts"] = time.time() + DICE_TURN_TIMEOUT_SEC
        user_active_dice_game[acceptor_id] = game_id

    return True, "✅ Вызов принят! Кости на столе!", game


async def cancel_dice_challenge(
    game_id: str,
    user_id: int,
    bot: Any = None
) -> Tuple[bool, str]:
    """Cancels a pending challenge before it is accepted."""
    async with dice_engine_lock:
        game = active_dice_games.get(game_id)
        if not game:
            return False, "❌ Вызов не найден."
        if game["state"] != "pending":
            return False, "❌ Нельзя отменить уже начавшуюся дуэль!"
        if user_id != game["player_1"] and (not game.get("target_id") or user_id != game.get("target_id")):
            return False, "❌ Только участники вызова могут его отменить."

        p1 = game["player_1"]
        game["state"] = "cancelled"
        game["finished"] = True
        game["finished_ts"] = time.time()
        user_active_dice_game.pop(game["player_1"], None)
        if game.get("target_id"):
            user_active_dice_game.pop(game["target_id"], None)

    if user_id == p1:
        return True, "🗑 Вызов успешно отменен."
    else:
        if bot and p1:
            dec_dm = (
                f"⚔️ <b>ВЫЗОВ НА PvP ДАЙС-ДУЭЛЬ ОТКЛОНЕН</b>\n\n"
                f"Анон [ID:{get_anon_id(user_id)}] отклонил твой вызов на кости."
            )
            asyncio.create_task(send_pvp_direct_notification(bot, p1, dec_dm))
        return True, f"❌ Вызов на дуэль отклонен Аноном [ID:{get_anon_id(user_id)}]."


# -----------------------------------------------------------------------------
# Rolling & Animated Execution Engine
# -----------------------------------------------------------------------------
async def execute_player_roll(
    game_id: str,
    user_id: int,
    bot: Any
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Executes a dice roll for the active player with animated suspense,
    advances the turn or resolves the game if both rolled.
    """
    current_round = None
    resolve_round = False

    async with dice_engine_lock:
        game = active_dice_games.get(game_id)
        if not game:
            return False, "❌ Партия не найдена.", {}
        if game.get("finished"):
            return False, "❌ Игра уже завершена.", game
        if game["state"] not in ("playing", "rolling"):
            return False, "❌ Игра не готова к броску.", game
        if user_id not in (game["player_1"], game["player_2"]):
            return False, "❌ Ты не участвуешь в этой дуэли!", game
        if user_id != game.get("current_turn"):
            return False, "⏳ Сейчас ход твоего соперника! Жди броска.", game

        current_round = game["round"]
        num_dice = game.get("num_dice", 2)
        rolled_values = roll_dice_set(num_dice)

        if user_id == game["player_1"]:
            game["p1_rolls"][current_round] = rolled_values
        else:
            game["p2_rolls"][current_round] = rolled_values

        p1_done = current_round in game["p1_rolls"]
        p2_done = current_round in game["p2_rolls"]

        other_player = game["player_2"] if user_id == game["player_1"] else game["player_1"]

        if not (p1_done and p2_done):
            # Advance turn to the second player
            game["state"] = "playing"
            game["current_turn"] = other_player
            game["turn_deadline_ts"] = time.time() + DICE_TURN_TIMEOUT_SEC
            return True, "✅ Бросок зафиксирован! Ход переходит к сопернику.", game

        # If both players have completed the current round, transition state to resolving
        game["state"] = "resolving"
        resolve_round = True

    if resolve_round:
        return await _evaluate_and_finish_round(game_id, current_round, bot)

    return True, "✅ Бросок зафиксирован!", game


async def _evaluate_and_finish_round(
    game_id: str,
    round_num: int,
    bot: Any
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Compares roll scores for the current round. Triggers sudden death overtime if tied,
    or finalizes the game with payouts.
    """
    async with dice_engine_lock:
        game = active_dice_games.get(game_id)
        if not game:
            return False, "❌ Игра не найдена.", {}
        if game.get("finished"):
            return False, "❌ Игра уже завершена.", game

        p1 = game["player_1"]
        p2 = game["player_2"]
        r1 = game["p1_rolls"].get(round_num)
        r2 = game["p2_rolls"].get(round_num)

        if not r1 or not r2:
            return False, "❌ Ошибка раунда: не все броски совершены.", game

        score1, combo1, flavor1 = evaluate_roll_combo(r1)
        score2, combo2, flavor2 = evaluate_roll_combo(r2)

        # Tie Breaker / Overtime check
        if score1 == score2:
            if round_num < 3:
                game["round"] += 1
                next_round = game["round"]
                game["current_turn"] = p1 if secrets.randbelow(2) == 0 else p2
                game["turn_deadline_ts"] = time.time() + DICE_TURN_TIMEOUT_SEC
                game["state"] = "playing"
                return True, f"⚖️ <b>НИЧЬЯ В РАУНДЕ {round_num} ({score1}:{score2})!</b> Назначается овертайм (Раунд {next_round})!", game
            else:
                # Absolute max rounds tie -> Refund minus nominal tie rake
                winner_id = None
                loser_id = None
                finish_reason = "draw"
        else:
            winner_id = p1 if score1 > score2 else p2
            loser_id = p2 if score1 > score2 else p1
            finish_reason = "win"

    return await _finish_dice_game(game_id, winner_id, loser_id, finish_reason, bot)


async def _finish_dice_game(
    game_id: str,
    winner_id: Optional[int],
    loser_id: Optional[int],
    reason: str,
    bot: Any
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Finalizes dice duel, distributes winnings/refunds, pays Abu fund rake,
    sends direct user notifications, and publishes the board announcement post.
    """
    async with dice_engine_lock:
        game = active_dice_games.get(game_id)
        if not game:
            return False, "❌ Игра не найдена.", {}
        if game.get("finished"):
            return False, "❌ Игра уже завершена.", game

        game["finished"] = True
        game["state"] = "finished"
        game["finished_ts"] = time.time()
        bet = game["bet"]
        board_id = game["board_id"]
        p1 = game["player_1"]
        p2 = game["player_2"]

        user_active_dice_game.pop(p1, None)
        if p2:
            user_active_dice_game.pop(p2, None)

    db = await get_pool()

    if reason == "draw":
        rake = max(1, int(bet * DICE_TIE_RAKE_PERCENT))
        refund_amt = bet - rake
        async with db_lock:
            await add_user_global_balance(db, p1, board_id, refund_amt)
            if p2:
                await add_user_global_balance(db, p2, board_id, refund_amt)
            await add_to_abu_fund(db, rake * 2)
            await record_user_transaction(db, p1, refund_amt, 'dice_duel', f'Возврат ничьей в Кости #{game_id}')
            if p2:
                await record_user_transaction(db, p2, refund_amt, 'dice_duel', f'Возврат ничьей в Кости #{game_id}')

        game["outcome"] = "draw"
        game["payout"] = refund_amt

        draw_notify_text = (
            f"🤝 <b>НИЧЬЯ В ДАЙС-ДУЭЛИ #{game_id}</b>\n\n"
            f"💰 Твоя ставка возвращена: <b>+{refund_amt:,} ₪</b> (за вычетом 2% в Казну Абу)."
        )
        if bot:
            asyncio.create_task(send_pvp_direct_notification(bot, p1, draw_notify_text))
            if p2:
                asyncio.create_task(send_pvp_direct_notification(bot, p2, draw_notify_text))
        
        p1_anon_ann = get_anon_id(p1) if p1 else "???"
        p2_anon_ann = get_anon_id(p2) if p2 else "???"
        announcement = (
            f"🎲 <b>PvP ДАЙС-ДУЭЛЬ: МЁРТВАЯ НИЧЬЯ!</b>\n\n"
            f">кости брошены трижды, победитель не выявлен\n"
            f"⚖️ <b>Анон <code>[ID:{p1_anon_ann}]</code></b> и <b>Анон <code>[ID:{p2_anon_ann}]</code></b> сошлись на равных на <b>{bet:,} ₪</b>!\n\n"
            f"💰 Ставки возвращены анонам за вычетом 2% в Казну Абу."
        )
        if bot:
            asyncio.create_task(broadcast_dice_announcement(bot, board_id, announcement))
        return True, "🤝 Ничья в дайс-дуэли!", game

    else:
        total_pot = bet * 2
        rake = max(5, int(total_pot * DICE_RAKE_PERCENT))
        win_payout = total_pot - rake

        async with db_lock:
            if winner_id:
                await add_user_global_balance(db, winner_id, board_id, win_payout)
                await record_user_transaction(db, winner_id, win_payout, 'dice_duel', f'Выигрыш в Дайс-Дуэль #{game_id}')
            await add_to_abu_fund(db, rake)

        game["outcome"] = "win"
        game["winner"] = winner_id
        game["loser"] = loser_id
        game["payout"] = win_payout

        last_round = game["round"]
        w_rolls = game["p1_rolls"].get(last_round) if winner_id == p1 else game["p2_rolls"].get(last_round)
        l_rolls = game["p2_rolls"].get(last_round) if winner_id == p1 else game["p1_rolls"].get(last_round)

        w_vis = format_dice_visual(w_rolls) if w_rolls else "Бросок"
        l_vis = format_dice_visual(l_rolls) if l_rolls else "Фейл"
        
        winner_anon = get_anon_id(winner_id) if winner_id else "???"
        loser_anon = get_anon_id(loser_id) if loser_id else "???"

        if bot:
            if winner_id:
                win_notify_text = (
                    f"👑 <b>ПОБЕДА В ДАЙС-ДУЭЛИ #{game_id}!</b>\n\n"
                    f"💰 Твой чистый выигрыш: <b>+{win_payout:,} ₪</b> зачислен на баланс!"
                )
                asyncio.create_task(send_pvp_direct_notification(bot, winner_id, win_notify_text))
            if loser_id:
                if reason == "timeout":
                    lose_reason_str = "Таймаут броска (45 сек)"
                elif reason == "surrender":
                    lose_reason_str = "Капитуляция"
                else:
                    lose_reason_str = "Меньшая сумма очков на костях"
                lose_notify_text = (
                    f"💀 <b>ПОРАЖЕНИЕ В ДАЙС-ДУЭЛИ #{game_id}</b>\n\n"
                    f"Причина: {lose_reason_str}.\n"
                    f"💸 Списано: <b>-{bet:,} ₪</b>."
                )
                asyncio.create_task(send_pvp_direct_notification(bot, loser_id, lose_notify_text))

        if reason == "timeout":
            announcement = (
                f"⏱️ <b>PvP ДАЙС-ДУЭЛЬ: ТЕХНИЧЕСКИЙ НОКАУТ!</b>\n\n"
                f">сыч испугался бросать кости и убежал в слезах\n"
                f"😴 Анон <code>[ID:{loser_anon}]</code> пропустил таймер хода (45 сек)!\n"
                f"👑 <b>Победитель:</b> Анон <code>[ID:{winner_anon}]</code> забирает весь банк <b>+{win_payout:,} ₪</b>!\n"
                f"🐒 Налог Абу: <code>{rake:,} ₪</code>"
            )
        elif reason == "surrender":
            announcement = (
                f"🏳️ <b>PvP ДАЙС-ДУЭЛЬ: КАПИТУЛЯЦИЯ!</b>\n\n"
                f">выкинул белый флаг прямо на игровое сукно\n"
                f"👑 <b>Победитель:</b> Анон <code>[ID:{winner_anon}]</code>\n"
                f"💰 Выигрыш: <b>+{win_payout:,} ₪</b> (Ставка: {bet:,} ₪)."
            )
        else:
            w_score, w_combo, w_flavor = evaluate_roll_combo(w_rolls) if w_rolls else (0, "", "")
            l_score, l_combo, l_flavor = evaluate_roll_combo(l_rolls) if l_rolls else (0, "", "")
            announcement = (
                f"🎲 <b>PvP ДАЙС-ДУЭЛЬ: РАЗНОС НА КОСТЯХ!</b>\n\n"
                f">сошлись два анона на сукне у параши\n"
                f">кости брошены, удача улыбнулась сильнейшему\n\n"
                f"👑 <b>Победитель:</b> Анон <code>[ID:{winner_anon}]</code>\n"
                f"🎲 Выкинул: {w_vis} — <i>{w_combo}</i>\n\n"
                f"💀 <b>Проигравший:</b> Анон <code>[ID:{loser_anon}]</code>\n"
                f"🎲 Выкинул: {l_vis} — <i>{l_combo}</i>\n\n"
                f"💰 <b>Банк игры:</b> <code>{total_pot:,} ₪</code>\n"
                f"🏆 <b>Чистый выигрыш:</b> <code>+{win_payout:,} ₪</code> отправлен чемпиону!\n"
                f"🐒 <b>Налог Абу (5%):</b> <code>{rake:,} ₪</code>"
            )

        if bot:
            asyncio.create_task(broadcast_dice_announcement(bot, board_id, announcement))
        return True, "👑 Победа в дайс-дуэли!", game


# -----------------------------------------------------------------------------
# Message Formatters & UI Presentation
# -----------------------------------------------------------------------------
def format_dice_game_message(game: Dict[str, Any]) -> str:
    """Formats live duel status message for Telegram chat."""
    p1 = game["player_1"]
    p2 = game.get("player_2")
    bet = game["bet"]
    mode = f"{game.get('num_dice', 2)}d6"
    round_num = game.get("round", 1)
    state = game["state"]

    p1_anon = get_anon_id(p1) if p1 else "Анон"
    p2_anon = get_anon_id(p2) if p2 else "Анон"

    if state == "pending":
        rem = max(0, int(game["turn_deadline_ts"] - time.time()))
        target_str = f"Анону <code>[ID:{get_anon_id(game['target_id'])}]</code>" if game.get("target_id") else "Любому желающему анону"
        return (
            f"🎲 <b>ВЫЗОВ НА PvP ДАЙС-ДУЭЛЬ ({mode})</b>\n\n"
            f"👤 <b>Создатель:</b> Анон <code>[ID:{p1_anon}]</code>\n"
            f"🎯 <b>Кому:</b> {target_str}\n"
            f"💰 <b>Ставка:</b> <code>{bet:,} ₪</code> | <b>Банк:</b> <code>{bet*2:,} ₪</code>\n"
            f"⏳ <b>Время на принятие:</b> <code>{rem}с</code>\n\n"
            f"<i>Жми кнопку ниже или напиши <code>/dice accept</code> в ответ на это сообщение!</i>"
        )

    p1_rolls = game["p1_rolls"].get(round_num)
    p2_rolls = game["p2_rolls"].get(round_num)

    p1_status = format_dice_visual(p1_rolls) if p1_rolls else "⏳ <i>Ожидает броска...</i>"
    p2_status = format_dice_visual(p2_rolls) if p2_rolls else "⏳ <i>Ожидает броска...</i>"

    turn_user = game.get("current_turn")
    turn_anon = get_anon_id(turn_user) if turn_user else "???"
    turn_rem = max(0, int(game["turn_deadline_ts"] - time.time()))

    header = f"🎲 <b>PvP ДАЙС-ДУЭЛЬ ({mode}) — РАУНД {round_num}</b>\n\n"
    body = (
        f"💰 <b>Банк:</b> <code>{bet*2:,} ₪</code> (Ставка: <code>{bet:,} ₪</code>)\n\n"
        f"🔴 <b>Игрок 1 [ID:{p1_anon}]:</b> {p1_status}\n"
        f"🔵 <b>Игрок 2 [ID:{p2_anon}]:</b> {p2_status}\n\n"
    )

    if game.get("finished"):
        outcome = game.get("outcome")
        if outcome == "draw":
            footer = f"🤝 <b>Игра завершена вничью!</b> Ставки возвращены."
        else:
            w = game.get("winner")
            w_anon = get_anon_id(w) if w else "???"
            payout = game.get("payout", 0)
            footer = f"👑 <b>Победитель: Анон [ID:{w_anon}]!</b> Забрал <code>+{payout:,} ₪</code>!"
    else:
        footer = (
            f"👉 <b>Сейчас бросает:</b> Анон <code>[ID:{turn_anon}]</code>\n"
            f"⏱️ <b>Таймер на бросок:</b> <code>{turn_rem}с</code>\n\n"
            f"<i>Нажми кнопку «🎲 Бросить кости!» ниже, чтобы бросить кубики.</i>"
        )

    return header + body + footer


# -----------------------------------------------------------------------------
# Background Watchdog & Live Dynamic Updates for Dice Duel
# -----------------------------------------------------------------------------
async def dice_watchdog_step(bot=None):
    """
    Single iteration step of background watchdog checking expired dice turns,
    updating live countdowns dynamically, and cleaning expired challenges.
    """
    now = time.time()
    expired_games = []
    expired_pending = []
    live_tick_games = []

    async with dice_engine_lock:
        for gid, game in list(active_dice_games.items()):
            if game.get("finished") or game.get("state") in ("finished", "expired", "cancelled"):
                fin_ts = game.get("finished_ts")
                if fin_ts is None:
                    game["finished_ts"] = now
                elif now - fin_ts > 60:
                    active_dice_games.pop(gid, None)
                continue
            if game["state"] in ("playing", "rolling"):
                if now > game["turn_deadline_ts"]:
                    expired_games.append(gid)
                else:
                    # Live countdown auto-update every 10 seconds
                    last_tick = game.get("last_tick_ts", game["turn_deadline_ts"] - DICE_TURN_TIMEOUT_SEC)
                    if now - last_tick >= 10.0:
                        game["last_tick_ts"] = now
                        live_tick_games.append(gid)
            elif game["state"] == "pending":
                if now > (game["created_ts"] + DICE_CHALLENGE_TIMEOUT_SEC):
                    # Expire unaccepted challenge
                    game["finished"] = True
                    game["state"] = "expired"
                    game["finished_ts"] = now
                    ch_id = game["player_1"]
                    user_active_dice_game.pop(ch_id, None)
                    if game.get("target_id"):
                        user_active_dice_game.pop(game["target_id"], None)
                    expired_pending.append(gid)
                else:
                    # Live countdown update for pending challenges every 15 seconds
                    last_tick = game.get("last_tick_ts", game["created_ts"])
                    if now - last_tick >= 15.0:
                        game["last_tick_ts"] = now
                        live_tick_games.append(gid)

    # 1. Live countdown updates (playing + pending)
    for gid in live_tick_games:
        async with dice_engine_lock:
            game = active_dice_games.get(gid)
            if not game or game.get("finished"):
                continue
            chat_id = game.get("chat_id")
            msg_id = game.get("msg_id")
            if game["state"] == "playing":
                turn_user = game.get("current_turn")
                kb = get_dice_roll_keyboard(gid, turn_user)
            else:
                kb = get_dice_challenge_keyboard(gid)
            updated_text = format_dice_game_message(game)

        if bot and chat_id and msg_id:
            try:
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=msg_id,
                    text=updated_text,
                    reply_markup=kb,
                    parse_mode="HTML"
                )
            except Exception:
                pass

    # 2. Expired turn games (timeout forfeit)
    for gid in expired_games:
        async with dice_engine_lock:
            game = active_dice_games.get(gid)
            if not game or game.get("finished"):
                continue
            loser_id = game.get("current_turn")
            winner_id = game["player_2"] if loser_id == game["player_1"] else game["player_1"]

        ok, msg, fin_game = await _finish_dice_game(gid, winner_id, loser_id, "timeout", bot)

        if ok and bot and fin_game and fin_game.get("chat_id") and fin_game.get("msg_id"):
            try:
                updated_text = format_dice_game_message(fin_game)
                kb = get_dice_finished_keyboard(gid, fin_game["bet"])
                await bot.edit_message_text(
                    chat_id=fin_game["chat_id"],
                    message_id=fin_game["msg_id"],
                    text=updated_text,
                    reply_markup=kb,
                    parse_mode="HTML"
                )
            except Exception:
                pass

    # 3. Expired pending challenges
    for gid in expired_pending:
        async with dice_engine_lock:
            game = active_dice_games.get(gid)
            if not game:
                continue
            chat_id = game.get("chat_id")
            msg_id = game.get("msg_id")
            p1 = game.get("player_1")
            bet = game.get("bet", 0)

        if bot and p1:
            exp_dm_text = (
                f"⏳ <b>ВЫЗОВ НА PvP ДАЙС-ДУЭЛЬ ИСТЕК</b>\n\n"
                f"Ни один анон не принял твой вызов на кости (<b>{bet:,} ₪</b>) за 2 минуты.\n"
                f"Вызов аннулирован, ставка не списывалась."
            )
            asyncio.create_task(send_pvp_direct_notification(bot, p1, exp_dm_text))

        if bot and chat_id and msg_id:
            try:
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=msg_id,
                    text=(
                        "⏳ <b>ВЫЗОВ НА PvP ДАЙС-ДУЭЛЬ ИСТЕК!</b>\n\n"
                        "Ни один анон не принял вызов на кости за 2 минуты.\n"
                        "Вызов аннулирован, ставка не списана."
                    ),
                    reply_markup=None,
                    parse_mode="HTML"
                )
            except Exception:
                pass


async def start_dice_watchdog_loop(bot):
    """
    Continuous background watchdog loop for Dice Duel timeouts and live countdowns.
    """
    shared_state.runtime_logger.info("Dice Duel PvP watchdog loop started.")
    while True:
        try:
            await dice_watchdog_step(bot)
        except asyncio.CancelledError:
            break
        except Exception as e:
            shared_state.runtime_logger.error(f"Error in dice_watchdog_loop: {e}")
        await asyncio.sleep(2.5)


# -----------------------------------------------------------------------------
# Aiogram Handlers & Command Router Registration
# -----------------------------------------------------------------------------
router = Router(name="dice_duel_router")

def register_dice_duel_handlers(dp: Any):
    """
    Registers all commands, shortcuts, and callback query handlers into aiogram dispatcher.
    """
    global cmd_dice_duel_entry, cmd_dice_duel

    @dp.message(Command("dice", "dice_duel", "diceduel", "дайс_дуэль", "кости_дуэль", "дайсдуэль", "костидуэль", "dices", "дайс", "дайсы", "кости", ignore_case=True, ignore_mention=True))
    async def cmd_dice_duel_entry(message: Message, board_id: str | None = None, stream: str = 'ru'):
        if not board_id:
            board_id = getattr(message.chat, 'id', 'b')
            board_id = str(board_id)

        user_id = message.from_user.id
        raw_text = message.text or message.caption or ""
        tokens = raw_text.strip().split()

        # Check for subcommands: /dice accept, /dice decline, /dice cancel
        if len(tokens) > 1:
            sub = tokens[1].lower()
            if sub in ("accept", "принять", "+", "yes", "ок"):
                await handle_dice_accept_command(message, board_id)
                return
            if sub in ("decline", "отклонить", "cancel", "отмена", "-"):
                await handle_dice_cancel_command(message, board_id)
                return

        # Parse stake amount
        bet_amount = None
        target_user_id = None

        if message.reply_to_message:
            try:
                from common.bot_helpers import get_author_id_by_reply
                target_user_id = await get_author_id_by_reply(message)
            except Exception:
                target_user_id = message.reply_to_message.from_user.id if (message.reply_to_message.from_user and not message.reply_to_message.from_user.is_bot) else None
            if target_user_id == user_id or target_user_id == 0:
                target_user_id = None

        db = await get_pool()
        async with db_lock:
            user_bal = await get_user_global_balance(db, user_id)

        if len(tokens) > 1:
            arg = tokens[1].lower().replace("к", "000").replace("k", "000").replace("м", "000000").replace("m", "000000")
            if arg in ("all", "вабанк", "ва-банк", "всё", "все"):
                bet_amount = int(user_bal)
            elif arg.isdigit():
                bet_amount = int(arg)

        if bet_amount is None:
            # Show interactive lobby menu
            default_bet = 100 if user_bal >= 100 else (50 if user_bal >= 50 else MIN_DICE_BET)
            lobby_kb = get_dice_lobby_keyboard(balance=int(user_bal), current_bet=default_bet, target_id=target_user_id or 0)
            target_str = f"🎯 <b>Цель:</b> Анон <code>[ID:{target_user_id}]</code>\n" if target_user_id else ""
            await message.answer(
                f"🎲 <b>PvP КОСТИ / ДАЙС-ДУЭЛЬ НА ШЕКЕЛИ</b>\n\n"
                f"💰 <b>Твой баланс:</b> <code>{int(user_bal):,} ₪</code>\n"
                f"💰 <b>Ставка:</b> <code>{default_bet:,} ₪</code>\n"
                f"{target_str}\n"
                f"Правила честной игры:\n"
                f"• Бросаем 2d6 (или 3d6) на честном генераторе с визуалом костей (⚀ ⚁ ⚂ ⚃ ⚄ ⚅).\n"
                f"• Побеждает тот, у кого сумма очков выше. При ничьей — переброс!\n"
                f"• Победитель забирает банк за вычетом 5% налога Абу.\n\n"
                f"<b>Команды:</b>\n"
                f"• <code>/dice &lt;ставка&gt;</code> — Бросить вызов всем в треде\n"
                f"• <code>/dice 500</code> (ответом на пост) — Вызвать конкретного анона\n"
                f"• <code>/dice accept</code> — Принять вызов",
                reply_markup=lobby_kb,
                parse_mode="HTML"
            )
            return

        ok, err_or_msg, game_id = await create_dice_challenge(
            board_id=board_id,
            challenger_id=user_id,
            bet=bet_amount,
            target_id=target_user_id,
            num_dice=2
        )

        if not ok:
            await message.answer(err_or_msg, parse_mode="HTML")
            return

        async with dice_engine_lock:
            game = active_dice_games.get(game_id)
            if not game:
                return
            msg_text = format_dice_game_message(game)
            kb = get_dice_challenge_keyboard(game_id)

        sent_msg = await message.answer(msg_text, reply_markup=kb, parse_mode="HTML")
        async with dice_engine_lock:
            if game_id in active_dice_games:
                active_dice_games[game_id]["msg_id"] = sent_msg.message_id
                active_dice_games[game_id]["chat_id"] = sent_msg.chat.id

    async def handle_dice_accept_command(message: Message, board_id: str):
        user_id = message.from_user.id
        found_gid = None

        # If replying to a challenge message
        async with dice_engine_lock:
            if message.reply_to_message:
                reply_mid = message.reply_to_message.message_id
                for gid, g in active_dice_games.items():
                    if g.get("msg_id") == reply_mid and g.get("state") == "pending":
                        found_gid = gid
                        break

            if not found_gid:
                # Find any open pending challenge for this board
                for gid, g in active_dice_games.items():
                    if g.get("board_id") == board_id and g.get("state") == "pending":
                        if g.get("player_1") != user_id and (not g.get("target_id") or g.get("target_id") == user_id):
                            found_gid = gid
                            break

        if not found_gid:
            await message.answer("❌ Нет активных вызовов на кости для принятия!", parse_mode="HTML")
            return

        ok, msg_text, game = await accept_dice_challenge(found_gid, user_id)
        if not ok:
            await message.answer(msg_text, parse_mode="HTML")
            return

        # Update duel message
        turn_user = game["current_turn"]
        kb = get_dice_roll_keyboard(found_gid, turn_user)
        updated_text = format_dice_game_message(game)

        try:
            await message.bot.edit_message_text(
                chat_id=game["chat_id"],
                message_id=game["msg_id"],
                text=updated_text,
                reply_markup=kb,
                parse_mode="HTML"
            )
        except Exception:
            await message.answer(updated_text, reply_markup=kb, parse_mode="HTML")

    async def handle_dice_cancel_command(message: Message, board_id: str):
        user_id = message.from_user.id
        found_gid = user_active_dice_game.get(user_id)
        if not found_gid:
            await message.answer("❌ У тебя нет активных созданных вызовов.", parse_mode="HTML")
            return

        ok, msg = await cancel_dice_challenge(found_gid, user_id)
        await message.answer(msg, parse_mode="HTML")

    # -------------------------------------------------------------------------
    # Callbacks Handlers
    # -------------------------------------------------------------------------
    @dp.callback_query(F.data.startswith("dice_accept:"))
    async def cb_dice_accept(callback: CallbackQuery):
        game_id = callback.data.split(":", 1)[1]
        user_id = callback.from_user.id

        ok, msg_text, game = await accept_dice_challenge(game_id, user_id)
        if not ok:
            shared_state.runtime_logger.warning(
                f"[DiceDuel] accept FAILED gid={game_id} uid={user_id}: {msg_text}"
            )
            await callback.answer(msg_text, show_alert=True)
            return

        await callback.answer("⚔️ Вызов принят! Кости на столе!")
        turn_user = game["current_turn"]
        kb = get_dice_roll_keyboard(game_id, turn_user)
        content = format_dice_game_message(game)

        try:
            await callback.message.edit_text(content, reply_markup=kb, parse_mode="HTML")
        except Exception:
            pass

    @dp.callback_query(F.data.startswith("dice_decline:") | F.data.startswith("dice_cancel:"))
    async def cb_dice_decline(callback: CallbackQuery):
        game_id = callback.data.split(":", 1)[1]
        user_id = callback.from_user.id

        async with dice_engine_lock:
            game = active_dice_games.get(game_id)
            if not game:
                await callback.answer("❌ Игра уже неактивна.", show_alert=True)
                return

            if user_id != game["player_1"] and (not game.get("target_id") or user_id != game.get("target_id")):
                await callback.answer("❌ Ты не можешь отменить чужой вызов!", show_alert=True)
                return

        ok, msg = await cancel_dice_challenge(game_id, user_id, bot=callback.bot)
        await callback.answer(msg)
        try:
            await callback.message.edit_text(f"🗑 <b>Вызов на кости отменен.</b>", parse_mode="HTML")
        except Exception:
            pass

    @dp.callback_query(F.data.startswith("dice_roll:"))
    async def cb_dice_roll(callback: CallbackQuery):
        game_id = callback.data.split(":", 1)[1]
        user_id = callback.from_user.id

        async with dice_engine_lock:
            game = active_dice_games.get(game_id)
            if not game:
                await callback.answer("❌ Игра не найдена.", show_alert=True)
                return
            if game.get("finished"):
                await callback.answer("❌ Игра уже завершена.", show_alert=True)
                return
            if game.get("state") != "playing":
                if game.get("state") == "rolling":
                    await callback.answer("⏳ Кости уже бросаются...", show_alert=False)
                elif game.get("state") == "resolving":
                    await callback.answer("⏳ Раунд завершается...", show_alert=False)
                else:
                    await callback.answer("❌ Сейчас нельзя бросить кости.", show_alert=True)
                return
            if user_id not in (game["player_1"], game["player_2"]):
                await callback.answer("❌ Ты не участвуешь в этой дуэли!", show_alert=True)
                return
            if user_id != game.get("current_turn"):
                await callback.answer("⏳ Сейчас не твой ход!", show_alert=True)
                return

            # Atomically lock this roll by transitioning to rolling
            game["state"] = "rolling"

        # Visual roll animation frames
        anim_frames = ["🎲 <i>Трясем стакан с костями...</i>", "🌀 <i>Кости крутятся на сукне...</i>"]
        for f_text in anim_frames:
            try:
                await callback.message.edit_text(
                    format_dice_game_message(game) + f"\n\n{f_text}",
                    parse_mode="HTML"
                )
                await asyncio.sleep(0.4)
            except Exception:
                pass

        ok, msg_text, updated_game = await execute_player_roll(game_id, user_id, callback.bot)
        if not ok:
            await callback.answer(msg_text, show_alert=True)
            return

        await callback.answer("🎲 Бросок сделан!")
        final_content = format_dice_game_message(updated_game)

        if updated_game.get("finished"):
            kb = get_dice_finished_keyboard(game_id, updated_game["bet"])
        else:
            next_turn = updated_game.get("current_turn")
            kb = get_dice_roll_keyboard(game_id, next_turn)

        try:
            await callback.message.edit_text(final_content, reply_markup=kb, parse_mode="HTML")
        except Exception:
            pass

    @dp.callback_query(F.data.startswith("dice_surrender:"))
    async def cb_dice_surrender(callback: CallbackQuery):
        game_id = callback.data.split(":", 1)[1]
        user_id = callback.from_user.id

        async with dice_engine_lock:
            game = active_dice_games.get(game_id)
            if not game or game.get("finished"):
                await callback.answer("❌ Игра уже завершена.", show_alert=True)
                return
            if user_id not in (game["player_1"], game["player_2"]):
                await callback.answer("❌ Ты не игрок этой партии.", show_alert=True)
                return

            winner_id = game["player_2"] if user_id == game["player_1"] else game["player_1"]

        ok, msg, res_game = await _finish_dice_game(game_id, winner_id, user_id, "surrender", callback.bot)
        if not ok:
            await callback.answer("❌ Игра уже завершена.", show_alert=True)
            return

        await callback.answer("🏳️ Ты сдался.")
        final_content = format_dice_game_message(res_game)
        kb = get_dice_finished_keyboard(game_id, res_game["bet"])
        try:
            await callback.message.edit_text(final_content, reply_markup=kb, parse_mode="HTML")
        except Exception:
            pass

    @dp.callback_query(F.data.startswith("dice_rematch:"))
    async def cb_dice_rematch(callback: CallbackQuery):
        game_id = callback.data.split(":", 1)[1]
        user_id = callback.from_user.id

        async with dice_engine_lock:
            old_game = active_dice_games.get(game_id)
            if not old_game:
                await callback.answer("❌ Данные прошлой дуэли не найдены.", show_alert=True)
                return

            if user_id not in (old_game["player_1"], old_game.get("player_2")):
                await callback.answer("❌ Ты не участвовал в этой дуэли!", show_alert=True)
                return

            bet = old_game["bet"]
            num_dice = old_game.get("num_dice", 2)
            board_id = old_game["board_id"]
            other_player = old_game["player_2"] if user_id == old_game["player_1"] else old_game["player_1"]

        ok, err_or_msg, new_game_id = await create_dice_challenge(
            board_id=board_id,
            challenger_id=user_id,
            bet=bet,
            target_id=other_player,
            num_dice=num_dice
        )
        if not ok:
            await callback.answer(err_or_msg, show_alert=True)
            return

        await callback.answer("⚔️ Вызов на реванш создан!")
        async with dice_engine_lock:
            new_game = active_dice_games.get(new_game_id)
            if not new_game:
                return
            msg_text = format_dice_game_message(new_game)
            kb = get_dice_challenge_keyboard(new_game_id)

        try:
            sent_msg = await callback.message.answer(msg_text, reply_markup=kb, parse_mode="HTML")
            async with dice_engine_lock:
                if new_game_id in active_dice_games:
                    active_dice_games[new_game_id]["msg_id"] = sent_msg.message_id
                    active_dice_games[new_game_id]["chat_id"] = sent_msg.chat.id
        except Exception:
            pass

    @dp.callback_query(F.data.startswith("dice_lobby_bet:"))
    async def cb_dice_lobby_bet(callback: CallbackQuery):
        # Format: dice_lobby_bet:<bet>:<target_id>
        parts = callback.data.split(":")
        bet = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 100
        target_id = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() and int(parts[2]) > 0 else 0
        user_id = callback.from_user.id

        db = await get_pool()
        async with db_lock:
            user_bal = await get_user_global_balance(db, user_id)

        bet = max(MIN_DICE_BET, min(MAX_DICE_BET, min(int(user_bal), bet) if user_bal >= MIN_DICE_BET else MIN_DICE_BET))
        lobby_kb = get_dice_lobby_keyboard(balance=int(user_bal), current_bet=bet, target_id=target_id)
        target_str = f"🎯 <b>Цель:</b> Анон <code>[ID:{target_id}]</code>\n" if target_id else ""
        try:
            await callback.message.edit_text(
                f"🎲 <b>PvP КОСТИ / ДАЙС-ДУЭЛЬ НА ШЕКЕЛИ</b>\n\n"
                f"💳 <b>Твой баланс:</b> <code>{int(user_bal):,} ₪</code>\n"
                f"💰 <b>Ставка:</b> <code>{bet:,} ₪</code>\n"
                f"{target_str}\n"
                f"Выбери ставку и режим броска:",
                reply_markup=lobby_kb,
                parse_mode="HTML"
            )
        except Exception:
            pass
        try: await callback.answer()
        except Exception: pass

    @dp.callback_query(F.data.startswith("dice_create_fast:"))
    async def cb_dice_create_fast(callback: CallbackQuery):
        # Format: dice_create_fast:<mode>:<bet>:<target_id>
        parts = callback.data.split(":")
        mode_str = parts[1] if len(parts) > 1 else "2d6"
        num_dice = 3 if mode_str == "3d6" else 2
        bet = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 100
        target_id = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() and int(parts[3]) > 0 else None
        user_id = callback.from_user.id
        board_id = getattr(callback.message.chat, 'id', 'b')
        board_id = str(board_id)

        ok, err_or_msg, game_id = await create_dice_challenge(
            board_id=board_id,
            challenger_id=user_id,
            bet=bet,
            target_id=target_id,
            num_dice=num_dice
        )
        if not ok:
            await callback.answer(err_or_msg, show_alert=True)
            return

        await callback.answer("✅ Вызов создан!")
        async with dice_engine_lock:
            game = active_dice_games.get(game_id)
            if not game:
                return
            msg_text = format_dice_game_message(game)
            kb = get_dice_challenge_keyboard(game_id)

        try:
            sent_msg = await callback.message.answer(msg_text, reply_markup=kb, parse_mode="HTML")
            async with dice_engine_lock:
                if game_id in active_dice_games:
                    active_dice_games[game_id]["msg_id"] = sent_msg.message_id
                    active_dice_games[game_id]["chat_id"] = sent_msg.chat.id
        except Exception:
            pass

# Auto-register handlers into module-level router
register_dice_duel_handlers(router)
