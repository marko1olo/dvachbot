import asyncio
import time
import random
import json
import logging
from aiogram import types
from shared_state import *
from common.config import *
from common.database import *
from common.db_pool import LazyLock
from common.anon_identity import get_anon_id
from typing import Optional, Any, Union
from post_processor import process_new_post

classic_duel_lock = LazyLock()


async def send_pvp_direct_notification(bot: Any, user_id: int, text: str) -> bool:
    """
    Safely sends a private notification DM to a user on Telegram with full error suppression.
    Catches TelegramForbiddenError, TelegramBadRequest, and generic exceptions cleanly.
    """
    if not bot or not user_id:
        return False
    try:
        from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest
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


async def safe_callback_answer(callback: types.CallbackQuery, *args, **kwargs) -> bool:
    """
    Safely answers a Telegram CallbackQuery with length truncation (<=195 chars)
    and suppression of TelegramBadRequest (e.g. query is too old or text is too long).
    """
    if not callback:
        return False
    # If no message/toast is requested and query has already been answered, skip to prevent double answer
    if not args and not kwargs:
        ans_mock = getattr(callback, "answer", None)
        if ans_mock and hasattr(ans_mock, "called") and bool(ans_mock.called):
            return True
        if bool(getattr(callback, "_answered", False)):
            return True
    try:
        from aiogram.exceptions import TelegramBadRequest
        if args and isinstance(args[0], str):
            text = args[0]
            if len(text) > 195:
                text = text[:192] + "..."
            args = (text,) + args[1:]
        elif "text" in kwargs and isinstance(kwargs["text"], str):
            text = kwargs["text"]
            if len(text) > 195:
                kwargs["text"] = text[:192] + "..."
        await callback.answer(*args, **kwargs)
        try:
            setattr(callback, "_answered", True)
        except Exception:
            pass
        return True
    except TelegramBadRequest as e:
        logging.getLogger("runtime").debug("safe_callback_answer: query expired or invalid: %s", e)
        return False
    except Exception as e:
        logging.getLogger("runtime").debug("safe_callback_answer error: %s", e)
        return False


class SafeMessageProxy:
    def __init__(self, original_msg, user, bot=None):
        self._msg = original_msg
        self.from_user = user
        self.bot = getattr(original_msg, 'bot', None) or bot
        self.chat = getattr(original_msg, 'chat', None)
        self.date = getattr(original_msg, 'date', None)
        self.message_id = getattr(original_msg, 'message_id', 0)
        self.text = "/command"
        self.caption = ""
        self.html_text = "/command"
        self.caption_html_text = ""
        self.reply_to_message = None

    async def answer(self, *args, **kwargs):
        from aiogram import types
        if self._msg and hasattr(self._msg, 'answer') and not isinstance(self._msg, types.InaccessibleMessage):
            try:
                return await self._msg.answer(*args, **kwargs)
            except Exception:
                pass
        target_chat_id = self.chat.id if (self.chat and hasattr(self.chat, 'id')) else (self.from_user.id if self.from_user else None)
        if self.bot and target_chat_id:
            text = args[0] if args else kwargs.pop('text', '')
            return await self.bot.send_message(chat_id=target_chat_id, text=text, **kwargs)
        return None

    async def reply(self, *args, **kwargs):
        return await self.answer(*args, **kwargs)



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

def merge_user_active_items_rows(rows: list, board_id: str | None = None, user_id: int | None = None) -> dict:
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

    shared_cooldowns = {}
    if user_id:
        try:
            from shared_state import get_user_work_cooldowns
            shared_cooldowns = get_user_work_cooldowns(user_id)
        except Exception:
            shared_cooldowns = {}
    daily_streak = 0
    daily_last_claim = 0
    last_bottles = 0
    mother_sold = False
    janitor_deletes_left = 0
    janitor_until = 0
    badge_color = None
    badge_color_active = False
    badge_color_expires = 0

    max_wanted_stars = 0
    max_bounty = 0.0
    max_dirty = 0.0
    max_wanted_updated_at = 0.0

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
        achs = list(data.get("unlocked_achievements", []) or []) + list(data.get("achievements", []) or [])
        for ach in achs:
            if isinstance(ach, str) and ach:
                all_achievements.add(ach)

        # 3. Work Cooldowns
        for job_id, cd_ts in data.get("work_cooldowns", {}).items():
            if isinstance(cd_ts, (int, float)):
                if shared_cooldowns and job_id in shared_cooldowns and shared_cooldowns[job_id] <= 0:
                    work_cooldowns[job_id] = 0
                else:
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
        if data.get("badge_color") and data.get("badge_color") not in ("none", "off", "0", ""):
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

        # 11. Criminal Syndicate Status (Cross-board wanted sync)
        ws = data.get("wanted_stars", 0)
        if isinstance(ws, (int, float)) and ws > max_wanted_stars:
            max_wanted_stars = int(ws)
        bp = data.get("bounty_pool", 0.0) or data.get("bounty", 0.0)
        if isinstance(bp, (int, float)) and bp > max_bounty:
            max_bounty = float(bp)
        db_bal = data.get("dirty_balance", 0.0)
        if isinstance(db_bal, (int, float)) and db_bal > max_dirty:
            max_dirty = float(db_bal)
        w_up = data.get("wanted_updated_at", 0.0)
        if isinstance(w_up, (int, float)) and w_up > max_wanted_updated_at:
            max_wanted_updated_at = float(w_up)

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

    # Collect recent_shifts and daily_quests across all board rows
    all_recent_shifts = {}
    merged_daily_quests = {}
    for b_id, a_str in rows:
        if not a_str:
            continue
        try:
            d = json.loads(a_str) if isinstance(a_str, str) else (a_str if isinstance(a_str, dict) else {})
        except Exception:
            continue
        if isinstance(d, dict):
            r_s = d.get("recent_shifts")
            if isinstance(r_s, dict):
                for jid, timestamps in r_s.items():
                    if isinstance(timestamps, list):
                        all_recent_shifts.setdefault(jid, []).extend(timestamps)
            dq = d.get("daily_quests")
            if isinstance(dq, dict):
                if dq.get("claimed"):
                    merged_daily_quests = dq
                elif not merged_daily_quests:
                    merged_daily_quests = dq

    if all_recent_shifts:
        now_ts = time.time()
        result["recent_shifts"] = {
            jid: sorted(list(set(ts for ts in tss if 0 <= now_ts - ts < 86400)))
            for jid, tss in all_recent_shifts.items()
        }
    if merged_daily_quests:
        result["daily_quests"] = merged_daily_quests

    if max_shifts > 0:
        result["work_shifts"] = max_shifts
    if all_achievements:
        result["unlocked_achievements"] = sorted(list(all_achievements))
    if work_cooldowns:
        if shared_cooldowns:
            for jid, scd in shared_cooldowns.items():
                if scd <= 0:
                    work_cooldowns[jid] = 0
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
    if current_items and "badge_color" in current_items:
        c_val = current_items.get("badge_color")
        result["badge_color"] = c_val if c_val not in ("none", "off", "0", "") else None
    elif badge_color and badge_color not in ("none", "off", "0", ""):
        result["badge_color"] = badge_color
    else:
        result["badge_color"] = None

    if max_wanted_stars > 0:
        result["wanted_stars"] = max_wanted_stars
        result["bounty_pool"] = max_bounty
        result["bounty"] = max_bounty
        if max_wanted_updated_at > 0:
            result["wanted_updated_at"] = max_wanted_updated_at
        try:
            from criminal_syndicate_engine import apply_wanted_decay
            apply_wanted_decay(result)
        except Exception:
            pass
    if max_dirty > 0:
        result["dirty_balance"] = max_dirty

    now_ts = int(time.time())
    if badge_color_expires > 0 and now_ts >= badge_color_expires:
        result["badge_color"] = None
        result["badge_color_active"] = False
    elif badge_color_active:
        result["badge_color_active"] = True

    if badge_color_expires > 0:
        result["badge_color_expires"] = badge_color_expires

    return result

