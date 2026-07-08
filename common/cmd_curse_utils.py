import typing

async def cmd_curse_logic(message: typing.Any, board_id: str | None, stream: str = 'ru'):
    await message.answer(
        "⚠️ Проклятие Хуесоса было признано слишком кринжовым и убрано из Теневого Магазина."
    )
