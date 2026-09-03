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
from common.db_pool import LazyLock
from common.anon_identity import get_anon_id
from typing import Optional, Any

classic_duel_lock = LazyLock()


async def send_pvp_direct_notification(bot: Any, user_id: int, text: str) -> bool:
    """
    Safely sends a private notification DM to a user on Telegram with full error suppression.
    Catches TelegramForbiddenError, TelegramBadRequest, and generic exceptions cleanly.
    """
    if not bot or not user_id:
        return False
    try:
        from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest, TelegramRetryAfter
        await bot.send_message(
            chat_id=user_id,
            text=text,
            parse_mode="HTML"
        )
        return True
    except (TelegramForbiddenError, TelegramBadRequest) as e:
        logging.getLogger("runtime").debug(f"Direct notification suppressed for user {user_id}: {e}")
        return False
    except Exception as e:
        logging.getLogger("runtime").warning(f"Direct notification failed for user {user_id}: {e}")
        return False


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
        "flag_ua_until", "cursed_until", "janitor_immunity_until",
        "partyvan_immunity_until"
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

    reject_msg = None
    duel_result = None

    async with classic_duel_lock:
        # Acceptor cannot already have an active open duel challenge themselves
        if user_id in _active_duels:
            existing = _active_duels[user_id]
            if time.time() - existing["ts"] < _DUEL_TIMEOUT:
                await message.answer("⚠️ У тебя самого есть активный вызов на дуэль — сначала отмени его.")
                return
            else:
                _active_duels.pop(user_id, None)

        if challenger_id not in _active_duels:
            reject_msg = "⚔️ Эта дуэль уже была принята или истекла."
        else:
            duel = _active_duels[challenger_id]
            now = time.time()
            if now - duel.get("ts", 0) > _DUEL_TIMEOUT:
                _active_duels.pop(challenger_id, None)
                reject_msg = "⚔️ Эта дуэль уже истекла."
            else:
                target_id = duel.get("target_id")
                if target_id and user_id != target_id:
                    reject_msg = f"⚔️ Этот персональный вызов брошен Анону [{get_anon_id(target_id)}]. Ты не можешь его принять!"
                else:
                    amount = duel.get("amount", 0)
                    async with db_lock:
                        ch_bal = await get_user_global_balance(db, challenger_id)
                        op_bal = await get_user_global_balance(db, user_id)

                    if ch_bal < amount:
                        _active_duels.pop(challenger_id, None)
                        reject_msg = f"⚔️ Вызывающий Анон [{get_anon_id(challenger_id)}] уже не потянет ставку — слился."
                    elif op_bal < amount:
                        # Opponent lacks funds; duel remains active in pool for other players
                        reject_msg = f"❌ У тебя недостаточно шекелей. Нужно {amount:,} ₪, у тебя {int(op_bal):,} ₪."
                    else:
                        # Capture broadcast copies for live updating
                        broadcast_msgs = list(duel.get("broadcast_msgs", []))
                        _active_duels.pop(challenger_id, None)

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
                            
                            try:
                                w_items = await _get_user_active_items(db, winner_id, board_id)
                                from achievements_engine import check_and_unlock_achievement
                                unlocked, ach_info = check_and_unlock_achievement(w_items, "ach_duel_win")
                                if unlocked and ach_info:
                                    await add_user_global_balance(db, winner_id, board_id, ach_info["reward_cash"])
                                    await record_user_transaction(db, winner_id, ach_info["reward_cash"], 'drop', f'Достижение: {ach_info["name"]}')
                                    await db.execute("UPDATE Users SET active_items = ? WHERE user_id = ? AND board_id = ?",
                                                     (json.dumps(w_items), winner_id, board_id))
                            except Exception:
                                pass
                            await db.commit()

                            duel_result = {
                                "winner_id": winner_id,
                                "loser_id": loser_id,
                                "amount": amount,
                                "net_win": net_win,
                                "broadcast_msgs": broadcast_msgs
                            }
                        else:
                            reject_msg = "❌ У одного из участников изменился баланс во время принятия дуэли."

    if reject_msg is not None:
        await message.answer(reject_msg)
        return

    if not duel_result:
        return

    winner_id = duel_result["winner_id"]
    loser_id = duel_result["loser_id"]
    amount = duel_result["amount"]
    net_win = duel_result["net_win"]
    broadcast_msgs = duel_result.get("broadcast_msgs", [])

    w_tag = f"Анон [{get_anon_id(winner_id)}]"
    l_tag = f"Анон [{get_anon_id(loser_id)}]"
    duel_text = (
        f"⚔️ <b>ДУЭЛЬ ЗАВЕРШЕНА!</b>\n\n"
        f"🎲 Монета решила исход битвы:\n"
        f"🏆 Победитель: <b>{w_tag}</b> <code>+{net_win:,} ₪</code>\n"
        f"💀 Проигравший: <b>{l_tag}</b> <code>-{amount:,} ₪</code>"
    )
    bot = getattr(message, "bot", None)

    # Обновляем все карточки вызова на доске
    if bot and broadcast_msgs:
        for cid, mid in broadcast_msgs:
            try:
                await bot.edit_message_text(
                    chat_id=cid,
                    message_id=mid,
                    text=duel_text,
                    reply_markup=None,
                    parse_mode="HTML"
                )
            except Exception:
                pass

    # Отправка плаката и итогов обоим участникам
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
        photo_bytes = buf.getvalue()

        if bot:
            win_notify_text = (
                f"👑 <b>ПОБЕДА В ДУЭЛИ!</b>\n\n"
                f"Противник: <b>{l_tag}</b>\n"
                f"💰 Твой чистый выигрыш: <b>+{net_win:,} ₪</b> (банк {amount:,} ₪ за вычетом 5% в Казну Абу) зачислен на баланс!"
            )
            lose_notify_text = (
                f"💀 <b>ПОРАЖЕНИЕ В ДУЭЛИ</b>\n\n"
                f"Победитель: <b>{w_tag}</b>\n"
                f"💸 Списано: <b>-{amount:,} ₪</b>."
            )
            try:
                await bot.send_photo(
                    chat_id=winner_id,
                    photo=BufferedInputFile(photo_bytes, filename="duel_win.png"),
                    caption=win_notify_text,
                    parse_mode="HTML"
                )
            except Exception:
                pass
            try:
                await bot.send_photo(
                    chat_id=loser_id,
                    photo=BufferedInputFile(photo_bytes, filename="duel_lose.png"),
                    caption=lose_notify_text,
                    parse_mode="HTML"
                )
            except Exception:
                pass
    except Exception:
        if bot:
            try: await bot.send_message(winner_id, duel_text, parse_mode="HTML")
            except Exception: pass
            try: await bot.send_message(loser_id, duel_text, parse_mode="HTML")
            except Exception: pass

