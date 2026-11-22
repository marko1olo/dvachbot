import pytest
import sys
import os
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
import httpx

# Ensure project root is in sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from common.text_utils import filter_gemini_refusals, clean_ai_thinking
from summarize import (
    GEMINI_SAFETY_SETTINGS_BLOCK_NONE,
    GEMINI_SAFETY_SETTINGS_BLOCK_ONLY_HIGH,
    is_gemini_service_refusal,
    _call_gemini_native_rest,
    dispatch_llm_completion,
    summarize_text_with_hf,
)


def test_filter_gemini_refusals():
    assert filter_gemini_refusals("The request asks for something illegal.") == ""
    assert filter_gemini_refusals("I cannot fulfill this request.") == ""
    assert filter_gemini_refusals("I am unable to transcribe this audio.") == ""
    assert filter_gemini_refusals("This is a normal response.") == "This is a normal response."
    assert filter_gemini_refusals("") == ""
    assert filter_gemini_refusals(None) == ""


def test_clean_ai_thinking_with_refusal():
    text = "Thinking: This is a thought. The request asks for something illegal."
    cleaned = clean_ai_thinking(text)
    assert cleaned == ""


def test_clean_ai_thinking_without_refusal():
    text = "This is a normal response."
    cleaned = clean_ai_thinking(text)
    assert cleaned == "This is a normal response."


def test_gemini_safety_settings_block_none_categories():
    """Verify BLOCK_NONE is configured for all required harm categories."""
    categories = {s["category"]: s["threshold"] for s in GEMINI_SAFETY_SETTINGS_BLOCK_NONE}
    assert categories["HARM_CATEGORY_HARASSMENT"] == "BLOCK_NONE"
    assert categories["HARM_CATEGORY_HATE_SPEECH"] == "BLOCK_NONE"
    assert categories["HARM_CATEGORY_SEXUALLY_EXPLICIT"] == "BLOCK_NONE"
    assert categories["HARM_CATEGORY_DANGEROUS_CONTENT"] == "BLOCK_NONE"
    assert categories["HARM_CATEGORY_CIVIC_INTEGRITY"] == "BLOCK_NONE"


def test_is_gemini_service_refusal_multilingual():
    """Verify refusal markers detect both Russian and English canned AI refusals."""
    assert is_gemini_service_refusal("I cannot fulfill this request")
    assert is_gemini_service_refusal("My safety policies do not permit this")
    assert is_gemini_service_refusal("Я не могу выполнить этот запрос")
    assert is_gemini_service_refusal("Позвоните по телефону доверия")
    assert not is_gemini_service_refusal("Здорово, анон! Это нормальный ответ без цензуры.")


@pytest.mark.asyncio
async def test_call_gemini_native_rest_prompt_blocked_prohibited():
    """When Gemini API blocks prompt with PROHIBITED_CONTENT, returns (None, 'safety')."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "promptFeedback": {
            "blockReason": "PROHIBITED_CONTENT",
            "safetyRatings": [
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "probability": "HIGH"}
            ]
        }
    }
    mock_client = AsyncMock()
    mock_client.post.return_value = mock_resp

    content, finish_reason = await _call_gemini_native_rest(
        http_client=mock_client,
        model_name="gemini-3.5-flash-lite",
        api_key="test-key",
        system_instruction="Sensitive prompt",
        user_text="User post",
    )
    assert content is None
    assert finish_reason == "safety"


@pytest.mark.asyncio
async def test_call_gemini_native_rest_finish_reason_safety():
    """When Gemini returns candidate with finishReason == SAFETY, returns text and 'safety'."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "candidates": [
            {
                "finishReason": "SAFETY",
                "content": {"parts": [{"text": "Partial text before cut..."}]}
            }
        ]
    }
    mock_client = AsyncMock()
    mock_client.post.return_value = mock_resp

    content, finish_reason = await _call_gemini_native_rest(
        http_client=mock_client,
        model_name="gemini-3.5-flash-lite",
        api_key="test-key",
        system_instruction="Sensitive prompt",
        user_text="User post",
    )
    assert content == "Partial text before cut..."
    assert finish_reason == "safety"


