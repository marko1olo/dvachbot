# -*- coding: utf-8 -*-
"""
common/reputation_engine.py — Newcomer Onboarding, Reputation Progression & Anti-Soft-Lock Engine.

Solves core user pain points (e.g. Post #468991 complaint):
1. Eradicates dry, hostile reputation blocks ("У вас недостаточно репутации!"): replaces them with
   friendly, culturally resonant onboarding alerts and 1-tap quick action buttons:
   [💼 Как заработать репутацию], [⚡ Первая смена на заводе], [ℹ️ Гайд новичка].
2. Eliminates soft locks: guarantees that a user with 0 shekels and 0 energy/health is never permanently
   stuck. Provides free rest (/rest), Abu humanitarian aid, and allows the survival entry job
   (🍾 Стеклотара, 0 shifts required) to always function as a lifeline.
3. Provides deterministic reputation calculations derived from user activity (shifts, posts, karma).
"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional, Tuple
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

# ══════════════════════════════════════════════════════════════════════════════
# REPUTATION TIERS & CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════

REPUTATION_TIERS: dict[str, dict[str, Any]] = {
    "newbie": {
        "title": "Новичок",
        "title_en": "Newbie",
        "title_jp": "初心者",
        "min_rep": 0,
        "max_rep": 4,
        "badge": "🌱",
        "desc": "Только что открыл для себя ТГАЧ. Вкатывайся в общение и делай первые смены!",
        "desc_en": "Fresh on TGACH. Join conversations and complete your first shifts!",
        "desc_jp": "TGACHへようこそ。会話に参加して最初のシフトをこなそう！",
    },
    "anon": {
        "title": "Анон",
        "title_en": "Anon",
        "title_jp": "名無し",
        "min_rep": 5,
        "max_rep": 19,
        "badge": "🎭",
        "desc": "Полноправный житель борды. Доступны базовые работы и все типы реакций.",
        "desc_en": "Full-fledged board citizen. Basic jobs and all reactions unlocked.",
        "desc_jp": "一人前の掲示板住人。基本ジョブと全リアクションが解放済み。",
    },
    "veteran": {
        "title": "Бывалый сыч",
        "title_en": "Veteran",
        "title_jp": "ベテラン",
        "min_rep": 20,
        "max_rep": 49,
        "badge": "🦉",
        "desc": "Опытный обитатель тредов. Доступны продвинутые вакансии и финансовые инструменты.",
        "desc_en": "Experienced thread dweller. Advanced vacancies and bank tools available.",
        "desc_jp": "スレッドの熟練者。上級職と銀行ツールが利用可能。",
    },
    "oldfag": {
        "title": "Олдфаг",
        "title_en": "Oldfag",
        "title_jp": "古参",
        "min_rep": 50,
        "max_rep": 99,
        "badge": "👑",
        "desc": "Уважаемый ветеран борды. Повышенные лимиты и доверие сообщества.",
        "desc_en": "Respected board oldfag. Elevated rate limits and community trust.",
        "desc_jp": "尊敬される古参住人。高いレートリミットと信頼。",
    },
    "ancient": {
        "title": "Патриарх Двача",
        "title_en": "Ancient Patriarch",
        "title_jp": "長老",
        "min_rep": 100,
        "max_rep": 999999,
        "badge": "🌌",
        "desc": "Живая легенда борды. Максимальные привилегии и авторитет.",
        "desc_en": "Living legend of the board. Maximum privileges and authority.",
        "desc_jp": "掲示板の生ける伝説。最大の権限と威厳。",
    },
}

# Free rest cooldown in seconds (5 minutes)
FREE_REST_COOLDOWN_SEC = 300.0


# ══════════════════════════════════════════════════════════════════════════════
# REPUTATION CALCULATION
# ══════════════════════════════════════════════════════════════════════════════

def calculate_user_reputation(
    user_id: int,
    items: Optional[dict] = None,
    posts_count: int = 0,
    balance: float = 0.0,
    is_verified_b: bool = False,
) -> int:
    """
    Рассчитывает честный рейтинг репутации пользователя (REP):
    - Смены на бирже труда (items['work_shifts']): +1 REP за смену.
    - Посты на доске (posts_count): +0.5 REP за пост (1 REP за каждые 2 поста).
    - Верификация /b/ (is_verified_b): +10 REP.
    - Бонусные очки репутации (items['reputation_bonus'] или items['reputation']): прямой плюс.
    - Баланс: +1 REP за каждые 10 000 ₪ капитала (максимум +20 REP от денег).
    """
    items_dict = items or {}
    rep = 0.0

    # 1. Shifts (truly earned labor)
    shifts = max(0, int(items_dict.get("work_shifts", 0) or 0))
    rep += shifts * 1.0

    # 2. Content posting (dialogues and threads)
    p_cnt = max(0, int(posts_count or 0))
    rep += p_cnt * 0.5

    # 3. Verified b-status
    if is_verified_b:
        rep += 10.0

    # 4. Item / direct bonus points
    bonus_rep = items_dict.get("reputation_bonus") or items_dict.get("reputation") or 0
    try:
        rep += float(bonus_rep)
    except (ValueError, TypeError):
        pass

    # 5. Wealth factor (slight bonus for active capitalists, capped at 20)
    try:
        bal = max(0.0, float(balance or 0.0))
        rep += min(20.0, bal / 10000.0)
    except (ValueError, TypeError):
        pass

    return max(0, int(rep))


def get_user_reputation_tier(rep_score: int) -> tuple[str, dict[str, Any]]:
    """Возвращает ключ тира и словарь метаданных для заданного количества REP."""
    score = max(0, int(rep_score or 0))
    for tier_key, meta in REPUTATION_TIERS.items():
        if meta["min_rep"] <= score <= meta["max_rep"]:
            return tier_key, meta
    return "ancient", REPUTATION_TIERS["ancient"]


def format_reputation_badge(rep_score: int, stream: str = "ru") -> str:
    """Форматирует красивый бейдж репутации (например: '🌱 Новичок (2 REP)')."""
    tier_key, meta = get_user_reputation_tier(rep_score)
    badge = meta["badge"]
    if stream == "en":
        title = meta["title_en"]
    elif stream == "jp":
        title = meta["title_jp"]
    else:
        title = meta["title"]
    return f"{badge} {title} ({rep_score} REP)"


# ══════════════════════════════════════════════════════════════════════════════
# ONBOARDING UI & ACTION KEYBOARDS
# ══════════════════════════════════════════════════════════════════════════════

def get_onboarding_alert_markup(stream: str = "ru") -> InlineKeyboardMarkup:
    """
    Генерирует инлайн-клавиатуру быстрого онбординга:
    [💼 Как заработать репутацию]
    [⚡ Первая смена на заводе]
    [ℹ️ Гайд новичка]
    """
    if stream == "en":
        btn_how = "💼 How to Earn Reputation"
        btn_shift = "⚡ First Job Shift"
        btn_guide = "ℹ️ Newcomer Guide"
    elif stream == "jp":
        btn_how = "💼 評判の上げ方"
        btn_shift = "⚡ 最初の仕事シフト"
        btn_guide = "ℹ️ 初心者ガイド"
    else:
        btn_how = "💼 Как заработать репутацию"
        btn_shift = "⚡ Первая смена на заводе"
        btn_guide = "ℹ️ Гайд новичка"

    buttons = [
        [InlineKeyboardButton(text=btn_how, callback_data="onboard_how_rep")],
        [InlineKeyboardButton(text=btn_shift, callback_data="onboard_first_shift")],
        [InlineKeyboardButton(text=btn_guide, callback_data="onboard_guide")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def format_newcomer_onboarding_alert(
    reason: str = "general",
    user_rep: int = 0,
    req_rep: int = 0,
    stream: str = "ru",
) -> str:
    """
    Формирует дружелюбное, культурно адаптированное онбординг-сообщение
    вместо грубой блокировки 'У вас недостаточно репутации!'.
    """
    badge = format_reputation_badge(user_rep, stream=stream)

    if stream == "en":
        return (
            f"🌱 <b>Welcome to TGACH, Anon!</b>\n"
            f"Your current status: <b>{badge}</b>.\n\n"
            f"💡 <b>Why is this gated?</b>\n"
            f"To protect the collective feed from automated spam and raid bots, advanced actions require "
            f"a little reputation (needed: <b>{req_rep} REP</b>).\n\n"
            f"✨ <b>No pay-to-win, no captchas:</b>\n"
            f"Reputation is earned immediately and completely free through regular board life! "
            f"Pick an option below to get started:"
        )
    elif stream == "jp":
        return (
            f"🌱 <b>TGACHへようこそ、名無しさん！</b>\n"
            f"現在のステータス: <b>{badge}</b>\n\n"
            f"💡 <b>制限の理由</b>\n"
            f"スパムボットや荒らしから掲示板を守るため、高度な機能には評判（必要: <b>{req_rep} REP</b>）が必要です。\n\n"
            f"✨ <b>課金なし・完全無料</b>\n"
            f"評判は掲示板での活動を通じて誰でもすぐに無料で獲得できます！以下のボタンから始めましょう:"
        )

    return (
        f"🌱 <b>Добро пожаловать в ТГАЧ, Анон!</b>\n"
        f"Твой текущий статус: <b>{badge}</b>.\n\n"
        f"💡 <b>Почему стоит ограничение?</b>\n"
        f"Чтобы рейдеры и спам-боты не засирали общий поток доски, для этого действия требуется немного "
        f"авторитета (нужно: <b>{req_rep} REP</b>, у тебя: <b>{user_rep} REP</b>).\n\n"
        f"✨ <b>Никакого доната и платных смс:</b>\n"
        f"Репутация зарабатывается мгновенно, честно и абсолютно бесплатно прямо во время обычной жизни на борде! "
        f"Начни с простой смены или почитай гайд:"
    )


def format_how_to_earn_reputation(stream: str = "ru") -> str:
    """Подробный, понятный мануал о способах заработка репутации."""
    if stream == "en":
        return (
            "💼 <b>How to Earn Reputation on TGACH (100% Free):</b>\n\n"
            "1. 🏭 <b>Labor Exchange (/work):</b>\n"
            "• Each shift completed awards <b>+1 REP</b> directly.\n"
            "• Start with 🍾 <i>Bottle Collection</i> (0 shifts required, zero cost) — work your way up to Courier and Factory!\n\n"
            "2. 💬 <b>Board Posting & Replies:</b>\n"
            "• Every 2 posts or replies grant <b>+1 REP</b>.\n"
            "• Jump into existing threads or start a fresh topic.\n\n"
            "3. 👍 <b>Reactions from Anons:</b>\n"
            "• Quality posts receive 👍 reactions which award shekels to your wallet.\n\n"
            "4. 📨 <b>Invite Friends (/ref):</b>\n"
            "• Share your personal link to earn starting funds and reputation.\n\n"
            "<i>No barrier can stop a motivated Anon. Pick a shift and begin!</i>"
        )
    elif stream == "jp":
        return (
            "💼 <b>TGACHで評判（REP）を獲得する方法（完全無料）:</b>\n\n"
            "1. 🏭 <b>労働取引所 (/work):</b>\n"
            "• 1シフト完了ごとに <b>+1 REP</b> 獲得。\n"
            "• 🍾 <i>空き瓶拾い</i>（必要シフト0、費用0）から始めて、工場やフリーランスへステップアップ！\n\n"
            "2. 💬 <b>掲示板への投稿と返信:</b>\n"
            "• 2件の投稿または返信で <b>+1 REP</b> 獲得。\n\n"
            "3. 👍 <b>アノンからのリアクション:</b>\n"
            "• 良い投稿には 👍 がつき、シェケルが手に入ります。\n\n"
            "4. 📨 <b>招待プログラム (/ref):</b>\n"
            "• 招待リンクを共有して資金と評判をゲット！"
        )

    return (
        "💼 <b>Как заработать репутацию на ТГАЧЕ (быстро и бесплатно):</b>\n\n"
        "1. 🏭 <b>Смены на Бирже Труда (/work):</b>\n"
        "• Каждая отработанная смена даёт <b>+1 REP</b> к стажу.\n"
        "• Вакансия 🍾 <i>«Сбор стеклотары»</i> доступна абсолютно с нуля (0 смен стажа, 0 затрат) "
        "и работает даже при нулевой энергии! За ней откроются Дворник, Курьер и Завод.\n\n"
        "2. 💬 <b>Постинг и реплаи на борде:</b>\n"
        "• Каждые 2 отправленных сообщения на доску дают <b>+1 REP</b>.\n"
        "• Отвечай через Reply на посты других анонов, развивай живые треды.\n\n"
        "3. 👍 <b>Одобрение анонов (Реакции):</b>\n"
        "• За годный контент аноны ставят 👍, приносящие звонкие шекели в твой кошелёк.\n\n"
        "4. 📨 <b>Реферальная программа (/ref):</b>\n"
        "• Приглашай знакомых сычей по личной ссылке и получай стартовые бонусы.\n\n"
        "<i>Никаких тупиков — делай первую смену и вкатывайся!</i>"
    )


def format_newcomer_guide(stream: str = "ru") -> str:
    """
    Компактный, разгруженный гайд для новичков (ответ на жалобу 'интерфейс перегруженный').
    Без лишней воды, строго по делу.
    """
    if stream == "en":
        return (
            "ℹ️ <b>Quick Newcomer Guide to TGACH:</b>\n\n"
            "• <b>Anonymous Posting:</b> Send any text, image, or video directly to the bot. It publishes anonymously to the board under a post number.\n"
            "• <b>Replying:</b> Swipe / reply to any chat message to link your thoughts into a thread.\n"
            "• <b>Earning Shekels:</b> Write <code>/work</code> to open the Labor Exchange. 🍾 <i>Bottle Collection</i> is always free.\n"
            "• <b>Resting:</b> Run <code>/rest</code> if your energy hits 0⚡ to recharge for free.\n"
            "• <b>Passport:</b> Check <code>/passport</code> or <code>/me</code> to view your inventory, reputation, and balance."
        )
    elif stream == "jp":
        return (
            "ℹ️ <b>TGACH 初心者クイックガイド:</b>\n\n"
            "• <b>匿名投稿:</b> ボットにテキストや画像を送るだけで、匿名番号で即座に板に流れます。\n"
            "• <b>返信（Reply）:</b> メッセージに返信するとスレッドが繋がります。\n"
            "• <b>シェケルを稼ぐ:</b> <code>/work</code> で労働所を開きます。🍾 <i>空き瓶拾い</i> はいつでも無料。\n"
            "• <b>休息:</b> エネルギーが切れたら <code>/rest</code> で無料回復。\n"
            "• <b>パスポート:</b> <code>/passport</code> または <code>/me</code> でステータス確認。"
        )

    return (
        "ℹ️ <b>Быстрый гайд новичка по ТГАЧУ:</b>\n\n"
        "• <b>Как постить:</b> Просто отправь любой текст, картинку или видео боту — сообщение анонимно "
        "улетит в общий поток под порядковым номером.\n"
        "• <b>Как отвечать:</b> Сделай <b>Reply (Ответить)</b> на сообщение анона, чтобы привязать реплай к треду.\n"
        "• <b>Как заработать:</b> Напиши <code>/work</code> — откроется Биржа труда. Первая работа 🍾 <i>Сбор стеклотары</i> "
        "всегда бесплатна и открыта сразу.\n"
        "• <b>Если устал:</b> Напиши <code>/rest</code> — бесплатный отдых восстановит энергию и здоровье без шекелей.\n"
        "• <b>Твой профиль:</b> Напиши <code>/passport</code> или <code>/me</code>, чтобы глянуть баланс, шмот и репутацию.\n\n"
        "<i>Никаких профилей, VPN и регистраций — ты дома, Анон!</i>"
    )


# ══════════════════════════════════════════════════════════════════════════════
# ANTI-SOFT-LOCK & RESCUE ENGINE
# ══════════════════════════════════════════════════════════════════════════════

def is_soft_locked(items: Optional[dict], balance: float = 0.0) -> bool:
    """
    Определяет, находится ли пользователь в состоянии 'soft lock':
    - Баланс <= 0 (нет денег даже на покупку энергетика/лекарства).
    - Энергия <= 0 ИЛИ Здоровье <= 0 (заблокированы обычные смены).
    """
    items_dict = items or {}
    try:
        bal = float(balance or 0.0)
    except (ValueError, TypeError):
        bal = 0.0

    try:
        energy = float(items_dict.get("energy", 100.0) or 0.0)
    except (ValueError, TypeError):
        energy = 100.0

    try:
        health = float(items_dict.get("health", 100.0) or 0.0)
    except (ValueError, TypeError):
        health = 100.0

    return bal <= 0.0 and (energy <= 0.0 or health <= 0.0)


def rescue_soft_locked_user(
    user_id: int,
    items: dict,
    balance: float = 0.0,
    stream: str = "ru",
) -> tuple[bool, str, dict]:
    """
    Анти-софтлок спасение: если у пользователя 0 шекелей и истощены жизненные ресурсы,
    Фонд Абу бесплатно выдает гуманитарный паёк:
    - Восстанавливает энергию до минимума (40⚡).
    - Восстанавливает здоровье до минимума (40❤️).
    - Защищает от перманентного тупика.
    """
    if not is_soft_locked(items, balance):
        return False, "", items

    items["energy"] = max(float(items.get("energy", 0.0) or 0.0), 40.0)
    items["health"] = max(float(items.get("health", 0.0) or 0.0), 40.0)

    if stream == "en":
        msg = (
            "🥫 <b>ABU'S HUMANITARIAN AID PACK!</b>\n\n"
            "Abu noticed you were stuck with 0 shekels and 0 energy on the frozen sidewalk.\n"
            "You received a warm can of stew and hot chifir tea: <b>+40⚡ Energy</b> and <b>+40❤️ Health</b>!\n"
            "Head straight to 🍾 <i>Bottle Collection</i> (/work) to get back on your feet!"
        )
    elif stream == "jp":
        msg = (
            "🥫 <b>アブの人道支援パック！</b>\n\n"
            "所持金ゼロ・エネルギーゼロで行き倒れていたあなたに、アブから支援物資が届きました。\n"
            "温かい缶詰と特製茶を補給: <b>+40⚡ エネルギー</b>, <b>+40❤️ 体力</b> 回復！\n"
            "🍾 <i>空き瓶拾い</i> (/work) で再起を図ろう！"
        )
    else:
        msg = (
            "🥫 <b>ГУМАНИТАРНАЯ ПОМОЩЬ ОТ АБУ!</b>\n\n"
            "Сам Абу лично заметил, что ты сидишь на теплотрассе с 0 шекелями и абсолютно без сил.\n"
            "Тебе подкинули банку армейской тушёнки и кружку горячего чифиря: <b>+40⚡ Энергии</b> и <b>+40❤️ Здоровья</b>!\n"
            "Срочно дуй на смену по сбору стеклотары (<code>/work</code>), чтобы встать на ноги!"
        )

    return True, msg, items


def execute_free_rest(
    user_id: int,
    items: dict,
    now_ts: Optional[float] = None,
    stream: str = "ru",
) -> tuple[bool, str, int]:
    """
    Выполняет бесплатный отдых (/rest) для восстановления энергии и здоровья:
    - Восстанавливает +35⚡ энергии (до макс 100).
    - Восстанавливает +15❤️ здоровья (до макс 100).
    - Имеет честный кулдаун (5 минут), но если энергия строго <= 0, кулдаун сбрасывается для защиты от софтлока.
    """
    now = float(now_ts) if now_ts is not None else time.time()
    last_rest = float(items.get("last_free_rest_ts", 0.0) or 0.0)

    cur_energy = float(items.get("energy", 100.0) or 0.0)
    cur_health = float(items.get("health", 100.0) or 0.0)

    # If completely depleted (<= 0), allow immediate rescue rest regardless of timer
    is_critical = cur_energy <= 0.0 or cur_health <= 0.0

    if not is_critical and (now - last_rest < FREE_REST_COOLDOWN_SEC):
        remaining = int(FREE_REST_COOLDOWN_SEC - (now - last_rest))
        mins, secs = divmod(remaining, 60)
        time_str = f"{mins}м {secs}с" if mins > 0 else f"{secs}с"

        if stream == "en":
            return False, f"⏳ You recently rested! Take a breather, next rest in <b>{time_str}</b>.", remaining
        elif stream == "jp":
            return False, f"⏳ 最近休憩したばかりです。次の休憩まであと <b>{time_str}</b>。", remaining
        return False, f"⏳ Ты недавно отдыхал! Сделай вдох, следующий бесплатный отдых через <b>{time_str}</b>.", remaining

    new_energy = min(100.0, max(0.0, cur_energy) + 35.0)
    new_health = min(100.0, max(0.0, cur_health) + 15.0)

    items["energy"] = new_energy
    items["health"] = new_health
    items["last_free_rest_ts"] = now

    if stream == "en":
        msg = (
            f"🛌 <b>Resting on the soft couch:</b>\n"
            f"You took a deep nap and drank warm water.\n"
            f"Restored: <b>+35⚡ Energy</b> (now {int(new_energy)}⚡), <b>+15❤️ Health</b> (now {int(new_health)}❤️)!"
        )
    elif stream == "jp":
        msg = (
            f"🛌 <b>ソファーで一休み:</b>\n"
            f"ぐっすり眠って温かい水を飲みました。\n"
            f"回復: <b>+35⚡ エネルギー</b> (現在 {int(new_energy)}⚡), <b>+15❤️ 体力</b> (現在 {int(new_health)}❤️)!"
        )
    else:
        msg = (
            f"🛌 <b>Сычевание на диване завершено:</b>\n"
            f"Ты хорошенько вздремнул под бубнёж стрима и заварил свежего чая.\n"
            f"Восстановлено: <b>+35⚡ Энергии</b> (стало {int(new_energy)}⚡), <b>+15❤️ Здоровья</b> (стало {int(new_health)}❤️)!"
        )

    return True, msg, 0


# ══════════════════════════════════════════════════════════════════════════════
# UNIFIED REPUTATION GATE CHECK
# ══════════════════════════════════════════════════════════════════════════════

def check_reputation_gate(
    user_id: int,
    action: str,
    items: Optional[dict] = None,
    posts_count: int = 0,
    balance: float = 0.0,
    required_rep: int = 0,
    stream: str = "ru",
) -> tuple[bool, Optional[str], Optional[InlineKeyboardMarkup]]:
    """
    Проверяет, проходит ли пользователь репутационный гейт для действия.
    Если REP < required_rep:
    - Возвращает (False, дружелюбный онбординг-алерт, клавиатуру с кнопками).
    Если проходит:
    - Возвращает (True, None, None).
    """
    user_rep = calculate_user_reputation(
        user_id,
        items=items,
        posts_count=posts_count,
        balance=balance,
    )

    if user_rep >= required_rep:
        return True, None, None

    alert_text = format_newcomer_onboarding_alert(
        reason=action,
        user_rep=user_rep,
        req_rep=required_rep,
        stream=stream,
    )
    markup = get_onboarding_alert_markup(stream=stream)
    return False, alert_text, markup
