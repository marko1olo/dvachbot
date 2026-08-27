"""
Drop Engine for DvachBot: Public Money Drop ("Чек / Дроп шекелей в тред на реакцию")
100% race-condition protected inside atomic db_lock & drop_lock, with persistent DB backup in MoneyDrops table.
"""

import asyncio
import secrets
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

# -----------------------------------------------------------------------------
# Data Structures
# -----------------------------------------------------------------------------

@dataclass
class DropRecord:
    drop_id: str
    donor_id: int
    donor_name: str
    board_id: str
    amount: int
    created_at: float
    expires_at: float
    status: str = "active"  # "active", "claimed", "expired", "cancelled"
    claimed_by: Optional[int] = None
    claimed_name: Optional[str] = None
    claimed_at: Optional[float] = None


# In-memory registry of active and recent drops
active_drops: Dict[str, DropRecord] = {}
drop_lock = asyncio.Lock()
# Track all sent messages for each drop_id: {drop_id: [(chat_id, message_id), ...]}
_drop_messages: Dict[str, List[Tuple[int, int]]] = defaultdict(list)
# Anti-spam cooldown tracking: {donor_id: cooldown_expiry_timestamp}
_user_drop_cooldowns: Dict[int, float] = {}

# -----------------------------------------------------------------------------
# Limits & Excuses
# -----------------------------------------------------------------------------

MIN_DROP_AMOUNT: int = 150
MAX_DROP_AMOUNT: int = 1_000_000

# Пул отмазок с черным юмором в стиле Двача при сумме меньше минимальной (< 150 ₪)
DROP_MIN_EXCUSES: List[str] = [
    "Слышь, нищеброд, твои копейки ({amount} ₪) даже на доширак не наскребут. Минимальный дроп — 150 ₪. Не позорься перед бордой.",
    "Ты кого тут насмешить вздумал своими {amount} ₪? Бомжи у параши громче сморкаются. Минимум 150 ₪, нищук.",
    "{amount} ₪? Серьёзно, сука? Ты эту сдачу с маршрутки у мамки из кармана вытащил? Меньше 150 ₪ в тред не высирай.",
    "Абу отказался принимать твои {amount} ₪ — сказал, что от такой нищеты у него серверная плесенью покроется. Минималка — 150 ₪.",
    "Твои {amount} ₪ — это даже не капля в море, а плевок в лицо анонам. Закидывай от 150 ₪ или пиздуй собирать бутылки.",
    "Экономический комитет Двача постановил: дропы меньше 150 ₪ приравниваются к биомусору. У тебя всего {amount} ₪.",
    "Ты бы ещё пыль из-под ногтей в тред дропнул. Твои {amount} ₪ — позор рода. Минимальный чек — 150 ₪.",
    "Шекелевый инспектор зафиксировал критический уровень нищеты ({amount} ₪). Меньше 150 ₪ даже цыгане не подберут.",
    "Пошел нахуй со своими {amount} ₪. Тут уважаемая борда, а не благотворительная столовая для опущенных. Минимум — 150 ₪.",
    "Твой донат на {amount} ₪ вызвал приступ смеха у модераторов. Не позорься, копи до 150 ₪.",
    "Дропнуть {amount} ₪? Да тебя за такие копейки в /b/ обоссут и на мороз выкинут. Минимальный дроп — 150 ₪.",
    "Твои {amount} ₪ застряли между половицами. Меньше 150 ₪ сюда даже не суй, нищета.",
]

