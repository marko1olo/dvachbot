import os
import httpx
import logging
import asyncio
from html.parser import HTMLParser
from openai import AsyncOpenAI
from common.token_pool import groq_pool, google_pool
from common.text_utils import clean_ai_thinking, strip_thinking_tags

logger = logging.getLogger("summarize")

GROQ_CONFIG = {
    "base_url": "https://api.groq.com/openai/v1",
    "model": "qwen/qwen3.6-27b", 
    "temperature": 0.8,
}

_SHARED_HTTP_CLIENT = None
# Ограничиваем параллельные LLM-вызовы Персоны: строго 1 одновременно
# Иначе 10+ конкурентных горутин дёргают все ключи одновременно и спамят 429
_PERSONA_SEMAPHORE: asyncio.Semaphore | None = None

def _get_persona_semaphore() -> asyncio.Semaphore:
    global _PERSONA_SEMAPHORE
    if _PERSONA_SEMAPHORE is None:
        _PERSONA_SEMAPHORE = asyncio.Semaphore(1)
    return _PERSONA_SEMAPHORE



def get_shared_http_client() -> httpx.AsyncClient:
    global _SHARED_HTTP_CLIENT
    if _SHARED_HTTP_CLIENT is None or getattr(_SHARED_HTTP_CLIENT, "is_closed", False):
        _SHARED_HTTP_CLIENT = httpx.AsyncClient(
            proxy=None,
            verify=False,
            timeout=60.0,
            trust_env=False,
            limits=httpx.Limits(max_keepalive_connections=50, max_connections=100)
        )
    return _SHARED_HTTP_CLIENT

async def close_shared_http_client() -> None:
    global _SHARED_HTTP_CLIENT
    if _SHARED_HTTP_CLIENT is not None and not getattr(_SHARED_HTTP_CLIENT, "is_closed", False):
        try:
            await _SHARED_HTTP_CLIENT.aclose()
        except Exception:
            pass
        _SHARED_HTTP_CLIENT = None


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

_key_cooldowns: dict[tuple[str, str], float] = {}
_provider_cooldowns: dict[str, float] = {}

async def summarize_text_with_hf(prompt: str, text_dump: str, model_preference: str | None = None) -> str:
    """
    Summarize text using a cascade of OpenAI-compatible endpoints:
    Supports choosing model/provider: gemini, qwen, llama, or default groq (Qwen + Llama + Gemini fallback).
    Prioritizes 500 RPD Gemini Lite models to maximize free quota.
    """
    if model_preference == "persona" or model_preference == "persona_gemini":
        # Persona Bot: строго 1 параллельный вызов через семафор
        async with _get_persona_semaphore():
            return await _summarize_inner(prompt, text_dump, None, model_preference)
    return await _summarize_inner(prompt, text_dump, None, model_preference)


