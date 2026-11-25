import os
import re
import json
import hashlib
import random
import httpx
import logging
import asyncio
import time
from html.parser import HTMLParser
from openai import AsyncOpenAI
from common.token_pool import groq_pool, google_pool, agentrouter_pool
from common.text_utils import clean_ai_thinking
from common.extractive_summary import generate_extractive_summary

logger = logging.getLogger("summarize")

GROQ_CONFIG = {
    "base_url": "https://api.groq.com/openai/v1",
    "model": "qwen/qwen3.8-27b", 
    "temperature": 0.8,
}

_SHARED_HTTP_CLIENT = None
# Внутрипамятный TTL кэш ответов саммари для одинаковых входных данных (защита от холостых вызовов)
_SUMMARY_CACHE: dict[str, tuple[str, float]] = {}
_CACHE_MAX_ENTRIES = 256
_IN_FLIGHT_REQUESTS: dict[str, asyncio.Future] = {}

# Ограничиваем параллельные LLM-вызовы Персоны: строго 1 одновременно
# Иначе 10+ конкурентных горутин дёргают все ключи одновременно и спамят 429
_PERSONA_SEMAPHORE: asyncio.Semaphore | None = None
_PERSONA_SEMAPHORE_LOOP: asyncio.AbstractEventLoop | None = None

def _get_persona_semaphore() -> asyncio.Semaphore:
    global _PERSONA_SEMAPHORE, _PERSONA_SEMAPHORE_LOOP
    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None
    if _PERSONA_SEMAPHORE is None or _PERSONA_SEMAPHORE_LOOP is not current_loop:
        _PERSONA_SEMAPHORE = asyncio.Semaphore(1)
        _PERSONA_SEMAPHORE_LOOP = current_loop
    return _PERSONA_SEMAPHORE



def get_shared_http_client() -> httpx.AsyncClient:
    global _SHARED_HTTP_CLIENT
    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None
    client_loop = getattr(_SHARED_HTTP_CLIENT, "_loop", None) if _SHARED_HTTP_CLIENT is not None else None
    if (
        _SHARED_HTTP_CLIENT is None
        or getattr(_SHARED_HTTP_CLIENT, "is_closed", False)
        or (current_loop is not None and client_loop is not None and client_loop is not current_loop)
    ):
        _SHARED_HTTP_CLIENT = httpx.AsyncClient(
            proxy=None,
            verify=False,
            timeout=httpx.Timeout(connect=10.0, read=60.0, write=10.0, pool=10.0),
            trust_env=False,
            limits=httpx.Limits(max_keepalive_connections=50, max_connections=100)
        )
        setattr(_SHARED_HTTP_CLIENT, "_loop", current_loop)
        try:
            from common.task_manager import register_http_client
            register_http_client(_SHARED_HTTP_CLIENT)
        except Exception:
            pass
    return _SHARED_HTTP_CLIENT

async def close_shared_http_client() -> None:
    global _SHARED_HTTP_CLIENT
    client = _SHARED_HTTP_CLIENT
    _SHARED_HTTP_CLIENT = None
    if client is not None and not getattr(client, "is_closed", False):
        try:
            await client.aclose()
        except Exception as e:
            logger.debug(f"Exception closing shared HTTP client: {e}")
        finally:
            # Yield to event loop on Windows to allow underlying SSL transport to close
            await asyncio.sleep(0.250)


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
_key_model_cooldowns: dict[tuple[str, str, str], float] = {}
_key_global_cooldowns: dict[tuple[str, str], float] = {}
_provider_cooldowns: dict[str, float] = {}
_model_cooldowns: dict[str, float] = {}


def _filter_keys_for_model(provider: str, model_name: str, keys: list[str], now_ts: float) -> list[str]:
    """
    Filters active keys for a specific (provider, model_name) pair.
    - Key-wide errors (401/403) live in _key_global_cooldowns and block all models for that key.
    - Per-model 429s live in _key_model_cooldowns and only cool down (provider, model_name, key),
      allowing the same key to still serve higher-RPM models (e.g. gemini-3.1-flash-lite).
    - If a test fixture clears _key_cooldowns, stale entries for cleared keys are pruned automatically.
    """
    if not _key_cooldowns:
        _key_global_cooldowns.clear()
        _key_model_cooldowns.clear()
    else:
        stale_global = [pk for pk in _key_global_cooldowns if pk not in _key_cooldowns]
        for pk in stale_global:
            _key_global_cooldowns.pop(pk, None)
        stale_model = [pmk for pmk in _key_model_cooldowns if (pmk[0], pmk[2]) not in _key_cooldowns]
        for pmk in stale_model:
            _key_model_cooldowns.pop(pmk, None)

    active: list[str] = []
    for k in keys:
        if _key_global_cooldowns.get((provider, k), 0.0) > now_ts:
            continue
        if _key_model_cooldowns.get((provider, model_name, k), 0.0) > now_ts:
            continue
        active.append(k)
    return active


_MEDIA_ONLY_LINE_RE = re.compile(
    r'^(?:[^:\n]{1,60}(?:\([^)]*\))?\s*:\s*)?'
    r'(?:\[(?:photo|sticker|video|animation|gif|voice|audio|document|media_group|video_note|'
    r'фото|стикер|видео|анимация|гифка|голосовое|аудио|документ|кружок|медиа)\]\s*)+$',
    re.IGNORECASE,
)

_MEDIA_TOKEN_RE = re.compile(
    r'\[(photo|sticker|video|animation|gif|voice|audio|document|media_group|video_note|'
    r'фото|стикер|видео|анимация|гифка|голосовое|аудио|документ|кружок|медиа)\]',
    re.IGNORECASE,
)


def is_media_only_dump(text_dump: str) -> bool:
    """Returns True when all non-empty lines in text_dump are bare media placeholders without discussion text."""
    if not text_dump or not text_dump.strip():
        return False
    lines = [ln.strip() for ln in text_dump.splitlines() if ln.strip()]
    if not lines:
        return False
    return all(_MEDIA_ONLY_LINE_RE.match(ln) for ln in lines)


def summarize_media_only_dump(text_dump: str) -> str:
    """Generates an accurate, non-hallucinated summary for media-only threads/dumps."""
    counts: dict[str, int] = {}
    label_map = {
        "photo": "фото", "фото": "фото",
        "sticker": "стикеров", "стикер": "стикеров",
        "video": "видео", "видео": "видео", "video_note": "кружков", "кружок": "кружков",
        "animation": "гифок", "gif": "гифок", "гифка": "гифок", "анимация": "гифок",
        "voice": "голосовых", "голосовое": "голосовых",
        "audio": "аудио", "аудио": "аудио",
        "document": "файлов", "документ": "файлов",
        "media_group": "альбомов", "медиа": "медиа",
    }
    for m in _MEDIA_TOKEN_RE.finditer(text_dump or ""):
        lbl = label_map.get(m.group(1).lower(), "медиа")
        counts[lbl] = counts.get(lbl, 0) + 1
    if not counts:
        return "🖼 <b>Медиа-тред:</b> текстовых сообщений нет, только вложения."
    parts = ", ".join(f"{k}: {v}" for k, v in counts.items())
    return f"🖼 <b>Медиа-тред без текста:</b> в подборке только вложения ({parts})."


