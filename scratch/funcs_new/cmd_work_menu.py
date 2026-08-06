@economy_router.message(Command("work", "earn", "bomj", "job", "economy"))
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
    except: pass