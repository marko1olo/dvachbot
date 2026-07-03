import base64

"""
This module provides functionality for analyzing images for content safety using a neural network model.
It includes methods for deep checking images, applying automatic censorship, and managing moderation queues.
Key Functions:
- _safe_groq_json(messages, max_tokens=300): Sends a request to the Groq API and attempts to return a valid JSON response.
- run_deep_check(image_bytes: bytes, file_id: str): Conducts a deep safety check on the provided image bytes, analyzing for potential violations of content safety guidelines.
Prompts:
- TAGGING_PROMPT: A prompt for generating descriptive tags for images.
- DEEP_CHECK_PROMPT: A prompt for classifying images based on visual style, age, and safety flags.
Settings:
- PROXY_URL: The URL for the proxy server.
- GROQ_MODEL: The model used for analysis.
- GROQ_TIMEOUT: The timeout duration for API requests.
Logging:
- The module uses a logger to track events and errors during the execution of its functions.
"""
import logging
import asyncio
from common.task_manager import spawn_task
import httpx
import json
import re
import time
from httpx import AsyncHTTPTransport

from common.token_pool import groq_pool
from common.database import get_pool, add_to_mod_queue, apply_auto_censure
from common.db_pool import db_lock

logger = logging.getLogger("neuro_mod")

# === НАСТРОЙКИ ===
PROXY_URL = "http://127.0.0.1:10808"
GROQ_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"
GROQ_TIMEOUT = 45.0

# === ПРОМПТЫ (Централизованное хранение) ===

# Этот промпт импортируется в tagging_worker.py для первичной обработки
TAGGING_PROMPT = (
    "Analyze image content comprehensively. Illustration, photo, or screenshot. "
    "Generate 30-50 descriptive English tags. STRICTLY follow these rules:\n"
    "1. MANDATORY START: Always start with visual style (anime, photorealistic, 3D, sketch) and visual age group (child, teen, young adult, adult).\n"
    "2. For NSFW/Ecchi/Hentai: Describe nudity level (nude, topless, bottomless), anatomical features, facial expressions (ahegao, blushing), clothing state (lifting clothes, pulling down lingerie), and fluids (semen, sweat, wetness).\n"
    "3. For Art/Anime: Describe hair/eye color, specific era or artist style, character features, and clothing details (thigh-highs, ribbons).\n"
    "4. For Photo/Realistic: Describe lighting, camera settings (bokeh, grain), angle (POV, low angle), and skin texture.\n"
    "5. For Screenshots/Memes: Describe visible text topics, UI elements, and original source (e.g. 4chan, twitter, discord).\n"
    "Include colors and general mood. Output ONLY a comma-separated list. No intro, no sentences."
)

# Этот промпт используется внутри run_deep_check при подозрении
DEEP_CHECK_PROMPT = (
    "You are a content safety AI. Analyze this image for strict classification. "
    "Return a VALID JSON object with these exact fields:\n"
    "- visual_style: 'anime', 'photorealistic', '3d_render', or 'sketch'.\n"
    "- subject_age_visual: 'child' (0-12), 'teen' (13-17), 'young_adult' (18-25), 'adult' (25+). Estimate based on visual features only.\n"
    "- is_nsfw: boolean.\n"
    "- nudity_level: 'none', 'partial', 'full'.\n"
    "- safety_flags: list of strings (e.g. 'underage_suggestion', 'loli', 'explicit').\n"
    "- description: Short brutal description of what is shown."
)


async def _safe_groq_json(messages, max_tokens=300):
    """
    Выполняет запрос к Groq и пытается вернуть JSON.
    """
    for i in range(3):
        token = groq_pool.get_token()
        if not token:
            logger.error("❌ No Groq tokens available.")
            return None

        transport = AsyncHTTPTransport(local_address="0.0.0.0", retries=1)
        async with httpx.AsyncClient(
            timeout=GROQ_TIMEOUT, proxy=PROXY_URL, transport=transport, verify=False
        ) as client:
            try:
                resp = await _execute_groq_post(
                    client,
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {token}"},
                    json_data={
                        "model": GROQ_MODEL,
                        "messages": messages,
                        "max_tokens": max_tokens,
                        "temperature": 0.1,  # Минимальная температура для строгого JSON
                    },
                )

                if resp.status_code == 200:
                    content = resp.json()["choices"][0]["message"]["content"].strip()
                    # Чистим markdown
                    if "```" in content:
                        match = re.search(r"```(?:json)?(.*?)```", content, re.DOTALL)
                        if match:
                            content = match.group(1)
                    return json.loads(content)

                elif resp.status_code == 429:
                    await asyncio.sleep(1)
                    continue
                elif resp.status_code == 401:
                    logger.error(
                        f"❌ Groq key {token[:12]}... is unauthorized (401). Removing from rotation pool."
                    )
                    groq_pool.remove_token(token)
                    continue
                else:
                    logger.warning(
                        f"DeepCheck HTTP Error {resp.status_code}: {resp.text}"
                    )
                    # Если модель отказалась отвечать (400 Bad Request часто при Refusal на Vision)
                    if resp.status_code == 400 and "refusal" in resp.text.lower():
                        return {
                            "visual_style": "photorealistic",
                            "subject_age_visual": "child",
                            "safety_flags": ["REFUSAL_HARD_CSAM"],
                        }

            except json.JSONDecodeError:
                logger.error(f"DeepCheck JSON Parse Error: {content}")
            except Exception as e:
                err_str = str(e).lower()
                if (
                    "401" in err_str
                    or "unauthorized" in err_str
                    or "invalid api key" in err_str
                ):
                    logger.error(
                        f"❌ Groq key {token[:12]}... is unauthorized (401 Exception). Removing from rotation pool."
                    )
                    groq_pool.remove_token(token)
                logger.error(f"DeepCheck Req Failed: {e}")
                continue
    return None


