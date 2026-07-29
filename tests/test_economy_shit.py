"""
Тесты ЖИВОГО /shit - того обработчика, который бот действительно исполняет.

Вторая копия cmd_shit лежит в economy_extension.py, но она зарегистрирована на
economy_router и не вызывается никогда: Dispatcher разрешает свои обработчики
раньше включённых под-роутеров. Поэтому функция берётся через
tests/economy_live.live_handler, то есть по РЕГИСТРАЦИИ на main.dp, а не
импортом по имени - иначе тест зеленел бы, ни разу не коснувшись работающего
кода (именно так этот проект уже горел на /rob и /curse).

ГДЕ ЛЕЖИТ СТАТУС «обмазан». Только в JSON Users.active_items["shit_until"];
отдельной колонки под него в схеме нет. Единственный консьюмер -
main.py:3029 внутри format_header (main.py:3012): он читает active_items из
Users и вешает на посты автора префикс «💩». Поэтому утверждения идут по
состоянию БД (live.items_of), а не по дословным текстам ответов: формулировки
правятся свободно, состояние - контракт.

/shit не денежная команда: балансы обеих сторон проверяются на неизменность.

ГЛОБАЛЫ. Этот обработчик трогает только message_to_post / messages_storage,
которые оснастка сохраняет и возвращает сама, поэтому изолировать здесь нечего.
"""

import json
import time
import unittest

from tests.economy_live import (BOARD, REPLY_CHAT_ID, REPLY_MESSAGE_ID,
                                live_economy, live_handler)
import main

THROWER = 3001
TARGET = 3002


