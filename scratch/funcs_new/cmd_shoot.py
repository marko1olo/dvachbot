@dp.message(Command("shoot"))
async def cmd_shoot(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id: return
    user_id = message.from_user.id
    if not message.reply_to_message:
        await message.answer("⚠️ Сделай Reply на пост жертвы с командой /shoot!")
        return

    import time
    db = await get_pool()

    active_items = await _get_user_active_items(db, user_id, board_id)
    if not active_items.get("mute_gun"):
        await message.answer("У тебя нет Мут-Гана! Купи его в магазине: /shop")
        return

    target_id = await get_author_id_by_reply(message)
    if not target_id or target_id == 0:
        await message.answer("🚫 Не удалось найти автора поста...")
        return
    if target_id == user_id:
        await message.answer("Ты пытаешься выстрелить в самого себя? Идиот.")
        return

    # Проверяем Зеркальный Щит у цели
    t_items = await _get_user_active_items(db, target_id, board_id)
    current_time = int(time.time())

    if t_items.get("reflect_shield_until", 0) > current_time:
        # Рикошет!
        # t_items передаём ВНУТРИ контекста: живая _handle_shoot_bounce
        # принимает один аргумент. Вторым позиционным это был TypeError,
        # то есть Зеркальный Щит не срабатывал ни разу.
        await _handle_shoot_bounce(ShootContext(message, db, db_lock, board_id, user_id, target_id, active_items, t_items))
        return

    # Идемпотентность: цель уже в муте
    from datetime import datetime, UTC

    async with storage_lock:
        current_mute = board_data[board_id]['mutes'].get(target_id)
        
    if current_mute and current_mute > datetime.now(UTC):
        await message.answer("⚠️ Эта цель УЖЕ находится в муте! Выбери кого-то другого. Мут-Ган остался у тебя.")
        # Здесь стоял вызов _handle_shoot_bounce. Он РАБОТАЛ, и в этом была
        # проблема: рикошет списывает мут-ган и сажает в мут на час самого
        # стрелка, отправляя вдогонку «🛡️ ЗЕРКАЛЬНЫЙ ЩИТ!». То есть на попытку
        # выстрелить в уже замученного пользователь получал два сообщения
        # подряд с противоположным смыслом и терял предмет — прямо вопреки
        # строке выше, где ему сказано «Мут-Ган остался у тебя».
        # Ветка «цель уже в муте» не рикошет: предупреждаем и выходим, ничего
        # не списывая. Это сознательное изменение поведения, а не фикс падения.
        return

    # Обычный мут цели
    await _handle_shoot_success(ShootContext(message, db, db_lock, board_id, user_id, target_id, active_items))