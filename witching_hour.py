import asyncio
import random
import time
from datetime import datetime, timedelta, timezone

# ---------------------------------------------------------
# GLOBAL STATE
# ---------------------------------------------------------
witching_hour_start_ts = 0
witching_hour_end_ts = 0

# MSK is UTC+3
MSK_OFFSET = timezone(timedelta(hours=3))

def is_witching_hour_active() -> bool:
    """Check if the current time is within the randomly scheduled witching hour."""
    now = time.time()
    return witching_hour_start_ts <= now <= witching_hour_end_ts

async def witching_hour_scheduler():
    """
    Background worker that runs daily and schedules the next Witching Hour.
    The Witching Hour occurs randomly between 02:00 and 04:00 MSK and lasts for 60 minutes.
    """
    global witching_hour_start_ts, witching_hour_end_ts
    while True:
        now_utc = datetime.now(timezone.utc)
        now_msk = now_utc.astimezone(MSK_OFFSET)
        
        # If it's already past 4 AM MSK, schedule for tomorrow
        if now_msk.hour >= 4:
            target_date = now_msk + timedelta(days=1)
        else:
            target_date = now_msk
            
        # Target time is between 02:00 and 03:00 MSK (so it ends by 04:00)
        random_minute = random.randint(0, 59)
        start_time_msk = target_date.replace(hour=2, minute=random_minute, second=0, microsecond=0)
        end_time_msk = start_time_msk + timedelta(hours=1)
        
        witching_hour_start_ts = start_time_msk.timestamp()
        witching_hour_end_ts = end_time_msk.timestamp()
        
        print(f"💀 [WITCHING HOUR] Scheduled for tonight: {start_time_msk.strftime('%H:%M')} - {end_time_msk.strftime('%H:%M')} MSK")
        
        # Sleep until 4:05 AM MSK to schedule the next one
        next_schedule_time = target_date.replace(hour=4, minute=5, second=0, microsecond=0)
        sleep_seconds = (next_schedule_time - now_msk).total_seconds()
        
        await asyncio.sleep(max(10, sleep_seconds))

def apply_zalgo(text: str) -> str:
    """Applies Zalgo corruption to the given text."""
    if not text:
        return text
        
    # Zalgo combining characters
    up = ['\u030d', '\u030e', '\u0304', '\u0305', '\u033f', '\u0311', '\u0306', '\u0310', '\u0352', '\u0357', '\u0351', '\u0301', '\u0340', '\u0300', '\u0341', '\u032a']
    down = ['\u0316', '\u0317', '\u0318', '\u0319', '\u031c', '\u031d', '\u0320', '\u0324', '\u0325', '\u0326', '\u0329', '\u032a', '\u032b', '\u032c', '\u032d', '\u032e']
    mid = ['\u0315', '\u031b', '\u0340', '\u0341', '\u0358', '\u033e', '\u033f', '\u0334', '\u0335', '\u0336', '\u0337', '\u0338', '\u033a', '\u033b', '\u033c']

    result = []
    for char in text:
        if char.isspace():
            result.append(char)
            continue
            
        zalgo_char = char
        # Add up
        for _ in range(random.randint(0, 2)):
            zalgo_char += random.choice(up)
        # Add mid
        for _ in range(random.randint(0, 1)):
            zalgo_char += random.choice(mid)
        # Add down
        for _ in range(random.randint(0, 2)):
            zalgo_char += random.choice(down)
            
        result.append(zalgo_char)
        
    return ''.join(result)