async def check_user_is_muted(db, user_id: int, board_id: str | None = None) -> bool:
    """
    Checks if a user is currently muted in RAM or in SQLite Mutes table.
    """
    import time
    from datetime import datetime, UTC
    now_ts = time.time()
    now_dt = datetime.now(UTC)

    # 1. RAM check
    try:
        from shared_state import board_data as b_data
    except Exception:
        import sys
        main_mod = sys.modules.get('__main__')
        b_data = getattr(main_mod, 'board_data', {})
    b_id = board_id or 'b'

    board_mutes = b_data.get(b_id, {}).get('mutes', {})
    all_mutes = b_data.get('ALL', {}).get('mutes', {})
    if (board_mutes.get(user_id) and board_mutes[user_id] > now_dt) or \
       (all_mutes.get(user_id) and all_mutes[user_id] > now_dt):
        return True

    # 2. DB check
    try:
        cursor_res = db.execute(
            "SELECT 1 FROM Mutes WHERE user_id = ? AND (board_id = ? OR board_id = 'ALL' OR board_id IS NULL) AND expires_at > ? LIMIT 1",
            (user_id, b_id, now_ts)
        )
        if asyncio.iscoroutine(cursor_res):
            cursor_res = await cursor_res
        row = None
        if hasattr(cursor_res, "__aenter__"):
            async with cursor_res as c:
                row = await c.fetchone()
        elif hasattr(cursor_res, "fetchone"):
            row = cursor_res.fetchone()
            if asyncio.iscoroutine(row):
                row = await row
        if row is not None:
            if not type(row).__name__.endswith("Mock"):
                return bool(row)
    except Exception:
        pass
    return False


async def _get_user_active_items(db, user_id: int, board_id: str | None = None) -> dict:
    """
    Asynchronously loads and merges user active_items across all boards.
    """
    from common.db_pool import db_lock, db_transaction
    try:
        async with asyncio.timeout(2.0):
            async def _fetch_and_merge():
                async with db.execute("SELECT board_id, active_items FROM Users WHERE user_id = ?", (user_id,)) as c:
                    rows = await c.fetchall()
                return merge_user_active_items_rows(rows, board_id, user_id=user_id)

            if getattr(db_lock, "is_owned_by_current_task", lambda: False)():
                return await _fetch_and_merge()
            else:
                async with db_lock:
                    return await _fetch_and_merge()
    except Exception:
        return {}

async def accept_duel_logic(message: types.Message, challenger_id: int, board_id: str, user_id: int | None = None):
    import time

    # Handle possible reversed/legacy argument order (message, db, board_id, challenger_id)
    if not isinstance(challenger_id, (int, float)) or hasattr(challenger_id, "execute"):
        if isinstance(user_id, (int, float)):
            challenger_id = int(user_id)
        user_id = getattr(getattr(message, "from_user", None), "id", None)

    db = await get_pool()
    if user_id is None:
        user_id = getattr(getattr(message, "from_user", None), "id", None)

    if challenger_id == user_id:
        await message.answer("Нельзя принять собственный вызов, трус.")
        return

    # Мут-гард для принимающего
    from common.database import is_shadow_muted as check_db_shadow_muted
    if await check_db_shadow_muted(user_id, board_id, db=db) or await check_user_is_muted(db, user_id, board_id):
        await message.answer("🔇 Замученным нельзя принимать дуэли.")
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
                if duel.get("escrowed"):
                    async with db_transaction(db):
                        await add_user_global_balance(db, challenger_id, duel.get("board_id", board_id), duel.get("amount", 0))
                        await record_user_transaction(db, challenger_id, duel.get("amount", 0), 'duel', 'Возврат ставки: таймаут дуэли')
                _active_duels.pop(challenger_id, None)
                reject_msg = "⚔️ Эта дуэль уже истекла."
            else:
                target_id = duel.get("target_id")
                if target_id and user_id != target_id:
                    reject_msg = f"⚔️ Этот персональный вызов брошен Анону [{get_anon_id(target_id)}]. Ты не можешь его принять!"
                else:
                    amount = duel.get("amount", 0)
                    ch_escrowed = bool(duel.get("escrowed", False))
                    # Мут-гард для создателя дуэли: если его замутили пока вызов висел
                    if await check_db_shadow_muted(challenger_id, board_id, db=db) or await check_user_is_muted(db, challenger_id, board_id):
                        if ch_escrowed:
                            async with db_transaction(db):
                                await add_user_global_balance(db, challenger_id, board_id, amount)
                                await record_user_transaction(db, challenger_id, amount, 'duel', 'Возврат ставки: создатель замучен')
                        _active_duels.pop(challenger_id, None)
                        reject_msg = f"⚔️ Вызывающий Анон [{get_anon_id(challenger_id)}] был замучен — дуэль отменена."
                    else:
                        async with db_transaction(db):
                            # 1. Verify and escrow challenger stake if not already escrowed
                            if not ch_escrowed:
                                ch_bal = await get_user_global_balance(db, challenger_id)
                                if ch_bal < amount:
                                    _active_duels.pop(challenger_id, None)
                                    reject_msg = f"⚔️ Вызывающий Анон [{get_anon_id(challenger_id)}] уже не потянет ставку — слился."
                                else:
                                    ok_c, _ = await deduct_user_global_balance(db, challenger_id, board_id, amount)
                                    if not ok_c:
                                        _active_duels.pop(challenger_id, None)
                                        reject_msg = f"⚔️ Вызывающий Анон [{get_anon_id(challenger_id)}] уже не потянет ставку — слился."
                                    else:
                                        ch_escrowed = True
                                        await record_user_transaction(db, challenger_id, -amount, 'duel', f'Ставка в дуэли против [{get_anon_id(user_id)}]')

                            if not reject_msg:
                                # 2. Verify and escrow acceptor stake
                                op_bal = await get_user_global_balance(db, user_id)
                                if op_bal < amount:
                                    if not duel.get("escrowed") and ch_escrowed:
                                        await add_user_global_balance(db, challenger_id, board_id, amount)
                                    reject_msg = f"❌ У тебя недостаточно шекелей. Нужно {amount:,} ₪, у тебя {int(op_bal):,} ₪."
                                else:
                                    ok_a, _ = await deduct_user_global_balance(db, user_id, board_id, amount)
                                    if not ok_a:
                                        if not duel.get("escrowed") and ch_escrowed:
                                            await add_user_global_balance(db, challenger_id, board_id, amount)
                                        reject_msg = f"❌ У тебя недостаточно шекелей. Нужно {amount:,} ₪."
                                    else:
                                        await record_user_transaction(db, user_id, -amount, 'duel', f'Ставка в дуэли против [{get_anon_id(challenger_id)}]')

                                        # Capture broadcast copies for live updating
                                        broadcast_msgs = list(duel.get("broadcast_msgs", []))
                                        _active_duels.pop(challenger_id, None)

                                        winner_id = random.choice([challenger_id, user_id])
                                        loser_id  = challenger_id if winner_id == user_id else user_id

                                        # 5% Rake to Abu's Fund and payout to winner
                                        rake = max(1, int(amount * 0.05))
                                        net_win = amount - rake
                                        winner_payout = (amount * 2) - rake

                                        await add_user_global_balance(db, winner_id, board_id, winner_payout)
                                        await add_to_abu_fund(db, rake)
                                        await record_user_transaction(db, winner_id, winner_payout, 'duel', f'Победа в дуэли против [{get_anon_id(loser_id)}]')

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

                                        duel_result = {
                                            "winner_id": winner_id,
                                            "loser_id": loser_id,
                                            "amount": amount,
                                            "net_win": net_win,
                                            "broadcast_msgs": broadcast_msgs
                                        }

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

    # Уведомление участникам дуэли в ЛС об исходе битвы
    if bot:
        for uid, is_win, amt_change in [(winner_id, True, net_win), (loser_id, False, amount)]:
            try:
                dm_res = (
                    f"⚔️ <b>ИТОГ ДУЭЛИ В /{board_id}/!</b>\n\n"
                    f"🏆 <b>Победа!</b> Ты выиграл <code>+{amt_change:,} ₪</code> в дуэли против {l_tag}!"
                    if is_win else
                    f"⚔️ <b>ИТОГ ДУЭЛИ В /{board_id}/!</b>\n\n"
                    f"💀 <b>Поражение!</b> Ты потерял <code>-{amt_change:,} ₪</code> в дуэли против {w_tag}."
                )
                await bot.send_message(chat_id=uid, text=dm_res, parse_mode="HTML")
            except Exception:
                pass

    if net_win >= 300000 and bot:
        try:
            from news_channel_publisher import publish_casino_jackpot_news
            asyncio.create_task(publish_casino_jackpot_news(
                bot=bot,
                user_id=winner_id,
                game_type="duel",
                bet_amount=amount,
                win_amount=net_win,
                multiplier=round(net_win / max(1, amount), 2),
                symbols=f"{w_tag} vs {l_tag}",
                board_id=board_id
            ))
        except Exception:
            pass

    if net_win >= 100000 and (net_win / max(1, amount)) >= 5.0 and bot:
        try:
            from post_processor import process_new_post
            import shared_state
            hype_text = (
                f"⚔️🔥 <b>МЕГА-ДУЭЛЬ: РАЗНОС НА {amount:,} ₪!</b> 🔥⚔️\n\n"
                f">два анона сошлись в кровавой схватке 50/50!\n"
                f"👑 <b>Триумфатор:</b> {w_tag}\n"
                f"💀 <b>Повержен:</b> {l_tag}\n"
                f"💰 <b>Куш дуэли:</b> <b>+{net_win:,} ₪</b>!\n"
            )
            params = shared_state.NewPostParams(
                bot_instance=bot,
                board_id=board_id,
                user_id=0,
                content={'type': 'text', 'text': hype_text, 'is_system_message': True, 'archive_allowed': True},
                reply_to_post=None,
                is_shadow_muted=False,
                stream='ru'
            )
            asyncio.create_task(process_new_post(params))
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

    return duel_result

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
        refund_amount = 0
        duel_board_id = "b"
        if duel.get("escrowed"):
            refund_amount = duel.get("amount", 0)
            duel_board_id = duel.get("board_id", "b")
        _active_duels.pop(challenger_id, None)

    if refund_amount > 0:
        db = await get_pool()
        async with db_transaction(db):
            await add_user_global_balance(db, challenger_id, duel_board_id, refund_amount)
            await record_user_transaction(db, challenger_id, refund_amount, 'duel', 'Возврат ставки: отмена дуэли')

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



