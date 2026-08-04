import base64
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
if not logger.handlers:
    _sh = logging.StreamHandler()
    _sh.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(_sh)
logger.propagate = True
GROQ_COOLDOWN_UNTIL = 0
_VISION_SEMAPHORE = None
BANNED_GEMINI_KEYS = set()


def _env_int(name, default):
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


VISION_CONCURRENCY = max(1, _env_int("STOMCHAT_VISION_CONCURRENCY", 1))
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
                pass


_LAST_VISION_CALL_TIME = 0.0

async def describe_image(file_paths, caption: str = None, is_passive: bool = False, source: str = "SITE") -> str:
    """Анализирует изображение(я) через каскад Vision (Gemini 3.5 -> Qwen 3.6 -> Llama 4 Scout)."""
    global GROQ_COOLDOWN_UNTIL
    global _LAST_VISION_CALL_TIME

    if time.time() < GROQ_COOLDOWN_UNTIL:
        logger.warning(f"⚠️ [VISION] [{source}] Skipped analysis due to active cooldown.")
        return None

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
                return None

            context = f" Context from the author: '{caption}'." if caption else ""
            system_prompt = (
                f"This is an image from an anonymous imageboard / Telegram chat.{context} "
                f"Describe what you see in Russian concisely (1-4 sentences). "
                f"If there is any visible text (meme caption, chat screenshot, post text), transcribe and quote it accurately. "
                f"Specify the visual style (meme, anime art, screenshot, photo, cosplay, digital art). "
                f"Respond directly. Do not use reasoning/thinking blocks. Do not output <think> tags."
            )
            
            # 33% / 33% / 33% load balancing pool between Qwen 3.6 27B, Gemini 3.5 Flash Lite, Gemini 3.1 Flash Lite
            models_pool = [
                ("qwen/qwen3.6-27b", "groq"),
                ("gemini-3.5-flash-lite", "gemini"),
                ("gemini-3.1-flash-lite", "gemini")
            ]
            start_idx = random.randint(0, 2)
            models_cascade = models_pool[start_idx:] + models_pool[:start_idx]

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
                    if provider == "gemini":
                        raw_keys = os.getenv("GOOGLE_API_KEYS", "") or os.getenv("GOOGLE_KEYS", "") or os.getenv("GEMINI_API_KEY", "") or os.getenv("GOOGLE_API_KEY", "")
                        base_url = "https://generativelanguage.googleapis.com/v1beta/openai/"
                    else:
                        raw_keys = os.getenv("GROQ_API_KEYS", "") or os.getenv("GROQ_KEYS", "") or os.getenv("GROQ_API_KEY", "")
                        base_url = "https://api.groq.com/openai/v1"

                    if isinstance(raw_keys, list):
                        keys = [k for k in raw_keys if k and k not in BANNED_GEMINI_KEYS]
                    else:
                        keys = [k.strip() for k in str(raw_keys).split(",") if k.strip() and k.strip() not in BANNED_GEMINI_KEYS]
                        
                    if not keys:
                        continue
                        
                    random.shuffle(keys)
                    
                    for api_key in keys:
                        try:
                            # Enforce global cooldown of 3 seconds between requests per provider
                            time_since_last_call = time.time() - _LAST_VISION_CALL_TIME
                            if time_since_last_call < 3.0:
                                await asyncio.sleep(3.0 - time_since_last_call)
                            _LAST_VISION_CALL_TIME = time.time()

                            client = AsyncOpenAI(
                                api_key=api_key,
                                base_url=base_url,
                                http_client=http_client,
                                max_retries=0,
                                timeout=GROQ_HTTP_TIMEOUT_SECONDS,
                            )
                            content_arr = [{"type": "text", "text": system_prompt}]
                            for iu in processed_image_urls:
                                content_arr.append({"type": "image_url", "image_url": {"url": iu}})
                            
                            resp = await client.chat.completions.create(
                                model=model_name,
                                messages=[
                                    {
                                        "role": "user",
                                        "content": content_arr
                                    }
                                ],
                                max_tokens=600
                            )
                            content = resp.choices[0].message.content
                            if content:
                                if "<think>" in content:
                                    if "</think>" in content:
                                        content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
                                    else:
                                        parts = content.split("</think>", 1)
                                        if len(parts) > 1 and parts[1].strip():
                                            content = parts[1].strip()
                                        else:
                                            parts2 = content.split("<think>", 1)
                                            content = parts2[0].strip() or parts2[1].strip()
                                if "1. **Analyze" in content or "**Drafting" in content or "**Final Polish" in content:
                                    # Extract lines after final polish / final output
                                    match = re.search(r"(?:Final Polish|Final Output|Construct Final Output).*?\n(.*)", content, flags=re.DOTALL | re.IGNORECASE)
                                    if match and match.group(1).strip():
                                        content = match.group(1).strip()
                                    else:
                                        # Take non-bullet Russian lines
                                        lines = [l.strip() for l in content.split("\n") if l.strip() and not re.match(r"^\d+\.\s+\*\*", l.strip()) and not l.strip().startswith("**")]
                                        if lines:
                                            content = "\n".join(lines)
                                if content.strip():
                                    result_str = content.strip()
                                    logger.info(f"👁️ [VISION] [{source}] ✅ Success via {provider} ({model_name}): '{result_str[:250]}...'")
                                    return result_str

                        except Exception as e:
                            err_str = str(e).lower()
                            if "413" in err_str: return None
                            if "503" in err_str or "504" in err_str or "unavailable" in err_str or "500" in err_str:
                                logger.warning(f"⚠️ [VISION] [{source}] {provider} server overloaded ({err_str}). Skipping model {model_name}.")
                                break
                            if "429" in err_str or "rate limit" in err_str or "quota" in err_str:
                                logger.info(f"ℹ️ [VISION] [{source}] {provider} key rate limited (429), cooling down 2.5s...")
                                await asyncio.sleep(2.5)
                                continue
                            if provider == "gemini" and ("403" in err_str or "permission_denied" in err_str):
                                logger.error(f"❌ [VISION] [{source}] Gemini key {api_key[:12]}... is permanently banned (403). Removing from pool.")
                                BANNED_GEMINI_KEYS.add(api_key)
                                continue
                            logger.warning(f"⚠️ [VISION] [{source}] {provider} key failed ({model_name}): {e}")

            logger.error(f"❌ [VISION] [{source}] Image analysis failed: all vision models exhausted.")
            return None

        except Exception as e:
            logger.error(f"❌ [VISION] [{source}] Critical error in Vision module: {e}")
            return None
        finally:
            resized_bytes = None
            image_url = None