async def _summarize_inner(prompt: str, text_dump: str, hf_token: str | None = None, model_preference: str | None = None) -> str:
    if model_preference in ("persona", "persona_gemini"):
        models_cascade = [
            ("gemini-3.5-flash-lite", "gemini"),
            ("gemini-3.1-flash-lite", "gemini"),
            ("qwen/qwen3.6-27b", "groq"),
            ("gemini-3.6-flash", "gemini"),
            ("gemini-3.7-flash", "gemini"),
        ]
    elif model_preference == "fast":
        models_cascade = [
            ("gemini-3.5-flash-lite", "gemini"),
            ("gemini-3.1-flash-lite", "gemini"),
            ("qwen/qwen3.6-27b", "groq"),
            ("gemini-3.6-flash", "gemini"),
        ]
    elif model_preference == "gemini":
        models_cascade = [
            ("gemini-3.5-flash-lite", "gemini"),
            ("gemini-3.1-flash-lite", "gemini"),
            ("gemini-3.6-flash", "gemini"),
            ("gemini-3.7-flash", "gemini"),
            ("qwen/qwen3.6-27b", "groq"),
        ]
    elif model_preference in ("qwen", "llama", "groq"):
        models_cascade = [
            ("qwen/qwen3.6-27b", "groq"),
            ("gemini-3.5-flash-lite", "gemini"),
            ("gemini-3.1-flash-lite", "gemini"),
            ("gemini-3.6-flash", "gemini"),
        ]
    else:
        # Default summarization cascade: Lite -> Qwen -> Fallback Flash
        models_cascade = [
            ("gemini-3.5-flash-lite", "gemini"),
            ("gemini-3.1-flash-lite", "gemini"),
            ("qwen/qwen3.6-27b", "groq"),
            ("gemini-3.6-flash", "gemini"),
            ("gemini-3.7-flash", "gemini"),
        ]

    
    system_instruction = prompt + (
        "\n\nCRITICAL OUTPUT FORMAT RULES:\n"
        "ALLOWED tags (ONLY these): <b>, <i>, <u>, <s>, <code>, <pre>, <a href=\"...\">.\n"
        "FORBIDDEN tags (NEVER use): <p>, <div>, <span>, <br>, <hr>, <h1>, <h2>, <h3>, <h4>, <h5>, <h6>, <ul>, <ol>, <li>, <table>, <tr>, <td>, <th>, <em>, <strong>, <section>, <article>, and ANY other HTML tag not listed above.\n"
        "FORBIDDEN formatting: Never use Markdown (no **bold**, no *italic*, no # headings, no - lists, no * lists).\n"
        "Separate paragraphs with a blank line (two newlines), NOT with <p> tags.\n"
        "For bullet lists use • character with a newline, NOT <ul>/<li> tags.\n"
        "Output must be parseable by Telegram Bot API HTML parser."
    )
    
    messages = [
        {"role": "system", "content": system_instruction},
        {"role": "user", "content": text_dump}
    ]

    import time
    now_ts = time.time()

    for model_name, provider in models_cascade:
        if _provider_cooldowns.get(provider, 0) > now_ts:
            logger.info(f"{provider} is in TPD cooldown ({_provider_cooldowns[provider] - now_ts:.1f}s remaining). Skipping model {model_name}.")
            continue

        if provider == "gemini":
            keys = google_pool.get_all_active_tokens()
            base_url = "https://generativelanguage.googleapis.com/v1beta/openai/"
        else:
            keys = groq_pool.get_all_active_tokens()
            base_url = "https://api.groq.com/openai/v1"
            
        if not keys:
            logger.warning(f"No keys for provider {provider}. Skipping model {model_name}.")
            continue
            
        # Filter out keys that are currently in 429 cooldown
        active_keys = [k for k in keys if _key_cooldowns.get((provider, k), 0) <= now_ts]
        if not active_keys:
            logger.info(f"All keys for {provider} are in cooldown. Skipping model {model_name}.")
            continue

        model_max_tokens = None if provider == "gemini" else 6000

        skip_model = False
        consecutive_429 = 0
        for api_key in active_keys:
            if skip_model:
                break
            try:
                http_client = get_shared_http_client()
                client = AsyncOpenAI(
                    api_key=api_key if api_key else "dummy", 
                    base_url=base_url,
                    http_client=http_client,
                    max_retries=0
                )
                create_kwargs = dict(
                    model=model_name,
                    messages=messages,
                    temperature=0.8,
                    timeout=15.0,
                )
                if model_max_tokens is not None:
                    create_kwargs["max_tokens"] = model_max_tokens
                completion = await client.chat.completions.create(**create_kwargs)
                if completion.choices and len(completion.choices) > 0:
                    choice = completion.choices[0]
                    if choice.message is not None:
                        result = choice.message.content
                        if result:
                            result = clean_ai_thinking(result)
                            if result:
                                return result
                            else:
                                logger.warning(f"Model {model_name} returned empty text after <think> stripping")
                                raise ValueError("Model returned empty text after <think> stripping")
            except Exception as e:
                err_str = str(e)
                logger.warning(f"⚠️ {provider} call failed ({model_name}) key=...{api_key[-6:]}: {err_str[:120]}")
                if "404" in err_str or "model_not_found" in err_str or "does not exist" in err_str.lower():
                    logger.warning(f"⚠️ {provider} model {model_name} not found (404). Skipping model.")
                    break
                if "401" in err_str or "unauthorized" in err_str.lower() or "invalid api key" in err_str.lower():
                    logger.error(f"❌ {provider} key {api_key[:12]}... is unauthorized (401). Removing from pool.")
                    if provider == "gemini":
                        google_pool.remove_token(api_key)
                    else:
                        groq_pool.remove_token(api_key)
                    await asyncio.sleep(2.5)
                    continue  # try next key
                if "413" in err_str or "too large" in err_str.lower() or "context_length_exceeded" in err_str.lower():
                    logger.warning(f"⚠️ {model_name}: request too large. Shrinking by 40% and retrying...")
                    half_len = int(len(text_dump) * 0.6)
                    text_dump = text_dump[-half_len:]
                    messages[1]["content"] = text_dump
                    await asyncio.sleep(2.5)
                    continue  # retry same key with smaller input
                if "403" in err_str:
                    # 403 = this specific key/project is banned. Cooldown it and try the NEXT KEY.
                    _key_cooldowns[(provider, api_key)] = time.time() + 3600.0  # 1h cooldown for banned keys
                    if provider == "gemini":
                        google_pool.ban_token(api_key)
                    else:
                        groq_pool.ban_token(api_key)
                    logger.warning(f"⚠️ {provider} key ...{api_key[-6:]} is 403 BANNED for {model_name}. Trying next key...")
                    await asyncio.sleep(3.0)
                    continue  # try next key, NOT next model
                if "tokens per day" in err_str.lower() or "tpd" in err_str.lower():
                    logger.warning(f"⚠️ {provider} daily token limit (TPD) reached for {model_name}. Pausing {provider} for 15m.")
                    _provider_cooldowns[provider] = time.time() + 900.0
                    break
                if "429" in err_str or "rate limit" in err_str.lower() or "quota" in err_str.lower() or "exhausted" in err_str.lower():
                    consecutive_429 += 1
                    _key_cooldowns[(provider, api_key)] = time.time() + 120.0
                    if provider == "gemini":
                        google_pool.penalize_token(api_key, 120.0)
                    else:
                        groq_pool.penalize_token(api_key, 120.0)
                    logger.warning(f"⚠️ {provider} key ...{api_key[-6:]} rate limited (429) for {model_name}.")
                    if consecutive_429 >= 2:
                        logger.warning(f"⚠️ {provider} hit multiple consecutive 429s ({consecutive_429}) for {model_name}. Halting {provider} attempts to protect keys from spam.")
                        break
                    await asyncio.sleep(3.0)
                    continue  # try next key
                if "timeout" in err_str.lower() or "timed out" in err_str.lower():
                    logger.warning(f"⚠️ {provider} request timed out for {model_name}. Trying next candidate...")
                    break
                # Any other error: skip model entirely
                logger.warning(f"⚠️ Unhandled error for {model_name}: {err_str[:80]}. Skipping model.")
                await asyncio.sleep(0.5)
                break


    return "Нейронка сдохла. Не удалось сгенерировать саммари."


