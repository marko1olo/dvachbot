from common.config import HTTP_LOCAL_ADDRESS
import os
import httpx
import logging
import asyncio
from openai import AsyncOpenAI
from common.token_pool import groq_pool

logger = logging.getLogger("summarize")

PROXY_URL = os.getenv("PROXY_URL") or os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY") or "http://127.0.0.1:10808"

GROQ_CONFIG = {
    "base_url": "https://api.groq.com/openai/v1",
    "model": "llama-3.3-70b-versatile", 
    "temperature": 0.8,
}

def _load_google_keys() -> list[str]:
    # Check .envgoogle
    if os.path.exists(".envgoogle"):
        try:
            with open(".envgoogle", "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("GOOGLE_API_KEYS="):
                        raw = line.split("=", 1)[1].strip()
                        return [k.strip() for k in raw.split(",") if k.strip()]
        except Exception as e:
            logger.warning(f"Error loading .envgoogle: {e}")
    # Fallback to .env
    raw_env = os.getenv("GOOGLE_API_KEYS", "")
    if raw_env:
        return [k.strip() for k in raw_env.split(",") if k.strip()]
    return []

<<<<<<< HEAD
async def summarize_text_with_hf(prompt: str, text_dump: str, hf_token: str | None = None, model_preference: str | None = None) -> str:
=======
async def summarize_text_with_gemini(prompt: str, text_dump: str, keys: list[str]) -> str | None:
    # Use gemini-2.5-flash as primary model
    model = "gemini-2.5-flash"
    strategies = [
        {"proxy": PROXY_URL, "name": "Proxy"},
        {"proxy": None, "name": "Direct"}
    ]
    
    for google_key in keys:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={google_key}"
        payload = {
            "contents": [{"role": "user", "parts": [{"text": text_dump}]}],
            "systemInstruction": {"parts": [{"text": prompt}]},
            "generationConfig": {
                "temperature": 0.8,
                "maxOutputTokens": 2000
            }
        }
        
        for strategy in strategies:
            try:
                transport = httpx.AsyncHTTPTransport(local_address=HTTP_LOCAL_ADDRESS, retries=1)
                async with httpx.AsyncClient(
                    proxy=strategy["proxy"], 
                    transport=transport,
                    verify=False,
                    timeout=10.0
                ) as client:
                    r = await client.post(url, json=payload)
                    if r.status_code == 200:
                        res = r.json()
                        text = res["candidates"][0]["content"]["parts"][0]["text"].strip()
                        if text:
                            logger.info(f"Gemini success using model {model} via {strategy['name']}")
                            return text
                    else:
                        logger.warning(f"Gemini model {model} failed via {strategy['name']}: {r.status_code}")
            except Exception as e:
                logger.warning(f"Gemini request failed via {strategy['name']}: {type(e).__name__}: {e}")
    return None

async def summarize_text_with_hf(prompt: str, text_dump: str, hf_token: str | None = None) -> str:
>>>>>>> 8e1f7bb (Save my changes)
    """
    Summarize text using a cascade of OpenAI-compatible endpoints:
    Supports choosing model/provider: gemini, qwen, llama, or default groq (Qwen + Llama + Gemini fallback).
    """
    if model_preference == "gemini":
        models_cascade = [
            ("gemini-3-flash-preview", "gemini"),
            ("gemini-3.1-flash-lite", "gemini"),
        ]
    elif model_preference == "qwen":
        models_cascade = [
            ("qwen/qwen3.6-27b", "groq")
        ]
    elif model_preference == "llama":
        models_cascade = [
            ("llama-3.3-70b-versatile", "groq")
        ]
    else:
        # Default: Groq first (free), Gemini as fallback for large chunks
        models_cascade = [
            ("gemini-3-flash-preview", "gemini"),
            ("gemini-3.1-flash-lite", "gemini"),
            ("qwen/qwen3.6-27b", "groq"),
            ("llama-3.3-70b-versatile", "groq"),
        ]

    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": text_dump}
    ]
    
    strategies = [
        {"proxy": PROXY_URL, "name": "Proxy"},
        {"proxy": None, "name": "Direct"}
    ]

    for model_name, provider in models_cascade:
        if provider == "gemini":
            keys = _load_google_keys()
            base_url = "https://generativelanguage.googleapis.com/v1beta/openai/"
        else:
            keys = []
            for _ in range(5):
                token = groq_pool.get_token()
                if token and token not in keys:
                    keys.append(token)
            base_url = "https://api.groq.com/openai/v1"

        if not keys:
            logger.warning(f"No keys for provider {provider}. Skipping model {model_name}.")
            continue

        skip_model = False
        for api_key in keys:
            if skip_model:
                break
            for strategy in strategies:
                try:
                    transport = httpx.AsyncHTTPTransport(local_address="0.0.0.0", retries=1)
                    async with httpx.AsyncClient(
                        proxy=strategy["proxy"],
                        transport=transport,
                        verify=False,
                        timeout=15.0
                    ) as http_client:

                        async with AsyncOpenAI(
                            api_key=api_key if api_key else "dummy",
                            base_url=base_url,
                            http_client=http_client,
                            max_retries=0
                        ) as client:
                            completion = await client.chat.completions.create(
                                model=model_name,
                                messages=messages,
                                temperature=0.8
                            )
                            if completion.choices and len(completion.choices) > 0:
                                result = completion.choices[0].message.content
                                if result:
                                    import re
                                    result = re.sub(r"<think>.*?</think>", "", result, flags=re.DOTALL).strip()
                                    logger.info(f"Success using model {model_name} via {provider} ({strategy['name']})")
                                    return result.strip()
                except Exception as e:
                    err_str = f"{type(e).__name__}: {e}"
                    logger.warning(f"⚠️ {provider} call failed ({model_name}) via {strategy['name']}: {err_str}")
                    if provider == "groq" and ("401" in err_str or "unauthorized" in err_str.lower() or "invalid api key" in err_str.lower()):
                        logger.error(f"❌ Groq key {api_key[:12]}... is unauthorized (401). Removing from rotation pool.")
                        groq_pool.remove_token(api_key)
                        break
                    if "413" in err_str or "too large" in err_str.lower() or "context_length_exceeded" in err_str.lower():
                        logger.warning(f"⚠️ {model_name}: request too large, skipping to next model.")
                        skip_model = True
                        break
                    if "429" in err_str or "rate limit" in err_str.lower() or "quota" in err_str.lower():
                        logger.warning(f"⚠️ {provider} Rate Limit. Switching key...")
                        break
                    continue