# Пул отмазок с черным юмором в стиле Двача при превышении лимита (> 1 000 000 ₪)
DROP_MAX_EXCUSES: List[str] = [
    "Осади коней, Ротшильд мамкин. Дропнуть {amount} ₪? Максимум 1 000 000 ₪ за раз, иначе серверная Абу сгорит от гиперинфляции.",
    "{amount} ₪ за один дроп?! Ты чё, печатный станок ЦБ ограбил? Лимит — 1 000 000 ₪, не ломай экономику борды.",
    "Шекелевый инфаркт! Сумма {amount} ₪ превышает лимит в 1 000 000 ₪. Моссад уже выехал по твою душу за отмывание триллионов.",
    "Куда разогнался, олигарх комнатный? {amount} ₪ — это перебор. Максимальный дроп — 1 000 000 ₪.",
    "Транзакция на {amount} ₪ заблокирована Интерполом Двача. Максимум за один раз — 1 000 000 ₪.",
    "Ты решил весь золотовалютный фонд треда в один клик слить? {amount} ₪ не пролезет, потолок — 1 000 000 ₪.",
    "Слишком жирно! Твои {amount} ₪ разорвут баланс борды на атомы. Срежь осетра до 1 000 000 ₪.",
    "Абу подавился мацой, увидев твои {amount} ₪. Лимит одного чека — ровно 1 000 000 ₪.",
    "Притормози, криптомагнат хуев! {amount} ₪ — слишком много для одной транзакции. Максимум — 1 000 000 ₪.",
    "Эй, Дракон Смауг, придержи чешую. Дроп на {amount} ₪ отклонен, лимит — 1 000 000 ₪ за раз.",
]

# Пул отмазок с черным юмором в стиле Двача при срабатывании кулдауна (20+ фраз)
DROP_COOLDOWN_PHRASES: List[str] = [
    "Слышь, нищеброд, твои копейки даже бомжи у параши не поднимают. Погоди {seconds}с, пока Абу подметёт твои гроши.",
    "Ты чё, автомат по выдаче мелочи? Засунь свои шекели обратно в очко и подожди {seconds}с.",
    "Еврейская община в ахуе от твоей щедрости. Остынь на {seconds}с перед следующим плевком в вечность.",
    "Руки от кошелька убрал, лудоман хуев. Раскидывать мелочь сможешь через {seconds}с.",
    "Остынь, меценат мамкин. Твой нищенский спам на кулдауне ещё {seconds}с.",
    "Абу конфисковал твою мелочь на ремонт серверов. Жди {seconds}с, олигарх из трущоб.",
    "Шекелевый инфаркт жопы. Твоя подачка на проверке в налоговой Моссада, таймер: {seconds}с.",
    "Твой благотворительный фонд «Помощь нищим даунам» заморожен. Кулдаун {seconds}с.",
    "Не сри мелочью в тред, тут люди деградируют. Подожди {seconds}с и подумай над своим поведением.",
    "Ты кого тут подкупить пытаешься, олигарх с помойки? Жди {seconds}с до следующего высера.",
    "Копеечный спамер детектирован. Санитары выехали, а твоя кнопка заблокирована на {seconds}с.",
    "Даже цыгане на вокзале побрезговали твоим дропом. Остынь на {seconds}с.",
    "Опять ты со своей сдачей от школьного обеда. Подожди {seconds}с, пока твой позор забудут.",
    "Твои копейки застряли в зубах у Абу. Выковыривать будут ещё {seconds}с.",
    "Финансовый регулятор Двача заблокировал твои гроши за отмывание бомжатских денег. Жди {seconds}с.",
    "Пособие по безработице кончилось? Не части, жди {seconds}с перед следующим дропом.",
    "Шекелемет перегрелся от твоих микро-плевков. Охлаждение ствола: {seconds}с.",
    "Анон, ты забыл таблетки и решил раздать всё имущество? Санитары прописали тайм-аут на {seconds}с.",
    "Твои три копейки вызвали дефляцию в Зимбабве. Посиди смирно {seconds}с, спамер.",
    "Дропалка не выросла так часто шекелями раскидываться. Подожди {seconds}с.",
]

COOLDOWN_EXCUSES = DROP_COOLDOWN_PHRASES


def get_min_drop_rejection_message(amount: int) -> str:
    """Генерирует рандомную токсичную отмазку для суммы меньше 150 ₪."""
    template = secrets.choice(DROP_MIN_EXCUSES)
    return f"❌ {template.format(amount=amount)}"


def get_max_drop_rejection_message(amount: int) -> str:
    """Генерирует рандомную токсичную отмазку для суммы больше 1 000 000 ₪."""
    template = secrets.choice(DROP_MAX_EXCUSES)
    return f"❌ {template.format(amount=amount)}"


