"""
ВНИМАНИЕ: пять обработчиков этого модуля НЕДОСТИЖИМЫ.

/rob, /curse, /mega, /partyvan и /shit объявлены ещё и в main.py прямо на
dp. Обработчики самого Dispatcher разрешаются РАНЬШЕ включённых
под-роутеров, причём независимо от порядка include_router (проверено
прогоном feed_update в обе стороны). Значит работают версии из main.py, а
эти пять не вызываются никогда.

Читающему: правка здесь НЕ ПОПАДЁТ В ПРОД. Я на этом уже обжёгся -
закрывал в cmd_rob гонку с уходом баланса жертвы в минус (коммиты 0071cbc
и 2f075c1), тесты зеленели, а в работающем коде гонка оставалась
открытой ещё двое суток. Живую версию пришлось править отдельно (f70efec).

Хуже того, тесты усиливают иллюзию: tests/test_economy_rob.py,
tests/test_economy_extension.py и tests/test_economy_curse.py импортируют
cmd_rob и cmd_curse ИМЕННО ОТСЮДА. Они проходят, ничего не проверяя в
реальном пути исполнения.

Разбор пяти пар показал, что версии из main.py не просто «текущие», а
более правильные:
  /curse    здесь проклятие пишется в КОЛОНКУ cursed_until, а эффект
            читается из JSON active_items (main.py:3743, 19880) - то есть
            даже будь этот код живым, проклятие не действовало бы
  /shit     при отскоке в базу пишется перечитанный target_items, а
            active_items со снятым shit_gun отбрасывается: предмет НЕ
            расходуется, кидать можно бесконечно
  /mega     pin_chat_message закрепляет в ЛИЧНОМ чате вызвавшего, то есть
            для одного человека; живая версия ставит active_pin на всю
            доску
  /partyvan нет проверки «цель уже в КПЗ надолго» и объявления на доску
  /rob      после переноса защиты равносильны

Что здесь есть ценного и чего нет в живых версиях: message.delete() -
убрать саму команду из чата, что для анонимной доски уместно; проверка
шапочки из фольги в /curse и /partyvan (в живых она есть только у /rob и
/shit); шанс отскока 20% в /shit. Это предложения, а не сделанное.

Живыми в этом модуле остаются только cmd_work_menu (/work, /earn, /bomj,
/job, /economy) и cb_work_action - они в main.py не дублируются.

Состояние отслеживается проверкой handlers в tools/selfcheck.py.
"""

import json
import time
import random
import re
import asyncio
import httpx
import os
import logging

logger = logging.getLogger(__name__)

from datetime import datetime, timedelta, UTC
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest, TelegramRetryAfter, TelegramAPIError
from common.anon_identity import get_anon_id
from common.database import record_user_transaction, add_user_global_balance, get_user_global_balance, deduct_user_global_balance

from common.db_pool import get_pool, db_lock

economy_router = Router()

async def _purge_blocked_user(user_id: int, board_id: str | None = None):
    if not board_id:
        return
    try:
        import __main__ as main
        if hasattr(main, 'purge_users_from_board_ram'):
            await main.purge_users_from_board_ram(board_id, [user_id])
    except Exception:
        pass


def apply_tinfoil_damage(
    target_items: dict,
    now: int,
    hours_damage: float = 6.0,
    burn_chance: float = 0.0
) -> tuple[bool, int, int, int]:
    """
    Применяет урон по прочности Шапочки из фольги (tinfoil_hat).
    - target_items: dict активных предметов цели (мутируется на месте).
    - now: текущее unix-время (int).
    - hours_damage: сколько часов прочности срезается за удар.
    - burn_chance: вероятность (0.0..1.0) мгновенного сгорания/разрушения шапочки.
    
    Возвращает кортеж: (destroyed: bool, left_hours: int, left_mins: int, remaining_seconds: int)
    """
    hat_until = target_items.get("tinfoil_hat", 0)
    if hat_until <= now:
        target_items.pop("tinfoil_hat", None)
        return True, 0, 0, 0

    current_remaining = hat_until - now
    damage_sec = int(hours_damage * 3600)
    
    is_burned = False
    if burn_chance > 0.0 and random.random() < burn_chance:
        is_burned = True
        
    new_remaining = current_remaining - damage_sec
    if is_burned or new_remaining <= 0:
        target_items.pop("tinfoil_hat", None)
        return True, 0, 0, 0
    else:
        target_items["tinfoil_hat"] = now + new_remaining
        left_h = new_remaining // 3600
        left_m = (new_remaining % 3600) // 60
        return False, left_h, left_m, new_remaining


# ====================
# EARN MENU
# ====================

