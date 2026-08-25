# -*- coding: utf-8 -*-
import pytest
from common.work_engine import WORK_VACANCIES, execute_job_action


def test_work_vacancies_structure():
    assert len(WORK_VACANCIES) == 16, f"Expected 16 vacancies, found {len(WORK_VACANCIES)}"
    
    expected_keys = [
        "bottles", "sweeper", "courier", "captcha", "spy", "factory",
        "it_freelance", "scam", "deputy", "escort_sugar", "crypto_cartel",
        "infogypsy_cult", "propaganda_troll", "abu_consigliere",
        "shadow_oligarch", "matrix_architect"
    ]
    for k in expected_keys:
        assert k in WORK_VACANCIES, f"Missing job key: {k}"
        job = WORK_VACANCIES[k]
        assert "title" in job
        assert "reward_range" in job and len(job["reward_range"]) == 2
        assert job["reward_range"][0] > 0 and job["reward_range"][1] >= job["reward_range"][0]
        assert "required_shifts" in job and job["required_shifts"] >= 0
        assert "cooldown_sec" in job and job["cooldown_sec"] > 0
        assert "risk_pct" in job and 0.0 <= job["risk_pct"] <= 1.0
        assert "phrases" in job and len(job["phrases"]) > 0


def test_execute_all_jobs():
    items = {
        "work_shifts": 1000,
        "work_cooldowns": {},
        "equipped_torso": "body_wasserman",
        "equipped_head": "hat_crown",
        "equipped_face": "face_thug_glasses"
    }

    for job_id in WORK_VACANCIES:
        items["work_cooldowns"] = {}
        is_succ, change, msg, drop = execute_job_action(job_id, items)
        assert isinstance(is_succ, bool)
        assert isinstance(change, int) and change >= 0
        assert isinstance(msg, str) and len(msg) > 0


def test_locked_job_requirements():
    items = {
        "work_shifts": 10,
        "work_cooldowns": {}
    }
    is_succ, change, msg, drop = execute_job_action("matrix_architect", items)
    assert not is_succ
    assert change == 0
    assert "заблокирована" in msg.lower()