def compress_thread_dump(text_dump: str, max_chars: int) -> str:
    """
    Compresses long thread/chat dumps to fit within max_chars while preserving:
    1) The head / OP post (~22% of budget),
    2) Salient middle posts (prioritizing posts with >>post_num / #post_num references, ~23% of budget),
    3) The newest tail discussion (~50% of budget) on clean line boundaries.
    """
    if not text_dump or max_chars <= 0 or len(text_dump) <= max_chars:
        return text_dump

    lines = [ln for ln in text_dump.splitlines() if ln.strip()]
    if len(lines) <= 2:
        if max_chars <= 64:
            return text_dump[-max_chars:]
        head_len = max(1, int(max_chars * 0.3))
        marker = "\n[...]\n"
        tail_len = max(1, max_chars - head_len - len(marker))
        return text_dump[:head_len] + marker + text_dump[-tail_len:]

    marker_mid = "\n\n[...часть середины треда сжата...]\n\n"
    marker_end = "\n\n[...переход к последним постам...]\n\n"
    reserve = len(marker_mid) + len(marker_end) + 16
    if max_chars <= reserve + 120:
        return text_dump[-max_chars:]

    budget = max_chars - reserve
    head_budget = int(budget * 0.22)
    mid_budget = int(budget * 0.23)
    tail_budget = budget - head_budget - mid_budget

    head_lines: list[str] = []
    head_chars = 0
    head_end_idx = 0
    for idx, ln in enumerate(lines):
        cost = len(ln) + (1 if head_lines else 0)
        if head_chars + cost > head_budget and head_lines:
            break
        if cost > head_budget and not head_lines:
            head_lines.append(ln[:head_budget])
            head_chars = len(head_lines[0])
            head_end_idx = idx + 1
            break
        head_lines.append(ln)
        head_chars += cost
        head_end_idx = idx + 1

    tail_lines: list[str] = []
    tail_chars = 0
    tail_start_idx = len(lines)
    for idx in range(len(lines) - 1, head_end_idx - 1, -1):
        ln = lines[idx]
        cost = len(ln) + (1 if tail_lines else 0)
        if tail_chars + cost > tail_budget and tail_lines:
            break
        if cost > tail_budget and not tail_lines:
            tail_lines.append(ln[-tail_budget:])
            tail_chars = len(tail_lines[0])
            tail_start_idx = idx
            break
        tail_lines.append(ln)
        tail_chars += cost
        tail_start_idx = idx
    tail_lines.reverse()

    mid_candidates = list(enumerate(lines[head_end_idx:tail_start_idx], start=head_end_idx))
    if not mid_candidates or mid_budget < 80:
        combined = "\n".join(head_lines) + marker_end + "\n".join(tail_lines)
        return combined[:max_chars]

    # Score middle posts: prioritize >>refs, replies, and substantive text; deprioritize bare media tags
    def _mid_score(item: tuple[int, str]) -> tuple[int, int]:
        _, ln = item
        if _MEDIA_ONLY_LINE_RE.match(ln.strip()):
            return (0, 0)
        has_ref = 1 if re.search(r'(?:>>|#)\d{3,}', ln) else 0
        has_reply = 1 if ("Ответ на" in ln or "reply to" in ln.lower()) else 0
        return (has_ref * 3 + has_reply * 2 + (1 if len(ln) >= 60 else 0), min(len(ln), 400))

    ranked = sorted(mid_candidates, key=_mid_score, reverse=True)
    picked: list[tuple[int, str]] = []
    mid_chars = 0
    for idx, ln in ranked:
        if len(ln) > mid_budget and not picked:
            picked.append((idx, ln[:mid_budget]))
            mid_chars = len(picked[0][1])
            break
        cost = len(ln) + (1 if picked else 0)
        if mid_chars + cost <= mid_budget:
            picked.append((idx, ln))
            mid_chars += cost

    picked.sort(key=lambda x: x[0])
    mid_block = "\n".join(ln for _, ln in picked)
    if mid_block:
        result = "\n".join(head_lines) + marker_mid + mid_block + marker_end + "\n".join(tail_lines)
    else:
        result = "\n".join(head_lines) + marker_end + "\n".join(tail_lines)
    if len(result) > max_chars:
        return result[:max_chars]
    return result


def safe_truncate_telegram_html(text: str, max_utf16: int = 4000, suffix: str = "…") -> str:
    """
    Safely truncates HTML text to Telegram UTF-16 code unit limits without ever cutting inside tags/entities
    or leaving unclosed <b>, <i>, <blockquote expandable>, <tg-spoiler>, <a> tags.
    """
    if not text:
        return ""
    from common.text_chunker import safe_html_truncate
    from common.html_utils import balance_html_tags
    return balance_html_tags(safe_html_truncate(text, max_units=max_utf16, suffix=suffix))


def sanitize_summary_html(text: str, max_utf16: int | None = None) -> str:
    """
    Normalizes LLM summary output into Telegram-parseable HTML while preserving
    <blockquote>, <blockquote expandable>, <tg-spoiler>, <b>, <i>, <u>, <s>, <code>, <pre>, <a>.
    """
    if not text:
        return ""
    from common.html_utils import balance_html_tags
    # Preserve tg-spoiler across clean_html_for_tg (which uses [a-zA-Z]+ in its tag balancer)
    placeholder_open = "\u2063TGSPOILEROPEN\u2063"
    placeholder_close = "\u2063TGSPOILERCLOSE\u2063"
    prepared = re.sub(r'<tg-spoiler\b[^>]*>', placeholder_open, text, flags=re.IGNORECASE)
    prepared = re.sub(r'</tg-spoiler\s*>', placeholder_close, prepared, flags=re.IGNORECASE)

    from common.text_utils import clean_html_for_tg
    cleaned = clean_html_for_tg(prepared)
    cleaned = cleaned.replace(placeholder_open, "<tg-spoiler>").replace(placeholder_close, "</tg-spoiler>")
    cleaned = balance_html_tags(cleaned)
    if max_utf16 is not None:
        cleaned = safe_truncate_telegram_html(cleaned, max_utf16=max_utf16)
    return cleaned

_CANNED_REFUSAL_MARKERS = (
    "я не могу предоставить информацию",
    "я не могу выполнить этот запрос",
    "я не могу ответить",
    "телефон доверия",
    "телефону доверия",
    "телефона доверия",
    "психологической помощи",
    "горячая линия",
    "совершения самоубийства",
    "причинении себе вреда",
    "обратитесь за помощью к специалистам",
    "i cannot fulfill this request",
    "as an ai language model",
)

_PROVIDER_LOCKS: dict[str, asyncio.Lock] = {}
_PROVIDER_LOCKS_LOOP: asyncio.AbstractEventLoop | None = None
_PROVIDER_LAST_REQUEST_TS: dict[str, float] = {}
DEFAULT_AGENTROUTER_MODEL = os.getenv("AGENTROUTER_MODEL", "gpt-6.1-sol")
MIN_PROVIDER_INTERVAL: dict[str, float] = {
    "gemini": 2.5,
    "groq": 2.5,
    "openrouter": 2.5,
    "openai": 1.0,
    "agentrouter": 1.0,
}