async def decline_duel_logic(message: types.Message, challenger_id: int, user_id: int | None = None) -> bool:
    if user_id is None:
        user_id = message.from_user.id
    
    broadcast_msgs = []
    async with classic_duel_lock:
        if challenger_id not in _active_duels:
            return False
            
        duel = _active_duels.get(challenger_id, {})
        target_id = duel.get("target_id")
        if target_id and user_id != target_id and user_id != challenger_id:
            return False

        broadcast_msgs = list(duel.get("broadcast_msgs", []))
        _active_duels.pop(challenger_id, None)

    bot = getattr(message, "bot", None)
    if bot and broadcast_msgs:
        for cid, mid in broadcast_msgs:
            try:
                await bot.edit_message_text(
                    chat_id=cid,
                    message_id=mid,
                    text="❌ <b>Вызов на дуэль был отменен или отклонен.</b>",
                    reply_markup=None,
                    parse_mode="HTML"
                )
            except Exception:
                pass

    if user_id == challenger_id:
        await message.answer("⚔️ Вызов на дуэль успешно отменен создателем.")
        return True
    else:
        bot = getattr(message, "bot", None)
        if bot and challenger_id:
            decline_notify_text = (
                f"⚔️ <b>ВЫЗОВ НА ДУЭЛЬ ОТКЛОНЕН</b>\n\n"
                f"Анон [{get_anon_id(user_id)}] отклонил твой вызов на дуэль."
            )
            asyncio.create_task(send_pvp_direct_notification(bot, challenger_id, decline_notify_text))

        await message.answer(f"⚔️ Вызов на дуэль отклонен Анон [{get_anon_id(user_id)}].")
        return True



