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
        "desc": "Свежее мясо с порога. На параше не задерживайся — дуй в /work таскать бутылки и набивай REP.",
        "desc_en": "Fresh meat off the boat. Stop lurking and hit /work to earn your keep.",
        "desc_jp": "新参の養分。さっさとレスして /work で底辺労働を始めろ。",
    },
    "anon": {
        "title": "Анон",
        "title_en": "Anon",
        "title_jp": "名無し",
        "min_rep": 5,
        "max_rep": 19,
        "badge": "🎭",
        "desc": "Уже не бесправный ньюфаг, но до олдфага как до Луны раком. Базовые смены и реакции открыты.",
        "desc_en": "Barely promoted from lurker scum. Basic shifts and reactions unlocked.",
        "desc_jp": "ようやく一人前の名無し。基本の底辺労働とリアクションが解放済み。",
    },
    "veteran": {
        "title": "Бывалый сыч",
        "title_en": "Veteran",
        "title_jp": "ベテラン",
        "min_rep": 20,
        "max_rep": 49,
        "badge": "🦉",
        "desc": "Просидел не одну пару треников в тредах. Открыты жирные вакансии и банковские схемы Абу.",
        "desc_en": "Survived enough shitstorms to know the ropes. Juicier jobs and Abu's bank unlocked.",
        "desc_jp": "数々のスレを生き延びた古株。上級職とアブ銀行の裏ワザが使える。",
    },
    "oldfag": {
        "title": "Олдфаг",
        "title_en": "Oldfag",
        "title_jp": "古参",
        "min_rep": 50,
        "max_rep": 99,
        "badge": "👑",
        "desc": "Прожжённый ветеран подвалов /b/. Повышенные лимиты, иммунитет к нытью ньюфагов и карт-бланш на стёб.",
        "desc_en": "Hardened /b/ basement dweller. Elevated limits and full license to roast newbies.",
        "desc_jp": "掲示板の重鎮。高いレートリミットと新参を煽る特権を持つ。",
    },
    "ancient": {
        "title": "Патриарх Двача",
        "title_en": "Ancient Patriarch",
        "title_jp": "長老",
        "min_rep": 100,
        "max_rep": 999999,
        "badge": "🌌",
        "desc": "Ископаемый динозавр Тиреча. Максимальные привилегии, запах старого ЭЛТ-монитора и право ссать с колокольни.",
        "desc_en": "Fossilized imageboard relic. Maximum privileges and authority to dunk from orbit.",
        "desc_jp": "掲示板の生ける化石。最大の権限と絶対的な威厳。",
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
    Формирует жёсткое, но понятное онбординг-сообщение с лором ТГАЧа
    вместо сухой заглушки 'У вас недостаточно репутации!'.
    """
    badge = format_reputation_badge(user_rep, stream=stream)

    if stream == "en":
        return (
            f"🌱 <b>HOLD UP, NEWFAG!</b>\n"
            f"Your current rank: <b>{badge}</b>.\n\n"
            f"🚧 <b>Why the gate?</b>\n"
            f"To keep raid bots and braindead spammers from drowning the board in slop, this action needs "
            f"<b>{req_rep} REP</b> (you have <b>{user_rep} REP</b>).\n\n"
            f"💊 <b>Zero paywalls, zero captchas:</b>\n"
            f"Farm REP free in minutes by grinding a shift (<code>/work</code>) or posting in live threads. "
            f"Hit the buttons below:"
        )
    elif stream == "jp":
        return (
            f"🌱 <b>待てや新参！</b>\n"
            f"現在の階級: <b>{badge}</b>\n\n"
            f"🚧 <b>なぜ制限されてる？</b>\n"
            f"荒らしボットやスパム業者を弾くため、この操作には <b>{req_rep} REP</b> が必要だ（お前は <b>{user_rep} REP</b>）。\n\n"
            f"💊 <b>課金不要・完全無料:</b>\n"
            f"<code>/work</code> で労働するかスレに書き込めばすぐ貯まる。下のボタンから動け:"
        )

    return (
        f"🌱 <b>ТОРМОЗНИ, НЬЮФАГ!</b>\n"
        f"Твоя масть сейчас: <b>{badge}</b>.\n\n"
        f"🚧 <b>Чё за шлагбаум?</b>\n"
        f"Чтобы спам-боты, вайперы и залётная школота не превратили доску в филиал Одноклассников, сюда пускают с репой от "
        f"<b>{req_rep} REP</b> (у тебя пока <b>{user_rep} REP</b>).\n\n"
        f"💊 <b>Без доната, смс и паспорта:</b>\n"
        f"Репа фармится бесплатно за пару минут: сдай бутылки на смене (<code>/work</code>) или навали годноты в тредах. "
        f"Хватай кнопки ниже:"
    )


def format_how_to_earn_reputation(stream: str = "ru") -> str:
    """Понятный, недушный мануал по фарму репутации без софтлока."""
    if stream == "en":
        return (
            "💼 <b>How to Farm Reputation on TGACH (Zero Paywalls):</b>\n\n"
            "1. 🏭 <b>Labor Exchange (/work):</b>\n"
            "• Every shift completed pays out <b>+1 REP</b> directly.\n"
            "• Start with 🍾 <i>Bottle Collection</i> (0 shifts needed, zero cost) and climb to Courier & Factory.\n\n"
            "2. 💬 <b>Board Shitposting & Replies:</b>\n"
            "• Every 2 posts or replies grant <b>+1 REP</b>.\n"
            "• Stop lurking — jump into threads and argue.\n\n"
            "3. 👍 <b>Anon Approval (Reactions):</b>\n"
            "• Good posts farm 👍 reactions and drop real shekels into your wallet.\n\n"
            "4. 📨 <b>Drag Friends In (/ref):</b>\n"
            "• Share your invite link to pocket referral shekels and clout.\n\n"
            "<i>No dead ends here — grab a shift and crawl out of the gutter!</i>"
        )
    elif stream == "jp":
        return (
            "💼 <b>TGACHで評判（REP）を稼ぐ方法（完全無料）:</b>\n\n"
            "1. 🏭 <b>労働取引所 (/work):</b>\n"
            "• 1シフト完了ごとに <b>+1 REP</b> 獲得。\n"
            "• 🍾 <i>空き瓶拾い</i>（必要シフト0、費用0）から始めて、工場や闇バイトへ這い上がれ！\n\n"
            "2. 💬 <b>掲示板への書き込み＆レス:</b>\n"
            "• 2件の投稿または返信で <b>+1 REP</b> 獲得。\n\n"
            "3. 👍 <b>アノンからの評価:</b>\n"
            "• 良レスに 👍 がつけば財布にシェケルが転がり込む。\n\n"
            "4. 📨 <b>新参の勧誘 (/ref):</b>\n"
            "• 招待リンクを撒いて養分を連れてくればボーナス獲得！"
        )

    return (
        "💼 <b>Как заработать репутацию на ТГАЧЕ (без доната и унижений):</b>\n\n"
        "1. 🏭 <b>Пахота на Бирже Труда (/work):</b>\n"
        "• Каждая отработанная смена капает <b>+1 REP</b> в трудовую книжку.\n"
        "• Вакансия 🍾 <i>«Сбор стеклотары»</i> открыта даже полному бомжу (0 смен, 0 затрат, пашет и при нулевой энергии). "
        "Дальше откроются Дворник, Курьер и Завод.\n\n"
        "2. 💬 <b>Постинг и реплаи на борде:</b>\n"
        "• Каждые 2 поста или реплая на доске дают <b>+1 REP</b>.\n"
        "• Врывайся в треды через Reply, набрасывай годноту — хватит молчать в углу.\n\n"
        "3. 👍 <b>База от анонов (Реакции):</b>\n"
        "• За годный высер сычи ставят 👍 — с каждого плюса в кошелёк летят шекели.\n\n"
        "4. 📨 <b>Вербовка мяса (/ref):</b>\n"
        "• Затащи знакомых битардов по своей ссылке и сруби жирный бонус на старт.\n\n"
        "<i>Софтлока тут нет — жми на смену и вылезай со дна!</i>"
    )


def format_newcomer_guide(stream: str = "ru") -> str:
    """
    Компактный, разгруженный гайд для новичков без корпоративной воды.
    """
    if stream == "en":
        return (
            "ℹ️ <b>Quick Newcomer Guide to TGACH:</b>\n\n"
            "• <b>Posting:</b> Send any text, pic, or video directly to the bot — it drops anonymously onto the board.\n"
            "• <b>Replying:</b> Swipe / reply to any post to jump into the thread brawl.\n"
            "• <b>Earning Shekels:</b> Run <code>/work</code> for the Labor Exchange. 🍾 <i>Bottle Collection</i> is free from shift #0.\n"
            "• <b>Resting:</b> Hit <code>/rest</code> when energy hits 0⚡ to rot on the couch and recharge free.\n"
            "• <b>Passport:</b> Check <code>/passport</code> or <code>/me</code> for your stash, gear, and REP.\n\n"
            "<i>No logins, no tracking, no janny tears — sink or swim, Anon!</i>"
        )
    elif stream == "jp":
        return (
            "ℹ️ <b>TGACH 初心者クイックガイド:</b>\n\n"
            "• <b>匿名投稿:</b> ボットに文字や画像を送るだけで即座に板へ匿名投下される。\n"
            "• <b>返信（Reply）:</b> レスに返信すればスレッドのレスバに参加可能。\n"
            "• <b>稼ぎ方:</b> <code>/work</code> で労働所を開け。🍾 <i>空き瓶拾い</i> はゼロから無料。\n"
            "• <b>休息:</b> エネルギーが0⚡になったら <code>/rest</code> で無料回復しろ。\n"
            "• <b>ステータス:</b> <code>/passport</code> または <code>/me</code> で所持金とREPを確認。"
        )

    return (
        "ℹ️ <b>Быстрый гайд новичка по ТГАЧУ:</b>\n\n"
        "• <b>Как постить:</b> Кидай любой текст, пикчу или видео прямо боту — высер анонимно улетит в тред под номером.\n"
        "• <b>Как отвечать:</b> Жми <b>Reply (Ответить)</b> на пост анона, чтобы ввязаться в срач в треде.\n"
        "• <b>Как заработать:</b> Пиши <code>/work</code> — откроется биржа рабского труда. Бомж-работа 🍾 <i>Сбор стеклотары</i> "
        "открыта сразу.\n"
        "• <b>Если устал:</b> Пиши <code>/rest</code> — бесплатное сычевание на диване поднимет энергию и ХП с нуля.\n"
        "• <b>Твой профиль:</b> Пиши <code>/passport</code> или <code>/me</code>, чтобы чекнуть шекели, шмот и репу.\n\n"
        "<i>Никаких паспортов, майоров и регистраций — либо вливайся, либо откисай!</i>"
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
            return False, f"⏳ You just rested! Get your ass off the couch later — next free nap in <b>{time_str}</b>.", remaining
        elif stream == "jp":
            return False, f"⏳ さっき休んだばかりだろ！次の無料休憩まであと <b>{time_str}</b>。", remaining
        return False, f"⏳ Ты недавно отдыхал! Хорош проперживать диван — следующий бесплатный перекур через <b>{time_str}</b>.", remaining

    new_energy = min(100.0, max(0.0, cur_energy) + 35.0)
    new_health = min(100.0, max(0.0, cur_health) + 15.0)

    items["energy"] = new_energy
    items["health"] = new_health
    items["last_free_rest_ts"] = now

    if stream == "en":
        msg = (
            f"🛌 <b>Couch rotting complete:</b>\n"
            f"You passed out to background brainrot and chugged lukewarm energy drink residue.\n"
            f"Restored: <b>+35⚡ Energy</b> (now {int(new_energy)}⚡), <b>+15❤️ Health</b> (now {int(new_health)}❤️)!"
        )
    elif stream == "jp":
        msg = (
            f"🛌 <b>ソファーでの引きこもり完了:</b>\n"
            f"ゴミ配信をBGMに気絶して、ぬるいエナドリを飲み干した。\n"
            f"回復: <b>+35⚡ エネルギー</b> (現在 {int(new_energy)}⚡), <b>+15❤️ 体力</b> (現在 {int(new_health)}❤️)!"
        )
    else:
        msg = (
            f"🛌 <b>Сычевание на диване завершено:</b>\n"
            f"Ты отрубился под бубнёж шизо-стрима и хлебнул вчерашнего чифиря из треснувшей кружки.\n"
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
    - Возвращает (False, понятный онбординг-алерт в стиле ТГАЧа, клавиатуру с кнопками).
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
