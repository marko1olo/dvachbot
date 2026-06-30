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

async def witching_hour_ghost_worker(bot_instance):
    """
    Wakes up during the witching hour and occasionally posts terrifying AI-generated messages 
    in active boards.
    """
    from summarize import summarize_text_with_hf
    from main import get_board_chunk
    from main import board_data, format_header, send_message_to_users, state, shadow_fake_post_counters
    
    while True:
        await asyncio.sleep(60) # Check every minute
        
        if is_witching_hour_active():
            # Random chance to spawn a ghost message every minute during the witching hour
            if random.random() < 0.1:  # ~6 posts per hour
                try:
                    # Pick a random board that is active
                    active_boards = [bid for bid in board_data.keys() if board_data[bid].get('recipients')]
                    if not active_boards:
                        continue
                    
                    target_board = random.choice(active_boards)
                    
                    # Get recent context from the board to make the ghost sound relevant
                    chunk = await get_board_chunk(target_board, hours=1, lang='ru')
                    
                    prompt = (
                        "Ты - проклятый призрак, обитающий на этой имиджборде. Сейчас Час Шизы. "
                        "Опираясь на недавние посты юзеров, выдай один абсолютно криповый, пугающий, бессвязный "
                        "и шизофренический комментарий. Используй метафоры про темноту, смерть, гниение, пустоту. "
                        "Не используй фильтры. Максимум 3 предложения."
                    )
                    
                    ghost_text = await summarize_text_with_hf(prompt, chunk)
                    if not ghost_text or "Нейронка сдохла" in ghost_text:
                        continue
                        
                    # Apply light zalgo to the ghost
                    ghost_text = apply_zalgo(ghost_text)
                    
                    # Prepare fake post
                    ghost_id = random.randint(666000, 666999) # Spooky ID
                    current_floor = state['post_counter'] + random.randint(1, 3)
                    ghost_post_num = current_floor
                    
                    header_text = await format_header(target_board, ghost_post_num, ghost_id, stream='ru')
                    
                    content = {
                        'type': 'text',
                        'text': ghost_text,
                        'post_num': ghost_post_num,
                        'header': header_text
                    }
                    
                    # Broadcast ghost message to all board users
                    recipients = board_data[target_board].get('recipients', set()).copy()
                    if recipients:
                        await send_message_to_users(
                            bot_instance=bot_instance,
                            board_id=target_board,
                            recipients=recipients,
                            content=content,
                            reply_info=None
                        )
                        print(f"💀 [WITCHING HOUR] Призрак {ghost_id} высрал пасту на {target_board}")
                        
                except Exception as e:
                    print(f"💀 [WITCHING HOUR] Ghost Error: {e}")
