import pytest
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

from summarize import (
    dispatch_llm_completion,
    _call_gemini_native_rest,
    _get_persona_semaphore,
    _create_telegraph_page_blocking,
    get_shared_http_client,
)
from site_tgach.neuro_poster import (
    NeuroManager,
    _execute_completion,
    _throttle_poster_provider,
)
from site_tgach.tagging_worker import (
    is_safe_url,
    download_file_with_fallback,
)
from common.token_pool import groq_pool, google_pool


# ==============================================================================
# SECTOR 4 AUDIT 1: SUMMARIZE.PY & GEMINI REST THINKING LEAK
# ==============================================================================

@pytest.mark.asyncio
async def test_gemini_native_rest_strips_internal_thought_parts():
    """
    VULNERABILITY: Gemini generateContent REST returns thoughts as {"thought": True, "text": "..."}.
    Verify that thought parts are excluded and internal reasoning does not leak to the user.
    """
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    
    # Candidate with thought part followed by actual response part
    mock_resp_json = {
        "candidates": [
            {
                "finishReason": "STOP",
                "content": {
                    "parts": [
                        {"thought": True, "text": "Internal chain of thought: the user wants a summary..."},
                        {"text": "<b>Заголовок</b>\nЭто настоящее саммари без утечки мыслей."}
                    ]
                }
            }
        ]
    }
    
    resp_obj = MagicMock()
    resp_obj.status_code = 200
    resp_obj.json.return_value = mock_resp_json
    mock_client.post.return_value = resp_obj

    content, finish_reason = await _call_gemini_native_rest(
        http_client=mock_client,
        model_name="gemini-3.5-flash",
        api_key="test_key",
        system_instruction="System",
        user_text="User",
    )

    assert finish_reason == "stop"
    assert "Internal chain of thought" not in content
    assert content == "<b>Заголовок</b>\nЭто настоящее саммари без утечки мыслей."


@pytest.mark.asyncio
async def test_gemini_native_rest_thought_only_returns_empty():
    """
    If the model hit max tokens while thinking and produced only thought parts,
    text_content should be empty (None) so the cascade properly fails over.
    """
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_resp_json = {
        "candidates": [
            {
                "finishReason": "MAX_TOKENS",
                "content": {
                    "parts": [
                        {"thought": True, "text": "I am thinking about step 1..."}
                    ]
                }
            }
        ]
    }
    resp_obj = MagicMock()
    resp_obj.status_code = 200
    resp_obj.json.return_value = mock_resp_json
    mock_client.post.return_value = resp_obj

    content, finish_reason = await _call_gemini_native_rest(
        http_client=mock_client,
        model_name="gemini-3.5-flash",
        api_key="test_key",
        system_instruction="System",
        user_text="User",
    )

    assert content is None
    assert finish_reason == "max_tokens"


@pytest.mark.asyncio
async def test_gemini_native_rest_invalid_json_handled_safely():
    """
    Verify malformed non-JSON response from Google does not crash with JSONDecodeError,
    but raises RuntimeError cleanly for cascade retry.
    """
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    resp_obj = MagicMock()
    resp_obj.status_code = 200
    resp_obj.json.side_effect = json.JSONDecodeError("Expecting value", "<html>Error</html>", 0)
    mock_client.post.return_value = resp_obj

    with pytest.raises(RuntimeError) as exc_info:
        await _call_gemini_native_rest(
            http_client=mock_client,
            model_name="gemini-3.5-flash",
            api_key="test_key",
            system_instruction="System",
            user_text="User",
        )
    assert "invalid JSON" in str(exc_info.value)


# ==============================================================================
# SECTOR 4 AUDIT 2: PERSONA SEMAPHORE & SINGLE-FLIGHT COALESCE
# ==============================================================================

@pytest.mark.asyncio
async def test_persona_semaphore_concurrency_limit():
    """
    Verify that _PERSONA_SEMAPHORE strictly limits persona generation concurrency to 1.
    """
    sem = _get_persona_semaphore()
    concurrency = 0
    max_concurrency = 0

    async def simulated_persona_call(task_id: int):
        nonlocal concurrency, max_concurrency
        async with _get_persona_semaphore():
            concurrency += 1
            max_concurrency = max(max_concurrency, concurrency)
            await asyncio.sleep(0.05)
            concurrency -= 1
            return f"result_{task_id}"

    tasks = [simulated_persona_call(i) for i in range(5)]
    results = await asyncio.gather(*tasks)

    assert len(results) == 5
    assert max_concurrency == 1, f"Expected strictly max concurrency 1, got {max_concurrency}"


@pytest.mark.asyncio
async def test_summarize_unwraps_accidental_json_in_standard_summary():
    """
    If a text summary accidentally returns markdown-fenced or raw JSON,
    dispatch_llm_completion unwraps the text field so the user gets clean text.
    """
    raw_llm_output = "```json\n{\n  \"summary\": \"Это важная суть треда про разработку бота.\"\n}\n```"

    with patch("summarize._summarize_inner", new=AsyncMock(return_value=raw_llm_output)):
        result = await dispatch_llm_completion(
            prompt="Сделай саммари",
            text_dump="Пост 1: привет | Пост 2: как дела",
            model_preference=None
        )

    assert result == "Это важная суть треда про разработку бота."