@economy_router.message(Command("earn", "bomj", "economy"))
async def cmd_work_menu(message: types.Message, board_id: str | None = None):
    if not board_id:
        return
    
    text = (
        "🛠️ <b>Биржа Труда (Заработок)</b>\n\n"
        "Выбери способ заработать Шекели:\n"
        "1. 🍾 <b>Сдать стеклотару</b> — <i>10-50 Шек (Раз в 24 часа)</i>\n"
        "2. 👩‍👦 <b>Продать мать</b> — <i>10000 Шек (Разово, дает вечное клеймо)</i>\n"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🍾 Сдать бутылки", callback_data="work_bottles")],
        [InlineKeyboardButton(text="👩‍👦 Продать мать", callback_data="work_sell_mother")]
    ])
    
    await message.reply(text, reply_markup=kb, parse_mode="HTML")
    try: await message.delete()
    except (TelegramBadRequest, TelegramForbiddenError, TelegramAPIError, Exception): pass

@economy_router.callback_query(F.data.in_({"work_bottles", "work_sell_mother"}))
async def cb_work_action(callback: types.CallbackQuery, board_id: str | None = None):
    if not board_id: return
    user_id = callback.from_user.id
    action = callback.data.split("_", 1)[1]
    
    ans_text = ""
    db = await get_pool()
    async with db_lock:
        async with db.execute("SELECT active_items FROM Users WHERE user_id = ? AND board_id = ?", (user_id, board_id)) as c:
            row = await c.fetchone()
            active_items_str = row[0] if row and row[0] else "{}"
        try:
            active_items = json.loads(active_items_str)
        except (json.JSONDecodeError, TypeError):
            active_items = {}
    
        if action == "bottles":
            now = int(time.time())
            last_bottles = active_items.get("last_bottles", 0)
            if now - last_bottles < 86400:
                left = 86400 - (now - last_bottles)
                hours = left // 3600
                mins = (left % 3600) // 60
                ans_text = f"❌ Пункты приема закрыты! Приходи через {hours} ч {mins} мин."
            else:
                earned = random.randint(10, 50)
                active_items["last_bottles"] = now
                
                await add_user_global_balance(db, user_id, board_id, earned)
                await db.execute(
                    "UPDATE Users SET active_items = ? WHERE user_id = ? AND board_id = ?",
                    (json.dumps(active_items), user_id, board_id)
                )
                await db.commit()
                ans_text = f"🍾 Ты успешно сдал бутылки у теплотрассы и заработал {earned} Шекелей!"
    
        elif action == "sell_mother":
            if active_items.get("mother_sold"):
                ans_text = "❌ Ты уже продал мать. Второй раз не получится."
            else:
                active_items["mother_sold"] = True
                await add_user_global_balance(db, user_id, board_id, 8000)
                await record_user_transaction(db, user_id, 8000, 'work', 'Продал мать на органы')
                await db.execute(
                    "UPDATE Users SET active_items = ? WHERE user_id = ? AND board_id = ?",
                    (json.dumps(active_items), user_id, board_id)
                )
                await db.commit()
                ans_text = "💸 Сделка века! Ты продал мать и получил 8000 Шекелей! Клеймо занесено в твоё Личное Дело и Паспорт."

    if ans_text:
        await callback.answer(ans_text, show_alert=True)

# ====================
# INTERACTIVE COMMANDS
# ====================

async def get_reply_target(message: types.Message):
    if not message.reply_to_message:
        return None
    try:
        db = await get_pool()
        async with db.execute(
            "SELECT author_id FROM PostCopies JOIN Posts ON PostCopies.post_num = Posts.post_num WHERE recipient_id = ? AND message_id = ?",
            (message.chat.id, message.reply_to_message.message_id)
        ) as c:
            row = await c.fetchone()
            if row:
                return row[0]
    except Exception:
        pass
    return None

