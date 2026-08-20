# -*- coding: utf-8 -*-
"""
common/work_engine.py — Dvach Work, Labor Exchange & Career System
Includes tier-based job vacancies, shift cooldowns, failure risks,
interconnected RPG Wardrobe Gear buffs, set bonuses, and item drops.
"""

import time
import random
import re
from typing import Dict, Any, Tuple, Optional

WORK_VACANCIES = {
    "courier": {
        "required_shifts": 0,
        "title": "🚴 Доставщик Яндекс.Еды",
        "desc": "Развозить шаурму и бургеры на дырявом велике по лужам и сугробам",
        "tier": "Уровень 1 • Педальный раб",
        "reward_range": (30, 60),
        "cooldown_sec": 600,  # 10 minutes
        "risk_pct": 0.05,
        "penalty": 15,
        "item_drop": "shit",
        "item_drop_chance": 0.08,
        "phrases": [
            "Доставил 3 двойные шаурмы в общагу без происшествий: заработано <code>+{reward} ₪</code>!",
            "Успешно сбежал от стаи бродячих собак во дворе и вручил заказ клиенту: получка <code>+{reward} ₪</code>!",
            "Поднялся на 16 этаж без лифта и получил щедрые чаевые: на кармане <code>+{reward} ₪</code>!"
        ],
        "fail_phrases": [
            "💥 <b>ДТП НА САМОКАТЕ!</b> Влетел в бордюр и расплескал суп Том-Ям: штраф от сервиса <code>-{penalty} ₪</code>!",
            "Злой питбуль прокусил желтый короб: компенсация ущерба <code>-{penalty} ₪</code>!"
        ],
        "jackpot_phrases": [
            "💎 <b>ЩЕДРЫЙ МАЖОР!</b> Пьяный айтишник перевел 500% чаевых за ночную доставку пиццы: куш <code>+{reward} ₪</code>!"
        ]
    },
    "factory": {
        "required_shifts": 10,
        "title": "⚙️ Токарь на Днепрогэсе",
        "desc": "Точить гайки, дышать мазутом и слушать байки старого мастера Михалыча",
        "tier": "Уровень 2 • Пролетарий года",
        "reward_range": (60, 110),
        "cooldown_sec": 1200,  # 20 minutes
        "risk_pct": 0.08,
        "penalty": 25,
        "item_drop": "knife",
        "item_drop_chance": 0.06,
        "phrases": [
            "Выточил партию из 50 титановых болтов по ГОСТу: получка <code>+{reward} ₪</code>!",
            "Отработал ночную смену у станка 16К20 без травм: мастер выдал <code>+{reward} ₪</code>!",
            "Выполнил двойную норму до обеда и ушел курить в каптерку: заработано <code>+{reward} ₪</code>!"
        ],
        "fail_phrases": [
            "📉 <b>БРАК НА ПРОИЗВОДСТВЕ!</b> Запорол деталь из легированной стали: вычет из зарплаты <code>-{penalty} ₪</code>!",
            "Уронил разводной ключ в чан с маслом: мастер лишил премии <code>-{penalty} ₪</code>!"
        ],
        "jackpot_phrases": [
            "💎 <b>ГОСПЛАН ПЕРЕВЫПОЛНЕН!</b> Завод получил оборонный заказ, всем начислена премия: <code>+{reward} ₪</code>!"
        ]
    },
    "shawarma": {
        "required_shifts": 25,
        "title": "🌯 Шаурмист у вокзала",
        "desc": "Крутить сочные свитки богов, сыпать секретный соус и шутить с таксистами",
        "tier": "Уровень 3 • Повелитель Лаваша",
        "reward_range": (90, 160),
        "cooldown_sec": 1800,  # 30 minutes
        "risk_pct": 0.12,
        "penalty": 40,
        "item_drop": "pills",
        "item_drop_chance": 0.07,
        "phrases": [
            "Скрутил 40 сырных шавух в час пик у метро: чистый навар <code>+{reward} ₪</code>!",
            "Секретный чесночный соус свёл с ума местных студентов: касса пополнилась на <code>+{reward} ₪</code>!",
            "Продал шаурму «Богатырскую» с тремя видами мяса: щедрый навар <code>+{reward} ₪</code>!"
        ],
        "fail_phrases": [
            "🚨 <b>ВИЗИТ РОСПОТРЕБНАДЗОРА!</b> На кухне нашли кота без санитарной книжки: штраф <code>-{penalty} ₪</code>!",
            "Перепутал острый соус с экстрактом Хабанеро, клиент вызвал полицию: откуп <code>-{penalty} ₪</code>!"
        ],
        "jackpot_phrases": [
            "💎 <b>ОПТОВЫЙ ЗАКАЗ!</b> Свадебный кортеж скупил всё мясо на вертеле: рекордная выручка <code>+{reward} ₪</code>!"
        ]
    },
    "cashier": {
        "required_shifts": 35,
        "title": "🍷 Кассир в Красном и Белом",
        "desc": "Пробивать чеки, продавать чипсы по акции и успокаивать местных алконавтов",
        "tier": "Уровень 4 • Страж Алко-Маркета",
        "reward_range": (120, 210),
        "cooldown_sec": 2400,  # 40 minutes
        "risk_pct": 0.15,
        "penalty": 50,
        "item_drop": "pepperspray",
        "item_drop_chance": 0.06,
        "phrases": [
            "Успешно закрыл смену в КБ без недостачи по водке: зарплата <code>+{reward} ₪</code>!",
            "Впарил 20 банок просроченных шпрот по акции 'Товар дня': премия <code>+{reward} ₪</code>!",
            "Обезвредил пьяного дебошира шваброй, директор выписал бонус <code>+{reward} ₪</code>!"
        ],
        "fail_phrases": [
            "📉 <b>НЕДОСТАЧА НА РЕВИЗИИ!</b> Местные школьники утащили элитный вискарь: штраф из ЗП <code>-{penalty} ₪</code>!",
            "Уронил пирамиду из Балтики 9 при разгрузке паллета: бой посуды <code>-{penalty} ₪</code>!"
        ],
        "jackpot_phrases": [
            "💎 <b>ПРЕМИЯ ОТ СЕТИ!</b> Лучший кассир месяца по продажам портвейна «Три Топора»: премия <code>+{reward} ₪</code>!"
        ]
    },
    "construction": {
        "required_shifts": 50,
        "title": "🧱 Разнорабочий на стройке",
        "desc": "Таскать мешки с цементом, месить раствор и слушать мат прораба",
        "tier": "Уровень 5 • Бетонный гладиатор",
        "reward_range": (160, 280),
        "cooldown_sec": 3600,  # 1 hour
        "risk_pct": 0.18,
        "penalty": 60,
        "item_drop": "tinfoil",
        "item_drop_chance": 0.05,
        "phrases": [
            "Залил 5 кубов бетона под залихватский мат прораба Петровича: получка <code>+{reward} ₪</code>!",
            "Разгрузил фуру со шлакоблоками за 2 часа, спина в труху: на кармане <code>+{reward} ₪</code>!",
            "Спас стройку от затопления, забив чопик в трубу: премия <code>+{reward} ₪</code>!"
        ],
        "fail_phrases": [
            "🧱 <b>КИРПИЧ НА ГОЛОВУ!</b> Уронил ведро с раствором на ногу бригадиру: штраф <code>-{penalty} ₪</code>!",
            "Прораб кинул на половину зарплаты за перекур: удержано <code>-{penalty} ₪</code>!"
        ],
        "jackpot_phrases": [
            "💎 <b>ХАЛЯВНЫЙ МЕТАЛЛОЛОМ!</b> Нашёл в котловане 300 кг медного кабеля и сдал тайком за <code>+{reward} ₪</code>!"
        ]
    },
    "moderator": {
        "required_shifts": 75,
        "title": "🛡️ Модератор Двача (/b/)",
        "desc": "Чистка тредов от цп, вайпов, говна и бана неугодных анонов",
        "tier": "Уровень 6 • Санитар Палаты",
        "reward_range": (250, 420),
        "cooldown_sec": 7200,  # 2 hours
        "risk_pct": 0.22,
        "penalty": 100,
        "item_drop": "lootbox_trash",
        "item_drop_chance": 0.06,
        "phrases": [
            "Успешно отбил ночной вайп пастами про говно: админ отсыпал <code>+{reward} ₪</code>!",
            "Забанил 50 школьников за однотипные треды про тянок: профит <code>+{reward} ₪</code>!",
            "Удалил шок-контент до того, как его увидел РКН: премия за спасение борды <code>+{reward} ₪</code>!"
        ],
        "fail_phrases": [
            "🔥 <b>ВЫГОРАНИЕ И ШИЗА!</b> Начитался тредов в /sn/ и /b/, поехала крыша: донаты психотерапевту <code>-{penalty} ₪</code>!",
            "Случайно забанил трейлера и ОПа главного треда: штраф от админа <code>-{penalty} ₪</code>!"
        ],
        "jackpot_phrases": [
            "💎 <b>ДОНАТ ОТ КИТА!</b> Благодарный анон закрепил донат за удаление треда с его деаноном: куш <code>+{reward} ₪</code>!"
        ]
    },
    "hacker": {
        "required_shifts": 100,
        "title": "💻 Теневой Кардер & Скаммер",
        "desc": "Прогрев мамонтов, арбитраж крипты и слив дампов баз данных",
        "tier": "Уровень 7 • Кибер-Мафиози",
        "reward_range": (400, 750),
        "cooldown_sec": 14400,  # 4 hours
        "risk_pct": 0.28,
        "penalty": 200,
        "item_drop": "partyvan",
        "item_drop_chance": 0.05,
        "phrases": [
            "Прогрел мамонта на покупку скам-сигналов для крипты: залутал <code>+{reward} ₪</code>!",
            "Сделал Rugpull скам-токена $DVACH, состриг хомяков: профит <code>+{reward} ₪</code>!",
            "Прокрутил P2P-связку с профитом 12%: чистый навар <code>+{reward} ₪</code>!"
        ],
        "fail_phrases": [
            "🚔 <b>ОБЛАВА ОБЭП!</b> Следователь вышел на криптокошелек, пришлось откупаться: взятка <code>-{penalty} ₪</code>!",
            "Мамонт оказался майором ФСБ: еле унёс ноги, потеряв <code>-{penalty} ₪</code>!"
        ],
        "jackpot_phrases": [
            "💎 <b>СКАМ ВЕКА!</b> Взломал смарт-контракт дефи-биржи и вывел куш в <code>+{reward} ₪</code>!"
        ]
    }
}


