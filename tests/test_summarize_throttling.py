import pytest
import time
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
from summarize import summarize_text_with_hf, _throttle_provider, MIN_PROVIDER_INTERVAL

@pytest.fixture(autouse=True)
def reset_summarize_module_state():
    import summarize
    summarize._key_cooldowns.clear()
    summarize._provider_cooldowns.clear()
    summarize._PROVIDER_LAST_REQUEST_TS.clear()
    summarize._SHARED_HTTP_CLIENT = None
    yield
    summarize._key_cooldowns.clear()
    summarize._provider_cooldowns.clear()
    summarize._PROVIDER_LAST_REQUEST_TS.clear()
    summarize._SHARED_HTTP_CLIENT = None


@pytest.mark.asyncio
async def test_throttle_provider_enforces_cooldown():
    """Verify _throttle_provider delays requests when called under MIN_PROVIDER_INTERVAL."""
    import summarize
    with patch.dict("os.environ", {}, clear=True):
        t0 = time.time()
        await _throttle_provider("gemini")
        t1 = time.time()
        await _throttle_provider("gemini")
        t2 = time.time()

        elapsed = t2 - t1
        expected = MIN_PROVIDER_INTERVAL["gemini"]
        assert elapsed >= expected * 0.85, f"Elapsed {elapsed:.2f}s is less than expected {expected:.2f}s"


@pytest.mark.asyncio
@patch("summarize.AsyncOpenAI")
@patch("summarize.google_pool.get_all_active_tokens", return_value=["gkey1", "gkey2", "gkey3", "gkey4"])
@patch("summarize.groq_pool.get_all_active_tokens", return_value=["groq1", "groq2"])
async def test_safety_filter_skips_all_gemini_models(
    mock_groq_tokens, mock_google_tokens, mock_async_openai
):
    """When Gemini returns finish_reason='safety', all remaining Gemini keys/models are skipped and Groq is used."""
    mock_client = AsyncMock()
    mock_async_openai.return_value = mock_client

    safety_choice = MagicMock()
    safety_choice.message.content = None
    safety_choice.finish_reason = "safety"
    safety_completion = MagicMock()
    safety_completion.choices = [safety_choice]

    groq_choice = MagicMock()
    groq_choice.message.content = '{"reply": true, "text": "Разъёб без соплей"}'
    groq_choice.finish_reason = "stop"
    groq_completion = MagicMock()
    groq_completion.choices = [groq_choice]

    mock_client.chat.completions.create.side_effect = [
        safety_completion,
        groq_completion,
    ]

    res = await summarize_text_with_hf("Prompt", "Text", model_preference="persona")

    assert "Разъёб без соплей" in res
    calls = mock_client.chat.completions.create.call_args_list
    assert len(calls) == 2
    assert "gemini" in calls[0].kwargs["model"]
    assert "qwen" in calls[1].kwargs["model"]


@pytest.mark.asyncio
@patch("summarize.AsyncOpenAI")
@patch("summarize.google_pool.get_all_active_tokens", return_value=["gkey1", "gkey2", "gkey3", "gkey4"])
@patch("summarize.groq_pool.get_all_active_tokens", return_value=["groq1"])
async def test_empty_content_skips_after_two_attempts(
    mock_groq_tokens, mock_google_tokens, mock_async_openai
):
    """When a model returns empty content twice, it skips to the next model without querying all keys."""
    mock_client = AsyncMock()
    mock_async_openai.return_value = mock_client

    empty_choice = MagicMock()
    empty_choice.message.content = ""
    empty_choice.finish_reason = "stop"
    empty_completion = MagicMock()
    empty_completion.choices = [empty_choice]

    ok_choice = MagicMock()
    ok_choice.message.content = "Summary result"
    ok_choice.finish_reason = "stop"
    ok_completion = MagicMock()
    ok_completion.choices = [ok_choice]

    mock_client.chat.completions.create.side_effect = [
        empty_completion,
        empty_completion,
        ok_completion,
    ]

    res = await summarize_text_with_hf("Prompt", "Text", model_preference="gemini")
    assert res == "Summary result"
    calls = mock_client.chat.completions.create.call_args_list
    assert len(calls) == 3
    assert calls[0].kwargs["model"] == calls[1].kwargs["model"]
    assert calls[1].kwargs["model"] != calls[2].kwargs["model"]


@pytest.mark.asyncio
@patch("summarize.AsyncOpenAI")
@patch("summarize.google_pool.get_all_active_tokens", return_value=["gkey1", "gkey2", "gkey3"])
@patch("summarize.groq_pool.get_all_active_tokens", return_value=["groq1"])
async def test_consecutive_429_halts_provider_and_sets_cooldown(
    mock_groq_tokens, mock_google_tokens, mock_async_openai
):
    """When provider hits consecutive 429s, provider is put in cooldown and subsequent provider models are skipped."""
    mock_client = AsyncMock()
    mock_async_openai.return_value = mock_client

    ok_choice = MagicMock()
    ok_choice.message.content = "Groq fallback result"
    ok_choice.finish_reason = "stop"
    ok_completion = MagicMock()
    ok_completion.choices = [ok_choice]

    mock_client.chat.completions.create.side_effect = [
        Exception("429 Too Many Requests"),
        Exception("429 Resource Exhausted"),
        ok_completion,
    ]

    import summarize
    res = await summarize_text_with_hf("Prompt", "Text", model_preference="persona")
    assert res == "Groq fallback result"
    assert "gemini" in summarize._provider_cooldowns
    assert summarize._provider_cooldowns["gemini"] > time.time()


@pytest.mark.asyncio
async def test_call_gemini_native_rest_sends_block_none():
    """Verify _call_gemini_native_rest sends BLOCK_NONE safetySettings to Gemini API."""
    from summarize import _call_gemini_native_rest
    mock_http_client = AsyncMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "candidates": [
            {
                "content": {
                    "parts": [{"text": "Разъёб от Чеда без цензуры"}]
                },
                "finishReason": "STOP"
            }
        ]
    }
    mock_http_client.post.return_value = mock_resp

    text, finish = await _call_gemini_native_rest(
        http_client=mock_http_client,
        model_name="gemini-3.1-flash-lite",
        api_key="test-key",
        system_instruction="System instruction",
        user_text="User abusive text",
    )

    assert text == "Разъёб от Чеда без цензуры"
    assert finish == "stop"
    assert mock_http_client.post.called
    call_kwargs = mock_http_client.post.call_args[1]
    payload = call_kwargs["json"]
    assert "safetySettings" in payload
    # All safety thresholds must be BLOCK_NONE
    for setting in payload["safetySettings"]:
        assert setting["threshold"] == "BLOCK_NONE"

