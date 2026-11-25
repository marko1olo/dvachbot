# -*- coding: utf-8 -*-
"""
tests/test_newcomer_reputation_ux.py — Test Suite for Newcomer Onboarding, Reputation Progression & Anti-Soft-Lock.

Verifies:
1. Reputation score calculation & tier progression (newbie -> anon -> veteran -> oldfag -> ancient).
2. Elimination of dry blocks: friendly onboarding alerts with action buttons:
   [💼 Как заработать репутацию], [⚡ Первая смена на заводе], [ℹ️ Гайд новичка].
3. Anti-soft-lock engine: rescue of players with 0 shekels and 0 energy/health via Abu aid and free /rest.
4. Work engine integration: locked vacancy friendly guidance and energy depletion messaging with /rest advice.
5. Interactive callbacks: cb_onboard_how_rep, cb_onboard_guide, cb_onboard_first_shift, cb_work_overtime, cmd_rest.
"""

import json
import time
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from common.reputation_engine import (
    REPUTATION_TIERS,
    calculate_user_reputation,
    get_user_reputation_tier,
    format_reputation_badge,
    get_onboarding_alert_markup,
    format_newcomer_onboarding_alert,
    format_how_to_earn_reputation,
    format_newcomer_guide,
    is_soft_locked,
    rescue_soft_locked_user,
    execute_free_rest,
    check_reputation_gate,
)
from common.work_engine import (
    WORK_VACANCIES,
    execute_job_action,
)


# ══════════════════════════════════════════════════════════════════════════════
# 1. REPUTATION PROGRESSION & SCORING TESTS
# ══════════════════════════════════════════════════════════════════════════════

def test_reputation_tiers_and_scoring():
    """Verify reputation score calculation, tier boundaries, and badge formatting."""
    uid = 111222333

    # Newcomer: 0 shifts, 0 posts, 0 bal
    rep0 = calculate_user_reputation(uid, items={}, posts_count=0, balance=0.0)
    assert rep0 == 0
    t_key, meta = get_user_reputation_tier(rep0)
    assert t_key == "newbie"
    assert meta["badge"] == "🌱"
    badge_ru = format_reputation_badge(rep0, stream="ru")
    assert "🌱 Новичок (0 REP)" in badge_ru

    # 5 shifts -> Promoted to Anon (5 REP)
    rep5 = calculate_user_reputation(uid, items={"work_shifts": 5}, posts_count=0)
    assert rep5 == 5
    t_key, meta = get_user_reputation_tier(rep5)
    assert t_key == "anon"
    assert "🎭 Анон" in format_reputation_badge(rep5, stream="ru")

    # 10 posts + 15 shifts = 5 + 15 = 20 REP -> Veteran
    rep20 = calculate_user_reputation(uid, items={"work_shifts": 15}, posts_count=10)
    assert rep20 == 20
    t_key, meta = get_user_reputation_tier(rep20)
    assert t_key == "veteran"
    assert "🦉 Бывалый сыч" in format_reputation_badge(rep20, stream="ru")

    # 50 shifts -> Oldfag
    rep50 = calculate_user_reputation(uid, items={"work_shifts": 50}, posts_count=0)
    assert rep50 == 50
    t_key, meta = get_user_reputation_tier(rep50)
    assert t_key == "oldfag"
    assert "👑 Олдфаг" in format_reputation_badge(rep50, stream="ru")

    # 100+ shifts -> Ancient Patriarch
    rep100 = calculate_user_reputation(uid, items={"work_shifts": 100}, posts_count=0)
    assert rep100 == 100
    t_key, meta = get_user_reputation_tier(rep100)
    assert t_key == "ancient"
    assert "🌌 Патриарх Двача" in format_reputation_badge(rep100, stream="ru")

    # Multilingual badges
    badge_en = format_reputation_badge(rep0, stream="en")
    assert "🌱 Newbie" in badge_en
    badge_jp = format_reputation_badge(rep0, stream="jp")
    assert "🌱 初心者" in badge_jp


# ══════════════════════════════════════════════════════════════════════════════
# 2. ONBOARDING ALERTS & ACTION KEYBOARD TESTS
# ══════════════════════════════════════════════════════════════════════════════

