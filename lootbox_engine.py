# -*- coding: utf-8 -*-
"""
lootbox_engine.py — Dvach Cases, Gacha & Lootbox System
2 tiers of lootboxes:
- 🗑️ Мусорный Пакет (150 ₪): Budget Case with trash, cashback, 7-day items & jackpot.
- 👑 Золотой Сейф Китов (500 ₪): High-tier Case with 30-day apparel, 15% chance of PERMANENT drop, and mythic cash.
Includes automatic duplicate item recycling and permanent upgrades.
"""

import random
import time
from typing import Tuple, Dict, Any, Optional

TRASH_ITEMS = [
    ("🥫 Пустая банка из-под балтики", "Старая пивная жестянка со следами ностальгии.", 50),
    ("🚬 Бычок от Примы", "Еще тлеющий окурок от анона из соседнего треда.", 30),
    ("🦴 Куриная косточка из КФС", "Хрустящий остаток обеда двачера.", 40),
    ("📦 Рваная коробка от пиццы", "Жирные пятна складываются в силуэт Сырно.", 60),
    ("🍬 Фантик от конфеты «Барбарис»", "Сладкие воспоминания о детстве на дваче.", 75),
    ("🧦 Дырчатый носок без пары", "Второй носок утерян в пространственно-временном континууме.", 45),
    ("🎟️ Просроченный билет на трамвай", "Компостер пробит в 2012 году.", 55),
]

PREMIUM_JUNK = [
    ("🪙 Серебряный полтинник 1924г", "Монета из чистого серебра раннего СССР.", 300),
    ("⌚ Часы «Командирские»", "Водонепроницаемые механические часы с гравировкой.", 250),
    ("🍾 Бутылка элитного портвейна «777»", "Выдержанный винтаж из подвала скуфа.", 200),
    ("💎 Фальшивый бриллиант", "Фианит высшей огранки, красиво блестит на свету.", 150),
    ("📟 Старый пейджер Motorola", "На экране мигает сообщение: 'ПРИВЕТ АНОН'.", 350),
]


def roll_trash_lootbox() -> Tuple[str, str, str, Dict[str, Any], int]:
    """
    Rolls a 150 ₪ Trash Case.
    """
    roll = random.random()
    now = int(time.time())

    # Tier 4: JACKPOT (5%)
    if roll < 0.05:
        if random.random() < 0.5:
            return (
                "🔥 ДЖЕКПОТ! (ЛЕГЕНДАРНЫЙ)",
                "💰 Толстая пачка шекелей (+1 000 ₪)!",
                "Из мусорного пакета выпала нетронутая пачка шекелей!",
                {},
                1000
            )
        else:
            return (
                "🔥 ДЖЕКПОТ! (ЛЕГЕНДАРНЫЙ)",
                "🚔 Пативэн-Ган (/partyvan)!",
                "Настоящая милицейская рация для вызова ОМОНа на тред!",
                {"partyvan_gun": True},
                0
            )

    # Tier 3: Rare Gear & 7-day Apparel (20% -> roll < 0.25)
    elif roll < 0.25:
        rare_roll = random.random()
        if rare_roll < 0.20:
            return (
                "✨ РЕДКИЙ ПРЕДМЕТ",
                "👽 Шапочка из фольги (на 6 часов)",
                "Экранирует твою голову от грабежей (/rob) и говна (/shit) на 6 часов!",
                {"tinfoil_hat": now + 6 * 3600, "tinfoil_until": now + 6 * 3600, "owned_hat_tinfoil": True, "equipped_head": "hat_tinfoil"},
                0
            )
        elif rare_roll < 0.40:
            return (
                "✨ РЕДКИЙ ПРЕДМЕТ",
                "🛡️ Зеркальный Щит (на 6 часов)",
                "Отражает выстрелы Мут-Гана обратно в стрелка!",
                {"reflect_shield_until": now + 6 * 3600, "shield_until": now + 6 * 3600},
                0
            )
        elif rare_roll < 0.60:
            return (
                "✨ РЕДКИЙ ПРЕДМЕТ",
                "🔇 Мут-Ган (/shoot на 1 час)",
                "Оружие для отстрела рака и неадекватов реплаем!",
                {"mute_gun": True},
                0
            )
        elif rare_roll < 0.80:
            return (
                "👗 БАЗОВЫЙ ШМОТ (7 ДНЕЙ)",
                "📦 Пакет из Пятерочки (на 7 дней)",
                "Головной убор труъ-анонима! Дает шанс выбивать лутбоксы на работе.",
                {"item_id": "hat_bag", "dur_hours": 168, "slot": "head"},
                0
            )
        else:
            return (
                "✨ РЕДКИЙ ПРЕДМЕТ",
                "🎨 Цветной Бейдж ника (на 3 дня)",
                "Открывает доступ к кастомному цвету ника (/color)!",
                {"badge_color_active": True, "badge_color_expires": now + 3 * 86400},
                0
            )

    # Tier 2: Combat Consumables (35% -> roll < 0.60)
    elif roll < 0.60:
        cons_roll = random.random()
        if cons_roll < 0.30:
            return (
                "⚔️ РАСХОДНИК",
                "🐒 Кусок говна (/shit)",
                "Тяжелый снаряд для метания в неугодных анонов.",
                {"shit_gun": True},
                0
            )
        elif cons_roll < 0.55:
            return (
                "⚔️ РАСХОДНИК",
                "💊 Аминазин (Лекарство)",
                "Моментально смывает все дебаффы (говно, понос, шизу).",
                {"pills_gun": True},
                0
            )
        elif cons_roll < 0.80:
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

    # Tier 1: Trash with Cashback (40%)
    else:
        name, desc, cashback = random.choice(TRASH_ITEMS)
        return (
            "🗑️ ДВАЧЕВСКИЙ МУСОР",
            name,
            f"{desc} (Кешбэк: +{cashback} ₪)",
            {},
            cashback
        )


