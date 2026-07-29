"""
Тесты ЖИВОГО /mega - того обработчика, который бот действительно исполняет.

Функция берётся через tests/economy_live.live_handler, то есть по РЕГИСТРАЦИИ
на main.dp, а не импортом по имени: копии экономики в economy_extension.py
висят на economy_router и не вызываются никогда (Dispatcher разрешает свои
обработчики раньше включённых под-роутеров). Тест на копию зеленел бы, не
касаясь работающего кода.

ГДЕ ЛЕЖИТ ЗАКРЕП. В ДВУХ местах, и оба обязательны:
  - в памяти: main.board_data[board_id]['active_pin'] - отсюда читает
    send_active_pin_to_new_user (main.py:6900), то есть новый читатель борды;
  - в БД: Boards.settings JSON, ключ 'active_pin' - его пишет
    update_board_settings, а load_state_from_db (common/database.py:1019)
    заливает обратно в board_data при старте.
Расхождение между ними не видно в рантайме и проявляется только после
рестарта, поэтому каждый тест успеха проверяет ОБА места.

ЧТО ЗДЕСЬ ИЗОЛИРОВАНО РУКАМИ. Оснастка economy_live отвечает за БД и за
message_to_post/messages_storage, но не за board_data и storage_lock - /mega
мутирует и то, и другое. Изоляция сделана локальным isolated_board() ниже;
в economy_live.py её не добавляли, потому что этот файл общий, а трогать его в
рамках этой задачи нельзя.
"""

import asyncio
import contextlib
import json
import unittest
from unittest import mock

from tests.economy_live import (BOARD, REPLY_CHAT_ID, REPLY_MESSAGE_ID,
                                REPLY_POST_NUM, live_economy, live_handler)
import main

SPEAKER = 4001
AUTHOR = 4002
OTHER_POST = 424242


