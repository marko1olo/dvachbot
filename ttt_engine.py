# -*- coding: utf-8 -*-
"""
ttt_engine.py — High-Performance PvP Tic-Tac-Toe on Shekels (❌⭕ Крестики-Нолики) for ТГАЧ
================================================================================================
Features:
1. Challenge creation via Reply or Open Board Lobby (/ttt <bet>, /tictactoe, /кн, /крестики).
2. Interactive 3x3 Inline Keyboard with real-time state visualization (❌, ⭕, ⬜).
3. Strict 60-second turn timeout watchdog with auto-loss and pot transfer to opponent.
4. Flexible betting (50 ₪ to player's balance) with atomic escrow upon game start.
5. Juicy authentic 2ch-style board announcements via `process_new_post` upon win/draw/timeout/forfeit.
6. Fair draw mechanics with bet refund (minus 2% Abu micro-fee).
7. Complete integration with /casino, /duel, and /help.
"""

import time
import asyncio
import random
import logging
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field

from aiogram import Router, F, types, Bot
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from common.db_pool import get_pool, db_lock
from common.database import (
    get_user_global_balance,
    add_user_global_balance,
    deduct_user_global_balance,
    add_to_abu_fund,
    record_user_transaction,
)
from common.anon_identity import get_anon_id

logger = logging.getLogger(__name__)

# ============================================================================
# CONFIGURATION & CONSTANTS
# ============================================================================

MIN_TTT_BET = 50
MAX_TTT_BET = 1_000_000
TURN_TIMEOUT_SECONDS = 60
CHALLENGE_TIMEOUT_SECONDS = 120  # 2 minutes waiting for opponent to accept

ABU_WIN_RAKE_PERCENT = 0.05  # 5% commission on total pot upon victory
ABU_DRAW_FEE_PERCENT = 0.02  # 2% fee per player upon draw

EMPTY_CELL = " "
X_SYMBOL = "X"
O_SYMBOL = "O"

EMOJI_EMPTY = "⬜"
EMOJI_X = "❌"
EMOJI_O = "⭕"

WINNING_COMBINATIONS = [
    # Rows
    (0, 1, 2),
    (3, 4, 5),
    (6, 7, 8),
    # Columns
    (0, 3, 6),
    (1, 4, 7),
    (2, 5, 8),
    # Diagonals
    (0, 4, 8),
    (2, 4, 6),
]

# 2ch/Imageboard phrase generators for announcements
TTT_WIN_PUNCHLINES = [
    "«Потренируйся на кошках, казуал ебаный.»",
    "«Шах и мат, аметисты! Деньги перекочевали к бате.»",
    "«Слишком легко. Этот сыч даже не понял, как проиграл.»",
    "«IQ 200 против IQ хлебушка. Исход был предрешен.»",
    "«Шекели карман не тянут, а проигравшему пора на завод.»",
    "«Диагональ смерти закрыта, касса зафиксирована.»",
]

TTT_DRAW_PUNCHLINES = [
    "«Два аутиста 9 ходов смотрели друг на друга и скатали в ничью.»",
    "«Борьба была равна — играли два гения.»",
    "«Абу забрал 2% за аренду клеток и довольно хрюкнул.»",
    "«Никто не победил, но Абу остался в плюсе.»",
]

TTT_TIMEOUT_PUNCHLINES = [
    "«Уснул лицом в клавиатуру прямо во время ответственного хода.»",
    "«Не выдержал накала страстей и откинулся в астрал.»",
    "«Таймер 60 секунд оказался непреодолимым препятствием для сыча.»",
    "«60 секунд тишины — и шекели испарились.»",
]

TTT_SURRENDER_PUNCHLINES = [
    "«Выбросил белый флаг и позорно убежал с доски.»",
    "«Осознал бесперспективность бытия и нажал F.»",
    "«Сдался без боя, подарив сопернику легчайшие шекели.»",
]


# ============================================================================
# DATA MODEL & STATE
# ============================================================================

@dataclass
class TicTacToeGame:
    game_id: str
    board_id: str
    chat_id: int
    challenger_id: int  # Player 1 (❌)
    bet: int
    opponent_id: Optional[int] = None  # Player 2 (⭕)
    target_user_id: Optional[int] = None  # Specific user challenged via Reply (if any)
    msg_id: Optional[int] = None
    grid: List[str] = field(default_factory=lambda: [EMPTY_CELL] * 9)
    current_turn: int = 0  # user_id whose turn it is
    status: str = "waiting"  # "waiting", "active", "finished"
    winner_id: Optional[int] = None
    finish_reason: Optional[str] = None  # "win", "draw", "timeout", "surrender", "cancelled"
    turn_start_time: float = 0.0
    created_at: float = field(default_factory=time.time)
    winning_line: Optional[Tuple[int, int, int]] = None
    timeout_task: Optional[asyncio.Task] = None
    bot_instance: Optional[Bot] = None

    @property
    def pot(self) -> int:
        return self.bet * 2

    def is_full(self) -> bool:
        return all(cell != EMPTY_CELL for cell in self.grid)

    def get_remaining_time(self) -> int:
        if self.status != "active" or self.turn_start_time <= 0:
            return TURN_TIMEOUT_SECONDS
        elapsed = time.time() - self.turn_start_time
        return max(0, int(TURN_TIMEOUT_SECONDS - elapsed))

    def get_user_symbol(self, user_id: int) -> str:
        if user_id == self.challenger_id:
            return X_SYMBOL
        elif user_id == self.opponent_id:
            return O_SYMBOL
        return "?"

    def get_user_emoji(self, user_id: int) -> str:
        sym = self.get_user_symbol(user_id)
        if sym == X_SYMBOL:
            return EMOJI_X
        elif sym == O_SYMBOL:
            return EMOJI_O
        return "❓"

    def check_winner(self) -> Optional[Tuple[str, Tuple[int, int, int]]]:
        """Returns (winning_symbol, (idx1, idx2, idx3)) if won, else None."""
        for combo in WINNING_COMBINATIONS:
            a, b, c = combo
            if self.grid[a] != EMPTY_CELL and self.grid[a] == self.grid[b] == self.grid[c]:
                return self.grid[a], combo
        return None


