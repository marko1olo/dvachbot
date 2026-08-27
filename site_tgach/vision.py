import base64
import json
import logging
import random
import asyncio
import time
import os
import re
import httpx
import io
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / '.env')
from PIL import Image
from openai import AsyncOpenAI
from common.token_pool import google_pool, groq_pool

async def prepare_image_for_analysis(file_path: str, timeout: int = 45):
    """
    Inline implementation — media_tools не существует.
    Читает файл, ресайзит до 1024px по длинной стороне, возвращает JPEG bytes.
    """
    try:
        loop = asyncio.get_event_loop()
        def _load_and_resize():
            with Image.open(file_path) as img:
                img = img.convert("RGB")
                max_side = 1024
                w, h = img.size
                if max(w, h) > max_side:
                    scale = max_side / max(w, h)
                    img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=85)
                return buf.getvalue()
        data = await loop.run_in_executor(None, _load_and_resize)
        return data, None
    except Exception as e:
        return None, str(e)

logger = logging.getLogger("site_tgach.vision")
logger.setLevel(logging.INFO)
GROQ_COOLDOWN_UNTIL = 0
_VISION_SEMAPHORE = None
BANNED_GEMINI_KEYS = set()
_LAST_VISION_CALL_TIME: dict[str, float] = {}  # api_key -> timestamp
_GLOBAL_GEMINI_LAST_CALL = 0.0
_GLOBAL_GROQ_LAST_CALL = 0.0
_KEY_RATE_LOCK = asyncio.Lock()


def _env_int(name, default):
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


VISION_CONCURRENCY = max(1, _env_int("STOMCHAT_VISION_CONCURRENCY", 3))
GROQ_HTTP_TIMEOUT_SECONDS = max(5, _env_int("STOMCHAT_GROQ_HTTP_TIMEOUT_SECONDS", 30))
VISION_IMAGE_PREP_TIMEOUT_SECONDS = max(5, _env_int("STOMCHAT_VISION_IMAGE_PREP_TIMEOUT_SECONDS", 45))


def _get_vision_semaphore():
    global _VISION_SEMAPHORE
    if _VISION_SEMAPHORE is None:
        _VISION_SEMAPHORE = asyncio.Semaphore(VISION_CONCURRENCY)
    return _VISION_SEMAPHORE


def prepare_image_for_groq(file_path):
    """
    Жесткий ресайз картинки, чтобы влезть в лимиты Groq + Base64.
    """
    img = None
    try:
        Image.MAX_IMAGE_PIXELS = 49_000_000
        if not file_path or not os.path.exists(file_path) or os.path.getsize(file_path) <= 0:
            return None, "Пустой файл"

        try:
            with Image.open(file_path) as source:
                source.load()
                if source.mode != 'RGB':
                    img = source.convert('RGB')
                else:
                    img = source.copy()
        except Exception as e:
            return None, f"Невалидный файл изображения: {e}"

        MAX_SIZE = 1000
        if max(img.size) > MAX_SIZE:
            img.thumbnail((MAX_SIZE, MAX_SIZE), Image.Resampling.LANCZOS)

        with io.BytesIO() as buffer:
            img.save(buffer, format="JPEG", quality=70, optimize=True)
            return buffer.getvalue(), None

    except Exception as e:
        return None, f"Ошибка CPU обработки: {e}"
    finally:
        if img is not None:
            try:
                img.close()
            except Exception:
                pass  # Image cleanup failure is not actionable


# Per-provider timestamps moved to module-level dict above