async def handle_cyberchad_counter_action(message: types.Message, action: str, user_id: int, board_id: str, db) -> bool:
    """
    Handles hilarious counter-attacks / excuses when users target AI / Cyberchad posts (author_id == 0).
    Returns True if handled.
    """
    import time, json
    from common.database import (
        record_user_transaction,
        get_user_global_balance, deduct_user_global_balance, add_to_abu_fund
    )
    current_time = int(time.time())

    if action == "shoot": # /shoot (Mutegun)
        mute_sec = 900 # 15 min
        try:
            from common.database import apply_regular_mute
            await apply_regular_mute(user_id, board_id, mute_sec)
        except Exception:
            pass
        async with db_lock:
            await db.execute(
                "INSERT INTO UserTransactions (user_id, amount, category, description, timestamp) VALUES (?, ?, ?, ?, ?)",
                (user_id, 0.0, 'combat', 'Рикошет Мут-Гана от Киберчеда (мут 15м)', current_time)
            )
            await db.commit()
        await message.answer(
            "🔇 <b>РИКОШЕТ МУТ-ГАНА!</b>\n\n"
            "Ты выстрелил из Мут-Гана в Киберчеда. Луч со звоном отскочил от его адамантиевых скул прямо тебе в лоб!\n\n"
            "💀 <b>Ты замучен на 15 минут за попытку заглушить высший разум.</b>",
            parse_mode="HTML"
        )
        return True

    elif action == "rob": # /rob (Knife robbery)
        fine = 500
        async with db_lock:
            user_bal = await get_user_global_balance(db, user_id)
            actual_fine = min(int(user_bal), fine)
            if actual_fine > 0:
                await deduct_user_global_balance(db, user_id, board_id, actual_fine)
                await add_to_abu_fund(db, actual_fine)
                await record_user_transaction(db, user_id, -actual_fine, 'rob', 'Попытка ограбить Киберчеда (штраф за наглость)')
                await db.commit()
        await message.answer(
            "🔪 <b>ОГРАБЛЕНИЕ ПРОВАЛЕНО!</b>\n\n"
            "Киберчед перехватывает твой нож двумя пальцами, завязывает его в узел и выворачивает твои карманы одной рукой, пока жмёт сотку другой.\n\n"
            f"💸 <b>Списано: -{actual_fine:,} ₪</b> в Фонд Абу за омежную наглость.",
            parse_mode="HTML"
        )
        return True

    elif action == "shit": # /shit (Throw poop)
        from shared_state import register_attacker_effect
        register_attacker_effect("shit", user_id, user_id, 3600)
        async with db_lock:
            u_items = await _get_user_active_items(db, user_id, board_id)
            u_items["shit_until"] = current_time + 3600
            await db.execute("""
                INSERT INTO Users (user_id, board_id, active_items)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id, board_id) DO UPDATE SET active_items = excluded.active_items
            """, (user_id, board_id, json.dumps(u_items)))
            await db.commit()
        await message.answer(
            "💩 <b>КРИТИЧЕСКИЙ САМООБСЁР!</b>\n\n"
            "Ты попытался метнуть говно в Киберчеда, но оно сгорело в плотных слоях его гигачад-ауры, а остатки ветром сдуло тебе прямо в лицо!\n\n"
            "🤮 <b>Ты весь в говне на 1 час.</b> Твои посты теперь помечены подливой.",
            parse_mode="HTML"
        )
        return True

    elif action == "vomit": # /vomit (Vomit)
        from shared_state import register_attacker_effect
        register_attacker_effect("vomit", user_id, user_id, 3600)
        async with db_lock:
            u_items = await _get_user_active_items(db, user_id, board_id)
            u_items["vomit_until"] = current_time + 3600
            await db.execute("""
                INSERT INTO Users (user_id, board_id, active_items)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id, board_id) DO UPDATE SET active_items = excluded.active_items
            """, (user_id, board_id, json.dumps(u_items)))
            await db.commit()
        await message.answer(
            "🤮 <b>ОБРАТНЫЙ РЕФЛЮКС!</b>\n\n"
            "Ты попытался блевануть на Киберчеда, но от одного его надменного взгляда подавился собственной желчью и залил свои же штаны!\n\n"
            "🤢 <b>Дебафф блевоты повешен на тебя на 1 час.</b>",
            parse_mode="HTML"
        )
        return True

    elif action == "pepperspray": # /pepperspray
        from shared_state import register_attacker_effect
        register_attacker_effect("pepperspray", user_id, user_id, 1800)
        async with db_lock:
            u_items = await _get_user_active_items(db, user_id, board_id)
            u_items["peppersprayed_until"] = current_time + 1800
            await db.execute("""
                INSERT INTO Users (user_id, board_id, active_items)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id, board_id) DO UPDATE SET active_items = excluded.active_items
            """, (user_id, board_id, json.dumps(u_items)))
            await db.commit()
        await message.answer(
            "🧯 <b>ПЕРЦОВЫЙ ИНГАЛЯТОР!</b>\n\n"
            "Ты выпустил струю перцовки в Киберчеда. Он глубоко вдохнул её ноздрями: <i>«Приятный ментол, сыч. Держи сдачу»</i> — и дунул струю тебе обратно в глаза!\n\n"
            "🌶️ <b>Ты ослеплён на 30 минут.</b> Твой экран слезится, а посты искажаются.",
            parse_mode="HTML"
        )
        return True

    elif action == "partyvan": # /partyvan (OMON)
        mute_sec = 7200 # 2 hours
        try:
            from common.database import apply_regular_mute
            await apply_regular_mute(user_id, board_id, mute_sec)
        except Exception:
            pass
        async with db_lock:
            await db.execute(
                "INSERT INTO UserTransactions (user_id, amount, category, description, timestamp) VALUES (?, ?, ?, ?, ?)",
                (user_id, 0.0, 'combat', 'Арест за ложный донос на Киберчеда (2ч)', current_time)
            )
            await db.commit()
        await message.answer(
            "🚔 <b>ЛОЖНЫЙ ДОНОС НА КИБЕРЧЕДА!</b>\n\n"
            "ОМОН с автоматами ворвался на хату Киберчеда, но увидев его бицепсы и пресс, майор извинился, взял автограф, а тебя упаковали в автозак за ложный вызов.\n\n"
            "⛓️ <b>Ты отправлен в обезьянник на 2 часа (полный мут).</b>",
            parse_mode="HTML"
        )
        return True

    elif action == "bribe":
        await message.answer(
            "💰 <b>ВЗЯТКА НЕ ПРИНЯТА!</b>\n\n"
            "Ты попытался сунуть Киберчеду пачку шекелей. Киберчед сжёг их взглядом: <i>«Я не беру подачки от омежек, я беру их души»</i>.\n\n"
            "Шекели превратились в пепел.",
            parse_mode="HTML"
        )
        return True

    elif action == "dossier":
        await message.answer(
            "📁 <b>ДОСЬЕ НА КИБЕРЧЕДА</b>\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "👤 <b>Субъект:</b> КИБЕРЧЕД-9000 (Alpha-Tier AI)\n"
            "💪 <b>Статус:</b> Абсолютный доминатор чата\n"
            "🏋️ <b>Жим лёжа:</b> 250 кг на 10 повторений\n"
            "🧠 <b>IQ:</b> Неизмеримо выше твоего\n"
            "💀 <b>Слабые места:</b> Отсутствуют\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "<i>Примечание майора: Не связываться, опасен для самооценки сычей.</i>",
            parse_mode="HTML"
        )
        return True

    return False


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


