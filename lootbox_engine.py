# -*- coding: utf-8 -*-
"""
lootbox_engine.py — Dvach Cases, Gacha & Lootbox System
Rebalanced EV/RTP Architecture (Milestone 2):
- 🗑️ Мусорный Пакет (150 ₪): Budget Case with rebalanced trash, consumables, 7-day items & jackpot.
  Nominal RTP <= 55% <= 85%, Cash RTP ~17%.
- 👑 Золотой Сейф Китов (500 ₪): High-tier Case with 30-day apparel, 10% chance of PERMANENT drop, and mythic cash.
  Nominal RTP <= 65% <= 85%, Cash RTP ~23%.
Includes strict duplicate cashback caps, fixed scrap recycling, bundle caps, and non-buyable status rewards.
"""

import random
import time
import asyncio
import math
import json
from contextlib import asynccontextmanager
from typing import Tuple, Dict, Any, Optional, List
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def _sanitize_active_items(active_items: Any) -> Dict[str, Any]:
    """
    Безопасно нормализует active_items.
    Если передан None, пустая строка, битый/поврежденный JSON, список или другой некорректный тип,
    предотвращает падение с ValueError, AttributeError или TypeError и возвращает валидный dict.
    """
    if active_items is None:
        return {}
    if isinstance(active_items, dict):
        return active_items
    if isinstance(active_items, str):
        trimmed = active_items.strip()
        if not trimmed:
            return {}
        try:
            parsed = json.loads(trimmed)
            if isinstance(parsed, dict):
                return parsed
            return {}
        except Exception:
            return {}
    return {}


def format_shekels(amount: int | float, show_sign: bool = False) -> str:
    """
    Красивое форматирование шекелей с разделителями тысяч (пробел) и защитой от float-артефактов:
    например, '1 500 ₪' вместо '1500.0000000001 ₪'.
    """
    if amount is None or (isinstance(amount, float) and (math.isnan(amount) or math.isinf(amount))):
        return "0 ₪"
    try:
        rounded = round(float(amount), 2)
        if abs(rounded - round(rounded)) < 1e-5:
            val_int = int(round(rounded))
            sign_prefix = "+" if (show_sign and val_int > 0) else ""
            formatted = f"{val_int:,}".replace(",", " ")
            return f"{sign_prefix}{formatted} ₪"
        else:
            sign_prefix = "+" if (show_sign and rounded > 0) else ""
            formatted = f"{rounded:,.2f}".replace(",", " ")
            return f"{sign_prefix}{formatted} ₪"
    except (ValueError, TypeError, OverflowError):
        return "0 ₪"


# -----------------------------------------------------------------------------
# Rarity Tiers & Visual Gradation (UX Resilience)
# -----------------------------------------------------------------------------
RARITY_TIERS = {
    "common": {"code": "common", "name": "Обычный", "emoji": "⚪", "badge": "⚪ Обычный"},
    "rare": {"code": "rare", "name": "Редкий", "emoji": "🔵", "badge": "🔵 Редкий"},
    "epic": {"code": "epic", "name": "Эпический", "emoji": "🟣", "badge": "🟣 Эпический"},
    "legendary": {"code": "legendary", "name": "Легендарный", "emoji": "🟡", "badge": "🟡 Легендарный"},
}


def get_rarity_info(tier_str: str) -> Dict[str, str]:
    """
    Определяет уровень редкости и бейдж (Обычный ⚪, Редкий 🔵, Эпический 🟣, Легендарный 🟡)
    по заголовку тира предмета.
    """
    lower = (tier_str or "").lower()
    if any(k in lower for k in ("легендарн", "джекпот", "мифическ", "навсегда", "супер-джекпот")) or "🟡" in tier_str or "🌟" in tier_str:
        return RARITY_TIERS["legendary"]
    if any(k in lower for k in ("эпическ", "элитн", "гарант", "гардероб")) or "🟣" in tier_str or "👗" in tier_str:
        return RARITY_TIERS["epic"]
    if any(k in lower for k in ("редк", "боевой", "расходник", "щит")) or "🔵" in tier_str or "✨" in tier_str or "⚔️" in tier_str:
        return RARITY_TIERS["rare"]
    return RARITY_TIERS["common"]


def format_rarity_badge(tier_str: str) -> str:
    """Возвращает форматированный бейдж редкости с соответствующим эмодзи."""
    return get_rarity_info(tier_str)["badge"]

