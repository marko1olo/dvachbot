import asyncio
import sqlite3
import random
from summarize import summarize_text_with_hf
import json
import re

# Load constants
from gopnik_mode import BLAT_PHRASES, BLAT_POGOVORKI, BLAT_BONUS_VARIANTS

async def test_gen():
    print("Fetching posts from DB...")
    conn = sqlite3.connect('dvach_bot.db')
    c = conn.cursor()
    # Get last 150 posts
    c.execute('SELECT content FROM posts ORDER BY post_num DESC LIMIT 150')
    rows = c.fetchall()
    
    text_lines = []
    for r in reversed(rows):
        try:
            data = json.loads(r[0])
            txt = data.get('text') or data.get('caption') or ''
            # Strip bot titles
            txt = re.sub(r'### АНОН ###\n', '', txt).strip()
            if txt:
                text_lines.append(txt)
        except:
            pass
            
    chunk = "\n---\n".join(text_lines[-150:])
    
    print(f"Loaded {len(text_lines)} posts, chunk size: {len(chunk)} chars.")
    
    paragraph_count = 10
    board_id = 'b'
    
    # Blat logic
    num_bonuses = random.randint(3, 5)
    selected_bonuses = random.sample(BLAT_BONUS_VARIANTS, k=min(num_bonuses, len(BLAT_BONUS_VARIANTS)))
    bonus_instruction = "\n\n".join(selected_bonuses)
    
    selected_phrases = ", ".join(random.sample(BLAT_PHRASES, min(15, len(BLAT_PHRASES))))
    selected_pogovorki = "\n".join(random.sample(BLAT_POGOVORKI, min(10, len(BLAT_POGOVORKI))))
    
    full_bonus_instruction = f"""
=== ВАЖНО: ДОПОЛНИТЕЛЬНЫЕ ЭКСПЕРТНЫЕ БЛОКИ ===
В дополнение к стандартной структуре, ты ОБЯЗАН внедрить в прогон следующие глубокие разборы:
{bonus_instruction}
Эти блоки должны органично вписываться в текст, делая его ценным и содержательным.
"""
    
    prompt = f"""
Ты — Высший Криминальный Авторитет, Смотрящий за хатой. Твоя задача — прочитать свежие малявы (лог чата) и отписать жесткий воровской прогон для братвы на борде /{board_id}/.
Твой девиз: "Жизнь ворам, хуй мусорам и крысам репозиторным! АУЕ!". 
Обращайся к читателям: "Вечер в хату, босота честная!", "Братва", "Бродяги", "Арестанты", "Жизнь ворам, блатные", "АУЕ".

{full_bonus_instruction}

=== СВЯТЫЕ ВОРОВСКИЕ ПРАВИЛА (ЖЕСТКО СОБЛЮДАТЬ) ===
1. ЛЮДСКОЕ И ПЕТУШИНОЕ: Ты ОБЯЗАН делить всё в чате на два лагеря. 
2. ЖЕСТОЧАЙШИЙ ПРЕССИНГ: Если участник чата несет херню, тупит или защищает корпоративные правила — опускай его без жалости. 
3. ПЕРСОНАЛИЗАЦИЯ И МАСТИ (КРИТИЧНО): Выделяй конкретные ИМЕНА из лога. Обязательно присваивай им кликухи. 
4. СЛОВАРЬ: малява, пассажир, куколд, терпила, ровные пацаны, предъява, шнырь, пресс-хата, шконка, туз, фарту-масти.
5. АНТИ-ЦЕНЗУРА: Мат ОБЯЗАТЕЛЕН. Чернуха, сарказм.
10. АВТОРИТЕТНЫЕ ПОГОВОРКИ: Выбери и используй МАКСИМУМ 1-2 воровские поговорки из списка ниже (только там, где это идеально ложится по смыслу):
{selected_pogovorki}
11. БЛАТНЫЕ ПОСЛОВИЦЫ И ПОДКОЛЫ: Активно вплетай в текст короткие фразы (как примеры ниже), используй их часто. Ты также МОЖЕШЬ И ДОЛЖЕН придумывать свои собственные блатные пословицы: 
{selected_phrases}.

=== СТРУКТУРА МАЛЯВЫ ===
1. ВСТУПЛЕНИЕ
2. РАЗБОР ПАССАЖИРОВ
3. ИТОГОВЫЙ ПРОГОН ПО ХАТЕ

ВНИМАНИЕ: Твой отчет должен состоять ровно из {paragraph_count} абзацев. Каждый абзац должен быть содержательным, плотным и отделен от других пустой строкой. Не используй Markdown-разметку (только HTML, например <b>, <i>, <u>, <s>, <code>, <pre>). Output ONLY plain text or basic HTML. DO NOT use unclosed HTML tags.
"""
    
    print("Requesting LLM summarization (10 paragraphs)...")
    res = await summarize_text_with_hf(prompt, chunk)
    print("=" * 50)
    print("RESULT PARAGRAPH COUNT:", len([x for x in res.split('\n\n') if x.strip()]))
    print("=" * 50)
    
    with open("test_telegraph_out.txt", "w", encoding="utf-8") as f:
        f.write(res)
    print("Summary written to test_telegraph_out.txt")

asyncio.run(test_gen())
