import asyncio
import time
import random
import json
import logging
from aiogram import Bot, types
from shared_state import *
from shared_state import NewPostParams
from common.config import *
from common.database import *
from common.anon_identity import get_anon_id, generate_anon_name
from post_processor import NewPostContext, NewPostProcessor, process_new_post
from typing import Optional

def is_admin(uid: int, board_id: Optional[str] = None) -> bool:
    if not uid:
        return False
    try:
        from site_tgach.admin_config import ADMIN_IDS
        if uid in ADMIN_IDS:
            return True
    except Exception:
        pass
    try:
        from common.config import ADMIN_IDS
        if uid in ADMIN_IDS:
            return True
    except Exception:
        pass
    if not board_id:
        return False
    from common.board_config import BOARD_CONFIG
    bconf = BOARD_CONFIG.get(board_id, {})
    admins = bconf.get('admins', [])
    return uid in admins

async def _get_user_active_items(db, user_id: int, board_id: str) -> dict:
    from common.db_pool import db_lock
    try:
        async with asyncio.timeout(2.0):
            if getattr(db_lock, "is_owned_by_current_task", lambda: False)():
                async with db.execute("SELECT active_items FROM Users WHERE user_id = ? AND board_id = ?", (user_id, board_id)) as c:
                    row = await c.fetchone()
                    active_items_str = row[0] if row and row[0] else "{}"
                return json.loads(active_items_str)
            else:
                async with db_lock:
                    async with db.execute("SELECT active_items FROM Users WHERE user_id = ? AND board_id = ?", (user_id, board_id)) as c:
                        row = await c.fetchone()
                        active_items_str = row[0] if row and row[0] else "{}"
                    return json.loads(active_items_str)
    except Exception:
        return {}

async def accept_duel_logic(message: types.Message, challenger_id: int, board_id: str, user_id: int | None = None):
    import time
    db = await get_pool()
    if user_id is None:
        user_id = message.from_user.id
    
    if challenger_id == user_id:
        await message.answer("Нельзя принять собственный вызов, трус.")
        return

    async with db_lock:
        # Проверяем глобальные балансы обоих под локом
        ch_bal = await get_user_global_balance(db, challenger_id)
        op_bal = await get_user_global_balance(db, user_id)

        reject_msg = None
        if challenger_id not in _active_duels:
            reject_msg = "⚔️ Эта дуэль уже была принята или истекла."
        else:
            duel = _active_duels.pop(challenger_id)
            amount = duel["amount"]
            if ch_bal < amount:
                reject_msg = f"⚔️ Вызывающий Анон [{get_anon_id(challenger_id)}] уже не потянет ставку — слился."
            elif op_bal < amount:
                # Возвращаем дуэль обратно в пул
                _active_duels[challenger_id] = duel
                reject_msg = f"❌ У тебя недостаточно шекелей. Нужно {amount:,} ₪, у тебя {int(op_bal):,} ₪."
            else:
                winner_id = random.choice([challenger_id, user_id])
                loser_id  = challenger_id if winner_id == user_id else user_id
                
                # 5% Rake to Abu's Fund and payout to winner
                rake = max(1, int(amount * 0.05))
                net_win = amount - rake

                # Атомарное списание у проигравшего и начисление победителю
                ok, _ = await deduct_user_global_balance(db, loser_id, board_id, amount)
                if ok:
                    await add_user_global_balance(db, winner_id, board_id, net_win)
                    await add_to_abu_fund(db, rake)
                    await record_user_transaction(db, winner_id, net_win, 'duel', f'Победа в дуэли против [{get_anon_id(loser_id)}]')
                    await record_user_transaction(db, loser_id, -amount, 'duel', f'Поражение в дуэли против [{get_anon_id(winner_id)}]')
                    
                    w_items = await _get_user_active_items(db, winner_id, board_id)
                    from achievements_engine import check_and_unlock_achievement
                    unlocked, ach_info = check_and_unlock_achievement(w_items, "ach_duel_win")
                    if unlocked and ach_info:
                        await add_user_global_balance(db, winner_id, board_id, ach_info["reward_cash"])
                        await record_user_transaction(db, winner_id, ach_info["reward_cash"], 'drop', f'Достижение: {ach_info["name"]}')
                        await db.execute("UPDATE Users SET active_items = ? WHERE user_id = ? AND board_id = ?",
                                         (json.dumps(w_items), winner_id, board_id))
                    await db.commit()
                else:
                    reject_msg = "❌ У одного из участников изменился баланс во время принятия дуэли."

    if reject_msg is not None:
        await message.answer(reject_msg)
        return

    w_tag = f"Анон [{get_anon_id(winner_id)}]"
    l_tag = f"Анон [{get_anon_id(loser_id)}]"
    you_w = " (ты)" if winner_id == user_id else ""
    you_l = " (ты)" if loser_id  == user_id else ""
    duel_text = (
        f"⚔️ <b>ДУЭЛЬ ЗАВЕРШЕНА!</b>\n\n"
        f"🎲 Монета решила исход битвы:\n"
        f"🏆 Победитель: <b>{w_tag}</b>{you_w} <code>+{net_win:,} ₪</code>\n"
        f"💀 Проигравший: <b>{l_tag}</b>{you_l} <code>-{amount:,} ₪</code>"
    )
    try:
        from combat_visuals import draw_duel_poster
        from aiogram.types import BufferedInputFile
        pfx_w = None
        pfx_l = None
        try:
            async with db.execute("SELECT custom_prefix FROM Users WHERE user_id=? AND board_id=?", (winner_id, board_id)) as c:
                r = await c.fetchone()
                pfx_w = r[0] if r else None
            async with db.execute("SELECT custom_prefix FROM Users WHERE user_id=? AND board_id=?", (loser_id, board_id)) as c:
                r = await c.fetchone()
                pfx_l = r[0] if r else None
        except Exception:
            pass

        buf = draw_duel_poster(winner_id, loser_id, amount, board_id, pfx_w, pfx_l)
        photo_file = BufferedInputFile(buf.getvalue(), filename="duel_poster.png")
        await message.answer_photo(photo=photo_file, caption=duel_text, parse_mode="HTML")
    except Exception:
        await message.answer(duel_text, parse_mode="HTML")

async def decline_duel_logic(message: types.Message, challenger_id: int, user_id: int | None = None):
    if user_id is None:
        user_id = message.from_user.id
    if challenger_id not in _active_duels:
        return False
        
    duel = _active_duels.get(challenger_id, {})
    target_id = duel.get("target_id")
    if target_id and user_id != target_id and user_id != challenger_id:
        return False

    _active_duels.pop(challenger_id, None)
    if user_id == challenger_id:
        await message.answer("⚔️ Вызов на дуэль успешно отменен создателем.")
        return True
    else:
        await message.answer(f"⚔️ Вызов на дуэль отклонен Анон [{get_anon_id(user_id)}].")
        return True



async def delete_message_after_delay(message: types.Message, delay: int):

    try:
        await asyncio.sleep(delay)
        await asyncio.wait_for(message.delete(), timeout=15.0)
    except asyncio.CancelledError:
        import traceback; traceback.print_exc()
    except asyncio.TimeoutError:
        print(f"⚠️ Таймаут при удалении сообщения {message.message_id} в чате {message.chat.id}")
    except Exception as e:
        if "message to delete not found" not in str(e).lower():
            print(f"🔥 Непредвиденная ошибка в delete_message_after_delay: {type(e).__name__}: {e}")