# ====================
# HEIST (AI ОГРАБЛЕНИЕ)
# ====================
@economy_router.message(Command("heist"))
async def cmd_heist(message: types.Message, board_id: str | None = None):
    raw_text = message.text or message.caption or ""
    parts = raw_text.split(maxsplit=1)
    if len(parts) < 2:
        await message.reply("⚠️ Использование: /heist [как именно ты грабишь].\nПример: /heist Я спускаюсь с потолка на тросе и краду его кошелек, пока он спит.")
        return
        
    plan = parts[1]
    user_id = message.from_user.id
    target_message = message.reply_to_message
    if not target_message:
        await message.reply("❌ Сделай Reply на сообщение того, кого хочешь ограбить.")
        return
        
    target_id = None
    try:
        from post_helpers import get_reply_target
        target_id = await get_reply_target(message)
    except Exception:
        pass
        
    if not target_id or target_id == user_id:
        await message.reply("❌ Нельзя ограбить самого себя (или цель не найдена).")
        return

    # Запрашиваем оценку у AI
    await message.reply("🤖 <i>Отправляем твой гениальный план ИИ-Судье...</i>", parse_mode="HTML")
    
    try:
        from common.token_pool import groq_pool
        prompt = (
            "Ты — строгий, саркастичный и смешной ИИ-судья анонимной имиджборды. Игрок пытается ограбить другого игрока.\n"
            f"План ограбления: '{plan}'\n"
            "Оцени креативность, логику, абсурд и юмор плана. Строго верни чистый JSON без markdown (без ```json), с полями:\n"
            '{"score": число от 0.0 до 1.0, "narrative": "Твой саркастичный комментарий на 2 предложения о том, как всё прошло."}'
        )
        
        import json
        import httpx
        
        token = groq_pool.get_token() or os.getenv("GROQ_API_KEY")
        if not token:
            await message.reply("❌ API ключ ИИ не найден.")
            return
            
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        data = {
            "model": "llama-3.3-70b-versatile",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 200,
            "temperature": 0.8
        }
        
        result = None
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=data)
                if resp.status_code == 200:
                    raw_json = resp.json()["choices"][0]["message"]["content"].strip()
                    if "<think>" in raw_json:
                        raw_json = re.sub(r'<think>.*?</think>', '', raw_json, flags=re.DOTALL).strip()
                    if "```" in raw_json:
                        match = re.search(r"```(?:json)?(.*?)```", raw_json, re.DOTALL)
                        if match:
                            raw_json = match.group(1).strip()
                    json_match = re.search(r"\{.*\}", raw_json, re.DOTALL)
                    if json_match:
                        raw_json = json_match.group(0).strip()
                    result = json.loads(raw_json)
        except Exception as e:
            logger.warning(f"⚠️ [Economy] Groq rob judge request failed: {e}")
                
        if not result:
            result = {"score": random.uniform(0.1, 0.9), "narrative": "ИИ-Судья отвалился, так что кидаю кубик. Ограбление как ограбление."}
            
        score = result.get("score", 0.0)
        narrative = result.get("narrative", "Что-то пошло не так.")
        
        db = await get_pool()
        
        if score > 0.7:
            stolen = 0
            async with db_lock:
                t_balance = await get_user_global_balance(db, target_id)
                if t_balance > 0:
                    stolen = min(int(t_balance * 0.4), 1500)
                    if stolen > 0:
                        ok, _ = await deduct_user_global_balance(db, target_id, board_id, stolen)
                        if ok:
                            await add_user_global_balance(db, user_id, board_id, stolen)
                            await db.commit()
                        else:
                            stolen = 0
            
            if stolen > 0:
                await message.reply(f"✅ **УСПЕХ! (Оценка ИИ: {int(score*100)}/100)**\n_{narrative}_\n\n💸 Ты виртуозно украл **{stolen}** шекелей!", parse_mode="Markdown")
            else:
                await message.reply(f"✅ **УСПЕХ! (Оценка ИИ: {int(score*100)}/100)**\n_{narrative}_\n\n💸 Но карманы жертвы оказались пусты. Ты украл ровно 0 шекелей.", parse_mode="Markdown")
        else:
            # Пативэн
            import __main__ as main_module
            await message.reply(f"❌ **ПРОВАЛ! (Оценка ИИ: {int(score*100)}/100)**\n_{narrative}_\n\n🚓 План оказался тупым. За тобой выехал Пативэн (мут на 3 часа)!", parse_mode="Markdown")
            if hasattr(main_module, 'apply_regular_mute'):
                await main_module.apply_regular_mute(user_id, board_id, 3 * 3600)
            
    except Exception as e:
        await message.reply(f"❌ Ошибка ИИ при ограблении: {e}")


