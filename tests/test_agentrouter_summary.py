import asyncio
import time
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from summarize import summarize_text_with_hf, _model_cooldowns, _key_cooldowns
from common.token_pool import agentrouter_pool, TokenRotator

@pytest.fixture(autouse=True)
def reset_module_state():
    import summarize
    summarize._key_cooldowns.clear()
    summarize._model_cooldowns.clear()
    summarize._provider_cooldowns.clear()
    summarize._SHARED_HTTP_CLIENT = None
    summarize._SUMMARY_CACHE.clear()
    yield
    summarize._key_cooldowns.clear()
    summarize._model_cooldowns.clear()
    summarize._provider_cooldowns.clear()
    summarize._SHARED_HTTP_CLIENT = None
    summarize._SUMMARY_CACHE.clear()


def test_agentrouter_pool_dedup_and_round_robin():
    """Verify agentrouter_pool deduplication, active tokens and rotation."""
    pool = TokenRotator(raw="sk-key1, sk-key2, sk-key1, sk-key3", min_interval=1.0, name="TestAR")
    assert pool.tokens == ["sk-key1", "sk-key2", "sk-key3"]
    
    # First rotation
    tokens_batch1 = pool.get_all_active_tokens()
    assert tokens_batch1 == ["sk-key1", "sk-key2", "sk-key3"]
    
    # Second rotation (shifted index)
    tokens_batch2 = pool.get_all_active_tokens()
    assert tokens_batch2 == ["sk-key2", "sk-key3", "sk-key1"]


@pytest.mark.asyncio
@patch("summarize.AsyncOpenAI")
@patch("summarize.agentrouter_pool.get_all_active_tokens", return_value=["sk-ar-test-01"])
@patch("summarize.google_pool.get_all_active_tokens", return_value=["google-key-01"])
@patch("summarize.groq_pool.get_all_active_tokens", return_value=["groq-key-01"])
async def test_default_preference_routes_to_deepseek_first(
    mock_groq, mock_google, mock_ar, mock_openai_cls
):
    """Default summary cascade routes to deepseek-v4-flash via AgentRouter with correct headers and tokens."""
    mock_client = AsyncMock()
    mock_openai_cls.return_value = mock_client
    
    mock_completion = MagicMock()
    mock_completion.choices = [MagicMock(message=MagicMock(content="<think>CoT reasoning</think>\n<b>Главные новости треда</b>"))]
    mock_client.chat.completions.create.return_value = mock_completion

    result = await summarize_text_with_hf("Prompt", "Text content")

    assert result == "<b>Главные новости треда</b>"
    
    # Verify client initialization arguments
    client_kwargs = mock_openai_cls.call_args[1]
    assert client_kwargs["api_key"] == "sk-ar-test-01"
    assert "agentrouter.org" in client_kwargs["base_url"]
    assert client_kwargs.get("default_headers") == {"User-Agent": "opencode/1.18.25"}
    
    # Verify create arguments: model and max_tokens
    create_kwargs = mock_client.chat.completions.create.call_args[1]
    assert create_kwargs["model"] == "deepseek-v4-flash"
    assert create_kwargs["max_tokens"] >= 4096


@pytest.mark.asyncio
@patch("summarize.AsyncOpenAI")
@patch("summarize.agentrouter_pool.get_all_active_tokens", return_value=["sk-ar-test-01"])
@patch("summarize.google_pool.get_all_active_tokens", return_value=["google-key-01"])
@patch("summarize.groq_pool.get_all_active_tokens", return_value=["groq-key-01"])
async def test_explicit_deepseek_preference(
    mock_groq, mock_google, mock_ar, mock_openai_cls
):
    """Explicit model_preference='deepseek' queries deepseek-v4-flash first."""
    mock_client = AsyncMock()
    mock_openai_cls.return_value = mock_client
    
    mock_completion = MagicMock()
    mock_completion.choices = [MagicMock(message=MagicMock(content="Ответ DeepSeek"))]
    mock_client.chat.completions.create.return_value = mock_completion

    result = await summarize_text_with_hf("Prompt", "Text content", model_preference="deepseek")

    assert result == "Ответ DeepSeek"
    assert mock_client.chat.completions.create.call_args[1]["model"] == "deepseek-v4-flash"


@pytest.mark.asyncio
@patch("summarize.AsyncOpenAI")
@patch("summarize.agentrouter_pool.get_all_active_tokens", return_value=["sk-ar-test-01"])
@patch("summarize.agentrouter_pool.penalize_token")
@patch("summarize.google_pool.get_all_active_tokens", return_value=["google-key-01"])
@patch("summarize.groq_pool.get_all_active_tokens", return_value=["groq-key-01"])
async def test_agentrouter_402_budget_pool_cooldowns_model_not_key(
    mock_groq, mock_google, mock_penalize_token, mock_ar, mock_openai_cls
):
    """Error 402 Budget pool quota exhausted puts model on 30m cooldown without penalizing key, then falls back."""
    mock_client = AsyncMock()
    mock_openai_cls.return_value = mock_client

    # First call to DeepSeek fails with 402 Budget pool
    # Second call (Gemini via AsyncOpenAI in mock env) succeeds
    mock_completion_fallback = MagicMock()
    mock_completion_fallback.choices = [MagicMock(message=MagicMock(content="Fallback Gemini summary"))]

    mock_client.chat.completions.create.side_effect = [
        Exception("Error code: 402 - {'error': {'message': 'Budget pool quota has been exhausted. Please ask an administrator to increase the limit'}}"),
        mock_completion_fallback
    ]

    result = await summarize_text_with_hf("Prompt", "Text content")

    assert result == "Fallback Gemini summary"
    
    # Model must be on cooldown
    assert "deepseek-v4-flash" in _model_cooldowns
    assert _model_cooldowns["deepseek-v4-flash"] > time.time() + 1700
    
    # Key must NOT have been penalized
    mock_penalize_token.assert_not_called()


@pytest.mark.asyncio
@patch("summarize.AsyncOpenAI")
@patch("summarize.agentrouter_pool.get_all_active_tokens", return_value=[])
@patch("summarize.google_pool.get_all_active_tokens", return_value=["google-key-01"])
@patch("summarize.groq_pool.get_all_active_tokens", return_value=["groq-key-01"])
async def test_agentrouter_fallback_when_no_keys(
    mock_groq, mock_google, mock_ar, mock_openai_cls
):
    """When agentrouter has no keys configured, cascade skips DeepSeek and succeeds on Gemini."""
    mock_client = AsyncMock()
    mock_openai_cls.return_value = mock_client

    mock_completion = MagicMock()
    mock_completion.choices = [MagicMock(message=MagicMock(content="Gemini summary response"))]
    mock_client.chat.completions.create.return_value = mock_completion

    result = await summarize_text_with_hf("Prompt", "Text content")

    assert result == "Gemini summary response"
    # First model called should be gemini-3.5-flash since deepseek was skipped
    assert mock_client.chat.completions.create.call_args[1]["model"] == "gemini-3.5-flash"
