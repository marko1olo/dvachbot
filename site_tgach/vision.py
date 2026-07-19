import base64
import logging
import random
import asyncio
import time
import os
import httpx
import io
from PIL import Image
from openai import AsyncOpenAI

import config
from media_tools import prepare_image_for_analysis

logger = logging.getLogger(__name__)
GROQ_COOLDOWN_UNTIL = 0
_VISION_SEMAPHORE = None


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
    from media_tools import _prepare_image_sync
    return _prepare_image_sync(file_path)
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

        # Лимит Groq жесток. Ужимаем до 800px по большей стороне.
        # Этого достаточно для диагностики, но экономит трафик.
        MAX_SIZE = 1000
        if max(img.size) > MAX_SIZE:
            img.thumbnail((MAX_SIZE, MAX_SIZE), Image.Resampling.LANCZOS)

        with io.BytesIO() as buffer:
            # Quality=70 - золотая середина для веса/качества
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

async def describe_image(file_paths, caption: str = None, is_passive: bool = False) -> str:
    """Анализирует изображение(я) через каскад Vision (Gemini 3.5 -> Qwen 3.6 -> Llama 4 Scout)."""
    global GROQ_COOLDOWN_UNTIL
    global _LAST_VISION_CALL_TIME

    if time.time() < GROQ_COOLDOWN_UNTIL:
        return None

    if isinstance(file_paths, str):
        file_paths = [file_paths]

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
                logger.error("Ошибка подготовки фото: ни одно фото не удалось обработать.")
                return None

            context = f" Context from the author: '{caption}'." if caption else ""
            system_prompt = (
                f"This is a dental image from a professional chat.{context} "
                f"Describe what you see in Russian (pathology, clinical step, or materials). If there is any text, analyze it (make conclusion). If picture is not medical, describe it briefly. "
                f"Be professional. (Write up to 4-6 sentences). "
                f"Respond directly. Do not use reasoning/thinking blocks. Do not output <think> tags."
            )
            
            if is_passive:
                # Cheaper/lighter models for passive background image description
                models_cascade = [
                    ("gemini-3.1-flash-lite", "gemini"),
                    ("qwen/qwen3.6-27b", "groq"),
                    ("meta-llama/llama-4-scout-17b-16e-instruct", "groq")
                ]
            else:
                # Best quality models for active bot mentions/calls/PMs
                models_cascade = [
                    ("gemini-3.5-flash", "gemini"),
                    ("gemini-3.1-flash-lite", "gemini"),
                    ("gemini-3-flash-preview", "gemini"),
                    ("gemini-2.5-flash", "gemini"),
                    ("qwen/qwen3.6-27b", "groq"),
                    ("meta-llama/llama-4-scout-17b-16e-instruct", "groq")
                ]

            timeout = httpx.Timeout(
                GROQ_HTTP_TIMEOUT_SECONDS,
                connect=min(10.0, GROQ_HTTP_TIMEOUT_SECONDS),
                read=GROQ_HTTP_TIMEOUT_SECONDS,
                write=min(15.0, GROQ_HTTP_TIMEOUT_SECONDS),
                pool=5.0,
            )

            async with httpx.AsyncClient(verify=False, timeout=timeout) as http_client:
                for model_name, provider in models_cascade:
                    if provider == "gemini":
                        keys = list(config.GOOGLE_KEYS)
                        base_url = "https://generativelanguage.googleapis.com/v1beta/openai/"
                    else:
                        keys = list(config.GROQ_KEYS)
                        base_url = "https://api.groq.com/openai/v1"
                        
                    if not keys:
                        continue
                        
                    random.shuffle(keys)
                    
                    for api_key in keys:
                        try:
                            # Enforce global cooldown of 3 seconds between requests
                            time_since_last_call = time.time() - _LAST_VISION_CALL_TIME
                            if time_since_last_call < 3.0:
                                await asyncio.sleep(3.0 - time_since_last_call)
                            _LAST_VISION_CALL_TIME = time.time()

                            if provider == "gemini":
                                from google import genai
                                from google.genai import types
                                client = genai.Client(api_key=api_key)
                                
                                contents = [system_prompt]
                                for img_bytes in images_data:
                                    contents.append(types.Part.from_bytes(
                                        data=img_bytes,
                                        mime_type="image/jpeg"
                                    ))
                                
                                safety_settings = [
                                    types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_NONE"),
                                    types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_NONE"),
                                    types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="BLOCK_NONE"),
                                    types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="BLOCK_NONE")
                                ]
                                gen_config = types.GenerateContentConfig(safety_settings=safety_settings)
                                
                                response = await client.aio.models.generate_content(
                                    model=model_name,
                                    contents=contents,
                                    config=gen_config
                                )
                                content = response.text
                            else:
                                client = AsyncOpenAI(
                                    api_key=api_key,
                                    base_url=base_url,
                                    http_client=http_client,
                                    max_retries=0,
                                    timeout=GROQ_HTTP_TIMEOUT_SECONDS,
                                )
                                content_arr = [{"type": "text", "text": system_prompt}]
                                for iu in image_urls:
                                    content_arr.append({"type": "image_url", "image_url": {"url": iu}})
                                
                                resp = await client.chat.completions.create(
                                    model=model_name,
                                    messages=[
                                        {
                                            "role": "user",
                                            "content": content_arr
                                        }
                                    ],
                                    max_tokens=1024
                                )
                                content = resp.choices[0].message.content
                            if content:
                                import re
                                if "<think>" in content:
                                    if "</think>" in content:
                                        content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
                                    else:
                                        parts = content.split("<think>", 1)
                                        content = parts[0].strip()
                                if content.strip():
                                    logger.info(f"Vision success via {provider} ({model_name})")
                                    return content.strip()

                        except Exception as e:
                            err_str = str(e).lower()
                            if "413" in err_str: return None
                            if "503" in err_str or "504" in err_str or "unavailable" in err_str or "500" in err_str:
                                logger.warning(f"Vision {provider} server overloaded ({err_str}). Skipping model {model_name}.")
                                break
                            if "429" in err_str or "rate limit" in err_str or "quota" in err_str:
                                logger.info(f"Vision key rate limited (429), cooling down 2.5s before next attempt...")
                                await asyncio.sleep(2.5)
                                continue
                            logger.warning(f"Vision {provider} key failed ({model_name}): {e}")

            GROQ_COOLDOWN_UNTIL = time.time() + 60
            return None

        except Exception as e:
            logger.error(f"Ошибка в модуле Vision: {e}")
            return None
        finally:
            resized_bytes = None
            image_url = None