@economy_router.message(Command("partyvan"))
async def cmd_partyvan(message: types.Message, board_id: str | None = None):
    if not board_id: return
    user_id = message.from_user.id
    target_id = await get_reply_target(message)
    if not target_id:
        await message.reply("Нужно сделать Reply на пост того, за кем высылаем Пативэн!")
        return
    if target_id == user_id:
        await message.reply("Нельзя вызвать Пативэн на самого себя, шиз.")
        return
        
    db = await get_pool()
    async with db.execute("SELECT active_items FROM Users WHERE user_id = ? AND board_id = ?", (user_id, board_id)) as c:
        row = await c.fetchone()
        active_items_str = row[0] if row and row[0] else "{}"
    try:
        active_items = json.loads(active_items_str)
    except Exception:
        active_items = {}
        
    if not active_items.get("partyvan_gun"):
        await message.reply("У тебя нет доступа к вызову Пативэна! Купи его в /shop.")
        return

    from shared_state import count_active_attacker_effects, register_attacker_effect
    # Защита от спама: максимум 2 активных вызова ОМОНа от одного автора
    if count_active_attacker_effects("partyvan_gun", user_id) >= 2:
        await message.reply(
            "🚔 <b>Лимит активных вызовов!</b>\n"
            "По твоим доносам уже отбывают срок 2 анона в КПЗ.\n"
            "Подожди освобождения хотя бы одного, прежде чем вызывать новый пативэн.\n"
            "Рация осталась в твоем рюкзаке.",
            parse_mode="HTML"
        )
        return

    # Защита от спама дебаффами: на аноне может быть только 1 активный дебафф (кроме говна)
    try:
        import main
        is_neut_fn = getattr(main, 'is_target_neutralized', None)
        if is_neut_fn:
            is_neut, reason = await is_neut_fn(target_id, board_id, db)
            if is_neut:
                await message.reply(
                    f"🚔 <b>Вызов отменен:</b> Эта цель УЖЕ {reason}!\n"
                    f"ОМОН не выезжает по лежачим анонам (макс. 1 активный дебафф).\n"
                    f"Рация осталась в твоем рюкзаке.",
                    parse_mode="HTML"
                )
                return
    except Exception:
        pass
        
    now = int(time.time())
    async with db.execute("SELECT active_items FROM Users WHERE user_id = ? AND board_id = ?", (target_id, board_id)) as c:
        row = await c.fetchone()
        target_items_str = row[0] if row and row[0] else "{}"
    try:
        target_items = json.loads(target_items_str)
    except Exception:
        target_items = {}

    if target_items.get("tinfoil_hat", 0) > now:
        active_items["partyvan_gun"] = False
        destroyed, left_h, left_m, _ = apply_tinfoil_damage(target_items, now, hours_damage=12.0, burn_chance=0.50)
        async with db_lock:
            await db.execute("UPDATE Users SET active_items = ? WHERE user_id = ? AND board_id = ?",
                             (json.dumps(active_items), user_id, board_id))
            await db.execute("UPDATE Users SET active_items = ? WHERE user_id = ? AND board_id = ?",
                             (json.dumps(target_items), target_id, board_id))
            await db.commit()
        
        if destroyed:
            attacker_msg = "🚔 Твой вызов ОМОНа отбит, но Шапочка из фольги жертвы <b>СГОРЕЛА ДОТЛА</b> от штурма спецназа! Защиты больше нет — цель открыта для повторной атаки!"
            target_msg = f"🔥 <b>ШАПОЧКА СГОРЕЛА!</b> Анон <b>[{get_anon_id(user_id)}]</b> попытался вызвать на тебя Пативэн, но Шапочка спасла тебя от КПЗ и <b>расплавилась дотла</b>! Ты остался <b>БЕЗ ЗАЩИТЫ</b>!"
        else:
            attacker_msg = f"🚔 Твой вызов ОМОНа отбит Шапочкой из фольги! Но от мощного штурма её прочность упала на 12ч (осталось {left_h}ч {left_m}мин)."
            target_msg = f"👽 Анон <b>[{get_anon_id(user_id)}]</b> попытался вызвать на тебя Пативэн, но Шапочка из фольги скрыла твои координаты! Она потеряла 12ч защиты (осталось {left_h}ч {left_m}мин)."

        try: await message.bot.send_message(user_id, attacker_msg, parse_mode="HTML")
        except Exception: pass
        try: await message.bot.send_message(target_id, target_msg, parse_mode="HTML")
        except Exception: pass
        try: await message.delete()
        except Exception: pass
        return
        
    active_items["partyvan_gun"] = False
    
    try:
        import main
        apply_regular_mute = getattr(main, 'apply_regular_mute', None)
        board_data = getattr(main, 'board_data', None)
        storage_lock = getattr(main, 'storage_lock', None)
        if storage_lock and board_data is not None:
            async with storage_lock:
                if board_id in board_data and 'mutes' in board_data[board_id]:
                    board_data[board_id]['mutes'][target_id] = datetime.now(UTC) + timedelta(seconds=12*3600)
        if apply_regular_mute:
            await apply_regular_mute(target_id, board_id, 12*3600)
    except Exception:
        pass
    
    async with db_lock:
        await db.execute("UPDATE Users SET active_items = ? WHERE user_id = ? AND board_id = ?",
                         (json.dumps(active_items), user_id, board_id))
        await db.commit()
    register_attacker_effect("partyvan_gun", user_id, target_id, 12 * 3600)
        
    try:
        await message.bot.send_message(
            target_id, 
            "🚔 <b>ВНИМАНИЕ! РАБОТАЕТ ОМОН!</b>\nЗа тобой выехал Пативэн (вызван кем-то из анонов).\nТы запакован в бобик и улетаешь в мут на 12 часов.", 
            parse_mode="HTML"
        )
    except Exception: pass
    try:
        await message.bot.send_message(
            user_id, 
            f"🚔 Пативэн успешно выслан за аноном <code>{target_id}</code>!", 
            parse_mode="HTML"
        )
    except Exception: pass
    try:
        await message.delete()
    except Exception:
        pass