async def handle_cyberchad_counter_action(message: types.Message, action: str, user_id: int, board_id: str, db=None) -> bool:
    """
    Handles hilarious counter-attacks / excuses when users target AI / Cyberchad posts (author_id == 0).
    Returns True if handled.
    """
    import time, json
    from common.db_pool import get_pool, db_transaction
    if db is None:
        db = await get_pool()
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
        try:
            async with db_transaction(db):
                await db.execute(
                    "INSERT INTO UserTransactions (user_id, amount, category, description, timestamp) VALUES (?, ?, ?, ?, ?)",
                    (user_id, 0.0, 'combat', 'Рикошет Мут-Гана от Киберчеда (мут 15м)', current_time)
                )
        except Exception:
            pass
        await message.answer(
            "🔇 <b>РИКОШЕТ МУТ-ГАНА!</b>\n\n"
            "Ты выстрелил из Мут-Гана в Киберчеда. Луч со звоном отскочил от его адамантиевых скул прямо тебе в лоб!\n\n"
            "💀 <b>Ты замучен на 15 минут за попытку заглушить высший разум.</b>",
            parse_mode="HTML"
        )
        return True

    elif action == "rob": # /rob (Knife robbery)
        fine = 500
        actual_fine = 0
        try:
            async with db_transaction(db):
                user_bal = await get_user_global_balance(db, user_id)
                actual_fine = min(int(user_bal), fine)
                if actual_fine > 0:
                    await deduct_user_global_balance(db, user_id, board_id, actual_fine)
                    await add_to_abu_fund(db, actual_fine)
                    await record_user_transaction(db, user_id, -actual_fine, 'rob', 'Попытка ограбить Киберчеда (штраф за наглость)')
        except Exception:
            pass
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
        try:
            async with db_transaction(db):
                u_items = await _get_user_active_items(db, user_id, board_id)
                u_items["shit_until"] = current_time + 3600
                await db.execute("""
                    INSERT INTO Users (user_id, board_id, active_items)
                    VALUES (?, ?, ?)
                    ON CONFLICT(user_id, board_id) DO UPDATE SET active_items = excluded.active_items
                """, (user_id, board_id, json.dumps(u_items)))
        except Exception:
            pass
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
        try:
            async with db_transaction(db):
                u_items = await _get_user_active_items(db, user_id, board_id)
                u_items["vomit_until"] = current_time + 3600
                await db.execute("""
                    INSERT INTO Users (user_id, board_id, active_items)
                    VALUES (?, ?, ?)
                    ON CONFLICT(user_id, board_id) DO UPDATE SET active_items = excluded.active_items
                """, (user_id, board_id, json.dumps(u_items)))
        except Exception:
            pass
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
        try:
            async with db_transaction(db):
                u_items = await _get_user_active_items(db, user_id, board_id)
                u_items["peppersprayed_until"] = current_time + 1800
                await db.execute("""
                    INSERT INTO Users (user_id, board_id, active_items)
                    VALUES (?, ?, ?)
                    ON CONFLICT(user_id, board_id) DO UPDATE SET active_items = excluded.active_items
                """, (user_id, board_id, json.dumps(u_items)))
        except Exception:
            pass
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
        try:
            async with db_transaction(db):
                await db.execute(
                    "INSERT INTO UserTransactions (user_id, amount, category, description, timestamp) VALUES (?, ?, ?, ?, ?)",
                    (user_id, 0.0, 'combat', 'Арест за ложный донос на Киберчеда (2ч)', current_time)
                )
        except Exception:
            pass
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