class TestLiveShitHandler(unittest.IsolatedAsyncioTestCase):
    def test_registered_handler_is_the_live_one(self):
        """/shit обслуживает main.cmd_shit, и он на dp ровно один."""
        handler = live_handler("shit")
        self.assertEqual(handler.__name__, "cmd_shit")
        self.assertEqual(handler.__module__, "main")

    async def test_without_reply_nothing_is_touched(self):
        async with live_economy() as live:
            await live.seed_user(THROWER, 100.0, {"shit_gun": True})
            msg = live.message(THROWER, with_reply=False)
            await live_handler("shit")(msg, BOARD)

            self.assertIn("Reply", " ".join(live.answers(msg)))
            # Кусок говна на месте.
            self.assertTrue((await live.items_of(THROWER))["shit_gun"])

    async def test_without_shit_gun_refuses(self):
        async with live_economy() as live:
            await live.seed_user(THROWER, 100.0, {})
            await live.seed_user(TARGET, 100.0, {})
            live.aim_at(TARGET)
            msg = live.message(THROWER)
            await live_handler("shit")(msg, BOARD)

            self.assertIn("нет куска говна", " ".join(live.answers(msg)))
            # Цель чиста: статус без предмета не выдаётся.
            self.assertNotIn("shit_until", await live.items_of(TARGET))

    async def test_shitting_self_keeps_the_item(self):
        async with live_economy() as live:
            await live.seed_user(THROWER, 100.0, {"shit_gun": True})
            live.aim_at(THROWER)
            msg = live.message(THROWER)
            await live_handler("shit")(msg, BOARD)

            self.assertIn("сам себя", " ".join(live.answers(msg)))
            items = await live.items_of(THROWER)
            self.assertTrue(items["shit_gun"])
            self.assertNotIn("shit_until", items)

    async def test_unaimable_reply_keeps_the_item(self):
        """Reply есть, но пост доске неизвестен - предмет не расходуется.

        Ключ вычищается явно: оснастка возвращает message_to_post к тому, что
        было на входе в блок, но не гарантирует, что там не лежит запись,
        оставленная другим тестовым файлом.
        """
        async with live_economy() as live:
            await live.seed_user(THROWER, 100.0, {"shit_gun": True})
            main.message_to_post.pop((REPLY_CHAT_ID, REPLY_MESSAGE_ID), None)
            msg = live.message(THROWER)
            await live_handler("shit")(msg, BOARD)

            self.assertIn("прицелиться", " ".join(live.answers(msg)))
            self.assertTrue((await live.items_of(THROWER))["shit_gun"])

    async def test_already_shitted_target_keeps_the_item(self):
        """Идемпотентность: повторное обмазывание не тратит говно впустую."""
        async with live_economy() as live:
            expires = int(time.time()) + 1800
            await live.seed_user(THROWER, 100.0, {"shit_gun": True})
            await live.seed_user(TARGET, 100.0, {"shit_until": expires})
            live.aim_at(TARGET)
            msg = live.message(THROWER)
            await live_handler("shit")(msg, BOARD)

            self.assertIn("УЖЕ обмазана", " ".join(live.answers(msg)))
            self.assertTrue((await live.items_of(THROWER))["shit_gun"])
            # Срок не продлён.
            self.assertEqual((await live.items_of(TARGET))["shit_until"], expires)

    async def test_expired_shit_can_be_reapplied(self):
        """Истёкший статус не защищает: цель можно обмазать снова."""
        async with live_economy() as live:
            await live.seed_user(THROWER, 100.0, {"shit_gun": True})
            await live.seed_user(TARGET, 100.0, {"shit_until": int(time.time()) - 10})
            live.aim_at(TARGET)
            msg = live.message(THROWER)
            await live_handler("shit")(msg, BOARD)

            self.assertIn("ПОПАДАНИЕ", " ".join(live.answers(msg)))
            self.assertGreater((await live.items_of(TARGET))["shit_until"], time.time())
            self.assertFalse((await live.items_of(THROWER))["shit_gun"])

    async def test_successful_hit_lands_in_json_where_format_header_reads_it(self):
        async with live_economy() as live:
            await live.seed_user(THROWER, 100.0, {"shit_gun": True})
            await live.seed_user(TARGET, 200.0, {})
            live.aim_at(TARGET)
            msg = live.message(THROWER)
            before = int(time.time())
            await live_handler("shit")(msg, BOARD)

            self.assertIn("ПОПАДАНИЕ", " ".join(live.answers(msg)))
            # Говно израсходовано, статус - у цели, ровно на час.
            self.assertFalse((await live.items_of(THROWER))["shit_gun"])
            expires = (await live.items_of(TARGET))["shit_until"]
            self.assertLessEqual(before + 3600, expires)
            self.assertLessEqual(expires, before + 3602)
            # Бросавший сам не обмазан - эффект не должен задевать стрелка.
            self.assertNotIn("shit_until", await live.items_of(THROWER))
            # Жертву уведомляют в личку.
            msg.bot.send_message.assert_awaited()

    async def test_tinfoil_hat_bounces_the_shit_onto_the_thrower(self):
        """Фольга: обмазан оказывается бросавший, цель остаётся чистой."""
        async with live_economy() as live:
            hat_until = int(time.time()) + 3600
            await live.seed_user(THROWER, 100.0, {"shit_gun": True})
            await live.seed_user(TARGET, 200.0, {"tinfoil_hat": hat_until})
            live.aim_at(TARGET)
            msg = live.message(THROWER)
            before = int(time.time())
            await live_handler("shit")(msg, BOARD)

            self.assertIn("ШАПОЧКА ИЗ ФОЛЬГИ", " ".join(live.answers(msg)))
            thrower_items = await live.items_of(THROWER)
            self.assertFalse(thrower_items["shit_gun"])
            self.assertLessEqual(before + 3600, thrower_items["shit_until"])
            self.assertLessEqual(thrower_items["shit_until"], before + 3602)
            # Цель не тронута, и фольга не расходуется - она защищает
            # многократно, пока не истекла.
            target_items = await live.items_of(TARGET)
            self.assertNotIn("shit_until", target_items)
            self.assertEqual(target_items["tinfoil_hat"], hat_until)

    async def test_expired_tinfoil_hat_does_not_protect(self):
        """Просроченная фольга не отражает: статус уходит цели, а не стрелку."""
        async with live_economy() as live:
            await live.seed_user(THROWER, 100.0, {"shit_gun": True})
            await live.seed_user(TARGET, 200.0, {"tinfoil_hat": int(time.time()) - 5})
            live.aim_at(TARGET)
            msg = live.message(THROWER)
            await live_handler("shit")(msg, BOARD)

            self.assertIn("ПОПАДАНИЕ", " ".join(live.answers(msg)))
            self.assertGreater((await live.items_of(TARGET))["shit_until"], time.time())
            self.assertNotIn("shit_until", await live.items_of(THROWER))

    async def test_shit_does_not_move_money(self):
        """/shit - не денежная команда: балансы обоих не меняются."""
        async with live_economy() as live:
            await live.seed_user(THROWER, 100.0, {"shit_gun": True})
            await live.seed_user(TARGET, 200.0, {})
            live.aim_at(TARGET)
            await live_handler("shit")(live.message(THROWER), BOARD)

            self.assertEqual(await live.balance_of(THROWER), 100.0)
            self.assertEqual(await live.balance_of(TARGET), 200.0)

    async def test_shit_writes_valid_json_and_keeps_other_keys(self):
        """Запись идёт целым JSON-объектом, поэтому проверяем, что он валиден
        и что чужие ключи цели не затёрты."""
        async with live_economy() as live:
            await live.seed_user(THROWER, 100.0, {"shit_gun": True, "knife_gun": True})
            await live.seed_user(TARGET, 200.0, {"laxative_gun": True})
            live.aim_at(TARGET)
            await live_handler("shit")(live.message(THROWER), BOARD)

            for uid in (THROWER, TARGET):
                raw = await live.column_of(uid, "active_items")
                self.assertIsInstance(json.loads(raw), dict)
            self.assertTrue((await live.items_of(THROWER))["knife_gun"])
            self.assertTrue((await live.items_of(TARGET))["laxative_gun"])


if __name__ == "__main__":
    unittest.main()