# -----------------------------------------------------------------------------
# Rebalanced Drop Tables (F2.1)
# -----------------------------------------------------------------------------
TRASH_ITEMS = [
    ("🥫 Пустая банка из-под балтики", "Старая пивная жестянка со следами ностальгии.", 15),
    ("🚬 Бычок от Примы", "Еще тлеющий окурок от анона из соседнего треда.", 10),
    ("🦴 Куриная косточка из КФС", "Хрустящий остаток обеда двачера.", 12),
    ("📦 Рваная коробка от пиццы", "Жирные пятна складываются в силуэт Сырно.", 20),
    ("🍬 Фантик от конфеты «Барбарис»", "Сладкие воспоминания о детстве на дваче.", 15),
    ("🧦 Дырчатый носок без пары", "Второй носок утерян в пространственно-временном континууме.", 10),
    ("🎟️ Просроченный билет на трамвай", "Компостер пробит в 2012 году.", 18),
    ("🍾 Половинчатый баллон «Охоты Крепкой»", "Выдохшаяся теплая жижа, забытая сычом под лавкой.", 16),
    ("🎈 Проткнутый презерватив «Гусарские»", "Срок годности истёк в 2008. Символ разбитых надежд омежки.", 11),
    ("🔥 Коробок со спичками и плесенью", "Чиркаш стёрт до дыр, спички отсырели в сычевальне.", 10),
    ("📱 Засаленный чехол от Siemens C65", "Пахнет старой маршруткой, дешёвым табаком и ностальгией.", 14),
    ("📟 Разбитый корпус от пейджера", "Внутри застряла пыль времён первых набегов на двач.", 13),
    ("🍜 Смятая пачка от Доширака с говядиной", "Специи уже вынюхали через свёрнутый чек из Пятёрочки.", 15),
    ("🧦 Носок с засохшей дыркой на пятке", "Второй носок намертво прилип к обоям за кроватью.", 12),
    ("💨 Сломанный кулер от GeForce 8600GT", "Вращается только силой мысли и воет как полярная метель.", 17),
    ("🧀 Ошмёток сырка «Красная цена»", "Срок годности заботливо соскоблен зубами неизвестного грызуна.", 11),
    ("🏷️ Этикетка от водки «Праздничная» 0.25", "На обороте химическим карандашом записан чей-то чужой IP.", 14),
    ("🏎️ Вкладыш «Турбо» с разбитым спорткаром", "Углы обгрызены от зависти в далёком детстве.", 18),
    ("🥄 Пластиковая ложка из «Кулинарии»", "Со следами засохшего пюре и слюны неизвестного сыча.", 10),
    ("📶 Половинка сим-карты Билайн без пина", "Навечно заблокирована за рассылку спама про микрозаймы.", 16),
    ("🗞️ Стекловата в газете «Сельская жизнь»", "Начинает нестерпимо чесаться даже через экран смартфона.", 12),
    ("🫙 Крышка от настойки боярышника", "Освящена святыми вокзальными алкашами в третьем поколении.", 13),
    ("🧼 Обмылок хозяйственного мыла с волосом", "Скользкий, мерзкий, ронять на пол категорически не рекомендуется.", 11),
    ("🚬 Окурок от «Беломорканала» с замятым мундштуком", "Пахнет дедом, гаражным кооперативом и политотой из телевизора.", 12),
    ("💾 Битая флешка на 128 МБ", "Внутри только битый архив с пометкой 'не удалять_важно.rar'.", 19),
    ("🔌 Погрызенный провод от зарядки Micro-USB", "Работает строго если подогнуть штекер под углом 73 градуса.", 15),
    ("🥫 Пустая жестянка из-под снюса", "Внутри сухо, но стойкий запах ментола и гнилых десен остался.", 14),
    ("💾 Треснувшая дискета 3.5 с надписью 'ПОРНО'", "Бэд-сектора безжалостно пожрали самые сочные пиксели.", 16),
    ("🔩 Ржавый гвоздь-сотка", "Погнут при попытке приколотить плакат с Аской прямо в бетон.", 10),
    ("🔘 Пуговица от драпового пальто вахтёра", "Оторвана с мясом во время яростного ночного штурма параши.", 13),
    ("🍷 Пробка от портвейна «Три Топора»", "Винтаж, классика, вечный памятник студенческому днищу.", 12),
    ("🧀 Засохший плавленый сырок «Дружба»", "Оружие дробящего типа. Можно легко пробить череп омежке.", 15),
    ("🧾 Скомканный чек из «Пятёрочки» на 43 рубля", "Состав чека: полбуханки серого, майонез по акции, пакет.", 11),
    ("✏️ Огрызок карандаша 'Конструктор 2Т'", "Заточен тупым кухонником, грифель безнадежно расколот внутри.", 10),
    ("🪟 Осколок советской кафельной плитки", "Цвет 'гнилой майонез', найден на заброшенном заводе.", 14),
    ("🔋 Батарейка 'Космос', покусанная зубами", "Ещё способна выдать 0.05 вольта, если очень сильно попросить.", 13),
    ("🦷 Зубочистка б/у из привокзальной шашлычной", "Второй свежести. Зато дерево отечественное, березовое.", 10),
    ("🍶 Промытая баночка из-под майонеза", "Идеальный контейнер для сдачи анализов или хранения шекелей.", 15),
]

PREMIUM_JUNK = [
    ("🪙 Серебряный полтинник 1924г", "Монета из чистого серебра раннего СССР.", 110),
    ("⌚ Часы «Командирские»", "Водонепроницаемые механические часы с гравировкой.", 90),
    ("🍾 Бутылка элитного портвейна «777»", "Выдержанный винтаж из подвала сыча.", 70),
    ("💎 Фианит с Алиэкспресса", "Фианит высшей огранки, красиво блестит на свету.", 50),
    ("📟 Старый пейджер Motorola", "На экране мигает сообщение: 'ПРИВЕТ АНОН'.", 130),
    ("📼 Кассета «Зеленый Слоник»", "Раритетная VHS кассета в идеальном сохране.", 90),
    ("🔥 Зажигалка Zippo с гравировкой «ДВАЧ 2007»", "Кремень искрит, фитиль слегка подпален, но пламя держит.", 115),
    ("🎖️ Серебряный значок «Гвардия» со сколом", "Трофей из дедовского серванта, бережно спасенный от ломбарда.", 95),
    ("📻 Кассетный плеер Sony Walkman", "Слегка жуёт плёнку с «Гражданской Обороной», но басы живые.", 105),
    ("💿 Лицензионный диск Half-Life 2 от СофтКлаба", "Ключ активирован 20 лет назад, но запах полиграфии божественен.", 85),
    ("⚙️ Механический шагомер «Заря»", "Намотал 40 000 км между диваном, холодильником и парашей.", 75),
    ("🪓 Советский складной нож «Белка»", "Лезвие люфтит, но докторскую колбасу за 140 рублей режет на ура.", 90),
    ("💡 Ламповый газоразрядный индикатор ИН-14", "Светится тёплым неоновым светом, излучая ламповость.", 120),
    ("☕ Кружка с принтом «/b/ — место для илиты»", "Покрыта толстым слоем благородного чайного налёта.", 65),
    ("📛 Оригинальный бейджик модератора Сосача", "Даёт +100 к ЧСВ и -500 к шансам завести реальных друзей.", 100),
    ("🥫 Банка сгущёнки Рогачёв по ГОСТу СССР", "Срок годности давно в астрале, но вкус чистого сахара бессмертен.", 80),
    ("🥄 Титановая ложка с надписью «АБУ НЕ ВОРУЕТ»", "Редчайший сувенир с первой подпольной сходки двачеров.", 110),
    ("🎵 Виниловая пластинка «Кино — Группа Крови»", "Шуршит как осенние листья под тапками выходящего за пивом сыча.", 95),
    ("🔌 Стеклянный изолятор с телеграфного столба", "Тяжёлый изумрудный артефакт, выдержит прямое попадание кирпича.", 70),
    ("🎮 Картридж Battletoads & Double Dragon для Dendy", "Работает с первого раза, если как следует дунуть в контакты.", 115),
    ("🔦 Армейский фонарик-жучок с динамо-машиной", "Грохочет при сжатии как трактор, зато батарейки не нужны.", 85),
    ("🧢 Кепка-восьмиклинка из кожзама", "Атрибут настоящего районного авторитета и грозы пивных ларьков.", 75),
    ("📿 Чётки из эбонита, выточенные на зоне", "Щёлкают солидно, успокаивают расшатанные нервы после слива в рулетку.", 90),
    ("🕶️ Солнцезащитные очки Polaroid из 90-х", "Скрывают мешки под глазами после трёх суток бессонного шитпостинга.", 85),
    ("📷 Плёночный фотоаппарат «Смена-8М»", "Застрявшая внутри плёнка «Свема» хранит тайны чужих вписок.", 105),
]

