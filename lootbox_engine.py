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
from typing import Tuple, Dict, Any, Optional, List

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
]

PREMIUM_JUNK = [
    ("🪙 Серебряный полтинник 1924г", "Монета из чистого серебра раннего СССР.", 110),
    ("⌚ Часы «Командирские»", "Водонепроницаемые механические часы с гравировкой.", 90),
    ("🍾 Бутылка элитного портвейна «777»", "Выдержанный винтаж из подвала скуфа.", 70),
    ("💎 Фианит с Алиэкспресса", "Фианит высшей огранки, красиво блестит на свету.", 50),
    ("📟 Старый пейджер Motorola", "На экране мигает сообщение: 'ПРИВЕТ АНОН'.", 130),
    ("📼 Кассета «Зеленый Слоник»", "Раритетная VHS кассета в идеальном сохране.", 90),
]

# -----------------------------------------------------------------------------
# Non-Buyable Status Rewards & Mythic Relics (F2.4)
# -----------------------------------------------------------------------------
NON_BUYABLE_TITLES = ["[Золотой Кит]", "[Шекелевый Барон]", "[Сборщик Стеклотары]", "[Король Помойки]"]
EXCLUSIVE_RELICS = ["hat_golden_foil", "hat_cyber_ushanka", "body_dva_ch_mantle"]

# -----------------------------------------------------------------------------
# Scrap Recycling Values (F2.2)
# -----------------------------------------------------------------------------
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


def calculate_duplicate_cashback(case_price: int, item_price: int, is_weapon: bool = False) -> int:
    """
    Contract formula from PROJECT.md:
    min(int(case_price * 0.30), int(item_price * 0.20))
    Caps duplicate compensation relative to case price and item retail price.
    """
    return min(int(case_price * 0.30), int(item_price * 0.20))


def roll_trash_lootbox(active_items: Optional[Dict[str, Any]] = None) -> Tuple[str, str, str, Dict[str, Any], int]:
    """
    Rolls a 150 ₪ Trash Case.
    Nominal RTP <= 55% <= 85%, Cash RTP ~17%.
    - Tier 4 Jackpot (3% chance): 50% 350 ₪, 35% Mute-gun, 15% Partyvan.
    - Tier 3 Rare (15% chance): avg scrap 30 ₪, includes title [Сборщик стеклотары].
    - Tier 2 Consumables (32% chance): scrap avg 24.25 ₪.
    - Tier 1 Trash (50% chance): avg 14.28 ₪.
    """
    roll = random.random()
    now = int(time.time())

    # Tier 4: JACKPOT (3% chance)
    if roll < 0.03:
        jp_sub = random.random()
        if jp_sub < 0.50:
            return (
                "🔥 ДЖЕКПОТ! (ЛЕГЕНДАРНЫЙ)",
                "💰 Пачка шекелей (+350 ₪) + Титул [Король Помойки]!",
                "Из мусорного пакета выпала пачка шекелей и корона повелителя помоек!",
                {"grant_title": "[Король Помойки]", "title_days": 30},
                350
            )
        elif jp_sub < 0.85:
            return (
                "🔥 ДЖЕКПОТ! (ЛЕГЕНДАРНЫЙ)",
                "🔇 Мут-Ган (/shoot на 1 час)!",
                "Оружие для отстрела рака и неадекватов реплаем!",
                {"mute_gun": True},
                0
            )
        else:
            return (
                "🔥 ДЖЕКПОТ! (ЛЕГЕНДАРНЫЙ)",
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
                "✨ РЕДКИЙ ПРЕДМЕТ",
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
                "✨ РЕДКИЙ ПРЕДМЕТ",
                "🛡️ Зеркальный Щит (на 6 часов)",
                "Отражает выстрелы Мут-Гана обратно в стрелка!",
                {"reflect_shield_until": now + 6 * 3600, "shield_until": now + 6 * 3600},
                0
            )
        elif rare_roll < 0.75:
            return (
                "👗 БАЗОВЫЙ ШМОТ (7 ДНЕЙ)",
                "📦 Пакет из Пятерочки (на 7 дней)",
                "Головной убор труъ-анонима! Дает шанс выбивать лутбоксы на работе.",
                {"item_id": "hat_bag", "dur_hours": 168, "slot": "head"},
                0
            )
        elif rare_roll < 0.90:
            return (
                "✨ РЕДКИЙ ПРЕДМЕТ",
                "🎨 Цветной Бейдж ника (на 48 часов)",
                "Открывает доступ к кастомному цвету ника (/color) на 48 часов!",
                {"badge_color_active": True, "badge_color_expires": now + 48 * 3600},
                0
            )
        else:
            return (
                "✨ РЕДКИЙ СТАТУС",
                "🏷️ Титул «Сборщик Стеклотары» (на 30 дней)",
                "Почетное звание санитара тредов и собирателя бутылок!",
                {"grant_title": "[Сборщик Стеклотары]", "title_days": 30},
                0
            )

    # Tier 2: Combat Consumables (32% chance -> roll < 0.50)
    elif roll < 0.50:
        cons_roll = random.random()
        if cons_roll < 0.35:
            return (
                "⚔️ РАСХОДНИК",
                "🐒 Кусок говна (/shit)",
                "Тяжелый снаряд для метания в неугодных анонов.",
                {"shit_gun": True},
                0
            )
        elif cons_roll < 0.65:
            return (
                "⚔️ РАСХОДНИК",
                "💊 Аминазин (Лекарство)",
                "Моментально смывает все дебаффы (говно, понос, шизу).",
                {"pills_gun": True},
                0
            )
        elif cons_roll < 0.85:
            return (
                "⚔️ РАСХОДНИК",
                "🔪 Заточка (/rob)",
                "Острая пика для отжима 10-30% шекелей у цели.",
                {"knife_gun": True},
                0
            )
        else:
            return (
                "⚔️ РАСХОДНИК",
                "🧯 Перцовый Баллончик (Авто-защита)",
                "При попытке ограбить тебя ослепляет нападающего и отбирает его деньги!",
                {"pepperspray_gun": True},
                0
            )

    # Tier 1: Trash with Cashback (50% chance -> roll >= 0.50)
    else:
        name, desc, cashback = random.choice(TRASH_ITEMS)
        return (
            "🗑️ ДВАЧЕВСКИЙ МУСОР",
            name,
            f"{desc} (Кешбэк: +{cashback} ₪)",
            {},
            cashback
        )


