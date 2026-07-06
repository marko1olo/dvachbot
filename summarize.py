import os
import socket
import httpx
import logging
import asyncio
from html.parser import HTMLParser
from openai import AsyncOpenAI
from common.token_pool import groq_pool

logger = logging.getLogger("summarize")

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

async def summarize_text_with_hf(prompt: str, text_dump: str, hf_token: str | None = None, model_preference: str | None = None) -> str:
    """
    Summarize text using a cascade of OpenAI-compatible endpoints:
    Supports choosing model/provider: gemini, qwen, llama, or default groq (Qwen + Llama + Gemini fallback).
    """
    if model_preference == "gemini":
        models_cascade = [
            ("gemini-3.5-flash", "gemini"),
            ("gemini-3.1-flash-lite", "gemini"),
            ("gemini-3.1-pro", "gemini"),
            ("gemini-2.5-flash", "gemini"),  # fallback if 3.x not on key
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
        # Default: Gemini 3.x first, Groq as fallback
        models_cascade = [
            ("gemini-3.5-flash", "gemini"),
            ("gemini-3.1-flash-lite", "gemini"),
            ("gemini-2.5-flash", "gemini"),  # fallback if 3.x not on key
            ("qwen/qwen3.6-27b", "groq"),
            ("llama-3.3-70b-versatile", "groq"),
        ]
    
    system_instruction = prompt + (
        "\n\nCRITICAL REQUIREMENT:\n"
        "You must output ONLY valid HTML using only <b>, <i>, <u>, <s>, <code>, <pre>, <a> tags. "
        "Strictly avoid any markdown formatting elements (never use asterisks '**', never use raw markdown lists like '* item' or '- item'). "
        "All output must be parsable by Telegram's HTML parser. If you format lists, use <b>•</b> or regular bullet characters instead of hyphens/asterisks."
    )
    
    messages = [
        {"role": "system", "content": system_instruction},
        {"role": "user", "content": text_dump}
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
            try:
                # Strictly bypass .env proxies and let OS route directly through WireGuard VPN
                async with httpx.AsyncClient(
                    proxy=None,
                    verify=False,
                    timeout=30.0,
                    trust_env=False
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
                                logger.info(f"Success using model {model_name} via {provider} (Direct VPN)")
                                return result.strip()
            except Exception as e:
                err_str = f"{type(e).__name__}: {e}"
                logger.warning(f"⚠️ {provider} call failed ({model_name}): {err_str[:120]}")
                if provider == "groq" and ("401" in err_str or "unauthorized" in err_str.lower() or "invalid api key" in err_str.lower()):
                    logger.error(f"❌ Groq key {api_key[:12]}... is unauthorized (401). Removing from rotation pool.")
                    groq_pool.remove_token(api_key)
                    break
                if "413" in err_str or "too large" in err_str.lower() or "context_length_exceeded" in err_str.lower():
                    logger.warning(f"⚠️ {model_name}: request too large. Shrinking by 40% and retrying...")
                    half_len = int(len(text_dump) * 0.6)
                    text_dump = text_dump[-half_len:]
                    messages[1]["content"] = text_dump
                    continue
                if "429" in err_str or "rate limit" in err_str.lower() or "quota" in err_str.lower():
                    logger.warning(f"⚠️ {provider} Rate Limit. Cooling down 1.5s...")
                    await asyncio.sleep(1.5)
                    break  # next key
                break  # any other error — try next key

    return "Нейронка сдохла. Не удалось сгенерировать саммари."


TELEGRAPH_TOKEN_FILE = os.path.join("data", "telegraph_token.txt")
_telegraph_token_cache = None

def _telegraph_request_sync(method: str, params: dict) -> dict:
    """Make a direct (no proxy) HTTP request to Telegraph API."""
    import requests
    url = f"https://api.telegra.ph/{method}"
    # Explicitly bypass proxy for Telegraph - SOCKS on 10808 is not for external APIs
    resp = requests.get(url, params=params, timeout=15, proxies={"http": None, "https": None})
    resp.raise_for_status()
    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegraph API error: {data.get('error', 'unknown')}")
    return data["result"]

def _telegraph_create_account_sync() -> str:
    """Create a Telegraph account and return the access token."""
    result = _telegraph_request_sync("createAccount", {
        "short_name": "tgach_bot",
        "author_name": "ТГАЧ"
    })
    return result.get("access_token", "")

def _telegraph_create_page_sync(token: str, title: str, content_nodes: list) -> str:
    """Create a Telegraph page and return its URL."""
    import json
    import requests
    url = "https://api.telegra.ph/createPage"
    payload = {
        "access_token": token,
        "title": title[:256],  # Telegraph title limit
        "content": json.dumps(content_nodes),
        "return_content": "false"
    }
    resp = requests.post(url, data=payload, timeout=20, proxies={"http": None, "https": None})
    resp.raise_for_status()
    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegraph createPage error: {data.get('error', 'unknown')}")
    return data["result"]["url"]

def get_telegraph_token() -> str:
    global _telegraph_token_cache
    if _telegraph_token_cache:
        return _telegraph_token_cache
    
    # Try environment variable first
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
        token = _telegraph_create_account_sync()
        if token:
            os.makedirs("data", exist_ok=True)
            with open(TELEGRAPH_TOKEN_FILE, "w", encoding="utf-8") as f:
                f.write(token)
            _telegraph_token_cache = token
            return token
    except Exception as e:
        logger.error(f"Failed to generate Telegraph token: {e}")
    return ""

class TelegraphHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack = [{"tag": "p", "children": []}]
        self.allowed_tags = {"b", "i", "u", "s", "code", "pre", "a", "p", "br", "h3", "h4"}

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag not in self.allowed_tags:
            return
        
        node = {"tag": tag}
        if attrs:
            node["attrs"] = {name: val for name, val in attrs if val is not None}
        node["children"] = []
        
        self.stack[-1]["children"].append(node)
        self.stack.append(node)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag not in self.allowed_tags:
            return
        
        temp = []
        while len(self.stack) > 1 and self.stack[-1]["tag"] != tag:
            temp.append(self.stack.pop())
        
        if len(self.stack) > 1:
            self.stack.pop()
        else:
            self.stack.extend(reversed(temp))

    def handle_data(self, data):
        if data:
            self.stack[-1]["children"].append(data)

def _text_to_telegraph_nodes(html_content: str) -> list:
    """Convert HTML/plain text to Telegraph Node objects by parsing HTML tags correctly."""
    parser = TelegraphHTMLParser()
    try:
        parser.feed(html_content)
        parser.close()
    except Exception as e:
        logger.error(f"HTML parsing failed for Telegraph node conversion: {e}")
        return [{"tag": "p", "children": [html_content]}]
    
    root_children = parser.stack[0]["children"]
    block_tags = {"p", "pre", "h3", "h4", "br"}
    nodes = []
    current_paragraph = []

    def flush_paragraph():
        if current_paragraph:
            nodes.append({"tag": "p", "children": list(current_paragraph)})
            current_paragraph.clear()

    for child in root_children:
        if isinstance(child, dict) and child.get("tag") in block_tags:
            flush_paragraph()
            if child["tag"] == "br":
                nodes.append({"tag": "p", "children": [""]})
            else:
                nodes.append(child)
        else:
            current_paragraph.append(child)
            
    flush_paragraph()
    
    if not nodes:
        nodes = [{"tag": "p", "children": [""]}]
    return nodes

def _create_telegraph_page_blocking(title: str, html_content: str, author: str = "ТГАЧ") -> str:
    token = get_telegraph_token()
    if not token:
        raise RuntimeError("API token is required")
    nodes = _text_to_telegraph_nodes(html_content)
    return _telegraph_create_page_sync(token, title, nodes)

async def create_telegraph_page_async(title: str, html_content: str, author: str = "ТГАЧ") -> str | None:
    try:
        url = await asyncio.to_thread(_create_telegraph_page_blocking, title, html_content, author)
        return url
    except Exception as e:
        logger.error(f"Failed to create Telegraph page: {e}")
        return None