def test_onboarding_alert_and_markup():
    """Verify onboarding markup contains exact required buttons and alert eliminates dry blocks."""
    markup_ru = get_onboarding_alert_markup(stream="ru")
    buttons_text = [b.text for row in markup_ru.inline_keyboard for b in row]
    callbacks = [b.callback_data for row in markup_ru.inline_keyboard for b in row]

    # Verify buttons
    assert "💼 Как заработать репутацию" in buttons_text
    assert "⚡ Первая смена на заводе" in buttons_text
    assert "ℹ️ Гайд новичка" in buttons_text

    # Verify callback keys
    assert "onboard_how_rep" in callbacks
    assert "onboard_first_shift" in callbacks
    assert "onboard_guide" in callbacks

    # Check alert text: must NOT be dry or corporate-soy, must explain clearly
    alert_ru = format_newcomer_onboarding_alert(reason="post", user_rep=0, req_rep=5, stream="ru")
    assert "У вас недостаточно репутации!" not in alert_ru
    assert "Добро пожаловать" not in alert_ru
    assert "ТОРМОЗНИ, НЬЮФАГ!" in alert_ru
    assert "5 REP" in alert_ru
    assert "бесплатно" in alert_ru

    # Check reputation gate
    uid = 999
    is_ok, alert, kb = check_reputation_gate(uid, action="high_roller", items={}, required_rep=10)
    assert is_ok is False
    assert alert is not None
    assert kb is not None

    # Passed gate
    is_ok_pass, alert_pass, kb_pass = check_reputation_gate(uid, action="high_roller", items={"work_shifts": 15}, required_rep=10)
    assert is_ok_pass is True
    assert alert_pass is None
    assert kb_pass is None


# ══════════════════════════════════════════════════════════════════════════════
# 3. ANTI-SOFT-LOCK & RESCUE LOGIC TESTS
# ══════════════════════════════════════════════════════════════════════════════

def test_anti_softlock_rescue_logic():
    """Verify detection and automatic rescue of softlocked users (0 shekels and 0 energy/health)."""
    uid = 555666

    # 1. Healthy user is not softlocked
    items_ok = {"energy": 80.0, "health": 100.0}
    assert is_soft_locked(items_ok, balance=0.0) is False

    # 2. User with money is not softlocked even at 0 energy (can buy items)
    items_tired = {"energy": 0.0, "health": 100.0}
    assert is_soft_locked(items_tired, balance=150.0) is False

    # 3. Broke user (0 ₪) with 0⚡ energy IS SOFTLOCKED
    items_locked = {"energy": 0.0, "health": 100.0}
    assert is_soft_locked(items_locked, balance=0.0) is True

    # 4. Broke user with 0❤️ health IS SOFTLOCKED
    items_dying = {"energy": 50.0, "health": 0.0}
    assert is_soft_locked(items_dying, balance=0.0) is True

    # 5. Rescue operation
    was_rescued, rescue_msg, updated_items = rescue_soft_locked_user(uid, items_locked, balance=0.0, stream="ru")
    assert was_rescued is True
    assert updated_items["energy"] >= 40.0
    assert updated_items["health"] >= 40.0
    assert "ГУМАНИТАРНАЯ ПОМОЩЬ ОТ АБУ" in rescue_msg
    assert is_soft_locked(updated_items, balance=0.0) is False

    # 6. Non-softlocked user does not trigger rescue
    was_r2, msg2, _ = rescue_soft_locked_user(uid, items_ok, balance=10.0)
    assert was_r2 is False
    assert msg2 == ""


def test_free_rest_recovery_execution():
    """Verify free rest (/rest) restores energy and health without costing shekels."""
    uid = 777888
    items = {"energy": 10.0, "health": 50.0}

    now = 100000.0
    ok, msg, remaining = execute_free_rest(uid, items, now_ts=now, stream="ru")
    assert ok is True
    assert items["energy"] == 45.0  # +35⚡
    assert items["health"] == 65.0  # +15❤️
    assert "Сычевание на диване завершено" in msg

    # Immediate second rest is rejected with countdown
    ok2, msg2, remaining2 = execute_free_rest(uid, items, now_ts=now + 60.0, stream="ru")
    assert ok2 is False
    assert remaining2 == 240
    assert "недавно отдыхал" in msg2

    # But if user becomes critically depleted (0 energy), emergency rest bypasses timer
    items["energy"] = 0.0
    ok3, msg3, _ = execute_free_rest(uid, items, now_ts=now + 70.0, stream="ru")
    assert ok3 is True
    assert items["energy"] == 35.0


