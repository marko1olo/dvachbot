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

async def summarize_text_with_hf(prompt: str, text_dump: str, hf_token: str | None = None) -> str:
    """
    Summarize text using a cascade of OpenAI-compatible endpoints:
    1. Gemini API (gemini-3.0-flash)
    2. Groq API (llama-3.3-70b-versatile)
    """
    models_cascade = [
        ("gemini-3.5-flash", "gemini"),
        ("gemini-3.1-flash-lite", "gemini"),
        ("llama-3.3-70b-versatile", "groq")
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
            
        for api_key in keys:
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
                                max_tokens=2000,
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
                    if "429" in err_str or "rate limit" in err_str.lower() or "quota" in err_str.lower():
                        logger.warning(f"⚠️ {provider} Rate Limit. Switching key...")
                        break
                    continue

    return "Нейронка сдохла. Не удалось сгенерировать саммари."
