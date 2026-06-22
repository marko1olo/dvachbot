import asyncio
from common.task_manager import spawn_task
import logging
import os
import sys
import time
from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter, TelegramForbiddenError, TelegramNetworkError
from dotenv import load_dotenv


load_dotenv()

def _load_bot_tokens():
    raw_tokens = os.getenv("COPY_BOT_TOKENS", "")
    tokens = [token.strip() for token in raw_tokens.split(",") if token.strip()]
    if not tokens:
        raise RuntimeError("COPY_BOT_TOKENS is not set. Use comma-separated bot tokens in .env.")
    return tokens


BOT_TOKENS = _load_bot_tokens()
# 2. Откуда и куда
SOURCE_CHANNEL_ID = -1003026863876  # ID Старого канала (или юзернейм "@tgach_archive")
TARGET_CHANNEL_ID = -1003549106152  # ID Нового канала (куда льем)

# 3. Диапазон постов (смотри ссылку: t.me/tgach_archive/154058)
START_ID = 154057   # С какого номера начать (последний живой пост)
COUNT = 10000       # Сколько постов отмотать назад (или вперед)

# 4. Направление
# True = Идем назад (154058 -> 154057 -> ...) - от новых к старым
# False = Идем вперед (154058 -> 154059 -> ...)
GO_BACKWARDS = True 

# Очередь задач
queue = asyncio.Queue()
stats = {'ok': 0, 'skip': 0, 'err': 0}

async def worker(bot_token, worker_id):
    """Один бот-работяга"""
    bot = Bot(token=bot_token)
    
    # Проверка бота
    try:
        me = await bot.get_me()
        print(f"🤖 Бот {worker_id} ({me.username}) готов к работе.")
    except Exception as e:
        print(f"❌ Бот {worker_id} сдох (неверный токен?): {e}")
        await bot.session.close()
        return

    while True:
        # Берем задачу из очереди
        msg_id = await queue.get()
        
        try:
            # Показываем, что работаем (перезаписываемая строка)
            sys.stdout.write(f"\r⏳ W-{worker_id} пробует ID: {msg_id} | OK: {stats['ok']} | Del: {stats['skip']}   ")
            sys.stdout.flush()

            await bot.copy_message(
                chat_id=TARGET_CHANNEL_ID,
                from_chat_id=SOURCE_CHANNEL_ID,
                message_id=msg_id
            )
            
            stats['ok'] += 1
            print(f"\n✅ [{msg_id}] Успех (Бот {worker_id})")
            
            # Пауза, чтобы канал не забанили за спам (даже с кучей ботов лучше не борщить)
            await asyncio.sleep(2) 

        except TelegramBadRequest:
            # Сообщение удалено или не существует
            stats['skip'] += 1
            # Не спамим в лог, просто счетчик крутится
            pass
            
        except TelegramRetryAfter as e:
            print(f"\n⏳ Бот {worker_id} словил лимит. Спит {e.retry_after} сек.")
            await asyncio.sleep(e.retry_after + 1)
            # Возвращаем задачу в очередь, чтобы её сделал другой бот или этот же позже
            await queue.put(msg_id) 
            queue.task_done()
            continue

        except TelegramForbiddenError:
            print(f"\n⛔ Бот {worker_id} не админ в канале! Выключаю его.")
            queue.task_done()
            break # Выход из воркера
            
        except Exception as e:
            print(f"\n❌ Ошибка ID {msg_id}: {e}")
            stats['err'] += 1

        # Сообщаем очереди, что задача сделана
        queue.task_done()
        
        # Микро-задержка для сети
        await asyncio.sleep(0.2)

    await bot.session.close()

async def main():
    print(f"🚀 Загрузка очереди...")
    
    # Заполняем очередь ID-шниками
    if GO_BACKWARDS:
        ids = range(START_ID, START_ID - COUNT, -1)
    else:
        ids = range(START_ID, START_ID + COUNT)
        
    for i in ids:
        if i > 0: queue.put_nowait(i)
        
    print(f"📦 В очереди {queue.qsize()} сообщений.")
    print(f"🤖 Запускаю {len(BOT_TOKENS)} ботов...")

    # Создаем воркеров
    tasks = []
    for i, token in enumerate(BOT_TOKENS):
        task = spawn_task(worker(token, i+1))
        tasks.append(task)

    # Ждем, пока очередь опустеет
    await queue.join()
    
    print("\n\n🏁 ВСЕ ЗАДАЧИ ВЫПОЛНЕНЫ.")
    print(f"Итог: ✅ {stats['ok']} | 🗑 {stats['skip']} | ❌ {stats['err']}")

    # Отменяем воркеров (они висят в бесконечном цикле)
    for task in tasks:
        task.cancel()

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Стоп.")