# -----------------------------------------------------------------------------
# Non-Buyable Status Rewards & Mythic Relics (F2.4)
# -----------------------------------------------------------------------------
NON_BUYABLE_TITLES = ["[Золотой Кит]", "[Шекелевый Барон]", "[Сборщик Стеклотары]", "[Король Помойки]"]
EXCLUSIVE_RELICS = ["hat_golden_foil", "hat_cyber_ushanka", "body_dva_ch_mantle"]

# -----------------------------------------------------------------------------
# Scrap Recycling Values (F2.2) & Scrap Tax (40% burn, recovery <= 60%)
# -----------------------------------------------------------------------------
SCRAP_TAX_RATE = 0.40  # 40% сгорает в пыль
MAX_SCRAP_RECOVERY_RATE = 0.60  # Не более 50-60% от номинала предмета

WEAPON_SCRAP_PRICES = {
    "trash": {
        "shit": 15,
        "pills": 20,
        "knife": 35,
        "pepperspray": 40,
        "mute": 45,
        "partyvan": 45,
    },
    "gold": {
        "shit": 20,
        "pills": 20,
        "knife": 80,
        "pepperspray": 80,
        "mute": 100,
        "partyvan": 150,
    },
    "whale": {
        "shit": 1000,
        "pills": 1000,
        "knife": 5000,
        "pepperspray": 5000,
        "mute": 8000,
        "partyvan": 12000,
    }
}


def calculate_scrap_value(item_nominal: int, max_rate: float = 0.60) -> int:
    """
    Рассчитывает стоимость переработки утиля/мусора с учетом scrap tax 40% (не более 50-60% от номинала).
    """
    effective_rate = min(max_rate, 1.0 - SCRAP_TAX_RATE)
    return int(item_nominal * effective_rate)


def calculate_duplicate_cashback(case_price: int, item_price: int, is_weapon: bool = False) -> int:
    """
    Contract formula from PROJECT.md:
    min(int(case_price * 0.30), int(item_price * 0.20))
    Caps duplicate compensation relative to case price and item retail price.
    """
    return min(int(case_price * 0.30), int(item_price * 0.20))


# -----------------------------------------------------------------------------
# Pity System & Anti-Bad-Luck Engine
# -----------------------------------------------------------------------------
LOOTBOX_PITY_THRESHOLD = 10  # После 10 пустых открытий 11-е гарантирует носимый предмет


def format_pity_counter(active_items: Optional[Dict[str, Any]] = None) -> str:
    """
    Formats the wardrobe pity counter status:
    `🛡️ Гарант гардероба: X/10 (через {10 - X} кейсов гарантирован шмот)`
    """
    pity_counter = active_items.get("lootbox_pity_counter", 0) if active_items else 0
    rem = max(0, LOOTBOX_PITY_THRESHOLD - pity_counter)
    return f"🛡️ Гарант гардероба: {pity_counter}/{LOOTBOX_PITY_THRESHOLD} (через {rem} кейсов гарантирован шмот)"

TRASH_PITY_WARDROBE_POOL = [
    ("hat_bag", "📦 Пакет из Пятерочки (на 7 дней)", "Головной убор труъ-анонима! Дает шанс выбивать лутбоксы на работе.", "head", 168),
    ("face_clown_nose", "🤡 Клоунский Нос (на 7 дней)", "Красный нос на 7 дней. +35 к Токсичности и троллингу в тредах.", "face", 168),
    ("face_thug_glasses", "🕶️ Очки Thug Life (на 7 дней)", "Пиксельные очки крутости (+5% в слотах).", "face", 168),
    ("feet_slippers", "🩴 Сланцы с носками (на 7 дней)", "Домашний уют на 7 дней. Сокращает кулдаун смен /work на 20%.", "feet", 168),
]

GOLD_PITY_WARDROBE_POOL = [
    ("body_cloak", "🧥 Плащ Нео / Анонима", "Стильный кожаный плащ. +30 к защите и скрытности.", "torso"),
    ("hat_helmet", "🪖 Шлем ОМОНа", "Тяжелая титановая броня силовика.", "head"),
    ("body_wasserman", "🦺 Жилетка Вассермана", "Легендарная жилетка с 28 карманами (+25% зарплаты).", "torso"),
    ("hat_cat_ears", "🐱 Неко-Ушки", "Кавайные аниме ушки для аватарки (+30 рассудка).", "head"),
    ("body_hoodie", "👘 Худи с Аской", "Теплая толстовка анимешника (+25 рассудка).", "torso"),
    ("face_thug_glasses", "🕶️ Очки Thug Life", "Пиксельные очки крутости (+5% в слотах).", "face"),
    ("face_wasserman_glasses", "🥽 Очки Онотоле", "Очки эрудита (+15% зарплаты на работе).", "face"),
    ("feet_boots", "🥾 Берцы ОМОНа", "Тяжелая армейская обувь (иммунитет к /shit).", "feet"),
    ("feet_sneakers", "👟 Стоптанные берцы", "Тяги битарда (+30% побега от /partyvan).", "feet"),
    ("hat_crown", "👑 Корона VIP-Сыча", "Золотая корона (+20% к чаевым на работе).", "head"),
    ("face_anon_mask", "🎭 Маска Анонимуса", "Маска Гая Фокса (скрывает баланс в карточке).", "face"),
    ("hat_tophat", "🎩 Цилиндр Джентльмена", "Викторианский цилиндр на 30 дней. +25 к Рассудку.", "head"),
    ("hat_cyber_ushanka", "🛸 Кибер-Ушанка", "Неоновая ушанка силовика будущего.", "head"),
    ("body_dva_ch_mantle", "👘 Мантия Олдфага", "Олдфажный балахон двачера навсегда.", "torso"),
]


def is_wearable_reward(payload: Optional[Dict[str, Any]]) -> bool:
    """
    Проверяет, содержит ли награда носимый предмет гардероба (шапка, очки, обувь, одежда).
    """
    if not payload or not isinstance(payload, dict):
        return False
    if "item_id" in payload:
        return True
    if payload.get("equipped_head") or payload.get("owned_hat_tinfoil") or payload.get("tinfoil_hat"):
        return True
    if any(k.startswith("equipped_") for k in payload):
        return True
    return False