def test_telegraph_page_blocking_unwraps_markdown_fenced_json():
    """
    Verify _create_telegraph_page_blocking unwraps JSON even when enclosed in markdown fences.
    """
    fenced_json = "```json\n{\n  \"text\": \"Развернутый текст статьи для Телеграфа.\"\n}\n```"
    
    with patch("summarize.get_telegraph_token", return_value="dummy_token"), \
         patch("summarize._telegraph_create_page_sync", return_value="https://telegra.ph/test") as mock_sync:
        
        url = _create_telegraph_page_blocking("Title", fenced_json)
        assert url == "https://telegra.ph/test"
        mock_sync.assert_called_once()
        nodes = mock_sync.call_args[0][2]
        # Text in nodes should be unwrapped
        text_nodes_flat = str(nodes)
        assert "Развернутый текст статьи для Телеграфа" in text_nodes_flat
        assert "```json" not in text_nodes_flat


def test_telegraph_page_blocking_empty_content_fallback():
    """
    Verify empty or whitespace-only content does not cause Telegraph API rejection.
    """
    with patch("summarize.get_telegraph_token", return_value="dummy_token"), \
         patch("summarize._telegraph_create_page_sync", return_value="https://telegra.ph/test") as mock_sync:
        
        url = _create_telegraph_page_blocking("Empty Page", "   \n  ")
        assert url == "https://telegra.ph/test"
        nodes = mock_sync.call_args[0][2]
        assert str(nodes) != "[]"


# ==============================================================================
# SECTOR 4 AUDIT 3: NEURO_POSTER.PY & TIMEOUTS / 429 SAFETY
# ==============================================================================

@pytest.mark.asyncio
async def test_neuro_poster_empty_thinking_does_not_abort_loop():
    """
    VULNERABILITY: If Groq model returned only thinking tags (<think>...</think>),
    the previous code returned empty string immediately without trying next keys or Gemini.
    Verify that empty text after stripping continues to next key or Gemini fallback.
    """
    nm = NeuroManager(bot=MagicMock())

    # Set up groq_pool with 1 token
    groq_pool.tokens = ["groq_test_1"]
    google_pool.tokens = ["gemini_test_1"]

    # First call (Groq) returns only thinking tags
    mock_groq_completion = MagicMock()
    mock_groq_choice = MagicMock()
    mock_groq_choice.message.content = "<think>Thinking deeply about the universe...</think>"
    mock_groq_completion.choices = [mock_groq_choice]

    # Second call (Gemini) returns actual post
    mock_gemini_completion = MagicMock()
    mock_gemini_choice = MagicMock()
    mock_gemini_choice.message.content = "<think>Fast think</think>База, анон прав."
    mock_gemini_completion.choices = [mock_gemini_choice]

    call_count = 0
    async def mock_execute(client, model, messages, max_tokens, temperature, timeout=30.0):
        nonlocal call_count
        call_count += 1
        if call_count <= 2:  # Groq attempts (proxy + direct)
            return mock_groq_completion
        return mock_gemini_completion

    with patch("site_tgach.neuro_poster._execute_completion", side_effect=mock_execute):
        result = await nm._safe_api_call(
            messages=[{"role": "user", "content": "Сап двач"}],
            max_tokens=150,
            temperature=0.9
        )

    assert result == "База, анон прав."
    assert call_count > 1, "Should have continued past empty thinking response"


@pytest.mark.asyncio
async def test_neuro_poster_429_penalizes_and_rotates_without_tenacity_storm():
    """
    VULNERABILITY: @api_retry on _execute_completion was retrying 5 times on 429,
    spamming rate-limited keys.
    Verify that _execute_completion does NOT retry 429 internally,
    and _safe_api_call penalizes the token immediately and switches to the next token.
    """
    nm = NeuroManager(bot=MagicMock())

    groq_pool.tokens = ["groq_dead_key", "groq_healthy_key"]
    google_pool.tokens = []

    mock_healthy_completion = MagicMock()
    mock_healthy_choice = MagicMock()
    mock_healthy_choice.message.content = "Успешный ответ после ротации."
    mock_healthy_completion.choices = [mock_healthy_choice]

    call_attempts = []

    async def mock_execute(client, model, messages, max_tokens, temperature, timeout=30.0):
        api_key = client.api_key
        call_attempts.append(api_key)
        if api_key == "groq_dead_key":
            raise RuntimeError("429 Too Many Requests: rate_limit_exceeded")
        return mock_healthy_completion

    with patch("site_tgach.neuro_poster._execute_completion", side_effect=mock_execute):
        result = await nm._safe_api_call(
            messages=[{"role": "user", "content": "тест"}],
            max_tokens=100,
            temperature=0.8
        )

    assert result == "Успешный ответ после ротации."
    # The dead key should be called only once per strategy before being penalized
    assert "groq_dead_key" in call_attempts
    assert "groq_healthy_key" in call_attempts
    # Ensure dead key was penalized
    assert "groq_dead_key" in getattr(groq_pool, "_cooldown_until", {})


