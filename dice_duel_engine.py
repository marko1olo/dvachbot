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

import shared_state
from common.db_pool import get_pool, db_lock
from common.database import (
    get_user_global_balance,
    add_user_global_balance,
    deduct_user_global_balance,
    add_to_abu_fund,
    record_user_transaction
)

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


def get_dice_lobby_keyboard(balance: int = 1000, current_bet: int = 100) -> InlineKeyboardMarkup:
    """Interactive quick lobby keyboard for /casino or /duel menu."""
    presets = [50, 250, 1000, 5000, 25000]
    preset_row = [
        InlineKeyboardButton(text=f"{p} ₪", callback_data=f"dice_lobby_bet:{p}")
        for p in presets if p <= max(50, balance)
    ]
    if not preset_row:
        preset_row = [InlineKeyboardButton(text="50 ₪", callback_data="dice_lobby_bet:50")]

    buttons = [
        [
            InlineKeyboardButton(text=f"🎲 Создать дуэль 2d6 ({current_bet:,} ₪)", callback_data=f"dice_create_fast:2d6:{current_bet}"),
            InlineKeyboardButton(text=f"🔥 Дуэль 3d6 ({current_bet:,} ₪)", callback_data=f"dice_create_fast:3d6:{current_bet}")
        ],
        preset_row,
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
            content={'type': 'text', 'text': text},
            reply_to_post=None,
            is_shadow_muted=False,
            stream='ru'
        )
        await process_new_post(params)
    except Exception as e:
        shared_state.runtime_logger.warning(f"Failed to broadcast dice duel post: {e}")


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
        if game["state"] != "pending":
            return False, "❌ Этот вызов уже принят или закрыт!", None
        if game["player_1"] == acceptor_id:
            return False, "❌ Нельзя играть в кости с самим собой, шизофреник.", None
        if game.get("target_id") and game["target_id"] != acceptor_id:
            return False, "❌ Этот вызов адресован персонально другому анону!", None

        bet = game["bet"]
        board_id = game["board_id"]
        challenger_id = game["player_1"]

    db = await get_pool()
    async with db_lock:
        bal_c = await get_user_global_balance(db, challenger_id)
        bal_a = await get_user_global_balance(db, acceptor_id)

        if bal_c < bet:
            return False, "❌ У создателя вызова уже не хватает шекелей на балансе!", None
        if bal_a < bet:
            return False, f"❌ У тебя не хватает шекелей! Ставка: <b>{bet:,} ₪</b>, твой баланс: <b>{int(bal_a):,} ₪</b>.", None

        # Atomic Escrow deduction with safe rollback
        ok_c, _ = await deduct_user_global_balance(db, challenger_id, board_id, bet)
        ok_a, _ = await deduct_user_global_balance(db, acceptor_id, board_id, bet)

        if not (ok_c and ok_a):
            if ok_c:
                await add_user_global_balance(db, challenger_id, board_id, bet)
            if ok_a:
                await add_user_global_balance(db, acceptor_id, board_id, bet)
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
    user_id: int
) -> Tuple[bool, str]:
    """Cancels a pending challenge before it is accepted."""
    async with dice_engine_lock:
        game = active_dice_games.get(game_id)
        if not game:
            return False, "❌ Вызов не найден."
        if game["state"] != "pending":
            return False, "❌ Нельзя отменить уже начавшуюся дуэль!"
        if game["player_1"] != user_id:
            return False, "❌ Только создатель вызова может его отменить."

        game["state"] = "cancelled"
        game["finished"] = True
        user_active_dice_game.pop(user_id, None)

    return True, "🗑 Вызов успешно отменен."


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
    async with dice_engine_lock:
        game = active_dice_games.get(game_id)
        if not game:
            return False, "❌ Партия не найдена.", {}
        if game["state"] != "playing" or game["finished"]:
            return False, "❌ Игра уже завершена.", game
        if user_id not in (game["player_1"], game["player_2"]):
            return False, "❌ Ты не участвуешь в этой дуэли!", game
        if user_id != game["current_turn"]:
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
            game["current_turn"] = other_player
            game["turn_deadline_ts"] = time.time() + DICE_TURN_TIMEOUT_SEC
            return True, "✅ Бросок зафиксирован! Ход переходит к сопернику.", game

    # If both players have completed the current round, resolve or overtime
    return await _evaluate_and_finish_round(game_id, current_round, bot)