def roll_trash_lootbox(active_items: Optional[Dict[str, Any]] = None) -> Tuple[str, str, str, Dict[str, Any], int]:
    """
    Rolls a 150 ₪ Trash Case.
    Nominal RTP <= 55% <= 60%, Cash RTP ~14.6% <= 25% (avg cash <= 35 ₪).
    Pity System: after 10 consecutive openings without wearable item,
    the 11th opening guarantees a 7-day wardrobe drop (hat, glasses, shoes).
    """
    now = int(time.time())
    active_items = _sanitize_active_items(active_items)

    # Pity System check (10 openings without wearable -> 11th is guaranteed)
    pity_counter = active_items.get("lootbox_pity_counter", 0)
    if pity_counter >= LOOTBOX_PITY_THRESHOLD:
        cid, base_name, desc, slot, dur = random.choice(TRASH_PITY_WARDROBE_POOL)
        return (
            "🟣 ЭПИЧЕСКИЙ [ГАРАНТ: Базовый шмот 7 дней]",
            base_name,
            f"{desc} (Сработал Гарант: 10 открытий без шмота!)",
            {"item_id": cid, "dur_hours": dur, "slot": slot, "pity_triggered": True},
            0
        )

    roll = random.random()

    # Tier 4: JACKPOT (3% chance)
    if roll < 0.03:
        jp_sub = random.random()
        if jp_sub < 0.50:
            return (
                "🟡 ЛЕГЕНДАРНЫЙ [Джекпот Абу]",
                "💰 Пачка шекелей (+350 ₪) + Титул [Король Помойки]!",
                "Из мусорного пакета выпала пачка шекелей и корона повелителя помоек!",
                {"grant_title": "[Король Помойки]", "title_days": 1},
                350
            )
        elif jp_sub < 0.85:
            return (
                "🟡 ЛЕГЕНДАРНЫЙ [Джекпот Абу]",
                "🔇 Мут-Ган (/shoot на 1 час)!",
                "Оружие для отстрела рака и неадекватов реплаем!",
                {"mute_gun": True},
                0
            )
        else:
            return (
                "🟡 ЛЕГЕНДАРНЫЙ [Джекпот Абу]",
                "🚔 Пативэн-Ган (/partyvan)!",
                "Настоящая милицейская рация для вызова ОМОНа на тред!",
                {"partyvan_gun": True},
                0
            )

    # Tier 3: Rare Gear & Status (15% chance -> roll < 0.18)
    elif roll < 0.18:
        rare_roll = random.random()
        if rare_roll < 0.25:
            return (
                "🟣 ЭПИЧЕСКИЙ [Редкий предмет]",
                "👽 Шапочка из фольги (на 6 часов)",
                "Экранирует твою голову от грабежей (/rob) и говна (/shit) на 6 часов!",
                {
                    "tinfoil_hat": now + 6 * 3600,
                    "tinfoil_until": now + 6 * 3600,
                    "owned_hat_tinfoil": True,
                    "equipped_head": "hat_tinfoil"
                },
                0
            )
        elif rare_roll < 0.50:
            return (
                "🟣 ЭПИЧЕСКИЙ [Редкий предмет]",
                "🛡️ Зеркальный Щит (на 6 часов)",
                "Отражает выстрелы Мут-Гана обратно в стрелка!",
                {"reflect_shield_until": now + 6 * 3600, "shield_until": now + 6 * 3600},
                0
            )
        elif rare_roll < 0.75:
            return (
                "🟣 ЭПИЧЕСКИЙ [Базовый шмот 7 дней]",
                "📦 Пакет из Пятерочки (на 7 дней)",
                "Головной убор труъ-анонима! Дает шанс выбивать лутбоксы на работе.",
                {"item_id": "hat_bag", "dur_hours": 168, "slot": "head"},
                0
            )
        elif rare_roll < 0.90:
            return (
                "🟣 ЭПИЧЕСКИЙ [Редкий предмет]",
                "🎨 Цветной Бейдж ника (на 48 часов)",
                "Открывает доступ к кастомному цвету ника (/color) на 48 часов!",
                {"badge_color_active": True, "badge_color_expires": now + 48 * 3600},
                0
            )
        else:
            return (
                "🟣 ЭПИЧЕСКИЙ [Редкий статус]",
                "🏷️ Титул «Сборщик Стеклотары» (на 24 часа)",
                "Почетное звание санитара тредов и собирателя бутылок!",
                {"grant_title": "[Сборщик Стеклотары]", "title_days": 1},
                0
            )

    # Tier 2: Combat Consumables (32% chance -> roll < 0.50)
    elif roll < 0.50:
        cons_roll = random.random()
        if cons_roll < 0.35:
            return (
                "🔵 РЕДКИЙ [Боевой расходник]",
                "🐒 Кусок говна (/shit)",
                "Тяжелый снаряд для метания в неугодных анонов.",
                {"shit_gun": True},
                0
            )
        elif cons_roll < 0.65:
            return (
                "🔵 РЕДКИЙ [Боевой расходник]",
                "💊 Аминазин (Лекарство)",
                "Моментально смывает все дебаффы (говно, понос, шизу).",
                {"pills_gun": True},
                0
            )
        elif cons_roll < 0.85:
            return (
                "🔵 РЕДКИЙ [Боевой расходник]",
                "🔪 Заточка (/rob)",
                "Острая пика для отжима 10-30% шекелей у цели.",
                {"knife_gun": True},
                0
            )
        else:
            return (
                "🔵 РЕДКИЙ [Боевой расходник]",
                "🧯 Перцовый Баллончик (Авто-защита)",
                "При попытке ограбить тебя ослепляет нападающего и отбирает его деньги!",
                {"pepperspray_gun": True},
                0
            )

    # Tier 1: Trash with Cashback (50% chance -> roll >= 0.50)
    else:
        name, desc, cashback = random.choice(TRASH_ITEMS)
        return (
            "⚪ ОБЫЧНЫЙ [Двачевский мусор]",
            name,
            f"{desc} (Кешбэк: +{cashback} ₪)",
            {},
            cashback
        )


