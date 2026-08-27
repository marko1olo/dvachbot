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
from typing import Optional

def is_ai_slop_content(content: dict | None = None, text: str | None = None) -> bool:
    """
    Determines if a post/message is AI-generated (voice/music roast, AI persona reply, slop).
    """
    if not content and not text:
        return False
    if content and isinstance(content, dict):
        if (
            content.get('is_ai_roast')
            or content.get('is_ai_persona')
            or content.get('is_ai')
            or content.get('is_slop')
            or content.get('is_ai_slop')
            or content.get('is_neuro_slop')
            or content.get('is_ai_reply')
        ):
            return True

    full_text = ""
    if content and isinstance(content, dict):
        full_text = str(content.get('text') or content.get('caption') or '')
    if text:
        full_text += " " + str(text)

    full_text_lower = full_text.lower()
    if "вердикт /b/ ai" in full_text_lower:
        return True
    if "вердикт /b/ музкритика" in full_text_lower:
        return True
    if "шкала говноедства" in full_text_lower:
        return True
    if "разъёб от киберчеда" in full_text_lower or "разъеб от киберчеда" in full_text_lower:
        return True
    if "шизо-таблетка" in full_text_lower or "[ai-анон]" in full_text_lower or "киберчед" in full_text_lower:
        return True
    return False

from post_processor import NewPostContext, NewPostProcessor, process_new_post

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

