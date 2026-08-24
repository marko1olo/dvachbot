# -*- coding: utf-8 -*-
"""
casino_engine.py — High-Performance Underground Casino Engine for ТГАЧ
Supports Slots 777, 50/50 Coinflip, Classic Blackjack (21), and Russian Roulette.
Features interactive lobbies, non-triggering previews, bet adjusters, and atomic balance integration.
"""

import random
import time
import asyncio
from typing import List, Tuple, Dict, Optional, Any
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# Global lock for thread-safe active sessions
session_lock = asyncio.Lock()
active_bj_sessions: Dict[int, Dict[str, Any]] = {}
active_roulette_sessions: Dict[int, Dict[str, Any]] = {}

# -----------------------------------------------------------------------------
# Configuration & Payout Tables
# -----------------------------------------------------------------------------

MIN_CASINO_BET = 10
MAX_CASINO_BET = 10_000
MAX_ROULETTE_BET = 5_000

SLOT_SYMBOLS = [
    ("👑", 50.0, 4),    # 777 Jackpot: 4 weight (x50.0)
    ("💎", 25.0, 6),    # Diamonds: 6 weight (x25.0)
    ("🍒", 8.0, 8),     # Cherries: 8 weight (x8.0)
    ("🍋", 4.0, 9),     # Lemons: 9 weight (x4.0)
    ("🍀", 2.5, 10),    # Clovers: 10 weight (x2.5)
    ("💀", 0.0, 11),    # Skulls: 11 weight (loss)
]

CARD_RANKS = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]
CARD_SUITS = ["♠️", "♥️", "♦️", "♣️"]

# -----------------------------------------------------------------------------
# Blackjack Mechanics
# -----------------------------------------------------------------------------

def create_deck() -> List[Tuple[str, str]]:
    deck = [(r, s) for s in CARD_SUITS for r in CARD_RANKS]
    random.shuffle(deck)
    return deck


def calculate_hand(hand: List[Tuple[str, str]]) -> int:
    score = 0
    aces = 0
    for rank, _ in hand:
        if rank in ["J", "Q", "K"]:
            score += 10
        elif rank == "A":
            aces += 1
            score += 11
        else:
            score += int(rank)

    while score > 21 and aces > 0:
        score -= 10
        aces -= 1
    return score


def format_hand(hand: List[Tuple[str, str]], hide_dealer_card: bool = False) -> str:
    if hide_dealer_card:
        visible = hand[0]
        return f"`[{visible[0]}{visible[1]}]` `[🂠 ?]`"
    return " ".join(f"`[{r}{s}]`" for r, s in hand)


# Anti-abuse and rate-limiting
CASINO_COOLDOWN_SECONDS = 2.5
user_casino_last_action: Dict[int, float] = {}
user_win_streaks: Dict[int, int] = {}


def check_casino_cooldown(user_id: int) -> Tuple[bool, float]:
    """
    Prevents script-bot hammering and rapid martingale bets.
    Returns: (is_allowed, remaining_seconds)
    """
    now = time.time()
    last = user_casino_last_action.get(user_id, 0.0)
    elapsed = now - last
    if elapsed < CASINO_COOLDOWN_SECONDS:
        return False, round(CASINO_COOLDOWN_SECONDS - elapsed, 1)
    user_casino_last_action[user_id] = now
    return True, 0.0


def calculate_vip_table_rake(bet: int) -> Tuple[int, int]:
    """
    Deducts a 2% VIP table fee for bets >= 2,000 ₪ sent straight to Abu's Fund.
    Returns: (rake_amount, active_bet)
    """
    if bet >= 2000:
        rake = max(10, int(bet * 0.02))
        return rake, bet - rake
    return 0, bet


def record_win_streak(user_id: int, is_win: bool) -> int:
    """
    Tracks consecutive wins to apply anti-streak house edge tilt.
    """
    if is_win:
        user_win_streaks[user_id] = user_win_streaks.get(user_id, 0) + 1
    else:
        user_win_streaks[user_id] = 0
    return user_win_streaks.get(user_id, 0)


def get_win_streak(user_id: int) -> int:
    return user_win_streaks.get(user_id, 0)


# -----------------------------------------------------------------------------
# Slots Mechanics
# -----------------------------------------------------------------------------