def roll_gold_safe(active_items: Optional[Dict[str, Any]] = None) -> Tuple[str, str, str, Dict[str, Any], int]:
    """
    Rolls a 500 ₪ Premium Gold Safe.
    Nominal RTP ~59.4% <= 60%, Cash RTP ~21.2% <= 25% (avg cash <= 110 ₪).
    - Tier 4 Jackpot (5% chance): 35% 1500 ₪, 30% Partyvan + Tinfoil 12h, 30% Golden Tinfoil Hat [Perm], 5% 3000 ₪ + [Золотой Кит] title (30d).
    - Tier 3 Apparel (30% chance): 10% perm, 90% 30d.
    - Tier 2 Combat kit (30% chance): Shield 6h + (knife or pepperspray) + pills, bundle_type="combat_kit".
    - Tier 1 Premium junk (35% chance): avg 90 ₪.
    Pity System: after 10 consecutive openings without wearable item,
    the 11th opening guarantees an apparel drop (head, face, feet, torso).
    """
    now = int(time.time())
    active_items = _sanitize_active_items(active_items)

    # Pity System check (10 openings without wearable -> 11th is guaranteed)
    pity_counter = active_items.get("lootbox_pity_counter", 0)
    if pity_counter >= LOOTBOX_PITY_THRESHOLD:
        cid, base_name, desc, slot = random.choice(GOLD_PITY_WARDROBE_POOL)
        is_permanent_drop = (random.random() < 0.10)
        if is_permanent_drop:
            title = "🟡 ЛЕГЕНДАРНЫЙ [ГАРАНТ: Вечный шмот навсегда]"
            item_name = f"{base_name} 🌟 [НАВСЕГДА]"
            payload = {
                "item_id": cid,
                "is_permanent": True,
                "dur_hours": 0,
                "slot": slot,
                "grant_title": "[Шекелевый Барон]",
                "title_days": 1,
                "pity_triggered": True,
            }
        else:
            title = "🟣 ЭПИЧЕСКИЙ [ГАРАНТ: Элитный шмот 30 дней]"
            item_name = f"{base_name} [на 30 дней]"
            payload = {
                "item_id": cid,
                "is_permanent": False,
                "dur_hours": 720,
                "slot": slot,
                "pity_triggered": True,
            }
        return title, item_name, f"{desc} (Сработал Гарант: 10 открытий без шмота!)", payload, 0

    roll = random.random()

    # Tier 4: МИФИЧЕСКИЙ ДЖЕКПОТ (5% chance)
    if roll < 0.05:
        jp_sub = random.random()
        if jp_sub < 0.25:
            return (
                "🟡 ЛЕГЕНДАРНЫЙ [Мифический джекпот]",
                "💰 Золотой Слиток Абу (+1 500 ₪)!",
                "Из сейфа посыпались новенькие хрустящие пачки шекелей!",
                {},
                1500
            )
        elif jp_sub < 0.65:
            return (
                "🟡 ЛЕГЕНДАРНЫЙ [Мифический джекпот]",
                "🚔 Пативэн-Ган + 👽 Шапочка из фольги (12ч)!",
                "Комплект силовика: вызов ОМОНа и защита от грабежа на 12 часов!",
                {
                    "partyvan_gun": True,
                    "tinfoil_hat": now + 12 * 3600,
                    "tinfoil_until": now + 12 * 3600
                },
                0
            )
        elif jp_sub < 0.95:
            return (
                "🟡 ЛЕГЕНДАРНЫЙ [Шмот навсегда]",
                "👑 Золотая Шапочка из Фольги 🌟 [НАВСЕГДА]",
                "Уникальный мифический артефакт! Пассивная защита от грабежей навсегда!",
                {
                    "item_id": "hat_golden_foil",
                    "is_permanent": True,
                    "dur_hours": 0,
                    "slot": "head"
                },
                0
            )
        else:
            return (
                "🟡 ЛЕГЕНДАРНЫЙ [Супер-джекпот кита]",
                "💰 КЕШ (+3 000 ₪) + Титул «Золотой Кит»!",
                "Легендарный куш! Казна Абу опустошена на 3 000 ₪!",
                {
                    "grant_title": "[Золотой Кит]",
                    "title_days": 1
                },
                3000
            )

    # Tier 3: Exclusive Clothing & Apparel (25% chance -> roll < 0.30)
    elif roll < 0.30:
        cid, base_name, desc, slot = random.choice(GOLD_PITY_WARDROBE_POOL)

        # 10% Chance to drop PERMANENT (🌟 НАВСЕГДА), 90% 30 days
        is_permanent_drop = (random.random() < 0.10)
        if is_permanent_drop:
            title = "🟡 ЛЕГЕНДАРНЫЙ [Шмот навсегда]"
            item_name = f"{base_name} 🌟 [НАВСЕГДА]"
            payload = {
                "item_id": cid,
                "is_permanent": True,
                "dur_hours": 0,
                "slot": slot,
                "grant_title": "[Шекелевый Барон]",
                "title_days": 1
            }
        else:
            title = "🟣 ЭПИЧЕСКИЙ [Элитный шмот 30 дней]"
            item_name = f"{base_name} [на 30 дней]"
            payload = {
                "item_id": cid,
                "is_permanent": False,
                "dur_hours": 720,
                "slot": slot
            }

        return title, item_name, desc, payload, 0

    # Tier 2: Heavy Combat Kit (30% chance -> roll < 0.60)
    elif roll < 0.60:
        w_choice = "pepperspray_gun" if random.random() < 0.5 else "knife_gun"
        w_name = "🧯 Перцовка" if w_choice == "pepperspray_gun" else "🔪 Заточка"
        return (
            "🔵 РЕДКИЙ [Боевой набор]",
            f"🛡️ Зеркальный Щит + {w_name} + 💊 Аминазин",
            "Комплект обороны от гопников и отражения атак!",
            {
                "reflect_shield_until": now + 6 * 3600,
                "shield_until": now + 6 * 3600,
                w_choice: True,
                "pills_gun": True,
                "bundle_type": "combat_kit"
            },
            0
        )

    # Tier 1: Premium Cash & Artifact (40% chance -> roll >= 0.60)
    else:
        name, desc, cashback = random.choice(PREMIUM_JUNK)
        return (
            "⚪ ОБЫЧНЫЙ [Ценная находка]",
            name,
            f"{desc} (Продано скупу за: +{cashback} ₪)",
            {},
            cashback
        )