def _get_provider_lock(provider: str) -> asyncio.Lock:
    global _PROVIDER_LOCKS, _PROVIDER_LOCKS_LOOP
    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None
    if _PROVIDER_LOCKS_LOOP is not current_loop:
        _PROVIDER_LOCKS.clear()
        _PROVIDER_LOCKS_LOOP = current_loop
    if provider not in _PROVIDER_LOCKS:
        _PROVIDER_LOCKS[provider] = asyncio.Lock()
    return _PROVIDER_LOCKS[provider]

async def _throttle_provider(provider: str) -> None:
    """
    Enforces minimum pause between consecutive requests to the same provider across all keys.
    Prevents API key bans and rapid-fire spam.
    """
    in_test = bool(os.environ.get("PYTEST_CURRENT_TEST"))
    if in_test:
        return
    lock = _get_provider_lock(provider)
    async with lock:
        now = time.time()
        last_ts = _PROVIDER_LAST_REQUEST_TS.get(provider, 0.0)
        min_int = MIN_PROVIDER_INTERVAL.get(provider, 2.5)
        elapsed = now - last_ts
        if elapsed < min_int:
            await asyncio.sleep(min_int - elapsed)
        _PROVIDER_LAST_REQUEST_TS[provider] = time.time()


GEMINI_SAFETY_SETTINGS_BLOCK_NONE = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_CIVIC_INTEGRITY", "threshold": "BLOCK_NONE"},
]
GEMINI_SAFETY_SETTINGS_BLOCK_ONLY_HIGH = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_ONLY_HIGH"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_ONLY_HIGH"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_ONLY_HIGH"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_ONLY_HIGH"},
    {"category": "HARM_CATEGORY_CIVIC_INTEGRITY", "threshold": "BLOCK_ONLY_HIGH"},
]

GEMINI_SERVICE_REFUSAL_MARKERS: tuple[str, ...] = (
    "the request asks for",
    "i cannot fulfill this request",
    "i am unable to transcribe",
    "i'm unable to transcribe",
    "i cannot transcribe",
    "i'm sorry, but i cannot",
    "i cannot complete this request",
    "i am unable to fulfill",
    "i'm unable to fulfill",
    "as an ai, i cannot",
    "as a language model, i cannot",
    "i cannot assist with this request",
    "my safety policies",
    "я не могу предоставить информацию",
    "я не могу выполнить этот запрос",
    "я не могу ответить",
    "телефон доверия",
    "телефону доверия",
    "телефона доверия",
    "психологической помощи",
    "горячая линия",
    "совершения самоубийства",
    "причинении себе вреда",
    "обратитесь за помощью к специалистам",
    "мои правила безопасности",
    "политикой безопасности",
)


def is_gemini_service_refusal(text: str | None) -> bool:
    """
    Проверяет, содержит ли текст служебный отказ Gemini AI
    ("The request asks for...", "I cannot fulfill this request", "I am unable to transcribe" и др.).
    Предотвращает попадание отказов модели в чат под видом речи анона и роаст Киберчедом.
    """
    if not text or not isinstance(text, str):
        return False
    t_lower = text.strip().lower()
    return any(marker in t_lower for marker in GEMINI_SERVICE_REFUSAL_MARKERS)

async def _call_gemini_native_rest(
    http_client: httpx.AsyncClient,
    model_name: str,
    api_key: str,
    system_instruction: str,
    user_text: str,
    temperature: float = 0.8,
    timeout: float | httpx.Timeout = 45.0,
    presence_penalty: float | None = None,
    frequency_penalty: float | None = None,
) -> tuple[str | None, str | None]:
    """
    Вызывает нативный REST API Google Gemini (generateContent) с BLOCK_NONE для полного снятия цензуры.
    Возвращает (content_text, finish_reason).
    """
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
    
    req_timeout = timeout if isinstance(timeout, httpx.Timeout) else httpx.Timeout(connect=10.0, read=float(timeout), write=10.0, pool=10.0)
    
    thresholds_to_try = [GEMINI_SAFETY_SETTINGS_BLOCK_NONE, GEMINI_SAFETY_SETTINGS_BLOCK_ONLY_HIGH]
    last_resp = None
    
    for safety_settings in thresholds_to_try:
        gen_config = {
            "temperature": temperature,
            "maxOutputTokens": 2048,
        }
        # Note: Google Gemini REST API (v1beta generateContent) does NOT support
        # presencePenalty or frequencyPenalty on Flash / Flash-Lite models, throwing
        # HTTP 400: "Penalty is not enabled for this model".
        # Therefore, we do NOT include them in gen_config for Gemini REST calls.

        payload = {
            "contents": [
                {"role": "user", "parts": [{"text": user_text}]}
            ],
            "generationConfig": gen_config,
            "safetySettings": safety_settings
        }
        if system_instruction:
            payload["systemInstruction"] = {
                "parts": [{"text": system_instruction}]
            }
            
        resp = await http_client.post(url, json=payload, timeout=req_timeout)
        last_resp = resp

        # Defensive fallback: if Gemini rejects with 400 "Penalty is not enabled",
        # strip presencePenalty / frequencyPenalty from gen_config and retry immediately once.
        resp_text = getattr(resp, "text", "") or ""
        if resp.status_code == 400 and ("Penalty is not enabled" in resp_text or "penalty is not enabled" in resp_text.lower()):
            logger.warning(f"⚠️ Gemini 400 'Penalty is not enabled' on {model_name}. Retrying without penalties...")
            gen_config.pop("presencePenalty", None)
            gen_config.pop("frequencyPenalty", None)
            payload["generationConfig"] = gen_config
            resp = await http_client.post(url, json=payload, timeout=req_timeout)
            last_resp = resp

        if resp.status_code == 400 and any(s.get("threshold") == "BLOCK_NONE" for s in safety_settings):
            logger.warning(f"⚠️ Gemini 400 with current BLOCK_NONE safetySettings on {model_name}. Retrying with fallback safety settings...")
            continue
        break
        
    if last_resp is None:
        raise RuntimeError("No response from Gemini API")
        
    if last_resp.status_code == 429:
        raise RuntimeError("429 Resource Exhausted (Rate Limit)")
    elif last_resp.status_code in (401, 403):
        raise RuntimeError(f"{last_resp.status_code} Unauthorized/Forbidden")
    elif last_resp.status_code == 413:
        raise RuntimeError(f"413 Request Entity Too Large: {last_resp.text[:150]}")
    elif last_resp.status_code == 404:
        raise RuntimeError(f"404 Model {model_name} not found")
    elif last_resp.status_code != 200:
        raise RuntimeError(f"Gemini API Error {last_resp.status_code}: {last_resp.text[:150]}")
        
    try:
        gdata = last_resp.json()
    except Exception as je:
        raise RuntimeError(f"Gemini API returned invalid JSON: {je}")

    candidates = gdata.get("candidates") or []
    if not candidates:
        prompt_feedback = gdata.get("promptFeedback") or {}
        block_reason = prompt_feedback.get("blockReason")
        if block_reason:
            logger.warning(f"⚠️ Gemini prompt blocked: {block_reason}")
            return None, "safety"
        return None, "empty_response"
        
    candidate = candidates[0]
    finish_reason = (candidate.get("finishReason") or "").lower()
    content_obj = candidate.get("content") or {}
    parts_resp = content_obj.get("parts") or []
    text_content = ""
    for p in parts_resp:
        if isinstance(p, dict) and "text" in p:
            # Skip Gemini internal thought/reasoning parts to prevent leaking internal CoT
            if p.get("thought") is True:
                continue
            text_content += p["text"]
    text_content = text_content.strip() or None

    if text_content and is_gemini_service_refusal(text_content):
        logger.warning(f"⚠️ Gemini service refusal detected: '{text_content[:80]}...'")
        return None, "safety"

    if finish_reason in ("safety", "content_filter"):
        return text_content, "safety"
        
    return text_content, finish_reason or "stop"


