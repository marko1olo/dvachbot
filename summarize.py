import os
import httpx
import logging
from openai import AsyncOpenAI
from common.token_pool import groq_pool

logger = logging.getLogger("summarize")

PROXY_URL = "http://127.0.0.1:10808" 

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
                "maxOutputTokens": 300
            }
        }
        
        for strategy in strategies:
            try:
                transport = httpx.AsyncHTTPTransport(local_address="0.0.0.0", retries=1)
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
    """
    Summarize text using Google Gemini API (gemini-2.5-flash) as primary.
    If Gemini fails, falls back to Groq API (llama-3.3-70b-versatile).
    """
    # 1. Try Google Gemini first
    google_keys = _load_google_keys()
    if google_keys:
        logger.info("Attempting primary Gemini summarization...")
        gemini_summary = await summarize_text_with_gemini(prompt, text_dump, google_keys)
        if gemini_summary:
            return gemini_summary
        logger.warning("Gemini phase failed. Falling back to Groq...")
    else:
        logger.warning("No Google API keys found. Skipping Gemini phase...")

    # 2. Fallback to Groq API
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": text_dump}
    ]
    target_model = GROQ_CONFIG["model"]
    
    for i in range(3):
        api_key = groq_pool.get_token()
        if not api_key: 
            logger.warning("No Groq API keys available. Skipping Groq phase.")
            break

        strategies = [
            {"proxy": PROXY_URL, "name": "Proxy"},
            {"proxy": None, "name": "Direct"}
        ]

        for strategy in strategies:
            try:
                transport = httpx.AsyncHTTPTransport(local_address="0.0.0.0", retries=1)
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
                            max_tokens=300,
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
                
    return "Нейронка сдохла. Не удалось сгенерировать саммари."
