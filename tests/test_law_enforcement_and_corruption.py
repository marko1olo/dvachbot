import pytest
import time
import json
from unittest.mock import AsyncMock, MagicMock, patch
import main
from main import (
    BASE_SHOP_PRICES,
    _build_pharma_shop_content,
    cb_shop_buy,
    _process_loli_reward_and_risk,
    cb_loli_explain,
    cmd_dopros,
    cb_dopros_action,
    cmd_fine,
    LOLI_BUST_STATE,
    USER_LOLI_REWARD_COOLDOWN,
    USER_DOPROS_COOLDOWN,
    ACTIVE_DOPROS,
    USER_DRUZHINA_COOLDOWN
)

@pytest.mark.asyncio
async def test_shop_items_registered():
    assert "ksiva_polkovnik" in BASE_SHOP_PRICES
    assert BASE_SHOP_PRICES["ksiva_polkovnik"] == 650
    assert "badge_druzhinnik" in BASE_SHOP_PRICES
    assert BASE_SHOP_PRICES["badge_druzhinnik"] == 400

    text, kb = _build_pharma_shop_content(user_id=123, balance=1000.0)
    assert "Ксива полковника" in text
    assert "Удостоверение дружинника" in text
    callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert "shop_buy_ksiva_polkovnik" in callbacks
    assert "shop_buy_badge_druzhinnik" in callbacks

@pytest.mark.asyncio
async def test_shop_buy_ksiva_and_druzhinnik():
    user_id = 999111
    board_id = "b"
    mock_db = MagicMock()
    mock_db.execute = AsyncMock()

    # 1. Buy ksiva
    callback_ksiva = MagicMock()
    callback_ksiva.data = "shop_buy_ksiva_polkovnik"
    callback_ksiva.from_user.id = user_id
    callback_ksiva.answer = AsyncMock()
    callback_ksiva.message.edit_text = AsyncMock()

    with patch("main.get_pool", AsyncMock(return_value=mock_db)),          patch("main.get_user_global_balance", AsyncMock(return_value=2000.0)),          patch("main.deduct_user_global_balance", AsyncMock(return_value=(True, 1350.0))),          patch("main._get_user_active_items", AsyncMock(return_value={})),          patch("main.record_user_transaction", AsyncMock()),          patch("shared_state.record_shop_purchase", MagicMock()),          patch("main._render_shop_subview", AsyncMock()):

        await cb_shop_buy(callback_ksiva, board_id)
        callback_ksiva.answer.assert_called()
        ans_args = callback_ksiva.answer.call_args[0][0]
        assert "Ксиву полковника юстиции" in ans_args

    # 2. Buy druzhinnik badge
    callback_druzh = MagicMock()
    callback_druzh.data = "shop_buy_badge_druzhinnik"
    callback_druzh.from_user.id = user_id
    callback_druzh.answer = AsyncMock()
    callback_druzh.message.edit_text = AsyncMock()

    with patch("main.get_pool", AsyncMock(return_value=mock_db)),          patch("main.get_user_global_balance", AsyncMock(return_value=2000.0)),          patch("main.deduct_user_global_balance", AsyncMock(return_value=(True, 1600.0))),          patch("main._get_user_active_items", AsyncMock(return_value={})),          patch("main.record_user_transaction", AsyncMock()),          patch("shared_state.record_shop_purchase", MagicMock()),          patch("main._render_shop_subview", AsyncMock()):

        await cb_shop_buy(callback_druzh, board_id)
        callback_druzh.answer.assert_called()
        ans_args = callback_druzh.answer.call_args[0][0]
        assert "Удостоверение дружинника" in ans_args

@pytest.mark.asyncio
async def test_loli_ksiva_rescues_from_bust():
    user_id = 777123
    board_id = "b"
    USER_LOLI_REWARD_COOLDOWN.clear()

    msg = MagicMock()
    msg.chat.id = user_id
    msg.answer = AsyncMock()

    mock_db = MagicMock()
    mock_db.execute = AsyncMock()
    active_items = {"ksiva_polkovnik": 1}

    with patch("main.get_pool", AsyncMock(return_value=mock_db)),          patch("main._get_user_active_items", AsyncMock(return_value=active_items)),          patch("main.add_user_global_balance", AsyncMock(return_value=1250.0)),          patch("main.record_user_transaction", AsyncMock()),          patch("random.random", return_value=0.01):  # Guarantees bust

        await _process_loli_reward_and_risk(msg, board_id, user_id, 10)

        # Ksiva was consumed
        assert active_items["ksiva_polkovnik"] == 0
        msg.answer.assert_called_once()
        sent_html = msg.answer.call_args[0][0]
        assert "Ксиву полковника юстиции" in sent_html
        assert "Товарищ майор нагрянул с облавой" in sent_html