def roll_slots(user_id: int = 0, balance: int = 0) -> Tuple[List[str], float, str]:
    """
    Spins 3 reels based on weighted probability.
    Applies Anti-Streak / High-Roller Tilt if user is on a win streak (>=3) or balance > 100,000 ₪.
    Returns: (symbols_list, multiplier, result_title)
    """
    streak = user_win_streaks.get(user_id, 0) if user_id else 0
    is_tilted = streak >= 3 or balance > 100_000

    # Adjust weights if player is on a hot streak or is an oligarch
    if is_tilted:
        weights = [3, 5, 7, 8, 9, 14]
    else:
        weights = [s[2] for s in SLOT_SYMBOLS]

    symbols = [s[0] for s in SLOT_SYMBOLS]

    reel1 = random.choices(symbols, weights=weights, k=1)[0]
    reel2 = random.choices(symbols, weights=weights, k=1)[0]
    reel3 = random.choices(symbols, weights=weights, k=1)[0]

    reels = [reel1, reel2, reel3]

    # Check 3 matching
    if reel1 == reel2 == reel3:
        for sym, mult, _ in SLOT_SYMBOLS:
            if reel1 == sym:
                if sym == "👑":
                    if user_id: record_win_streak(user_id, True)
                    return reels, mult, "🔥 ДЖЕКПОТ! ТРИ КОРОНЫ 777! 🔥"
                elif sym == "💀":
                    if user_id: record_win_streak(user_id, False)
                    return reels, 0.0, "💀 ТРИ ЧЕРЕПА! Полный провал!"
                if user_id: record_win_streak(user_id, True)
                return reels, mult, f"✨ ВЫИГРЫШ: Три в ряд ({sym})! x{mult:.0f}!"

    # Check 2 matching (excluding skulls)
    if (reel1 == reel2 or reel2 == reel3 or reel1 == reel3) and ("💀" not in reels or reels.count("💀") < 2):
        matched_sym = reel1 if reel1 == reel2 or reel1 == reel3 else reel2
        if matched_sym == "👑":
            if user_id: record_win_streak(user_id, True)
            return reels, 3.0, "👑 Пара Корон! Отличный занос x3.0!"
        elif matched_sym == "💎":
            if user_id: record_win_streak(user_id, True)
            return reels, 2.0, "💎 Пара Бриллиантов! Выигрыш x2.0!"
        elif matched_sym != "💀":
            if user_id: record_win_streak(user_id, True)
            return reels, 1.5, f"🎉 Пара совпадений ({matched_sym})! x1.5"

    if user_id: record_win_streak(user_id, False)
    return reels, 0.0, "💨 Мимо! Попробуй еще раз."


# -----------------------------------------------------------------------------
# Coinflip Mechanics
# -----------------------------------------------------------------------------

def play_coinflip(chosen_side: str, user_id: int = 0, balance: int = 0) -> Tuple[str, bool, float, str]:
    """
    Plays 50/50 coinflip with Anti-Streak Tilt for hot streaks and oligarchs.
    chosen_side: 'heads' ('орел', 'eagle') or 'tails' ('решка')
    Returns: (result_side, is_win, multiplier, text_message)
    """
    streak = user_win_streaks.get(user_id, 0) if user_id else 0
    is_tilted = streak >= 3 or balance > 100_000

    # Under tilt, house edge increases slightly (45% win chance)
    if is_tilted:
        win_prob = 0.45
    else:
        win_prob = 0.50

    side_match = (random.random() < win_prob)

    chosen_is_heads = chosen_side.lower() in ["heads", "орел", "орёл", "eagle", "h"]
    if side_match:
        side = "heads" if chosen_is_heads else "tails"
    else:
        side = "tails" if chosen_is_heads else "heads"

    side_ru = "🦅 ОРЕЛ" if side == "heads" else "👑 РЕШКА"
    is_win = side_match

    if user_id:
        record_win_streak(user_id, is_win)

    mult = 1.95 if is_win else 0.0
    tilt_note = " <i>(Абу подкрутил монетку)</i>" if is_tilted and not is_win else ""
    title = f"🎉 ПОБЕДА! Выпал {side_ru} (x1.95)!" if is_win else f"💀 ПРОИГРЫШ! Выпал {side_ru}.{tilt_note}"
    return side_ru, is_win, mult, title


# -----------------------------------------------------------------------------
# Russian Roulette on Shekels Mechanics
# -----------------------------------------------------------------------------

ROULETTE_STREAK_MULTS = {
    1: 1.15,  # 83.33% chance * 1.15 = 95.83% RTP (Eliminates positive EV exploit)
    2: 1.40,  # 69.44% chance * 1.40 = 97.22% RTP
    3: 1.80,  # 57.87% chance * 1.80 = 104.1% on 3-streak (high risk)
    4: 2.50,
    5: 4.00,
}

