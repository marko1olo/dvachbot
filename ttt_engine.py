# -*- coding: utf-8 -*-
"""
ttt_engine.py — High-Performance PvP Tic-Tac-Toe on Shekels (❌⭕ Крестики-Нолики) for ТГАЧ
================================================================================================
Features:
1. Challenge creation via Reply or Open Board Lobby (/ttt <bet>, /tictactoe, /кн, /крестики).
2. Interactive 3x3 Inline Keyboard with real-time state visualization (❌, ⭕, ⬜).
3. Strict 120-second turn timeout watchdog with auto-loss and pot transfer to opponent.
4. Flexible betting (50 ₪ to player's balance) with atomic escrow upon game start.
5. Juicy authentic 2ch-style board announcements via `process_new_post` upon win/draw/timeout/forfeit.
6. Fair draw mechanics with bet refund (minus 2% Abu micro-fee).
7. Complete integration with /casino, /duel, and /help.
"""

import time
import re
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
from common.task_manager import spawn_task

logger = logging.getLogger(__name__)

# ============================================================================
# CONFIGURATION & CONSTANTS
# ============================================================================

MIN_TTT_BET = 50
MAX_TTT_BET = 1_000_000
TURN_TIMEOUT_SECONDS = 120  # 2 minutes per turn
CHALLENGE_TIMEOUT_SECONDS = 600  # 10 minutes waiting for opponent to accept

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
    "«Проиграть в крестики-нолики в 2026 году — это диагноз.»",
    "«Вытри сопли и пиздуй в песочницу, омежка.»",
    "«Размотал сыча на трех клетках без регистрации и смс.»",
    "«Твой уровень аналитики — предсказывать вчерашнюю погоду.»",
    "«Задоминировал над деревенским аутистом. Легчайшие шекели.»",
    "«Линия замкнута, очко разорвано, деньги на базе.»",
    "«Это было избиение младенца на координатной сетке 3х3.»",
    "«С таким скиллом тебе только капчу в гугле кликать.»",
    "«Даже нейросеть 90-х годов сыграла бы умнее этого сыча.»",
    "«Уничтожен, деклассирован и пущен по кругу в три хода.»",
    "«Спас твои шекели от инфляции, забрав их себе в карман.»",
    "«Тактика галактического уровня разбила колхозный дефенс.»",
    "«Спасибо за донат, лошок. Батя пошел пить пиво.»",
    "«Три символа в ряд — и лузер отправляется плакать под плед.»",
    "«Учи матчасть, сынуля. Здесь играют взрослые дяди.»",
    "«Победа чистая, как слеза омежки, проебавшего баланс.»",
    "«Классический блицкриг по диагонали. Сыч даже мяукнуть не успел.»",
    "«Ты пытался думать, но перегрузил процессор и проебал.»",
    "«Очередной комнатный гроссмейстер отправлен мыть парашу.»",
    "«Твой дед в окопе и то лучше крестики чертил.»",
    "«Просто нажал три кнопки и забрал чужие карманные деньги.»",
    "«Крест поставлен не только на доске, но и на твоей карьере игрока.»",
    "«Быстро, грязно и унизительно. Всё по канонам двача.»",
    "«Скилл не пропьешь, а вот ты свои шекели только что проебал.»",
    "«Математика борды беспощадна к гуманитариям.»",
    "«Зашел, поставил крест/ноль, забрал банк. Изи пизи.»",
    "«У тебя было всего 9 клеток, и ты умудрился обосраться.»",
    "«Сычевать тебе теперь с нулевым балансом до следующего пейдея.»",
    "«Тактическое превосходство подтверждено чеком в Казну Абу.»",
    "«Такой позор даже в анонимном треде стыдно показать.»",
    "«Отрицательный рост твоего кошелька зафиксирован.»",
    "«Переигран по всем фронтам. Пшёл вон с поля боя.»",
    "«Логика вышла из чата, забрав с собой твои последние шекели.»",
    "«Этот гений думал, что клетка по центру его спасет. Наивный.»",
    "«Слил партию со свистом. Касса закрыта, анон обоссан.»",
    "«Победа на классе. Возвращайся, когда отрастишь мозг.»"
]