@pytest.mark.asyncio
async def test_loli_explanation_mercy_and_fine():
    user_id = 888222
    board_id = "b"
    bust_id = f"{user_id}_12345"
    LOLI_BUST_STATE[bust_id] = {
        "user_id": user_id,
        "board_id": board_id,
        "count": 10,
        "fine": 200.0,
        "actual_fine": 200.0,
        "created_at": time.time(),
    }

    mock_db = MagicMock()
    mock_db.execute = AsyncMock()
    callback = MagicMock()
    callback.data = f"loli_explain:{bust_id}"
    callback.from_user.id = user_id
    callback.answer = AsyncMock()
    callback.message.edit_text = AsyncMock()

    # Case 1: 25% mercy
    with patch("main.get_pool", AsyncMock(return_value=mock_db)),          patch("random.random", return_value=0.10),          patch("main.add_user_global_balance", AsyncMock(return_value=600.0)),          patch("main.deduct_from_abu_fund", AsyncMock()),          patch("main.record_user_transaction", AsyncMock()):

        await cb_loli_explain(callback, board_id)
        callback.message.edit_text.assert_called_once()
        text = callback.message.edit_text.call_args[0][0]
        assert "ОБЪЯСНИТЕЛЬНАЯ ПРИНЯТА К СВЕДЕНИЮ" in text
        assert "+100 ₪" in text  # 50% of 200 fine refunded

    # Case 2: 75% denial (second bust)
    bust_id_2 = f"{user_id}_67890"
    LOLI_BUST_STATE[bust_id_2] = {
        "user_id": user_id,
        "board_id": board_id,
        "count": 10,
        "fine": 200.0,
        "actual_fine": 200.0,
        "created_at": time.time(),
    }
    callback_2 = MagicMock()
    callback_2.data = f"loli_explain:{bust_id_2}"
    callback_2.from_user.id = user_id
    callback_2.answer = AsyncMock()
    callback_2.message.edit_text = AsyncMock()

    with patch("main.get_pool", AsyncMock(return_value=mock_db)),          patch("random.random", return_value=0.90),          patch("main.get_user_global_balance", AsyncMock(return_value=500.0)),          patch("main.deduct_user_global_balance", AsyncMock(return_value=(True, 480.0))),          patch("main.add_to_abu_fund", AsyncMock()),          patch("main.record_user_transaction", AsyncMock()):

        await cb_loli_explain(callback_2, board_id)
        callback_2.message.edit_text.assert_called_once()
        text = callback_2.message.edit_text.call_args[0][0]
        assert "ОБЪЯСНИТЕЛЬНАЯ ОТКЛОНЕНА" in text
        assert "Ты кого наебать пытаешься, сыч?!" in text
        assert "-20 ₪" in text