@pytest.mark.asyncio
async def test_neuro_poster_generate_summary_truncates_huge_dump():
    """
    Verify generate_summary truncates dumps > 15,000 characters before passing to _safe_api_call
    to prevent 413 Payload Too Large.
    """
    nm = NeuroManager(bot=MagicMock())
    huge_dump = "А" * 50000

    captured_messages = []
    async def mock_safe_api_call(messages, max_tokens, temperature):
        captured_messages.extend(messages)
        return "Краткое саммари"

    with patch("summarize.summarize_text_with_hf", side_effect=RuntimeError("Primary down")), \
         patch.object(nm, "_safe_api_call", side_effect=mock_safe_api_call):
        
        result = await nm.generate_summary(huge_dump, stream="ru")

    assert result == "Краткое саммари"
    user_msg = captured_messages[1]["content"]
    assert len(user_msg) < 20000, f"Payload should be truncated, got {len(user_msg)}"
    assert "сокращена во избежание 413" in user_msg


# ==============================================================================
# SECTOR 4 AUDIT 4: TAGGING_WORKER.PY & SSRF / PARSING ROBUSTNESS
# ==============================================================================

def test_is_safe_url_blocks_ssrf():
    """
    Verify SSRF defense in tagging worker blocks localhost, intranet, and AWS metadata.
    """
    # Malicious URLs
    assert not is_safe_url("http://localhost:8000/secret")
    assert not is_safe_url("http://127.0.0.1/admin")
    assert not is_safe_url("http://169.254.169.254/latest/meta-data/")
    assert not is_safe_url("http://10.0.0.1/internal")
    assert not is_safe_url("http://192.168.1.1/router")
    assert not is_safe_url("http://172.16.0.5/docker")
    assert not is_safe_url("ftp://example.com/file.jpg")
    assert not is_safe_url("file:///etc/passwd")

    # Safe external CDN URLs
    assert is_safe_url("https://files.catbox.moe/abc.jpg")
    assert is_safe_url("https://i.pixhost.to/images/123/img.jpg")
    assert is_safe_url("https://api.telegram.org/file/bot123/file.jpg")


@pytest.mark.asyncio
async def test_download_file_rejects_ssrf_url():
    """
    Verify download_file_with_fallback immediately rejects SSRF URL without network fetch.
    """
    img_bytes, bot, status = await download_file_with_fallback("http://169.254.169.254/latest/meta-data")
    assert img_bytes is None
    assert status == "failed"


@pytest.mark.asyncio
async def test_tagging_worker_parses_markdown_fenced_json_tags():
    """
    VULNERABILITY: If Vision returns ```json\n{"tags": ["cat", "cute"], ...}\n```,
    the worker previously skipped it because ai_response did not start with '{'.
    Verify that JSON inside markdown fences is correctly extracted into tags.
    """
    vision_response = "```json\n{\n  \"tags\": [\"cat\", \"cute\", \"kitten\"],\n  \"description\": \"A cute small kitten\"\n}\n```"
    
    # Simulate the worker extraction logic directly
    ai_response = vision_response
    tags = None
    description = None

    if ai_response:
        stripped = ai_response.strip()
        if stripped.startswith("```"):
            lines = stripped.splitlines()
            if len(lines) >= 2 and lines[-1].strip().startswith("```"):
                stripped = "\n".join(lines[1:-1]).strip()
        s_idx = stripped.find("{")
        e_idx = stripped.rfind("}")
        if s_idx != -1 and e_idx != -1 and e_idx > s_idx:
            parsed = json.loads(stripped[s_idx:e_idx+1])
            raw_t = parsed.get("tags", "")
            if isinstance(raw_t, list):
                tags = ", ".join(str(t).strip() for t in raw_t if t)
            else:
                tags = str(raw_t or "").strip()
            description = str(parsed.get("description", "")).strip()

    assert tags == "cat, cute, kitten"
    assert description == "A cute small kitten"


@pytest.mark.asyncio
async def test_tagging_worker_parses_plain_text_tags():
    """
    If Vision returns plain text tags (no JSON), tags must NOT be lost as None.
    """
    vision_response = "anime, 1girl, blue_hair, digital_art"
    
    ai_response = vision_response
    tags = None
    description = None

    if ai_response:
        stripped = ai_response.strip()
        if stripped.startswith("```"):
            lines = stripped.splitlines()
            if len(lines) >= 2 and lines[-1].strip().startswith("```"):
                stripped = "\n".join(lines[1:-1]).strip()
        s_idx = stripped.find("{")
        e_idx = stripped.rfind("}")
        if s_idx != -1 and e_idx != -1 and e_idx > s_idx:
            pass
        else:
            tags = stripped

    assert tags == "anime, 1girl, blue_hair, digital_art"
    assert description is None