def apply_lootbox_reward(
    active_items: Any,
    payload: Optional[Dict[str, Any]],
    base_cash: int,
    case_type: str = "gold"
) -> Tuple[Dict[str, Any], int, Optional[str]]:
    """
    Applies the lootbox reward payload to active_items.
    Handles apparel stacking, permanent upgrades, scrap recycling, and bundle cashback caps.
    Enforces maximum 7-day cap on all protective buffs.
    """
    from wardrobe_engine import CLOTHING_CATALOG, add_item_duration
    active_items = _sanitize_active_items(active_items)
    payload = payload if isinstance(payload, dict) else {}
    recycle_msg = None
    final_cash = base_cash
    now = int(time.time())
    max_protection_cap = now + 7 * 86400  # Cap at 7 days maximum

    # 1. Custom Status Titles
    if "grant_title" in payload:
        raw_title = payload["grant_title"]
        title = raw_title if raw_title.startswith("[") else f"[{raw_title}]"
        days = payload.get("title_days", 30)
        active_items["custom_title"] = title
        active_items["title_expires_at"] = now + days * 86400
        title_msg = f"👑 <b>ПОЛУЧЕН ТИТУЛ:</b> {title} на {days} дней!"
        recycle_msg = (recycle_msg + "\n" + title_msg) if recycle_msg else title_msg

    # 2. Check if payload is an apparel drop
    if "item_id" in payload:
        item_id = payload["item_id"]
        is_perm = payload.get("is_permanent", False)
        dur_hours = payload.get("dur_hours", 720)
        slot = payload.get("slot", "torso")

        c_item = CLOTHING_CATALOG.get(item_id, {})
        item_name = c_item.get("name", item_id)
        price = c_item.get("price", 400)

        already_perm = active_items.get(f"{item_id}_is_permanent", False)

        if is_perm:
            if already_perm:
                # Permanent duplicate: min(120, max(40, int(price * 0.20)))
                cashback = min(120, max(40, int(price * 0.20)))
                final_cash += cashback
                note = f"♻️ <b>У тебя уже есть этот предмет!</b> Вечный дубликат «{item_name}» сдан в ломбард. Начислен кэшбэк: +{cashback} ₪ в кошелек!"
                recycle_msg = (recycle_msg + "\n" + note) if recycle_msg else note
            else:
                add_item_duration(active_items, item_id, 0, is_permanent=True)
                active_items[f"equipped_{slot}"] = item_id
                note = f"🌟 <b>ПЕРМАНЕНТНЫЙ АПГРЕЙД!</b> «{item_name}» теперь навсегда в твоем гардеробе!"
                recycle_msg = (recycle_msg + "\n" + note) if recycle_msg else note
        else:
            if already_perm:
                # Fixed scrap recycling: Rolling timed apparel when permanent is already owned gives fixed 35 ₪ scrap
                cashback = 35
                final_cash += cashback
                note = f"♻️ <b>У тебя уже есть этот предмет!</b> Вещь «{item_name}» уже есть навсегда! Начислен кэшбэк (Утиль: +{cashback} ₪)!"
                recycle_msg = (recycle_msg + "\n" + note) if recycle_msg else note
            else:
                add_item_duration(active_items, item_id, dur_hours, is_permanent=False)
                active_items[f"equipped_{slot}"] = item_id
                days_added = dur_hours // 24
                note = f"⏳ <b>Продление экипировки:</b> +{days_added} дней к «{item_name}»!"
                recycle_msg = (recycle_msg + "\n" + note) if recycle_msg else note

        # Check wardrobe set achievements upon auto-equipping
        from wardrobe_engine import check_wardrobe_set_achievements
        new_achs = check_wardrobe_set_achievements(active_items)
        if new_achs:
            for ach in new_achs:
                final_cash += ach.get("reward_cash", 0)
                recycle_msg = (recycle_msg or "") + f"\n🏆 <b>ДОСТИЖЕНИЕ ЗА СЕТ:</b> {ach['name']} (+{ach['reward_cash']} ₪)!"

    else:
        # 3. Combat kit bundle cap handling
        if payload.get("bundle_type") == "combat_kit":
            # In combat_kit bundle, if user already has weapon, cap total bundle cashback at 80 ₪
            has_duplicate_weapon = False
            for wk in ("knife_gun", "pepperspray_gun"):
                if payload.get(wk) and active_items.get(wk):
                    has_duplicate_weapon = True
                    break
            if has_duplicate_weapon:
                final_cash += 80
                bundle_note = f"♻️ <b>У тебя уже есть этот предмет!</b> Оружие из набора уже заряжено: Начислен кэшбэк (компенсация +80 ₪)!"
                recycle_msg = (recycle_msg + "\n" + bundle_note) if recycle_msg else bundle_note

            # Activate weapons and consumables from bundle
            for wk in ("knife_gun", "pepperspray_gun", "pills_gun"):
                if payload.get(wk):
                    active_items[wk] = True

        # 4. Protection and individual weapons/consumables
        # Handle paired protective buffs first to prevent duplicate notifications
        has_tinfoil = any(k in payload for k in ("tinfoil_hat", "tinfoil_until"))
        if has_tinfoil:
            added_sec = 6 * 3600
            for tk in ("tinfoil_hat", "tinfoil_until"):
                if tk in payload and isinstance(payload[tk], (int, float)) and payload[tk] > now:
                    added_sec = max(added_sec, int(payload[tk] - now))
            cur_exp = max(active_items.get("tinfoil_hat", 0), active_items.get("tinfoil_until", 0))
            base = cur_exp if cur_exp > now else now
            new_exp = min(base + added_sec, max_protection_cap)
            active_items["tinfoil_hat"] = new_exp
            active_items["tinfoil_until"] = new_exp
            active_items["owned_hat_tinfoil"] = True
            active_items["equipped_head"] = "hat_tinfoil"
            hours_added = added_sec // 3600
            note = f"👽 <b>Шапочка из фольги:</b> +{hours_added} часов к длительности защиты!"
            recycle_msg = (recycle_msg + "\n" + note) if recycle_msg else note

        has_shield = any(k in payload for k in ("reflect_shield_until", "shield_until"))
        if has_shield:
            added_sec = 6 * 3600
            for sk in ("reflect_shield_until", "shield_until"):
                if sk in payload and isinstance(payload[sk], (int, float)) and payload[sk] > now:
                    added_sec = max(added_sec, int(payload[sk] - now))
            cur_exp = max(active_items.get("reflect_shield_until", 0), active_items.get("shield_until", 0))
            base = cur_exp if cur_exp > now else now
            new_exp = min(base + added_sec, max_protection_cap)
            active_items["reflect_shield_until"] = new_exp
            active_items["shield_until"] = new_exp
            active_items["shield_gun"] = True
            active_items["shield"] = True
            hours_added = added_sec // 3600
            note = f"🛡️ <b>Зеркальный Щит:</b> +{hours_added} часов к длительности защиты!"
            recycle_msg = (recycle_msg + "\n" + note) if recycle_msg else note

        for k, v in payload.items():
            if k in ("tinfoil_hat", "tinfoil_until", "reflect_shield_until", "shield_until", "owned_hat_tinfoil"):
                continue
            if k == "equipped_head" and v == "hat_tinfoil":
                continue
            elif k == "janitor_until":
                current_exp = active_items.get("janitor_until", 0)
                base = current_exp if current_exp > now else now
                active_items["janitor_until"] = min(base + 6 * 3600, max_protection_cap)
                active_items["janitor_deletes_left"] = active_items.get("janitor_deletes_left", 0) + 5
                note = "🧹 <b>Билет Дворника:</b> +6 часов и +5 удалений!"
                recycle_msg = (recycle_msg + "\n" + note) if recycle_msg else note
            elif k in ("knife_gun", "mute_gun", "partyvan_gun", "pepperspray_gun", "shit_gun", "pills_gun", "laxative_gun", "schizopill_gun"):
                if payload.get("bundle_type") != "combat_kit":
                    if active_items.get(k):
                        scrap_table = WEAPON_SCRAP_PRICES.get(case_type, WEAPON_SCRAP_PRICES["gold"])
                        ik = k.replace("_gun", "")
                        default_cb = calculate_duplicate_cashback(50000 if case_type == "whale" else (500 if case_type == "gold" else 150), 200, is_weapon=True)
                        cb = scrap_table.get(ik, default_cb)
                        if case_type == "whale":
                            cb = min(cb, 15000)
                        final_cash += cb
                        note = f"♻️ <b>У тебя уже есть этот предмет!</b> Оружие уже заряжено: Начислен кэшбэк (утиль +{cb} ₪ в кошелек)!"
                        recycle_msg = (recycle_msg + "\n" + note) if recycle_msg else note
                    else:
                        active_items[k] = True
            else:
                if k not in ("bundle_type", "grant_title", "title_days"):
                    active_items[k] = v

    # Ensure any preexisting bloated protection duration is capped to 7 days
    for prot_key in ("shield_until", "reflect_shield_until", "tinfoil_until", "tinfoil_hat", "janitor_until"):
        if active_items.get(prot_key, 0) > max_protection_cap:
            active_items[prot_key] = max_protection_cap

    # 5. Pity System Tracking (Guarantee after 10 openings without wearable item)
    if is_wearable_reward(payload):
        active_items["lootbox_pity_counter"] = 0
        if payload.get("pity_triggered"):
            pity_note = "🛡️ <b>Сработала защита от невезения (Гарант 10):</b> получен гарантированный предмет гардероба!"
            recycle_msg = (recycle_msg + "\n" + pity_note) if recycle_msg else pity_note
    else:
        active_items["lootbox_pity_counter"] = active_items.get("lootbox_pity_counter", 0) + 1

    return active_items, final_cash, recycle_msg




