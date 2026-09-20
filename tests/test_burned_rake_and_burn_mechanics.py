# -*- coding: utf-8 -*-
"""
tests/test_burned_rake_and_burn_mechanics.py
Unit and E2E test suite for deflationary burned rake (10% on bets > 50,000 ₪)
and Flash Ultra daily usage nerf (max 2/day).
"""

import pytest
import time
from datetime import datetime, timezone
import casino_engine
from economy_extension import check_flash_ultra_limit, record_flash_ultra_use


def test_calculate_vip_table_rake():
    # Low bets: no rake
    rake, active_bet = casino_engine.calculate_vip_table_rake(500)
    assert rake == 0
    assert active_bet == 500
    assert casino_engine.is_burn_vip_rake(500) is False

    # Standard VIP table (>= 2000 and <= 50000): 2% to Abu's Fund
    rake, active_bet = casino_engine.calculate_vip_table_rake(2000)
    assert rake == 40
    assert active_bet == 1960
    assert casino_engine.is_burn_vip_rake(2000) is False

    rake, active_bet = casino_engine.calculate_vip_table_rake(50000)
    assert rake == 1000
    assert active_bet == 49000
    assert casino_engine.is_burn_vip_rake(50000) is False

    # High Roller (> 50000): 10% Burned Rake (Deflationary sink)
    rake, active_bet = casino_engine.calculate_vip_table_rake(60000)
    assert rake == 6000  # 10%
    assert active_bet == 54000
    assert casino_engine.is_burn_vip_rake(60000) is True

    rake, active_bet = casino_engine.calculate_vip_table_rake(100000)
    assert rake == 10000  # 10%
    assert active_bet == 90000
    assert casino_engine.is_burn_vip_rake(100000) is True


def test_flash_ultra_daily_limit_nerf():
    user_items = {}
    now = time.time()
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # 1st use: OK
    can_use, err = check_flash_ultra_limit(user_items, now=now)
    assert can_use is True
    assert err == ""
    rem1 = record_flash_ultra_use(user_items, now=now)
    assert rem1 == 1
    assert user_items["overtime_uses_today"] == 1
    assert user_items["overtime_day"] == today_str

    # Attempt immediate 2nd use (< 30 min cooldown): Blocked by min_cd
    can_use_soon, err_soon = check_flash_ultra_limit(user_items, now=now + 600)  # 10 min later
    assert can_use_soon is False
    assert "Пульс зашкаливает" in err_soon

    # 2nd use after 31 minutes: OK
    now2 = now + 1860
    can_use2, err2 = check_flash_ultra_limit(user_items, now=now2)
    assert can_use2 is True
    assert err2 == ""
    rem2 = record_flash_ultra_use(user_items, now=now2)
    assert rem2 == 0
    assert user_items["overtime_uses_today"] == 2

    # 3rd use on same day: BLOCKED by daily limit!
    now3 = now2 + 3600
    can_use3, err3 = check_flash_ultra_limit(user_items, now=now3)
    assert can_use3 is False
    assert "Лимит Flash Ultra исчерпан" in err3
    assert user_items["overtime_uses_today"] == 2
