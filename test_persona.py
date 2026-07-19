import asyncio
from site_tgach.persona_bot import generate_anon_reply, get_random_persona_prompt
from summarize import summarize_text_with_hf

async def test_sim():
    context = """[анон #4512]: пацаны посоветуйте аниме про повседневность
[анон #8123]: к-он посмотри, классика
[ТЫ (Нейроанон)]: к-он для даунов, смотри еву и страдай
[анон #8123]: лол ева переоценена, чисто шиза для псевдоинтеллектуалов
[анон #4512]: а что-то поновее есть?"""

    target_post = "[анон #4512]: а что-то поновее есть?"
    
    full_text = f"=== КОНТЕКСТ ЧАТА (последние сообщения) ===\n{context}\n\n=== СООБЩЕНИЕ, НА КОТОРОЕ ТЕБЕ НУЖНО ОТВЕТИТЬ ===\n{target_post}\n\nТВОЙ ОТВЕТ (только текст, по правилам выше):"
    
    print("Testing gemini direct...")
    reply = await summarize_text_with_hf(get_random_persona_prompt(), full_text, model_preference="gemini")
    import sys
    sys.stdout.buffer.write(f"RAW: {reply}\n".encode('utf-8'))

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    asyncio.run(test_sim())
