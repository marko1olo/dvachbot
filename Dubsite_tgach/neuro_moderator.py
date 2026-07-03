import base64
import logging
import asyncio
import httpx
from httpx import AsyncHTTPTransport # <--- Импорт транспорта

from common.token_pool import hf_accounts, groq_pool 
from common.database import get_pool, add_to_mod_queue
from common.db_pool import db_lock

logger = logging.getLogger("neuro_mod")

# === НАСТРОЙКА ПРОКСИ ===
PROXY_URL = "http://127.0.0.1:10808" 
# ========================

GROQ_MODEL = "meta-llama/llama-3.2-11b-vision-preview" # Или 11b/90b vision
GROQ_TIMEOUT = 30.0 

async def check_image_content(image_bytes: bytes, file_id: str):
    """
    Генерирует теги через Groq (Llama Vision) и сохраняет в БД.
    Проверяет на запрещенку по ключевым словам.
    """
    import base64
    
    # Кодируем
    try:
        b64_image = base64.b64encode(image_bytes).decode("utf-8")
        url = f"data:image/jpeg;base64,{b64_image}"
    except Exception as e:
        logger.error(f"Base64 error: {e}")
        return

    # Тот самый универсальный промпт
    prompt = (
        "Analyze the image content comprehensively. It can be an illustration, a screenshot, a photo, a chart, or a meme. "
        "Generate a diverse list of 20-40 descriptive tags based on the content type:\n"
        "1. If Art/Anime/NSFW: Describe character features, clothing (or lack of), pose, action, artistic style.\n"
        "2. If Screenshot/Meme: Describe UI elements, visible text topics, visual jokes, platform (e.g., 4chan, twitter).\n"
        "3. If Chart/Graph: Describe data type, visual style, key topics.\n"
        "4. If Photo: Describe objects, scenery, lighting, realism.\n"
        "Always include colors and general mood. "
        "Output ONLY the comma-separated list of English tags. No intro, no sentences."
    )

    tags_result = None

    # Ротация токенов
    for i in range(3):
        token = groq_pool.get_token()
        if not token: break

        try:
            # === ФИКС ДЛЯ VPN/TUN ===
            transport = AsyncHTTPTransport(local_address="0.0.0.0")

            async with httpx.AsyncClient(
                timeout=GROQ_TIMEOUT, 
                proxy=PROXY_URL, 
                transport=transport, # <--- Привязываем транспорт
                verify=False
            ) as client:
                resp = await client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {token}"},
                    json={
                        "model": GROQ_MODEL,
                        "messages": [{
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {"type": "image_url", "image_url": {"url": url}}
                            ]
                        }],
                        "max_tokens": 300
                    }
                )
                if resp.status_code == 401:
                    logger.error(f"❌ Groq key {token[:12]}... is unauthorized (401). Removing from rotation pool.")
                    groq_pool.remove_token(token)
                    continue
                
                if resp.status_code == 429: # Rate Limit
                    await asyncio.sleep(2)
                    continue
                
                if resp.status_code == 200:
                    data = resp.json()
                    tags_result = data['choices'][0]['message']['content'].strip()
                    break 
                
                # Логируем, если модель сдохла
                if resp.status_code == 400:
                    logger.error(f"Groq 400 Error: {resp.text}")
                    break
                
                logger.error(f"Groq HTTP Error {resp.status_code}")

        except Exception as e:
            err_str = str(e).lower()
            if "401" in err_str or "unauthorized" in err_str or "invalid api key" in err_str:
                logger.error(f"❌ Groq key {token[:12]}... is unauthorized (401 Exception). Removing from rotation pool.")
                groq_pool.remove_token(token)
            logger.error(f"Groq Request Error: {e}")
            continue

    if tags_result:
        # Чистка
        clean_tags = " ".join(tags_result.split()).replace(", ,", ",")
        
        # Сохранение в БД
        db = await get_pool()
        try:
            async with db_lock:
                await db.execute(
                    "UPDATE FileRegistry SET tags = ? WHERE file_id = ?",
                    (clean_tags, file_id)
                )
                await db.commit()
            logger.info(f"🏷️ TAGS SAVED for {file_id}")
        except Exception as e:
            logger.error(f"DB Save Tags Error: {e}")

        # Модерация по словам
        lower_tags = clean_tags.lower()
        if "scat" in lower_tags or "feces" in lower_tags or "excrement" in lower_tags:
             await apply_neuro_ban(file_id, "SCAT (Tags)")
        elif "mutilated" in lower_tags and "gore" in lower_tags:
             await apply_neuro_ban(file_id, "GORE (Tags)")
        elif "child" in lower_tags and ("nudity" in lower_tags or "naked" in lower_tags):
             await add_to_mod_queue(0, file_id, "CP Suspicion (Tags)", 1.0)

async def apply_neuro_ban(file_id: str, reason: str):
    logger.info(f"🔨 NEURO-BAN: {reason} | File: {file_id}")
    db = await get_pool()
    try:
        query = "SELECT post_num FROM Posts WHERE content LIKE ? LIMIT 1"
        async with db.execute(query, (f"%{file_id}%",)) as cursor:
            row = await cursor.fetchone()
            if row:
                post_num = row[0]
                async with db_lock:
                    await db.execute("UPDATE Posts SET is_shadow = 1 WHERE post_num = ?", (post_num,))
                    await db.commit()
    except Exception as e:
        logger.error(f"DB Ban error: {e}")