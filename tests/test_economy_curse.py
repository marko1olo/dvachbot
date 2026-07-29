"""
Тесты ЖИВОГО /curse - того обработчика, который бот действительно исполняет.

До переписывания этот файл импортировал cmd_curse из economy_extension.py -
функцию, зарегистрированную на economy_router и потому недостижимую (Dispatcher
разрешает свои обработчики раньше включённых под-роутеров). Обработчик берётся
через tests/economy_live.live_handler, то есть по РЕГИСТРАЦИИ на main.dp.

ГДЕ ЛЕЖИТ ПРОКЛЯТИЕ. У «проклят до» два разных места хранения, и это важно:
  - КОЛОНКА Users.cursed_until;
  - ключ "cursed_until" внутри JSON Users.active_items.
Живая версия пишет ТОЛЬКО в JSON, мёртвая писала только в колонку. Консьюмеров
тоже два, и читают они по-разному:
  - main.py:3735 _apply_content_transformations читает ОБА (колонку через row[0]
    и JSON через row[1]) и вешает на пост «[Я ХУЕСОС 🤮]»;
  - main.py:19880 читает ТОЛЬКО JSON и блокирует посты длиннее 50 символов.
Поэтому JSON - единственное место, которое honor'ят оба консьюмера, и тесты
проверяют именно его. Заодно это опровергает более раннее утверждение, что
запись мёртвой версии в колонку «не действовала бы вообще»: половину эффекта
(пометку поста) она бы дала.
"""

import json
import time

import pytest

from tests.economy_live import BOARD, live_economy, live_handler

CURSER = 2001
TARGET = 2002


def test_registered_handler_is_the_live_one():
    handler = live_handler("curse")
    assert handler.__name__ == "cmd_curse"
    assert handler.__module__ == "main"


def test_vomit_is_the_same_live_handler():
    """/vomit - алиас той же живой функции, а не отдельная реализация."""
    assert live_handler("vomit") is live_handler("curse")


@pytest.mark.asyncio
async def test_without_reply_nothing_is_touched():
    async with live_economy() as live:
        await live.seed_user(CURSER, items={"laxative_gun": True})
        msg = live.message(CURSER, with_reply=False)
        await live_handler("curse")(msg, BOARD)

        assert "Reply" in " ".join(live.answers(msg))
        assert (await live.items_of(CURSER))["laxative_gun"] is True


@pytest.mark.asyncio
async def test_without_laxative_refuses():
    async with live_economy() as live:
        await live.seed_user(CURSER, items={})
        await live.seed_user(TARGET, items={})
        live.aim_at(TARGET)
        msg = live.message(CURSER)
        await live_handler("curse")(msg, BOARD)

        assert "Слабительного" in " ".join(live.answers(msg))
        assert (await live.items_of(TARGET)) == {}


@pytest.mark.asyncio
async def test_cursing_self_keeps_the_item():
    async with live_economy() as live:
        await live.seed_user(CURSER, items={"laxative_gun": True})
        live.aim_at(CURSER)
        msg = live.message(CURSER)
        await live_handler("curse")(msg, BOARD)

        assert "сам себя" in " ".join(live.answers(msg))
        assert (await live.items_of(CURSER))["laxative_gun"] is True


@pytest.mark.asyncio
async def test_already_cursed_target_keeps_the_item():
    """Идемпотентность: повторное проклятие не тратит слабительное впустую."""
    async with live_economy() as live:
        expires = int(time.time()) + 1800
        await live.seed_user(CURSER, items={"laxative_gun": True})
        await live.seed_user(TARGET, items={"cursed_until": expires})
        live.aim_at(TARGET)
        msg = live.message(CURSER)
        await live_handler("curse")(msg, BOARD)

        assert "И ТАК словесный понос" in " ".join(live.answers(msg))
        assert (await live.items_of(CURSER))["laxative_gun"] is True
        # Срок не продлён.
        assert (await live.items_of(TARGET))["cursed_until"] == expires


@pytest.mark.asyncio
async def test_expired_curse_can_be_reapplied():
    """Истёкшее проклятие не защищает: цель можно проклясть снова."""
    async with live_economy() as live:
        await live.seed_user(CURSER, items={"laxative_gun": True})
        await live.seed_user(TARGET, items={"cursed_until": int(time.time()) - 10})
        live.aim_at(TARGET)
        msg = live.message(CURSER)
        await live_handler("curse")(msg, BOARD)

        assert "ПРОКЛЯТИЕ СРАБОТАЛО" in " ".join(live.answers(msg))
        assert (await live.items_of(TARGET))["cursed_until"] > time.time()


@pytest.mark.asyncio
async def test_successful_curse_lands_in_json_where_consumers_read_it():
    async with live_economy() as live:
        await live.seed_user(CURSER, items={"laxative_gun": True})
        await live.seed_user(TARGET, items={})
        live.aim_at(TARGET)
        msg = live.message(CURSER)
        before = int(time.time())
        await live_handler("curse")(msg, BOARD)

        assert "ПРОКЛЯТИЕ СРАБОТАЛО" in " ".join(live.answers(msg))
        # Слабительное израсходовано.
        assert (await live.items_of(CURSER))["laxative_gun"] is False
        # Проклятие - в JSON active_items, на час.
        expires = (await live.items_of(TARGET))["cursed_until"]
        assert before + 3600 <= expires <= before + 3602
        # Ограничитель на 50 символов (main.py:19880) читает ровно этот путь.
        assert expires > time.time()


@pytest.mark.asyncio
async def test_curse_does_not_touch_the_curser_target_balance():
    """/curse - не денежная команда: балансы обоих участников не меняются."""
    async with live_economy() as live:
        await live.seed_user(CURSER, 100.0, {"laxative_gun": True})
        await live.seed_user(TARGET, 200.0, {})
        live.aim_at(TARGET)
        await live_handler("curse")(live.message(CURSER), BOARD)

        assert await live.balance_of(CURSER) == 100.0
        assert await live.balance_of(TARGET) == 200.0


@pytest.mark.asyncio
async def test_curse_writes_valid_json_for_both_sides():
    async with live_economy() as live:
        await live.seed_user(CURSER, items={"laxative_gun": True})
        await live.seed_user(TARGET, items={"tinfoil_hat": 0})
        live.aim_at(TARGET)
        await live_handler("curse")(live.message(CURSER), BOARD)

        for uid in (CURSER, TARGET):
            assert isinstance(json.loads(await live.column_of(uid, "active_items")), dict)
        # Существующие ключи цели не затёрты.
        assert "tinfoil_hat" in await live.items_of(TARGET)
