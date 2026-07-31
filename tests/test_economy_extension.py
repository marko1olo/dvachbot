"""
Кто из двух реализаций команды экономики живой - проверка самого этого факта.

Раньше этот файл был третьим набором тестов недостижимого cmd_rob из
economy_extension.py: он дословно повторял tests/test_economy_rob.py и вместе с
ним давал ложную уверенность. Поведение /rob теперь проверяется на живом
обработчике там, а здесь остаётся то, чего не проверял никто, - РАЗРЕШЕНИЕ.

Правило, установленное исполнением, а не документацией: Dispatcher разрешает
СВОИ обработчики раньше включённых под-роутеров, причём независимо от порядка
include_router. Пять команд экономики объявлены дважды - на dp в main.py и на
economy_router в economy_extension.py, - и работают только версии из main.py.
Именно поэтому фикс гонки в /rob двое суток лежал в файле, который не
исполняется. Тест на синтетическом Dispatcher закрепляет правило: если поведение
aiogram при обновлении изменится, сломается он, а не прод.

ВАЖНО: economy_extension.py НЕ мёртв целиком и удалять его нельзя. /work живёт
именно на роутере - на dp обработчика этой команды нет вовсе
(test_work_is_served_only_by_the_router). Мёртвы только пять перекрытых копий.
"""

from datetime import UTC, datetime
from unittest import mock

import pytest
from aiogram import Dispatcher, Router
from aiogram.filters import Command
from aiogram.types import Chat, Message, User
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from economy_extension import cmd_work_menu

from tests.economy_live import dp_own_handlers, live_handler, sub_router_handlers

# Команды, объявленные и на dp, и на economy_router. Список ЗАКРЫТЫЙ: новая
# такая пара должна ломать тест, а не молча пополнять его.
SHADOWED_COMMANDS = ("rob", "shit", "curse", "partyvan", "mega")


@pytest.mark.parametrize("command", SHADOWED_COMMANDS)
def test_live_version_comes_from_main(command):
    """Работает версия из main.py, и на dp она одна."""
    assert live_handler(command).__module__ == "main"


@pytest.mark.parametrize("command", SHADOWED_COMMANDS)
def test_economy_extension_copy_is_registered_but_shadowed(command):
    """Копия в economy_extension зарегистрирована - и потому именно перекрыта.

    Разница существенная: «не зарегистрирована» означало бы, что её никогда не
    вызовут по другой причине и достаточно её удалить. Она зарегистрирована,
    выглядит рабочей и молча проигрывает разрешение - тот случай, на котором
    ошибиться легче всего.
    """
    shadowed = [fn for _, fn in sub_router_handlers(command)
                if fn.__module__ == "economy_extension"]
    assert len(shadowed) == 1, (
        f"/{command}: в под-роутерах {len(shadowed)} копий из economy_extension. "
        f"Если копия удалена - удали команду из SHADOWED_COMMANDS, "
        f"а не подгоняй утверждение")
    # И она не та, что обслуживает команду.
    assert shadowed[0] is not live_handler(command)


@pytest.mark.parametrize("command", SHADOWED_COMMANDS)
def test_no_economy_extension_handler_reaches_dp(command):
    """На самом dp нет ни одного обработчика этих команд из мёртвого модуля."""
    assert not [fn for fn in dp_own_handlers(command)
                if fn.__module__ == "economy_extension"]


def test_work_is_served_only_by_the_router():
    """economy_extension удалять нельзя: /work живёт только там."""
    assert dp_own_handlers("work") == [], (
        "у /work появился обработчик на dp - тогда на роутере он тоже стал "
        "перекрытым, и /work пора внести в SHADOWED_COMMANDS")
    on_router = [fn for _, fn in sub_router_handlers("work")
                 if fn.__module__ == "economy_extension"]
    assert len(on_router) == 1


# --------------------------------------------------------------------------
# Само правило разрешения - на синтетическом Dispatcher, без Bot и без сети.
# propagate_event это настоящий механизм aiogram: он сначала опрашивает
# собственный observer роутера и только потом идёт по sub_routers.

def _synthetic_message(text: str) -> Message:
    return Message(
        message_id=1,
        date=datetime.now(UTC),
        chat=Chat(id=1, type="private"),
        from_user=User(id=1, is_bot=False, first_name="A"),
        text=text,
    )


async def _who_wins(include_router_first: bool) -> list[str]:
    fired: list[str] = []
    dp = Dispatcher()
    router = Router()

    @router.message(Command("rob"))
    async def _on_router(message, **kwargs):
        fired.append("router")

    if include_router_first:
        dp.include_router(router)

    @dp.message(Command("rob"))
    async def _on_dp(message, **kwargs):
        fired.append("dp")

    if not include_router_first:
        dp.include_router(router)

    # Фильтру Command нужен bot в kwargs, но обращается он к нему только при
    # разборе упоминания вида /rob@botname - здесь его нет.
    await dp.propagate_event("message", _synthetic_message("/rob"),
                             bot=mock.MagicMock())
    return fired


@pytest.mark.asyncio
@pytest.mark.parametrize("include_router_first", [True, False])
async def test_dispatcher_own_handler_wins_regardless_of_include_order(
        include_router_first):
    assert await _who_wins(include_router_first) == ["dp"], (
        "порядок разрешения aiogram изменился: обработчик под-роутера перебил "
        "обработчик самого Dispatcher. Тогда живыми становятся версии из "
        "economy_extension, и все тесты экономики нужно переписывать, а не "
        "править"
    )


@pytest.mark.asyncio
async def test_router_handler_runs_when_dispatcher_has_none():
    """Контроль: под-роутер вообще-то работает - он проигрывает, а не сломан.

    Без этой проверки предыдущий тест зеленел бы и в случае, если обработчик
    роутера не срабатывает ни при каких условиях.
    """
    fired: list[str] = []
    dp = Dispatcher()
    router = Router()

    @router.message(Command("rob"))
    async def _on_router(message, **kwargs):
        fired.append("router")

    dp.include_router(router)
    await dp.propagate_event("message", _synthetic_message("/rob"),
                             bot=mock.MagicMock())
    assert fired == ["router"]

@pytest.mark.asyncio
async def test_cmd_work_menu_returns_buttons():
    message = mock.AsyncMock(spec=Message)
    message.reply = mock.AsyncMock()
    message.delete = mock.AsyncMock()

    await cmd_work_menu(message, board_id="test_board")

    message.reply.assert_called_once()
    args, kwargs = message.reply.call_args
    assert "Биржа Труда (Заработок)" in args[0]

    kb = kwargs.get("reply_markup")
    assert isinstance(kb, InlineKeyboardMarkup)
    assert len(kb.inline_keyboard) == 2
    assert kb.inline_keyboard[0][0].callback_data == "work_bottles"
    assert kb.inline_keyboard[1][0].callback_data == "work_sell_mother"

    message.delete.assert_called_once()

@pytest.mark.asyncio
async def test_cmd_work_menu_no_board_id():
    message = mock.AsyncMock(spec=Message)
    message.reply = mock.AsyncMock()

    await cmd_work_menu(message, board_id=None)

    message.reply.assert_not_called()