TTT_DRAW_PUNCHLINES = [
    "«Два аутиста 9 ходов смотрели друг на друга и скатали в ничью.»",
    "«Борьба была равна — играли два гения.»",
    "«Абу забрал 2% за аренду клеток и довольно хрюкнул.»",
    "«Никто не победил, но Абу остался в плюсе.»",
    "«Девять клеток тупости: ни победителя, ни мозгов.»",
    "«Два сыча уперлись рогами в забор и поделили ноль на ноль.»",
    "«Битва титанов специальной олимпиады закончилась пшиком.»",
    "«Заставили всю доску мусором и разошлись ни с чем.»",
    "«Великие стратеги перехитрили сами себя. Ничья, епта.»",
    "«Абу довольно потирает лапки: 2% комиссии не пахнут.»",
    "«Ничьей в 3х3 гордятся только выпускники коррекционных школ.»",
    "«Столько пота ради того, чтобы просто покормить комиссию Абу.»",
    "«Оба так боялись проиграть, что забыли, как побеждать.»",
    "«Ни рыбы, ни мяса — два омежки скатали в тухлый пат.»",
    "«Клетки кончились, фантазия тоже. Расходимся, пацаны.»",
    "«Ничейный высер вселенского масштаба на 9 ячеек.»",
    "«Суммарный IQ участников равен номеру последней пустой клетки.»",
    "«Поздравляю, вы оба одинаково бездарны!»",
    "«Два сверхразума заблокировали друг друга и потеряли шекели на комиссии.»",
    "«Боевая ничья двух инвалидов логического фронта.»",
    "«Сычевали 9 ходов, а в итоге только обогатили Казну Абу.»",
    "«Так упорно блокировали ходы, будто защищали девственность.»",
    "«Оба достойны параши за такую безыдейную игру.»",
    "«Доска заполнена до отказа, тред зевает от скуки.»",
    "«Паритет двух аутистов зафиксирован протоколом борды.»",
    "«Ни один не смог нащупать победу даже с лупой.»",
    "«Комиссия Абу списана, гордость утеряна, ничья оформлена.»",
    "«Два барана на мосту 3х3. Итог предсказуемо уныл.»",
    "«Играли на интерес, а получилось как всегда — ничья и стыд.»",
    "«Слишком много осторожности для игры на девять клеток.»",
    "«Ничья в крестиках — верный признак глубокого аутизма обоих.»",
    "«Сухой остаток: минус 2% налога и ноль удовольствия.»"
]

TTT_TIMEOUT_PUNCHLINES = [
    "«Уснул лицом в клавиатуру прямо во время ответственного хода.»",
    "«Не выдержал накала страстей и откинулся в астрал за 120 секунд.»",
    "«Таймер 120 секунд оказался непреодолимым препятствием для сыча.»",
    "«120 секунд тишины — и шекели испарились в чужой карман.»",
    "«Думал над ходом целых 120 секунд в игре 3х3 и в итоге обосрался.»",
    "«Слишком сложно для одноклеточного: 120 секунд пролетели, мозг не включился.»",
    "«Сыч ушел варить пельмени и забыл, что на таймере всего 120 секунд.»",
    "«Две минуты смотрел на три клетки как баран на новые ворота.»",
    "«120 секунд позора! Даже улитка успела бы тыкнуть в крестик.»",
    "«Завис намертво. Перезагрузите сыча, он сломался на 120-й секунде.»",
    "«Время вышло, шекели тю-тю. Не щёлкай клювом 120 секунд!»",
    "«Пока этот тормоз рожал ход 120 секунд, оппонент успел постареть.»",
    "«Таймаут для дауна: 120 секунд на ход в крестиках-ноликах — это перебор.»",
    "«Мамка позвала кушать борщ прямо посреди партии. Слив по таймауту!»",
    "«120 секунд медитировал на пустую клетку и познал дзен поражения.»",
    "«Просрал партию просто потому, что забыл, как дышать за 120 секунд.»",
    "«Таймер тикал, очко играло, 120 секунд кончились — техлуз в копилку.»",
    "«Пинг до мозга превысил допустимый лимит в 120 секунд.»",
    "«Легчайшая победа над спящей омежкой за 120 секунд ожидания.»",
    "«Не осилил тайм-менеджмент на 120 секунд. Шагай обратно в детсад.»",
    "«Пока сыч тупил 120 секунд, соперник уже считал профит.»",
    "«120 секунд апатии и депрессии привели к потере банка.»",
    "«АФК-аутист подарил шекели бате без единого нажатия за 120 секунд.»",
    "«Мыслительный процесс длиною в 120 секунд завершился полным крахом.»",
    "«Две минуты гипнотизировал экран и всё равно проспал дедлайн.»",
    "«120 секунд на ход — и всё равно тех-луз! Пора менять провайдера мозгов.»",
    "«Уснул в луже собственной подливы за 120 секунд до победы.»",
    "«Таймер безжалостен к тормозам: 120 секунд истекли, забирайте труп.»",
    "«Казалось бы, 9 клеток, но сычу не хватило даже 120 секунд.»",
    "«Технический нокаут лентяю, проспавшему ход на 120 секунд.»",
    "«Слился по таймеру как последний казуал. 120 секунд коту под хвост!»",
    "«120 секунд молчания в эфире. Трус признан недееспособным.»"
]