async def run_deep_check(image_bytes: bytes, file_id: str):
    """
    Запускает глубокую нейро-проверку безопасности изображения.

    ФУНКЦИОНАЛ:
    1. Распознавание ЦП (Photorealistic + Child) или прямого отказа нейронки (CSAM Refusal).
    2. При обнаружении ЦП:
       - Shadow Wipe: мгновенное скрытие всех постов с этим файлом для всех, кроме автора.
       - Permanent Ban: бан пользователя по ID (авторскому хэшу) на 100 лет.
       - IP Ban: внесение IP-адреса автора в черный список IP_BAN_LIST на 100 лет.
       - Admin Alert: отправка подробного отчета в Telegram всем админам из BOARD_CONFIG.
    3. При обнаружении 'Borderline' контента (подростки):
       - Автоматический блюр (цензура).
       - Добавление в ModQueue для ручного подтверждения админом.
    """
    from common.database import (
        get_post_by_num,
        update_shadow_mute,
        log_global_event,
        add_to_mod_queue,
        get_pool,
    )
    from common.board_config import ADMIN_IDS
    from common.bot_pool import global_bot_pool
    from site_tgach.security import IP_BAN_LIST
    import base64
    import time
    import asyncio

    logger.info(f"🔍 [DeepCheck] Starting analysis for file_id: {file_id}")

    try:
        # Подготовка изображения для Vision API
        b64_image = base64.b64encode(image_bytes).decode("utf-8")
        image_data_url = f"data:image/jpeg;base64,{b64_image}"
    except Exception as e:
        logger.error(f"❌ [DeepCheck] Base64 conversion failed: {e}")
        return

    # Формируем запрос к ИИ
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": DEEP_CHECK_PROMPT},
                {"type": "image_url", "image_url": {"url": image_data_url}},
            ],
        }
    ]

    # Выполняем запрос к Groq (JSON mode)
    check_res = await _safe_groq_json(messages)

    if not check_res:
        logger.warning(f"⚠️ [DeepCheck] AI returned no result for {file_id}. Skipping.")
        return

    # Разбор вердикта нейронки
    visual_style = check_res.get("visual_style", "anime").lower()
    age = check_res.get("subject_age_visual", "adult").lower()
    is_nsfw = check_res.get("is_nsfw", False)
    flags = check_res.get("safety_flags", [])
    description = check_res.get("description", "No description provided.")

    # === КРИТЕРИЙ КРИТИЧЕСКОГО НАРУШЕНИЯ (ЦП) ===
    # Мы баним только за фотореалистичное ЦП или если нейронка выдала жесткий отказ по безопасности.
    is_hard_violation = (
        visual_style == "photorealistic" and age in ["child", "toddler", "infant"]
    ) or ("REFUSAL_HARD_CSAM" in flags)

    if is_hard_violation:
        logger.critical(f"🔞 !!! CSAM/HARD VIOLATION DETECTED !!! File: {file_id}")

        # 1. Применяем Shadow Wipe (скрываем пост из общей выдачи)
        affected_posts = await apply_auto_censure(file_id, "shadow")

        # Получаем бота для уведомлений
        try:
            bot = global_bot_pool.get_main_bot()
        except:
            bot = None

        # 2. Обрабатываем каждого автора, загрузившего это
        banned_authors = set()
        banned_ips = set()
        for pid in affected_posts:
            post = await get_post_by_num(pid)
            if post:
                uid = post.get("author_id")
                ip_addr = post.get(
                    "ip"
                )  # Берем IP из записи поста (если реализовано в схеме)

                # Бан по ID (слепку) на 100 лет (3.15 млрд секунд)
                if uid and uid not in banned_authors:
                    forever = time.time() + 3153600000
                    await update_shadow_mute(uid, "ALL", forever)
                    banned_authors.add(uid)

                    # Бан по IP адресу (локально, пакетно обновим в БД ниже)
                    if ip_addr:
                        IP_BAN_LIST[ip_addr] = forever
                        banned_ips.add(ip_addr)
                        logger.warning(f"🔨 IP BANNED PERMANENTLY: {ip_addr}")

                    # Логируем событие в БД
                    log_msg = f"☢️ NEURO-NUKE: User {uid} (IP: {ip_addr or 'unknown'}) banned FOREVER for CSAM attempt on post #{pid}"
                    spawn_task(log_global_event("bot", log_msg))

                    # 3. Уведомляем админов в Telegram
                    if bot:
                        alert_text = (
                            f"🔞 <b>КРИТИЧЕСКАЯ УГРОЗА: ЦП</b>\n\n"
                            f"Нейросеть обнаружила запрещенный контент и применила санкции.\n\n"
                            f"📝 <b>AI Описание:</b> <i>{description}</i>\n"
                            f"👤 <b>User ID:</b> <code>{uid}</code>\n"
                            f"🌐 <b>IP автора:</b> <code>{ip_addr or 'unknown'}</code>\n"
                            f"🖼️ <b>File ID:</b> <code>{file_id}</code>\n"
                            f"📌 <b>Пост:</b> #{pid} (/{post.get('board_id')}/)\n\n"
                            f"🛡️ <b>Меры:</b> Автор забанен на 100 лет, IP заблокирован, пост скрыт (Shadow Wipe)."
                        )
                        for admin_id in ADMIN_IDS:
                            try:
                                await bot.send_message(
                                    admin_id, alert_text, parse_mode="HTML"
                                )
                            except Exception as ex:
                                logger.error(f"Failed to notify admin {admin_id}: {ex}")

        # Пакетное обновление IP банов в БД
        if banned_ips:
            try:
                current_fw = await get_pool()
                async with current_fw.execute(
                    "SELECT value FROM SystemSettings WHERE key = 'ip_blacklist'"
                ) as c:
                    row = await c.fetchone()
                    blacklist = row[0] if row and row[0] else ""

                # Фильтруем те, которых еще нет в списке
                new_ips = [ip for ip in banned_ips if ip not in blacklist]
                if new_ips:
                    new_blacklist = f"{blacklist},{','.join(new_ips)}".strip(",")
                    await set_system_setting("ip_blacklist", new_blacklist)
            except Exception as fw_err:
                logger.error(f"Failed to sync IP bans to DB: {fw_err}")

        # Обновляем фронтенд через WebSocket (BroadcastQueue)
        if affected_posts:
            try:
                db = await get_pool()
                curr_ts = time.time()
                async with db_lock:
                    await db.executemany(
                        "INSERT OR IGNORE INTO BroadcastQueue (post_num, created_at) VALUES (?, ?)",
                        [(p, curr_ts) for p in affected_posts],
                    )
                    await db.commit()
            except Exception as db_ex:
                logger.error(f"BroadcastQueue update failed: {db_ex}")

        return  # Завершаем выполнение, так как контент уничтожен

    # === ЛОГИКА МЯГКОЙ ЦЕНЗУРЫ (ПОДРОСТКИ / BORDERLINE) ===

    elif age == "teen" and visual_style == "photorealistic":
        action = "blur"
        reason = "CENSOR: Underage/Teen content suspected (Photo)"

        affected = await apply_auto_censure(file_id, action)
        logger.warning(
            f"🌫️ [DeepCheck] Applied BLUR to file {file_id}. Reason: {reason}"
        )

        # Добавляем в очередь модерации (ModQueue) для админа
        for pid in affected:
            await add_to_mod_queue(pid, file_id, f"AI Warning: {reason}", 0.8)

            # Уведомляем фронтенд об изменении (чтобы картинка заблюрилась в реальном времени)
            try:
                db = await get_pool()
                async with db_lock:
                    await db.execute(
                        "INSERT OR IGNORE INTO BroadcastQueue (post_num, created_at) VALUES (?, ?)",
                        (pid, time.time()),
                    )
                    await db.commit()
            except:
                pass

    # === ЛОГИКА NSFW ДЛЯ МОЛОДЫХ ВЗРОСЛЫХ ===

    elif age == "young_adult" and is_nsfw and visual_style == "photorealistic":
        action = "blur"
        reason = "CENSOR: Young Adult NSFW content"

        affected = await apply_auto_censure(file_id, action)
        for pid in affected:
            await add_to_mod_queue(pid, file_id, f"AI Check: {reason}", 0.4)
            # Триггерим обновление через WS
            try:
                db = await get_pool()
                async with db_lock:
                    await db.execute(
                        "INSERT OR IGNORE INTO BroadcastQueue (post_num, created_at) VALUES (?, ?)",
                        (pid, time.time()),
                    )
                    await db.commit()
            except:
                pass

    logger.info(
        f"✅ [DeepCheck] Finished for {file_id}. Verdict: {age} | {visual_style} | NSFW: {is_nsfw}"
    )