@pytest.mark.asyncio
async def test_cmd_dopros_and_admin_immunity():
    user_id = 333444
    board_id = "b"
    USER_DOPROS_COOLDOWN.clear()
    ACTIVE_DOPROS.clear()

    mock_db = MagicMock()
    mock_db.execute = AsyncMock()

    # Admin target -> rejected
    msg_admin = MagicMock()
    msg_admin.from_user.id = user_id
    msg_admin.reply_to_message = MagicMock()
    msg_admin.reply_to_message.from_user.id = 999999
    msg_admin.reply_to_message.from_user.first_name = "SuperAdmin"
    msg_admin.answer = AsyncMock()

    with patch("main.get_pool", AsyncMock(return_value=mock_db)),          patch("main.is_admin", return_value=True):
        await cmd_dopros(msg_admin, board_id)
        msg_admin.answer.assert_called_once()
        assert "ОТМЕНА ОПЕРАЦИИ!" in msg_admin.answer.call_args[0][0]

    # Non-admin target -> summons protocol
    USER_DOPROS_COOLDOWN.clear()
    msg_target = MagicMock()
    msg_target.from_user.id = user_id
    msg_target.reply_to_message = MagicMock()
    msg_target.reply_to_message.from_user.id = 555666
    msg_target.reply_to_message.from_user.first_name = "SuspectAnon"
    msg_target.answer = AsyncMock()

    with patch("main.get_pool", AsyncMock(return_value=mock_db)),          patch("main.is_admin", return_value=False):
        await cmd_dopros(msg_target, board_id)
        msg_target.answer.assert_called_once()
        sent_html = msg_target.answer.call_args[0][0]
        assert "ПОВЕСТКА НА ДОПРОС В ОТДЕЛ «К»" in sent_html
        assert len(ACTIVE_DOPROS) == 1

        dopros_id = list(ACTIVE_DOPROS.keys())[0]

        # Test bribe callback
        cb_bribe = MagicMock()
        cb_bribe.data = f"dopros_bribe:{dopros_id}"
        cb_bribe.from_user.id = 555666
        cb_bribe.answer = AsyncMock()
        cb_bribe.message.edit_text = AsyncMock()

        with patch("main.get_user_global_balance", AsyncMock(return_value=100.0)),              patch("main.deduct_user_global_balance", AsyncMock(return_value=(True, 50.0))),              patch("main.add_to_abu_fund", AsyncMock()),              patch("main.record_user_transaction", AsyncMock()):
            await cb_dopros_action(cb_bribe, board_id)
            cb_bribe.message.edit_text.assert_called_once()
            assert "ДЕЛО ЗАКРЫТО!" in cb_bribe.message.edit_text.call_args[0][0]

@pytest.mark.asyncio
async def test_cmd_fine_mechanics():
    druzh_id = 111222
    target_id = 333555
    board_id = "b"
    USER_DRUZHINA_COOLDOWN.clear()
    mock_db = MagicMock()
    mock_db.execute = AsyncMock()

    msg = MagicMock()
    msg.from_user.id = druzh_id
    msg.reply_to_message = MagicMock()
    msg.reply_to_message.from_user.id = target_id
    msg.reply_to_message.from_user.first_name = "RuleBreaker"
    msg.answer = AsyncMock()

    # 1. No badge -> error
    with patch("main.get_pool", AsyncMock(return_value=mock_db)),          patch("main._get_user_active_items", AsyncMock(return_value={})):
        await cmd_fine(msg, board_id)
        msg.answer.assert_called_once()
        assert "Удостоверения дружинника" in msg.answer.call_args[0][0]

    # 2. Has badge, targets admin -> druzhinnik gets fined!
    USER_DRUZHINA_COOLDOWN.clear()
    msg.answer.reset_mock()
    with patch("main.get_pool", AsyncMock(return_value=mock_db)),          patch("main._get_user_active_items", AsyncMock(return_value={"badge_druzhinnik_expires": time.time() + 86400})),          patch("main.is_admin", return_value=True),          patch("main.get_user_global_balance", AsyncMock(return_value=50.0)),          patch("main.deduct_user_global_balance", AsyncMock(return_value=(True, 20.0))),          patch("main.add_to_abu_fund", AsyncMock()),          patch("main.record_user_transaction", AsyncMock()):
        await cmd_fine(msg, board_id)
        msg.answer.assert_called_once()
        assert "ПРЕВЫШЕНИЕ СЛУЖЕБНЫХ ПОЛНОМОЧИЙ!" in msg.answer.call_args[0][0]

    # 3. Successful fine against normal target
    USER_DRUZHINA_COOLDOWN.clear()
    msg.answer.reset_mock()
    with patch("main.get_pool", AsyncMock(return_value=mock_db)),          patch("main._get_user_active_items", AsyncMock(side_effect=[
             {"badge_druzhinnik_expires": time.time() + 86400}, # druzhinnik
             {} # target has no shield
         ])),          patch("main.is_admin", return_value=False),          patch("main.get_user_global_balance", AsyncMock(return_value=100.0)),          patch("main.deduct_user_global_balance", AsyncMock(return_value=(True, 85.0))),          patch("main.add_user_global_balance", AsyncMock(return_value=110.0)),          patch("main.add_to_abu_fund", AsyncMock()),          patch("main.record_user_transaction", AsyncMock()):
        await cmd_fine(msg, board_id)
        msg.answer.assert_called_once()
        sent_html = msg.answer.call_args[0][0]
        assert "ШТРАФ ОТ НАРОДНОЙ ДРУЖИНЫ!" in sent_html
        assert "-15 ₪" in sent_html
        assert "+10 ₪" in sent_html