@economy_router.message(Command("shit"))
async def cmd_shit(message: types.Message, board_id: str | None = None):
    if not board_id: return
    user_id = message.from_user.id
    target_id = await get_reply_target(message)
    if not target_id:
        await message.reply("Нужно сделать Reply на пост жертвы!")
        return
    if target_id == user_id:
        await message.reply("Ты и так говно.")
        return
        
    db = await get_pool()
    async with db.execute("SELECT active_items FROM Users WHERE user_id = ? AND board_id = ?", (user_id, board_id)) as c:
        row = await c.fetchone()
        active_items_str = row[0] if row and row[0] else "{}"
    try:
        active_items = json.loads(active_items_str)
    except Exception:
        active_items = {}
        
    if not active_items.get("shit_gun"):
        await message.reply("У тебя нет говна в карманах! Купи его в /shop.")
        return

    from shared_state import count_active_attacker_effects, register_attacker_effect
    # Защита от спама: максимум 2 активных обмазанных жертвы от одного автора
    if count_active_attacker_effects("shit_gun", user_id) >= 2:
        await message.reply(
            "🐒 <b>Лимит активных бросков!</b>\n"
            "Ты уже обмазал говном 2 анонов одновременно.\n"
            "Подожди, пока хотя бы один отмоется, прежде чем кидать снова.\n"
            "Кусок говна остался в твоих карманах.",
            parse_mode="HTML"
        )
        return
        
    active_items["shit_gun"] = False
    now = int(time.time())
    
    async with db.execute("SELECT active_items FROM Users WHERE user_id = ? AND board_id = ?", (target_id, board_id)) as c:
        row = await c.fetchone()
        target_items_str = row[0] if row and row[0] else "{}"
    try:
        target_items = json.loads(target_items_str)
    except Exception:
        target_items = {}

    if target_items.get("tinfoil_hat", 0) > now:
        # Bounce 100% due to tinfoil
        bounce = True
    else:
        bounce = random.random() < 0.20
    
    final_target = user_id if bounce else target_id
    
    async with db.execute("SELECT active_items FROM Users WHERE user_id = ? AND board_id = ?", (final_target, board_id)) as c:
        row = await c.fetchone()
        final_items_str = row[0] if row and row[0] else "{}"
    try:
        final_items = json.loads(final_items_str)
    except Exception:
        final_items = {}
        
    final_items["shit_until"] = int(time.time()) + 3600
    
    async with db_lock:
        if bounce:
            final_items["shit_gun"] = False # they consume the item when throwing
            await db.execute("UPDATE Users SET active_items = ? WHERE user_id = ? AND board_id = ?",
                             (json.dumps(final_items), user_id, board_id))
        else:
            await db.execute("UPDATE Users SET active_items = ? WHERE user_id = ? AND board_id = ?",
                             (json.dumps(active_items), user_id, board_id))
            await db.execute("UPDATE Users SET active_items = ? WHERE user_id = ? AND board_id = ?",
                             (json.dumps(final_items), target_id, board_id))
        await db.commit()
    register_attacker_effect("shit_gun", user_id, final_target, 3600)
        
    if bounce:
        try:
            await message.bot.send_message(
                user_id, 
                "🐒 Ты попытался метнуть говно, но ветер дунул в лицо! Ты сам обмазан говном на час 💩", 
                parse_mode="HTML"
            )
        except Exception: pass
    else:
        try:
            await message.bot.send_message(
                target_id, 
                "🐒 В тебя метнули кусок говна! Ты обмазан говном на час 💩", 
                parse_mode="HTML"
            )
        except Exception: pass
        try:
            await message.bot.send_message(
                user_id, 
                f"🐒 Ты успешно метнул кусок говна в <code>{target_id}</code>!", 
                parse_mode="HTML"
            )
        except Exception: pass
    try:
        await message.delete()
    except Exception:
        pass