def merge_user_active_items_rows(rows: list, board_id: str | None = None) -> dict:
    """
    Consistently aggregates and synchronizes user assets across all boards so that
    a user never loses shifts, items, achievements, equipment, weapons, buffs, or cooldowns.
    """
    if not rows:
        return {}

    current_items = {}
    max_shifts = 0
    all_achievements = set()
    work_cooldowns = {}
    daily_streak = 0
    daily_last_claim = 0
    last_bottles = 0
    mother_sold = False
    janitor_deletes_left = 0
    janitor_until = 0
    badge_color = None
    badge_color_active = False
    badge_color_expires = 0

    equipped_gear = {}
    guns = {}
    durations = {}
    wardrobe_items = {}
    all_other = {}

    KNOWN_GUNS = (
        "mute_gun", "knife_gun", "pepperspray_gun", "partyvan_gun",
        "shit_gun", "vomit_gun", "laxative_gun", "schizopill_gun",
        "megaphone_gun", "flag_ru_gun", "flag_ua_gun", "pills_gun"
    )

    KNOWN_DURATIONS = (
        "reflect_shield_until", "shield_until", "shield_active",
        "tinfoil_hat", "tinfoil_until", "peppersprayed_until",
        "schizo_pill_until", "schizopill_active", "shit_until",
        "shit_covered_until", "vomit_until", "flag_ru_until",
        "flag_ua_until", "cursed_until"
    )

    for b_id, a_str in rows:
        if not a_str:
            continue
        try:
            data = json.loads(a_str) if isinstance(a_str, str) else (a_str if isinstance(a_str, dict) else {})
        except Exception:
            continue
        if not isinstance(data, dict):
            continue

        if board_id and b_id == board_id:
            current_items = dict(data)

        # 1. Shifts
        s = data.get("work_shifts", 0)
        if isinstance(s, (int, float)) and s > max_shifts:
            max_shifts = int(s)

        # 2. Achievements
        for ach in data.get("unlocked_achievements", []):
            if isinstance(ach, str) and ach:
                all_achievements.add(ach)

        # 3. Work Cooldowns
        for job_id, cd_ts in data.get("work_cooldowns", {}).items():
            if isinstance(cd_ts, (int, float)):
                work_cooldowns[job_id] = max(work_cooldowns.get(job_id, 0), int(cd_ts))

        # 4. Daily
        dlc = data.get("daily_last_claim", 0)
        if isinstance(dlc, (int, float)) and dlc > daily_last_claim:
            daily_last_claim = int(dlc)
        ds = data.get("daily_streak", 0)
        if isinstance(ds, (int, float)) and ds > daily_streak:
            daily_streak = int(ds)

        # 5. Economy work
        lb = data.get("last_bottles", 0)
        if isinstance(lb, (int, float)) and lb > last_bottles:
            last_bottles = int(lb)
        if data.get("mother_sold"):
            mother_sold = True

        # 6. Janitor
        ju = data.get("janitor_until", 0)
        if isinstance(ju, (int, float)) and ju > janitor_until:
            janitor_until = int(ju)
        jdl = data.get("janitor_deletes_left", 0)
        if isinstance(jdl, (int, float)) and jdl > janitor_deletes_left:
            janitor_deletes_left = int(jdl)

        # 7. Badge color
        bce = data.get("badge_color_expires", 0)
        if isinstance(bce, (int, float)) and bce > badge_color_expires:
            badge_color_expires = int(bce)
        if data.get("badge_color_active"):
            badge_color_active = True
        if data.get("badge_color"):
            badge_color = data.get("badge_color")

        # 8. Guns
        for g_key in KNOWN_GUNS:
            if data.get(g_key):
                guns[g_key] = True

        # 9. Durations / status effects
        for d_key in KNOWN_DURATIONS:
            val = data.get(d_key)
            if isinstance(val, (int, float)):
                durations[d_key] = max(durations.get(d_key, 0), int(val))
            elif isinstance(val, bool) and val:
                durations[d_key] = True

        # 10. Wardrobe items & equipped gear
        for k, v in data.items():
            if k.startswith("owned_") and v:
                wardrobe_items[k] = True
            elif k.endswith("_is_permanent") and v:
                wardrobe_items[k] = True
            elif k.endswith("_expires") and isinstance(v, (int, float)):
                wardrobe_items[k] = max(wardrobe_items.get(k, 0), int(v))
            elif k.startswith("equipped_") and v:
                if (board_id and b_id == board_id) or k not in equipped_gear:
                    equipped_gear[k] = v
            elif k not in all_other:
                all_other[k] = v

    result = dict(all_other)
    result.update(current_items)
    result.update(wardrobe_items)
    result.update(guns)
    result.update(durations)
    for slot_k, eq_v in equipped_gear.items():
        if eq_v:
            result[slot_k] = eq_v

    if max_shifts > 0:
        result["work_shifts"] = max_shifts
    if all_achievements:
        result["unlocked_achievements"] = sorted(list(all_achievements))
    if work_cooldowns:
        result["work_cooldowns"] = work_cooldowns
    if daily_streak > 0:
        result["daily_streak"] = daily_streak
    if daily_last_claim > 0:
        result["daily_last_claim"] = daily_last_claim
    if last_bottles > 0:
        result["last_bottles"] = last_bottles
    if mother_sold:
        result["mother_sold"] = True
    if janitor_until > 0:
        result["janitor_until"] = janitor_until
    if janitor_deletes_left > 0:
        result["janitor_deletes_left"] = janitor_deletes_left
    if badge_color:
        result["badge_color"] = badge_color
    if badge_color_active:
        result["badge_color_active"] = True
    if badge_color_expires > 0:
        result["badge_color_expires"] = badge_color_expires

    return result


async def _get_user_active_items(db, user_id: int, board_id: str | None = None) -> dict:
    """
    Asynchronously loads and merges user active_items across all boards.
    """
    from common.db_pool import db_lock
    try:
        async with asyncio.timeout(2.0):
            async def _fetch_and_merge():
                async with db.execute("SELECT board_id, active_items FROM Users WHERE user_id = ?", (user_id,)) as c:
                    rows = await c.fetchall()
                return merge_user_active_items_rows(rows, board_id)

            if getattr(db_lock, "is_owned_by_current_task", lambda: False)():
                return await _fetch_and_merge()
            else:
                async with db_lock:
                    return await _fetch_and_merge()
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
        pass
    except asyncio.TimeoutError:
        print(f"⚠️ Таймаут при удалении сообщения {message.message_id} в чате {message.chat.id}")
    except Exception as e:
        if "message to delete not found" not in str(e).lower():
            print(f"🔥 Ошибка в delete_message_after_delay: {type(e).__name__}: {e}")