TTT_SURRENDER_PUNCHLINES = [
    "«Выбросил белый флаг и позорно убежал с доски.»",
    "«Осознал бесперспективность бытия и нажал F.»",
    "«Сдался без боя, подарив сопернику легчайшие шекели.»",
    "«Увидел диагональ оппонента и наложил в штаны прямо на доску.»",
    "«Капитулировал, едва почувствовав запах тактического члена во рту.»",
    "«Слишком больно для неокрепшей психики — сыч ливнул в слезах.»",
    "«Нажал 'Сдаться', чтобы спасти остатки своего разбитого эго.»",
    "«Дрогнула рука омежки — белый флаг взвился над полем боя.»",
    "«Сбежал с доски быстрее, чем батя за хлебом.»",
    "«Понял, что попал в вилку, и предпочел позорную сдачу честному мату.»",
    "«Сдался в крестиках-ноликах... Ты вообще понимаешь, насколько ты жалок?»",
    "«Самослив зафиксирован. Шекели у победителя, позор у беглеца.»",
    "«Выронил мышку из вспотевших ладошек и нажал капитуляцию.»",
    "«Так испугался чужого крестика, что нажал сдаться на втором ходу.»",
    "«Позорный лив из дуэли. Смыть это пятно уже не получится.»",
    "«Сложил полномочия гроссмейстера и уполз под плинтус.»",
    "«Сдался досрочно. Видимо, вспомнил, что утюг дома не выключил.»",
    "«Осознал глубину своего умственного дна и нажал кнопку сдачи.»",
    "«Испугался неминуемого унижения и капитулировал заранее.»",
    "«Слив засчитан, омежка. Иди поплачь в подушку.»",
    "«Белый флаг на сукне! Досрочный финиш для безвольного сыча.»",
    "«Подарил победу на блюдечке. Настоящий меценат для победителя!»",
    "«Даже доиграть смелости не хватило. Полная капитуляция духа.»",
    "«Ливнул из партии, как типичный школьник из доты.»",
    "«Сдался, признав себя абсолютным нулем перед чужим крестиком.»",
    "«Позорное бегство с поля 3х3. Тред аплодирует твоей трусости!»",
    "«Не вывез морального прессинга и нажал кнопку капитуляции.»",
    "«Сдался без сопротивления, лишь бы прекратить этот позор.»",
    "«Убежал с доски, сверкая пятками и роняя кал.»",
    "«Капитуляция оформлена по всем правилам омежьего этикета.»",
    "«Позорная сдача — лучший подарок для твоего оппонента.»",
    "«Сложил лапки и отдал банк. Ни капли чести, сплошной позор.»"
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
    finished_at: float = 0.0
    winning_line: Optional[Tuple[int, int, int]] = None
    timeout_task: Optional[asyncio.Task] = None
    bot_instance: Optional[Bot] = None
    player_msgs: Dict[int, Tuple[int, int]] = field(default_factory=dict)
    broadcast_msgs: List[Tuple[int, int]] = field(default_factory=list)

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


def get_ttt_lobby_keyboard(bet: int, balance: int = 1000, target_user_id: int = 0) -> InlineKeyboardMarkup:
    """Lobby for configuring bet before launching challenge."""
    bet = max(MIN_TTT_BET, min(MAX_TTT_BET, bet))
    presets = get_adaptive_bet_presets(balance, bet)
    t_tag = f":{target_user_id}" if target_user_id else ":0"
    preset_row = [
        InlineKeyboardButton(text=format_bet_amount(p), callback_data=f"ttt:lobby:{p}{t_tag}")
        for p in presets
    ]
    half_bet = max(MIN_TTT_BET, bet // 2)
    double_bet = min(MAX_TTT_BET, min(int(balance), bet * 2)) if balance >= bet * 2 else bet
    max_bet = max(MIN_TTT_BET, min(MAX_TTT_BET, int(balance)))
    ctrl_row = [
        InlineKeyboardButton(text="/2", callback_data=f"ttt:lobby:{half_bet}{t_tag}"),
        InlineKeyboardButton(text="x2", callback_data=f"ttt:lobby:{double_bet}{t_tag}"),
        InlineKeyboardButton(text="💰 ВА-БАНК", callback_data=f"ttt:lobby:{max_bet}{t_tag}"),
    ]
    buttons = [
        [InlineKeyboardButton(text=f"⚔️ Бросить вызов ({format_bet_amount(bet)})", callback_data=f"ttt:create:{bet}{t_tag}")],
        preset_row,
        ctrl_row,
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
            f"⏳ <i>Вызов активен 10 минут. Нажми кнопку ниже или напиши <code>/ttt accept</code>, чтобы принять бой!</i>"
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
            f"{time_warn}<b>На ход: 120 сек</b> (Осталось: <code>{rem_time}с</code>)\n"
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
            f"⏰ <b>ИГРА ЗАВЕРШЕНА: ТАЙМАУТ (120 сек)!</b>\n\n"
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


async def sync_ttt_screens(bot: Bot, game: TicTacToeGame):
    """
    Simultaneously edits active game messages for BOTH players in their personal chats,
    ensuring each player gets the updated 3x3 board and active turn status.
    Also clears buttons for third-party broadcast viewers when challenge is accepted.
    """
    if not bot or not game:
        return

    p1 = game.challenger_id
    p2 = game.opponent_id
    player_msgs = getattr(game, "player_msgs", None)
    if player_msgs is None:
        game.player_msgs = {}
        player_msgs = game.player_msgs

    # Fallback for p1
    if p1 and p1 not in player_msgs and game.chat_id and game.msg_id:
        player_msgs[p1] = (game.chat_id, game.msg_id)

    rendered_text = render_game_text(game)
    kb = get_ttt_game_keyboard(game)

    # 1. Update both active players' messages
    for uid in (p1, p2):
        if not uid or uid not in player_msgs:
            continue
        chat_id, msg_id = player_msgs[uid]
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=msg_id,
                text=rendered_text,
                reply_markup=kb,
                parse_mode="HTML"
            )
        except TelegramBadRequest as e:
            if "message is not modified" not in str(e).lower():
                logger.debug(f"[TTT] sync edit failed for user {uid}: {e}")
        except Exception as e:
            logger.debug(f"[TTT] sync unexpected error for user {uid}: {e}")

    # 2. If game started or finished, neutralize other broadcast copies
    if p2 and getattr(game, "broadcast_msgs", None):
        anon_x = get_anon_id(p1)
        anon_o = get_anon_id(p2)
        other_text = (
            f"❌⭕ <b>КРЕСТИКИ-НОЛИКИ: ВЫЗОВ ПРИНЯТ!</b>\n\n"
            f"Партия на <code>{game.bet:,} ₪</code> уже началась между Аноном [{anon_x}] и Аноном [{anon_o}].\n"
            f"Мест за столом больше нет."
        )
        remaining_bcast = []
        for chat_id, msg_id in list(game.broadcast_msgs):
            if any((chat_id, msg_id) == player_msgs.get(p) for p in (p1, p2) if p in player_msgs):
                remaining_bcast.append((chat_id, msg_id))
                continue
            try:
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=msg_id,
                    text=other_text,
                    reply_markup=None,
                    parse_mode="HTML"
                )
            except Exception:
                pass
        game.broadcast_msgs = remaining_bcast


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


async def send_pvp_direct_notification(bot: Any, user_id: int, text: str) -> bool:
    """
    Safely sends a private notification DM to a user on Telegram with full error suppression.
    Catches TelegramForbiddenError, TelegramBadRequest, and generic exceptions cleanly.
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
        logger.debug(f"Direct notification suppressed for user {user_id}: {e}")
        return False
    except Exception as e:
        logger.warning(f"Direct notification failed for user {user_id}: {e}")
        return False


# ============================================================================
# TIMEOUT WATCHDOG (120 Seconds Turn Timer)
# ============================================================================

async def _turn_timeout_watcher(game_id: str, turn_user_id: int) -> None:
    """Asynchronous background watchdog enforcing strictly 120 seconds per turn with live dynamic countdown updates."""
    try:
        # Tick in 10-second increments for dynamic live countdown updates
        for _ in range(TURN_TIMEOUT_SECONDS // 10):
            await asyncio.sleep(10)
            async with ttt_lock:
                game = active_ttt_games.get(game_id)
                if not game or game.status != "active" or game.current_turn != turn_user_id:
                    return
            # Dynamic live message edit if game is still running
            if game.get_remaining_time() > 0 and game.bot_instance and game.chat_id and game.msg_id:
                try:
                    await game.bot_instance.edit_message_text(
                        chat_id=game.chat_id,
                        message_id=game.msg_id,
                        text=render_game_text(game),
                        reply_markup=get_ttt_game_keyboard(game),
                        parse_mode="HTML"
                    )
                except Exception:
                    pass

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
            game.finished_at = time.time()
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
                f"Техническое поражение (таймаут 120с) в КН против [{get_anon_id(winner_id)}]"
            )

        # Update message in chats for BOTH players
        if game.bot_instance:
            await sync_ttt_screens(game.bot_instance, game)

        # Post 2ch announcement to board
        winner_anon = get_anon_id(winner_id)
        loser_anon = get_anon_id(loser_id)
        punchline = random.choice(TTT_TIMEOUT_PUNCHLINES)
        announcement = (
            f"💤 <b>[КРЕСТИКИ-НОЛИКИ / ТАЙМАУТ]</b>\n"
            f"<b>Анон [{loser_anon}]</b> не справился с таймером 120 сек в битве на <b>{game.pot:,} ₪</b>!\n\n"
            f"🏆 Техническая победа присуждается <b>Анону [{winner_anon}]</b>!\n"
            f"💰 Чистый занос: <code>+{net_win:,} ₪</code> <i>(Рейк Абу: {rake:,} ₪)</i>\n\n"
            f"<i>{punchline}</i>"
        )
        if game.bot_instance:
            win_notify_text = (
                f"👑 <b>ПОБЕДА В КРЕСТИКАХ-НОЛИКАХ #{game_id}!</b>\n\n"
                f"Соперник пропустил таймер хода (120 сек).\n"
                f"💰 Твой чистый выигрыш: <b>+{net_win:,} ₪</b> (банк {game.pot:,} ₪ за вычетом рейка {rake:,} ₪ в Казну Абу) зачислен на баланс!"
            )
            lose_notify_text = (
                f"⏱️ <b>ТАЙМАУТ В КРЕСТИКАХ-НОЛИКАХ #{game_id}</b>\n\n"
                f"Ты не сделал ход за 120 секунд (техническое поражение).\n"
                f"💸 Списано: <b>-{game.bet:,} ₪</b>."
            )
            asyncio.create_task(send_pvp_direct_notification(game.bot_instance, winner_id, win_notify_text))
            asyncio.create_task(send_pvp_direct_notification(game.bot_instance, loser_id, lose_notify_text))
            await publish_ttt_board_announcement(game.bot_instance, game.board_id, announcement)

    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"Error in TTT turn timeout watcher: {e}", exc_info=True)


def _reset_and_start_timer(game: TicTacToeGame) -> None:
    """Cancels old timer task and spawns a fresh 120s turn timer task."""
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
    from common.database import is_shadow_muted as check_db_shadow_muted
    from common.bot_helpers import check_user_is_muted
    if await check_db_shadow_muted(challenger_id, board_id, db=db) or await check_user_is_muted(db, challenger_id, board_id):
        return False, "🔇 Замученным нельзя создавать игры в крестики-нолики.", None

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
        if game.status not in ("waiting",):
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

        # Mark state to prevent double-accept race condition
        game.status = "accepting"


    def _ttt_rollback():
        g = active_ttt_games.get(game_id)
        if g and g.status == "accepting":
            g.status = "waiting"

    # Mute guard: check opponent and challenger before committing escrow
    from common.database import is_shadow_muted as check_db_shadow_muted
    from common.bot_helpers import check_user_is_muted
    if await check_db_shadow_muted(opponent_id, game.board_id, db=db) or await check_user_is_muted(db, opponent_id, game.board_id):
        _ttt_rollback()
        return False, "🔇 Замученным нельзя принимать игры в крестики-нолики.", None
    if await check_db_shadow_muted(game.challenger_id, game.board_id, db=db) or await check_user_is_muted(db, game.challenger_id, game.board_id):
        game.status = "cancelled"
        user_active_ttt_session.pop(game.challenger_id, None)
        return False, "❌ Создатель вызова был замучен. Вызов отменён.", None

    async with ttt_lock:

        # Escrow verification under db_lock
        async with db_lock:
            ch_bal = await get_user_global_balance(db, game.challenger_id)
            op_bal = await get_user_global_balance(db, opponent_id)

            if ch_bal < game.bet:
                # Challenger can no longer pay — cancel cleanly without nuking game object
                game.status = "cancelled"
                user_active_ttt_session.pop(game.challenger_id, None)
                return False, f"❌ У создателя вызова [{get_anon_id(game.challenger_id)}] изменился баланс. Вызов отменен.", None

            if op_bal < game.bet:
                _ttt_rollback()
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
                _ttt_rollback()
                return False, "❌ Ошибка списания средств. Попробуй снова.", None

            await record_user_transaction(db, game.challenger_id, -game.bet, "ttt", f"Ставка в КН против [{get_anon_id(opponent_id)}]")
            await record_user_transaction(db, opponent_id, -game.bet, "ttt", f"Ставка в КН против [{get_anon_id(game.challenger_id)}]")

        # Launch Game
        game.opponent_id = opponent_id
        game.status = "active"
        game.current_turn = game.challenger_id  # ❌ starts first
        game.bot_instance = bot
        user_active_ttt_session[opponent_id] = game_id

        # Start 120s turn timer
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
            game.finished_at = time.time()
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
            game.finished_at = time.time()
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
        bot_to_use = bot or game.bot_instance
        if bot_to_use:
            win_notify_text = (
                f"👑 <b>ПОБЕДА В КРЕСТИКАХ-НОЛИКАХ #{game.game_id}!</b>\n\n"
                f"Ты собрал выигрышную линию!\n"
                f"💰 Твой чистый выигрыш: <b>+{net_win:,} ₪</b> (банк {game.pot:,} ₪ за вычетом рейка {rake:,} ₪ в Казну Абу) зачислен на баланс!"
            )
            lose_notify_text = (
                f"💀 <b>ПОРАЖЕНИЕ В КРЕСТИКАХ-НОЛИКАХ #{game.game_id}</b>\n\n"
                f"Соперник собрал выигрышную линию.\n"
                f"💸 Списано: <b>-{game.bet:,} ₪</b>."
            )
            asyncio.create_task(send_pvp_direct_notification(bot_to_use, game.winner_id, win_notify_text))
            asyncio.create_task(send_pvp_direct_notification(bot_to_use, loser_id, lose_notify_text))
            await publish_ttt_board_announcement(bot_to_use, game.board_id, announcement)

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
        bot_to_use = bot or game.bot_instance
        if bot_to_use:
            draw_notify_text = (
                f"🤝 <b>НИЧЬЯ В КРЕСТИКАХ-НОЛИКАХ #{game.game_id}</b>\n\n"
                f"Все 9 клеток заняты, ничья!\n"
                f"💰 Твоя ставка возвращена: <b>+{refund:,} ₪</b> (за вычетом 2% в Казну Абу)."
            )
            asyncio.create_task(send_pvp_direct_notification(bot_to_use, game.challenger_id, draw_notify_text))
            asyncio.create_task(send_pvp_direct_notification(bot_to_use, game.opponent_id, draw_notify_text))
            await publish_ttt_board_announcement(bot_to_use, game.board_id, announcement)

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
        game.finished_at = time.time()
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
    bot_to_use = bot or game.bot_instance
    if bot_to_use:
        win_notify_text = (
            f"👑 <b>ПОБЕДА В КРЕСТИКАХ-НОЛИКАХ #{game_id}!</b>\n\n"
            f"Соперник сдался без боя!\n"
            f"💰 Твой чистый выигрыш: <b>+{net_win:,} ₪</b> зачислен на баланс!"
        )
        lose_notify_text = (
            f"🏳️ <b>КАПИТУЛЯЦИЯ В КРЕСТИКАХ-НОЛИКАХ #{game_id}</b>\n\n"
            f"Ты сдался.\n"
            f"💸 Списано: <b>-{game.bet:,} ₪</b>."
        )
        asyncio.create_task(send_pvp_direct_notification(bot_to_use, winner_id, win_notify_text))
        asyncio.create_task(send_pvp_direct_notification(bot_to_use, loser_id, lose_notify_text))
        await publish_ttt_board_announcement(bot_to_use, game.board_id, announcement)

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


@router.message(F.text.regexp(r"^/(?:ttt|tictactoe|кн|крестики)(\d+[kк]?|all|всё|все)(?:\s+.*)?$", flags=re.IGNORECASE))
async def cmd_ttt_shorthand(message: Message, board_id: Optional[str] = None, stream: str = "ru"):
    if not message.text:
        return
    m = re.match(r"^/(?:ttt|tictactoe|кн|крестики)(\d+[kк]?|all|всё|все)(?:\s+(.*))?$", message.text.strip(), re.IGNORECASE)
    if not m:
        return
    amt = m.group(1)
    rest = m.group(2)
    message.text = f"/ttt {amt}" + (f" {rest}" if rest else "")
    return await cmd_ttt(message, board_id=board_id, stream=stream)


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
            # Check if user is already participating in an active game
            active_game = None
            for gid, g in list(active_ttt_games.items()):
                if g.status == "active" and (g.challenger_id == user_id or g.opponent_id == user_id):
                    active_game = g
                    break
            if active_game:
                whose_turn = "Твой ход! Выбирай клетку на поле ниже." if active_game.current_turn == user_id else "Ход соперника, ожидай..."
                await message.answer(
                    f"⚔️ <b>Партия уже идёт!</b> {whose_turn}\n\n" + render_game_text(active_game),
                    reply_markup=get_ttt_game_keyboard(active_game),
                    parse_mode="HTML"
                )
                return

            await message.answer("❌ Нет активных вызовов в крестики-нолики на этой борде.")
            return

        ok, err, game = await accept_ttt_challenge(message.bot, found_game_id, user_id)
        if not ok:
            await message.answer(err)
            return

        # Update challenge message in challenger's chat
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

        # Send interactive game board to the accepting player
        try:
            whose_turn = "Ход соперника (❌)" if game.current_turn != user_id else "Твой ход!"
            await message.answer(
                f"⚔️ <b>Вызов принят!</b> {whose_turn}\n\n" + render_game_text(game),
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

    # Mute guard: zamuted users cannot accept, create, or open lobby
    db = await get_pool()
    from common.database import is_shadow_muted as check_db_shadow_muted
    from common.bot_helpers import check_user_is_muted
    if await check_db_shadow_muted(user_id, board_id, db=db) or await check_user_is_muted(db, user_id, board_id):
        await message.answer("🔇 Замученным нельзя играть в крестики-нолики.")
        return

    # Target user via Reply (if any)
    target_user_id = None
    if message.reply_to_message:
        try:
            from common.bot_helpers import get_author_id_by_reply
            target_user_id = await get_author_id_by_reply(message)
        except Exception:
            target_user_id = message.reply_to_message.from_user.id if (message.reply_to_message.from_user and not message.reply_to_message.from_user.is_bot) else None
        if target_user_id == user_id or target_user_id == 0:
            target_user_id = None

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
            f"• ⏳ <b>Строго 120 секунд на ход!</b> При таймауте — авто-луз и передача банка.\n"
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
    game.player_msgs[user_id] = (sent.chat.id, sent.message_id)
    game.broadcast_msgs.append((sent.chat.id, sent.message_id))

    # Broadcast challenge to active board users
    try:
        from shared_state import board_data as _board_data
        active_users = list(_board_data.get(board_id, {}).get('users', {}).get('active', []))
        for uid in active_users:
            if uid == user_id:
                continue
            if target_user_id is not None and uid != target_user_id:
                continue
            try:
                bcast_sent = await message.bot.send_message(
                    chat_id=uid,
                    text=render_game_text(game),
                    reply_markup=kb,
                    parse_mode="HTML"
                )
                game.broadcast_msgs.append((uid, bcast_sent.message_id))
            except Exception:
                pass
    except Exception:
        pass

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
    target_user_id = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() and int(parts[3]) > 0 else 0
    
    db = await get_pool()
    async with db_lock:
        balance = await get_user_global_balance(db, user_id)
    
    bet = max(MIN_TTT_BET, min(MAX_TTT_BET, min(int(balance), bet) if balance >= MIN_TTT_BET else MIN_TTT_BET))
    kb = get_ttt_lobby_keyboard(bet, balance=int(balance), target_user_id=target_user_id)
    target_str = f"🎯 <b>Цель:</b> Анон <code>[ID:{target_user_id}]</code>\n" if target_user_id else ""
    caption = (
        f"❌⭕ <b>КРЕСТИКИ-НОЛИКИ НА ШЕКЕЛИ (PvP)</b>\n\n"
        f"💳 Твой баланс: <code>{int(balance):,} ₪</code>\n"
        f"💰 Выбранная ставка: <code>{bet:,} ₪</code>\n"
        f"{target_str}\n"
        f"Выбери размер ставки и создай вызов на доску:"
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
    target_user_id = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() and int(parts[3]) > 0 else None

    ok, err, game = await create_ttt_challenge(
        bot=callback.bot,
        chat_id=callback.message.chat.id,
        board_id=board_id,
        challenger_id=user_id,
        bet=bet,
        target_user_id=target_user_id,
    )
    if not ok or not game:
        await callback.answer(err, show_alert=True)
        return

    kb = get_ttt_challenge_keyboard(game.game_id)
    sent = await callback.message.answer(render_game_text(game), reply_markup=kb, parse_mode="HTML")
    game.msg_id = sent.message_id
    game.player_msgs[user_id] = (sent.chat.id, sent.message_id)
    game.broadcast_msgs.append((sent.chat.id, sent.message_id))

    # Broadcast challenge to active board users
    try:
        from shared_state import board_data as _board_data
        active_users = list(_board_data.get(board_id, {}).get('users', {}).get('active', []))
        for uid in active_users:
            if uid == user_id:
                continue
            if target_user_id is not None and uid != target_user_id:
                continue
            try:
                bcast_sent = await callback.bot.send_message(
                    chat_id=uid,
                    text=render_game_text(game),
                    reply_markup=kb,
                    parse_mode="HTML"
                )
                game.broadcast_msgs.append((uid, bcast_sent.message_id))
            except Exception:
                pass
    except Exception:
        pass

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
        logger.warning(f"[TTT] accept FAILED gid={game_id} uid={user_id}: {err}")
        await callback.answer(err, show_alert=True)
        return

    # Track opponent's message so sync_ttt_screens can update both screens
    game.player_msgs[user_id] = (callback.message.chat.id, callback.message.message_id)

    await sync_ttt_screens(callback.bot, game)
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

    await sync_ttt_screens(callback.bot, game)
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

    await sync_ttt_screens(callback.bot, game)
    await callback.answer("🏳️ Ты сдался.")


@router.callback_query(F.data.startswith("ttt:cancel:"))
async def cb_ttt_cancel(callback: CallbackQuery):
    """Challenger clicks Cancel Challenge."""
    user_id = callback.from_user.id
    game_id = callback.data.split(":")[2]

    game = active_ttt_games.get(game_id)
    broadcast_msgs = list(getattr(game, "broadcast_msgs", [])) if game else []

    ok, msg = await cancel_ttt_challenge(game_id, user_id)
    if not ok:
        await callback.answer(msg, show_alert=True)
        return

    try:
        await callback.message.edit_text("❌ <b>Вызов в крестики-нолики отменен создателем.</b>", parse_mode="HTML")
    except Exception:
        pass

    for chat_id, msg_id in broadcast_msgs:
        if chat_id == callback.message.chat.id and msg_id == callback.message.message_id:
            continue
        try:
            await callback.bot.edit_message_text(
                chat_id=chat_id,
                message_id=msg_id,
                text="❌ <b>Вызов в крестики-нолики отменен создателем.</b>",
                reply_markup=None,
                parse_mode="HTML"
            )
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


# ============================================================================
# BACKGROUND WATCHDOG FOR CHALLENGE EXPIRATION
# ============================================================================

async def ttt_watchdog_step(bot=None):
    """Checks for expired pending challenges in TTT (120s) and cleans them up with message edits."""
    now = time.time()
    expired_pending = []
    async with ttt_lock:
        for gid, game in list(active_ttt_games.items()):
            if game.status == "finished":
                fin_ts = getattr(game, 'finished_at', 0.0) or game.created_at
                if now - fin_ts > 60:
                    active_ttt_games.pop(gid, None)
                continue
            if game.status == "waiting" and (now - game.created_at) > CHALLENGE_TIMEOUT_SECONDS:
                game.status = "finished"
                game.finished_at = now
                game.finish_reason = "cancelled"
                user_active_ttt_session.pop(game.challenger_id, None)
                expired_pending.append(gid)

    for gid in expired_pending:
        game = active_ttt_games.get(gid)
        if not game:
            continue
        bot_to_use = bot or game.bot_instance
        if bot_to_use and game.challenger_id:
            exp_dm_text = (
                f"⏳ <b>ВЫЗОВ В КРЕСТИКИ-НОЛИКИ ИСТЕК</b>\n\n"
                f"Ни один анон не принял твой вызов на <b>{game.bet:,} ₪</b> за 10 минут.\n"
                f"Вызов аннулирован, ставка не списывалась."
            )
            spawn_task(send_pvp_direct_notification(bot_to_use, game.challenger_id, exp_dm_text), name="pvp_notify_ttt_expired")

        if bot_to_use and getattr(game, "broadcast_msgs", None):
            for chat_id, msg_id in list(game.broadcast_msgs):
                try:
                    await bot_to_use.edit_message_text(
                        chat_id=chat_id,
                        message_id=msg_id,
                        text=(
                            "⏳ <b>ВЫЗОВ В КРЕСТИКИ-НОЛИКИ ИСТЕК!</b>\n\n"
                            "Ни один анон не принял вызов за 10 минут.\n"
                            "Вызов аннулирован, ставка не списана."
                        ),
                        reply_markup=None,
                        parse_mode="HTML"
                    )
                except Exception:
                    pass
        elif bot_to_use and game.chat_id and game.msg_id:
            try:
                await bot_to_use.edit_message_text(
                    chat_id=game.chat_id,
                    message_id=game.msg_id,
                    text=(
                        "⏳ <b>ВЫЗОВ В КРЕСТИКИ-НОЛИКИ ИСТЕК!</b>\n\n"
                        "Ни один анон не принял вызов за 10 минут.\n"
                        "Вызов аннулирован, ставка не списана."
                    ),
                    reply_markup=None,
                    parse_mode="HTML"
                )
            except Exception:
                pass


async def start_ttt_watchdog_loop(bot):
    """Continuous background watchdog loop for TTT challenge expiration."""
    logger.info("TTT watchdog loop started.")
    while True:
        try:
            await ttt_watchdog_step(bot)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in ttt_watchdog_loop: {e}")
        await asyncio.sleep(3.0)