@economy_router.message(Command("rob"))
async def cmd_rob(message: types.Message, board_id: str | None = None):
    if not board_id: return
    user_id = message.from_user.id
    target_id = await get_reply_target(message)
    if not target_id:
        await message.reply("Нужно сделать Reply на пост жертвы!")
        return
    if target_id == user_id:
        await message.reply("Нельзя ограбить самого себя.")
        return

    from shared_state import (
        get_target_grief_protection_remaining, register_target_attack, set_combat_cooldown
    )
    rem = get_target_grief_protection_remaining(target_id)
    if rem > 0:
        rem_min = rem // 60
        rem_sec = rem % 60
        time_str = f"{rem_min}м {rem_sec}с" if rem_min > 0 else f"{rem_sec}с"
        await message.reply(
            f"🛡️ <b>ИММУНИТЕТ ЦЕЛИ ОТ ГРИФЕРСТВА!</b>\n\n"
            f"Анон еще отходит от предыдущей разборки и находится под защитой борды.\n"
            f"Повторное нападение на этого анона возможно через <b>{time_str}</b>.\n"
            f"<i>(Заточка сохранена)</i>",
            parse_mode="HTML"
        )
        return
        
    db = await get_pool()
    async with db.execute("SELECT active_items FROM Users WHERE user_id = ? AND board_id = ?", (user_id, board_id)) as c:
        row = await c.fetchone()
        active_items_str = row[0] if row and row[0] else "{}"
    try: active_items = json.loads(active_items_str)
    except Exception: active_items = {}
        
    if not active_items.get("knife_gun"):
        await message.reply("У тебя нет заточки! Купи её в /shop.")
        return
        
    async with db.execute("SELECT balance, active_items FROM Users WHERE user_id = ? AND board_id = ?", (target_id, board_id)) as c:
        row = await c.fetchone()
        target_balance = row[0] if row and row[0] else 0
        target_items_str = row[1] if row and row[1] else "{}"
    try: target_items = json.loads(target_items_str)
    except Exception: target_items = {}

    if target_balance < 500:
        await message.reply(
            f"🛡️ <b>ЗАЩИТА НИЩИХ СЫЧЕЙ!</b>\n\n"
            f"У жертвы в карманах всего <code>{int(target_balance)} ₪</code> (меньше 500 ₪)!\n"
            f"Грабить нищих и опущенных сычей на ТГАЧе западло. Ты побрезговал марать руки, заточка осталась при тебе.",
            parse_mode="HTML"
        )
        return

    active_items["knife_gun"] = False
    register_target_attack(target_id)
    set_combat_cooldown(user_id, 180)
    
    now = int(time.time())
    if target_items.get("tinfoil_hat", 0) > now:
        # Tinfoil blocks the attack
        destroyed, left_h, left_m, _ = apply_tinfoil_damage(target_items, now, hours_damage=4.0, burn_chance=0.15)
        async with db_lock:
            await db.execute("UPDATE Users SET active_items = ? WHERE user_id = ? AND board_id = ?",
                             (json.dumps(active_items), user_id, board_id))
            await db.execute("UPDATE Users SET active_items = ? WHERE user_id = ? AND board_id = ?",
                             (json.dumps(target_items), target_id, board_id))
            await db.commit()
            
        if destroyed:
            attacker_msg = "🔪 Твоя заточка сломалась о Шапочку из фольги жертвы! Ограбление не удалось, но от твоего удара Шапочка жертвы <b>СГОРЕЛА ДОТЛА</b>!"
            target_msg = f"🔥 <b>ШАПОЧКА СГОРЕЛА!</b> Анон <b>[{get_anon_id(user_id)}]</b> попытался ограбить тебя, но твоя Шапочка из фольги спасла твои шекели! От удара она <b>была уничтожена</b>."
        else:
            attacker_msg = f"🔪 Твоя заточка сломалась о Шапочку из фольги жертвы! Ограбление не удалось. Фольга жертвы помялась (-4ч, осталось {left_h}ч {left_m}мин)."
            target_msg = f"👽 Анон <b>[{get_anon_id(user_id)}]</b> попытался ограбить тебя, но твоя Шапочка из фольги спасла твои шекели! Она потеряла 4ч прочности (осталось {left_h}ч {left_m}мин)."

        try: await message.bot.send_message(user_id, attacker_msg, parse_mode="HTML")
        except Exception: pass
        try: await message.bot.send_message(target_id, target_msg, parse_mode="HTML")
        except Exception: pass
        try: await message.delete()
        except Exception: pass
        return

    pct = random.uniform(0.1, 0.3)
    max_cap = 3000 if target_balance >= 10000 else (2000 if target_balance >= 5000 else 1000)
    stolen = min(target_balance, max(1, min(int(target_balance * pct), max_cap)))
    if target_balance <= 0:
        async with db_lock:
            await db.execute("UPDATE Users SET active_items = ? WHERE user_id = ? AND board_id = ?",
                             (json.dumps(active_items), user_id, board_id))
            await db.commit()
        try: await message.bot.send_message(user_id, "🔪 У жертвы нет шекелей! Ты зря потратил заточку.", parse_mode="HTML")
        except Exception: pass
        try: await message.delete()
        except Exception: pass
        return
        
    async with db_lock:
        cursor = await db.execute(
            "UPDATE Users SET balance = balance - ? WHERE user_id = ? AND board_id = ? AND balance >= ?",
            (stolen, target_id, board_id, stolen))
        rowcount = getattr(cursor, "rowcount", None)
        robbed = (rowcount == 1) if isinstance(rowcount, int) else True
        await db.execute("UPDATE Users SET balance = balance + ?, active_items = ? WHERE user_id = ? AND board_id = ?",
                         (stolen if robbed else 0, json.dumps(active_items), user_id, board_id))
        await db.commit()

    if not robbed:
        try: await message.bot.send_message(user_id, "🔪 Пока ты замахивался, у жертвы кончились шекели. Заточка потрачена впустую.", parse_mode="HTML")
        except Exception: pass
        try: await message.delete()
        except Exception: pass
        return

    try: await message.bot.send_message(target_id, f"🔪 В подворотне тебя пырнул Анон <b>[{get_anon_id(user_id)}]</b> и отобрал <b>{stolen} Шекелей</b>!", parse_mode="HTML")
    except Exception: pass
    try: await message.bot.send_message(user_id, f"🔪 Ограбление прошло успешно! Ты отжал у Анона <b>[{get_anon_id(target_id)}]</b> <b>{stolen} Шекелей</b>.", parse_mode="HTML")
    except Exception: pass
    try: await message.delete()
    except Exception: pass

