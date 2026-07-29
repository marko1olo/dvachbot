"""
Тесты ЖИВОГО /partyvan - того обработчика, который бот действительно исполняет.

Функция берётся через tests/economy_live.live_handler, то есть по РЕГИСТРАЦИИ
на main.dp, а не импортом по имени: копии экономики в economy_extension.py
висят на economy_router и не вызываются никогда (Dispatcher разрешает свои
обработчики раньше включённых под-роутеров).

ГДЕ ЛЕЖИТ МУТ. В ДВУХ местах, и оба обязательны:
  - в памяти: main.board_data[board_id]['mutes'][user_id] - datetime с tz=UTC,
    именно его читает проверка идемпотентности самого /partyvan;
  - в БД: таблица Mutes, строка mute_type='mute' с expires_at (unix-время,
    float) - её пишет apply_regular_mute, а load_state_from_db
    (common/database.py:1030) заливает Mutes обратно в board_data при старте.
Расхождение между ними в рантайме незаметно и всплывает только после рестарта,
поэтому тесты успеха проверяют ОБА места и их согласованность.

СЕТИ ЗДЕСЬ НЕТ, и поэтому ничего не подменяется. В задании
common.database.apply_regular_mute значилась как «мут через сеть»; по коду
(common/database.py:4308-4346) это чистая работа с БД: DELETE + INSERT в Mutes
под db_lock, никаких вызовов Telegram API. db_lock и get_pool у неё - локальные
импорты внутри функции, то есть попадают под подмены economy_live, и мут
уезжает в временную БД. Мокать её означало бы потерять единственную настоящую
проверку эффекта команды, поэтому она исполняется как есть. Единственный
внешний вызов /partyvan - message.bot.send_message, а bot в оснастке уже
AsyncMock.

ЧТО ИЗОЛИРОВАНО РУКАМИ. board_data и storage_lock оснастка не изолирует, а
/partyvan мутирует board_data[board_id]['mutes'] - этим занят локальный
isolated_board() ниже. В economy_live.py его не добавляли: файл общий, а по
условию задачи править его нельзя.
"""

import asyncio
import contextlib
import json
import time
import unittest
from datetime import UTC, datetime, timedelta
from unittest import mock

from tests.economy_live import (BOARD, REPLY_CHAT_ID, REPLY_MESSAGE_ID,
                                live_economy, live_handler)
import main

SNITCH = 5001
TARGET = 5002
TWELVE_HOURS = 12 * 3600


@contextlib.asynccontextmanager
async def isolated_board():
    """Свежая запись board_data[BOARD] и свежий storage_lock на время теста.

    Менеджер асинхронный не потому, что внутри есть await, а чтобы его можно
    было ставить в один `async with` рядом с live_economy(): смешивать в одном
    операторе синхронный и асинхронный менеджеры Python не разрешает.

    board_data - defaultdict в main, общий на весь прогон pytest. Вернуть на
    место тот же объект недостаточно: мутация словаря 'mutes' уже внутри него.
    Поэтому подставляется НОВАЯ запись, созданная тем же default_factory
    (полный набор ключей, как в проде), а на выходе исходная возвращается либо
    удаляется, если её не было.

    storage_lock подменяется по той же причине, что db_lock в economy_live:
    asyncio.Lock привязывается к циклу, в котором его впервые ЖДУТ, а
    IsolatedAsyncioTestCase даёт каждому тесту свой цикл. Это страховка от
    состояния, оставленного другим тестовым файлом, а не обход дефекта бота -
    незанятый замок берётся быстрым путём, вообще не обращаясь к циклу.
    """
    fresh = main.board_data.default_factory()
    existed = BOARD in main.board_data
    saved = main.board_data.get(BOARD)
    main.board_data[BOARD] = fresh
    lock_patch = mock.patch.object(main, "storage_lock", asyncio.Lock())
    lock_patch.start()
    try:
        yield fresh
    finally:
        lock_patch.stop()
        if existed:
            main.board_data[BOARD] = saved
        else:
            main.board_data.pop(BOARD, None)


async def mute_rows(live, user_id: int) -> list[tuple]:
    """Строки Mutes из БД - половина мута, переживающая рестарт."""
    async with live.db.execute(
            "SELECT mute_type, expires_at FROM Mutes "
            "WHERE user_id = ? AND board_id = ?", (user_id, BOARD)) as cur:
        return list(await cur.fetchall())