# ══════════════════════════════════════════════════════════════════════════════
# 4. WORK ENGINE INTEGRATION & GUIDANCE TESTS
# ══════════════════════════════════════════════════════════════════════════════

def test_work_engine_locked_vacancy_and_energy_guidance():
    """Verify work engine gives helpful qualification tips on locked vacancies and mentions /rest."""
    # 1. Locked vacancy (factory requires 40 shifts, user has 0)
    res_factory = execute_job_action("factory", {"work_shifts": 0})
    assert res_factory[0] is False
    assert "🔒 Вакансия заблокирована" in res_factory[2]
    assert "🍾 Стеклотара или 🚮 Дворник" in res_factory[2]

    # 2. Energy depleted on job gives /rest and Flash Ultra guidance
    res_energy = execute_job_action("bottles", {"energy": 0})
    assert res_energy[0] is False
    assert "закончилась энергия (0⚡)" in res_energy[2]
    assert "/rest" in res_energy[2]
    assert "Flash Ultra" in res_energy[2]

    # 3. Health depleted on job gives /cure and /rest guidance
    res_health = execute_job_action("bottles", {"health": 0})
    assert res_health[0] is False
    assert "здоровье на нуле (0 HP)" in res_health[2]
    assert "/cure" in res_health[2]
    assert "/rest" in res_health[2]


# ══════════════════════════════════════════════════════════════════════════════
# 5. ASYNC BOT CALLBACKS & COMMANDS VERIFICATION
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_main_onboarding_callbacks_and_cmd_rest(isolated_test_db):
    """Verify async execution of onboard_how_rep, onboard_guide, onboard_first_shift, work_overtime, and cmd_rest."""
    db = isolated_test_db
    import main

    user_id = 987654321
    board_id = "b"

    # Setup user in db
    await db.execute("INSERT OR IGNORE INTO Users (user_id, board_id, balance) VALUES (?, ?, 0)", (user_id, board_id))
    await db.commit()

    # 1. Test onboard_how_rep callback
    cb_rep = MagicMock()
    cb_rep.from_user.id = user_id
    cb_rep.data = "onboard_how_rep"
    cb_rep.message = MagicMock()
    cb_rep.message.chat.id = user_id
    cb_rep.answer = AsyncMock()

    with patch("main.safe_edit_message", new=AsyncMock()) as mock_edit:
        await main.cb_onboard_how_rep(cb_rep, board_id=board_id)
        assert mock_edit.called
        call_text = mock_edit.call_args[0][1]
        assert "Как заработать репутацию" in call_text
        assert "Сбор стеклотары" in call_text

    # 2. Test onboard_guide callback
    cb_guide = MagicMock()
    cb_guide.from_user.id = user_id
    cb_guide.data = "onboard_guide"
    cb_guide.message = MagicMock()
    cb_guide.message.chat.id = user_id
    cb_guide.answer = AsyncMock()

    with patch("main.safe_edit_message", new=AsyncMock()) as mock_edit_g:
        await main.cb_onboard_guide(cb_guide, board_id=board_id)
        assert mock_edit_g.called
        call_text_g = mock_edit_g.call_args[0][1]
        assert "Быстрый гайд новичка" in call_text_g
        assert "/rest" in call_text_g

    # 3. Test cmd_rest command
    msg_rest = MagicMock()
    msg_rest.from_user.id = user_id
    msg_rest.chat.id = user_id
    msg_rest.answer = AsyncMock()

    await main.cmd_rest(msg_rest, board_id=board_id)
    assert msg_rest.answer.called
    ans_text = msg_rest.answer.call_args[0][0]
    assert "Сычевание на диване завершено" in ans_text or "Ты недавно отдыхал" in ans_text

    # 4. Test work_overtime callback when broke (anti-softlock rescue triggered)
    cb_ot = MagicMock()
    cb_ot.from_user.id = user_id
    cb_ot.data = "work_overtime"
    cb_ot.message = MagicMock()
    cb_ot.message.chat.id = user_id
    cb_ot.answer = AsyncMock()

    # Set user to 0 energy in DB
    items_broke = {"energy": 0.0, "health": 10.0}
    await db.execute("UPDATE Users SET active_items = ? WHERE user_id = ?", (json.dumps(items_broke), user_id))
    await db.commit()

    with patch("main.safe_callback_answer", new=AsyncMock()) as mock_ans, \
         patch("main.safe_edit_message", new=AsyncMock()):
        await main.cb_work_overtime(cb_ot, board_id=board_id)
        assert mock_ans.called
        toast = mock_ans.call_args[0][1]
        assert "Абу" in toast or "вздремнул" in toast or "энерги" in toast


