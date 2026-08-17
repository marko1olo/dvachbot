import sqlite3
import asyncio
from site_tgach.persona_bot import generate_anon_reply

async def test_real_data():
    conn = sqlite3.connect("C:/Users/danat/Desktop/dvachbot/dvach_bot.db")
    c = conn.cursor()
    c.execute("SELECT author_id, content FROM Posts WHERE board_id='b' ORDER BY post_num DESC LIMIT 15")
    rows = c.fetchall()
    
    if not rows:
        print("Нет сообщений в БД.")
        return
        
    import json
    context_msgs = []
    
    # Порядок DESC, поэтому перевернем
    for row in reversed(rows):
        author_id = row[0]
        try:
            content = json.loads(row[1])
            txt = content.get('text', '')
            if not txt:
                caption = content.get('caption', '')
                if caption: txt = caption
        except:
            txt = row[1]
            
        if txt:
            from common.anon_identity import get_anon_id
            sender = "ТЫ (Нейроанон)" if author_id == 999999999 else f"Анон [{get_anon_id(author_id)}]"
            context_msgs.append(f"[{sender}]: {txt}")
            
    if not context_msgs:
        print("Нет текста в последних сообщениях.")
        return

    context_text = "\n".join(context_msgs[:-1])
    target_post = context_msgs[-1]
    
    print("=== РЕАЛЬНЫЙ КОНТЕКСТ ИЗ /b/ ===")
    print(context_text)
    print("\n=== ЦЕЛЕВОЕ СООБЩЕНИЕ ===")
    print(target_post)
    
    print("\nГенерация ответа (через generate_anon_reply)...")
    reply_texts = await generate_anon_reply(
        context_text=context_text,
        target_post=target_post,
        is_dialogue=True,
        atmosphere_text="• #444101 [ЮЗЕР (Анон)]: Привет, кто здесь?\n• #444105 [ЮЗЕР (Анон)]: Тестируем нового нейроанона на борде."
    )
    print("\n=== ОТВЕТ НЕЙРОАНОНА RAW ===")
    if reply_texts:
        for i, r in enumerate(reply_texts):
            print(f"[{i+1}/{len(reply_texts)}] {r}")
    else:
        print("None (generation failed or skipped)")

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    asyncio.run(test_real_data())