async def _evaluate_and_finish_round(
    game_id: str,
    round_num: int,
    bot: Any
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Compares roll scores for the current round. Triggers sudden death overtime if tied,
    or finalizes the game with payouts.
    """
    game = active_dice_games[game_id]
    p1 = game["player_1"]
    p2 = game["player_2"]
    r1 = game["p1_rolls"][round_num]
    r2 = game["p2_rolls"][round_num]

    score1, combo1, flavor1 = evaluate_roll_combo(r1)
    score2, combo2, flavor2 = evaluate_roll_combo(r2)

    # Tie Breaker / Overtime check
    if score1 == score2:
        if round_num < 3:
            async with dice_engine_lock:
                game["round"] += 1
                next_round = game["round"]
                game["current_turn"] = p1 if secrets.randbelow(2) == 0 else p2
                game["turn_deadline_ts"] = time.time() + DICE_TURN_TIMEOUT_SEC

            return True, f"⚖️ <b>НИЧЬЯ В РАУНДЕ {round_num} ({score1}:{score2})!</b> Назначается овертайм (Раунд {next_round})!", game
        else:
            # Absolute max rounds tie -> Refund minus nominal tie rake
            return await _finish_dice_game(game_id, None, None, "draw", bot)

    winner_id = p1 if score1 > score2 else p2
    loser_id = p2 if score1 > score2 else p1

    return await _finish_dice_game(game_id, winner_id, loser_id, "win", bot)


async def _finish_dice_game(
    game_id: str,
    winner_id: Optional[int],
    loser_id: Optional[int],
    reason: str,
    bot: Any
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Finalizes dice duel, distributes winnings/refunds, pays Abu fund rake,
    and publishes the board announcement post.
    """
    async with dice_engine_lock:
        game = active_dice_games[game_id]
        game["finished"] = True
        game["state"] = "finished"
        bet = game["bet"]
        board_id = game["board_id"]
        p1 = game["player_1"]
        p2 = game["player_2"]

        user_active_dice_game.pop(p1, None)
        user_active_dice_game.pop(p2, None)

    db = await get_pool()

    if reason == "draw":
        rake = max(1, int(bet * DICE_TIE_RAKE_PERCENT))
        refund_amt = bet - rake
        async with db_lock:
            await add_user_global_balance(db, p1, board_id, refund_amt)
            await add_user_global_balance(db, p2, board_id, refund_amt)
            await add_to_abu_fund(db, rake * 2)
            await record_user_transaction(db, p1, refund_amt, 'dice_duel', f'Возврат ничьей в Кости #{game_id}')
            await record_user_transaction(db, p2, refund_amt, 'dice_duel', f'Возврат ничьей в Кости #{game_id}')

        game["outcome"] = "draw"
        game["payout"] = refund_amt

        announcement = (
            f"🎲 <b>PvP ДАЙС-ДУЭЛЬ: МЁРТВАЯ НИЧЬЯ!</b>\n\n"
            f">кости брошены трижды, победитель не выявлен\n"
            f"⚖️ <b>Анон <code>[ID:{p1}]</code></b> и <b>Анон <code>[ID:{p2}]</code></b> сошлись на равных на <b>{bet:,} ₪</b>!\n\n"
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
            await add_user_global_balance(db, winner_id, board_id, win_payout)
            await add_to_abu_fund(db, rake)
            await record_user_transaction(db, winner_id, win_payout, 'dice_duel', f'Выигрыш в Дайс-Дуэль #{game_id}')

        game["outcome"] = "win"
        game["winner"] = winner_id
        game["loser"] = loser_id
        game["payout"] = win_payout

        last_round = game["round"]
        w_rolls = game["p1_rolls"].get(last_round) if winner_id == p1 else game["p2_rolls"].get(last_round)
        l_rolls = game["p2_rolls"].get(last_round) if winner_id == p1 else game["p1_rolls"].get(last_round)

        w_vis = format_dice_visual(w_rolls) if w_rolls else "Бросок"
        l_vis = format_dice_visual(l_rolls) if l_rolls else "Фейл"

        if reason == "timeout":
            announcement = (
                f"⏱️ <b>PvP ДАЙС-ДУЭЛЬ: ТЕХНИЧЕСКИЙ НОКАУТ!</b>\n\n"
                f">сыч испугался бросать кости и убежал в слезах\n"
                f"😴 Анон <code>[ID:{loser_id}]</code> пропустил таймер хода (45 сек)!\n"
                f"👑 <b>Победитель:</b> Анон <code>[ID:{winner_id}]</code> забирает весь банк <b>+{win_payout:,} ₪</b>!\n"
                f"🐒 Налог Абу: <code>{rake:,} ₪</code>"
            )
        elif reason == "surrender":
            announcement = (
                f"🏳️ <b>PvP ДАЙС-ДУЭЛЬ: КАПИТУЛЯЦИЯ!</b>\n\n"
                f">выкинул белый флаг прямо на игровое сукно\n"
                f"👑 <b>Победитель:</b> Анон <code>[ID:{winner_id}]</code>\n"
                f"💰 Выигрыш: <b>+{win_payout:,} ₪</b> (Ставка: {bet:,} ₪)."
            )
        else:
            w_score, w_combo, w_flavor = evaluate_roll_combo(w_rolls) if w_rolls else (0, "", "")
            l_score, l_combo, l_flavor = evaluate_roll_combo(l_rolls) if l_rolls else (0, "", "")
            announcement = (
                f"🎲 <b>PvP ДАЙС-ДУЭЛЬ: РАЗНОС НА КОСТЯХ!</b>\n\n"
                f">сошлись два анона на сукне у параши\n"
                f">кости брошены, удача улыбнулась сильнейшему\n\n"
                f"👑 <b>Победитель:</b> Анон <code>[ID:{winner_id}]</code>\n"
                f"🎲 Выкинул: {w_vis} — <i>{w_combo}</i>\n\n"
                f"💀 <b>Проигравший:</b> Анон <code>[ID:{loser_id}]</code>\n"
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

    if state == "pending":
        rem = max(0, int(game["turn_deadline_ts"] - time.time()))
        target_str = f"Анону <code>[ID:{game['target_id']}]</code>" if game.get("target_id") else "Любому желающему анону"
        return (
            f"🎲 <b>ВЫЗОВ НА PvP ДАЙС-ДУЭЛЬ ({mode})</b>\n\n"
            f"👤 <b>Создатель:</b> Анон <code>[ID:{p1}]</code>\n"
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
    turn_rem = max(0, int(game["turn_deadline_ts"] - time.time()))

    header = f"🎲 <b>PvP ДАЙС-ДУЭЛЬ ({mode}) — РАУНД {round_num}</b>\n\n"
    body = (
        f"💰 <b>Банк:</b> <code>{bet*2:,} ₪</code> (Ставка: <code>{bet:,} ₪</code>)\n\n"
        f"🔴 <b>Игрок 1 [ID:{p1}]:</b> {p1_status}\n"
        f"🔵 <b>Игрок 2 [ID:{p2}]:</b> {p2_status}\n\n"
    )

    if game.get("finished"):
        outcome = game.get("outcome")
        if outcome == "draw":
            footer = f"🤝 <b>Игра завершена вничью!</b> Ставки возвращены."
        else:
            w = game.get("winner")
            payout = game.get("payout", 0)
            footer = f"👑 <b>Победитель: Анон [ID:{w}]!</b> Забрал <code>+{payout:,} ₪</code>!"
    else:
        footer = (
            f"👉 <b>Сейчас бросает:</b> Анон <code>[ID:{turn_user}]</code>\n"
            f"⏱️ <b>Таймер на бросок:</b> <code>{turn_rem}с</code>\n\n"
            f"<i>Нажми кнопку «🎲 Бросить кости!» ниже, чтобы бросить кубики.</i>"
        )

    return header + body + footer


# -----------------------------------------------------------------------------
# Aiogram Handlers & Command Router Registration
# -----------------------------------------------------------------------------
router = Router(name="dice_duel_router")

def register_dice_duel_handlers(dp: Any):
    """
    Registers all commands, shortcuts, and callback query handlers into aiogram dispatcher.
    """
    global cmd_dice_duel_entry, cmd_dice_duel

    @dp.message(Command("dice_duel", "diceduel", "дайс_дуэль", "кости_дуэль", "дайсдуэль", "костидуэль", "dices", "дайс", "дайсы", ignore_case=True, ignore_mention=True))
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

        if message.reply_to_message and message.reply_to_message.from_user:
            target_user_id = message.reply_to_message.from_user.id
            if target_user_id == user_id:
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
            lobby_kb = get_dice_lobby_keyboard(balance=int(user_bal), current_bet=100)
            await message.answer(
                f"🎲 <b>PvP КОСТИ / ДАЙС-ДУЭЛЬ НА ШЕКЕЛИ</b>\n\n"
                f"💰 <b>Твой баланс:</b> <code>{int(user_bal):,} ₪</code>\n\n"
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

        game = active_dice_games[game_id]
        msg_text = format_dice_game_message(game)
        kb = get_dice_challenge_keyboard(game_id)

        sent_msg = await message.answer(msg_text, reply_markup=kb, parse_mode="HTML")
        game["msg_id"] = sent_msg.message_id
        game["chat_id"] = sent_msg.chat.id

    async def handle_dice_accept_command(message: Message, board_id: str):
        user_id = message.from_user.id
        found_gid = None

        # If replying to a challenge message
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

        game = active_dice_games.get(game_id)
        if not game:
            await callback.answer("❌ Игра уже неактивна.", show_alert=True)
            return

        if user_id != game["player_1"] and user_id != game.get("target_id"):
            await callback.answer("❌ Ты не можешь отменить чужой вызов!", show_alert=True)
            return

        ok, msg = await cancel_dice_challenge(game_id, game["player_1"])
        await callback.answer(msg)
        try:
            await callback.message.edit_text(f"🗑 <b>Вызов на кости отменен.</b>", parse_mode="HTML")
        except Exception:
            pass

    @dp.callback_query(F.data.startswith("dice_roll:"))
    async def cb_dice_roll(callback: CallbackQuery):
        game_id = callback.data.split(":", 1)[1]
        user_id = callback.from_user.id

        game = active_dice_games.get(game_id)
        if not game:
            await callback.answer("❌ Игра не найдена.", show_alert=True)
            return
        if user_id != game.get("current_turn"):
            await callback.answer("⏳ Сейчас не твой ход!", show_alert=True)
            return

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

        game = active_dice_games.get(game_id)
        if not game or game.get("finished"):
            await callback.answer("❌ Игра уже завершена.", show_alert=True)
            return
        if user_id not in (game["player_1"], game["player_2"]):
            await callback.answer("❌ Ты не игрок этой партии.", show_alert=True)
            return

        winner_id = game["player_2"] if user_id == game["player_1"] else game["player_1"]
        ok, msg, res_game = await _finish_dice_game(game_id, winner_id, user_id, "surrender", callback.bot)

        await callback.answer("🏳️ Ты сдался.")
        final_content = format_dice_game_message(res_game)
        kb = get_dice_finished_keyboard(game_id, res_game["bet"])
        try:
            await callback.message.edit_text(final_content, reply_markup=kb, parse_mode="HTML")
        except Exception:
            pass

    @dp.callback_query(F.data.startswith("dice_create_fast:"))
    async def cb_dice_create_fast(callback: CallbackQuery):
        # Format: dice_create_fast:<mode>:<bet>
        parts = callback.data.split(":")
        mode_str = parts[1] if len(parts) > 1 else "2d6"
        num_dice = 3 if mode_str == "3d6" else 2
        bet = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 100
        user_id = callback.from_user.id
        board_id = getattr(callback.message.chat, 'id', 'b')
        board_id = str(board_id)

        ok, err_or_msg, game_id = await create_dice_challenge(
            board_id=board_id,
            challenger_id=user_id,
            bet=bet,
            num_dice=num_dice
        )
        if not ok:
            await callback.answer(err_or_msg, show_alert=True)
            return

        await callback.answer("✅ Вызов создан!")
        game = active_dice_games[game_id]
        msg_text = format_dice_game_message(game)
        kb = get_dice_challenge_keyboard(game_id)
        await callback.message.answer(msg_text, reply_markup=kb, parse_mode="HTML")

# Auto-register handlers into module-level router
register_dice_duel_handlers(router)