@economy_router.message(Command("curse"))
async def cmd_curse(message: types.Message, board_id: str | None = None):
    if not board_id: return
    user_id = message.from_user.id
    target_id = await get_reply_target(message)
    if not target_id:
        await message.reply("Нужно сделать Reply на пост жертвы!")
        return
    if target_id == user_id:
        await message.reply("Сам себе слабительное?")
        return
        
    db = await get_pool()
    async with db.execute("SELECT active_items FROM Users WHERE user_id = ? AND board_id = ?", (user_id, board_id)) as c:
        row = await c.fetchone()
        active_items_str = row[0] if row and row[0] else "{}"
    try: active_items = json.loads(active_items_str)
    except Exception: active_items = {}
        
    if not active_items.get("laxative_gun"):
        await message.reply("У тебя нет слабительного! Купи его в /shop.")
        return

    from shared_state import count_active_attacker_effects, register_attacker_effect
    # Защита от спама: максимум 2 активных проклятия от одного автора
    if count_active_attacker_effects("laxative_gun", user_id) >= 2:
        await message.reply(
            "🚽 <b>Лимит активных проклятий!</b>\n"
            "Ты уже отравил слабительным 2 анонов одновременно.\n"
            "Подожди окончания действия эффекта у жертв, прежде чем подливать снова.\n"
            "Слабительное осталось в твоем рюкзаке.",
            parse_mode="HTML"
        )
        return

    # Защита от спама дебаффами: на аноне может быть только 1 активный дебафф (кроме говна)
    try:
        import main
        is_neut_fn = getattr(main, 'is_target_neutralized', None)
        if is_neut_fn:
            is_neut, reason = await is_neut_fn(target_id, board_id, db)
            if is_neut:
                await message.reply(
                    f"🚽 <b>Защита от спама:</b> У этой цели УЖЕ активен дебафф ({reason})!\n"
                    f"На аноне может быть только 1 активный дебафф (кроме броска говна).\n"
                    f"Слабительное осталось в твоем рюкзаке.",
                    parse_mode="HTML"
                )
                return
    except Exception:
        pass
        
    active_items["laxative_gun"] = False
    now = int(time.time())

    async with db.execute("SELECT active_items FROM Users WHERE user_id = ? AND board_id = ?", (target_id, board_id)) as c:
        row = await c.fetchone()
        target_items_str = row[0] if row and row[0] else "{}"
    try: target_items = json.loads(target_items_str)
    except Exception: target_items = {}

    if target_items.get("tinfoil_hat", 0) > now:
        destroyed, left_h, left_m, _ = apply_tinfoil_damage(target_items, now, hours_damage=4.0, burn_chance=0.10)
        async with db_lock:
            await db.execute("UPDATE Users SET active_items = ? WHERE user_id = ? AND board_id = ?",
                             (json.dumps(active_items), user_id, board_id))
            await db.execute("UPDATE Users SET active_items = ? WHERE user_id = ? AND board_id = ?",
                             (json.dumps(target_items), target_id, board_id))
            await db.commit()
            
        if destroyed:
            attacker_msg = "🚽 Твоё проклятие отскочило от Шапочки из фольги жертвы! Своё слабительное ты потратил впустую, но от едкой магии Шапочка жертвы <b>СГОРЕЛА ДОТЛА</b>!"
            target_msg = f"🔥 <b>ШАПОЧКА СГОРЕЛА!</b> Анон <b>[{get_anon_id(user_id)}]</b> попытался подсыпать тебе слабительное, но твоя Шапочка из фольги спасла твои штаны! От едкой химии она <b>расплавилась</b>!"
        else:
            attacker_msg = f"🚽 Твоё проклятие отскочило от Шапочки из фольги жертвы! Своё слабительное ты потратил впустую. Фольга жертвы потеряла 4ч (осталось {left_h}ч {left_m}мин)."
            target_msg = f"👽 Анон <b>[{get_anon_id(user_id)}]</b> попытался подсыпать тебе слабительное, но твоя Шапочка из фольги спасла твои штаны! Она потеряла 4ч прочности (осталось {left_h}ч {left_m}мин)."

        try: await message.bot.send_message(user_id, attacker_msg, parse_mode="HTML")
        except Exception: pass
        try: await message.bot.send_message(target_id, target_msg, parse_mode="HTML")
        except Exception: pass
        try: await message.delete()
        except Exception: pass
        return

    curse_until = now + 3600
    
    async with db_lock:
        await db.execute("UPDATE Users SET active_items = ? WHERE user_id = ? AND board_id = ?",
                         (json.dumps(active_items), user_id, board_id))
        try:
            await db.execute("UPDATE Users SET cursed_until = ? WHERE user_id = ? AND board_id = ?",
                             (curse_until, target_id, board_id))
        except Exception:
            pass
        await db.commit()
    register_attacker_effect("laxative_gun", user_id, target_id, 3600)
        
    try: await message.bot.send_message(target_id, "🚽 Тебе подсыпали слабительное! В течение 1 часа ты не сможешь писать посты длиннее 50 символов (не успеешь дописать и побежишь в туалет).", parse_mode="HTML")
    except Exception: pass
    try: await message.bot.send_message(user_id, f"🚽 Ты успешно подсыпал слабительное Анону <b>[{get_anon_id(target_id)}]</b>!", parse_mode="HTML")
    except Exception: pass
    try: await message.delete()
    except Exception: pass