# Global active sessions memory registry
active_ttt_games: Dict[str, TicTacToeGame] = {}
user_active_ttt_session: Dict[int, str] = {}  # user_id -> game_id
ttt_lock = asyncio.Lock()


# ============================================================================
# HELPER FORMATTERS & KEYBOARDS
# ============================================================================

def format_bet_amount(amount: int) -> str:
    if amount >= 1_000_000:
        if amount % 1_000_000 == 0:
            return f"{amount // 1_000_000}M ₪"
        return f"{amount / 1_000_000:.1f}M ₪"
    elif amount >= 1000:
        if amount % 1000 == 0:
            return f"{amount // 1000}k ₪"
        return f"{amount / 1000:.1f}k ₪"
    return f"{amount} ₪"


def get_adaptive_bet_presets(balance: int, current_bet: int = 100) -> List[int]:
    """Generates affordable bet presets based on player's current balance."""
    ALL_PRESETS = [50, 100, 250, 500, 1000, 2500, 5000, 10000, 25000, 50000, 100000, 250000, 500000, 1000000]
    eff_bal = max(0, int(balance))
    if eff_bal < MIN_TTT_BET:
        return [MIN_TTT_BET]
    affordable = [p for p in ALL_PRESETS if p <= eff_bal and p <= MAX_TTT_BET]
    if not affordable:
        return [max(MIN_TTT_BET, min(eff_bal, MAX_TTT_BET))]
    if len(affordable) <= 5:
        return affordable
    indices = [0, len(affordable) // 4, len(affordable) // 2, (len(affordable) * 3) // 4, len(affordable) - 1]
    return sorted(list(set(affordable[i] for i in indices)))


def get_ttt_lobby_keyboard(bet: int, balance: int = 1000) -> InlineKeyboardMarkup:
    """Lobby for configuring bet before launching challenge."""
    bet = max(MIN_TTT_BET, min(MAX_TTT_BET, bet))
    presets = get_adaptive_bet_presets(balance, bet)
    preset_row = [
        InlineKeyboardButton(text=format_bet_amount(p), callback_data=f"ttt:lobby:{p}")
        for p in presets
    ]
    buttons = [
        [InlineKeyboardButton(text=f"⚔️ Бросить вызов ({format_bet_amount(bet)})", callback_data=f"ttt:create:{bet}")],
        preset_row,
        [
            InlineKeyboardButton(text="🎲 Дуэли (/duel)", callback_data="cas:menu:duel"),
            InlineKeyboardButton(text="🔙 Меню Казино", callback_data="cas:hub"),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_ttt_challenge_keyboard(game_id: str) -> InlineKeyboardMarkup:
    """Keyboard attached to the open challenge message."""
    buttons = [
        [
            InlineKeyboardButton(text="⚔️ Принять вызов (❌⭕)", callback_data=f"ttt:join:{game_id}"),
        ],
        [
            InlineKeyboardButton(text="❌ Отменить вызов", callback_data=f"ttt:cancel:{game_id}"),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_ttt_game_keyboard(game: TicTacToeGame) -> InlineKeyboardMarkup:
    """Interactive 3x3 grid keyboard during game + surrender/actions."""
    buttons = []
    
    # 3x3 Grid
    for row in range(3):
        row_buttons = []
        for col in range(3):
            idx = row * 3 + col
            cell_val = game.grid[idx]
            
            if cell_val == X_SYMBOL:
                btn_text = EMOJI_X
                cb_data = f"ttt:noop:{game.game_id}:{idx}"
            elif cell_val == O_SYMBOL:
                btn_text = EMOJI_O
                cb_data = f"ttt:noop:{game.game_id}:{idx}"
            else:
                btn_text = EMOJI_EMPTY
                if game.status == "active":
                    cb_data = f"ttt:mv:{game.game_id}:{idx}"
                else:
                    cb_data = f"ttt:noop:{game.game_id}:{idx}"
            
            row_buttons.append(InlineKeyboardButton(text=btn_text, callback_data=cb_data))
        buttons.append(row_buttons)

    # Control row
    if game.status == "active":
        buttons.append([
            InlineKeyboardButton(text="🏳️ Сдаться", callback_data=f"ttt:ff:{game.game_id}"),
            InlineKeyboardButton(text="🔄 Обновить доску", callback_data=f"ttt:refresh:{game.game_id}")
        ])
    elif game.status == "finished":
        buttons.append([
            InlineKeyboardButton(text="🎮 Сыграть еще раз", callback_data="cas:menu:ttt"),
            InlineKeyboardButton(text="🔙 Меню Казино", callback_data="cas:hub")
        ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def render_game_text(game: TicTacToeGame) -> str:
    """Renders high-clarity HTML formatted game message."""
    anon_x = get_anon_id(game.challenger_id)
    anon_o = get_anon_id(game.opponent_id) if game.opponent_id else "Ожидание соперника..."
    
    if game.status == "waiting":
        target_clause = ""
        if game.target_user_id:
            target_clause = f"\n🎯 Персональный вызов для: <b>Анон [{get_anon_id(game.target_user_id)}]</b>"
        return (
            f"❌⭕ <b>КРЕСТИКИ-НОЛИКИ НА ШЕКЕЛИ</b>\n\n"
            f"💰 <b>Ставка:</b> <code>{game.bet:,} ₪</code> (Общий куш: <b>{game.pot:,} ₪</b>)\n"
            f"⚔️ <b>Создатель:</b> ❌ <b>Анон [{anon_x}]</b>{target_clause}\n\n"
            f"⏳ <i>Вызов активен 2 минуты. Нажми кнопку ниже или напиши <code>/ttt accept</code>, чтобы принять бой!</i>"
        )

    rem_time = game.get_remaining_time()
    
    if game.status == "active":
        curr_anon = get_anon_id(game.current_turn)
        curr_emoji = game.get_user_emoji(game.current_turn)
        
        # Highlight urgency if low time
        time_warn = "🚨 " if rem_time <= 15 else "⏳ "
        
        return (
            f"❌⭕ <b>КРЕСТИКИ-НОЛИКИ НА ШЕКЕЛИ (PvP)</b>\n\n"
            f"💰 <b>Банк игры:</b> <code>{game.pot:,} ₪</code> <i>(по {game.bet:,} ₪ с каждого)</i>\n"
            f"⚔️ <b>Соперники:</b>\n"
            f"  ❌ <b>Анон [{anon_x}]</b>\n"
            f"  ⭕ <b>Анон [{anon_o}]</b>\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"{time_warn}<b>На ход: 60 сек</b> (Осталось: <code>{rem_time}с</code>)\n"
            f"👉 <b>Сейчас ходит:</b> {curr_emoji} <b>Анон [{curr_anon}]</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"<i>Нажимай на свободные клетки ⬜ на клавиатуре ниже:</i>"
        )

    # Finished status
    if game.finish_reason == "win":
        winner_anon = get_anon_id(game.winner_id) if game.winner_id else "?"
        winner_emoji = game.get_user_emoji(game.winner_id) if game.winner_id else "👑"
        loser_id = game.opponent_id if game.winner_id == game.challenger_id else game.challenger_id
        loser_anon = get_anon_id(loser_id) if loser_id else "?"
        rake = max(1, int(game.pot * ABU_WIN_RAKE_PERCENT))
        net_win = game.pot - rake
        
        return (
            f"🏆 <b>ИГРА ЗАВЕРШЕНА: ПОБЕДА!</b>\n\n"
            f"👑 Победитель: {winner_emoji} <b>Анон [{winner_anon}]</b>\n"
            f"💀 Проигравший: <b>Анон [{loser_anon}]</b>\n\n"
            f"💰 Выигрыш: <code>+{net_win:,} ₪</code> <i>(Рейк Абу 5%: {rake:,} ₪)</i>\n"
            f"<i>«{random.choice(TTT_WIN_PUNCHLINES)}»</i>"
        )
    elif game.finish_reason == "draw":
        fee = max(1, int(game.bet * ABU_DRAW_FEE_PERCENT))
        refund = game.bet - fee
        return (
            f"🤝 <b>ИГРА ЗАВЕРШЕНА: БОЕВАЯ НИЧЬЯ!</b>\n\n"
            f"Ни один из гроссмейстеров не смог продавить оборону!\n"
            f"• ❌ <b>Анон [{anon_x}]</b>: возврат <code>{refund:,} ₪</code>\n"
            f"• ⭕ <b>Анон [{anon_o}]</b>: возврат <code>{refund:,} ₪</code>\n"
            f"🏛 Микрокомиссия Абу (2%): по {fee:,} ₪\n\n"
            f"<i>«{random.choice(TTT_DRAW_PUNCHLINES)}»</i>"
        )
    elif game.finish_reason == "timeout":
        winner_anon = get_anon_id(game.winner_id) if game.winner_id else "?"
        loser_id = game.opponent_id if game.winner_id == game.challenger_id else game.challenger_id
        loser_anon = get_anon_id(loser_id) if loser_id else "?"
        rake = max(1, int(game.pot * ABU_WIN_RAKE_PERCENT))
        net_win = game.pot - rake
        return (
            f"⏰ <b>ИГРА ЗАВЕРШЕНА: ТАЙМАУТ (60 сек)!</b>\n\n"
            f"💤 <b>Анон [{loser_anon}]</b> пропустил время хода и получает тех-луз!\n"
            f"🏆 Техническая победа: <b>Анон [{winner_anon}]</b> (<code>+{net_win:,} ₪</code>)\n\n"
            f"<i>«{random.choice(TTT_TIMEOUT_PUNCHLINES)}»</i>"
        )
    elif game.finish_reason == "surrender":
        winner_anon = get_anon_id(game.winner_id) if game.winner_id else "?"
        loser_id = game.opponent_id if game.winner_id == game.challenger_id else game.challenger_id
        loser_anon = get_anon_id(loser_id) if loser_id else "?"
        rake = max(1, int(game.pot * ABU_WIN_RAKE_PERCENT))
        net_win = game.pot - rake
        return (
            f"🏳️ <b>ИГРА ЗАВЕРШЕНА: КАПИТУЛЯЦИЯ!</b>\n\n"
            f"<b>Анон [{loser_anon}]</b> выбросил белый флаг!\n"
            f"🏆 Победитель: <b>Анон [{winner_anon}]</b> (<code>+{net_win:,} ₪</code>)\n\n"
            f"<i>«{random.choice(TTT_SURRENDER_PUNCHLINES)}»</i>"
        )
    elif game.finish_reason == "cancelled":
        return "❌ <b>Вызов в крестики-нолики был отменен создателем.</b>"

    return "❌⭕ <b>Крестики-Нолики</b>"


# ============================================================================
# BOARD ANNOUNCEMENT ENGINE (process_new_post)
# ============================================================================

async def publish_ttt_board_announcement(
    bot: Bot,
    board_id: str,
    text: str,
    stream: str = "ru"
) -> None:
    """Publishes spicy 2ch-style announcement directly to the board feed."""
    try:
        from shared_state import NewPostParams
        from post_processor import process_new_post
        
        await process_new_post(NewPostParams(
            bot_instance=bot,
            board_id=board_id,
            user_id=0,  # 0 denotes system announcement
            content={"type": "text", "text": text, "is_system_message": True},
            reply_to_post=None,
            is_shadow_muted=False,
            stream=stream
        ))
    except Exception as e:
        logger.warning(f"⚠️ Failed to publish TTT announcement to board feed: {e}")


# ============================================================================
# TIMEOUT WATCHDOG (60 Seconds Turn Timer)
# ============================================================================

async def _turn_timeout_watcher(game_id: str, turn_user_id: int) -> None:
    """Asynchronous background watchdog enforcing strictly 60 seconds per turn."""
    try:
        await asyncio.sleep(TURN_TIMEOUT_SECONDS)
        
        async with ttt_lock:
            game = active_ttt_games.get(game_id)
            if not game or game.status != "active":
                return
            # Verify that current turn did not change
            if game.current_turn != turn_user_id:
                return
            
            # Auto-loss triggered!
            loser_id = turn_user_id
            winner_id = game.opponent_id if loser_id == game.challenger_id else game.challenger_id
            
            game.status = "finished"
            game.winner_id = winner_id
            game.finish_reason = "timeout"
            
            # Clean user sessions
            user_active_ttt_session.pop(game.challenger_id, None)
            if game.opponent_id:
                user_active_ttt_session.pop(game.opponent_id, None)
        
        # Payout logic under db_lock
        db = await get_pool()
        rake = max(1, int(game.pot * ABU_WIN_RAKE_PERCENT))
        net_win = game.pot - rake
        
        async with db_lock:
            await add_user_global_balance(db, winner_id, game.board_id, net_win)
            await add_to_abu_fund(db, rake, donor_id=winner_id, reason="Рейк с таймаута в КН")
            await record_user_transaction(
                db, winner_id, net_win, "ttt",
                f"Техническая победа (таймаут) в КН против [{get_anon_id(loser_id)}]"
            )
            await record_user_transaction(
                db, loser_id, -game.bet, "ttt",
                f"Техническое поражение (таймаут 60с) в КН против [{get_anon_id(winner_id)}]"
            )

        # Update message in chat
        if game.bot_instance and game.chat_id and game.msg_id:
            try:
                await game.bot_instance.edit_message_text(
                    chat_id=game.chat_id,
                    message_id=game.msg_id,
                    text=render_game_text(game),
                    reply_markup=get_ttt_game_keyboard(game),
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.debug(f"Failed to edit TTT timeout message: {e}")

        # Post 2ch announcement to board
        winner_anon = get_anon_id(winner_id)
        loser_anon = get_anon_id(loser_id)
        punchline = random.choice(TTT_TIMEOUT_PUNCHLINES)
        announcement = (
            f"💤 <b>[КРЕСТИКИ-НОЛИКИ / ТАЙМАУТ]</b>\n"
            f"<b>Анон [{loser_anon}]</b> не справился с таймером 60 сек в битве на <b>{game.pot:,} ₪</b>!\n\n"
            f"🏆 Техническая победа присуждается <b>Анону [{winner_anon}]</b>!\n"
            f"💰 Чистый занос: <code>+{net_win:,} ₪</code> <i>(Рейк Абу: {rake:,} ₪)</i>\n\n"
            f"<i>{punchline}</i>"
        )
        if game.bot_instance:
            await publish_ttt_board_announcement(game.bot_instance, game.board_id, announcement)

    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"Error in TTT turn timeout watcher: {e}", exc_info=True)


def _reset_and_start_timer(game: TicTacToeGame) -> None:
    """Cancels old timer task and spawns a fresh 60s turn timer task."""
    if game.timeout_task and not game.timeout_task.done():
        game.timeout_task.cancel()
    
    game.turn_start_time = time.time()
    game.timeout_task = asyncio.create_task(
        _turn_timeout_watcher(game.game_id, game.current_turn)
    )


# ============================================================================
# CORE GAME ACTIONS (CREATE, JOIN, MOVE, FORFEIT, CANCEL)
# ============================================================================

async def create_ttt_challenge(
    bot: Bot,
    chat_id: int,
    board_id: str,
    challenger_id: int,
    bet: int,
    target_user_id: Optional[int] = None,
    stream: str = "ru"
) -> Tuple[bool, str, Optional[TicTacToeGame]]:
    """Creates a new Tic-Tac-Toe challenge and checks balance."""
    if bet < MIN_TTT_BET:
        return False, f"❌ Минимальная ставка: {MIN_TTT_BET:,} ₪", None
    if bet > MAX_TTT_BET:
        return False, f"❌ Максимальная ставка: {MAX_TTT_BET:,} ₪", None

    db = await get_pool()
    async with db_lock:
        bal = await get_user_global_balance(db, challenger_id)
    
    if bal < bet:
        return False, f"❌ Недостаточно шекелей! Ставка {bet:,} ₪, твой баланс: {int(bal):,} ₪.", None

    async with ttt_lock:
        # Check if user already has an active session
        existing_id = user_active_ttt_session.get(challenger_id)
        if existing_id:
            existing_game = active_ttt_games.get(existing_id)
            if existing_game and existing_game.status in ("waiting", "active"):
                return False, "⚠️ У тебя уже есть активная игра или открытый вызов в крестики-нолики!", None

        import uuid
        game_id = uuid.uuid4().hex[:10]
        game = TicTacToeGame(
            game_id=game_id,
            board_id=board_id,
            chat_id=chat_id,
            challenger_id=challenger_id,
            bet=bet,
            target_user_id=target_user_id,
            status="waiting",
            bot_instance=bot,
        )
        active_ttt_games[game_id] = game
        user_active_ttt_session[challenger_id] = game_id

    return True, "OK", game


async def accept_ttt_challenge(
    bot: Bot,
    game_id: str,
    opponent_id: int
) -> Tuple[bool, str, Optional[TicTacToeGame]]:
    """Accepts challenge, locks escrow from both players, and starts the game."""
    db = await get_pool()
    
    async with ttt_lock:
        game = active_ttt_games.get(game_id)
        if not game:
            return False, "❌ Вызов не найден или устарел.", None
        if game.status != "waiting":
            return False, "❌ Эта игра уже начата или завершена.", None
        if game.challenger_id == opponent_id:
            return False, "❌ Ты не можешь принять собственный вызов!", None
        if game.target_user_id and game.target_user_id != opponent_id:
            return False, f"❌ Этот вызов предназначен только для Анона [{get_anon_id(game.target_user_id)}]!", None
        
        # Check if opponent is already in game
        opp_existing = user_active_ttt_session.get(opponent_id)
        if opp_existing and opp_existing != game_id:
            existing_g = active_ttt_games.get(opp_existing)
            if existing_g and existing_g.status in ("waiting", "active"):
                return False, "⚠️ У тебя уже есть другая активная игра в крестики-нолики!", None

        # Escrow verification under db_lock
        async with db_lock:
            ch_bal = await get_user_global_balance(db, game.challenger_id)
            op_bal = await get_user_global_balance(db, opponent_id)

            if ch_bal < game.bet:
                active_ttt_games.pop(game_id, None)
                user_active_ttt_session.pop(game.challenger_id, None)
                return False, f"❌ У создателя вызова [{get_anon_id(game.challenger_id)}] изменился баланс. Вызов отменен.", None

            if op_bal < game.bet:
                return False, f"❌ Недостаточно шекелей. Нужно {game.bet:,} ₪, у тебя {int(op_bal):,} ₪.", None

            # Deduct escrow from both players
            ok_ch, _ = await deduct_user_global_balance(db, game.challenger_id, game.board_id, game.bet)
            ok_op, _ = await deduct_user_global_balance(db, opponent_id, game.board_id, game.bet)

            if not (ok_ch and ok_op):
                # Rollback if partial failure
                if ok_ch:
                    await add_user_global_balance(db, game.challenger_id, game.board_id, game.bet)
                if ok_op:
                    await add_user_global_balance(db, opponent_id, game.board_id, game.bet)
                return False, "❌ Ошибка списания средств. Попробуй снова.", None

            await record_user_transaction(db, game.challenger_id, -game.bet, "ttt", f"Ставка в КН против [{get_anon_id(opponent_id)}]")
            await record_user_transaction(db, opponent_id, -game.bet, "ttt", f"Ставка в КН против [{get_anon_id(game.challenger_id)}]")

        # Launch Game
        game.opponent_id = opponent_id
        game.status = "active"
        game.current_turn = game.challenger_id  # ❌ starts first
        game.bot_instance = bot
        user_active_ttt_session[opponent_id] = game_id

        # Start 60s turn timer
        _reset_and_start_timer(game)

    return True, "OK", game


async def process_ttt_move(
    bot: Bot,
    game_id: str,
    user_id: int,
    cell_idx: int
) -> Tuple[bool, str, Optional[TicTacToeGame]]:
    """Handles cell click, updates grid, checks win/draw conditions."""
    if not (0 <= cell_idx < 9):
        return False, "❌ Некорректная клетка.", None

    async with ttt_lock:
        game = active_ttt_games.get(game_id)
        if not game:
            return False, "❌ Игра не найдена.", None
        if game.status != "active":
            return False, "❌ Игра уже завершена.", None
        if user_id not in (game.challenger_id, game.opponent_id):
            return False, "👀 Ты зритель в этой партии!", None
        if user_id != game.current_turn:
            return False, "⏳ Сейчас не твой ход! Подожди соперника.", None
        if game.grid[cell_idx] != EMPTY_CELL:
            return False, "⚠️ Эта клетка уже занята!", None

        # Apply move
        symbol = game.get_user_symbol(user_id)
        game.grid[cell_idx] = symbol

        # Check win
        win_result = game.check_winner()
        if win_result:
            winning_sym, combo = win_result
            game.status = "finished"
            game.winner_id = user_id
            game.winning_line = combo
            game.finish_reason = "win"
            if game.timeout_task and not game.timeout_task.done():
                game.timeout_task.cancel()
            
            user_active_ttt_session.pop(game.challenger_id, None)
            if game.opponent_id:
                user_active_ttt_session.pop(game.opponent_id, None)
            
            is_win = True
            is_draw = False

        elif game.is_full():
            # Draw
            game.status = "finished"
            game.finish_reason = "draw"
            if game.timeout_task and not game.timeout_task.done():
                game.timeout_task.cancel()

            user_active_ttt_session.pop(game.challenger_id, None)
            if game.opponent_id:
                user_active_ttt_session.pop(game.opponent_id, None)
            
            is_win = False
            is_draw = True
        else:
            # Switch turn
            is_win = False
            is_draw = False
            game.current_turn = game.opponent_id if user_id == game.challenger_id else game.challenger_id
            _reset_and_start_timer(game)

    # Handle financial settlement outside ttt_lock
    db = await get_pool()
    if is_win:
        rake = max(1, int(game.pot * ABU_WIN_RAKE_PERCENT))
        net_win = game.pot - rake
        loser_id = game.opponent_id if game.winner_id == game.challenger_id else game.challenger_id
        
        async with db_lock:
            await add_user_global_balance(db, game.winner_id, game.board_id, net_win)
            await add_to_abu_fund(db, rake, donor_id=game.winner_id, reason="Рейк с победы в КН")
            await record_user_transaction(
                db, game.winner_id, net_win, "ttt",
                f"Победа в КН против [{get_anon_id(loser_id)}]"
            )
            await record_user_transaction(
                db, loser_id, -game.bet, "ttt",
                f"Поражение в КН против [{get_anon_id(game.winner_id)}]"
            )

        # 2ch board announcement
        winner_anon = get_anon_id(game.winner_id)
        loser_anon = get_anon_id(loser_id)
        winner_emoji = game.get_user_emoji(game.winner_id)
        punchline = random.choice(TTT_WIN_PUNCHLINES)
        announcement = (
            f"🎮 <b>[КРЕСТИКИ-НОЛИКИ / ПОБЕДА]</b>\n"
            f"Ебанаты сыграли в крестики-нолики на <b>{game.pot:,} ₪</b>!\n\n"
            f"🏆 <b>Анон [{winner_anon}]</b> ({winner_emoji}) раскатал по доске сыча <b>Анона [{loser_anon}]</b>!\n"
            f"💰 Занос: <code>+{net_win:,} ₪</code> <i>(Рейк Абу: {rake:,} ₪)</i>\n\n"
            f"<i>{punchline}</i>"
        )
        await publish_ttt_board_announcement(bot, game.board_id, announcement)

    elif is_draw:
        fee = max(1, int(game.bet * ABU_DRAW_FEE_PERCENT))
        refund = game.bet - fee
        
        async with db_lock:
            await add_user_global_balance(db, game.challenger_id, game.board_id, refund)
            await add_user_global_balance(db, game.opponent_id, game.board_id, refund)
            await add_to_abu_fund(db, fee * 2, reason="Микрокомиссия 2% за ничью в КН")
            await record_user_transaction(db, game.challenger_id, refund - game.bet, "ttt", "Возврат ставки (ничья КН)")
            await record_user_transaction(db, game.opponent_id, refund - game.bet, "ttt", "Возврат ставки (ничья КН)")

        # 2ch board announcement
        anon_x = get_anon_id(game.challenger_id)
        anon_o = get_anon_id(game.opponent_id)
        punchline = random.choice(TTT_DRAW_PUNCHLINES)
        announcement = (
            f"🤝 <b>[КРЕСТИКИ-НОЛИКИ / НИЧЬЯ]</b>\n"
            f"Два сверхразума <b>Анон [{anon_x}]</b> и <b>Анон [{anon_o}]</b> скатали в ничью на <b>{game.pot:,} ₪</b>!\n\n"
            f"Ставки возвращены владельцам (минус 2% налог Абу: по {fee:,} ₪).\n\n"
            f"<i>{punchline}</i>"
        )
        await publish_ttt_board_announcement(bot, game.board_id, announcement)

    return True, "OK", game


async def surrender_ttt_game(
    bot: Bot,
    game_id: str,
    user_id: int
) -> Tuple[bool, str, Optional[TicTacToeGame]]:
    """Handles surrender button click."""
    async with ttt_lock:
        game = active_ttt_games.get(game_id)
        if not game:
            return False, "❌ Игра не найдена.", None
        if game.status != "active":
            return False, "❌ Игра не активна.", None
        if user_id not in (game.challenger_id, game.opponent_id):
            return False, "👀 Ты не участник этой партии!", None

        loser_id = user_id
        winner_id = game.opponent_id if loser_id == game.challenger_id else game.challenger_id
        
        game.status = "finished"
        game.winner_id = winner_id
        game.finish_reason = "surrender"
        if game.timeout_task and not game.timeout_task.done():
            game.timeout_task.cancel()

        user_active_ttt_session.pop(game.challenger_id, None)
        if game.opponent_id:
            user_active_ttt_session.pop(game.opponent_id, None)

    # Financial settlement
    db = await get_pool()
    rake = max(1, int(game.pot * ABU_WIN_RAKE_PERCENT))
    net_win = game.pot - rake
    
    async with db_lock:
        await add_user_global_balance(db, winner_id, game.board_id, net_win)
        await add_to_abu_fund(db, rake, donor_id=winner_id, reason="Рейк при сдаче в КН")
        await record_user_transaction(db, winner_id, net_win, "ttt", f"Победа (сдача) в КН против [{get_anon_id(loser_id)}]")
        await record_user_transaction(db, loser_id, -game.bet, "ttt", f"Капитуляция в КН против [{get_anon_id(winner_id)}]")

    # 2ch announcement
    winner_anon = get_anon_id(winner_id)
    loser_anon = get_anon_id(loser_id)
    punchline = random.choice(TTT_SURRENDER_PUNCHLINES)
    announcement = (
        f"🏳️ <b>[КРЕСТИКИ-НОЛИКИ / СДАЧА]</b>\n"
        f"<b>Анон [{loser_anon}]</b> выбросил белый флаг в дуэли на <b>{game.pot:,} ₪</b>!\n\n"
        f"🏆 <b>Анон [{winner_anon}]</b> забирает куш <code>+{net_win:,} ₪</code> без боя!\n\n"
        f"<i>{punchline}</i>"
    )
    await publish_ttt_board_announcement(bot, game.board_id, announcement)

    return True, "OK", game


async def cancel_ttt_challenge(
    game_id: str,
    user_id: int
) -> Tuple[bool, str]:
    """Cancels a pending challenge before anyone joins."""
    async with ttt_lock:
        game = active_ttt_games.get(game_id)
        if not game:
            return False, "❌ Вызов не найден или уже завершен."
        if game.status != "waiting":
            return False, "❌ Нельзя отменить уже начатую игру!"
        if game.challenger_id != user_id:
            return False, "❌ Только создатель вызова может его отменить!"

        game.status = "finished"
        game.finish_reason = "cancelled"
        active_ttt_games.pop(game_id, None)
        user_active_ttt_session.pop(user_id, None)
        return True, "✅ Вызов успешно отменен."


# ============================================================================
# AIOGRAM ROUTER & HANDLERS
# ============================================================================

router = Router(name="ttt_engine")


@router.message(Command("ttt", "tictactoe", "кн", "крестики", "крестикинолики", ignore_case=True, ignore_mention=True))
async def cmd_ttt(message: Message, board_id: Optional[str] = None, stream: str = "ru"):
    """Main command handler for /ttt [bet] / [accept]."""
    if not board_id:
        return
    user_id = message.from_user.id
    text = (message.text or message.caption or "").strip()
    parts = text.split()
    args = parts[1:] if len(parts) > 1 else []

    # Handle "/ttt accept"
    if args and args[0].lower() in ("accept", "принять", "+", "yes", "да"):
        # Search by reply first
        found_game_id = None
        if message.reply_to_message:
            reply_msg_id = message.reply_to_message.message_id
            for gid, g in list(active_ttt_games.items()):
                if g.msg_id == reply_msg_id and g.status == "waiting" and g.board_id == board_id:
                    found_game_id = gid
                    break
        
        # If not by reply, find any open challenge on board
        if not found_game_id:
            for gid, g in list(active_ttt_games.items()):
                if g.status == "waiting" and g.board_id == board_id and g.challenger_id != user_id:
                    if not g.target_user_id or g.target_user_id == user_id:
                        found_game_id = gid
                        break

        if not found_game_id:
            await message.answer("❌ Нет активных вызовов в крестики-нолики на этой борде.")
            return

        ok, err, game = await accept_ttt_challenge(message.bot, found_game_id, user_id)
        if not ok:
            await message.answer(err)
            return

        # Update challenge message
        if game and game.msg_id:
            try:
                await message.bot.edit_message_text(
                    chat_id=game.chat_id,
                    message_id=game.msg_id,
                    text=render_game_text(game),
                    reply_markup=get_ttt_game_keyboard(game),
                    parse_mode="HTML"
                )
            except Exception:
                pass
        return

    # Handle "/ttt cancel"
    if args and args[0].lower() in ("cancel", "отмена", "отменить"):
        gid = user_active_ttt_session.get(user_id)
        if not gid:
            await message.answer("❌ У тебя нет активных вызовов.")
            return
        ok, msg = await cancel_ttt_challenge(gid, user_id)
        await message.answer(msg)
        return

    # Target user via Reply (if any)
    target_user_id = None
    if message.reply_to_message and message.reply_to_message.from_user:
        if not message.reply_to_message.from_user.is_bot:
            target_user_id = message.reply_to_message.from_user.id

    # Parse Bet or Open Lobby
    if not args or not args[0].isdigit():
        db = await get_pool()
        async with db_lock:
            balance = await get_user_global_balance(db, user_id)
        
        default_bet = 100 if balance >= 100 else (50 if balance >= 50 else MIN_TTT_BET)
        kb = get_ttt_lobby_keyboard(default_bet, balance=int(balance))
        caption = (
            f"❌⭕ <b>КРЕСТИКИ-НОЛИКИ НА ШЕКЕЛИ (PvP)</b>\n\n"
            f"💳 Твой баланс: <code>{int(balance):,} ₪</code>\n"
            f"💰 Выбранная ставка: <code>{default_bet:,} ₪</code>\n\n"
            f"Правила:\n"
            f"• Поле 3x3, ходы по очереди (❌ начинают первыми).\n"
            f"• ⏳ <b>Строго 60 секунд на ход!</b> При таймауте — авто-луз и передача банка.\n"
            f"• При ничьей — возврат ставки (минус 2% сбор Абу).\n"
            f"• Победитель забирает банк (минус 5% рейк Абу).\n\n"
            f"Выбери ставку кнопками или напиши: <code>/ttt 500</code>"
        )
        await message.answer(caption, reply_markup=kb, parse_mode="HTML")
        return

    bet = int(args[0])
    ok, err, game = await create_ttt_challenge(
        bot=message.bot,
        chat_id=message.chat.id,
        board_id=board_id,
        challenger_id=user_id,
        bet=bet,
        target_user_id=target_user_id,
        stream=stream
    )
    if not ok or not game:
        await message.answer(err)
        return

    kb = get_ttt_challenge_keyboard(game.game_id)
    sent = await message.answer(render_game_text(game), reply_markup=kb, parse_mode="HTML")
    game.msg_id = sent.message_id

    try:
        await message.delete()
    except Exception:
        pass


@router.callback_query(F.data == "cas:menu:ttt")
async def cb_casino_ttt_menu(callback: CallbackQuery, board_id: Optional[str] = None):
    """Opens Tic-Tac-Toe lobby from casino hub."""
    user_id = callback.from_user.id
    db = await get_pool()
    async with db_lock:
        balance = await get_user_global_balance(db, user_id)
    
    default_bet = 100 if balance >= 100 else 50
    kb = get_ttt_lobby_keyboard(default_bet, balance=int(balance))
    caption = (
        f"❌⭕ <b>КРЕСТИКИ-НОЛИКИ НА ШЕКЕЛИ (PvP)</b>\n\n"
        f"💳 Твой баланс: <code>{int(balance):,} ₪</code>\n"
        f"💰 Выбранная ставка: <code>{default_bet:,} ₪</code>\n\n"
        f"Выбери размер ставки и создай открытый вызов на доску:"
    )
    try:
        await callback.message.edit_text(caption, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await callback.message.answer(caption, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("ttt:lobby:"))
async def cb_ttt_lobby_change_bet(callback: CallbackQuery):
    """Updates selected bet preset in lobby."""
    user_id = callback.from_user.id
    parts = callback.data.split(":")
    bet = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 100
    
    db = await get_pool()
    async with db_lock:
        balance = await get_user_global_balance(db, user_id)
    
    kb = get_ttt_lobby_keyboard(bet, balance=int(balance))
    caption = (
        f"❌⭕ <b>КРЕСТИКИ-НОЛИКИ НА ШЕКЕЛИ (PvP)</b>\n\n"
        f"💳 Твой баланс: <code>{int(balance):,} ₪</code>\n"
        f"💰 Выбранная ставка: <code>{bet:,} ₪</code>\n\n"
        f"Выбери размер ставки и создай открытый вызов на доску:"
    )
    try:
        await callback.message.edit_text(caption, reply_markup=kb, parse_mode="HTML")
    except Exception:
        pass
    await callback.answer()


@router.callback_query(F.data.startswith("ttt:create:"))
async def cb_ttt_create(callback: CallbackQuery, board_id: Optional[str] = None):
    """Creates challenge from lobby button."""
    if not board_id:
        board_id = "b"
    user_id = callback.from_user.id
    parts = callback.data.split(":")
    bet = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 100

    ok, err, game = await create_ttt_challenge(
        bot=callback.bot,
        chat_id=callback.message.chat.id,
        board_id=board_id,
        challenger_id=user_id,
        bet=bet,
    )
    if not ok or not game:
        await callback.answer(err, show_alert=True)
        return

    kb = get_ttt_challenge_keyboard(game.game_id)
    sent = await callback.message.answer(render_game_text(game), reply_markup=kb, parse_mode="HTML")
    game.msg_id = sent.message_id
    
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.answer("⚔️ Вызов выставлен на доску!")


@router.callback_query(F.data.startswith("ttt:join:"))
async def cb_ttt_join(callback: CallbackQuery):
    """Opponent clicks Accept Challenge."""
    user_id = callback.from_user.id
    game_id = callback.data.split(":")[2]

    ok, err, game = await accept_ttt_challenge(callback.bot, game_id, user_id)
    if not ok or not game:
        await callback.answer(err, show_alert=True)
        return

    game.msg_id = callback.message.message_id
    try:
        await callback.message.edit_text(
            render_game_text(game),
            reply_markup=get_ttt_game_keyboard(game),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.debug(f"Failed to edit TTT message upon join: {e}")

    await callback.answer("⚔️ Игра началась! Первый ход за ❌")


@router.callback_query(F.data.startswith("ttt:mv:"))
async def cb_ttt_move(callback: CallbackQuery):
    """Player clicks on a 3x3 grid cell."""
    user_id = callback.from_user.id
    parts = callback.data.split(":")
    game_id = parts[2]
    cell_idx = int(parts[3])

    ok, err, game = await process_ttt_move(callback.bot, game_id, user_id, cell_idx)
    if not ok or not game:
        await callback.answer(err, show_alert=True)
        return

    try:
        await callback.message.edit_text(
            render_game_text(game),
            reply_markup=get_ttt_game_keyboard(game),
            parse_mode="HTML"
        )
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e).lower():
            logger.debug(f"Edit move TelegramBadRequest: {e}")
    except Exception as e:
        logger.debug(f"Error editing TTT move message: {e}")

    await callback.answer()


@router.callback_query(F.data.startswith("ttt:ff:"))
async def cb_ttt_surrender(callback: CallbackQuery):
    """Player clicks surrender button."""
    user_id = callback.from_user.id
    game_id = callback.data.split(":")[2]

    ok, err, game = await surrender_ttt_game(callback.bot, game_id, user_id)
    if not ok or not game:
        await callback.answer(err, show_alert=True)
        return

    try:
        await callback.message.edit_text(
            render_game_text(game),
            reply_markup=get_ttt_game_keyboard(game),
            parse_mode="HTML"
        )
    except Exception:
        pass
    await callback.answer("🏳️ Ты сдался.")


@router.callback_query(F.data.startswith("ttt:cancel:"))
async def cb_ttt_cancel(callback: CallbackQuery):
    """Challenger clicks Cancel Challenge."""
    user_id = callback.from_user.id
    game_id = callback.data.split(":")[2]

    ok, msg = await cancel_ttt_challenge(game_id, user_id)
    if not ok:
        await callback.answer(msg, show_alert=True)
        return

    try:
        await callback.message.edit_text("❌ <b>Вызов в крестики-нолики отменен создателем.</b>", parse_mode="HTML")
    except Exception:
        pass
    await callback.answer(msg)


@router.callback_query(F.data.startswith("ttt:refresh:"))
async def cb_ttt_refresh(callback: CallbackQuery):
    """Refreshes remaining turn time on board."""
    game_id = callback.data.split(":")[2]
    game = active_ttt_games.get(game_id)
    if not game:
        await callback.answer("Игра завершена", show_alert=False)
        return
    try:
        await callback.message.edit_text(
            render_game_text(game),
            reply_markup=get_ttt_game_keyboard(game),
            parse_mode="HTML"
        )
    except Exception:
        pass
    await callback.answer(f"⏳ Осталось времени: {game.get_remaining_time()}с")


@router.callback_query(F.data.startswith("ttt:noop:"))
async def cb_ttt_noop(callback: CallbackQuery):
    """Clicked on an already occupied cell."""
    await callback.answer("⚠️ Клетка уже занята!", show_alert=False)
