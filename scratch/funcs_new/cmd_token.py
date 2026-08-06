@dp.message(Command("token"))
async def cmd_token(message: types.Message, board_id: str | None, stream: str = 'ru'):
    """
    Генерирует или показывает пользователю его персональный токен для входа на сайт.
    """
    if not board_id: return
    user_id = message.from_user.id
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    try:
        token = await get_or_create_api_token(user_id, generate_unique_token)
        WEBAPP_URL_DISPLAY = "https://tgach.top" 
        if lang == 'en':
            response_text = (
                "🔑 **Your personal token for website access:**\n\n"
                f"Use it to log in on {WEBAPP_URL_DISPLAY}. **Do not share it with anyone.**\n\n"
                "Tap the token below to copy it:"
            )
        elif lang == 'jp':
            response_text = (
                "🔑 **ウェブサイトアクセスのための個人トークン:**\n\n"
                f"{WEBAPP_URL_DISPLAY} でログインするために使用します。**他人には教えないでください。**\n\n"
                "下のトークンをタップしてコピー:"
            )
        else:
            response_text = (
                "🔑 **Ваш токен для входа на сайт ТГАЧа:**\n\n"
                f"Используйте его для входа на {WEBAPP_URL_DISPLAY}.\n**Никому его не показывайте.**\n\n"
                "Нажмите на токен ниже, чтобы скопировать его:"
            )
        token_display = f"<code>{token}</code>"
        await message.answer(response_text, parse_mode="HTML")
        await message.answer(token_display, parse_mode="HTML")
    except Exception as e:
        print(f"⛔ Критическая ошибка при генерации токена для user {user_id}: {e}")
        if lang == 'en': error = "An error occurred while creating the token."
        elif lang == 'jp': error = "トークンの作成中にエラーが発生しました。"
        else: error = "Произошла ошибка при создании токена."
        await message.answer(error)
    try:
        await message.delete()
    except (TelegramBadRequest, TelegramForbiddenError):
        import traceback; traceback.print_exc()