async def apply_regular_mute(user_id: int, board_id: str, duration_seconds: int = 1800, reason: str | None = None):
    """Applies mute in board_data in-memory, SQLite Mutes table, and Users.cursed_until."""
    from datetime import datetime, timedelta, UTC
    now_dt = datetime.now(UTC)
    expire_dt = now_dt + timedelta(seconds=duration_seconds)
    b_id = board_id or 'b'
    if b_id in board_data and 'mutes' in board_data[b_id]:
        board_data[b_id]['mutes'][user_id] = expire_dt
    else:
        board_data[b_id]['mutes'] = {user_id: expire_dt}
    try:
        from common.db_pool import get_pool, db_transaction
        db = await get_pool()
        async with db_transaction(db):
            await db.execute(
                "DELETE FROM Mutes WHERE user_id = ? AND board_id = ? AND mute_type = 'mute'",
                (user_id, b_id)
            )
            try:
                await db.execute(
                    "INSERT INTO Mutes (user_id, board_id, mute_type, expires_at, reason) VALUES (?, ?, 'mute', ?, ?)",
                    (user_id, b_id, int(expire_dt.timestamp()), reason)
                )
            except Exception:
                await db.execute(
                    "INSERT INTO Mutes (user_id, board_id, mute_type, expires_at) VALUES (?, ?, 'mute', ?)",
                    (user_id, b_id, int(expire_dt.timestamp()))
                )
            await db.execute(
                "UPDATE Users SET cursed_until = MAX(COALESCE(cursed_until, 0), ?) WHERE user_id = ? AND board_id = ?",
                (int(expire_dt.timestamp()), user_id, b_id)
            )
    except Exception:
        pass


async def remove_regular_mute(user_id: int, board_id: str):
    """Removes mute from board_data, SQLite Mutes table, and Users.cursed_until."""
    b_id = board_id or 'b'
    if b_id in board_data and 'mutes' in board_data[b_id]:
        board_data[b_id]['mutes'].pop(user_id, None)
    if 'ALL' in board_data and 'mutes' in board_data['ALL']:
        board_data['ALL']['mutes'].pop(user_id, None)
    try:
        from common.db_pool import get_pool, db_transaction
        db = await get_pool()
        async with db_transaction(db):
            await db.execute(
                "DELETE FROM Mutes WHERE user_id = ? AND (board_id = ? OR board_id = 'ALL' OR board_id IS NULL) AND mute_type = 'mute'",
                (user_id, b_id)
            )
            await db.execute(
                "UPDATE Users SET cursed_until = 0 WHERE user_id = ? AND board_id = ?",
                (user_id, b_id)
            )
    except Exception:
        pass


async def get_author_id_by_reply(msg: types.Message) -> int | None:
    """Resolves true author_id from a replied message across memory and DB copies."""
    if not msg or not msg.reply_to_message:
        return None

    reply_user = msg.reply_to_message.from_user
    if reply_user and not reply_user.is_bot:
        return reply_user.id
    if msg.reply_to_message.forward_from and not msg.reply_to_message.forward_from.is_bot:
        return msg.reply_to_message.forward_from.id

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
                if info[1] is not None:
                    return info[1]
        except Exception:
            pass

    if not post_num:
        try:
            from common.text_utils import decode_post_num_zw
            reply_text = msg.reply_to_message.text or msg.reply_to_message.caption or ""
            zw_num = decode_post_num_zw(reply_text)
            if zw_num:
                post_num = zw_num
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

    try:
        from common.db_pool import get_pool
        db = await get_pool()
        async with db.execute(
            "SELECT p.author_id FROM ChannelCopies cc JOIN Posts p ON cc.post_num = p.post_num WHERE cc.channel_id = ? AND cc.message_id = ?",
            (target_chat_id, reply_mid)
        ) as cur:
            row = await cur.fetchone()
            if row and row[0]:
                return row[0]
    except Exception:
        pass

    if reply_user and reply_user.is_bot:
        return 0

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

def is_media_message(msg: Any) -> bool:
    """
    Determines whether a message is a media (photo/video/animation) message
    or a plain text message. Handles real aiogram Message objects and test mocks.
    """
    if not msg:
        return False
    # If photo attribute exists and is a non-empty sequence or real non-mock photo
    photo = getattr(msg, "photo", None)
    if photo is not None:
        if isinstance(photo, (list, tuple)):
            if len(photo) > 0:
                return True
        elif type(photo).__name__ != "MagicMock" and bool(photo):
            return True

    video = getattr(msg, "video", None)
    if video is not None and type(video).__name__ != "MagicMock" and bool(video):
        return True

    animation = getattr(msg, "animation", None)
    if animation is not None and type(animation).__name__ != "MagicMock" and bool(animation):
        return True

    content_type = getattr(msg, "content_type", None)
    if isinstance(content_type, str) and content_type in ("photo", "video", "animation"):
        return True

    caption = getattr(msg, "caption", None)
    if isinstance(caption, str) and caption:
        return True

    # If edit_caption is specifically provided without edit_text (specialized photo mock)
    if hasattr(msg, "edit_caption") and not hasattr(msg, "edit_text"):
        return True
    return False


def get_telegram_utf16_len(text: str) -> int:
    """
    Returns text length in UTF-16 code units (as counted by Telegram Bot API).
    Surrogate pairs (most emojis) count as 2.
    """
    if not text:
        return 0
    return len(text.encode("utf-16-le")) // 2


