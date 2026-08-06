@dp.message(Command(commands=['b', 'po', 'pol', 'a', 'sex', 'vg', 'int', 'test', 'threads', 'trash', 'ai']))
async def cmd_show_board_info(message: types.Message, board_id: str | None, stream: str = 'ru'):
    """
    Отвечает на команду с названием доски, предоставляя информацию о ней.
    """
    if not board_id: return
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    requested_board_alias = (message.text or message.caption or "").lstrip('/')
    if requested_board_alias == 'pol': requested_board_alias = 'po'
    if requested_board_alias not in BOARD_CONFIG:
        await message.delete()
        return
    target_config = BOARD_CONFIG[requested_board_alias]
    safe_current_name = escape_html(BOARD_CONFIG[board_id]['name'])
    safe_target_name = escape_html(target_config['name'])
    raw_desc = target_config.get('description')
    desc_str = ""
    if lang in ['en', 'jp'] and target_config.get('description_en'):
        desc_str = target_config['description_en']
    elif isinstance(raw_desc, dict):
        desc_str = raw_desc.get(lang) or raw_desc.get('en') or raw_desc.get('ru') or ""
        if not desc_str and raw_desc:
             desc_str = list(raw_desc.values())[0] # Берем любое доступное
    else:
        desc_str = str(raw_desc) if raw_desc else ""
    target_desc = escape_html(desc_str)
    if lang == 'en':
        header_text = f"🌐 You are currently on the <b>{safe_current_name}</b> board."
        board_info_text = (
            f"You requested information about the <b>{safe_target_name}</b> board:\n"
            f"<i>{target_desc}</i>\n\n"
            f"You can switch to it here: {target_config['username']}"
        )
    elif lang == 'jp':
        header_text = f"🌐 現在の板: <b>{safe_current_name}</b>"
        board_info_text = (
            f"板情報 <b>{safe_target_name}</b>:\n"
            f"<i>{target_desc}</i>\n\n"
            f"移動はこちら: {target_config['username']}"
        )
    else:
        header_text = f"🌐 Вы находитесь на доске <b>{safe_current_name}</b>."
        board_info_text = (
            f"Вы запросили информацию о доске <b>{safe_target_name}</b>:\n"
            f"<i>{target_desc}</i>\n\n"
            f"Переключиться на нее можно здесь: {target_config['username']}"
        )
    full_response_text = f"{header_text}\n\n{board_info_text}"
    try:
        await message.answer(full_response_text, parse_mode="HTML", disable_web_page_preview=True)
        await message.delete()
    except (TelegramBadRequest, TelegramForbiddenError):
        import traceback; traceback.print_exc()
    except Exception as e:
        print(f"Ошибка в cmd_show_board_info: {e}")