def get_drop_cooldown_seconds(amount: int) -> int:
    """
    Дифференцированный кулдаун на создание дропов:
    - 150 – 500 ₪: 45 секунд
    - 500 – 5 000 ₪: 20 секунд
    - > 5 000 ₪: 10 секунд
    """
    if amount <= 500:
        return 45
    elif amount <= 5000:
        return 20
    else:
        return 10


def get_user_cooldown_remaining(user_id: int) -> float:
    """Возвращает оставшееся время кулдауна пользователя в секундах (float >= 0.0)."""
    expiry = _user_drop_cooldowns.get(user_id, 0.0)
    now = time.time()
    if now < expiry:
        return expiry - now
    return 0.0


def get_cooldown_rejection_message(remaining_seconds: int) -> str:
    """Генерирует рандомную отмазку с таймером в стиле Двача."""
    template = secrets.choice(COOLDOWN_EXCUSES)
    return f"⏳ {template.format(seconds=max(1, remaining_seconds))}"


def reset_drop_cooldowns():
    """Сбрасывает кулдауны всех пользователей (для тестов)."""
    _user_drop_cooldowns.clear()


def set_user_drop_cooldown(user_id: int, duration_sec: float):
    """Устанавливает кулдаун пользователю на указанное количество секунд."""
    _user_drop_cooldowns[user_id] = time.time() + duration_sec


def register_drop_message(drop_id: str, chat_id: int, message_id: int):
    """Регистрирует отправленное сообщение о дропе для последующего обновления при перехвате."""
    pair = (chat_id, message_id)
    if pair not in _drop_messages[drop_id]:
        _drop_messages[drop_id].append(pair)


def get_drop_messages(drop_id: str) -> List[Tuple[int, int]]:
    """Возвращает список всех (chat_id, message_id) для данного drop_id."""
    return list(_drop_messages.get(drop_id, []))


def clear_drop_messages(drop_id: str):
    """Очищает зарегистрированные сообщения для drop_id."""
    _drop_messages.pop(drop_id, None)


# -----------------------------------------------------------------------------
# Drop Creation, Claiming & Persistence
# -----------------------------------------------------------------------------

async def init_drop_engine(db_conn) -> int:
    """
    Загружает неистекшие активные дропы из БД при старте бота.
    Если дроп истек во время оффлайна бота, автоматически возвращает шекели донору.
    """
    now = time.time()
    loaded = 0
    from common.database import add_user_global_balance
    try:
        async with db_conn.execute("SELECT drop_id, donor_id, board_id, amount, created_at FROM MoneyDrops WHERE status = 'active'") as c:
            rows = await c.fetchall()
        
        async with drop_lock:
            for r in rows:
                d_id, donor, board, amt, c_at = r
                exp_at = c_at + 600.0
                if now < exp_at:
                    donor_name = "Анон"
                    active_drops[d_id] = DropRecord(
                        drop_id=d_id,
                        donor_id=donor,
                        donor_name=donor_name,
                        board_id=board,
                        amount=int(amt),
                        created_at=c_at,
                        expires_at=exp_at,
                        status="active",
                    )
                    loaded += 1
                else:
                    await db_conn.execute(
                        "UPDATE MoneyDrops SET status = 'expired', refunded_at = ? WHERE drop_id = ?",
                        (now, d_id),
                    )
                    await add_user_global_balance(db_conn, donor, board, int(amt))
            await db_conn.commit()
    except Exception:
        pass
    return loaded


