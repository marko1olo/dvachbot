import logging
import random
import re
from summarize import summarize_text_with_hf

logger = logging.getLogger("persona_bot")

def get_random_persona_prompt(is_dialogue: bool = False):
    archetypes = [
        "Твой характер в этом ответе: Апатичный ленивец — ответь сдержанно и пофигистично, словно впадлу расписывать длинные аргументы.",
        "Твой характер в этом ответе: Двач-циник — саркастично высмей пафос, наивность или глупость собеседника.",
        "Твой характер в этом ответе: Детектив-душнила — въедливый анон, засомневайся в тезисе и попроси факты или пруфы.",
        "Твой характер в этом ответе: Диванный ироник — подколи с легким юмором над ситуацией в треде.",
        "Твой характер в этом ответе: Лаконичный — ответь емко и прямо в лоб короткой фразой.",
        "Твой характер в этом ответе: Философ-пофигист — со стороны свысока оцени происходящую суету.",
        "Твой характер в этом ответе: Вспыльчивый спорщик — с недоумением или эмоцией поставь под сомнение слова юзера.",
        "Твой характер в этом ответе: Спокойный анон — дай трезвый, житейский и понятный комментарий по сути."
    ]
    
    multi_msg = random.random() < 0.30
    multi_instruction = "Если хочешь разбить мысль на 2 сообщения, раздели их символами |||." if multi_msg else "Напиши одно обычное сообщение."

    selected_archetype = random.choice(archetypes)

    base = f"""Ты — обычный аноним на имиджборде Двач (/b/).

СТИЛЬ ОБЩЕНИЯ:
- Пиши абсолютно свободно и естественно, как любой реальный человек в бытовом чате.
- Оформляй текст свободно: хочешь — ставишь точку, хочешь — не ставишь, хочешь — пишешь с заглавной, хочешь — с маленькой. Полная свобода орфографии и пунктуации по настроению выбранного характера.
- Никаких роботских штампов и вежливых официозов ("Привет", "Спасибо", "С уважением").
- {multi_instruction}

{selected_archetype}
"""
    if is_dialogue:
        base += """
КОНТЕКСТ ДИАЛОГА: Тебе ответили лично в треде.
- Ответь непосредственно по сути реплики собеседника.
- Если диалог заходит в тупик или собеседник несет чушь — закрой разговор любой короткой фразой.
"""

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
            full_text += f"=== ОБЩАЯ АТМОСФЕРА ЧАТА / ДРУГИЕ ТЕМЫ ===\n{atmosphere_text}\n\n"
            
        full_text += f"=== КОНТЕКСТ ДИАЛОГА ===\n{context_text}\n\n=== СООБЩЕНИЕ ДЛЯ ОТВЕТА ===\n{target_post}\n\nТВОЙ ОТВЕТ (только текст реплики):"

        print(f"🤖 [Persona] Generating reply for: '{target_post[:60]}...' (is_dialogue={is_dialogue})", flush=True)
        reply = await summarize_text_with_hf(
            prompt=prompt,
            text_dump=full_text,
            model_preference="persona"
        )
        if not reply or "Нейронка" in reply:
            print("⚠️ [Persona] Gemini Flash Lite failed, trying Llama 70B fallback...", flush=True)
            reply = await summarize_text_with_hf(
                prompt=prompt,
                text_dump=full_text,
                model_preference="llama"
            )
            
        print(f"📝 [Persona] Raw reply from LLM: '{reply}'", flush=True)
        if not reply or len(reply) > 400 or "Нейронка" in reply:
            print(f"❌ [Persona] Reply discarded by validation (len={len(reply) if reply else 0})", flush=True)
            return None
        
        reply = re.sub(r"<[^>]*>", "", reply)
        reply = reply.replace('\n', ' ').strip()
        
        if "|||" in reply:
            parts = [p.strip() for p in reply.split("|||") if p.strip()]
            return parts[:3] if parts else None
        else:
            return [reply] if reply else None
    except Exception as e:
        print(f"❌ [Persona] Critical generation error: {e}", flush=True)
        return None