class TestLivePartyvanHandler(unittest.IsolatedAsyncioTestCase):
    def test_registered_handler_is_the_live_one(self):
        """/partyvan обслуживает main.cmd_partyvan, и он на dp ровно один."""
        handler = live_handler("partyvan")
        self.assertEqual(handler.__name__, "cmd_partyvan")
        self.assertEqual(handler.__module__, "main")

    async def test_without_reply_nothing_is_touched(self):
        async with live_economy() as live, isolated_board() as board:
            await live.seed_user(SNITCH, 100.0, {"partyvan_gun": True})
            msg = live.message(SNITCH, with_reply=False)
            await live_handler("partyvan")(msg, BOARD)

            self.assertIn("Reply", " ".join(live.answers(msg)))
            self.assertTrue((await live.items_of(SNITCH))["partyvan_gun"])
            self.assertEqual(board["mutes"], {})

    async def test_without_radio_refuses(self):
        async with live_economy() as live, isolated_board() as board:
            await live.seed_user(SNITCH, 100.0, {})
            await live.seed_user(TARGET, 100.0, {})
            live.aim_at(TARGET)
            msg = live.message(SNITCH)
            await live_handler("partyvan")(msg, BOARD)

            self.assertIn("нет рации", " ".join(live.answers(msg)))
            # Ни в памяти, ни в БД мута не появилось.
            self.assertEqual(board["mutes"], {})
            self.assertEqual(await mute_rows(live, TARGET), [])

    async def test_snitching_on_self_keeps_the_radio(self):
        async with live_economy() as live, isolated_board() as board:
            await live.seed_user(SNITCH, 100.0, {"partyvan_gun": True})
            live.aim_at(SNITCH)
            msg = live.message(SNITCH)
            await live_handler("partyvan")(msg, BOARD)

            self.assertIn("Не удалось определить цель", " ".join(live.answers(msg)))
            self.assertTrue((await live.items_of(SNITCH))["partyvan_gun"])
            self.assertEqual(board["mutes"], {})
            self.assertEqual(await mute_rows(live, SNITCH), [])

    async def test_unaimable_reply_keeps_the_radio(self):
        """Reply есть, но автор поста не определяется - рация не расходуется.

        Ключ вычищается явно: оснастка возвращает message_to_post к тому, что
        было на входе в блок, но не гарантирует, что там пусто.
        """
        async with live_economy() as live, isolated_board() as board:
            await live.seed_user(SNITCH, 100.0, {"partyvan_gun": True})
            main.message_to_post.pop((REPLY_CHAT_ID, REPLY_MESSAGE_ID), None)
            msg = live.message(SNITCH)
            await live_handler("partyvan")(msg, BOARD)

            self.assertIn("Не удалось определить цель", " ".join(live.answers(msg)))
            self.assertTrue((await live.items_of(SNITCH))["partyvan_gun"])
            self.assertEqual(board["mutes"], {})

    async def test_target_already_in_kpz_keeps_the_radio(self):
        """Идемпотентность: на уже сидящего надолго вызов не тратится."""
        async with live_economy() as live, isolated_board() as board:
            existing = datetime.now(UTC) + timedelta(hours=12)
            await live.seed_user(SNITCH, 100.0, {"partyvan_gun": True})
            await live.seed_user(TARGET, 100.0, {})
            live.aim_at(TARGET)
            board["mutes"][TARGET] = existing
            msg = live.message(SNITCH)
            await live_handler("partyvan")(msg, BOARD)

            self.assertIn("УЖЕ откисает в КПЗ", " ".join(live.answers(msg)))
            self.assertTrue((await live.items_of(SNITCH))["partyvan_gun"])
            # Срок не продлён и в БД ничего не писалось.
            self.assertEqual(board["mutes"][TARGET], existing)
            self.assertEqual(await mute_rows(live, TARGET), [])
            msg.bot.send_message.assert_not_awaited()

    async def test_short_mute_does_not_block_the_partyvan(self):
        """Порог идемпотентности - 11 часов, а не «есть хоть какой-то мут».

        Сидящего час пативэн всё равно забирает и срок поднимается до 12 часов.
        """
        async with live_economy() as live, isolated_board() as board:
            short = datetime.now(UTC) + timedelta(hours=1)
            await live.seed_user(SNITCH, 100.0, {"partyvan_gun": True})
            await live.seed_user(TARGET, 100.0, {})
            live.aim_at(TARGET)
            board["mutes"][TARGET] = short
            msg = live.message(SNITCH)
            await live_handler("partyvan")(msg, BOARD)

            self.assertEqual(live.answers(msg), [])
            self.assertFalse((await live.items_of(SNITCH))["partyvan_gun"])
            self.assertGreater(board["mutes"][TARGET], short)
            self.assertEqual(len(await mute_rows(live, TARGET)), 1)

    async def test_mute_just_under_the_threshold_still_fires(self):
        """10 ч 50 мин < 11 ч - вызов проходит.

        Взято с запасом от границы: сравнение в обработчике идёт с его
        собственным datetime.now(UTC), который на микросекунды позже нашего.
        """
        async with live_economy() as live, isolated_board() as board:
            await live.seed_user(SNITCH, 100.0, {"partyvan_gun": True})
            await live.seed_user(TARGET, 100.0, {})
            live.aim_at(TARGET)
            board["mutes"][TARGET] = datetime.now(UTC) + timedelta(hours=10, minutes=50)
            await live_handler("partyvan")(live.message(SNITCH), BOARD)

            self.assertFalse((await live.items_of(SNITCH))["partyvan_gun"])
            self.assertEqual(len(await mute_rows(live, TARGET)), 1)

    async def test_mute_just_over_the_threshold_is_refused(self):
        """11 ч 10 мин > 11 ч - вызов отклонён, рация остаётся."""
        async with live_economy() as live, isolated_board() as board:
            await live.seed_user(SNITCH, 100.0, {"partyvan_gun": True})
            await live.seed_user(TARGET, 100.0, {})
            live.aim_at(TARGET)
            board["mutes"][TARGET] = datetime.now(UTC) + timedelta(hours=11, minutes=10)
            msg = live.message(SNITCH)
            await live_handler("partyvan")(msg, BOARD)

            self.assertIn("УЖЕ откисает в КПЗ", " ".join(live.answers(msg)))
            self.assertTrue((await live.items_of(SNITCH))["partyvan_gun"])
            self.assertEqual(await mute_rows(live, TARGET), [])

    async def test_successful_call_writes_memory_and_db_consistently(self):
        async with live_economy() as live, isolated_board() as board:
            await live.seed_user(SNITCH, 100.0, {"partyvan_gun": True})
            await live.seed_user(TARGET, 100.0, {})
            live.aim_at(TARGET)
            msg = live.message(SNITCH)
            before = time.time()
            await live_handler("partyvan")(msg, BOARD)

            # На успехе message.answer не вызывается вовсе: объявление уходит в
            # чат через bot.send_message, реплаем на пост-донос.
            self.assertEqual(live.answers(msg), [])
            # Рация израсходована.
            self.assertFalse((await live.items_of(SNITCH))["partyvan_gun"])

            # Память: 12 часов от «сейчас».
            memory_expires = board["mutes"][TARGET].timestamp()
            self.assertLessEqual(before + TWELVE_HOURS, memory_expires)
            self.assertLessEqual(memory_expires, before + TWELVE_HOURS + 5)

            # БД: ровно одна строка обычного мута с тем же сроком. Разъезд этих
            # двух значений виден только после рестарта, когда board_data
            # перестраивается из Mutes, - потому и проверяется согласованность.
            rows = await mute_rows(live, TARGET)
            self.assertEqual(len(rows), 1)
            mute_type, db_expires = rows[0]
            self.assertEqual(mute_type, "mute")
            self.assertLess(abs(db_expires - memory_expires), 5)

            # Объявление на доску - реплаем на пост жертвы.
            msg.bot.send_message.assert_awaited()
            self.assertEqual(
                msg.bot.send_message.await_args.kwargs["reply_to_message_id"],
                REPLY_MESSAGE_ID)

    async def test_second_partyvan_does_not_duplicate_db_rows(self):
        """Повторный вызов по той же цели отклоняется, дублей в Mutes нет.

        Проверяется сквозь состояние, оставленное первым вызовом, а не
        подготовленное руками: после первого пативэна цель уже сидит 12 часов,
        значит второй обязан упереться в идемпотентность.
        """
        async with live_economy() as live, isolated_board() as board:
            await live.seed_user(SNITCH, 100.0, {"partyvan_gun": True})
            await live.seed_user(TARGET, 100.0, {})
            live.aim_at(TARGET)
            partyvan = live_handler("partyvan")
            await partyvan(live.message(SNITCH), BOARD)

            # Вторая рация - чтобы отказ пришёл именно от проверки КПЗ, а не от
            # отсутствия предмета.
            await live.seed_user(SNITCH, 100.0, {"partyvan_gun": True})
            second = live.message(SNITCH)
            await partyvan(second, BOARD)

            self.assertIn("УЖЕ откисает в КПЗ", " ".join(live.answers(second)))
            self.assertTrue((await live.items_of(SNITCH))["partyvan_gun"])
            self.assertEqual(len(await mute_rows(live, TARGET)), 1)
            self.assertIn(TARGET, board["mutes"])

    async def test_partyvan_does_not_move_money(self):
        async with live_economy() as live, isolated_board():
            await live.seed_user(SNITCH, 100.0, {"partyvan_gun": True})
            await live.seed_user(TARGET, 200.0, {})
            live.aim_at(TARGET)
            await live_handler("partyvan")(live.message(SNITCH), BOARD)

            self.assertEqual(await live.balance_of(SNITCH), 100.0)
            self.assertEqual(await live.balance_of(TARGET), 200.0)

    async def test_partyvan_keeps_other_items_intact(self):
        """Запись идёт целым JSON - чужие ключи не должны потеряться."""
        async with live_economy() as live, isolated_board():
            await live.seed_user(
                SNITCH, 100.0, {"partyvan_gun": True, "knife_gun": True})
            await live.seed_user(TARGET, 200.0, {"tinfoil_hat": 0})
            live.aim_at(TARGET)
            await live_handler("partyvan")(live.message(SNITCH), BOARD)

            self.assertIsInstance(
                json.loads(await live.column_of(SNITCH, "active_items")), dict)
            self.assertTrue((await live.items_of(SNITCH))["knife_gun"])
            # Фольга от пативэна не спасает и не расходуется.
            self.assertIn("tinfoil_hat", await live.items_of(TARGET))


if __name__ == "__main__":
    unittest.main()
