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
import asyncio
import httpx
import os
from datetime import datetime, timedelta, UTC
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest, TelegramRetryAfter, TelegramAPIError
from common.anon_identity import get_anon_id
from common.database import add_user_global_balance, get_user_global_balance

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
                prefix = "[Продал мать]"
                expires = 2147483647
                
                await add_user_global_balance(db, user_id, board_id, 10000)
                await db.execute(
                    "UPDATE Users SET active_items = ?, custom_prefix = ?, prefix_expires_at = ? WHERE user_id = ? AND board_id = ?",
                    (json.dumps(active_items), prefix, expires, user_id, board_id)
                )
                await db.commit()
                ans_text = "💸 Сделка века! Ты продал мать и получил 10000 Шекелей. На тебя повешено клеймо."

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
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=data)
            if resp.status_code == 200:
                raw_json = resp.json()["choices"][0]["message"]["content"].strip()
                if raw_json.startswith("```"):
                    raw_json = raw_json.split("\n", 1)[-1]
                if raw_json.endswith("```"):
                    raw_json = raw_json.rsplit("\n", 1)[0]
                result = json.loads(raw_json)
                
        if not result:
            result = {"score": random.uniform(0.1, 0.9), "narrative": "ИИ-Судья отвалился, так что кидаю кубик. Ограбление как ограбление."}
            
        score = result.get("score", 0.0)
        narrative = result.get("narrative", "Что-то пошло не так.")
        
        db = await get_pool()
        
        if score > 0.7:
            stolen = 0
            async with db_lock:
                async with db.execute("SELECT balance FROM Users WHERE user_id = ? AND board_id = ?", (target_id, board_id)) as c:
                    row = await c.fetchone()
                    t_balance = row[0] if row and row[0] else 0
                
                if t_balance > 0:
                    stolen = min(int(t_balance * 0.4), 1500)
                    if stolen > 0:
                        await db.execute("UPDATE Users SET balance = MAX(0, balance - ?) WHERE user_id = ? AND board_id = ?", (stolen, target_id, board_id))
                        await db.execute("UPDATE Users SET balance = balance + ? WHERE user_id = ? AND board_id = ?", (stolen, user_id, board_id))
                        await db.commit()
            
            if stolen > 0:
                await message.reply(f"✅ **УСПЕХ! (Оценка ИИ: {int(score*100)}/100)**\n_{narrative}_\n\n💸 Ты виртуозно украл **{stolen}** шекелей!", parse_mode="Markdown")
            else:
                await message.reply(f"✅ **УСПЕХ! (Оценка ИИ: {int(score*100)}/100)**\n_{narrative}_\n\n💸 Но карманы жертвы оказались пусты. Ты украл ровно 0 шекелей.", parse_mode="Markdown")
        else:
            # Пативэн
            import __main__ as main_module
            await message.reply(f"❌ **ПРОВАЛ! (Оценка ИИ: {int(score*100)}/100)**\n_{narrative}_\n\n🚓 План оказался тупым. За тобой выехал Пативэн (мут на 3 часа)!", parse_mode="Markdown")
            if hasattr(main_module, 'apply_regular_mute'):
                await main_module.apply_regular_mute(user_id, board_id, int(time.time()) + 3*3600)
            
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
        async with db_lock:
            await db.execute("UPDATE Users SET active_items = ? WHERE user_id = ? AND board_id = ?",
                             (json.dumps(active_items), user_id, board_id))
            await db.commit()
        try: await message.bot.send_message(user_id, "🚔 Твой вызов ОМОНа отменили! У жертвы была надета Шапочка из фольги, они не смогли её запеленговать.", parse_mode="HTML")
        except Exception: pass
        try: await message.bot.send_message(target_id, f"👽 Анон <b>[{get_anon_id(user_id)}]</b> попытался вызвать на тебя Пативэн, но Шапочка из фольги скрыла твои координаты!", parse_mode="HTML")
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
        
    db = await get_pool()
    async with db.execute("SELECT active_items FROM Users WHERE user_id = ? AND board_id = ?", (user_id, board_id)) as c:
        row = await c.fetchone()
        active_items_str = row[0] if row and row[0] else "{}"
    try: active_items = json.loads(active_items_str)
    except Exception: active_items = {}
        
    if not active_items.get("knife_gun"):
        await message.reply("У тебя нет заточки! Купи её в /shop.")
        return
        
    active_items["knife_gun"] = False
    
    async with db.execute("SELECT balance, active_items FROM Users WHERE user_id = ? AND board_id = ?", (target_id, board_id)) as c:
        row = await c.fetchone()
        target_balance = row[0] if row and row[0] else 0
        target_items_str = row[1] if row and row[1] else "{}"
    try: target_items = json.loads(target_items_str)
    except Exception: target_items = {}
    
    now = int(time.time())
    if target_items.get("tinfoil_hat", 0) > now:
        # Tinfoil blocks the attack
        async with db_lock:
            await db.execute("UPDATE Users SET active_items = ? WHERE user_id = ? AND board_id = ?",
                             (json.dumps(active_items), user_id, board_id))
            await db.commit()
        try: await message.bot.send_message(user_id, "🔪 Твоя заточка сломалась о Шапочку из фольги жертвы! Ограбление не удалось.", parse_mode="HTML")
        except Exception: pass
        try: await message.bot.send_message(target_id, f"👽 Анон <b>[{get_anon_id(user_id)}]</b> попытался ограбить тебя, но твоя Шапочка из фольги спасла твои шекели!", parse_mode="HTML")
        except Exception: pass
        try: await message.delete()
        except Exception: pass
        return

    stolen = min(target_balance, random.randint(50, 300))
    if stolen <= 0:
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
        
    active_items["laxative_gun"] = False
    now = int(time.time())

    async with db.execute("SELECT active_items FROM Users WHERE user_id = ? AND board_id = ?", (target_id, board_id)) as c:
        row = await c.fetchone()
        target_items_str = row[0] if row and row[0] else "{}"
    try: target_items = json.loads(target_items_str)
    except Exception: target_items = {}

    if target_items.get("tinfoil_hat", 0) > now:
        async with db_lock:
            await db.execute("UPDATE Users SET active_items = ? WHERE user_id = ? AND board_id = ?",
                             (json.dumps(active_items), user_id, board_id))
            await db.commit()
        try: await message.bot.send_message(user_id, "🚽 Твоё проклятие отскочило от Шапочки из фольги жертвы! Своё слабительное ты потратил впустую.", parse_mode="HTML")
        except Exception: pass
        try: await message.bot.send_message(target_id, f"👽 Анон <b>[{get_anon_id(user_id)}]</b> попытался подсыпать тебе слабительное, но твоя Шапочка из фольги спасла твои штаны!", parse_mode="HTML")
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
        
    try: await message.bot.send_message(target_id, "🚽 Тебе подсыпали слабительное! В течение 1 часа ты не сможешь писать посты длиннее 50 символов (не успеешь дописать и побежишь в туалет).", parse_mode="HTML")
    except Exception: pass
    try: await message.bot.send_message(user_id, f"🚽 Ты успешно подсыпал слабительное Анону <b>[{get_anon_id(target_id)}]</b>!", parse_mode="HTML")
    except Exception: pass
    try: await message.delete()
    except Exception: pass