async def apply_regular_mute(user_id: int, board_id: str, duration_seconds: int = 1800):
    """Applies mute in board_data in-memory and database."""
    from datetime import datetime, timedelta, timezone, UTC
    now_dt = datetime.now(UTC)
    expire_dt = now_dt + timedelta(seconds=duration_seconds)
    if board_id in board_data and 'mutes' in board_data[board_id]:
        board_data[board_id]['mutes'][user_id] = expire_dt
    else:
        board_data[board_id]['mutes'] = {user_id: expire_dt}
    try:
        from common.db_pool import get_pool, db_lock
        db = await get_pool()
        async with db_lock:
            await db.execute(
                "UPDATE Users SET cursed_until = MAX(COALESCE(cursed_until, 0), ?) WHERE user_id = ? AND board_id = ?",
                (int(expire_dt.timestamp()), user_id, board_id)
            )
            await db.commit()
    except Exception:
        pass


async def remove_regular_mute(user_id: int, board_id: str):
    """Removes mute from board_data and database."""
    if board_id in board_data and 'mutes' in board_data[board_id]:
        board_data[board_id]['mutes'].pop(user_id, None)
    try:
        from common.db_pool import get_pool, db_lock
        db = await get_pool()
        async with db_lock:
            await db.execute(
                "UPDATE Users SET cursed_until = 0 WHERE user_id = ? AND board_id = ?",
                (user_id, board_id)
            )
            await db.commit()
    except Exception:
        pass


async def get_author_id_by_reply(msg: types.Message) -> int | None:
    """Resolves true author_id from a replied message across memory and DB copies."""
    if not msg or not msg.reply_to_message:
        return None
    target_chat_id = msg.reply_to_message.chat.id
    reply_mid = msg.reply_to_message.message_id
    lookup_key = (target_chat_id, reply_mid)
    post_num = None
    try:
        from shared_state import storage_lock, message_to_post, messages_storage
        async with storage_lock:
            post_num = message_to_post.get(lookup_key)
            if post_num and post_num in messages_storage:
                return messages_storage[post_num].get("author_id")
    except Exception:
        pass

    if not post_num:
        try:
            from common.database import get_post_info_by_copy
            info = await get_post_info_by_copy(target_chat_id, reply_mid)
            if info:
                post_num = info[0]
        except Exception:
            pass

    if post_num:
        try:
            from common.database import get_post_by_num
            db_post = await get_post_by_num(post_num)
            if db_post and 'author_id' in db_post:
                return db_post['author_id']
        except Exception:
            pass

    try:
        from common.database import get_post_author_by_copy
        db_author_id = await get_post_author_by_copy(target_chat_id, reply_mid)
        if db_author_id is not None:
            return db_author_id
    except Exception:
        pass
    return None


async def get_post_num_by_reply(msg: types.Message) -> int | None:
    """Resolves true post_num from a replied message."""
    if not msg or not msg.reply_to_message:
        return None
    target_chat_id = msg.reply_to_message.chat.id
    reply_mid = msg.reply_to_message.message_id
    lookup_key = (target_chat_id, reply_mid)
    try:
        from shared_state import storage_lock, message_to_post
        async with storage_lock:
            post_num = message_to_post.get(lookup_key)
            if post_num:
                return post_num
    except Exception:
        pass

    try:
        from common.database import get_post_info_by_copy
        info = await get_post_info_by_copy(target_chat_id, reply_mid)
        if info and info[0]:
            return info[0]
    except Exception:
        pass
    return None

