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

SLOT_SYMBOLS = [
    ("👑", 50.0, 1),    # 777 Jackpot: 1 weight
    ("💎", 15.0, 3),    # Diamonds: 3 weight
    ("🍒", 5.0, 6),     # Cherries: 6 weight
    ("🍋", 3.0, 8),     # Lemons: 8 weight
    ("🍀", 2.0, 10),    # Clovers: 10 weight
    ("💀", 0.0, 12),    # Skulls: 12 weight (loss)
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


# -----------------------------------------------------------------------------
# Slots Mechanics
# -----------------------------------------------------------------------------

def roll_slots() -> Tuple[List[str], float, str]:
    """
    Spins 3 reels based on weighted probability.
    Returns: (symbols_list, multiplier, result_title)
    """
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
                    return reels, mult, "🔥 ДЖЕКПОТ! ТРИ КОРОНЫ 777! 🔥"
                elif sym == "💀":
                    return reels, 0.0, "💀 ТРИ ЧЕРЕПА! Полный провал!"
                return reels, mult, f"✨ ВЫИГРЫШ: Три в ряд ({sym})! x{mult:.0f}!"

    # Check 2 matching (excluding skulls)
    if (reel1 == reel2 or reel2 == reel3 or reel1 == reel3) and ("💀" not in reels or reels.count("💀") < 2):
        matched_sym = reel1 if reel1 == reel2 or reel1 == reel3 else reel2
        if matched_sym != "💀":
            return reels, 1.5, f"🎉 Пара совпадений ({matched_sym})! x1.5"

    return reels, 0.0, "💨 Мимо! Попробуй еще раз."


# -----------------------------------------------------------------------------
# Coinflip Mechanics
# -----------------------------------------------------------------------------

def play_coinflip(chosen_side: str) -> Tuple[str, bool, float, str]:
    """
    Plays 50/50 coinflip.
    chosen_side: 'heads' ('орел', 'eagle') or 'tails' ('решка')
    Returns: (result_side, is_win, multiplier, text_message)
    """
    side = random.choice(["heads", "tails"])
    side_ru = "🦅 ОРЕЛ" if side == "heads" else "👑 РЕШКА"

    is_win = (chosen_side.lower() in ["heads", "орел", "орёл", "eagle", "h"] and side == "heads") or \
             (chosen_side.lower() in ["tails", "решка", "t"] and side == "tails")

    mult = 1.95 if is_win else 0.0
    title = f"🎉 ПОБЕДА! Выпал {side_ru} (x1.95)!" if is_win else f"💀 ПРОИГРЫШ! Выпал {side_ru}."
    return side_ru, is_win, mult, title


# -----------------------------------------------------------------------------
# Russian Roulette on Shekels Mechanics
# -----------------------------------------------------------------------------

ROULETTE_STREAK_MULTS = {
    1: 1.25,
    2: 1.50,
    3: 2.00,
    4: 3.00,
    5: 5.00,
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
    mult = ROULETTE_STREAK_MULTS.get(new_streak, 5.0 + (new_streak - 5) * 1.5)

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
    buttons = [
        [
            InlineKeyboardButton(text=f"🔄 Крутить снова ({bet} ₪)", callback_data=f"cas:slots:spin:{bet}"),
            InlineKeyboardButton(text="2x Ставка", callback_data=f"cas:slots:spin:{bet*2}"),
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
    buttons = [
        [
            InlineKeyboardButton(text=f"🦅 Орел ({bet} ₪)", callback_data=f"cas:coin:heads:{bet}"),
            InlineKeyboardButton(text=f"👑 Решка ({bet} ₪)", callback_data=f"cas:coin:tails:{bet}"),
        ],
        [
            InlineKeyboardButton(text="x2 Ставка", callback_data=f"cas:coin:preset:{bet*2}"),
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