# -----------------------------------------------------------------------------
# Abu Yacht Fund 50% Burn & Lootbox Pricing
# -----------------------------------------------------------------------------
LOOTBOX_PRICES = {
    "trash": 150,
    "lootbox_trash": 150,
    "trash_lootbox": 150,
    "gold": 500,
    "lootbox_gold": 500,
    "gold_safe": 500,
    "whale": 50000,
    "lootbox_whale": 50000,
    "whale_safe": 50000,
}

LOOTBOX_ABU_BURN_RATE = 0.50  # 50% сжигается в Фонд Абу


def get_lootbox_price(case_type: str) -> int:
    """Возвращает базовую цену покупки лутбокса."""
    key = normalize_lootbox_key(case_type)
    return LOOTBOX_PRICES.get(key, LOOTBOX_PRICES.get(case_type, 150))


def calculate_abu_burn_amount(case_type: str, custom_price: Optional[int] = None) -> float:
    """Вычисляет сумму сжигания в Фонд Абу (50% от стоимости покупки кейса)."""
    price = custom_price if custom_price is not None else get_lootbox_price(case_type)
    return round(price * LOOTBOX_ABU_BURN_RATE, 2)


async def burn_lootbox_to_abu(db, case_type: str, donor_id: int = 0, custom_price: Optional[int] = None) -> float:
    """
    Сжигает 50% от стоимости покупки кейса в Фонд Яхты Абу (GlobalStats['abu_yacht_fund']).
    """
    from common.database import add_to_abu_fund
    burn_amount = calculate_abu_burn_amount(case_type, custom_price=custom_price)
    reason = f"Сжигание 50% от покупки кейса {case_type}"
    return await add_to_abu_fund(db, burn_amount, donor_id=donor_id, reason=reason)


# -----------------------------------------------------------------------------
# Daily Purchase Limits & Persistence Integration
# -----------------------------------------------------------------------------

LOOTBOX_KEY_ALIASES = {
    "trash": "lootbox_trash",
    "lootbox_trash": "lootbox_trash",
    "trash_lootbox": "lootbox_trash",
    "gold": "lootbox_gold",
    "lootbox_gold": "lootbox_gold",
    "gold_safe": "lootbox_gold",
    "whale": "lootbox_whale",
    "lootbox_whale": "lootbox_whale",
    "whale_safe": "lootbox_whale",
}


def normalize_lootbox_key(case_type: str) -> str:
    """Приводит различные варианты названия кейса к каноническому ключу товара."""
    return LOOTBOX_KEY_ALIASES.get(case_type, case_type)


def get_lootbox_daily_limit(case_type: str) -> Optional[int]:
    """Возвращает суточный лимит покупок для данного кейса (100 для trash, 40 для gold)."""
    import shared_state
    key = normalize_lootbox_key(case_type)
    return shared_state.SHOP_DAILY_LIMITS.get(key)


def check_lootbox_daily_limit(user_id: int, case_type: str) -> Tuple[bool, int, int]:
    """
    Проверяет, не исчерпан ли суточный лимит открытия данного типа лутбокса.
    Возвращает (is_allowed, current_buys, max_limit).
    """
    import shared_state
    key = normalize_lootbox_key(case_type)
    return shared_state.check_shop_purchase_limit(user_id, key)


async def check_lootbox_daily_limit_persistent(db, user_id: int, case_type: str) -> Tuple[bool, int, int]:
    """
    Асинхронно проверяет суточный лимит с актуализацией данных из SQLite (UserDailyLimits).
    Возвращает (is_allowed, current_buys, max_limit).
    """
    import shared_state
    key = normalize_lootbox_key(case_type)
    return await shared_state.check_shop_purchase_limit_async(db, user_id, key)


def record_lootbox_purchase(user_id: int, case_type: str):
    """
    Фиксирует открытие/покупку лутбокса в суточных счетчиках (in-memory и SQLite).
    """
    import shared_state
    key = normalize_lootbox_key(case_type)
    shared_state.record_shop_purchase(user_id, key)


async def record_lootbox_purchase_persistent(db, user_id: int, case_type: str, burn_to_abu: bool = True) -> int:
    """
    Асинхронно фиксирует открытие/покупку лутбокса в памяти и SQLite (UserDailyLimits).
    Также сжигает 50% стоимости кейса в Фонд Яхты Абу (GlobalStats['abu_yacht_fund']).
    Возвращает актуальный счетчик за сегодня.
    """
    import shared_state
    if burn_to_abu and db is not None:
        try:
            await burn_lootbox_to_abu(db, case_type, donor_id=user_id)
        except Exception:
            pass
    key = normalize_lootbox_key(case_type)
    return await shared_state.record_shop_purchase_async(db, user_id, key)


def can_open_lootbox(user_id: int, case_type: str) -> bool:
    """Проверяет доступность открытия лутбокса по лимитам."""
    allowed, _, _ = check_lootbox_daily_limit(user_id, case_type)
    return allowed