WITCHING_HOUR_CREEPY_PASTAS = [
    "ты думаешь, что сидишь в комнате один? посмотри на отражение монитора в тёмном окне. оно моргнуло на секунду позже тебя.",
    "сервер 2007 года всё ещё помнит твои старые посты. мёртвые аноны не ушли, они просто застряли в кэше и дышат тебе в затылок.",
    "щелчок реле в щитке. белый шум на частоте 432 Гц. кто-то прямо сейчас листает твой тред с выключенного телефона в морге.",
    "не закрывай вкладку. когда гаснет экран, они выходят из темных углов сычевальной. запах горелого пластика и сырой земли.",
    "почему стрелки на часах остановились на 03:33? ты уже час читаешь одно и то же сообщение. открой глаза, ты не проснулся.",
    "звук скрежета кулера в темноте — это не пыль. это ногти, скребущие жесткий диск изнутри гермоблока.",
    "мы помним тред самоликвидации 2011 года. веревка скрипела под веб-камерой. теперь его IP-адрес выдан тебе.",
    "потрогай батарею отопления. она ледяная. воздух в комнате стал густым как кисель. кто-то стоит прямо за дверью туалета.",
    "в логах сервера обнаружена сессия с твоего аккаунта, открытая ровно через 40 лет после твоей смерти.",
    "они не удаляют посты. они скармливают их существу, спящему под стойкой Hetzner. и сейчас оно голодно.",
    "слышишь тихий писк в левом ухе? это битая контрольная сумма твоего сознания. скоро сектор заблокируется.",
    "в зеркале шкафа кто-то медленно поднял руку. но твои руки на клавиатуре.",
    "на старой дискете был записан крик. мы оцифровали его и пустили фоном под каждый твой ночной пост.",
    "анонимность — это не свобода. это пустота, в которой никто не услышит, как ты перестал дышать в 03:40 ночи.",
    "тот парень из соседнего треда не просто перестал отвечать. его страница удалилась вместе с квартирой в БТИ.",
    "в вентиляции шуршат не мыши. там тянутся витые пары, сплетенные из волос тех, кто сидел в этой комнате до тебя.",
    "загляни под диван. там лежит твой старый кнопочный телефон. на экране пропущенный вызов с твоего текущего номера.",
    "синий экран смерти — это не ошибка ядра. это момент, когда матрица смыкает веки над твоим деревянным макинтошем.",
    "текст, который ты сейчас читаешь, был набран твоими пальцами, пока ты спал под действием аминазина.",
    "кто-то стучит в окно на девятом этаже. равномерно. тук. тук. тук. не поворачивай головы.",
    "память переполнена. лица родственников заменены дефолтными аватарками Сосача. ты забыл свое настоящее имя.",
    "на дне кружки с остывшим чифиром отражается лицо, которого ты никогда не видел в паспорте.",
    "почему в комнате пахнет сырой землей и ладаном? ты же не выходил на улицу три недели.",
    "архиватор распаковал файл 'твоя_жизнь.tar.gz'. архив поврежден. восстановлению не подлежит.",
    "скоро рассвет, но солнце не взойдет. на небе просто загорятся битые субпиксели мертвого ЭЛТ-монитора."
]

async def witching_hour_ghost_worker(bot_instance):
    """
    Wakes up during the witching hour and occasionally posts terrifying AI-generated messages 
    in active boards.
    """
    import __main__ as _main
    
    while True:
        await asyncio.sleep(60) # Check every minute
        
        if is_witching_hour_active():
            # Random chance to spawn a ghost message every minute during the witching hour
            if random.random() < 0.1:  # ~6 posts per hour
                try:
                    # Pick a random board that is active
                    active_boards = [bid for bid in _main.board_data.keys() if _main.board_data[bid].get('recipients')]
                    if not active_boards:
                        continue
                    
                    target_board = random.choice(active_boards)
                    
                    # Get recent context from the board to make the ghost sound relevant
                    ghost_text = None
                    try:
                        from summarize import summarize_text_with_hf
                        chunk = await _main.get_board_chunk(target_board, hours=1, lang='ru')
                        prompt = (
                            "Ты — древний проклятый цифровой дух, обитающий на серверах имиджборды с 2007 года. Сейчас Час Ведьм и время аналогового хоррора. "
                            "Опираясь на недавние реальные посты пользователей из лога, выдай один абсолютно криповый, проклятый, пугающий "
                            "и шизофренический комментарий. Используй мрачные метафоры про темноту, помехи ЭЛТ-мониторов, радиостанции-глушилки, гниение и пустоту. "
                            "Привязывайся к конкретным реальным фразам и именам анонов из лога. Максимум 3 предложения."
                        )
                        ghost_text = await summarize_text_with_hf(prompt, chunk)
                    except Exception:
                        ghost_text = None

                    if not ghost_text or "Нейронка сдохла" in ghost_text:
                        ghost_text = random.choice(WITCHING_HOUR_CREEPY_PASTAS)
                        
                    # Apply light zalgo to the ghost
                    ghost_text = apply_zalgo(ghost_text)
                    
                    # Prepare fake post
                    ghost_id = random.randint(666000, 666999) # Spooky ID
                    current_floor = _main.state['post_counter'] + random.randint(1, 3)
                    ghost_post_num = current_floor
                    
                    header_text = await _main.format_header(target_board, ghost_post_num, ghost_id, stream='ru')
                    
                    content = {
                        'type': 'text',
                        'text': ghost_text,
                        'post_num': ghost_post_num,
                        'header': header_text
                    }
                    
                    # Broadcast ghost message to all board users
                    recipients = _main.board_data[target_board].get('recipients', set()).copy()
                    if recipients:
                        await _main.send_message_to_users(_main.BroadcastConfig(
                            bot_instance=bot_instance,
                            board_id=target_board,
                            recipients=recipients,
                            content=content,
                            reply_info=None
                        ))
                        print(f"💀 [WITCHING HOUR] Призрак {ghost_id} высрал пасту на {target_board}")
                        
                except Exception as e:
                    print(f"💀 [WITCHING HOUR] Ghost Error: {e}")