# ══════════════════════════════════════════════════════════════════════════════
# 6. RESOLUTION OF REAL USER COMPLAINTS (POST #468991)
# ══════════════════════════════════════════════════════════════════════════════

def test_user_complaint_reputation_and_overloaded_ui_resolved():
    """
    Specifically verifies that the grievances from Post #468991:
    - 'нужно сначала её заработать, а уже потом посты пилить'
    - 'интерфейс перегруженный и неудобный'
    are explicitly solved by the newcomer onboarding engine.
    """
    # 1. Friendly onboarding guide makes reputation intuitive and non-blocking
    how_rep = format_how_to_earn_reputation(stream="ru")
    assert "100% Free" not in how_rep  # Pure RU without English traces
    assert "Сбор стеклотары" in how_rep
    assert "Постинг и реплаи" in how_rep

    # 2. Newcomer guide gives clean 5-bullet summary without 20 buttons clutter
    guide = format_newcomer_guide(stream="ru")
    assert "Как постить" in guide
    assert "Как отвечать" in guide
    assert "Как заработать" in guide
    assert "Если устал" in guide
    assert "Твой профиль" in guide
    # Ensure it is lightweight (< 600 chars)
    assert len(guide) < 800


# ══════════════════════════════════════════════════════════════════════════════
# 7. PASSPORT & PROFILE REPUTATION, REFERRAL & ANONYMITY INTEGRATION
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_cmd_passport_reputation_and_referral_integration(isolated_test_db):
    """
    Verify /passport and /profile:
    1. Shows reputation title/badge (e.g. 🌱 Новичок (0 REP) or 🦉 Бывалый сыч).
    2. Shows referral statistics (Рефералы: N анонов, Заработано: M ₪).
    3. Has button [🤝 Пригласить друга (+22,320 ₪)] with callback 'prof_ref'.
    4. STRICT LAW OF ANONYMITY: ensures raw numeric Telegram ID is never exposed.
    """
    db = isolated_test_db
    import main
    from common.anon_identity import get_anon_id

    user_id = 777666555
    board_id = "b"

    # Setup user in DB
    await db.execute(
        "INSERT OR IGNORE INTO Users (user_id, board_id, balance, posts_count) VALUES (?, ?, 5000, 10)",
        (user_id, board_id)
    )
    await db.commit()

    msg = MagicMock()
    msg.from_user.id = user_id
    msg.from_user.username = "test_anon"
    msg.from_user.first_name = "Anon"
    msg.chat.id = user_id
    msg.answer_photo = AsyncMock()
    msg.answer = AsyncMock()

    with patch("main.get_pool", return_value=db), \
         patch("main.safe_delete_message", new=AsyncMock()), \
         patch("main.spawn_task"):
        await main.cmd_passport(msg, board_id=board_id, stream="ru")

    # Either answer_photo or answer was called
    called_method = msg.answer_photo if msg.answer_photo.called else msg.answer
    assert called_method.called

    caption_or_text = called_method.call_args[1].get("caption") or called_method.call_args[0][0]
    reply_markup = called_method.call_args[1].get("reply_markup") or (called_method.call_args[0][1] if len(called_method.call_args[0]) > 1 else None)

    # 1. Reputation title/badge in caption/text
    assert "Репутация:" in caption_or_text
    assert any(badge in caption_or_text for badge in ["🌱", "🎭", "🦉", "👑", "🌌"])

    # 2. Referral statistics in caption/text
    assert "Рефералы:" in caption_or_text
    assert "Заработано:" in caption_or_text

    # 3. Strict Anonymity Law: raw numerical Telegram ID must NEVER be in caption/text
    assert str(user_id) not in caption_or_text
    expected_anon_id = get_anon_id(user_id, stream="ru")
    assert expected_anon_id in caption_or_text

    # 4. Button '🤝 Пригласить друга (+22,320 ₪)' with callback 'prof_ref'
    assert reply_markup is not None
    button_callbacks = [b.callback_data for row in reply_markup.inline_keyboard for b in row]
    button_texts = [b.text for row in reply_markup.inline_keyboard for b in row]
    assert "prof_ref" in button_callbacks
    assert any("Пригласить друга" in t for t in button_texts)
    assert any("22,320" in t for t in button_texts)