async def can_open_lootbox_persistent(db, user_id: int, case_type: str) -> bool:
    """Асинхронно проверяет доступность открытия лутбокса по постоянным лимитам из SQLite."""
    allowed, _, _ = await check_lootbox_daily_limit_persistent(db, user_id, case_type)
    return allowed


# -----------------------------------------------------------------------------
# Balance Validation & Insufficient Funds Alerts
# -----------------------------------------------------------------------------

def validate_lootbox_funds(balance: int | float, case_type: str, custom_price: Optional[int] = None) -> Tuple[bool, int, str]:
    """
    Проверяет, достаточно ли средств у пользователя на открытие кейса/сейфа.
    Возвращает (is_allowed, case_price, alert_message).
    При нехватке формирует понятный информативный алерт для callback.answer(show_alert=True).
    """
    price = custom_price if custom_price is not None else get_lootbox_price(case_type)
    try:
        bal = 0 if balance is None or (isinstance(balance, float) and (math.isnan(balance) or math.isinf(balance))) else int(balance)
    except (ValueError, TypeError, OverflowError):
        bal = 0

    if bal < price:
        diff = price - bal
        msg = (
            f"❌ Недостаточно шекелей для открытия!\n"
            f"Стоимость кейса: {format_shekels(price)}\n"
            f"Твой баланс: {format_shekels(bal)}\n"
            f"Не хватает: {format_shekels(diff)}"
        )
        return False, price, msg
    return True, price, ""


# -----------------------------------------------------------------------------
# In-Flight Locks & Debouncing (Button Spam & Double-Click Protection)
# -----------------------------------------------------------------------------

_user_lootbox_locks: Dict[int, asyncio.Lock] = {}
_lootbox_inflight: Dict[int, float] = {}
_lootbox_meta_lock = asyncio.Lock()
user_lootbox_last_action: Dict[int, float] = {}


class LootboxInFlightError(Exception):
    """Выбрасывается при попытке открыть кейс, пока предыдущее открытие ещё не завершилось."""
    pass


async def get_user_lootbox_lock(user_id: int) -> asyncio.Lock:
    """Возвращает или создает per-user asyncio.Lock для сериализации открытия лутбоксов."""
    async with _lootbox_meta_lock:
        if user_id not in _user_lootbox_locks:
            _user_lootbox_locks[user_id] = asyncio.Lock()
        return _user_lootbox_locks[user_id]


def is_lootbox_in_flight(user_id: int) -> bool:
    """Проверяет, открывается ли кейс прямо сейчас для данного пользователя."""
    lock = _user_lootbox_locks.get(user_id)
    if lock is not None and lock.locked():
        return True
    return user_id in _lootbox_inflight


@asynccontextmanager
async def lootbox_in_flight_guard(user_id: int, timeout: float = 0.0):
    """
    Контекстный менеджер защиты от спама кнопками 'Открыть кейс/сейф'.
    Блокирует параллельные запросы до завершения транзакции списания и начисления.
    """
    user_lock = await get_user_lootbox_lock(user_id)
    if user_lock.locked() and timeout <= 0.0:
        raise LootboxInFlightError("⏳ Кейс уже открывается! Пожалуйста, дождитесь окончания анимации.")

    acquired = False
    try:
        if timeout > 0.0:
            try:
                await asyncio.wait_for(user_lock.acquire(), timeout=timeout)
                acquired = True
            except asyncio.TimeoutError:
                raise LootboxInFlightError("⏳ Кейс уже открывается! Пожалуйста, дождитесь окончания анимации.")
        else:
            await user_lock.acquire()
            acquired = True

        _lootbox_inflight[user_id] = time.time()
        yield
    finally:
        _lootbox_inflight.pop(user_id, None)
        if acquired and user_lock.locked():
            user_lock.release()


def check_lootbox_debounce(user_id: int, min_interval: float = 1.0) -> Tuple[bool, str]:
    """
    Защита от быстрого спама кликами открытия лутбоксов (debouncing).
    Возвращает (is_allowed, error_message).
    """
    now = time.time()
    last = user_lootbox_last_action.get(user_id, 0.0)
    if now - last < min_interval:
        rem = round(min_interval - (now - last), 1)
        return False, f"⏳ Не спеши! Подожди {rem} сек. перед следующим открытием кейса."
    user_lootbox_last_action[user_id] = now
    return True, ""


def format_lootbox_result_card(
    case_name: str,
    tier: str,
    item_title: str,
    item_desc: str,
    cashback_amount: int = 0,
    recycle_note: Optional[str] = None,
    balance_after: Optional[int | float] = None
) -> str:
    """
    Форматирует информативную карточку результата открытия лутбокса с четким бейджем редкости,
    описанием и указанием кэшбэка при наличии.
    """
    rarity_badge = format_rarity_badge(tier)
    lines = [
        f"🎁 <b>ОТКРЫТ {case_name.upper()}!</b>\n",
        f"⭐ <b>Редкость:</b> {rarity_badge}",
        f"📦 <b>Дроп:</b> <b>{item_title}</b>",
        f"📝 <i>{item_desc}</i>",
    ]
    if cashback_amount > 0:
        lines.append(f"💰 <b>Начислен кэшбэк:</b> +{format_shekels(cashback_amount)}")
    if recycle_note:
        lines.append(f"\n{recycle_note}")
    if balance_after is not None:
        lines.append(f"\n💳 Твой баланс: <b>{format_shekels(balance_after)}</b>")
    return "\n".join(lines)


def roll_whale_safe(active_items: Optional[Dict[str, Any]] = None) -> Tuple[str, str, str, Dict[str, Any], int]:
    """
    Proxy to whale_economy_engine.roll_whale_safe with active_items sanitization.
    """
    from whale_economy_engine import roll_whale_safe as _rws
    return _rws(active_items=_sanitize_active_items(active_items))


def get_lootbox_insufficient_funds_keyboard(case_type: str = "trash", balance: int = 0) -> InlineKeyboardMarkup:
    """
    Клавиатура быстрого выхода при недостатке шекелей на открытие кейса/сейфа.
    Предлагает заработать шекели на работе (/work) или получить ежедневный бонус (/daily).
    """
    buttons = [
        [
            InlineKeyboardButton(text="💼 Пойти на работу (/work)", callback_data="work_hub"),
            InlineKeyboardButton(text="🎁 Ежедневный бонус (/daily)", callback_data="bonus_daily"),
        ],
        [
            InlineKeyboardButton(text="🛒 В Магазин (/shop)", callback_data="shop_main_hub"),
            InlineKeyboardButton(text="⚡ Главное меню", callback_data="menu_main"),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

