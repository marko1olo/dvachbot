"""
Тесты ЖИВОГО /rob - того обработчика, который бот действительно исполняет.

До переписывания этот файл импортировал cmd_rob из economy_extension.py.
Та функция висит на economy_router и не вызывается никогда (Dispatcher
разрешает свои обработчики раньше включённых под-роутеров), поэтому файл был
не бесполезным, а вредным: он зеленел, пока в работающем /rob двое суток жила
гонка, уводившая баланс жертвы в минус. Обработчик берётся через
tests/economy_live.live_handler, то есть по РЕГИСТРАЦИИ на main.dp.

Проверки идут по состоянию настоящей БД, а не по дословным текстам ответов:
состояние - это контракт, а формулировки правятся свободно.
"""

import asyncio
import json
import time
import unittest
from unittest import mock

from tests.economy_live import BOARD, live_economy, live_handler

ROBBER = 1001
VICTIM = 1002


class TestLiveRobHandler(unittest.IsolatedAsyncioTestCase):
    def test_registered_handler_is_the_live_one(self):
        """/rob обслуживает main.cmd_rob, и он на dp ровно один."""
        handler = live_handler("rob")
        self.assertEqual(handler.__name__, "cmd_rob")
        self.assertEqual(handler.__module__, "main")

    async def test_without_reply_nothing_is_touched(self):
        async with live_economy() as live:
            await live.seed_user(ROBBER, 100.0, {"knife_gun": True})
            msg = live.message(ROBBER, with_reply=False)
            await live_handler("rob")(msg, BOARD)

            self.assertIn("Reply", " ".join(live.answers(msg)))
            # Заточка на месте, деньги не двигались.
            self.assertTrue((await live.items_of(ROBBER))["knife_gun"])
            self.assertEqual(await live.balance_of(ROBBER), 100.0)

    async def test_without_knife_refuses(self):
        async with live_economy() as live:
            await live.seed_user(ROBBER, 100.0, {})
            await live.seed_user(VICTIM, 500.0, {})
            live.aim_at(VICTIM)
            msg = live.message(ROBBER)
            await live_handler("rob")(msg, BOARD)

            self.assertIn("Заточки", " ".join(live.answers(msg)))
            self.assertEqual(await live.balance_of(VICTIM), 500.0)

    async def test_robbing_self_keeps_the_knife(self):
        async with live_economy() as live:
            await live.seed_user(ROBBER, 100.0, {"knife_gun": True})
            live.aim_at(ROBBER)
            msg = live.message(ROBBER)
            await live_handler("rob")(msg, BOARD)

            self.assertIn("сам себя", " ".join(live.answers(msg)))
            self.assertTrue((await live.items_of(ROBBER))["knife_gun"])
            self.assertEqual(await live.balance_of(ROBBER), 100.0)

    async def test_broke_victim_keeps_the_knife(self):
        """Нечего украсть - заточка не расходуется."""
        async with live_economy() as live:
            await live.seed_user(ROBBER, 100.0, {"knife_gun": True})
            await live.seed_user(VICTIM, 0.0, {})
            live.aim_at(VICTIM)
            msg = live.message(ROBBER)
            await live_handler("rob")(msg, BOARD)

            self.assertIn("шекелей", " ".join(live.answers(msg)))
            self.assertTrue((await live.items_of(ROBBER))["knife_gun"])
            self.assertEqual(await live.balance_of(ROBBER), 100.0)
            self.assertEqual(await live.balance_of(VICTIM), 0.0)

    async def test_tinfoil_hat_makes_robber_pay(self):
        """Шапочка из фольги: жертва цела, грабитель теряет долю СВОИХ денег."""
        async with live_economy() as live:
            await live.seed_user(ROBBER, 300.0, {"knife_gun": True})
            await live.seed_user(
                VICTIM, 1000.0, {"tinfoil_hat": int(time.time()) + 3600})
            live.aim_at(VICTIM)
            msg = live.message(ROBBER)
            with mock.patch("random.uniform", return_value=0.2):
                await live_handler("rob")(msg, BOARD)

            self.assertIn("ШАПОЧКА ИЗ ФОЛЬГИ", " ".join(live.answers(msg)))
            # 20% от 300 своих = 60 потеряно; у жертвы не тронуто ничего.
            self.assertEqual(await live.balance_of(ROBBER), 240.0)
            self.assertEqual(await live.balance_of(VICTIM), 1000.0)
            self.assertFalse((await live.items_of(ROBBER))["knife_gun"])

    async def test_successful_robbery_moves_exact_amount(self):
        async with live_economy() as live:
            await live.seed_user(ROBBER, 0.0, {"knife_gun": True})
            await live.seed_user(VICTIM, 500.0, {})
            live.aim_at(VICTIM)
            msg = live.message(ROBBER)
            with mock.patch("random.uniform", return_value=0.2):
                await live_handler("rob")(msg, BOARD)

            self.assertIn("ОГРАБЛЕНИЕ УДАЛОСЬ", " ".join(live.answers(msg)))
            self.assertEqual(await live.balance_of(VICTIM), 400.0)
            self.assertEqual(await live.balance_of(ROBBER), 100.0)
            self.assertFalse((await live.items_of(ROBBER))["knife_gun"])
            # Жертву уведомляют в личку.
            msg.bot.send_message.assert_awaited()

    async def test_stolen_amount_is_capped(self):
        """Сколько бы ни было у жертвы, за один раз уходит не больше 1000."""
        async with live_economy() as live:
            await live.seed_user(ROBBER, 0.0, {"knife_gun": True})
            await live.seed_user(VICTIM, 100000.0, {})
            live.aim_at(VICTIM)
            msg = live.message(ROBBER)
            with mock.patch("random.uniform", return_value=0.3):
                await live_handler("rob")(msg, BOARD)

            self.assertEqual(await live.balance_of(ROBBER), 1000.0)
            self.assertEqual(await live.balance_of(VICTIM), 99000.0)

    async def test_concurrent_robberies_cannot_overdraw_victim(self):
        """ГОНКА. Два одновременных грабежа по 200 при 250 на счету жертвы.

        Это тот самый дефект, из-за которого файл переписан. До защиты оба
        грабежа проходили: списание шло безусловным upsert-ом и ПОСЛЕ
        начисления грабителю, поэтому баланс жертвы уходил в минус, а
        грабителям начислялось то, чего у неё не было. Защита делает проверку и
        списание одной операцией: UPDATE ... WHERE balance >= ?.

        Утверждения намеренно про инварианты, а не про то, какой из двух
        вызовов победил: порядок задач планировщик не обязан повторять.
        """
        async with live_economy() as live:
            await live.seed_user(ROBBER, 0.0, {"knife_gun": True})
            await live.seed_user(VICTIM, 250.0, {})
            live.aim_at(VICTIM)
            first, second = live.message(ROBBER), live.message(ROBBER)
            rob = live_handler("rob")
            # 250 * 0.8 = 200: одного грабежа хватает, двух - нет.
            with mock.patch("random.uniform", return_value=0.8):
                await asyncio.gather(rob(first, BOARD), rob(second, BOARD))

            victim = await live.balance_of(VICTIM)
            robber = await live.balance_of(ROBBER)
            said = live.answers(first) + live.answers(second)
            wins = [t for t in said if "ОГРАБЛЕНИЕ УДАЛОСЬ" in t]
            fails = [t for t in said if "кончились шекели" in t]

            self.assertGreaterEqual(
                victim, 0.0,
                f"баланс жертвы ушёл в минус ({victim}): защита гонки в "
                f"main.cmd_rob снята или обойдена")
            self.assertEqual(
                len(wins), 1,
                f"успешных грабежей {len(wins)}, ожидался ровно один: {said}")
            self.assertEqual(len(fails), 1, f"нет отказа второму грабителю: {said}")
            self.assertEqual(victim, 50.0)
            self.assertEqual(robber, 200.0)
            # Закон сохранения: шекели не создаются из воздуха.
            self.assertEqual(victim + robber, 250.0)

    async def test_concurrent_robberies_leave_valid_json(self):
        """Одновременная запись active_items не портит JSON обоим участникам."""
        async with live_economy() as live:
            await live.seed_user(ROBBER, 0.0, {"knife_gun": True})
            await live.seed_user(VICTIM, 250.0, {})
            live.aim_at(VICTIM)
            rob = live_handler("rob")
            with mock.patch("random.uniform", return_value=0.8):
                await asyncio.gather(rob(live.message(ROBBER), BOARD),
                                     rob(live.message(ROBBER), BOARD))

            for uid in (ROBBER, VICTIM):
                raw = await live.column_of(uid, "active_items")
                self.assertIsInstance(json.loads(raw), dict)


if __name__ == "__main__":
    unittest.main()