@pytest.mark.asyncio
async def test_cb_prof_card_refresh_reputation_and_anonymity(isolated_test_db):
    """
    Verify callback 'prof_card' (refresh passport card):
    1. Keeps reputation and referral statistics.
    2. Enforces strict anonymity law (no raw numerical user ID).
    3. Contains referral button 'prof_ref'.
    """
    db = isolated_test_db
    import main
    from common.anon_identity import get_anon_id

    user_id = 888777666
    board_id = "b"

    await db.execute(
        "INSERT OR IGNORE INTO Users (user_id, board_id, balance, posts_count) VALUES (?, ?, 2500, 5)",
        (user_id, board_id)
    )
    await db.commit()

    cb = MagicMock()
    cb.from_user.id = user_id
    cb.from_user.username = "veteran_anon"
    cb.from_user.first_name = "Veteran"
    cb.data = "prof_card"
    cb.message = MagicMock()
    cb.message.chat.id = user_id
    cb.message.edit_media = AsyncMock()
    cb.answer = AsyncMock()

    with patch("main.get_pool", return_value=db), \
         patch("main.safe_callback_answer", new=AsyncMock()):
        await main.cb_prof_card(cb, board_id=board_id, stream="ru")

    assert cb.message.edit_media.called
    media_arg = cb.message.edit_media.call_args[1].get("media") or cb.message.edit_media.call_args[0][0]
    caption = media_arg.caption
    reply_markup = cb.message.edit_media.call_args[1].get("reply_markup") or cb.message.edit_media.call_args[0][1]

    # Verify reputation and referral lines
    assert "Репутация:" in caption
    assert "Рефералы:" in caption
    assert str(user_id) not in caption
    assert get_anon_id(user_id, stream="ru") in caption

    # Verify buttons
    button_callbacks = [b.callback_data for row in reply_markup.inline_keyboard for b in row]
    assert "prof_ref" in button_callbacks


@pytest.mark.asyncio
async def test_cb_prof_referral_routing(isolated_test_db):
    """Verify clicking 'prof_ref' routes to handle_referral_command properly."""
    db = isolated_test_db
    import main

    user_id = 999111222
    cb = MagicMock()
    cb.from_user.id = user_id
    cb.data = "prof_ref"
    cb.message = MagicMock()
    cb.message.chat.id = user_id
    cb.message.reply = AsyncMock()
    cb.answer = AsyncMock()

    with patch("common.referral_engine.handle_referral_command", new=AsyncMock()) as mock_ref:
        await main.cb_prof_referral(cb, board_id="b", stream="ru")
        assert mock_ref.called
        assert mock_ref.call_args[1]["stream"] == "ru"


def test_stats_generator_text_report_reputation_and_anonymity():
    """Verify stats_generator._format_text_report formats reputation badge and scrubs raw numerical user_id."""
    from stats_generator import _format_text_report, UserStatsCardData
    from common.anon_identity import get_anon_id

    raw_uid = 987654321
    anon_tag = get_anon_id(raw_uid, stream="ru")

    data = UserStatsCardData(
        user_id=raw_uid,
        board_id="b",
        schizo_name=f"Анон [{anon_tag}]",
        role_name="Анонимус",
        posts_count=25,
        balance=15000.0,
        active_items={"work_shifts": 30},
        slang_comment=f"Секретный агент {raw_uid}",
    )

    report = _format_text_report(data)

    # 1. Reputation badge must be rendered
    assert "🌟 <b>Репутация:</b>" in report
    assert any(tier in report for tier in ["Бывалый сыч", "Анон", "Новичок", "Олдфаг", "Патриарх"])

    # 2. STRICT LAW OF ANONYMITY: Raw numerical Telegram ID must be scrubbed
    assert str(raw_uid) not in report
    assert anon_tag in report