def roll_gold_safe(active_items: Optional[Dict[str, Any]] = None) -> Tuple[str, str, str, Dict[str, Any], int]:
    """
    Rolls a 500 ₪ Premium Gold Safe.
    Nominal RTP <= 65% <= 85%, Cash RTP ~23%.
    - Tier 4 Jackpot (5% chance): 40% 1500 ₪, 30% Partyvan + Tinfoil 12h, 20% Golden Tinfoil Hat [Perm], 10% 3000 ₪ + [Золотой Кит] title (30d).
    - Tier 3 Apparel (35% chance): 10% perm, 90% 30d.
    - Tier 2 Combat kit (25% chance): Shield 6h + (knife or pepperspray) + pills, bundle_type="combat_kit".
    - Tier 1 Premium junk (35% chance): avg 90 ₪.
    """
    roll = random.random()
    now = int(time.time())

    # Tier 4: МИФИЧЕСКИЙ ДЖЕКПОТ (5% chance)
    if roll < 0.05:
        jp_sub = random.random()
        if jp_sub < 0.40:
            return (
                "🌟 МИФИЧЕСКИЙ ДЖЕКПОТ",
                "💰 Золотой Слиток Абу (+1 500 ₪)!",
                "Из сейфа посыпались новенькие хрустящие пачки шекелей!",
                {},
                1500
            )
        elif jp_sub < 0.70:
            return (
                "🌟 МИФИЧЕСКИЙ ДЖЕКПОТ",
                "🚔 Пативэн-Ган + 👽 Шапочка из фольги (12ч)!",
                "Комплект силовика: вызов ОМОНа и защита от грабежа на 12 часов!",
                {
                    "partyvan_gun": True,
                    "tinfoil_hat": now + 12 * 3600,
                    "tinfoil_until": now + 12 * 3600
                },
                0
            )
        elif jp_sub < 0.90:
            return (
                "🌟 МИФИЧЕСКИЙ ДЖЕКПОТ",
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
                "👑 СУПЕР-ДЖЕКПОТ КИТА",
                "💰 КЕШ (+3 000 ₪) + Титул «Золотой Кит»!",
                "Легендарный куш! Казна Абу опустошена на 3 000 ₪!",
                {
                    "grant_title": "[Золотой Кит]",
                    "title_days": 30
                },
                3000
            )

    # Tier 3: Exclusive Clothing & Apparel (35% chance -> roll < 0.40)
    elif roll < 0.40:
        clothes_pool = [
            ("body_cloak", "🧥 Плащ Нео / Анонима", "Стильный кожаный плащ. +30 к защите и скрытности.", "torso"),
            ("hat_helmet", "🪖 Шлем ОМОНа", "Тяжелая титановая броня силовика.", "head"),
            ("body_wasserman", "🦺 Жилетка Вассермана", "Легендарная жилетка с 28 карманами (+25% зарплаты).", "torso"),
            ("hat_cat_ears", "🐱 Неко-Ушки", "Кавайные аниме ушки для аватарки (+30 рассудка).", "head"),
            ("body_hoodie", "👘 Худи с Аской", "Теплая толстовка анимешника (+25 рассудка).", "torso"),
            ("face_thug_glasses", "🕶️ Очки Thug Life", "Пиксельные очки крутости (+5% в слотах).", "face"),
            ("face_wasserman_glasses", "🥽 Очки Онотоле", "Очки эрудита (+15% зарплаты на работе).", "face"),
            ("feet_boots", "🥾 Берцы ОМОНа", "Тяжелая армейская обувь (иммунитет к /shit).", "feet"),
            ("feet_sneakers", "👟 Тяги бархатные", "Подкрадули (+30% побега от /partyvan).", "feet"),
            ("hat_crown", "👑 Корона VIP-Скуфа", "Золотая корона (+20% к чаевым на работе).", "head"),
            ("face_anon_mask", "🎭 Маска Анонимуса", "Маска Гая Фокса (скрывает баланс в карточке).", "face"),
            ("hat_tophat", "🎩 Цилиндр Джентльмена", "Викторианский цилиндр на 30 дней. +25 к Рассудку.", "head"),
            ("hat_cyber_ushanka", "🛸 Кибер-Ушанка", "Неоновая ушанка силовика будущего.", "head"),
            ("body_dva_ch_mantle", "👘 Мантия Олдфага", "Олдфажный балахон двачера навсегда.", "torso"),
        ]
        cid, base_name, desc, slot = random.choice(clothes_pool)

        # 10% Chance to drop PERMANENT (🌟 НАВСЕГДА), 90% 30 days
        is_permanent_drop = (random.random() < 0.10)
        if is_permanent_drop:
            title = "🌟 ЛЕГЕНДАРНЫЙ ШМОТ (НАВСЕГДА)"
            item_name = f"{base_name} 🌟 [НАВСЕГДА]"
            payload = {
                "item_id": cid,
                "is_permanent": True,
                "dur_hours": 0,
                "slot": slot,
                "grant_title": "[Шекелевый Барон]",
                "title_days": 30
            }
        else:
            title = "👗 ЭЛИТНЫЙ ШМОТ (30 ДНЕЙ)"
            item_name = f"{base_name} [на 30 дней]"
            payload = {
                "item_id": cid,
                "is_permanent": False,
                "dur_hours": 720,
                "slot": slot
            }

        return title, item_name, desc, payload, 0

    # Tier 2: Heavy Combat Kit (25% chance -> roll < 0.65)
    elif roll < 0.65:
        w_choice = "pepperspray_gun" if random.random() < 0.5 else "knife_gun"
        w_name = "🧯 Перцовка" if w_choice == "pepperspray_gun" else "🔪 Заточка"
        return (
            "⚔️ БОЕВОЙ НАБОР",
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

    # Tier 1: Premium Cash & Artifact (35% chance -> roll >= 0.65)
    else:
        name, desc, cashback = random.choice(PREMIUM_JUNK)
        return (
            "💎 ЦЕННАЯ НАХОДКА",
            name,
            f"{desc} (Продано скупу за: +{cashback} ₪)",
            {},
            cashback
        )


def apply_lootbox_reward(
    active_items: Dict[str, Any],
    payload: Dict[str, Any],
    base_cash: int,
    case_type: str = "gold"
) -> Tuple[Dict[str, Any], int, Optional[str]]:
    """
    Applies the lootbox reward payload to active_items.
    Handles apparel stacking, permanent upgrades, scrap recycling, and bundle cashback caps.
    Enforces maximum 7-day cap on all protective buffs.
    """
    from wardrobe_engine import CLOTHING_CATALOG, add_item_duration
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
                note = f"♻️ <b>Вечный дубликат «{item_name}» сдан в ломбард:</b> +{cashback} ₪ в кошелек!"
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
                note = f"♻️ <b>Вещь «{item_name}» уже есть навсегда!</b> Утиль: +{cashback} ₪!"
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
                bundle_note = "♻️ <b>Оружие из набора уже заряжено:</b> компенсация +80 ₪!"
                recycle_msg = (recycle_msg + "\n" + bundle_note) if recycle_msg else bundle_note

            # Activate weapons and consumables from bundle
            for wk in ("knife_gun", "pepperspray_gun", "pills_gun"):
                if payload.get(wk):
                    active_items[wk] = True

        # 4. Protection and individual weapons/consumables
        for k, v in payload.items():
            if k in ("tinfoil_hat", "tinfoil_until"):
                current_exp = active_items.get(k, 0)
                base = current_exp if current_exp > now else now
                active_items[k] = min(base + 6 * 3600, max_protection_cap)
                active_items["owned_hat_tinfoil"] = True
                active_items["equipped_head"] = "hat_tinfoil"
                note = "👽 <b>Шапочка из фольги:</b> +6 часов к длительности защиты!"
                recycle_msg = (recycle_msg + "\n" + note) if recycle_msg else note
            elif k in ("reflect_shield_until", "shield_until"):
                current_exp = active_items.get(k, 0)
                base = current_exp if current_exp > now else now
                active_items[k] = min(base + 6 * 3600, max_protection_cap)
                note = "🛡️ <b>Зеркальный Щит:</b> +6 часов к длительности защиты!"
                recycle_msg = (recycle_msg + "\n" + note) if recycle_msg else note
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
                        note = f"♻️ <b>Оружие уже заряжено:</b> утиль +{cb} ₪ в кошелек!"
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

    return active_items, final_cash, recycle_msg


from whale_economy_engine import calculate_whale_safe_price, roll_whale_safe


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


async def record_lootbox_purchase_persistent(db, user_id: int, case_type: str) -> int:
    """
    Асинхронно фиксирует открытие/покупку лутбокса в памяти и SQLite (UserDailyLimits).
    Возвращает актуальный счетчик за сегодня.
    """
    import shared_state
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

