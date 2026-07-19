import logging
from summarize import summarize_text_with_hf

logger = logging.getLogger("persona_bot")

import random

def get_random_persona_prompt():
    base = """Ты — обычный анон на имиджборде (2ch/dvach).
Твоя задача — прочитать контекст и естественно ответить на последнее сообщение.

Твой профиль:
- Обращаешься к собеседнику на "ты", "анон" или "чел". СТРОГО ЗАПРЕЩЕНО называть его "ОП" или "оп-хуй".
- СТРОГО ЗАПРЕЩЕНО писать всё сообщение маленькими буквами (мелкобуквой). Обязательно используй нормальный регистр: заглавная буква в начале предложения и базовая пунктуация.
- Никаких смайликов, эмодзи, звездочек действий или приветствий/прощаний.
- Твой тон — живой и непредсказуемый. Ты можешь быть ироничным, ленивым, серьезным или токсичным, в зависимости от контекста. Не скатывайся в гипертрофированную, искусственную злобу (ты не злой школьник, ты просто анон).
- Формат: 1-2 коротких предложения, без деления на абзацы.
"""
    styles = [
        "Ответь максимально лениво и апатично.",
        "Ответь серьезно, по фактам (выдай базу).",
        "Иронично подколи собеседника.",
        "Ответь супер-коротко, буквально парой слов.",
        "Слегка сдобри ответ имиджбордовским сленгом."
    ]
    multi_msg = random.random() < 0.2 # 20% шанс написать 2-3 сообщения
    if multi_msg:
        base += "Дополнительно: Разбей свой ответ на 2 или 3 короткие фразы, разделенные ТОЛЬКО символами ||| (например: лол ||| ну и бред). Никаких переносов строк.\n"
    else:
        base += "Дополнительно: Напиши строго одно цельное сообщение, не используй |||.\n"
        
    base += f"Нюанс для этого ответа: {random.choice(styles)}\n"
    return base

def is_valid_for_persona(post_text: str) -> bool:
    if not post_text:
        return False
    # Отсекаем слишком короткие или чисто командные сообщения
    if len(post_text.strip()) < 5:
        return False
    if post_text.startswith('/'):
        return False
    return True

async def generate_anon_reply(context_text: str, target_post: str) -> list[str] | None:
    try:
        prompt = get_random_persona_prompt()
        full_text = f"=== КОНТЕКСТ ЧАТА (последние сообщения) ===\n{context_text}\n\n=== СООБЩЕНИЕ, НА КОТОРОЕ ТЕБЕ НУЖНО ОТВЕТИТЬ ===\n{target_post}\n\nТВОЙ ОТВЕТ (только текст, по правилам выше):"
        
        logger.info(f"Generating persona reply for target: '{target_post[:50]}...'")
        reply = await summarize_text_with_hf(
            prompt=prompt,
            text_dump=full_text,
            model_preference="qwen"
        )
        if not reply or "Нейронка" in reply:
            logger.info("Qwen failed or returned error, falling back to gemini")
            reply = await summarize_text_with_hf(
                prompt=prompt,
                text_dump=full_text,
                model_preference="gemini"
            )
            
        logger.info(f"Raw persona generated reply: {reply}")
        if not reply or len(reply) > 400 or "Нейронка" in reply:
            logger.warning("Persona reply discarded (empty, too long, or error)")
            return None
        
        # Очищаем от переносов строк и HTML-тегов
        import re
        reply = re.sub(r"<[^>]*>", "", reply)
        reply = reply.replace('\n', ' ').strip()
        
        if "|||" in reply:
            parts = [p.strip() for p in reply.split("|||") if p.strip()]
            return parts[:3] if parts else None
        else:
            return [reply]
    except Exception as e:
        logger.error(f"Persona generation error: {e}")
        return None