TELEGRAPH_TOKEN_FILE = os.path.join("data", "telegraph_token.txt")
_telegraph_token_cache = None

def _telegraph_request_sync(method: str, params: dict) -> dict:
    """Make a direct (no proxy) HTTP request to Telegraph API."""
    import requests
    import time
    url = f"https://api.telegra.ph/{method}"
    # Explicitly bypass proxy for Telegraph - SOCKS on 10808 is not for external APIs
    last_err = None
    for attempt in range(3):
        try:
            resp = requests.get(url, params=params, timeout=15, proxies={"http": None, "https": None})
            resp.raise_for_status()
            data = resp.json()
            if not data.get("ok"):
                raise RuntimeError(f"Telegraph API error: {data.get('error', 'unknown')}")
            return data["result"]
        except Exception as e:
            last_err = e
            time.sleep(2 * (attempt + 1))
            
    raise RuntimeError(f"Telegraph request failed after 3 attempts: {last_err}")

def _telegraph_create_account_sync() -> str:
    """Create a Telegraph account and return the access token."""
    result = _telegraph_request_sync("createAccount", {
        "short_name": "tgach_bot",
        "author_name": "ТГАЧ"
    })
    return result.get("access_token", "")

def _telegraph_create_page_sync(token: str, title: str, content_nodes: list) -> str:
    """Create a Telegraph page and return its URL with auto-shrinking if CONTENT_TOO_BIG."""
    import json
    import requests
    import time
    url = "https://api.telegra.ph/createPage"
    
    def _get_payload_size(nodes: list) -> int:
        return len(json.dumps(nodes, ensure_ascii=False).encode('utf-8'))

    # Ensure initial payload is safely under Telegraph's limit (<= 55,000 bytes)
    while _get_payload_size(content_nodes) > 55000:
        if len(content_nodes) > 1:
            if isinstance(content_nodes[-1], dict) and content_nodes[-1].get("children") == [{"tag": "i", "children": ["... (Текст сокращен из-за лимита Telegraph)"]}]:
                content_nodes.pop()
            new_len = max(1, int(len(content_nodes) * 0.75))
            if new_len >= len(content_nodes):
                new_len = len(content_nodes) - 1
            content_nodes = content_nodes[:new_len]
            content_nodes.append({"tag": "p", "children": [{"tag": "i", "children": ["... (Текст сокращен из-за лимита Telegraph)"]}]})
        else:
            # Single massive node: truncate text inside the node
            node = content_nodes[0]
            if isinstance(node, dict) and "children" in node and node["children"]:
                first_child = node["children"][0]
                if isinstance(first_child, str):
                    node["children"][0] = first_child[:8000] + "… (Текст сокращен из-за лимита Telegraph)"
                else:
                    node["children"] = ["... (Текст сокращен из-за лимита Telegraph)"]
            else:
                content_nodes = [{"tag": "p", "children": ["... (Текст сокращен из-за лимита Telegraph)"]}]
            break

    payload = {
        "access_token": token,
        "title": title[:256],  # Telegraph title limit
        "content": json.dumps(content_nodes, ensure_ascii=False),
        "return_content": "false"
    }
    
    last_err = None
    for attempt in range(4):
        try:
            resp = requests.post(url, data=payload, timeout=20, proxies={"http": None, "https": None})
            resp.raise_for_status()
            data = resp.json()
            if not data.get("ok"):
                err_str = str(data.get("error", "unknown"))
                if "CONTENT_TOO_BIG" in err_str:
                    logger.warning(f"Telegraph reported CONTENT_TOO_BIG on attempt {attempt}, reducing nodes...")
                    if isinstance(content_nodes[-1], dict) and content_nodes[-1].get("children") == [{"tag": "i", "children": ["... (Текст сокращен из-за лимита Telegraph)"]}]:
                        content_nodes.pop()
                    if len(content_nodes) > 1:
                        new_len = max(1, int(len(content_nodes) * 0.6))
                        if new_len >= len(content_nodes):
                            new_len = len(content_nodes) - 1
                        content_nodes = content_nodes[:new_len]
                        content_nodes.append({"tag": "p", "children": [{"tag": "i", "children": ["... (Текст сокращен из-за лимита Telegraph)"]}]})
                    else:
                        content_nodes = [{"tag": "p", "children": ["... (Текст сокращен из-за лимита Telegraph)"]}]
                    payload["content"] = json.dumps(content_nodes, ensure_ascii=False)
                    continue
                raise RuntimeError(f"Telegraph createPage error: {err_str}")
            return data["result"]["url"]
        except Exception as e:
            last_err = e
            if "CONTENT_TOO_BIG" in str(e):
                if isinstance(content_nodes[-1], dict) and content_nodes[-1].get("children") == [{"tag": "i", "children": ["... (Текст сокращен из-за лимита Telegraph)"]}]:
                    content_nodes.pop()
                if len(content_nodes) > 1:
                    new_len = max(1, int(len(content_nodes) * 0.6))
                    if new_len >= len(content_nodes):
                        new_len = len(content_nodes) - 1
                    content_nodes = content_nodes[:new_len]
                    content_nodes.append({"tag": "p", "children": [{"tag": "i", "children": ["... (Текст сокращен из-за лимита Telegraph)"]}]})
                else:
                    content_nodes = [{"tag": "p", "children": ["... (Текст сокращен из-за лимита Telegraph)"]}]
                payload["content"] = json.dumps(content_nodes, ensure_ascii=False)
            time.sleep(1.5 * (attempt + 1))
            
    raise RuntimeError(f"Telegraph createPage failed after retries: {last_err}")

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
            import traceback; traceback.print_exc()
    try:
        token = _telegraph_create_account_sync()
        if token:
            os.makedirs("data", exist_ok=True)
            with open(TELEGRAPH_TOKEN_FILE, "w", encoding="utf-8") as f:
                f.write(token)
            _telegraph_token_cache = token
            return token
    except Exception as e:
        logger.error(f"Failed to generate Telegraph token: {e}", exc_info=True)
    return ""

class TelegraphHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack = [{"tag": "p", "children": []}]
        self.allowed_tags = {"b", "i", "u", "s", "code", "pre", "a", "p", "br", "h3", "h4"}

    def handle_starttag(self, tag, attrs):  # noqa
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

    def handle_data(self, data):  # noqa
        if data:
            self.stack[-1]["children"].append(data)

def _text_to_telegraph_nodes(html_content: str) -> list:
    """Convert HTML/plain text to Telegraph Node objects by parsing HTML tags correctly.
    Uses a robust flattener to ensure Telegraph API compliance (no nested block tags)."""
    parser = TelegraphHTMLParser()
    try:
        parser.feed(html_content)
        parser.close()
    except Exception as e:
        logger.error(f"HTML parsing failed for Telegraph node conversion: {e}", exc_info=True)
        return [{"tag": "p", "children": [html_content]}]
    
    root_children = parser.stack[0]["children"]
    
    nodes = []
    current_block = {"tag": "p", "children": []}
    
    block_tags = {"p", "pre", "h3", "h4", "blockquote", "aside"}
    inline_tags = {"b", "i", "u", "s", "code", "a"}
    
    def flush_block():
        nonlocal current_block
        if current_block["children"]:
            nodes.append(current_block)
        current_block = {"tag": "p", "children": []}
        
    def wrap_inlines(text, inline_stack):
        if not text:
            return None
        node = text
        for inline in reversed(inline_stack):
            new_node = {"tag": inline["tag"], "children": [node]}
            if "attrs" in inline:
                new_node["attrs"] = inline["attrs"]
            node = new_node
        return node
        
    def walk(child, inline_stack):
        if isinstance(child, str):
            parts = child.split('\n')
            for i, part in enumerate(parts):
                if part:
                    wrapped = wrap_inlines(part, inline_stack)
                    if wrapped:
                        current_block["children"].append(wrapped)
                if i < len(parts) - 1:
                    current_block["children"].append({"tag": "br"})
                    
        elif isinstance(child, dict):
            tag = child.get("tag")
            if tag in block_tags:
                flush_block()
                current_block["tag"] = tag
                for c in child.get("children", []):
                    walk(c, inline_stack)
                flush_block()
                
            elif tag in inline_tags:
                new_inline = {"tag": tag}
                if "attrs" in child:
                    new_inline["attrs"] = child["attrs"]
                inline_stack.append(new_inline)
                for c in child.get("children", []):
                    walk(c, inline_stack)
                inline_stack.pop()
                
            elif tag == "br":
                current_block["children"].append({"tag": "br"})
                
            else:
                # Unknown tags just have their children processed transparently
                for c in child.get("children", []):
                    walk(c, inline_stack)

    for child in root_children:
        walk(child, [])
        
    flush_block()
    
    if not nodes:
        nodes = [{"tag": "p", "children": [""]}]
    return nodes