<<<<<<< HEAD
=======
        for strategy in strategies:
            try:
                transport = httpx.AsyncHTTPTransport(local_address=HTTP_LOCAL_ADDRESS, retries=1)
                async with httpx.AsyncClient(
                    proxy=strategy["proxy"], 
                    transport=transport,
                    verify=False,
                    timeout=10.0
                ) as http_client:
                    
                    async with AsyncOpenAI(
                        api_key=api_key, 
                        base_url=GROQ_CONFIG["base_url"],
                        http_client=http_client
                    ) as client:
                        completion = await client.chat.completions.create(
                            model=target_model,
                            messages=messages,
                            max_tokens=2000,
                            temperature=GROQ_CONFIG["temperature"]
                        )
                        result = completion.choices[0].message.content.strip()
                        if result:
                            logger.info(f"Groq fallback success using model {target_model} via {strategy['name']}")
                            return result
            except Exception as e:
                err_str = f"{type(e).__name__}: {e}"
                logger.warning(f"⚠️ Groq call failed via {strategy['name']}: {err_str}")
                if "429" in err_str or "rate limit" in err_str.lower():
                    logger.warning("⚠️ Groq Rate Limit. Switching key...")
                    break
                continue
                
>>>>>>> 8e1f7bb (Save my changes)
    return "Нейронка сдохла. Не удалось сгенерировать саммари."


TELEGRAPH_TOKEN_FILE = os.path.join("data", "telegraph_token.txt")
_telegraph_token_cache = None

def get_telegraph_token() -> str:
    global _telegraph_token_cache
    if _telegraph_token_cache:
        return _telegraph_token_cache

    # Try environment variable first (same as stomchat)
    env_token = os.getenv("TELEGRAPH_TOKEN")
    if env_token:
        _telegraph_token_cache = env_token.strip()
        return _telegraph_token_cache

    if os.path.exists(TELEGRAPH_TOKEN_FILE):
        try:
            with open(TELEGRAPH_TOKEN_FILE, "r", encoding="utf-8") as f:
                token = f.read().strip()
                if token:
                    _telegraph_token_cache = token
                    return token
        except Exception:
            pass
    try:
        from html_telegraph_poster import TelegraphPoster
        poster = TelegraphPoster(use_api=True)
        poster.create_api_token("tgach_bot", "ТГАЧ")
        token = poster.access_token
        if token:
            os.makedirs("data", exist_ok=True)
            with open(TELEGRAPH_TOKEN_FILE, "w", encoding="utf-8") as f:
                f.write(token)
            _telegraph_token_cache = token
            return token
    except Exception as e:
        logger.error(f"Failed to generate Telegraph token: {e}")
    return ""

def _create_telegraph_page_blocking(title: str, html_content: str, author: str = "ТГАЧ") -> str:
    from html_telegraph_poster import TelegraphPoster
    token = get_telegraph_token()
    poster = TelegraphPoster(use_api=True, access_token=token)

    # Format line breaks as <br> for Telegraph
    formatted_body = html_content.replace("\n", "<br>")

    page = poster.post(
        title=title,
        author=author,
        text=formatted_body
    )
    return page["url"]

async def create_telegraph_page_async(title: str, html_content: str, author: str = "ТГАЧ") -> str | None:
    try:
        url = await asyncio.to_thread(_create_telegraph_page_blocking, title, html_content, author)
        return url
    except Exception as e:
        logger.error(f"Failed to create Telegraph page: {e}")
        return None