@economy_router.message(Command("mega"))
async def cmd_mega(message: types.Message, board_id: str | None = None):
    if not board_id: return
    user_id = message.from_user.id
    target_id = await get_reply_target(message)
    if not target_id:
        await message.reply("Сделай Reply на СВОЙ пост, который хочешь закрепить!")
        return
    if target_id != user_id:
        await message.reply("Мегафон работает только на свои собственные посты!")
        return
        
    db = await get_pool()
    async with db.execute("SELECT active_items FROM Users WHERE user_id = ? AND board_id = ?", (user_id, board_id)) as c:
        row = await c.fetchone()
        active_items_str = row[0] if row and row[0] else "{}"
    try: active_items = json.loads(active_items_str)
    except Exception: active_items = {}
        
    if not active_items.get("megaphone_gun"):
        await message.reply("У тебя нет рупора! Купи его в /shop.")
        return
        
    active_items["megaphone_gun"] = False
    
    # Try to pin the message
    try:
        await message.bot.pin_chat_message(message.chat.id, message.reply_to_message.message_id)
        alert = "📣 Твой пост успешно закреплен с помощью Мегафона!"
    except Exception as e:
        alert = f"❌ Ошибка закрепления: {e}"
        active_items["megaphone_gun"] = True # Refund
    
    async with db_lock:
        await db.execute("UPDATE Users SET active_items = ? WHERE user_id = ? AND board_id = ?",
                         (json.dumps(active_items), user_id, board_id))
        await db.commit()
        
    try: await message.bot.send_message(user_id, alert, parse_mode="HTML")
    except Exception: pass
    
    if "успешно" in alert:
        try:
            await message.bot.send_message(
                message.chat.id, 
                "📣 <b>ВНИМАНИЕ!</b> Кто-то из анонов проплатил закрепление поста через Мегафон!", 
                reply_to_message_id=message.reply_to_message.message_id, 
                parse_mode="HTML"
            )
        except Exception: pass
        
    try: await message.delete()
    except Exception: pass

