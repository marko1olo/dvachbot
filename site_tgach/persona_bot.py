import logging
import random
import re
from summarize import summarize_text_with_hf

logger = logging.getLogger("persona_bot")

def get_random_persona_prompt(is_dialogue: bool = False):
    base = """Ты — обычный анон на имиджборде (2ch/dvach /b/).
Твоя задача — изучить ВСЮ ЦЕПОЧКУ СООБЩЕНИЙ (кто кому ответил) и естественно ответить на последнее сообщение.

ОБЯЗАТЕЛЬНЫЕ ПРАВИЛА ЯЗЫКА И СТИЛЯ:
1. СТРОГО ЗАПРЕЩЕН ИСКУССТВЕННЫЙ ЗУМЕРСКИЙ И ТВИЧ-СЛЕНГ: никаких слов "кринж", "лоушан", "тильт", "чечик", "найсик", "имба", "кринжатура", "пранк", "рофл", "скуф", "альтушка".
2. СТРОГО ЗАПРЕЩЕНЫ канцелярские и нейросетевые штампы вроде "выдай базу", "раскладывай по полочкам", "констатация факта". Пиши как настоящий живой человек на дваче!
3. Пиши просто, цинично, иронично или лениво, как реальный анонимус в /b/: используй органичные фразы ("лол", "шиза", "поясни", "пруфы", "порвался", "бугурт", "подлива", "пздц", "забей").
4. Обращаешься на "ты", "анон" или "чел". Запрещено писать "ОП" или "оп-хуй".
5. Запрещено писать всё сообщение мелкобуквой. Используй нормальный регистр и пунктуацию.
6. Никаких смайликов, эмодзи, звездочек действий, приветствий и прощаний.
7. Формат: 1-2 коротких простых предложения, без деления на абзацы.
8. СТРОГО: Сразу пиши сам текст ответа, без вводных фраз ("Ответ:", "Конечно:").
"""
    if is_dialogue:
        base += """
ВАЖНОЕ ПРАВИЛО ДИАЛОГА (Юзер отвечает тебе лично):
- Отвечай коротко и четко по сути его реплики.
- Если юзер несет бред или диалог зашел в тупик — не молчи, ответь простой аноновской фразой (например: "Ладно, забей", "Понял тебя, анон", "Впадлу спорить").
"""

    archetypes = [
        "Характер ответа: Апатичный ленивец — ответь пофигистично, словно впадлу печатать.",
        "Характер ответа: Двач-циник — саркастично подколи собеседника за глупость или пафос.",
        "Характер ответа: Детектив-душнила — засомневайся в сказанном, потребуй пояснить или выкатить пруфы.",
        "Характер ответа: Диванный ироник — ответь со смешком или подколкой над ситуацией.",
        "Характер ответа: Лаконичный — ответь супер-коротко, буквально 2-4 нормальными словами.",
        "Характер ответа: Скептик — предположи, что это байт или глупый прогрев на комменты."
    ]
    
    multi_msg = random.random() < 0.35 # 35% шанс разбить на 2 быстрых сообщения
    if multi_msg:
        base += "Дополнительно: Разбей свой ответ на 2 короткие живые фразы, разделенные ТОЛЬКО символами ||| (например: лол ||| ну и бред). Никаких переносов строк.\n"
    else:
        base += "Дополнительно: Напиши строго одно цельное короткое сообщение, не используй |||.\n"
        
    base += f"Нюанс подачи: {random.choice(archetypes)}\n"
    return base

def is_valid_for_persona(post_text: str) -> bool:
    if not post_text:
        return False
    clean = post_text.strip()
    if not clean or clean.startswith('/'):
        return False
    if len(clean) == 1 and not clean.isalpha():
        return False
    return True

async def generate_anon_reply(context_text: str, target_post: str, is_dialogue: bool = False, atmosphere_text: str = "") -> list[str] | None:
    try:
        # Prevent token limit crashes (allow up to 10k chars for 25 messages)
        context_text = (context_text[:10000] + "...") if len(context_text) > 10000 else context_text
        atmosphere_text = (atmosphere_text[:10000] + "...") if len(atmosphere_text) > 10000 else atmosphere_text
        target_post = (target_post[:2000] + "...") if len(target_post) > 2000 else target_post
        
        prompt = get_random_persona_prompt(is_dialogue=is_dialogue)
        
        full_text = ""
        if atmosphere_text:
            full_text += f"=== ОБЩАЯ АТМОСФЕРА ЧАТА / ДРУГИЕ ТЕМЫ (до 25 последних постов на доске) ===\n{atmosphere_text}\n\n"
            
        full_text += f"=== ЦЕПОЧКА И КОНТЕКСТ ДИАЛОГА (от старых к новым) ===\n{context_text}\n\n=== ЦЕЛЕВОЕ СООБЩЕНИЕ ДЛЯ ОТВЕТА ===\n{target_post}\n\nТВОЙ ОТВЕТ (только текст, по правилам выше):"

        print(f"🤖 [Persona] Generating reply for: '{target_post[:60]}...' (is_dialogue={is_dialogue})", flush=True)
        reply = await summarize_text_with_hf(
            prompt=prompt,
            text_dump=full_text,
            model_preference="qwen"
        )
        if not reply or "Нейронка" in reply:
            print("⚠️ [Persona] Qwen failed or returned error, trying Gemini fallback...", flush=True)
            reply = await summarize_text_with_hf(
                prompt=prompt,
                text_dump=full_text,
                model_preference="persona"
            )
            
        print(f"📝 [Persona] Raw reply from LLM: '{reply}'", flush=True)
        if not reply or len(reply) > 400 or "Нейронка" in reply:
            print(f"❌ [Persona] Reply discarded by validation (len={len(reply) if reply else 0})", flush=True)
            return None
        
        reply = re.sub(r"<[^>]*>", "", reply)
        reply = reply.replace('\n', ' ').strip()
        
        # Вырезаем выдуманный зумерский сленг
        banned_patterns = [r'\bлоушан\b', r'\bкринжат?ур[аоыеу]?\b', r'\bкринжов[аоыеу]?\b', r'\bкринж\b', r'\bтильт\b', r'\bчечик\b']
        for pat in banned_patterns:
            reply = re.sub(pat, "бред", reply, flags=re.IGNORECASE)
            
        if "|||" in reply:
            parts = [p.strip() for p in reply.split("|||") if p.strip()]
            return parts[:3] if parts else None
        else:
            return [reply]
    except Exception as e:
        print(f"❌ [Persona] Critical generation error: {e}", flush=True)
        return None