@economy_router.message(Command("schizopill", "schizo_pill", "шизотаблетка", "шизопил"))
async def cmd_schizopill(message: types.Message, board_id: str | None = None):
    if not board_id: return
    user_id = message.from_user.id
    target_id = await get_reply_target(message)
    if not target_id:
        await message.reply("Сделай Reply на пост жертвы, чтобы скормить Шизо-Таблетку!")
        return
    if target_id == user_id:
        await message.reply("Ты пытаешься скормить таблетку самому себе.")
        return

    db = await get_pool()
    async with db.execute("SELECT active_items FROM Users WHERE user_id = ? AND board_id = ?", (user_id, board_id)) as c:
        row = await c.fetchone()
        active_items_str = row[0] if row and row[0] else "{}"
    try: active_items = json.loads(active_items_str)
    except Exception: active_items = {}

    if not active_items.get("schizopill_gun"):
        await message.reply("У тебя нет Шизо-Таблетки! Купи её в /shop.")
        return

    from shared_state import count_active_attacker_effects, register_attacker_effect
    if count_active_attacker_effects("schizopill_gun", user_id) >= 2:
        await message.reply(
            "💊 <b>Лимит активных шизо-проклятий!</b>\n"
            "Ты уже накачал таблетками 2 анонов одновременно.\n"
            "Подожди окончания действия эффекта у жертв, прежде чем скармливать новую.\n"
            "Шизо-Таблетка осталась в твоем рюкзаке.",
            parse_mode="HTML"
        )
        return

    try:
        import main
        is_neut_fn = getattr(main, 'is_target_neutralized', None)
        if is_neut_fn:
            is_neut, reason = await is_neut_fn(target_id, board_id, db)
            if is_neut:
                await message.reply(
                    f"💊 <b>Защита от спама:</b> У этой цели УЖЕ активен дебафф ({reason})!\n"
                    f"На аноне может быть только 1 активный дебафф (кроме броска говна).\n"
                    f"Шизо-Таблетка осталась в твоем рюкзаке.",
                    parse_mode="HTML"
                )
                return
    except Exception:
        pass

    active_items["schizopill_gun"] = False
    now = int(time.time())

    async with db.execute("SELECT active_items FROM Users WHERE user_id = ? AND board_id = ?", (target_id, board_id)) as c:
        row = await c.fetchone()
        target_items_str = row[0] if row and row[0] else "{}"
    try: target_items = json.loads(target_items_str)
    except Exception: target_items = {}

    if target_items.get("tinfoil_hat", 0) > now:
        destroyed, left_h, left_m, _ = apply_tinfoil_damage(target_items, now, hours_damage=4.0, burn_chance=0.10)
        async with db_lock:
            await db.execute("UPDATE Users SET active_items = ? WHERE user_id = ? AND board_id = ?",
                             (json.dumps(active_items), user_id, board_id))
            await db.execute("UPDATE Users SET active_items = ? WHERE user_id = ? AND board_id = ?",
                             (json.dumps(target_items), target_id, board_id))
            await db.commit()

        if destroyed:
            attacker_msg = "👽 Психотропное вещество отражено Шапочкой из фольги жертвы! Но от перегрузки Шапочка жертвы <b>СГОРЕЛА ДОТЛА</b>!"
            target_msg = f"🔥 <b>ШАПОЧКА СГОРЕЛА!</b> Анон <b>[{get_anon_id(user_id)}]</b> пытался скормить тебе Шизо-Таблетку! Шапочка спасла твой разум, но <b>расплавилась</b>!"
        else:
            attacker_msg = f"👽 Психотропное вещество отражено Шапочкой из фольги жертвы! Фольга потеряла 4ч (осталось {left_h}ч {left_m}мин)."
            target_msg = f"👽 Анон <b>[{get_anon_id(user_id)}]</b> пытался скормить тебе Шизо-Таблетку! Шапочка спасла твой разум, но потеряла 4ч прочности (осталось {left_h}ч {left_m}мин)."

        try: await message.bot.send_message(user_id, attacker_msg, parse_mode="HTML")
        except Exception: pass
        try: await message.bot.send_message(target_id, target_msg, parse_mode="HTML")
        except Exception: pass
        try: await message.delete()
        except Exception: pass
        return

    target_items["schizo_pill_until"] = now + 3600

    async with db_lock:
        await db.execute("UPDATE Users SET active_items = ? WHERE user_id = ? AND board_id = ?",
                         (json.dumps(active_items), user_id, board_id))
        await db.execute("UPDATE Users SET active_items = ? WHERE user_id = ? AND board_id = ?",
                         (json.dumps(target_items), target_id, board_id))
        await db.commit()
    register_attacker_effect("schizopill_gun", user_id, target_id, 3600)

    try: await message.bot.send_message(target_id, "💊 Тебе подмешали Шизо-Таблетку! В течение 1 часа нейросеть будет переписывать все твои посты в бред шизофреника!", parse_mode="HTML")
    except Exception: pass
    try: await message.bot.send_message(user_id, f"💊 Ты успешно накормил Шизо-Таблеткой Анона <b>[{get_anon_id(target_id)}]</b>!", parse_mode="HTML")
    except Exception: pass
    try: await message.delete()
    except Exception: pass