@contextlib.asynccontextmanager
async def isolated_board():
    """Свежая запись board_data[BOARD] и свежий storage_lock на время теста.

    Менеджер асинхронный не потому, что внутри есть await, а чтобы его можно
    было ставить в один `async with` рядом с live_economy(): смешивать в одном
    операторе синхронный и асинхронный менеджеры Python не разрешает.

    board_data - defaultdict в main, общий на весь прогон pytest. Вернуть на
    место тот же объект недостаточно: мутация 'active_pin' уже внутри него.
    Поэтому на время теста подставляется НОВАЯ запись, созданная тем же
    default_factory (полный набор ключей, как в проде), а на выходе исходная
    возвращается либо удаляется, если её не было.

    storage_lock подменяется по той же причине, что db_lock в economy_live:
    asyncio.Lock привязывается к циклу, в котором его впервые ЖДУТ, а
    IsolatedAsyncioTestCase даёт каждому тесту свой цикл. Незанятый замок
    берётся быстрым путём и цикла не касается, так что это страховка от
    состояния, оставленного другим тестовым файлом, а не обход дефекта бота.
    cmd_mega делает `from main import ... storage_lock` внутри функции, то есть
    читает атрибут модуля на каждом вызове - подмена доходит до него.
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


def mega_message(live, user_id: int, with_reply: bool = True):
    """Сообщение, у которого чат КОМАНДЫ совпадает с чатом реплая.

    cmd_mega ищет пост по (message.chat.id, reply_to_message.message_id) - по
    чату, где отдана команда, тогда как get_author_id_by_reply берёт
    reply_to_message.chat.id. В проде это один и тот же приватный чат, поэтому
    расхождения не видно, но в оснастке msg.chat.id - автоатрибут MagicMock, и
    без этой строки живой /mega не нашёл бы пост никогда.
    """
    msg = live.message(user_id, with_reply=with_reply)
    msg.chat.id = REPLY_CHAT_ID
    return msg


async def board_settings(live) -> dict:
    """Настройки доски из БД - вторая, переживающая рестарт половина закрепа."""
    async with live.db.execute(
            "SELECT settings FROM Boards WHERE board_id = ?", (BOARD,)) as cur:
        row = await cur.fetchone()
    return json.loads(row[0]) if row and row[0] else {}


class TestLiveMegaHandler(unittest.IsolatedAsyncioTestCase):
    def test_registered_handler_is_the_live_one(self):
        """/mega обслуживает main.cmd_mega, и он на dp ровно один."""
        handler = live_handler("mega")
        self.assertEqual(handler.__name__, "cmd_mega")
        self.assertEqual(handler.__module__, "main")

    async def test_without_reply_nothing_is_touched(self):
        async with live_economy() as live, isolated_board() as board:
            await live.seed_user(SPEAKER, 100.0, {"megaphone_gun": True})
            msg = mega_message(live, SPEAKER, with_reply=False)
            await live_handler("mega")(msg, BOARD)

            self.assertIn("Reply", " ".join(live.answers(msg)))
            self.assertTrue((await live.items_of(SPEAKER))["megaphone_gun"])
            self.assertIsNone(board["active_pin"])
            self.assertNotIn("active_pin", await board_settings(live))

    async def test_without_megaphone_refuses(self):
        async with live_economy() as live, isolated_board() as board:
            await live.seed_user(SPEAKER, 100.0, {})
            live.aim_at(AUTHOR)
            msg = mega_message(live, SPEAKER)
            await live_handler("mega")(msg, BOARD)

            self.assertIn("нет Мегафона", " ".join(live.answers(msg)))
            self.assertIsNone(board["active_pin"])
            self.assertNotIn("active_pin", await board_settings(live))

    async def test_unknown_post_keeps_the_megaphone(self):
        """Пост не в памяти доски - мегафон не расходуется.

        Ключ вычищается явно: оснастка возвращает message_to_post к тому, что
        было на входе, но не гарантирует, что там пусто.
        """
        async with live_economy() as live, isolated_board() as board:
            await live.seed_user(SPEAKER, 100.0, {"megaphone_gun": True})
            main.message_to_post.pop((REPLY_CHAT_ID, REPLY_MESSAGE_ID), None)
            msg = mega_message(live, SPEAKER)
            await live_handler("mega")(msg, BOARD)

            self.assertIn("не удалось найти этот пост",
                          " ".join(live.answers(msg)).lower())
            self.assertTrue((await live.items_of(SPEAKER))["megaphone_gun"])
            self.assertIsNone(board["active_pin"])

    async def test_command_from_another_chat_keeps_the_megaphone(self):
        """Поиск идёт по чату КОМАНДЫ: чужой chat.id - пост не найден.

        Тест закрепляет именно это поведение cmd_mega: ключ строится из
        message.chat.id, а не из reply_to_message.chat.id. Пост в памяти есть,
        реплай на него указывает, но команда «отдана» из другого чата.
        """
        async with live_economy() as live, isolated_board() as board:
            await live.seed_user(SPEAKER, 100.0, {"megaphone_gun": True})
            live.aim_at(AUTHOR)
            msg = mega_message(live, SPEAKER)
            msg.chat.id = REPLY_CHAT_ID + 1
            await live_handler("mega")(msg, BOARD)

            self.assertIn("не удалось найти этот пост",
                          " ".join(live.answers(msg)).lower())
            self.assertTrue((await live.items_of(SPEAKER))["megaphone_gun"])
            self.assertIsNone(board["active_pin"])

    async def test_already_pinned_post_keeps_the_megaphone(self):
        """Идемпотентность: закрепить то, что и так в закрепе, нельзя."""
        async with live_economy() as live, isolated_board() as board:
            await live.seed_user(SPEAKER, 100.0, {"megaphone_gun": True})
            live.aim_at(AUTHOR)
            board["active_pin"] = REPLY_POST_NUM
            msg = mega_message(live, SPEAKER)
            await live_handler("mega")(msg, BOARD)

            self.assertIn("И ТАК уже висит в закрепе", " ".join(live.answers(msg)))
            self.assertTrue((await live.items_of(SPEAKER))["megaphone_gun"])
            self.assertEqual(board["active_pin"], REPLY_POST_NUM)
            # В БД ничего не писалось - отказ произошёл до update_board_settings.
            self.assertNotIn("active_pin", await board_settings(live))
            msg.bot.send_message.assert_not_awaited()

    async def test_successful_pin_lands_in_memory_and_in_db(self):
        async with live_economy() as live, isolated_board() as board:
            await live.seed_user(SPEAKER, 100.0, {"megaphone_gun": True})
            live.aim_at(AUTHOR)
            msg = mega_message(live, SPEAKER)
            await live_handler("mega")(msg, BOARD)

            # На успехе message.answer не используется вовсе - объявление идёт
            # в чат целиком, поэтому пустой список ответов здесь и есть признак
            # прохода по успешной ветке.
            self.assertEqual(live.answers(msg), [])
            # Мегафон израсходован.
            self.assertFalse((await live.items_of(SPEAKER))["megaphone_gun"])
            # Обе половины закрепа согласованы: иначе рестарт бота «откатил» бы
            # закреп, потому что board_data восстанавливается из Boards.settings.
            self.assertEqual(board["active_pin"], REPLY_POST_NUM)
            self.assertEqual((await board_settings(live))["active_pin"],
                             REPLY_POST_NUM)
            # Объявление на всю доску идёт через bot.send_message, а не answer.
            msg.bot.send_message.assert_awaited()

    async def test_new_pin_replaces_the_old_one_in_both_places(self):
        async with live_economy() as live, isolated_board() as board:
            await live.seed_user(SPEAKER, 100.0, {"megaphone_gun": True})
            live.aim_at(AUTHOR)
            board["active_pin"] = OTHER_POST
            msg = mega_message(live, SPEAKER)
            await live_handler("mega")(msg, BOARD)

            self.assertEqual(board["active_pin"], REPLY_POST_NUM)
            self.assertEqual((await board_settings(live))["active_pin"],
                             REPLY_POST_NUM)
            self.assertFalse((await live.items_of(SPEAKER))["megaphone_gun"])

    async def test_pinning_own_post_is_allowed(self):
        """У /mega НЕТ запрета «на себя», в отличие от /shit и /rob.

        Проверки target_id == user_id здесь нет вообще: команда не адресная,
        цель - пост, а не анон. Тест фиксирует это как поведение, чтобы
        появление запрета не прошло молча.
        """
        async with live_economy() as live, isolated_board() as board:
            await live.seed_user(SPEAKER, 100.0, {"megaphone_gun": True})
            live.aim_at(SPEAKER)  # автор поста - сам вызывающий
            msg = mega_message(live, SPEAKER)
            await live_handler("mega")(msg, BOARD)

            self.assertEqual(board["active_pin"], REPLY_POST_NUM)
            self.assertFalse((await live.items_of(SPEAKER))["megaphone_gun"])

    async def test_mega_does_not_move_money(self):
        async with live_economy() as live, isolated_board():
            await live.seed_user(SPEAKER, 100.0, {"megaphone_gun": True})
            live.aim_at(AUTHOR)
            await live_handler("mega")(mega_message(live, SPEAKER), BOARD)

            self.assertEqual(await live.balance_of(SPEAKER), 100.0)

    async def test_mega_keeps_other_items_intact(self):
        """Запись идёт целым JSON - чужие ключи не должны потеряться."""
        async with live_economy() as live, isolated_board():
            await live.seed_user(
                SPEAKER, 100.0, {"megaphone_gun": True, "knife_gun": True})
            live.aim_at(AUTHOR)
            await live_handler("mega")(mega_message(live, SPEAKER), BOARD)

            items = await live.items_of(SPEAKER)
            self.assertIsInstance(
                json.loads(await live.column_of(SPEAKER, "active_items")), dict)
            self.assertTrue(items["knife_gun"])


if __name__ == "__main__":
    unittest.main()