def play_russian_roulette_shot(user_id: int, bet: int) -> Tuple[bool, float, int, str]:
    """
    Pulls the trigger in 6-chamber cylinder with 1 bullet (16.67% death).
    Returns: (survived, current_multiplier, current_streak, status_text)
    """
    # 1 out of 6 is bullet
    chamber = random.randint(1, 6)
    is_bullet = (chamber == 1)

    session = active_roulette_sessions.get(user_id, {"streak": 0, "bet": bet})

    if is_bullet:
        active_roulette_sessions.pop(user_id, None)
        return False, 0.0, 0, "💥 БАХ! Пуля пробила череп! Ставка сгорела."

    new_streak = session.get("streak", 0) + 1
    mult = ROULETTE_STREAK_MULTS.get(new_streak, 4.0 + (new_streak - 5) * 1.0)

    active_roulette_sessions[user_id] = {
        "streak": new_streak,
        "bet": bet,
        "current_mult": mult,
        "last_shot": time.time(),
    }

    return True, mult, new_streak, f"💨 *ЩЁЛК!* Пустая камора! Серия: {new_streak} (Множитель: x{mult:.2f})"


# -----------------------------------------------------------------------------
# Keyboards & Visuals (Lobbies & In-Game)
# -----------------------------------------------------------------------------