@pytest.mark.asyncio
async def test_seamless_fallback_on_safety_filter():
    """
    When Gemini triggers a safety filter, the cascade seamlessly fails over to Groq
    without crashing or returning an empty string.
    """
    import summarize
    summarize._key_cooldowns.clear()
    summarize._provider_cooldowns.clear()
    summarize._model_cooldowns.clear()

    # Model 1 (Gemini) triggers safety block
    async def mock_gemini_call(*args, **kwargs):
        return None, "safety"

    # Model 2 (Groq) succeeds
    mock_completion = MagicMock()
    mock_completion.choices = [MagicMock()]
    mock_completion.choices[0].finish_reason = "stop"
    mock_completion.choices[0].message.content = '{"reply": true, "text": "Разъёб засчитан!"}'

    mock_openai_client = AsyncMock()
    mock_openai_client.chat.completions.create.return_value = mock_completion

    with patch("summarize._call_gemini_native_rest", side_effect=mock_gemini_call), \
         patch("summarize.AsyncOpenAI", return_value=mock_openai_client), \
         patch("summarize.google_pool.get_all_active_tokens", return_value=["gkey1"]), \
         patch("summarize.groq_pool.get_all_active_tokens", return_value=["groqkey1"]):
        
        result = await dispatch_llm_completion(
            prompt="Ты — Киберчед",
            text_dump="Оскорбительный пост анона",
            model_preference="persona_gemini"
        )

        assert result is not None
        assert "Разъёб засчитан!" in result
        assert not result.startswith("Нейронка сдохла")


@pytest.mark.asyncio
async def test_read_timeout_cooldown_and_failover():
    """
    When a slow model encounters a ReadTimeout, it is placed on cooldown and
    the cascade immediately switches to the next candidate model.
    """
    import summarize
    summarize._key_cooldowns.clear()
    summarize._provider_cooldowns.clear()
    summarize._model_cooldowns.clear()

    call_models = []

    async def mock_gemini_call(http_client, model_name, *args, **kwargs):
        call_models.append(model_name)
        if "3.7" in model_name or "3.6" in model_name:
            raise httpx.ReadTimeout("Read timed out on slow reasoning model")
        return '{"reply": true, "text": "Быстрый ответ от flash-lite"}', "stop"

    with patch("summarize._call_gemini_native_rest", side_effect=mock_gemini_call), \
         patch("summarize.google_pool.get_all_active_tokens", return_value=["gkey1"]):
        
        result = await dispatch_llm_completion(
            prompt="Ты — Киберчед",
            text_dump="Быстрый тред",
            model_preference="gemini"
        )

        assert result is not None
        assert "Быстрый ответ" in result
        # Verify that timed-out models got placed on cooldown
        for m in call_models:
            if "3.7" in m or "3.6" in m:
                assert summarize._model_cooldowns.get(m, 0) > 0


@pytest.mark.asyncio
async def test_cyberchad_prompt_preserves_umlauts():
    """Verify that Cyberchad system prompt preserves translit-umlauts for sensitive themes."""
    from ai_manager import CYBERCHAD_SYSTEM_JSON_PROMPT
    assert "pёtlü zаlёz" in CYBERCHAD_SYSTEM_JSON_PROMPT
    assert "Vÿydï v öknö" in CYBERCHAD_SYSTEM_JSON_PROMPT


def test_ai_manager_uses_shared_gemini_safety_settings():
    """Verify ai_manager imports and uses GEMINI_SAFETY_SETTINGS_BLOCK_NONE."""
    import ai_manager
    assert hasattr(ai_manager, "GEMINI_SAFETY_SETTINGS_BLOCK_NONE")
    assert ai_manager.GEMINI_SAFETY_SETTINGS_BLOCK_NONE is GEMINI_SAFETY_SETTINGS_BLOCK_NONE