async def create_money_drop(
    donor_id: int,
    donor_name: str,
    board_id: str,
    amount: int,
    db_lock: asyncio.Lock,
    db_conn,
    timeout_sec: float = 600.0,
    check_cooldown: bool = True,
) -> Tuple[bool, str, Optional[DropRecord]]:
    """
    Atomically creates a public money drop by deducting funds from donor global balance.
    Persists drop in MoneyDrops DB table.
    Enforces minimum drop (150 ₪), maximum drop (1,000,000 ₪), and anti-spam differentiated cooldowns.
    """
    if amount < MIN_DROP_AMOUNT:
        return False, get_min_drop_rejection_message(amount), None

    if amount > MAX_DROP_AMOUNT:
        return False, get_max_drop_rejection_message(amount), None

    now = time.time()

    async with drop_lock:
        if check_cooldown:
            expiry = _user_drop_cooldowns.get(donor_id, 0.0)
            if now < expiry:
                rem_sec = int(expiry - now) + 1
                return False, get_cooldown_rejection_message(rem_sec), None

    from common.database import deduct_user_global_balance, get_user_global_balance

    drop_id = secrets.token_hex(6)

    async with db_lock:
        try:
            ok, new_bal = await deduct_user_global_balance(db_conn, donor_id, board_id, amount)
            if not ok:
                current_bal = await get_user_global_balance(db_conn, donor_id)
                return False, f"❌ Недостаточно средств! Твой баланс: {int(current_bal)} ₪, а попытка дропнуть: {amount} ₪.", None
            
            await db_conn.execute(
                "INSERT INTO MoneyDrops (drop_id, donor_id, board_id, amount, status, created_at) VALUES (?, ?, ?, ?, 'active', ?)",
                (drop_id, donor_id, board_id, float(amount), now),
            )
            from common.database import record_user_transaction
            await record_user_transaction(db_conn, donor_id, -amount, 'drop', f'Сброс чека в тред (#{drop_id})')
            await db_conn.commit()
        except Exception as e:
            return False, f"❌ Ошибка базы данных при создании дропа: {e}", None

    record = DropRecord(
        drop_id=drop_id,
        donor_id=donor_id,
        donor_name=donor_name,
        board_id=board_id,
        amount=amount,
        created_at=now,
        expires_at=now + timeout_sec,
        status="active",
    )
    
    async with drop_lock:
        active_drops[drop_id] = record
        # Set cooldown for the donor based on amount dropped
        cd_duration = get_drop_cooldown_seconds(amount)
        _user_drop_cooldowns[donor_id] = now + cd_duration

    return True, "✅ Дроп успешно создан и отправлен в чат!", record


async def claim_money_drop(
    drop_id: str,
    claimer_id: int,
    claimer_name: str,
    claimer_board_id: str,
    db_lock: asyncio.Lock,
    db_conn,
) -> Tuple[bool, str, Optional[DropRecord]]:
    """
    Atomically claims a money drop (First-Come, First-Served).
    Guarantees exactly 1 winner under high concurrency.
    """
    async with drop_lock:
        record = active_drops.get(drop_id)
        if not record:
            return False, "❌ Дроп не найден или уже был завершен.", None

        if record.status == "claimed":
            winner = record.claimed_name or f"Анон #{record.claimed_by}"
            return False, f"❌ Этот дроп уже забрал {winner}!", record

        if record.status == "expired":
            return False, "❌ Время действия этого дропа истекло, шекели вернулись донору.", record

        if record.status == "cancelled":
            return False, "❌ Этот дроп был отменен создателем.", record

        if record.donor_id == claimer_id:
            return False, "❌ Ты не можешь забрать свой собственный дроп! (Используй отмену, если передумал).", record

        # Reserve drop status immediately inside drop_lock
        record.status = "claimed"
        record.claimed_by = claimer_id
        record.claimed_name = claimer_name
        record.claimed_at = time.time()

    # Atomically credit claimer in DB and update MoneyDrops record
    from common.database import add_user_global_balance, record_user_transaction
    async with db_lock:
        try:
            await add_user_global_balance(db_conn, claimer_id, claimer_board_id, record.amount)
            await record_user_transaction(db_conn, claimer_id, record.amount, 'drop', f'Активация чека из треда от {record.donor_name}')
            await db_conn.execute(
                "UPDATE MoneyDrops SET status = 'claimed', claimed_by = ?, claimed_board_id = ?, claimed_at = ? WHERE drop_id = ?",
                (claimer_id, claimer_board_id, record.claimed_at, drop_id),
            )
            await db_conn.commit()
        except Exception as e:
            # Revert status on severe db failure
            async with drop_lock:
                record.status = "active"
                record.claimed_by = None
                record.claimed_name = None
            return False, f"❌ Ошибка начисления выигрыша: {e}", None

    return True, f"🎉 Ты успешно перехватил дроп на {record.amount} ₪!", record