def get_vacancies() -> Dict[str, Dict[str, Any]]:
    return WORK_VACANCIES


def execute_job_action(job_id: str, current_items: dict) -> Tuple[bool, int, str, Optional[str]]:
    """
    Executes job action with interconnected RPG Wardrobe Gear buffs & Set Bonuses.
    """
    if job_id not in WORK_VACANCIES:
        return False, 0, "❌ Неизвестная вакансия.", None

    job = WORK_VACANCIES[job_id]
    req_shifts = job.get("required_shifts", 0)
    current_shifts = current_items.get("work_shifts", 0)
    if current_shifts < req_shifts:
        return False, 0, f"🔒 Закрыто! Требуется стаж: {req_shifts} смен (у тебя {current_shifts}). Начни с доступных вакансий!", None

    now = int(time.time())
    work_timers = current_items.setdefault("work_cooldowns", {})
    last_time = work_timers.get(job_id, 0)
    passed = now - last_time

    # --- RPG WARDROBE BUFFS & SET BONUSES ---
    from wardrobe_engine import get_active_set_bonuses
    eq_torso = current_items.get("equipped_torso")
    eq_head = current_items.get("equipped_head")
    eq_face = current_items.get("equipped_face")
    eq_feet = current_items.get("equipped_feet")
    active_sets = get_active_set_bonuses(current_items)

    gear_buffs = []
    salary_multiplier = 1.0

    # 🩴 Slippers: -20% cooldown reduction
    cooldown_sec = job["cooldown_sec"]
    if eq_feet == "feet_slippers":
        cooldown_sec = int(cooldown_sec * 0.80)
        gear_buffs.append("🩴 Сланцы: -20% кулдаун")

    if passed < cooldown_sec:
        left_min = ((cooldown_sec - passed) // 60) + 1
        return False, 0, f"⏳ Кулдаун! Эта работа будет доступна через {left_min} мин.", None

    # Set Bonus: Wasserman
    has_wasserman_set = any(s["id"] == "set_wasserman" for s in active_sets)
    has_riot_set = any(s["id"] == "set_riot_police" for s in active_sets)
    has_anime_set = any(s["id"] == "set_anime_hikka" for s in active_sets)
    has_skuf_set = any(s["id"] == "set_gop_skuf" for s in active_sets)

    if has_wasserman_set:
        salary_multiplier += 0.40
        gear_buffs.append("🦺 Сет Онотоле: +40% ЗП")
    else:
        if eq_torso == "body_wasserman":
            salary_multiplier += 0.25
            gear_buffs.append("🦺 Вассерман +25%")
        if eq_face == "face_wasserman_glasses":
            salary_multiplier += 0.15
            gear_buffs.append("🥽 Очки Онотоле +15%")

    if has_skuf_set:
        salary_multiplier += 0.35
        gear_buffs.append("🩲 Сет Скуфа: +35% чаевые")
    elif eq_head == "hat_crown":
        salary_multiplier += 0.20
        gear_buffs.append("👑 VIP Корона +20%")

    # 🪖 Helmet or Riot Set: fine immunity
    has_fine_immunity = (eq_head == "hat_helmet" or has_riot_set)

    # 🩲 Tracksuit / Anime Set: loot drop multiplier
    drop_rate_mult = 2.0 if (eq_torso == "body_tracksuit" or has_anime_set) else 1.0
    if has_anime_set:
        gear_buffs.append("👘 Сет Аниме: x2 дроп кейсов")
    elif eq_torso == "body_tracksuit":
        gear_buffs.append("🩲 Треники: x2 дроп")

    # Check for Failure
    is_fail = (job.get("risk_pct", 0) > 0 and random.random() < job["risk_pct"])
    if is_fail:
        penalty = job.get("penalty", 30)
        work_timers[job_id] = now

        if has_fine_immunity:
            return False, 0, "🪖 <b>БРОНЯ ОМОНА СПАСЛА!</b> Тебя пытались оштрафовать, но броня защитила от штрафа (0 ₪ потерь)!", None

        fail_list = job.get("fail_phrases", ["🚨 Штраф: -{penalty} ₪!"])
        raw_fail = random.choice(fail_list).format(penalty=penalty, reward=0)
        clean_fail = re.sub(r'<[^>]+>', '', raw_fail)
        return False, penalty, clean_fail, None

    # Check for Jackpot (5% chance)
    is_jackpot = random.random() < 0.05 and bool(job.get("jackpot_phrases"))
    if is_jackpot:
        mult = random.randint(2, 3)
        base_reward = random.randint(job["reward_range"][0], job["reward_range"][1])
        reward = int(base_reward * mult * salary_multiplier)
        work_timers[job_id] = now
        current_items["work_shifts"] = current_items.get("work_shifts", 0) + 1
        jp_tmpl = random.choice(job["jackpot_phrases"]).format(reward=reward, penalty=0)
        clean_jp = re.sub(r'<[^>]+>', '', jp_tmpl)
        if gear_buffs:
            clean_jp += f" (Бонусы: {', '.join(gear_buffs)})"
        return True, reward, clean_jp, None

    # Standard Success
    base_reward = random.randint(job["reward_range"][0], job["reward_range"][1])
    reward = int(base_reward * salary_multiplier)
    work_timers[job_id] = now
    current_items["work_shifts"] = current_items.get("work_shifts", 0) + 1
    total_shifts = current_items["work_shifts"]
    succ_list = job.get("phrases", ["✅ Успешно! +{reward} ₪"])
    raw_succ = random.choice(succ_list).format(reward=reward, penalty=0)
    clean_succ = re.sub(r'<[^>]+>', '', raw_succ)

    # Check work milestones achievements
    import achievements_engine
    if total_shifts >= 10:
        unl, a_info = achievements_engine.check_and_unlock_achievement(current_items, "ach_work_10")
        if unl and a_info:
            reward += a_info["reward_cash"]
            clean_succ += f" | 🏆 Ачивка: {a_info['name']} (+{a_info['reward_cash']} ₪)!"
    if total_shifts >= 50:
        unl, a_info = achievements_engine.check_and_unlock_achievement(current_items, "ach_work_50")
        if unl and a_info:
            reward += a_info["reward_cash"]
            clean_succ += f" | 🏆 Ачивка: {a_info['name']} (+{a_info['reward_cash']} ₪)!"
    if total_shifts >= 100:
        unl, a_info = achievements_engine.check_and_unlock_achievement(current_items, "ach_work_100")
        if unl and a_info:
            reward += a_info["reward_cash"]
            clean_succ += f" | 🏆 Ачивка: {a_info['name']} (+{a_info['reward_cash']} ₪)!"

    # Item Drop calculation
    dropped_item = None
    if job.get("item_drop"):
        chance = job.get("item_drop_chance", 0.05) * drop_rate_mult
        if random.random() < chance:
            dropped_item = job["item_drop"]

    # 8% chance to find a Trash Lootbox if wearing Grocery Bag
    if eq_head == "hat_bag" and random.random() < 0.08:
        dropped_item = "lootbox_trash"

    if gear_buffs:
        clean_succ += f" (Шмот: {', '.join(gear_buffs)})"

    return True, reward, f"✅ {clean_succ}", dropped_item