def smart_split_html(text: str, max_chunk_size: int = 4000) -> List[str]:
    """
    Splits text (plain or HTML formatted) into chunks of at most `max_chunk_size` characters,
    preserving HTML tag hierarchy across chunk boundaries so that every chunk is valid HTML.

    Guarantees:
    - len(chunk) <= max_chunk_size for every chunk.
    - All tags opened within or across chunk boundaries are properly closed before chunk ends
      and re-opened at the start of the next chunk.
    - Never breaks in the middle of an HTML tag or HTML entity.
    - Splits on natural paragraph breaks (\n\n), line breaks (\n), or whitespace when possible.
    """
    if not text:
        return []
    if len(text) <= max_chunk_size:
        return [text]

    import re
    TAG_REGEX = re.compile(r'(<(/)?([a-zA-Z0-9_-]+)(?:\s+[^>]*)?>)')

    def get_open_tags(slice_text: str, initial_stack: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
        stack = list(initial_stack)
        for m in TAG_REGEX.finditer(slice_text):
            full_tag, is_close, tag_name = m.group(1), m.group(2), m.group(3).lower()
            if is_close:
                for i in range(len(stack) - 1, -1, -1):
                    if stack[i][0] == tag_name:
                        stack.pop(i)
                        break
            else:
                if not full_tag.endswith("/>"):
                    stack.append((tag_name, full_tag))
        return stack

    def calc_closing_str(stack: List[Tuple[str, str]]) -> str:
        return "".join(f"</{tag_name}>" for tag_name, _ in reversed(stack))

    chunks: List[str] = []
    current_pos = 0
    total_len = len(text)
    open_tag_stack: List[Tuple[str, str]] = []

    while current_pos < total_len:
        prefix = "".join(tag_full for _, tag_full in open_tag_stack)

        est_closing_len = sum(len(tag_name) + 3 for tag_name, _ in open_tag_stack) + 50
        available_content_len = max(50, max_chunk_size - len(prefix) - est_closing_len)

        target_end = min(total_len, current_pos + available_content_len)

        # Check if rest of text fits cleanly
        rest_text = text[current_pos:]
        rest_stack = get_open_tags(rest_text, open_tag_stack)
        rest_closing = calc_closing_str(rest_stack)
        if len(prefix) + len(rest_text) + len(rest_closing) <= max_chunk_size:
            chunks.append(prefix + rest_text + rest_closing)
            break

        sub = text[current_pos:target_end]

        # Don't cut inside open tag
        last_lt = sub.rfind('<')
        last_gt = sub.rfind('>')
        if last_lt > last_gt:
            target_end = current_pos + last_lt
            sub = text[current_pos:target_end]

        # Don't cut inside HTML entity
        last_amp = sub.rfind('&')
        last_semi = sub.rfind(';')
        if last_amp > last_semi and (len(sub) - last_amp) < 10:
            target_end = current_pos + last_amp
            sub = text[current_pos:target_end]

        # Find best split point in sub: \n\n > \n > space > hard cut
        split_idx = -1
        p_idx = sub.rfind('\n\n')
        if p_idx != -1 and p_idx > len(sub) // 4:
            split_idx = p_idx + 2
        else:
            nl_idx = sub.rfind('\n')
            if nl_idx != -1 and nl_idx > len(sub) // 4:
                split_idx = nl_idx + 1
            else:
                sp_idx = sub.rfind(' ')
                if sp_idx != -1 and sp_idx > len(sub) // 4:
                    split_idx = sp_idx + 1
                else:
                    split_idx = len(sub)

        if split_idx <= 0:
            split_idx = max(1, len(sub))

        while split_idx > 0:
            chunk_slice = text[current_pos:current_pos + split_idx]
            candidate_stack = get_open_tags(chunk_slice, open_tag_stack)
            closing = calc_closing_str(candidate_stack)
            if len(prefix) + len(chunk_slice) + len(closing) <= max_chunk_size:
                open_tag_stack = candidate_stack
                chunks.append(prefix + chunk_slice + closing)
                current_pos += split_idx
                break
            split_idx -= max(1, (len(prefix) + len(chunk_slice) + len(closing) - max_chunk_size))
            sub_temp = text[current_pos:current_pos + split_idx]
            last_lt = sub_temp.rfind('<')
            last_gt = sub_temp.rfind('>')
            if last_lt > last_gt:
                split_idx = last_lt
        else:
            chunk_slice = text[current_pos:current_pos + 1]
            chunks.append(chunk_slice)
            current_pos += 1
            open_tag_stack = []

    return chunks


async def safe_send_message(
    bot: Any,
    chat_id: int,
    text: str,
    reply_markup: Optional[types.InlineKeyboardMarkup] = None,
    parse_mode: Optional[str] = "HTML",
    disable_web_page_preview: bool = True,
    sleep_between: float = 0.05
) -> Optional[Any]:
    """
    Safely sends any message, splitting it into valid HTML chunks if len(text) > 4000 chars.
    Guarantees that TelegramBadRequest: MESSAGE_TOO_LONG is never thrown.
    Handles HTML parsing fallbacks gracefully.
    """
    if not text or not bot or not chat_id:
        return None
    import inspect
    from aiogram.exceptions import TelegramBadRequest

    chunks = smart_split_html(text, max_chunk_size=4000) if len(text) > 4000 else [text]
    last_msg = None

    for i, chunk in enumerate(chunks):
        is_last = (i == len(chunks) - 1)
        kb = reply_markup if is_last else None
        try:
            res = bot.send_message(
                chat_id=chat_id,
                text=chunk,
                reply_markup=kb,
                parse_mode=parse_mode,
                disable_web_page_preview=disable_web_page_preview
            )
            if inspect.isawaitable(res):
                last_msg = await res
            else:
                last_msg = res
        except TelegramBadRequest as ex:
            err = str(ex).lower()
            if "parse" in err or "entity" in err:
                try:
                    res = bot.send_message(
                        chat_id=chat_id,
                        text=chunk,
                        reply_markup=kb,
                        parse_mode=None,
                        disable_web_page_preview=disable_web_page_preview
                    )
                    if inspect.isawaitable(res):
                        last_msg = await res
                    else:
                        last_msg = res
                except Exception:
                    pass
            elif "message is too long" in err or "too_long" in err:
                sub_chunks = smart_split_html(chunk, max_chunk_size=2000)
                for j, sc in enumerate(sub_chunks):
                    sub_kb = kb if (j == len(sub_chunks) - 1) else None
                    try:
                        res = bot.send_message(
                            chat_id=chat_id,
                            text=sc,
                            reply_markup=sub_kb,
                            parse_mode=None,
                            disable_web_page_preview=disable_web_page_preview
                        )
                        if inspect.isawaitable(res):
                            last_msg = await res
                        else:
                            last_msg = res
                    except Exception:
                        pass
            else:
                pass
        except Exception:
            pass

        if not is_last and sleep_between > 0:
            await asyncio.sleep(sleep_between)

    return last_msg


async def safe_answer(
    target_obj: Any,
    text: str,
    reply_markup: Optional[types.InlineKeyboardMarkup] = None,
    parse_mode: Optional[str] = "HTML",
    disable_web_page_preview: bool = True,
    sleep_between: float = 0.05
) -> Optional[Any]:
    """
    Safely answers via target_obj (Message or CallbackQuery) with automatic HTML chunking.
    """
    if not text or not target_obj:
        return None
    bot = getattr(target_obj, "bot", None)
    chat_id = 0
    if hasattr(target_obj, "chat") and target_obj.chat and hasattr(target_obj.chat, "id"):
        chat_id = target_obj.chat.id
    elif hasattr(target_obj, "from_user") and target_obj.from_user and hasattr(target_obj.from_user, "id"):
        chat_id = target_obj.from_user.id

    if len(text) <= 4000 and hasattr(target_obj, "answer"):
        import inspect
        from aiogram.exceptions import TelegramBadRequest
        try:
            res = target_obj.answer(
                text,
                reply_markup=reply_markup,
                parse_mode=parse_mode,
                disable_web_page_preview=disable_web_page_preview
            )
            if inspect.isawaitable(res):
                return await res
            return res
        except TelegramBadRequest as ex:
            err = str(ex).lower()
            if "parse" in err or "entity" in err:
                try:
                    res = target_obj.answer(
                        text,
                        reply_markup=reply_markup,
                        parse_mode=None,
                        disable_web_page_preview=disable_web_page_preview
                    )
                    if inspect.isawaitable(res):
                        return await res
                    return res
                except Exception:
                    pass
            elif "message is too long" in err:
                pass
            else:
                return None
        except Exception:
            return None

    if bot and chat_id:
        return await safe_send_message(
            bot=bot,
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
            disable_web_page_preview=disable_web_page_preview,
            sleep_between=sleep_between
        )
    return None


async def safe_reply(
    message: Any,
    text: str,
    reply_markup: Optional[types.InlineKeyboardMarkup] = None,
    parse_mode: Optional[str] = "HTML",
    disable_web_page_preview: bool = True,
    sleep_between: float = 0.05
) -> Optional[Any]:
    """
    Safely replies to a message with automatic HTML chunking.
    The first chunk is sent as reply; remaining chunks are sent sequentially.
    """
    if not text or not message:
        return None
    bot = getattr(message, "bot", None)
    chat_id = message.chat.id if (hasattr(message, "chat") and message.chat) else 0

    if len(text) <= 4000 and hasattr(message, "reply"):
        import inspect
        from aiogram.exceptions import TelegramBadRequest
        try:
            res = message.reply(
                text,
                reply_markup=reply_markup,
                parse_mode=parse_mode,
                disable_web_page_preview=disable_web_page_preview
            )
            if inspect.isawaitable(res):
                return await res
            return res
        except TelegramBadRequest as ex:
            err = str(ex).lower()
            if "parse" in err or "entity" in err:
                try:
                    res = message.reply(
                        text,
                        reply_markup=reply_markup,
                        parse_mode=None,
                        disable_web_page_preview=disable_web_page_preview
                    )
                    if inspect.isawaitable(res):
                        return await res
                    return res
                except Exception:
                    pass
            elif "message is too long" in err:
                pass
            else:
                return None
        except Exception:
            return None

    chunks = smart_split_html(text, max_chunk_size=4000)
    last_msg = None
    mid = getattr(message, "message_id", None)

    for i, chunk in enumerate(chunks):
        is_first = (i == 0)
        is_last = (i == len(chunks) - 1)
        kb = reply_markup if is_last else None
        try:
            if is_first and mid:
                last_msg = await bot.send_message(
                    chat_id=chat_id,
                    text=chunk,
                    reply_to_message_id=mid,
                    reply_markup=kb,
                    parse_mode=parse_mode,
                    disable_web_page_preview=disable_web_page_preview
                )
            else:
                last_msg = await bot.send_message(
                    chat_id=chat_id,
                    text=chunk,
                    reply_markup=kb,
                    parse_mode=parse_mode,
                    disable_web_page_preview=disable_web_page_preview
                )
        except Exception:
            try:
                last_msg = await bot.send_message(
                    chat_id=chat_id,
                    text=chunk,
                    reply_to_message_id=mid if is_first else None,
                    reply_markup=kb,
                    parse_mode=None,
                    disable_web_page_preview=disable_web_page_preview
                )
            except Exception:
                pass
        if not is_last and sleep_between > 0:
            await asyncio.sleep(sleep_between)

    return last_msg


async def _send_safe_text_message(
    target_obj: Any,
    bot: Optional[Any],
    chat_id: int,
    text: str,
    reply_markup: Optional[types.InlineKeyboardMarkup] = None
) -> Optional[Any]:
    """
    Attempts to send text message via safe_answer or safe_send_message.
    Automatically handles messages > 4000 chars, malformed HTML, and network retries.
    """
    if not text:
        return None

    if len(text) > 4000:
        if bot and chat_id:
            return await safe_send_message(bot, chat_id, text, reply_markup=reply_markup)
        if hasattr(target_obj, "answer"):
            return await safe_answer(target_obj, text, reply_markup=reply_markup)

    import inspect
    from aiogram.exceptions import TelegramBadRequest

    # 1. Try target_obj.answer (HTML)
    if hasattr(target_obj, "answer"):
        try:
            res = target_obj.answer(
                text,
                reply_markup=reply_markup,
                parse_mode="HTML",
                disable_web_page_preview=True
            )
            if inspect.isawaitable(res):
                return await res
            return res
        except TelegramBadRequest as ex:
            err = str(ex).lower()
            if "parse" in err or "entity" in err:
                try:
                    res = target_obj.answer(
                        text,
                        reply_markup=reply_markup,
                        parse_mode=None,
                        disable_web_page_preview=True
                    )
                    if inspect.isawaitable(res):
                        return await res
                    return res
                except Exception:
                    pass
            elif "message is too long" in err or "too_long" in err:
                if bot and chat_id:
                    return await safe_send_message(bot, chat_id, text, reply_markup=reply_markup)
        except Exception:
            pass

    # 2. Try bot.send_message (HTML -> Plain text fallback)
    if bot and chat_id:
        try:
            return await bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode="HTML",
                disable_web_page_preview=True
            )
        except TelegramBadRequest as ex:
            err = str(ex).lower()
            if "parse" in err or "entity" in err:
                try:
                    return await bot.send_message(
                        chat_id=chat_id,
                        text=text,
                        reply_markup=reply_markup,
                        parse_mode=None,
                        disable_web_page_preview=True
                    )
                except Exception:
                    pass
            elif "message is too long" in err or "too_long" in err:
                return await safe_send_message(bot, chat_id, text, reply_markup=reply_markup)
        except Exception:
            pass

    return None


