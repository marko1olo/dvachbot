import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from summarize import summarize_text_with_hf

@pytest.fixture(autouse=True)
def reset_summarize_module_state():
    import summarize
    summarize._key_cooldowns.clear()
    summarize._SHARED_HTTP_CLIENT = None
    if hasattr(summarize, "_provider_cooldowns"):
        summarize._provider_cooldowns.clear()
    yield
    summarize._key_cooldowns.clear()
    summarize._SHARED_HTTP_CLIENT = None
    if hasattr(summarize, "_provider_cooldowns"):
        summarize._provider_cooldowns.clear()


@pytest.mark.asyncio
@patch("summarize.httpx.AsyncHTTPTransport")
@patch("summarize.httpx.AsyncClient")
@patch("summarize.AsyncOpenAI")
@patch("summarize.google_pool.get_all_active_tokens", return_value=["google-key"])
@patch("summarize.groq_pool.get_all_active_tokens", return_value=["groq-key"])
async def test_summarize_success_removes_think_tags(
    mock_groq_tokens, mock_google_tokens, mock_async_openai, mock_httpx_client, mock_httpx_transport
):
    mock_client = AsyncMock()
    mock_async_openai.return_value = mock_client

    mock_completion = MagicMock()
    mock_completion.choices = [MagicMock()]
    mock_completion.choices[0].message.content = "<think>Thinking...</think>\nActual Summary."
    mock_client.chat.completions.create.return_value = mock_completion

    result = await summarize_text_with_hf("Prompt", "Text", model_preference="llama")

    assert result == "Actual Summary."
    mock_client.chat.completions.create.assert_called_once()
    assert mock_client.chat.completions.create.call_args[1]["model"] == "qwen/qwen3.8-27b"


@pytest.mark.asyncio
@patch("summarize.httpx.AsyncHTTPTransport")
@patch("summarize.httpx.AsyncClient")
@patch("summarize.AsyncOpenAI")
@patch("summarize.google_pool.get_all_active_tokens", return_value=["google-key"])
@patch("summarize.groq_pool.get_all_active_tokens", return_value=["groq-key"])
async def test_summarize_fails_all_retries(
    mock_groq_tokens, mock_google_tokens, mock_async_openai, mock_httpx_client, mock_httpx_transport
):
    mock_client = AsyncMock()
    mock_async_openai.return_value = mock_client
    mock_client.chat.completions.create.side_effect = Exception("API Error")

    result = await summarize_text_with_hf("Prompt", "Text", model_preference="llama")

    assert result == "Нейронка сдохла. Не удалось сгенерировать саммари."


@pytest.mark.asyncio
@patch("summarize.httpx.AsyncHTTPTransport")
@patch("summarize.httpx.AsyncClient")
@patch("summarize.AsyncOpenAI")
@patch("summarize.google_pool.get_all_active_tokens", return_value=["google-key"])
@patch("summarize.groq_pool.get_all_active_tokens", return_value=["groq-key"])
@patch("summarize.groq_pool.remove_token")
async def test_summarize_401_removes_token(
    mock_remove_token, mock_groq_tokens, mock_google_tokens, mock_async_openai, mock_httpx_client, mock_httpx_transport
):
    mock_client = AsyncMock()
    mock_async_openai.return_value = mock_client
    mock_client.chat.completions.create.side_effect = Exception("401 Unauthorized")

    result = await summarize_text_with_hf("Prompt", "Text", model_preference="llama")

    assert result == "Нейронка сдохла. Не удалось сгенерировать саммари."
    mock_remove_token.assert_any_call("groq-key")


@pytest.mark.asyncio
@patch("summarize.httpx.AsyncHTTPTransport")
@patch("summarize.httpx.AsyncClient")
@patch("summarize.AsyncOpenAI")
@patch("summarize.google_pool.get_all_active_tokens", return_value=["google-key"])
@patch("summarize.groq_pool.get_all_active_tokens", return_value=["groq-key"])
async def test_summarize_413_skips_model(
    mock_groq_tokens, mock_google_tokens, mock_async_openai, mock_httpx_client, mock_httpx_transport
):
    mock_client = AsyncMock()
    mock_async_openai.return_value = mock_client

    mock_completion = MagicMock()
    mock_completion.choices = [MagicMock()]
    mock_completion.choices[0].message.content = "Summary from second model."

    mock_client.chat.completions.create.side_effect = [
        Exception("413 Request Entity Too Large"),
        mock_completion
    ]

    result = await summarize_text_with_hf("Prompt", "Text")

    assert result == "Summary from second model."
    assert mock_client.chat.completions.create.call_count == 2
    calls = mock_client.chat.completions.create.call_args_list
    assert calls[0].kwargs["model"] != calls[1].kwargs["model"]