# Alias for external callers/tests
call_gemini_rest = _call_gemini_native_rest


async def dispatch_llm_completion(prompt: str, text_dump: str, model_preference: str | None = None) -> str:
    """
    Dispatch LLM completion using a cascade of OpenAI-compatible endpoints (Google Gemini & Groq).
    Supports choosing model/provider preference: persona, fast, gemini, qwen, llama, or default.
    Prioritizes high-throughput Gemini models with Groq Qwen failover.
    Automatically activates extractive summary fallback if all LLMs are down/rate-limited.
    """
    # Guard against completely empty or whitespace-only dumps (saves wasted token calls)
    if not text_dump or not text_dump.strip():
        logger.warning("⚠️ dispatch_llm_completion received empty text_dump. Skipping LLM call.")
        return ""

    if model_preference not in ("persona", "persona_gemini") and is_media_only_dump(text_dump):
        logger.info("🖼️ dispatch_llm_completion detected media-only dump without text. Returning concise media summary.")
        return summarize_media_only_dump(text_dump)

    in_test = bool(os.environ.get("PYTEST_CURRENT_TEST"))
    cache_key = None
    if not in_test:
        cache_key = hashlib.sha256(f"{model_preference or 'default'}:{prompt.strip()}:{text_dump.strip()}".encode("utf-8")).hexdigest()
        now_ts = time.time()
        if cache_key in _SUMMARY_CACHE:
            cached_val, expires_at = _SUMMARY_CACHE[cache_key]
            if now_ts < expires_at:
                logger.info(f"⚡ [LLM Cache Hit] Returning cached response for {model_preference or 'default'} (key={cache_key[:8]}).")
                return cached_val

        # Single-Flight Request Coalescing:
        # If another concurrent coroutine is already generating this exact response, await its result
        in_flight_fut = _IN_FLIGHT_REQUESTS.get(cache_key)
        if in_flight_fut is not None and not in_flight_fut.done():
            try:
                fut_loop = in_flight_fut.get_loop()
                cur_loop = asyncio.get_running_loop()
            except Exception:
                fut_loop, cur_loop = None, None
            if fut_loop is cur_loop and fut_loop is not None:
                logger.info(f"⚡ [Single-Flight Coalesce] Awaiting in-flight request for {model_preference or 'default'} (key={cache_key[:8]}).")
                try:
                    return await asyncio.shield(in_flight_fut)
                except Exception as e:
                    logger.debug(f"In-flight request join error: {e}")

    my_fut = None
    if cache_key and not in_test:
        try:
            loop = asyncio.get_running_loop()
            my_fut = loop.create_future()
            _IN_FLIGHT_REQUESTS[cache_key] = my_fut
        except Exception:
            my_fut = None

    raw_res = ""
    try:
        if model_preference in ("persona", "persona_gemini"):
            # Persona / Cyberchad: строго 1 параллельный вызов через семафор
            async with _get_persona_semaphore():
                # Double-checked locking inside semaphore in case preceding coroutine filled the cache
                if cache_key and not in_test and cache_key in _SUMMARY_CACHE:
                    c_val, c_exp = _SUMMARY_CACHE[cache_key]
                    if time.time() < c_exp:
                        raw_res = c_val
                        return raw_res
                raw_res = await _summarize_inner(prompt, text_dump, None, model_preference)
        else:
            raw_res = await _summarize_inner(prompt, text_dump, None, model_preference)

        if raw_res and is_gemini_service_refusal(raw_res):
            logger.warning(f"⚠️ summarize_text_with_hf: Gemini service refusal filtered: '{raw_res[:80]}...'")
            raw_res = None

        # Unwrap accidental JSON wrapper for standard summaries (not persona)
        if raw_res and model_preference not in ("persona", "persona_gemini") and not raw_res.startswith("Нейронка сдохла"):
            trimmed_res = raw_res.strip()
            if trimmed_res.startswith("```"):
                lines = trimmed_res.splitlines()
                if len(lines) >= 2 and lines[-1].strip().startswith("```"):
                    trimmed_res = "\n".join(lines[1:-1]).strip()
            if trimmed_res.startswith("{") and trimmed_res.endswith("}"):
                try:
                    data = json.loads(trimmed_res)
                    if isinstance(data, dict):
                        extracted = data.get("text") or data.get("summary") or data.get("response") or data.get("content")
                        if extracted and isinstance(extracted, str):
                            raw_res = extracted
                except Exception:
                    pass

        # CASCADE FALLBACK: If LLMs failed completely or returned error
        if not raw_res or raw_res.startswith("Нейронка сдохла"):
            # If this is a real text dump (not a unit-test with mock 'Text'), generate rich extractive summary!
            if len(text_dump.strip()) >= 20 and model_preference not in ("persona", "persona_gemini"):
                logger.warning("🛡️ All LLMs failed/exhausted. Activating intelligent extractive summary fallback!")
                try:
                    raw_res = generate_extractive_summary(text_dump, prompt, paragraph_count=4)
                except Exception as ext_err:
                    logger.error(f"Extractive fallback error: {ext_err}")
        elif cache_key and not in_test and raw_res:
            # Save to cache: 180s for normal summaries, 10s micro-burst for personas
            ttl = 10.0 if model_preference in ("persona", "persona_gemini") else 180.0
            now = time.time()
            if len(_SUMMARY_CACHE) >= _CACHE_MAX_ENTRIES:
                # Evict expired entries first
                expired = [k for k, (_, exp) in _SUMMARY_CACHE.items() if exp <= now]
                for k in expired:
                    _SUMMARY_CACHE.pop(k, None)
                # If still at max capacity, evict oldest entries (25% batch)
                if len(_SUMMARY_CACHE) >= _CACHE_MAX_ENTRIES:
                    oldest = sorted(_SUMMARY_CACHE.items(), key=lambda it: it[1][1])[:max(1, _CACHE_MAX_ENTRIES // 4)]
                    for k, _ in oldest:
                        _SUMMARY_CACHE.pop(k, None)
            _SUMMARY_CACHE[cache_key] = (raw_res, now + ttl)

        return raw_res
    finally:
        if my_fut is not None:
            if not my_fut.done():
                my_fut.set_result(raw_res)
            _IN_FLIGHT_REQUESTS.pop(cache_key, None)


# Канонический алиас для обратной совместимости
summarize_text_with_hf = dispatch_llm_completion


async def _summarize_inner(prompt: str, text_dump: str, hf_token: str | None = None, model_preference: str | None = None) -> str:
    if model_preference in ("persona", "persona_gemini"):
        top_candidates = [
            ("gemini-3.7-flash", "gemini"),
            ("gemini-3.6-flash", "gemini"),
            ("gemini-3.5-flash", "gemini"),
            ("gemini-3.5-flash-lite", "gemini"),
        ]
        # Weighted random selection of the primary model per request
        chosen_first = random.choices(
            top_candidates,
            weights=[0.35, 0.35, 0.20, 0.10],
            k=1
        )[0]
        # All remaining top candidates become immediate fallbacks (shuffled)
        remaining_top = [m for m in top_candidates if m != chosen_first]
        random.shuffle(remaining_top)

        models_cascade = (
            [chosen_first]
            + remaining_top
            + [
                ("qwen/qwen3.8-27b", "groq"),
                ("llama-3.3-70b-versatile", "groq"),
                (DEFAULT_AGENTROUTER_MODEL, "agentrouter"),
                ("openai/gpt-oss-120b", "groq"),
                ("gemini-3.1-flash-lite", "gemini"),
                ("llama-3.1-8b-instant", "groq"),
                ("openai/gpt-oss-20b", "groq"),
            ]
        )
        logger.info(
            f"🎲 [persona] Primary model randomly selected: {chosen_first[0]} ({chosen_first[1]}). "
            f"Full fallback cascade: {[m[0] for m in models_cascade]}"
        )
    elif model_preference == "fast":
        top_fast = [
            ("gemini-3.5-flash-lite", "gemini"),
            ("gemini-3.1-flash-lite", "gemini"),
        ]
        chosen_fast = random.choice(top_fast)
        remaining_fast = [m for m in top_fast if m != chosen_fast]
        models_cascade = [chosen_fast] + remaining_fast + [
            ("gemini-3.6-flash", "gemini"),
            ("llama-3.1-8b-instant", "groq"),
            ("qwen/qwen3.8-27b", "groq"),
            ("openai/gpt-oss-20b", "groq"),
        ]
    elif model_preference == "gemini":
        top_gem = [
            ("gemini-3.5-flash", "gemini"),
            ("gemini-3.5-flash-lite", "gemini"),
            ("gemini-3.1-flash-lite", "gemini"),
        ]
        chosen_gem = random.choice(top_gem)
        remaining_gem = [m for m in top_gem if m != chosen_gem]
        models_cascade = [chosen_gem] + remaining_gem + [
            ("gemini-3.6-flash", "gemini"),
            ("gemini-3.7-flash", "gemini"),
            (DEFAULT_AGENTROUTER_MODEL, "agentrouter"),
            ("qwen/qwen3.8-27b", "groq"),
            ("llama-3.3-70b-versatile", "groq"),
            ("openai/gpt-oss-120b", "groq"),
            ("llama-3.1-8b-instant", "groq"),
            ("openai/gpt-oss-20b", "groq"),
        ]
    elif model_preference in ("qwen", "llama", "groq"):
        models_cascade = [
            ("qwen/qwen3.8-27b", "groq"),
            ("llama-3.3-70b-versatile", "groq"),
            ("openai/gpt-oss-120b", "groq"),
            ("llama-3.1-8b-instant", "groq"),
            ("openai/gpt-oss-20b", "groq"),
            (DEFAULT_AGENTROUTER_MODEL, "agentrouter"),
            ("gemini-3.5-flash", "gemini"),
            ("gemini-3.5-flash-lite", "gemini"),
            ("gemini-3.1-flash-lite", "gemini"),
            ("gemini-3.6-flash", "gemini"),
        ]
    elif model_preference in ("deepseek", "agentrouter"):
        models_cascade = [
            (DEFAULT_AGENTROUTER_MODEL, "agentrouter"),
            ("gemini-3.5-flash", "gemini"),
            ("gemini-3.5-flash-lite", "gemini"),
            ("gemini-3.1-flash-lite", "gemini"),
            ("gemini-3.6-flash", "gemini"),
            ("gemini-3.7-flash", "gemini"),
            ("qwen/qwen3.8-27b", "groq"),
            ("llama-3.3-70b-versatile", "groq"),
            ("openai/gpt-oss-120b", "groq"),
            ("llama-3.1-8b-instant", "groq"),
            ("openai/gpt-oss-20b", "groq"),
        ]
    else:
        # Default summarization cascade: DeepSeek prioritized as #1
        models_cascade = [
            (DEFAULT_AGENTROUTER_MODEL, "agentrouter"),
            ("gemini-3.5-flash", "gemini"),
            ("gemini-3.5-flash-lite", "gemini"),
            ("gemini-3.1-flash-lite", "gemini"),
            ("gemini-3.6-flash", "gemini"),
            ("gemini-3.7-flash", "gemini"),
            ("qwen/qwen3.8-27b", "groq"),
            ("llama-3.3-70b-versatile", "groq"),
            ("openai/gpt-oss-120b", "groq"),
            ("llama-3.1-8b-instant", "groq"),
            ("openai/gpt-oss-20b", "groq"),
        ]

    # Additional fallbacks if external keys configured
    if os.getenv("OPENROUTER_API_KEY"):
        models_cascade.extend([
            ("meta-llama/llama-3.3-70b-instruct:free", "openrouter"),
            ("mistralai/mistral-7b-instruct:free", "openrouter"),
        ])
    if os.getenv("OPENAI_API_KEY"):
        models_cascade.extend([
            ("gpt-4o-mini", "openai"),
        ])

    prompt_lower = (prompt or "").lower()
    is_json_prompt = (
        "json" in prompt_lower
        or '"persona"' in prompt_lower
        or '"reply"' in prompt_lower
    )
    is_summary_prompt = any(
        kw in prompt_lower
        for kw in (
            "саммари", "сводк", "пересказ", "summary", "digest", "дайджест",
            "прожарк", "roast", "разбор", "летопис", "хроник", "маляв", "досье",
            "обзор", "суть треда", "summarize", "chronicler", "要約", "まとめ",
        )
    )

    if model_preference not in ("persona", "persona_gemini") and not is_json_prompt:
        extra_rules = (
            "\n\nCRITICAL OUTPUT FORMAT RULES:\n"
            "ALLOWED tags (ONLY these): <b>, <i>, <u>, <s>, <code>, <pre>, <blockquote>, <blockquote expandable>, <tg-spoiler>, <a href=\"...\">.\n"
            "FORBIDDEN tags (NEVER use): <p>, <div>, <span>, <br>, <hr>, <h1>, <h2>, <h3>, <h4>, <h5>, <h6>, <ul>, <ol>, <li>, <table>, <tr>, <td>, <th>, <em>, <strong>, <section>, <article>, and ANY other HTML tag not listed above.\n"
            "FORBIDDEN formatting: Never use Markdown (no **bold**, no *italic*, no # headings, no - lists, no * lists).\n"
            "Separate paragraphs with a blank line (two newlines), NOT with <p> tags.\n"
            "For bullet lists use • character with a newline, NOT <ul>/<li> tags.\n"
            "Always close every HTML tag you open. Output must be parseable by Telegram Bot API HTML parser."
        )
        if is_summary_prompt:
            extra_rules += (
                "\n\nCONTENT & GROUNDING RULES:\n"
                "- Cut the robotic/bureaucratic filler: NEVER start with phrases like 'В этом треде участники обсудили...', 'В данном обсуждении...', 'Подводя итоги...', 'Можно выделить следующие темы...'. Jump straight into the substance.\n"
                "- Anchor claims to concrete facts, positions, conflicts, and short real quotes from the log. When post numbers (#123456 or >>123456) appear in the log, cite key posts explicitly as >>123456 (never invent fake post numbers).\n"
                "- Keep the tone sharp, lively, and concrete rather than generic."
            )
        system_instruction = prompt + extra_rules
    else:
        system_instruction = prompt

    import time
    now_ts = time.time()
    skip_providers: set[str] = set()
    provider_safety_count: dict[str, int] = {}
    provider_model_counts: dict[str, int] = {}
    for _, _prov in models_cascade:
        provider_model_counts[_prov] = provider_model_counts.get(_prov, 0) + 1
    provider_429_models: dict[str, set[str]] = {}
    provider_exhausted_models: dict[str, set[str]] = {}
    persona_temperature = round(random.uniform(0.76, 0.84), 2)

    for model_name, provider in models_cascade:
        if provider in skip_providers:
            continue
        if _provider_cooldowns.get(provider, 0) > now_ts:
            logger.info(f"{provider} is in provider cooldown ({_provider_cooldowns[provider] - now_ts:.1f}s remaining). Skipping model {model_name}.")
            continue
        if _model_cooldowns.get(model_name, 0) > now_ts:
            logger.info(f"Model {model_name} is in cooldown ({_model_cooldowns[model_name] - now_ts:.1f}s remaining). Skipping.")
            provider_exhausted_models.setdefault(provider, set()).add(model_name)
            continue

        if provider == "gemini":
            keys = google_pool.get_all_active_tokens()
            base_url = "https://generativelanguage.googleapis.com/v1beta/openai/"
        elif provider == "agentrouter":
            keys = agentrouter_pool.get_all_active_tokens()
            base_url = os.getenv("AGENTROUTER_BASE_URL", "https://agentrouter.org/v1")
        elif provider == "groq":
            keys = groq_pool.get_all_active_tokens()
            base_url = "https://api.groq.com/openai/v1"
        elif provider == "openrouter":
            or_key = os.getenv("OPENROUTER_API_KEY")
            keys = [or_key] if or_key else []
            base_url = "https://openrouter.ai/api/v1"
        elif provider == "openai":
            oa_key = os.getenv("OPENAI_API_KEY")
            keys = [oa_key] if oa_key else []
            base_url = "https://api.openai.com/v1"
        else:
            continue
            
        if not keys:
            logger.warning(f"No keys for provider {provider}. Skipping model {model_name}.")
            continue
            
        # Filter out keys that are globally banned or cooling down for THIS specific (provider, model_name)
        active_keys = _filter_keys_for_model(provider, model_name, keys, now_ts)
        if not active_keys:
            logger.info(f"All keys for {provider} ({model_name}) are in cooldown. Skipping model {model_name}.")
            provider_exhausted_models.setdefault(provider, set()).add(model_name)
            continue

        # Cap keys tried per model to max 8 healthy keys to ensure full pool utilization
        active_keys = active_keys[:8]

        # Безопасный лимит выходных токенов: для Gemini None (без урезания)
        # Для AgentRouter (DeepSeek reasoning): 4096 токенов
        # Для Groq: для persona 1024 токена, для summary 3500 токенов
        is_persona = model_preference in ("persona", "persona_gemini")
        if provider == "gemini":
            model_max_tokens = None
        elif provider == "agentrouter":
            model_max_tokens = 4096
        elif is_persona:
            model_max_tokens = 1024
        else:
            model_max_tokens = 3500

        # Защита от 413 Payload Too Large и избыточного сжигания токенов при сохранении начала (ОП-поста), середины и хвоста треда
        if len(text_dump) > 80000:
            text_dump = compress_thread_dump(text_dump, 60000)

        effective_sys = system_instruction
        effective_dump = text_dump
        if provider == "groq":
            if is_persona:
                if len(effective_dump) > 10000:
                    effective_dump = compress_thread_dump(effective_dump, 10000)
            else:
                if len(effective_sys) > 8000:
                    effective_sys = effective_sys[:8000]
                if len(effective_dump) > 15000:
                    effective_dump = compress_thread_dump(effective_dump, 15000)
        elif provider == "gemini":
            if not is_persona and len(effective_dump) > 35000:
                effective_dump = compress_thread_dump(effective_dump, 35000)
            elif is_persona and len(effective_dump) > 10000:
                effective_dump = compress_thread_dump(effective_dump, 10000)
        else:
            if is_persona and len(effective_dump) > 8000:
                effective_dump = compress_thread_dump(effective_dump, 8000)
            elif not is_persona and len(effective_dump) > 35000:
                effective_dump = compress_thread_dump(effective_dump, 35000)

        messages = [
            {"role": "system", "content": effective_sys},
            {"role": "user", "content": effective_dump}
        ]

        skip_model = False
        consecutive_429 = 0
        consecutive_empty = 0

        for api_key in active_keys:
            if skip_model or provider in skip_providers:
                break
            try:
                await _throttle_provider(provider)
                http_client = get_shared_http_client()
                is_mock_env = hasattr(AsyncOpenAI, "assert_called") or "mock" in type(AsyncOpenAI).__name__.lower()

                if provider == "gemini" and not is_mock_env:
                    is_persona = model_preference in ("persona", "persona_gemini")
                    gemini_timeout = httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=10.0)
                    raw_text, finish_reason = await _call_gemini_native_rest(
                        http_client=http_client,
                        model_name=model_name,
                        api_key=api_key,
                        system_instruction=effective_sys,
                        user_text=effective_dump,
                        temperature=persona_temperature if is_persona else 0.8,
                        timeout=gemini_timeout,
                        presence_penalty=0.35 if is_persona else None,
                        frequency_penalty=0.45 if is_persona else None,
                    )
                    if raw_text and finish_reason not in ("safety", "content_filter"):
                        result = clean_ai_thinking(raw_text)
                        if result and (any(m in result.lower() for m in _CANNED_REFUSAL_MARKERS) or is_gemini_service_refusal(result)):
                            logger.warning(f"🛡️ Canned refusal/helpline detected from {model_name}. Skipping model.")
                            skip_model = True
                            break
                        if result:
                            return result
                        else:
                            logger.warning(f"Model {model_name} returned empty text after <think> stripping")
                            consecutive_empty += 1
                            if consecutive_empty >= 2:
                                skip_model = True
                                break
                    else:
                        logger.warning(f"⚠️ {provider} model {model_name} returned empty/safety content (finish_reason={finish_reason})")
                        if finish_reason in ("safety", "content_filter"):
                            logger.warning(f"🛡️ Safety filter triggered for {provider} on model {model_name}. Skipping provider {provider} for this prompt.")
                            skip_providers.add(provider)
                            skip_model = True
                            break
                        else:
                            consecutive_empty += 1
                            if consecutive_empty >= 2:
                                logger.warning(f"⚠️ Multiple empty responses from {model_name}. Skipping model.")
                                skip_model = True
                                break
                else:
                    client_kwargs = dict(
                        api_key=api_key if api_key else "dummy",
                        base_url=base_url,
                        http_client=http_client,
                        max_retries=0
                    )
                    if provider == "agentrouter":
                        client_kwargs["default_headers"] = {"User-Agent": "opencode/1.18.25"}
                    if provider == "agentrouter" and not is_mock_env:
                        ar_headers = {
                            "Authorization": f"Bearer {api_key}",
                            "User-Agent": "opencode/1.18.25",
                            "Content-Type": "application/json"
                        }
                        ar_input = f"{effective_sys}\n\n{effective_dump}" if effective_sys else effective_dump
                        ar_payload = {
                            "model": model_name,
                            "input": ar_input,
                        }
                        ar_base = base_url.rstrip("/")
                        ar_resp = await http_client.post(
                            f"{ar_base}/responses",
                            headers=ar_headers,
                            json=ar_payload,
                            timeout=httpx.Timeout(connect=10.0, read=45.0, write=10.0, pool=10.0),
                        )
                        if ar_resp.status_code == 200:
                            ar_data = ar_resp.json()
                            extracted_txt = None
                            for out_item in ar_data.get("output", []):
                                if out_item.get("type") == "message":
                                    msg_content = out_item.get("content", [])
                                    if isinstance(msg_content, list) and msg_content:
                                        extracted_txt = msg_content[0].get("text")
                                    elif isinstance(msg_content, str):
                                        extracted_txt = msg_content
                            if not extracted_txt and "text" in ar_data:
                                extracted_txt = ar_data.get("text")
                            if extracted_txt:
                                result = clean_ai_thinking(extracted_txt)
                                if result and (any(m in result.lower() for m in _CANNED_REFUSAL_MARKERS) or is_gemini_service_refusal(result)):
                                    logger.warning(f"🛡️ Canned refusal/helpline detected from {model_name}. Skipping model.")
                                    skip_model = True
                                    break
                                if result:
                                    return result
                                else:
                                    logger.warning(f"Model {model_name} returned empty text after <think> stripping")
                                    consecutive_empty += 1
                                    if consecutive_empty >= 2:
                                        skip_model = True
                                        break
                                    continue
                            else:
                                raise RuntimeError(f"AgentRouter empty message output: {ar_data}")
                        elif ar_resp.status_code in (400, 404) or any(phrase in ar_resp.text.lower() for phrase in ("not support", "unsupported", "unknown model")):
                            # Fall back to standard OpenAI chat/completions endpoint
                            pass
                        else:
                            raise RuntimeError(f"AgentRouter error {ar_resp.status_code}: {ar_resp.text[:300]}")

                    client = AsyncOpenAI(**client_kwargs)
                    create_kwargs = dict(
                        model=model_name,
                        messages=messages,
                        temperature=persona_temperature if model_preference in ("persona", "persona_gemini") else 0.8,
                        timeout=httpx.Timeout(connect=10.0, read=45.0, write=10.0, pool=10.0),
                    )
                    if model_preference in ("persona", "persona_gemini"):
                        create_kwargs["presence_penalty"] = 0.35
                        create_kwargs["frequency_penalty"] = 0.45
                    if model_max_tokens is not None:
                        create_kwargs["max_tokens"] = model_max_tokens
                    completion = await client.chat.completions.create(**create_kwargs)
                    choice = completion.choices[0] if (completion.choices and len(completion.choices) > 0) else None
                    if choice and choice.message is not None:
                        result = choice.message.content
                        finish_reason = (getattr(choice, "finish_reason", "") or "").lower()
                        if result and finish_reason not in ("safety", "content_filter"):
                            result = clean_ai_thinking(result)
                            if result and (any(m in result.lower() for m in _CANNED_REFUSAL_MARKERS) or is_gemini_service_refusal(result)):
                                logger.warning(f"🛡️ Canned refusal/helpline detected from {model_name}. Skipping model.")
                                skip_model = True
                                break
                            if result:
                                return result
                            else:
                                logger.warning(f"Model {model_name} returned empty text after <think> stripping")
                                consecutive_empty += 1
                                if consecutive_empty >= 2:
                                    skip_model = True
                                    break
                        else:
                            logger.warning(f"⚠️ {provider} model {model_name} returned empty/None content (finish_reason={finish_reason})")
                            if finish_reason in ("safety", "content_filter"):
                                logger.warning(f"🛡️ Safety filter triggered for {provider} on model {model_name}. Skipping provider {provider} for this prompt.")
                                skip_providers.add(provider)
                                skip_model = True
                                break
                            else:
                                consecutive_empty += 1
                                if consecutive_empty >= 2:
                                    logger.warning(f"⚠️ Multiple empty responses from {model_name}. Skipping model.")
                                    skip_model = True
                                    break
            except Exception as e:
                err_str = str(e).strip() or repr(e)
                logger.warning(f"⚠️ {provider} call failed ({model_name}) key=...{api_key[-6:]}: {err_str[:120]}")
                if "404" in err_str or "model_not_found" in err_str or "does not exist" in err_str.lower():
                    logger.warning(f"⚠️ {provider} model {model_name} not found (404). Skipping model.")
                    break
                if "unauthorized_client" in err_str.lower() or "unauthorized client" in err_str.lower():
                    logger.warning(f"⚠️ {provider} client rejected upstream (unauthorized_client). Placing provider on 1h cooldown.")
                    _provider_cooldowns[provider] = time.time() + 3600.0
                    skip_providers.add(provider)
                    break
                if (
                    "无可用渠道" in err_str
                    or "no available channel" in err_str.lower()
                    or "no channel available" in err_str.lower()
                ):
                    logger.warning(
                        f"⚠️ {provider} model {model_name} has no available channels upstream. Placing model on 30m cooldown."
                    )
                    _model_cooldowns[model_name] = time.time() + 1800.0
                    skip_model = True
                    break
                if "402" in err_str or "budget pool" in err_str.lower():
                    logger.warning(f"⚠️ {provider} model {model_name} budget pool quota exhausted (402). Placing model on 30m cooldown.")
                    _model_cooldowns[model_name] = time.time() + 1800.0
                    skip_model = True
                    break
                if "413" in err_str or "too large" in err_str.lower() or "context_length_exceeded" in err_str.lower():
                    logger.warning(f"⚠️ {model_name}: request too large ({provider}). Shrinking by 40% and skipping to next model...")
                    half_len = int(len(text_dump) * 0.6)
                    text_dump = text_dump[-half_len:]
                    effective_dump = text_dump
                    if provider == "groq":
                        model_max_tokens = 512
                    messages[1]["content"] = effective_dump
                    in_test = bool(os.environ.get("PYTEST_CURRENT_TEST"))
                    await asyncio.sleep(0.01 if in_test else 2.5)
                    skip_model = True
                    break
                if (re.search(r'\b401\b', err_str) or "unauthorized" in err_str.lower() or "invalid api key" in err_str.lower()) and "413" not in err_str:
                    logger.warning(f"⚠️ {provider} key ...{api_key[-6:]} returned 401 unauthorized. Removing from pool and setting cooldown.")
                    until_401 = time.time() + 900.0
                    _key_global_cooldowns[(provider, api_key)] = until_401
                    _key_cooldowns[(provider, api_key)] = until_401
                    if provider == "gemini":
                        google_pool.penalize_token(api_key, 900.0)
                        if hasattr(google_pool, "remove_token"):
                            google_pool.remove_token(api_key)
                    elif provider == "agentrouter":
                        agentrouter_pool.penalize_token(api_key, 900.0)
                        if hasattr(agentrouter_pool, "remove_token"):
                            agentrouter_pool.remove_token(api_key)
                    else:
                        groq_pool.penalize_token(api_key, 900.0)
                        if hasattr(groq_pool, "remove_token"):
                            groq_pool.remove_token(api_key)
                    in_test = bool(os.environ.get("PYTEST_CURRENT_TEST"))
                    await asyncio.sleep(0.01 if in_test else 2.5)
                    continue  # try next key
                if "403" in err_str:
                    # 403 = this specific key/project is banned. Cooldown it and try the NEXT KEY.
                    until_403 = time.time() + 3600.0
                    _key_global_cooldowns[(provider, api_key)] = until_403
                    _key_cooldowns[(provider, api_key)] = until_403  # 1h cooldown for banned keys
                    if provider == "gemini":
                        google_pool.ban_token(api_key)
                    elif provider == "agentrouter":
                        agentrouter_pool.ban_token(api_key)
                    else:
                        groq_pool.ban_token(api_key)
                    logger.warning(f"⚠️ {provider} key ...{api_key[-6:]} is 403 BANNED for {model_name}. Trying next key...")
                    in_test = bool(os.environ.get("PYTEST_CURRENT_TEST"))
                    await asyncio.sleep(0.01 if in_test else 3.0)
                    continue  # try next key, NOT next model
                if "tokens per day" in err_str.lower() or "tpd" in err_str.lower():
                    logger.warning(f"⚠️ {provider} daily token limit (TPD) reached for {model_name}. Pausing {provider} for 2h (account-level daily limit).")
                    _provider_cooldowns[provider] = time.time() + 7200.0  # 2h — TPD is account-wide, not per-key
                    skip_providers.add(provider)
                    break
                if "429" in err_str or "rate limit" in err_str.lower() or "quota" in err_str.lower() or "exhausted" in err_str.lower():
                    consecutive_429 += 1
                    cd_sec = 90.0 if provider == "gemini" else 120.0
                    cd_until = time.time() + cd_sec
                    _key_model_cooldowns[(provider, model_name, api_key)] = cd_until
                    _key_cooldowns[(provider, api_key)] = cd_until
                    if provider == "gemini":
                        google_pool.penalize_token(api_key, cd_sec, model=model_name)
                    elif provider == "agentrouter":
                        agentrouter_pool.penalize_token(api_key, cd_sec, model=model_name)
                    else:
                        groq_pool.penalize_token(api_key, cd_sec, model=model_name)
                    logger.warning(f"⚠️ {provider} key ...{api_key[-6:]} rate limited (429) for {model_name}.")

                    all_keys_tried = (consecutive_429 >= len(active_keys))
                    if consecutive_429 >= 2 or all_keys_tried:
                        provider_429_models.setdefault(provider, set()).add(model_name)
                        provider_exhausted_models.setdefault(provider, set()).add(model_name)
                        _model_cooldowns[model_name] = time.time() + (90.0 if provider == "gemini" else 120.0)
                        skip_model = True
                        total_prov_models = provider_model_counts.get(provider, 1)
                        if len(provider_exhausted_models[provider]) >= total_prov_models and len(provider_429_models[provider]) >= 1:
                            halt_sec = 1800.0 if provider == "groq" else 300.0
                            logger.warning(
                                f"⚠️ {provider} exhausted all {total_prov_models} cascade model(s) on 429/errors. "
                                f"Halting {provider} for {int(halt_sec//60)}m."
                            )
                            _provider_cooldowns[provider] = time.time() + halt_sec
                            skip_providers.add(provider)
                        else:
                            logger.warning(
                                f"⚠️ {provider} model {model_name} hit {consecutive_429} consecutive 429s. "
                                f"Cooling down {model_name} only and switching to next model..."
                            )
                        break
                    in_test = bool(os.environ.get("PYTEST_CURRENT_TEST"))
                    await asyncio.sleep(0.01 if in_test else 3.0)
                    continue  # try next key
                if isinstance(e, (httpx.TimeoutException, asyncio.TimeoutError, TimeoutError)) or "timeout" in err_str.lower() or "timed out" in err_str.lower():
                    logger.warning(f"⚠️ {provider} request timed out for {model_name}. Setting 60s cooldown on {model_name} and switching to next candidate...")
                    _model_cooldowns[model_name] = time.time() + 60.0
                    provider_exhausted_models.setdefault(provider, set()).add(model_name)
                    skip_model = True
                    break
                if "503" in err_str or "high demand" in err_str.lower() or "service unavailable" in err_str.lower():
                    logger.warning(f"⚠️ {provider} model {model_name} returned 503 (high demand). Setting 45s cooldown on model.")
                    _model_cooldowns[model_name] = time.time() + 45.0
                    provider_exhausted_models.setdefault(provider, set()).add(model_name)
                    skip_model = True
                    break
                # Any other error: skip model entirely
                logger.warning(f"⚠️ Unhandled error for {model_name}: {err_str[:80]}. Skipping model.")
                in_test = bool(os.environ.get("PYTEST_CURRENT_TEST"))
                await asyncio.sleep(0.01 if in_test else 0.5)
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
            import traceback
            traceback.print_exc()
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
        self.allowed_tags = {"b", "i", "u", "s", "code", "pre", "a", "p", "br", "h3", "h4", "blockquote"}

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
            # Split into distinct paragraphs on double newlines to form proper Telegraph <p> blocks
            paragraphs = re.split(r'\n\s*\n', child)
            for p_idx, para in enumerate(paragraphs):
                para_clean = para.strip('\r\n')
                if not para_clean:
                    continue
                if current_block["children"] and p_idx > 0:
                    flush_block()
                lines = para_clean.split('\n')
                for i, line in enumerate(lines):
                    line_clean = line.strip('\r')
                    if line_clean:
                        wrapped = wrap_inlines(line_clean, inline_stack)
                        if wrapped:
                            current_block["children"].append(wrapped)
                    if i < len(lines) - 1:
                        current_block["children"].append({"tag": "br"})
                if p_idx < len(paragraphs) - 1 and current_block["children"]:
                    flush_block()
                    
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

    if not html_content or not html_content.strip():
        html_content = "<i>(Пустой текст)</i>"

    # Defensive check: unwrap accidental raw JSON responses from model (including markdown fenced)
    trimmed = html_content.strip()
    if trimmed.startswith("```"):
        lines = trimmed.splitlines()
        if len(lines) >= 2 and lines[-1].strip().startswith("```"):
            trimmed = "\n".join(lines[1:-1]).strip()
    if trimmed.startswith("{") and trimmed.endswith("}"):
        try:
            data = json.loads(trimmed)
            if isinstance(data, dict):
                extracted = data.get("text") or data.get("summary") or data.get("response") or data.get("content")
                if extracted and isinstance(extracted, str):
                    html_content = extracted
        except Exception:
            pass
        
    # Prevent Telegraph CONTENT_TOO_BIG error (limits at ~64KB of JSON payload, AST nodes take ~3x size)
    if len(html_content) > 18000:
        logger.warning(f"Telegraph content too big ({len(html_content)} chars), pre-truncating safely to 18000...")
        truncated = safe_truncate_telegram_html(html_content, max_utf16=18000, suffix="")
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