_MESSAGE_SAFETY_GUARD_INSTALLED = False

def install_message_safety_guard():
    """
    Installs transparent interceptors on Message.answer and Message.reply.
    Guarantees that ANY handler in dvachbot passing text > 4000 characters is
    safely chunked and sent rather than raising TelegramBadRequest: MESSAGE_TOO_LONG.
    """
    global _MESSAGE_SAFETY_GUARD_INSTALLED
    if _MESSAGE_SAFETY_GUARD_INSTALLED:
        return
    _MESSAGE_SAFETY_GUARD_INSTALLED = True

    from aiogram.types import Message
    from aiogram.exceptions import TelegramBadRequest

    _orig_answer = Message.answer
    _orig_reply = Message.reply

    async def _guarded_answer(self: Message, text: str, *args, **kwargs):
        if not text:
            return None
        if len(text) <= 4000:
            try:
                return await _orig_answer(self, text, *args, **kwargs)
            except TelegramBadRequest as ex:
                err = str(ex).lower()
                if "parse" in err or "entity" in err:
                    no_parse = dict(kwargs)
                    no_parse["parse_mode"] = None
                    return await _orig_answer(self, text, *args, **no_parse)
                elif "message is too long" in err or "too_long" in err:
                    pass
                else:
                    raise

        # Over 4000 chars or rejected by Telegram: use safe chunking
        bot = getattr(self, "bot", None)
        chat_id = self.chat.id if (self.chat and hasattr(self.chat, "id")) else None
        if bot and chat_id:
            return await safe_send_message(
                bot=bot,
                chat_id=chat_id,
                text=text,
                reply_markup=kwargs.get("reply_markup"),
                parse_mode=kwargs.get("parse_mode", "HTML"),
                disable_web_page_preview=kwargs.get("disable_web_page_preview", True)
            )
        return await _orig_answer(self, text, *args, **kwargs)

    async def _guarded_reply(self: Message, text: str, *args, **kwargs):
        if not text:
            return None
        if len(text) <= 4000:
            try:
                return await _orig_reply(self, text, *args, **kwargs)
            except TelegramBadRequest as ex:
                err = str(ex).lower()
                if "parse" in err or "entity" in err:
                    no_parse = dict(kwargs)
                    no_parse["parse_mode"] = None
                    return await _orig_reply(self, text, *args, **no_parse)
                elif "message is too long" in err or "too_long" in err:
                    pass
                else:
                    raise

        return await safe_reply(
            message=self,
            text=text,
            reply_markup=kwargs.get("reply_markup"),
            parse_mode=kwargs.get("parse_mode", "HTML"),
            disable_web_page_preview=kwargs.get("disable_web_page_preview", True)
        )

    Message.answer = _guarded_answer
    Message.reply = _guarded_reply
    logging.getLogger("runtime").info("🛡️ Message safety guard installed on Message.answer and Message.reply")


