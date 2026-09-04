import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import aiosqlite
import shared_state
import wardrobe_engine
import achievements_engine


@pytest.mark.asyncio
async def test_wardrobe_collection_achievements():
    """Verify 5+, 15+, and 30+ items unlock respective wardrobe trophies."""
    items = {
        "unlocked_achievements": []
    }
    unlocked = wardrobe_engine.check_wardrobe_collection_achievements(items)
    assert len(unlocked) == 0

    # Add 5 items
    for i, item_id in enumerate(list(wardrobe_engine.CLOTHING_CATALOG.keys())[:5]):
        items[f"owned_{item_id}"] = True
        items[f"{item_id}_is_permanent"] = True

    unlocked = wardrobe_engine.check_wardrobe_collection_achievements(items)
    assert any(a["id"] == "ach_wardrobe_enthusiast" for a in unlocked)
    assert "ach_wardrobe_enthusiast" in items["unlocked_achievements"]

    # Add up to 15 items
    for i, item_id in enumerate(list(wardrobe_engine.CLOTHING_CATALOG.keys())[:15]):
        items[f"owned_{item_id}"] = True
        items[f"{item_id}_is_permanent"] = True

    unlocked = wardrobe_engine.check_wardrobe_collection_achievements(items)
    assert any(a["id"] == "ach_wardrobe_collector" for a in unlocked)
    assert "ach_wardrobe_collector" in items["unlocked_achievements"]

    # Add up to 30 items
    catalog_keys = list(wardrobe_engine.CLOTHING_CATALOG.keys())
    for item_id in catalog_keys:
        items[f"owned_{item_id}"] = True
        items[f"{item_id}_is_permanent"] = True
    for fake_idx in range(len(catalog_keys), 32):
        fake_id = f"fake_clothing_{fake_idx}"
        wardrobe_engine.CLOTHING_CATALOG[fake_id] = {"name": f"Fake {fake_idx}", "slot": "torso", "price": 100}
        items[f"owned_{fake_id}"] = True
        items[f"{fake_id}_is_permanent"] = True

    unlocked = wardrobe_engine.check_wardrobe_collection_achievements(items)
    assert any(a["id"] == "ach_fashion_demon" for a in unlocked)
    assert "ach_fashion_demon" in items["unlocked_achievements"]

    all_achs = achievements_engine.get_user_achievements(items)
    for target_id in ["ach_wardrobe_enthusiast", "ach_wardrobe_collector", "ach_fashion_demon"]:
        found = next((a for a in all_achs if a["id"] == target_id), None)
        assert found is not None
        assert found["is_unlocked"] is True


@pytest.mark.asyncio
async def test_multiboard_work_cooldown_sync():
    """Verify shared_state global work cooldowns sync across boards."""
    user_id = 888777
    shared_state._GLOBAL_WORK_COOLDOWNS.pop(user_id, None)

    import time
    now_ts = int(time.time())
    shared_state.set_user_work_cooldown(user_id, "courier", now_ts + 600)

    cds = shared_state.get_user_work_cooldowns(user_id)
    assert cds.get("courier") == now_ts + 600

    items = {"work_cooldowns": {"bottles": now_ts + 30}}
    for job, ts in cds.items():
        items["work_cooldowns"][job] = max(items["work_cooldowns"].get(job, 0), ts)

    assert items["work_cooldowns"]["courier"] == now_ts + 600
    assert items["work_cooldowns"]["bottles"] == now_ts + 30


@pytest.mark.asyncio
async def test_janitor_immunity_on_clean():
    """Verify janitor receives 15m grief protection upon cleaning posts."""
    janitor_id = 999888
    shared_state._TARGET_LAST_ATTACKED_TS.pop(janitor_id, None)

    assert shared_state.get_target_grief_protection_remaining(janitor_id) == 0

    shared_state.register_target_attack(janitor_id, duration_seconds=900)
    rem = shared_state.get_target_grief_protection_remaining(janitor_id)
    assert rem > 850


@pytest.mark.asyncio
async def test_set_neo_command_permission_and_grant():
    """Verify /set_neo grants permanent Neo set, activates set bonus and unlocks achievement."""
    import main
    dev_id = 7716348189
    target_id = 112233
    board_id = "b"

    async with aiosqlite.connect(":memory:") as db:
        await db.execute("""CREATE TABLE Users (
            user_id INTEGER,
            board_id TEXT,
            balance REAL DEFAULT 0,
            active_items TEXT DEFAULT '{}',
            PRIMARY KEY(user_id, board_id)
        )""")
        await db.commit()

        msg_unauth = MagicMock()
        msg_unauth.from_user = MagicMock(id=999999)
        msg_unauth.reply_to_message = None
        msg_unauth.answer = AsyncMock()

        with patch("main.is_admin", return_value=False):
            await main.cmd_set_neo(msg_unauth, board_id)
            assert msg_unauth.answer.called
            assert "Матрица отвергает тебя" in msg_unauth.answer.call_args[0][0]

        msg_auth = MagicMock()
        msg_auth.from_user = MagicMock(id=dev_id)
        msg_auth.reply_to_message = MagicMock()
        msg_auth.answer = AsyncMock()

        with patch("main.get_pool", return_value=db):
            with patch("main.get_author_id_by_reply", return_value=target_id):
                with patch("main._get_user_active_items", return_value={}):
                    await main.cmd_set_neo(msg_auth, board_id)
                    assert msg_auth.answer.called
                    ans_text = msg_auth.answer.call_args[0][0]
                    assert "СЕТ «ИЗБРАННЫЙ / НЕО» УСПЕШНО АКТИВИРОВАН" in ans_text

        async with db.execute("SELECT active_items FROM Users WHERE user_id=? AND board_id=?", (target_id, board_id)) as c:
            row = await c.fetchone()
            assert row is not None
            saved_items = json.loads(row[0])
            assert saved_items.get("equipped_torso") == "body_cloak"
            assert saved_items.get("equipped_face") == "face_anon_mask"
            assert saved_items.get("body_cloak_is_permanent") is True
            assert saved_items.get("face_anon_mask_is_permanent") is True
            assert "ach_set_neo" in saved_items.get("unlocked_achievements", [])