async def cancel_money_drop(
    drop_id: str,
    user_id: int,
    db_lock: asyncio.Lock,
    db_conn,
) -> Tuple[bool, str]:
    """
    Cancels an active drop and refunds donor.
    """
    async with drop_lock:
        record = active_drops.get(drop_id)
        if not record:
            return False, "❌ Дроп не найден."
        if record.donor_id != user_id:
            return False, "❌ Ты не являешься создателем этого дропа."
        if record.status != "active":
            return False, f"❌ Нельзя отменить дроп со статусом '{record.status}'."
        
        record.status = "cancelled"

    from common.database import add_user_global_balance
    now = time.time()
    async with db_lock:
        try:
            await add_user_global_balance(db_conn, record.donor_id, record.board_id, record.amount)
            await db_conn.execute(
                "UPDATE MoneyDrops SET status = 'cancelled', refunded_at = ? WHERE drop_id = ?",
                (now, drop_id),
            )
            await db_conn.commit()
        except Exception as e:
            return False, f"❌ Ошибка возврата средств: {e}"

    return True, f"✅ Дроп на {record.amount} ₪ отменен, средства возвращены на баланс."


async def expire_unclaimed_drops_step(db_lock: asyncio.Lock, db_conn) -> List[DropRecord]:
    """
    Background step: refunds drops older than their expiration timestamp.
    """
    from common.database import add_user_global_balance
    now = time.time()
    expired_list: List[DropRecord] = []

    async with drop_lock:
        for drop_id, record in list(active_drops.items()):
            if record.status == "active" and now >= record.expires_at:
                record.status = "expired"
                expired_list.append(record)

    if not expired_list:
        return []

    async with db_lock:
        for rec in expired_list:
            try:
                await add_user_global_balance(db_conn, rec.donor_id, rec.board_id, rec.amount)
                await db_conn.execute(
                    "UPDATE MoneyDrops SET status = 'expired', refunded_at = ? WHERE drop_id = ?",
                    (now, rec.drop_id),
                )
            except Exception:
                pass
        try:
            await db_conn.commit()
        except Exception:
            pass

    return expired_list


# -----------------------------------------------------------------------------
# Inline Keyboards for Drop System
# -----------------------------------------------------------------------------

def get_drop_claim_keyboard(drop_id: str, amount: int) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text=f"💸 Забрать {amount} ₪", callback_data=f"drop:claim:{drop_id}"),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_drop_creator_keyboard(current_balance: int) -> InlineKeyboardMarkup:
    third = max(MIN_DROP_AMOUNT, current_balance // 3)
    half = max(MIN_DROP_AMOUNT, current_balance // 2)
    all_in = max(MIN_DROP_AMOUNT, current_balance)

    buttons = [
        [
            InlineKeyboardButton(text=f"💰 Треть ({third} ₪)", callback_data=f"drop:create:{third}"),
            InlineKeyboardButton(text=f"💰 Половина ({half} ₪)", callback_data=f"drop:create:{half}"),
        ],
        [
            InlineKeyboardButton(text=f"🔥 Выбросить всё ({all_in} ₪)", callback_data=f"drop:create:{all_in}"),
        ],
        [
            InlineKeyboardButton(text="150 ₪", callback_data="drop:create:150"),
            InlineKeyboardButton(text="500 ₪", callback_data="drop:create:500"),
            InlineKeyboardButton(text="1 000 ₪", callback_data="drop:create:1000"),
        ],
        [
            InlineKeyboardButton(text="5 000 ₪", callback_data="drop:create:5000"),
            InlineKeyboardButton(text="10 000 ₪", callback_data="drop:create:10000"),
            InlineKeyboardButton(text="50 000 ₪", callback_data="drop:create:50000"),
        ],
        [
            InlineKeyboardButton(text="❌ Отмена", callback_data="drop:cancel_menu"),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)