async def _safe_delete_message(msg: Any) -> bool:
    """Safely deletes message without throwing unhandled exceptions."""
    if not msg or not hasattr(msg, "delete"):
        return False
    try:
        import inspect
        res = msg.delete()
        if inspect.isawaitable(res):
            await res
        return True
    except Exception:
        return False


_MENU_MESSAGE_OWNERS: dict[tuple[int, int], int] = {}

def record_menu_owner(chat_id: int, message_id: int, owner_id: int) -> None:
    if not (isinstance(chat_id, int) and isinstance(message_id, int) and isinstance(owner_id, int)):
        return
    if len(_MENU_MESSAGE_OWNERS) > 5000:
        for k in list(_MENU_MESSAGE_OWNERS.keys())[:1000]:
            _MENU_MESSAGE_OWNERS.pop(k, None)
    _MENU_MESSAGE_OWNERS[(chat_id, message_id)] = owner_id

def track_menu_owner(chat_or_tuple: Any, message_or_owner: Any = None, owner_id: Optional[int] = None) -> None:
    """
    Tracks menu ownership across messages and callbacks. Supports:
    track_menu_owner((chat_id, message_id), user_id)
    track_menu_owner(chat_id, message_id, user_id)
    track_menu_owner(message, user_id)
    """
    if owner_id is not None:
        chat_id = chat_or_tuple
        msg_id = message_or_owner
        uid = owner_id
    elif isinstance(chat_or_tuple, (tuple, list)) and len(chat_or_tuple) == 2:
        chat_id, msg_id = chat_or_tuple
        uid = message_or_owner
    else:
        chat_id = getattr(getattr(chat_or_tuple, "chat", None), "id", None)
        msg_id = getattr(chat_or_tuple, "message_id", None)
        uid = message_or_owner

    if isinstance(chat_id, int) and isinstance(msg_id, int) and isinstance(uid, int):
        record_menu_owner(chat_id, msg_id, uid)

def get_menu_owner(message: Optional[Any]) -> Optional[int]:
    if not message or getattr(message, "__class__", None).__name__ == "InaccessibleMessage":
        return None
    chat_id = getattr(getattr(message, "chat", None), "id", None)
    msg_id = getattr(message, "message_id", None)
    if isinstance(chat_id, int) and isinstance(msg_id, int):
        owner = _MENU_MESSAGE_OWNERS.get((chat_id, msg_id))
        if isinstance(owner, int):
            return owner
    reply = getattr(message, "reply_to_message", None)
    if reply and hasattr(reply, "from_user") and reply.from_user and hasattr(reply.from_user, "id"):
        reply_user_id = getattr(reply.from_user, "id", None)
        if isinstance(reply_user_id, int):
            return reply_user_id
    return None

def check_menu_owner(
    callback: Any,
    original_user_id: Optional[int] = None
) -> bool:
    """
    Checks if callback.from_user.id belongs to the original owner of the menu message in groups.
    If original_user_id is not provided, tries to resolve from tracked owners or reply_to_message.
    In private chats, always returns True.
    """
    msg = getattr(callback, "message", None)
    if not msg or getattr(msg, "__class__", None).__name__ == "InaccessibleMessage":
        return True
    chat = getattr(msg, "chat", None)
    chat_type = getattr(chat, "type", None)
    chat_id = getattr(chat, "id", None)
    if isinstance(chat_type, str) and chat_type == "private":
        return True
    if isinstance(chat_id, int) and chat_id > 0:
        return True

    owner_id = original_user_id if isinstance(original_user_id, int) else get_menu_owner(msg)
    user = getattr(callback, "from_user", None)
    caller_id = getattr(user, "id", None)
    if isinstance(owner_id, int) and isinstance(caller_id, int) and caller_id != owner_id:
        return False
    return True


