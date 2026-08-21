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

async def _get_user_active_items(db, user_id: int, board_id: str) -> dict:
    try:
        async with asyncio.timeout(2.0):
            async with db.execute("SELECT active_items FROM Users WHERE user_id = ? AND board_id = ?", (user_id, board_id)) as c:
                row = await c.fetchone()
                active_items_str = row[0] if row and row[0] else "{}"
            return json.loads(active_items_str)
    except Exception:
        return {}

async def accept_duel_logic(message: types.Message, challenger_id: int, board_id: str):
    import time
    db = await get_pool()
    user_id = message.from_user.id
    time.time()
    
    if challenger_id == user_id:
        await message.answer("Нельзя принять собственный вызов, трус.")
        return

    async with db_lock:
        # Проверяем глобальные балансы обоих под локом
        ch_bal = await get_user_global_balance(db, challenger_id)
        op_bal = await get_user_global_balance(db, user_id)

        # Ответ юзеру откладываем до выхода из лока: db_lock сериализует ВЕСЬ
        # доступ к базе в процессе, и держать его на время сетевого вызова
        # Telegram — значит остановить создание постов и любые запросы во всём
        # боте. Решение (проверка балансов, изъятие дуэли из пула и перевод)
        # целиком остаётся под локом, иначе одну дуэль приняли бы дважды.
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
                reject_msg = f"❌ У тебя недостаточно бабок. Нужно {amount} RUB, есть {int(op_bal)}."
            else:
                winner_id = random.choice([challenger_id, user_id])
                loser_id  = challenger_id if winner_id == user_id else user_id
                
                # Атомарное списание у проигравшего и начисление победителю
                ok, _ = await deduct_user_global_balance(db, loser_id, board_id, amount)
                if ok:
                    await add_user_global_balance(db, winner_id, board_id, amount)
                    w_items = await _get_user_active_items(db, winner_id, board_id)
                    from achievements_engine import check_and_unlock_achievement
                    unlocked, ach_info = check_and_unlock_achievement(w_items, "ach_duel_win")
                    if unlocked and ach_info:
                        await add_user_global_balance(db, winner_id, board_id, ach_info["reward_cash"])
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
        f"🏆 Победитель: <b>{w_tag}</b>{you_w} <code>+{amount:,} ₪</code>\n"
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

async def decline_duel_logic(message: types.Message, challenger_id: int):
    user_id = message.from_user.id
    if challenger_id not in _active_duels:
        return False
        
    # Отклонить дуэль может либо создатель (отмена), либо любой другой пользователь (отклонение)
    if user_id == challenger_id:
        _active_duels.pop(challenger_id, None)
        await message.answer("⚔️ Вызов на дуэль успешно отменен создателем.")
        return True
    else:
        _active_duels.pop(challenger_id, None)
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