def roll_gold_safe() -> Tuple[str, str, str, Dict[str, Any], int]:
    """
    Rolls a 500 ₪ Premium Gold Safe.
    30-day apparel with 15% chance of PERMANENT drop.
    """
    roll = random.random()
    now = int(time.time())

    # Tier 4: ULTRA JACKPOT (10%)
    if roll < 0.10:
        if random.random() < 0.5:
            return (
                "🌟 УЛЬТРА ДЖЕКПОТ (МИФИЧЕСКИЙ)",
                "💰 ЗОЛОТОЙ КЕШ (+2 500 ₪)!",
                "Из сейфа посыпались новенькие хрустящие пачки шекелей!",
                {},
                2500
            )
        else:
            return (
                "🌟 УЛЬТРА ДЖЕКПОТ (МИФИЧЕСКИЙ)",
                "🚔 Пативэн-Ган + 👽 Шапочка из фольги!",
                "Полный комплект элитного модератора борды!",
                {"partyvan_gun": True, "tinfoil_hat": now + 24 * 3600, "tinfoil_until": now + 24 * 3600},
                0
            )

    # Tier 3: Exclusive Clothing & Apparel (40% -> roll < 0.50)
    elif roll < 0.50:
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
        ]
        cid, base_name, desc, slot = random.choice(clothes_pool)

        # 15% Chance to drop PERMANENT (🌟 НАВСЕГДА)
        is_permanent_drop = (random.random() < 0.15)
        if is_permanent_drop:
            title = "🌟 ЛЕГЕНДАРНЫЙ ШМОТ (НАВСЕГДА)"
            item_name = f"{base_name} 🌟 [НАВСЕГДА]"
            payload = {"item_id": cid, "is_permanent": True, "dur_hours": 0, "slot": slot}
        else:
            title = "👗 ЭЛИТНЫЙ ШМОТ (30 ДНЕЙ)"
            item_name = f"{base_name} [на 30 дней]"
            payload = {"item_id": cid, "is_permanent": False, "dur_hours": 720, "slot": slot}

        return (
            title,
            item_name,
            desc,
            payload,
            0
        )

    # Tier 2: Heavy Combat Kit (30% -> roll < 0.80)
    elif roll < 0.80:
        return (
            "⚔️ БОЕВОЙ НАБОР",
            "🛡️ Зеркальный Щит + 🧯 Перцовка + 🔪 Заточка",
            "Тройной комплект: нападение, оборона и защита от грабежа!",
            {
                "reflect_shield_until": now + 12 * 3600,
                "shield_until": now + 12 * 3600,
                "pepperspray_gun": True,
                "knife_gun": True
            },
            0
        )

    # Tier 1: Premium Cash & Artifact (20%)
    else:
        name, desc, cashback = random.choice(PREMIUM_JUNK)
        return (
            "💎 ЦЕННАЯ НАХОДКА",
            name,
            f"{desc} (Продано за: +{cashback} ₪)",
            {},
            cashback
        )