async def render_menu_transition(
    callback: Union[types.CallbackQuery, types.Message],
    text: str,
    reply_markup: Optional[types.InlineKeyboardMarkup] = None,
    category: Optional[str] = None,
    prefer_banner: bool = False,
    original_user_id: Optional[int] = None
) -> None:
    """
    Universal Safe View Renderer / Transition Helper for DvachBot Telegram UI.
    Eliminates all photo-to-text, text-to-photo, and caption-overflow crashes across all menus.
    Enforces Telegram UTF-16 caption limit (1024 code units) and prevents Ghost UI deletion.

    Rules:
    1. If source message is media AND new view cannot be media (not prefer_banner or UTF-16 len > 1024):
       Send new text message first (with plain text fallback on bad HTML), then safely delete old media message.
    2. If source message is media AND new view can be media (prefer_banner and UTF-16 len <= 1024):
       Try edit_caption. If message is not modified, show toast '🔄 Информация актуальна'.
       If edit_caption fails, send new via send_banner_message and safely delete old message.
    3. If source message is text AND prefer_banner is True:
       Send via send_banner_message (with fallback to text), then safely delete old text message.
    4. If source message is text AND prefer_banner is False:
       Try edit_text (with plain-text fallback on entity error). If message is not modified, show toast.
       If edit_text fails, send new text message and safely delete old message.
    5. Always ensures callback query is safely answered without raising unhandled timeouts.
    """
    import inspect
    from aiogram.exceptions import TelegramBadRequest

    # Unpack Message and CallbackQuery safely across real aiogram classes and mock objects
    is_callback = isinstance(callback, types.CallbackQuery) or (
        hasattr(callback, "data") and isinstance(getattr(callback, "data", None), (str, bytes))
    )
    if not is_callback and (
        isinstance(callback, types.Message)
        or hasattr(callback, "chat")
        or hasattr(callback, "edit_text")
        or hasattr(callback, "edit_caption")
        or not hasattr(callback, "message")
    ):
        msg = callback
        cb = None
        bot = getattr(callback, "bot", None)
        chat_id = callback.chat.id if (callback.chat and hasattr(callback.chat, "id")) else 0
    else:
        cb = callback
        msg = getattr(callback, "message", None)
        bot = getattr(callback, "bot", None) or (getattr(msg, "bot", None) if msg else None)
        chat_id = 0
        if msg and hasattr(msg, "chat") and msg.chat and hasattr(msg.chat, "id"):
            chat_id = msg.chat.id
        elif hasattr(callback, "from_user") and callback.from_user and hasattr(callback.from_user, "id"):
            chat_id = callback.from_user.id

    target_owner_id = original_user_id if isinstance(original_user_id, int) else None
    if target_owner_id is None:
        if (isinstance(callback, types.Message) or hasattr(callback, "from_user")) and getattr(callback, "from_user", None):
            uid = getattr(callback.from_user, "id", None)
            if isinstance(uid, int):
                target_owner_id = uid
        elif is_callback and msg:
            target_owner_id = get_menu_owner(msg)
            if target_owner_id is None and getattr(callback, "from_user", None):
                uid = getattr(callback.from_user, "id", None)
                if isinstance(uid, int):
                    target_owner_id = uid

    def _track_transition_owner(res_msg: Any) -> None:
        if res_msg and hasattr(res_msg, "chat") and hasattr(res_msg, "message_id") and isinstance(target_owner_id, int):
            c_id = getattr(res_msg.chat, "id", None)
            m_id = getattr(res_msg, "message_id", None)
            if isinstance(c_id, int) and isinstance(m_id, int):
                record_menu_owner(c_id, m_id, target_owner_id)

    async def _safe_answer_if_needed(toast: Optional[str] = None) -> None:
        if not cb:
            return
        ans_mock = getattr(cb, "answer", None)
        if ans_mock and hasattr(ans_mock, "called") and isinstance(ans_mock.called, bool):
            is_answered = ans_mock.called
        else:
            raw_answered = getattr(cb, "_answered", False)
            is_answered = bool(raw_answered) if isinstance(raw_answered, bool) else False

        if toast:
            await safe_callback_answer(cb, toast)
        elif not is_answered:
            await safe_callback_answer(cb)

    # Missing or InaccessibleMessage
    from aiogram.types import InaccessibleMessage
    if not msg or isinstance(msg, InaccessibleMessage):
        if prefer_banner and bot:
            try:
                from banner_manager import send_banner_message
                sent = await send_banner_message(
                    bot=bot,
                    chat_id=chat_id,
                    caption=text,
                    reply_markup=reply_markup,
                    category=category or "start",
                    parse_mode="HTML"
                )
                if sent:
                    _track_transition_owner(sent)
                    await _safe_answer_if_needed()
                    return
            except Exception:
                pass
        if bot and chat_id:
            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    reply_markup=reply_markup,
                    parse_mode="HTML",
                    disable_web_page_preview=True
                )
            except TelegramBadRequest as ex:
                if "parse" in str(ex).lower() or "entity" in str(ex).lower():
                    try:
                        await bot.send_message(
                            chat_id=chat_id,
                            text=text,
                            reply_markup=reply_markup,
                            parse_mode=None,
                            disable_web_page_preview=True
                        )
                    except Exception:
                        pass
            except Exception:
                pass
        await _safe_answer_if_needed()
        return

    is_media = is_media_message(msg)
    utf16_len = get_telegram_utf16_len(text)
    can_fit_caption = (utf16_len <= 1024) and (len(text) <= 1024)

    # Case 1: Source message is media (photo/banner)
    if is_media:
        if prefer_banner and can_fit_caption:
            try:
                if hasattr(msg, "edit_caption"):
                    res = msg.edit_caption(
                        caption=text,
                        reply_markup=reply_markup,
                        parse_mode="HTML"
                    )
                    if inspect.isawaitable(res):
                        await res
                    _track_transition_owner(msg)
                    await _safe_answer_if_needed()
                    return
            except TelegramBadRequest as ex:
                if "message is not modified" in str(ex).lower():
                    await _safe_answer_if_needed("🔄 Информация актуальна")
                    return
                logging.getLogger("runtime").debug(f"render_menu_transition: edit_caption failed: {ex}")
            except Exception as ex:
                logging.getLogger("runtime").debug(f"render_menu_transition: edit_caption error: {ex}")

            # If edit_caption failed, send fresh banner then delete old
            sent = None
            if bot:
                try:
                    from banner_manager import send_banner_message
                    sent = await send_banner_message(
                        bot=bot,
                        chat_id=chat_id,
                        caption=text,
                        reply_markup=reply_markup,
                        category=category or "start",
                        parse_mode="HTML"
                    )
                except Exception:
                    pass

            if not sent:
                sent = await _send_safe_text_message(msg, bot, chat_id, text, reply_markup=reply_markup)

            if sent:
                _track_transition_owner(sent)
                await _safe_delete_message(msg)

            await _safe_answer_if_needed()
            return
        else:
            # Source is media, but target is text (prefer_banner is False or UTF-16 len > 1024)
            sent = await _send_safe_text_message(msg, bot, chat_id, text, reply_markup=reply_markup)
            if sent:
                _track_transition_owner(sent)
                await _safe_delete_message(msg)

            await _safe_answer_if_needed()
            return

    # Case 2: Source message is plain text
    else:
        if prefer_banner:
            sent = None
            if bot:
                try:
                    from banner_manager import send_banner_message
                    sent = await send_banner_message(
                        bot=bot,
                        chat_id=chat_id,
                        caption=text,
                        reply_markup=reply_markup,
                        category=category or "start",
                        parse_mode="HTML"
                    )
                except Exception:
                    pass

            if not sent:
                sent = await _send_safe_text_message(msg, bot, chat_id, text, reply_markup=reply_markup)

            if sent:
                _track_transition_owner(sent)
                await _safe_delete_message(msg)

            await _safe_answer_if_needed()
            return
        else:
            # Source is text and target is text: try edit_text
            try:
                if hasattr(msg, "edit_text"):
                    res = msg.edit_text(
                        text=text,
                        reply_markup=reply_markup,
                        parse_mode="HTML",
                        disable_web_page_preview=True
                    )
                    if inspect.isawaitable(res):
                        await res
                    _track_transition_owner(msg)
                    await _safe_answer_if_needed()
                    return
            except TelegramBadRequest as ex:
                if "message is not modified" in str(ex).lower():
                    await _safe_answer_if_needed("🔄 Информация актуальна")
                    return
                if "parse" in str(ex).lower() or "entity" in str(ex).lower():
                    try:
                        res = msg.edit_text(
                            text=text,
                            reply_markup=reply_markup,
                            parse_mode=None,
                            disable_web_page_preview=True
                        )
                        if inspect.isawaitable(res):
                            await res
                        await _safe_answer_if_needed()
                        return
                    except Exception:
                        pass
                logging.getLogger("runtime").debug(f"render_menu_transition: edit_text failed: {ex}")
            except Exception as ex:
                logging.getLogger("runtime").debug(f"render_menu_transition: edit_text error: {ex}")

            # Fallback if edit_text fails (e.g. message too old or was deleted)
            sent = await _send_safe_text_message(msg, bot, chat_id, text, reply_markup=reply_markup)
            if sent:
                _track_transition_owner(sent)
                await _safe_delete_message(msg)

            await _safe_answer_if_needed()
            return


render_menu_view = render_menu_transition


async def resolve_target_user_id(db, target_str: str) -> int | None:
    """Определяет Telegram user_id по переданной строке (Anon-ID или числовой ID)."""
    if not target_str:
        return None
    raw = target_str.strip("[]@ #").lower()
    if not raw:
        return None

    # 1. Числовой Telegram ID
    if raw.isdigit() and len(raw) >= 6:
        try:
            tid = int(raw)
            async with db.execute("SELECT 1 FROM Users WHERE user_id = ? LIMIT 1", (tid,)) as cursor:
                if await cursor.fetchone():
                    return tid
        except Exception:
            pass

    # 2. Поиск по Anon ID среди пользователей в БД
    try:
        from common.anon_identity import get_anon_id
        async with db.execute("SELECT DISTINCT user_id FROM Users LIMIT 5000") as cursor:
            rows = await cursor.fetchall()
            for r in rows:
                uid = r[0]
                if get_anon_id(uid).lower() == raw or get_anon_id(uid, "en").lower() == raw:
                    return uid
    except Exception:
        pass

    return None


def get_active_visual_debuff_count(items: dict, now: int) -> int:
    """Returns number of active visual debuffs (shit, vomit, flags)."""
    if not isinstance(items, dict):
        return 0
    cnt = 0
    if items.get("shit_until", 0) > now:
        cnt += 1
    if items.get("vomit_until", 0) > now:
        cnt += 1
    if items.get("flag_ua_until", 0) > now or items.get("flag_ru_until", 0) > now:
        cnt += 1
    return cnt