@pytest.mark.asyncio
@patch("summarize.httpx.AsyncHTTPTransport")
@patch("summarize.httpx.AsyncClient")
@patch("summarize.AsyncOpenAI")
@patch("summarize.google_pool.get_all_active_tokens", return_value=["google-key1", "google-key2"])
@patch("summarize.groq_pool.get_all_active_tokens", return_value=[])
async def test_summarize_429_switches_key(
    mock_groq_tokens, mock_google_tokens, mock_async_openai, mock_httpx_client, mock_httpx_transport
):
    mock_client = AsyncMock()
    mock_async_openai.return_value = mock_client

    mock_completion = MagicMock()
    mock_completion.choices = [MagicMock()]
    mock_completion.choices[0].message.content = "Summary after switching key."

    mock_client.chat.completions.create.side_effect = [
        Exception("429 Too Many Requests"),
        mock_completion
    ]

    result = await summarize_text_with_hf("Prompt", "Text", model_preference="gemini")

    assert result == "Summary after switching key."
    assert mock_client.chat.completions.create.call_count == 2
    used_keys = [c.kwargs["api_key"] for c in mock_async_openai.call_args_list]
    assert used_keys == ["google-key1", "google-key2"]
    import summarize
    assert ("gemini", "google-key1") in summarize._key_cooldowns
    assert ("gemini", "google-key2") not in summarize._key_cooldowns


@pytest.mark.asyncio
@patch("summarize.httpx.AsyncHTTPTransport")
@patch("summarize.httpx.AsyncClient")
@patch("summarize.AsyncOpenAI")
@patch("summarize.google_pool.get_all_active_tokens", return_value=[])
@patch("summarize.groq_pool.get_all_active_tokens", return_value=[])
async def test_summarize_no_keys_skips_model(
    mock_groq_tokens, mock_google_tokens, mock_async_openai, mock_httpx_client, mock_httpx_transport
):
    result = await summarize_text_with_hf("Prompt", "Text", model_preference="llama")

    assert result == "Нейронка сдохла. Не удалось сгенерировать саммари."
    mock_async_openai.assert_not_called()


@pytest.mark.asyncio
@patch("summarize.httpx.AsyncHTTPTransport")
@patch("summarize.httpx.AsyncClient")
@patch("summarize.AsyncOpenAI")
@patch("summarize.google_pool.get_all_active_tokens", return_value=["google-key"])
@patch("summarize.groq_pool.get_all_active_tokens", return_value=["groq-key"])
async def test_summarize_empty_result(
    mock_groq_tokens, mock_google_tokens, mock_async_openai, mock_httpx_client, mock_httpx_transport
):
    mock_client = AsyncMock()
    mock_async_openai.return_value = mock_client

    mock_completion = MagicMock()
    mock_completion.choices = [MagicMock()]
    mock_completion.choices[0].message.content = ""
    mock_client.chat.completions.create.return_value = mock_completion

    result = await summarize_text_with_hf("Prompt", "Text", model_preference="llama")

    assert result == "Нейронка сдохла. Не удалось сгенерировать саммари."


def test_load_google_keys():
    from summarize import _load_google_keys
    with patch("os.path.exists", return_value=True), \
         patch("builtins.open", unittest_mock_open(read_data="GOOGLE_API_KEYS=key1,key2, key3 \n")):
        keys = _load_google_keys()
        assert keys == ["key1", "key2", "key3"]


def unittest_mock_open(read_data=""):
    from unittest.mock import mock_open
    return mock_open(read_data=read_data)


def test_get_telegraph_token_cached():
    from summarize import get_telegraph_token
    import summarize
    summarize._telegraph_token_cache = "cached_token"
    assert get_telegraph_token() == "cached_token"
    summarize._telegraph_token_cache = None


def test_get_telegraph_token_env_var():
    from summarize import get_telegraph_token
    import summarize
    summarize._telegraph_token_cache = None
    with patch.dict("os.environ", {"TELEGRAPH_TOKEN": "env_token"}):
        assert get_telegraph_token() == "env_token"
    summarize._telegraph_token_cache = None


def test_get_telegraph_token_file():
    from summarize import get_telegraph_token
    import summarize
    summarize._telegraph_token_cache = None
    with patch.dict("os.environ", {}, clear=True), \
         patch("os.path.exists", return_value=True), \
         patch("builtins.open", unittest_mock_open(read_data="file_token")):
        assert get_telegraph_token() == "file_token"
    summarize._telegraph_token_cache = None


def test_get_telegraph_token_generation_success():
    from summarize import get_telegraph_token
    import summarize
    summarize._telegraph_token_cache = None
    with patch.dict("os.environ", {}, clear=True), \
         patch("os.path.exists", return_value=False), \
         patch("summarize._telegraph_create_account_sync", return_value="new_token"), \
         patch("builtins.open", unittest_mock_open()):
        assert get_telegraph_token() == "new_token"
    summarize._telegraph_token_cache = None


def test_get_telegraph_token_generation_failure():
    from summarize import get_telegraph_token
    import summarize
    summarize._telegraph_token_cache = None
    with patch.dict("os.environ", {}, clear=True), \
         patch("os.path.exists", return_value=False), \
         patch("summarize._telegraph_create_account_sync", side_effect=Exception("Failed")):
        assert get_telegraph_token() == ""
    summarize._telegraph_token_cache = None