def apply_lootbox_reward(
    active_items: Dict[str, Any],
    payload: Dict[str, Any],
    base_cash: int
) -> Tuple[Dict[str, Any], int, Optional[str]]:
    """
    Applies the lootbox reward payload to active_items.
    Handles apparel stacking, permanent upgrades, and duplicate recycling (75% cashback).
    """
    from wardrobe_engine import CLOTHING_CATALOG, add_item_duration
    recycle_msg = None
    final_cash = base_cash

    # Check if payload is an apparel drop
    if "item_id" in payload:
        item_id = payload["item_id"]
        is_perm = payload.get("is_permanent", False)
        dur_hours = payload.get("dur_hours", 720)
        slot = payload.get("slot", "torso")

        c_item = CLOTHING_CATALOG.get(item_id, {})
        item_name = c_item.get("name", item_id)

        already_perm = active_items.get(f"{item_id}_is_permanent", False)
        already_owned = active_items.get(f"owned_{item_id}", False)

        if is_perm:
            if already_perm:
                # Already permanent duplicate -> 75% cashback
                price = c_item.get("price", 400)
                cashback = int(price * 0.75)
                final_cash += cashback
                recycle_msg = f"♻️ <b>Вечный дубликат «{item_name}» переработан:</b> +{cashback} ₪ в кошелек!"
            else:
                add_item_duration(active_items, item_id, 0, is_permanent=True)
                active_items[f"equipped_{slot}"] = item_id
                recycle_msg = f"🌟 <b>ПЕРМАНЕНТНЫЙ АПГРЕЙД!</b> «{item_name}» теперь навсегда в твоем гардеробе!"
        else:
            if already_perm:
                # User already has it forever -> give 75% cashback for timed drop
                price = c_item.get("price", 400)
                cashback = int(price * 0.75)
                final_cash += cashback
                recycle_msg = f"♻️ <b>У тебя уже есть вечный «{item_name}»!</b> Временный дроп переработан: +{cashback} ₪!"
            else:
                add_item_duration(active_items, item_id, dur_hours, is_permanent=False)
                active_items[f"equipped_{slot}"] = item_id
                days_added = dur_hours // 24
                recycle_msg = f"⏳ <b>Продление экипировки:</b> +{days_added} дней к «{item_name}»!"

    else:
        now = int(time.time())
        # Standard combat / duration / consumable payload
        for k, v in payload.items():
            if k in ("tinfoil_hat", "tinfoil_until"):
                current_exp = active_items.get(k, 0)
                base = current_exp if current_exp > now else now
                active_items[k] = base + 6 * 3600
                active_items["owned_hat_tinfoil"] = True
                active_items["equipped_head"] = "hat_tinfoil"
                recycle_msg = "👽 <b>Шапочка из фольги:</b> +6 часов к длительности защиты!"
            elif k in ("reflect_shield_until", "shield_until"):
                current_exp = active_items.get(k, 0)
                base = current_exp if current_exp > now else now
                active_items[k] = base + 6 * 3600
                recycle_msg = "🛡️ <b>Зеркальный Щит:</b> +6 часов к длительности защиты!"
            elif k == "janitor_until":
                current_exp = active_items.get("janitor_until", 0)
                base = current_exp if current_exp > now else now
                active_items["janitor_until"] = base + 6 * 3600
                active_items["janitor_deletes_left"] = active_items.get("janitor_deletes_left", 0) + 5
                recycle_msg = "🧹 <b>Билет Дворника:</b> +6 часов и +5 удалений!"
            elif k in ("knife_gun", "mute_gun", "partyvan_gun", "pepperspray_gun", "shit_gun", "laxative_gun", "schizopill_gun"):
                if active_items.get(k):
                    # Already possessed -> 75% cashback compensation
                    combat_prices = {
                        "knife": 400, "mute": 500, "partyvan": 1200,
                        "pepperspray": 450, "shit": 100, "laxative": 300,
                        "schizopill": 350,
                    }
                    item_key = k.replace("_gun", "")
                    base_price = combat_prices.get(item_key, 200)
                    cb = int(base_price * 0.75)
                    final_cash += cb
                    recycle_msg = f"♻️ <b>Оружие уже заряжено:</b> компенсация +{cb} ₪ в кошелек!"
                else:
                    active_items[k] = True
            else:
                active_items[k] = v

    return active_items, final_cash, recycle_msg