def _create_telegraph_page_blocking(title: str, html_content: str, author: str = "ТГАЧ") -> str:
    token = get_telegraph_token()
    if not token:
        raise RuntimeError("API token is required")
        
    # Prevent Telegraph CONTENT_TOO_BIG error (limits at ~64KB of JSON payload, AST nodes take ~3x size)
    if len(html_content) > 18000:
        logger.warning(f"Telegraph content too big ({len(html_content)} chars), pre-truncating to 18000...")
        truncated = html_content[:18000]
        last_lt = truncated.rfind('<')
        last_gt = truncated.rfind('>')
        if last_lt > last_gt:
            # We cut right in the middle of a tag, truncate before the tag
            truncated = truncated[:last_lt]
        html_content = truncated + "\n\n<i>... (Саммари сокращено по лимиту Telegraph)</i>"
        
    nodes = _text_to_telegraph_nodes(html_content)
    return _telegraph_create_page_sync(token, title, nodes)

async def create_telegraph_page_async(title: str, html_content: str, author: str = "ТГАЧ") -> str | None:
    try:
        url = await asyncio.to_thread(_create_telegraph_page_blocking, title, html_content, author)
        return url
    except Exception as e:
        logger.error(f"Failed to create Telegraph page: {e}", exc_info=True)
        return None