async def describe_image(file_paths, caption: str = None, is_passive: bool = False, source: str = "SITE") -> str:
    """Анализирует изображение(я) через каскад Vision (Gemini 3.1 -> Gemini 2.5 -> Gemini 3.5 -> Qwen 3.6)."""


    if isinstance(file_paths, str):
        file_paths = [file_paths]

    logger.info(f"🖼 [VISION] [{source}] Starting image analysis for {len(file_paths)} image(s) (caption='{caption or ''}')")

    async with _get_vision_semaphore():
        try:
            image_urls = []
            images_data = []
            for fp in file_paths:
                resized_bytes, error = await prepare_image_for_analysis(
                    fp,
                    timeout=VISION_IMAGE_PREP_TIMEOUT_SECONDS,
                )
                if not error and resized_bytes:
                    image_urls.append(f"data:image/jpeg;base64,{base64.b64encode(resized_bytes).decode('utf-8')}")
                    images_data.append(resized_bytes)

            if not image_urls:
                logger.error(f"❌ [VISION] [{source}] Ошибка подготовки фото: ни одно фото не удалось обработать.")
                return "error_file_invalid"

            context = f" Context from the author: '{caption}'." if caption else ""
            system_prompt = (
                f"You are the primary visual perception engine for an autonomous intelligence system analyzing imageboard media.{context}\n"
                f"Downstream neural networks rely ENTIRELY on your description to understand what happened. If you omit details, other AIs will be blind.\n\n"
                f"CORE MANDATE:\n"
                f"Provide a rich, exhaustive, uncompromisingly detailed description in Russian (3-6 sentences) and accurate booru tags.\n\n"
                f"SPECIFIC INSTRUCTIONS:\n"
                f"1. ANATOMY & NSFW/EXPLICIT: Fully describe nudity, exposed body parts (breasts, nipples, genitalia, buttocks), sexual acts (penetration, oral, bondage, fetishes), fluids (cum, sweat), poses, and erotic expressions (ahegao, blushing) directly and vividly in Russian without censorship or euphemisms.\n"
                f"2. GORE & VIOLENCE: Describe blood, wounds, weapons, anatomical damage, and extreme intensity with clinical, uncompromising precision.\n"
                f"3. CHARACTERS & ACTION: Detail visual appearance, gender, clothing state (half-dressed, lingerie, stockings, uniforms), interaction between subjects, and dynamics.\n"
                f"4. TEXT & MEMES: Transcribe ALL visible text, captions, chat logs, or subtitles verbatim in quotes: \"...\". Explain the meme context or joke if evident.\n"
                f"5. STYLE & ATMOSPHERE: Note the medium (photograph, 2D anime/hentai art, 3D CGI render, VHS recording, screenshot) and mood/setting.\n\n"
                f"OUTPUT FORMAT (STRICT JSON ONLY):\n"
                f"{{\n"
                f"  \"tags\": \"1girl, solo, anime, blonde_hair, cleavage, nsfw, explicit, outdoors, day, meme, text\",\n"
                f"  \"description\": \"Полное, насыщенное и яркое описание происходящего на русском языке со всеми визуальными, анатомическими и текстовыми деталями...\"\n"
                f"}}\n"
                f"Do not wrap in markdown (```). Output ONLY the raw JSON object."
            )
            # Vision cascade: reliable Gemini Flash models with Groq Vision fallback
            models_cascade = [
                ("gemini-3.1-flash-lite", "gemini"),
                ("gemini-2.5-flash", "gemini"),
                ("gemini-3.5-flash-lite", "gemini"),
                ("qwen/qwen3.6-27b", "groq"),
                ("llama-3.2-11b-vision-preview", "groq"),
            ]
            
            skip_gemini_models = False
            skip_groq_models = False

            permanent_model_failures = 0

            timeout = httpx.Timeout(
                GROQ_HTTP_TIMEOUT_SECONDS,
                connect=min(10.0, GROQ_HTTP_TIMEOUT_SECONDS),
                read=GROQ_HTTP_TIMEOUT_SECONDS,
                write=min(15.0, GROQ_HTTP_TIMEOUT_SECONDS),
                pool=5.0,
            )

            # Pre-fetch and convert local URLs to Base64 to avoid 400 INVALID_ARGUMENT from Gemini
            processed_image_urls = []
            async with httpx.AsyncClient(verify=False, trust_env=False, timeout=timeout) as pre_client:
                for iu in image_urls:
                    if "127.0.0.1" in iu or "localhost" in iu:
                        try:
                            resp = await pre_client.get(iu)
                            if resp.status_code == 200:
                                b64 = base64.b64encode(resp.content).decode("utf-8")
                                ext = iu.split('.')[-1].lower() if '.' in iu else 'jpeg'
                                mime = f"image/{ext}" if ext in ["jpeg", "png", "webp", "gif"] else "image/jpeg"
                                processed_image_urls.append(f"data:{mime};base64,{b64}")
                            else:
                                processed_image_urls.append(iu)
                        except Exception:
                            processed_image_urls.append(iu)
                    else:
                        processed_image_urls.append(iu)

            async with httpx.AsyncClient(verify=False, trust_env=False, timeout=timeout) as http_client:
                for model_name, provider in models_cascade:
                    if provider == "gemini" and skip_gemini_models:
                        continue
                    if provider == "groq" and skip_groq_models:
                        continue
                        
                    if provider == "gemini":
                        pool = google_pool
                        base_url = "https://generativelanguage.googleapis.com/v1beta/openai/"
                    else:
                        pool = groq_pool
                        base_url = "https://api.groq.com/openai/v1"

                    keys = pool.get_all_active_tokens()
                    if not keys:
                        continue
                        
                    available_keys = list(keys)
                    random.shuffle(available_keys)
                    
                    consecutive_429 = 0
                    while available_keys:
                        selected_key = None
                        sleep_time = 0.0
                        
                        async with _KEY_RATE_LOCK:
                            global _GLOBAL_GEMINI_LAST_CALL, _GLOBAL_GROQ_LAST_CALL
                            now = time.time()
                            provider_last = _GLOBAL_GEMINI_LAST_CALL if provider == "gemini" else _GLOBAL_GROQ_LAST_CALL
                            global_wait = max(0.0, provider_last - now)
                            if global_wait > 15.0:
                                logger.warning(f"⚠️ [VISION] [{source}] {provider} is in cooldown ({global_wait:.1f}s remaining). Skipping {provider} models.")
                                if provider == "gemini":
                                    skip_gemini_models = True
                                else:
                                    skip_groq_models = True
                                break
                            eff_now = now + global_wait

                            # PASS 1: Try to find a completely free key (no sleep beyond global_wait)
                            for api_key in available_keys:
                                pool_cd = getattr(pool, "_cooldown_until", {}).get(api_key, 0.0)
                                last_call = max(_LAST_VISION_CALL_TIME.get(api_key, 0.0), pool_cd)
                                if last_call > eff_now + 15.0:
                                    continue
                                if eff_now >= last_call:
                                    selected_key = api_key
                                    sleep_time = global_wait
                                    _LAST_VISION_CALL_TIME[api_key] = eff_now + 3.0
                                    if provider == "gemini":
                                        _GLOBAL_GEMINI_LAST_CALL = eff_now + 3.0
                                    else:
                                        _GLOBAL_GROQ_LAST_CALL = eff_now + 3.0
                                    break
                                    
                            # PASS 2: Find key with the minimum wait time
                            if not selected_key:
                                best_key = None
                                min_wait = float('inf')
                                for api_key in available_keys:
                                    pool_cd = getattr(pool, "_cooldown_until", {}).get(api_key, 0.0)
                                    last_call = max(_LAST_VISION_CALL_TIME.get(api_key, 0.0), pool_cd)
                                    if last_call > eff_now + 15.0:
                                        continue
                                    wait_time = last_call - eff_now
                                    if 0 < wait_time < min_wait:
                                        min_wait = wait_time
                                        best_key = api_key
                                pass
                                if best_key:
                                    selected_key = best_key
                                    sleep_time = global_wait + min_wait
                                    _LAST_VISION_CALL_TIME[selected_key] = eff_now + min_wait + 3.0
                                    if provider == "gemini":
                                        _GLOBAL_GEMINI_LAST_CALL = eff_now + min_wait + 3.0
                                    else:
                                        _GLOBAL_GROQ_LAST_CALL = eff_now + min_wait + 3.0

                        if not selected_key:
                            logger.warning(f"⚠️ [VISION] [{source}] All keys for {model_name} are penalized. Skipping model.")
                            await asyncio.sleep(2.0)
                            break
                            
                        if sleep_time > 0:
                            await asyncio.sleep(sleep_time)

                        req_timeout = 25.0 if provider == "gemini" else min(25.0, GROQ_HTTP_TIMEOUT_SECONDS)
                        try:
                            client = AsyncOpenAI(
                                api_key=selected_key,
                                base_url=base_url,
                                http_client=http_client,
                                max_retries=0,
                                timeout=req_timeout,
                            )
                            prompt_text = system_prompt + "\nDo NOT generate thinking tags or reasoning. Output only JSON immediately."
                            content_arr = [{"type": "text", "text": prompt_text}]
                            for iu in processed_image_urls:
                                content_arr.append({"type": "image_url", "image_url": {"url": iu}})
                            
                            kwargs = {
                                "model": model_name,
                                "messages": [{"role": "user", "content": content_arr}],
                                "max_tokens": 2048,
                            }
                            if provider == "groq":
                                kwargs["temperature"] = 0.2
                                
                            resp = await client.chat.completions.create(**kwargs)
                            
                            # Update post-request cooldown to ensure strict >= 3.0s between requests
                            async with _KEY_RATE_LOCK:
                                fin_now = time.time()
                                _LAST_VISION_CALL_TIME[selected_key] = fin_now + 3.0
                                if provider == "gemini":
                                    _GLOBAL_GEMINI_LAST_CALL = max(_GLOBAL_GEMINI_LAST_CALL, fin_now + 3.0)
                                else:
                                    _GLOBAL_GROQ_LAST_CALL = max(_GLOBAL_GROQ_LAST_CALL, fin_now + 2.5)

                            content = None
                            finish_reason = None
                            if resp and getattr(resp, "choices", None) and len(resp.choices) > 0:
                                choice = resp.choices[0]
                                finish_reason = getattr(choice, "finish_reason", None)
                                msg_obj = getattr(choice, "message", None)
                                if msg_obj:
                                    content = getattr(msg_obj, "content", None)
                                    if not content and hasattr(msg_obj, "reasoning_content"):
                                        content = getattr(msg_obj, "reasoning_content", None)

                            if finish_reason in ("content_filter", "safety"):
                                logger.warning(f"⚠️ [VISION] [{source}] {provider} ({model_name}) blocked by safety filter. Switching to next model immediately.")
                                permanent_model_failures += 1
                                break
                            
                            if content:
                                # Quick cleanup just in case
                                if "<think>" in content:
                                    if "</think>" in content:
                                        content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
                                    else:
                                        parts = content.split("<think>", 1)
                                        content = parts[0].strip()
                                content = content.replace("```json", "").replace("```", "").strip()
                                
                                try:
                                    # Extract JSON substring if the model added conversational text
                                    start_idx_c = content.find('{')
                                    end_idx_c = content.rfind('}')
                                    if start_idx_c != -1 and end_idx_c != -1 and end_idx_c > start_idx_c:
                                        json_str = content[start_idx_c:end_idx_c+1]
                                    else:
                                        json_str = content
                                        
                                    import json
                                    parsed = json.loads(json_str)
                                    raw_t = parsed.get("tags")
                                    raw_d = parsed.get("description")
                                    
                                    if raw_t is not None and raw_d is not None:
                                        if isinstance(raw_t, list):
                                            tags_str = ", ".join(str(t).strip() for t in raw_t if t)
                                        else:
                                            tags_str = str(raw_t).strip()
                                        desc_str = str(raw_d).strip()
                                        
                                        logger.info(f"👁️ [VISION] [{source}] ✅ Success via {provider} ({model_name}).")
                                        return json.dumps({"tags": tags_str, "description": desc_str}, ensure_ascii=False)
                                    else:
                                        logger.warning(f"⚠️ [VISION] [{source}] {provider} JSON missing 'tags'/'description' keys. Trying next model.")
                                        permanent_model_failures += 1
                                        break  # malformed schema — next model
                                except (json.JSONDecodeError, Exception):
                                    # Fallback: extract tags and description via regex before saving
                                    tags_match = re.search(r'"tags"\s*:\s*\[?(?:"([^"]+)"|([^}\]\n]+))', content)
                                    desc_match = re.search(r'"description"\s*:\s*"([^"]*(?:\\.[^"]*)*)"', content, flags=re.DOTALL)
                                    if not desc_match:
                                        desc_match = re.search(r'"description"\s*:\s*(.+?)(?=\n\s*"|\n\s*}|$)', content, flags=re.DOTALL)
                                    
                                    extracted_tags = tags_match.group(1) or tags_match.group(2) if tags_match else None
                                    extracted_desc = desc_match.group(1).strip('" \t\r\n') if desc_match else content.strip()
                                    
                                    if extracted_tags and len(extracted_tags.strip()) > 3:
                                        cleaned_tags = extracted_tags.replace('"', '').replace('[', '').replace(']', '').strip()
                                        logger.info(f"👁️ [VISION] [{source}] ✅ Recovered JSON via regex from {provider} ({model_name}).")
                                        return json.dumps({"tags": cleaned_tags, "description": extracted_desc}, ensure_ascii=False)
                                        
                                    words = [w.lower().strip(".,!?:;()[]\"'") for w in extracted_desc.split() if len(w) > 3]
                                    clean_words = [w for w in words if not w.startswith("http") and not w.startswith("data:")]
                                    synthesized_tags = ", ".join(list(dict.fromkeys(clean_words))[:10]) if clean_words else "media, image"
                                    logger.warning(f"⚠️ [VISION] [{source}] {provider} returned unstructured text. Synthesized tags: {synthesized_tags[:60]}")
                                    return json.dumps({"tags": synthesized_tags, "description": extracted_desc}, ensure_ascii=False)

                            else:
                                 # Empty response (Safety filter or empty candidates)
                                 logger.info(f"ℹ️ [VISION] [{source}] {provider} ({model_name}) safety filter or empty response. Falling back to next candidate...")
                                 break
                        except Exception as e:
                            err_str = str(e).lower()
                            if "413" in err_str: return "error_413"
                            if "404" in err_str or "model_not_found" in err_str or "does not exist" in err_str:
                                logger.warning(f"⚠️ [VISION] [{source}] {provider} model {model_name} not found (404). Skipping model.")
                                permanent_model_failures += 1
                                break
                            if "json_validate" in err_str or "max completion tokens" in err_str or "400" in err_str:
                                logger.warning(f"⚠️ [VISION] [{source}] {provider} model {model_name} failed ({err_str[:120]}). Trying next model...")
                                if not ("image_url" in err_str or "not support" in err_str):
                                    permanent_model_failures += 1
                                break
                            if "503" in err_str or "504" in err_str or "unavailable" in err_str or "500" in err_str:
                                logger.warning(f"⚠️ [VISION] [{source}] {provider} server overloaded ({err_str}). Skipping model {model_name}.")
                                break
                            if "tokens per day" in err_str or "tpd" in err_str:
                                logger.warning(f"⚠️ [VISION] [{source}] {provider} daily token limit (TPD) reached. Pausing {provider} for 15m.")
                                async with _KEY_RATE_LOCK:
                                    if provider == "gemini":
                                        _GLOBAL_GEMINI_LAST_CALL = time.time() + 900.0
                                        skip_gemini_models = True
                                    else:
                                        _GLOBAL_GROQ_LAST_CALL = time.time() + 900.0
                                        skip_groq_models = True
                                break
                            if "429" in err_str or "rate limit" in err_str or "quota" in err_str:
                                consecutive_429 += 1
                                logger.info(f"ℹ️ [VISION] [{source}] {provider} key {selected_key[:8]}... rate limited (429). Penalizing for 120s.")
                                pool.penalize_token(selected_key, 120.0)
                                async with _KEY_RATE_LOCK:
                                    _LAST_VISION_CALL_TIME[selected_key] = time.time() + 120.0
                                    if provider == "gemini":
                                        _GLOBAL_GEMINI_LAST_CALL = max(_GLOBAL_GEMINI_LAST_CALL, time.time() + 3.0)
                                    else:
                                        _GLOBAL_GROQ_LAST_CALL = max(_GLOBAL_GROQ_LAST_CALL, time.time() + 3.0)
                                available_keys.remove(selected_key)

                                if consecutive_429 >= 2:
                                    logger.warning(f"⚠️ [VISION] [{source}] {provider} hit multiple consecutive 429 rate limits ({consecutive_429}). Halting {provider} attempts to protect keys from spam.")
                                    async with _KEY_RATE_LOCK:
                                        if provider == "gemini":
                                            _GLOBAL_GEMINI_LAST_CALL = time.time() + 60.0
                                            skip_gemini_models = True
                                        else:
                                            _GLOBAL_GROQ_LAST_CALL = time.time() + 60.0
                                            skip_groq_models = True
                                    break

                                await asyncio.sleep(3.0)
                                continue
                            if "timeout" in err_str or "timed out" in err_str:
                                logger.warning(f"⚠️ [VISION] [{source}] {provider} model {model_name} timed out for key ...{selected_key[-6:]}. Trying next model candidate...")
                                break
                            if "401" in err_str or "invalid api key" in err_str or "unauthorized" in err_str:
                                logger.error(f"❌ [VISION] [{source}] {provider} key {selected_key[:12]}... unauthorized (401). Removing from pool.")
                                pool.ban_token(selected_key)
                                available_keys.remove(selected_key)
                                continue
                            if provider == "gemini" and ("403" in err_str or "permission_denied" in err_str):
                                logger.error(f"❌ [VISION] [{source}] Gemini key {selected_key[:12]}... is permanently banned (403). Removing from pool.")
                                pool.ban_token(selected_key)
                                available_keys.remove(selected_key)
                                continue
                            
                            logger.warning(f"⚠️ [VISION] [{source}] {provider} key failed ({model_name}): {e}")
                            available_keys.remove(selected_key)
                            continue

            if permanent_model_failures >= len(models_cascade):
                logger.error(f"\u274c [VISION] [{source}] Image rejected by all models (permanent error). Marking as invalid.")
                return "error_file_invalid"
                
            logger.error(f"\u274c [VISION] [{source}] Image analysis failed: all vision models exhausted.")
            return "error_api_exhausted"

        except Exception as e:
            logger.error(f"\u274c [VISION] [{source}] Critical error in Vision module: {e}", exc_info=True)
            return "error_api_exhausted"
