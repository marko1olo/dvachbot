import pytest
from unittest.mock import MagicMock, AsyncMock, patch
import httpx
from summarize import _call_gemini_native_rest, call_gemini_rest, dispatch_llm_completion

pytestmark = pytest.mark.asyncio


async def test_call_gemini_rest_alias_identity():
    """Verify call_gemini_rest is an alias of _call_gemini_native_rest."""
    assert call_gemini_rest is _call_gemini_native_rest


async def test_gemini_gen_config_never_sends_penalties():
    """
    Requirement 2a: Verify gen_config never sends presencePenalty / frequencyPenalty
    to Google Gemini REST endpoint, even when presence_penalty and frequency_penalty
    are explicitly passed to call_gemini_rest.
    """
    mock_http_client = AsyncMock(spec=httpx.AsyncClient)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = '{"candidates": [{"content": {"parts": [{"text": "Gemini response text"}]}, "finishReason": "STOP"}]}'
    mock_resp.json.return_value = {
        "candidates": [
            {
                "content": {
                    "parts": [{"text": "Gemini response text"}]
                },
                "finishReason": "STOP"
            }
        ]
    }
    mock_http_client.post.return_value = mock_resp

    text, finish = await call_gemini_rest(
        http_client=mock_http_client,
        model_name="gemini-3.5-flash",
        api_key="test-api-key",
        system_instruction="System prompt",
        user_text="User prompt",
        temperature=0.85,
        presence_penalty=0.35,
        frequency_penalty=0.45,
    )

    assert text == "Gemini response text"
    assert finish == "stop"
    assert mock_http_client.post.called

    call_kwargs = mock_http_client.post.call_args[1]
    payload = call_kwargs["json"]
    assert "generationConfig" in payload
    gen_config = payload["generationConfig"]

    # Invariants: presencePenalty and frequencyPenalty MUST NEVER be in gen_config
    assert "presencePenalty" not in gen_config
    assert "frequencyPenalty" not in gen_config
    assert gen_config["temperature"] == 0.85
    assert gen_config["maxOutputTokens"] == 2048


async def test_gemini_penalty_400_fallback_retries_and_succeeds():
    """
    Requirement 2b: If a 400 'Penalty is not enabled' is received from Gemini REST API,
    call_gemini_rest immediately removes penalties from gen_config, retries once,
    and returns the successful response without falling through to agentrouter/timeout.
    """
    mock_http_client = AsyncMock(spec=httpx.AsyncClient)

    # First call: 400 error because penalties are rejected
    mock_resp_400 = MagicMock()
    mock_resp_400.status_code = 400
    mock_resp_400.text = '{"error": {"code": 400, "message": "Penalty is not enabled for this model", "status": "INVALID_ARGUMENT"}}'

    # Second call (retry): 200 OK after penalties are stripped
    mock_resp_200 = MagicMock()
    mock_resp_200.status_code = 200
    mock_resp_200.text = '{"candidates": [{"content": {"parts": [{"text": "Fast AI reply recovered!"}]}, "finishReason": "STOP"}]}'
    mock_resp_200.json.return_value = {
        "candidates": [
            {
                "content": {
                    "parts": [{"text": "Fast AI reply recovered!"}]
                },
                "finishReason": "STOP"
            }
        ]
    }

    mock_http_client.post.side_effect = [mock_resp_400, mock_resp_200]

    text, finish = await call_gemini_rest(
        http_client=mock_http_client,
        model_name="gemini-3.1-flash-lite",
        api_key="test-api-key",
        system_instruction="System prompt",
        user_text="User prompt",
        presence_penalty=0.35,
        frequency_penalty=0.45,
    )

    assert text == "Fast AI reply recovered!"
    assert finish == "stop"

    # Exactly 2 calls made: initial and immediate penalty retry
    assert mock_http_client.post.call_count == 2

    # Verify both calls never send penalties, and retry payload is clean
    retry_call = mock_http_client.post.call_args_list[1]
    retry_gen_config = retry_call[1]["json"]["generationConfig"]
    assert "presencePenalty" not in retry_gen_config
    assert "frequencyPenalty" not in retry_gen_config


async def test_gemini_penalty_400_case_insensitive_and_variants():
    """Verify defensive fallback works with lowercase 'penalty is not enabled' error strings."""
    mock_http_client = AsyncMock(spec=httpx.AsyncClient)

    mock_resp_400 = MagicMock()
    mock_resp_400.status_code = 400
    mock_resp_400.text = '{"error": {"message": "frequency_penalty or penalty is not enabled for this model"}}'

    mock_resp_200 = MagicMock()
    mock_resp_200.status_code = 200
    mock_resp_200.text = '{"candidates": [{"content": {"parts": [{"text": "Recovered variant"}]}, "finishReason": "STOP"}]}'
    mock_resp_200.json.return_value = {
        "candidates": [
            {
                "content": {
                    "parts": [{"text": "Recovered variant"}]
                },
                "finishReason": "STOP"
            }
        ]
    }

    mock_http_client.post.side_effect = [mock_resp_400, mock_resp_200]

    text, finish = await call_gemini_rest(
        http_client=mock_http_client,
        model_name="gemini-3.5-flash-lite",
        api_key="test-key",
        system_instruction="",
        user_text="Test prompt",
    )

    assert text == "Recovered variant"
    assert finish == "stop"
    assert mock_http_client.post.call_count == 2


async def test_gemini_non_penalty_400_still_retries_block_only_high():
    """
    Verify that standard 400 (e.g. BLOCK_NONE safety restriction) still falls back
    to GEMINI_SAFETY_SETTINGS_BLOCK_ONLY_HIGH.
    """
    mock_http_client = AsyncMock(spec=httpx.AsyncClient)

    # 400 with BLOCK_NONE error (not penalty)
    mock_resp_block_none_400 = MagicMock()
    mock_resp_block_none_400.status_code = 400
    mock_resp_block_none_400.text = '{"error": {"code": 400, "message": "Safety threshold BLOCK_NONE not supported for account"}}'

    # Second try with BLOCK_ONLY_HIGH succeeds
    mock_resp_200 = MagicMock()
    mock_resp_200.status_code = 200
    mock_resp_200.text = '{"candidates": [{"content": {"parts": [{"text": "Success with BLOCK_ONLY_HIGH"}]}, "finishReason": "STOP"}]}'
    mock_resp_200.json.return_value = {
        "candidates": [
            {
                "content": {
                    "parts": [{"text": "Success with BLOCK_ONLY_HIGH"}]
                },
                "finishReason": "STOP"
            }
        ]
    }

    mock_http_client.post.side_effect = [mock_resp_block_none_400, mock_resp_200]

    text, finish = await call_gemini_rest(
        http_client=mock_http_client,
        model_name="gemini-3.5-flash",
        api_key="test-key",
        system_instruction="",
        user_text="User input",
    )

    assert text == "Success with BLOCK_ONLY_HIGH"
    assert finish == "stop"
    assert mock_http_client.post.call_count == 2
    # Verify second call used BLOCK_ONLY_HIGH
    second_payload = mock_http_client.post.call_args_list[1][1]["json"]
    for setting in second_payload["safetySettings"]:
        assert setting["threshold"] == "BLOCK_ONLY_HIGH"