def get_casino_hub_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text="🎰 Слоты 777", callback_data="cas:menu:slots"),
            InlineKeyboardButton(text="🪙 Монетка 50/50", callback_data="cas:menu:coin"),
        ],
        [
            InlineKeyboardButton(text="🃏 Блэкджек 21", callback_data="cas:menu:bj"),
            InlineKeyboardButton(text="💀 Русская Рулетка", callback_data="cas:menu:roulette"),
        ],
        [
            InlineKeyboardButton(text="💸 Дроп шекелей в тред", callback_data="cas:menu:drop"),
            InlineKeyboardButton(text="📊 Баланс & Статы", callback_data="cas:menu:balance"),
        ],
        [
            InlineKeyboardButton(text="🛒 В Магазин (/shop)", callback_data="shop_main_hub"),
            InlineKeyboardButton(text="💼 На Работу (/work)", callback_data="work_main_hub"),
        ],
        [
            InlineKeyboardButton(text="💳 Мой Кошелек (/wallet)", callback_data="prof_wallet"),
            InlineKeyboardButton(text="🎭 Персонаж RPG (/avatar)", callback_data="avatar_view"),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# --- SLOTS KEYBOARDS ---

def get_slots_lobby_keyboard(bet: int = 100) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text=f"🎰 Крутить барабан ({bet} ₪)", callback_data=f"cas:slots:spin:{bet}"),
        ],
        [
            InlineKeyboardButton(text="25 ₪", callback_data="cas:slots:lobby:25"),
            InlineKeyboardButton(text="50 ₪", callback_data="cas:slots:lobby:50"),
            InlineKeyboardButton(text="100 ₪", callback_data="cas:slots:lobby:100"),
            InlineKeyboardButton(text="250 ₪", callback_data="cas:slots:lobby:250"),
            InlineKeyboardButton(text="500 ₪", callback_data="cas:slots:lobby:500"),
        ],
        [
            InlineKeyboardButton(text="🔙 Меню Казино", callback_data="cas:hub"),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_slots_keyboard(bet: int) -> InlineKeyboardMarkup:
    bet = min(MAX_CASINO_BET, max(MIN_CASINO_BET, bet))
    doubled = min(MAX_CASINO_BET, bet * 2)
    buttons = [
        [
            InlineKeyboardButton(text=f"🔄 Крутить снова ({bet} ₪)", callback_data=f"cas:slots:spin:{bet}"),
            InlineKeyboardButton(text=f"2x Ставка ({doubled} ₪)", callback_data=f"cas:slots:spin:{doubled}"),
        ],
        [
            InlineKeyboardButton(text="50 ₪", callback_data="cas:slots:spin:50"),
            InlineKeyboardButton(text="100 ₪", callback_data="cas:slots:spin:100"),
            InlineKeyboardButton(text="500 ₪", callback_data="cas:slots:spin:500"),
            InlineKeyboardButton(text="1000 ₪", callback_data="cas:slots:spin:1000"),
        ],
        [
            InlineKeyboardButton(text="🔙 Меню Казино", callback_data="cas:hub"),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# --- COINFLIP KEYBOARDS ---

def get_coinflip_lobby_keyboard(bet: int = 100) -> InlineKeyboardMarkup:
    bet = min(MAX_CASINO_BET, max(MIN_CASINO_BET, bet))
    buttons = [
        [
            InlineKeyboardButton(text=f"🦅 На Орла ({bet} ₪)", callback_data=f"cas:coin:heads:{bet}"),
            InlineKeyboardButton(text=f"👑 На Решку ({bet} ₪)", callback_data=f"cas:coin:tails:{bet}"),
        ],
        [
            InlineKeyboardButton(text="25 ₪", callback_data="cas:coin:lobby:25"),
            InlineKeyboardButton(text="50 ₪", callback_data="cas:coin:lobby:50"),
            InlineKeyboardButton(text="100 ₪", callback_data="cas:coin:lobby:100"),
            InlineKeyboardButton(text="250 ₪", callback_data="cas:coin:lobby:250"),
            InlineKeyboardButton(text="500 ₪", callback_data="cas:coin:lobby:500"),
        ],
        [
            InlineKeyboardButton(text="🔙 Меню Казино", callback_data="cas:hub"),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_coinflip_keyboard(bet: int) -> InlineKeyboardMarkup:
    bet = min(MAX_CASINO_BET, max(MIN_CASINO_BET, bet))
    doubled = min(MAX_CASINO_BET, bet * 2)
    buttons = [
        [
            InlineKeyboardButton(text=f"🦅 Орел ({bet} ₪)", callback_data=f"cas:coin:heads:{bet}"),
            InlineKeyboardButton(text=f"👑 Решка ({bet} ₪)", callback_data=f"cas:coin:tails:{bet}"),
        ],
        [
            InlineKeyboardButton(text=f"x2 Ставка ({doubled} ₪)", callback_data=f"cas:coin:preset:{doubled}"),
            InlineKeyboardButton(text="100 ₪", callback_data="cas:coin:preset:100"),
            InlineKeyboardButton(text="500 ₪", callback_data="cas:coin:preset:500"),
        ],
        [
            InlineKeyboardButton(text="🔙 Меню Казино", callback_data="cas:hub"),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# --- BLACKJACK KEYBOARDS ---

def get_blackjack_lobby_keyboard(bet: int = 100) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text=f"🃏 Раздать карты ({bet} ₪)", callback_data=f"cas:bj:start:{bet}"),
        ],
        [
            InlineKeyboardButton(text="50 ₪", callback_data="cas:bj:lobby:50"),
            InlineKeyboardButton(text="100 ₪", callback_data="cas:bj:lobby:100"),
            InlineKeyboardButton(text="250 ₪", callback_data="cas:bj:lobby:250"),
            InlineKeyboardButton(text="500 ₪", callback_data="cas:bj:lobby:500"),
            InlineKeyboardButton(text="1000 ₪", callback_data="cas:bj:lobby:1000"),
        ],
        [
            InlineKeyboardButton(text="🔙 Меню Казино", callback_data="cas:hub"),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_blackjack_keyboard(bet: int, can_double: bool = True) -> InlineKeyboardMarkup:
    row1 = [
        InlineKeyboardButton(text="🃏 Еще карту", callback_data=f"cas:bj:hit:{bet}"),
        InlineKeyboardButton(text="✋ Хватит", callback_data=f"cas:bj:stand:{bet}"),
    ]
    if can_double:
        row1.append(InlineKeyboardButton(text="💥 Дабл (x2)", callback_data=f"cas:bj:double:{bet}"))

    buttons = [
        row1,
        [
            InlineKeyboardButton(text="❌ Сдаться", callback_data=f"cas:bj:surrender:{bet}"),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# --- RUSSIAN ROULETTE KEYBOARDS ---

def get_roulette_lobby_keyboard(bet: int = 100) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text=f"💥 Взвести курок ({bet} ₪)", callback_data=f"cas:roulette:shoot:{bet}"),
        ],
        [
            InlineKeyboardButton(text="50 ₪", callback_data="cas:roulette:lobby:50"),
            InlineKeyboardButton(text="100 ₪", callback_data="cas:roulette:lobby:100"),
            InlineKeyboardButton(text="250 ₪", callback_data="cas:roulette:lobby:250"),
            InlineKeyboardButton(text="500 ₪", callback_data="cas:roulette:lobby:500"),
            InlineKeyboardButton(text="1000 ₪", callback_data="cas:roulette:lobby:1000"),
        ],
        [
            InlineKeyboardButton(text="🔙 Меню Казино", callback_data="cas:hub"),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_roulette_keyboard(bet: int, current_mult: float) -> InlineKeyboardMarkup:
    win_amount = int(bet * current_mult)
    buttons = [
        [
            InlineKeyboardButton(text="💥 Нажать на спуск еще раз!", callback_data=f"cas:roulette:shoot:{bet}"),
        ],
        [
            InlineKeyboardButton(text=f"💰 Забрать {win_amount} ₪ (x{current_mult:.2f})", callback_data=f"cas:roulette:cashout:{bet}"),
        ],
        [
            InlineKeyboardButton(text="🔙 Меню Казино", callback_data="cas:hub"),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)
