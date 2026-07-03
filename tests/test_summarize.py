import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from summarize import summarize_text_with_hf

@pytest.mark.asyncio
@patch("summarize.httpx.AsyncHTTPTransport")
@patch("summarize.httpx.AsyncClient")
@patch("summarize.AsyncOpenAI")
@patch("summarize._load_google_keys", return_value=["google-key"])
@patch("summarize.groq_pool.get_token", return_value="groq-key")
async def test_summarize_success_removes_think_tags(
    mock_get_token, mock_load_google_keys, mock_async_openai, mock_httpx_client, mock_httpx_transport
):
    mock_client = AsyncMock()
    mock_async_openai.return_value.__aenter__.return_value = mock_client

    mock_completion = MagicMock()
    mock_completion.choices = [MagicMock()]
    mock_completion.choices[0].message.content = "<think>Thinking...</think>\nActual Summary."
    mock_client.chat.completions.create.return_value = mock_completion

    result = await summarize_text_with_hf("Prompt", "Text", model_preference="llama")

    assert result == "Actual Summary."
    mock_client.chat.completions.create.assert_called_once()
    assert mock_client.chat.completions.create.call_args[1]["model"] == "llama-3.3-70b-versatile"

@pytest.mark.asyncio
@patch("summarize.httpx.AsyncHTTPTransport")
@patch("summarize.httpx.AsyncClient")
@patch("summarize.AsyncOpenAI")
@patch("summarize._load_google_keys", return_value=["google-key"])
@patch("summarize.groq_pool.get_token", return_value="groq-key")
async def test_summarize_fails_all_retries(
    mock_get_token, mock_load_google_keys, mock_async_openai, mock_httpx_client, mock_httpx_transport
):
    mock_client = AsyncMock()
    mock_async_openai.return_value.__aenter__.return_value = mock_client
    mock_client.chat.completions.create.side_effect = Exception("API Error")

    result = await summarize_text_with_hf("Prompt", "Text", model_preference="llama")

    assert result == "Нейронка сдохла. Не удалось сгенерировать саммари."

@pytest.mark.asyncio
@patch("summarize.httpx.AsyncHTTPTransport")
@patch("summarize.httpx.AsyncClient")
@patch("summarize.AsyncOpenAI")
@patch("summarize._load_google_keys", return_value=["google-key"])
@patch("summarize.groq_pool.get_token", return_value="groq-key")
@patch("summarize.groq_pool.remove_token")
async def test_summarize_401_removes_token(
    mock_remove_token, mock_get_token, mock_load_google_keys, mock_async_openai, mock_httpx_client, mock_httpx_transport
):
    mock_client = AsyncMock()
    mock_async_openai.return_value.__aenter__.return_value = mock_client
    mock_client.chat.completions.create.side_effect = Exception("401 Unauthorized")

    result = await summarize_text_with_hf("Prompt", "Text", model_preference="llama")

    assert result == "Нейронка сдохла. Не удалось сгенерировать саммари."
    mock_remove_token.assert_called_with("groq-key")

@pytest.mark.asyncio
@patch("summarize.httpx.AsyncHTTPTransport")
@patch("summarize.httpx.AsyncClient")
@patch("summarize.AsyncOpenAI")
@patch("summarize._load_google_keys", return_value=["google-key"])
@patch("summarize.groq_pool.get_token", return_value="groq-key")
async def test_summarize_413_skips_model(
    mock_get_token, mock_load_google_keys, mock_async_openai, mock_httpx_client, mock_httpx_transport
):
    mock_client = AsyncMock()
    mock_async_openai.return_value.__aenter__.return_value = mock_client

    # First call throws 413, second call succeeds
    mock_completion = MagicMock()
    mock_completion.choices = [MagicMock()]
    mock_completion.choices[0].message.content = "Summary from second model."

    # We want it to fail on the first model (gemini) and succeed on the second (gemini fallback or groq)
    # The default cascade is: gemini-3-flash-preview, gemini-3.1-flash-lite, qwen, llama
    mock_client.chat.completions.create.side_effect = [
        Exception("413 Request Entity Too Large"),
        mock_completion
    ]

    result = await summarize_text_with_hf("Prompt", "Text") # Default model_preference

    assert result == "Summary from second model."
    assert mock_client.chat.completions.create.call_count == 2

@pytest.mark.asyncio
@patch("summarize.httpx.AsyncHTTPTransport")
@patch("summarize.httpx.AsyncClient")
@patch("summarize.AsyncOpenAI")
@patch("summarize._load_google_keys", return_value=["google-key1", "google-key2"])
async def test_summarize_429_switches_key(
    mock_load_google_keys, mock_async_openai, mock_httpx_client, mock_httpx_transport
):
    mock_client = AsyncMock()
    mock_async_openai.return_value.__aenter__.return_value = mock_client

    mock_completion = MagicMock()
    mock_completion.choices = [MagicMock()]
    mock_completion.choices[0].message.content = "Summary after switching key."

    # Fail with 429 on key1, then succeed on key2 (gemini)
    mock_client.chat.completions.create.side_effect = [
        Exception("429 Too Many Requests"),
        mock_completion
    ]

    result = await summarize_text_with_hf("Prompt", "Text", model_preference="gemini")

    assert result == "Summary after switching key."
    assert mock_client.chat.completions.create.call_count == 2

@pytest.mark.asyncio
@patch("summarize.httpx.AsyncHTTPTransport")
@patch("summarize.httpx.AsyncClient")
@patch("summarize.AsyncOpenAI")
@patch("summarize._load_google_keys", return_value=[])
@patch("summarize.groq_pool.get_token", return_value=None)
async def test_summarize_no_keys_skips_model(
    mock_get_token, mock_load_google_keys, mock_async_openai, mock_httpx_client, mock_httpx_transport
):
    # Setup mock to make sure client is never created
    result = await summarize_text_with_hf("Prompt", "Text", model_preference="llama")

    assert result == "Нейронка сдохла. Не удалось сгенерировать саммари."
    mock_async_openai.assert_not_called()

@pytest.mark.asyncio
@patch("summarize.httpx.AsyncHTTPTransport")
@patch("summarize.httpx.AsyncClient")
@patch("summarize.AsyncOpenAI")
@patch("summarize._load_google_keys", return_value=["google-key"])
@patch("summarize.groq_pool.get_token", return_value="groq-key")
async def test_summarize_empty_result(
    mock_get_token, mock_load_google_keys, mock_async_openai, mock_httpx_client, mock_httpx_transport
):
    mock_client = AsyncMock()
    mock_async_openai.return_value.__aenter__.return_value = mock_client

    mock_completion = MagicMock()
    mock_completion.choices = [MagicMock()]
    mock_completion.choices[0].message.content = ""
    mock_client.chat.completions.create.return_value = mock_completion

    result = await summarize_text_with_hf("Prompt", "Text", model_preference="llama")

    # It should loop through strategies/models and eventually return failure message
    assert result == "Нейронка сдохла. Не удалось сгенерировать саммари."


def test_load_google_keys(tmp_path, monkeypatch):
    from summarize import _load_google_keys
    import os

    # 1. No .envgoogle, no env var
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GOOGLE_API_KEYS", raising=False)
    assert _load_google_keys() == []

    # 2. Only env var
    monkeypatch.setenv("GOOGLE_API_KEYS", "key1, key2, ")
    assert _load_google_keys() == ["key1", "key2"]

    # 3. .envgoogle exists
    envgoogle = tmp_path / ".envgoogle"
    envgoogle.write_text("GOOGLE_API_KEYS=file-key1, file-key2")
    assert _load_google_keys() == ["file-key1", "file-key2"]

import unittest
from unittest.mock import patch, mock_open, MagicMock
import os
import sys

# Mock modules to avoid heavy imports or missing dependencies
sys.modules["openai"] = MagicMock()
sys.modules["common.token_pool"] = MagicMock()
sys.modules["httpx"] = MagicMock()

from summarize import _load_google_keys

class TestSummarizeKeys(unittest.TestCase):
    @patch("os.path.exists")
    @patch("builtins.open")
    @patch.dict(os.environ, clear=True)
    def test_load_google_keys_from_envgoogle(self, mock_open_func, mock_exists):
        """Test loading from .envgoogle file."""
        mock_exists.return_value = True
        mock_open_func.return_value = mock_open(read_data="GOOGLE_API_KEYS=key1, key2 ,key3\nOTHER_KEY=val").return_value

        keys = _load_google_keys()
        self.assertEqual(keys, ["key1", "key2", "key3"])
        mock_exists.assert_called_once_with(".envgoogle")
        mock_open_func.assert_called_once_with(".envgoogle", "r", encoding="utf-8")

    @patch("os.path.exists")
    @patch.dict(os.environ, {"GOOGLE_API_KEYS": "envkey1, envkey2  , envkey3"}, clear=True)
    def test_load_google_keys_from_env_fallback(self, mock_exists):
        """Test fallback to os.environ when .envgoogle doesn't exist."""
        mock_exists.return_value = False

        keys = _load_google_keys()
        self.assertEqual(keys, ["envkey1", "envkey2", "envkey3"])

    @patch("os.path.exists")
    @patch("builtins.open")
    @patch.dict(os.environ, {"GOOGLE_API_KEYS": "envkey1, envkey2"}, clear=True)
    def test_load_google_keys_invalid_envgoogle(self, mock_open_func, mock_exists):
        """Test fallback to os.environ when .envgoogle is invalid/doesn't contain key."""
        mock_exists.return_value = True
        mock_open_func.return_value = mock_open(read_data="INVALID_FORMAT").return_value

        keys = _load_google_keys()
        self.assertEqual(keys, ["envkey1", "envkey2"])

    @patch("os.path.exists")
    @patch("builtins.open")
    @patch("summarize.logger.warning")
    @patch.dict(os.environ, {"GOOGLE_API_KEYS": "envkey1, envkey2"}, clear=True)
    def test_load_google_keys_exception_envgoogle(self, mock_logger, mock_open_func, mock_exists):
        """Test fallback to os.environ when reading .envgoogle raises an exception."""
        mock_exists.return_value = True
        mock_open_func.side_effect = PermissionError("Permission denied")

        keys = _load_google_keys()
        self.assertEqual(keys, ["envkey1", "envkey2"])
        mock_logger.assert_called_once()
        self.assertIn("Error loading .envgoogle", mock_logger.call_args[0][0])

    @patch("os.path.exists")
    @patch.dict(os.environ, clear=True)
    def test_load_google_keys_empty(self, mock_exists):
        """Test when no keys are found anywhere."""
        mock_exists.return_value = False

        keys = _load_google_keys()
        self.assertEqual(keys, [])

    @patch("os.path.exists")
    @patch("builtins.open")
    @patch.dict(os.environ, clear=True)
    def test_load_google_keys_empty_elements(self, mock_open_func, mock_exists):
        """Test empty elements are ignored when splitting."""
        mock_exists.return_value = True
        mock_open_func.return_value = mock_open(read_data="GOOGLE_API_KEYS=key1,,key2\n").return_value

        keys = _load_google_keys()
        self.assertEqual(keys, ["key1", "key2"])

if __name__ == "__main__":
    unittest.main()

import unittest
from unittest.mock import patch, mock_open, MagicMock
import os
import sys

# Mock modules to avoid heavy imports or missing dependencies
sys.modules["openai"] = MagicMock()
sys.modules["common.token_pool"] = MagicMock()
sys.modules["httpx"] = MagicMock()

from summarize import _load_google_keys

class TestSummarizeKeys(unittest.TestCase):
    @patch("os.path.exists")
    @patch("builtins.open")
    @patch.dict(os.environ, clear=True)
    def test_load_google_keys_from_envgoogle(self, mock_open_func, mock_exists):
        """Test loading from .envgoogle file."""
        def mock_open_side_effect(filename, *args, **kwargs):
            if filename == ".envgoogle":
                return mock_open(read_data="GOOGLE_API_KEYS=key1, key2 ,key3\nOTHER_KEY=val").return_value
            elif filename == "google_keys.txt":
                raise FileNotFoundError()
            return mock_open().return_value

        mock_exists.return_value = True
        mock_open_func.side_effect = mock_open_side_effect

        keys = _load_google_keys()
        self.assertEqual(keys, ["key1", "key2", "key3"])
        mock_exists.assert_called_once_with(".envgoogle")

    @patch("os.path.exists")
    @patch("builtins.open")
    @patch.dict(os.environ, {"GOOGLE_API_KEYS": "envkey1, envkey2  , envkey3"}, clear=True)
    def test_load_google_keys_from_env_fallback(self, mock_open_func, mock_exists):
        """Test fallback to os.environ when .envgoogle doesn't exist."""
        def mock_open_side_effect(filename, *args, **kwargs):
            raise FileNotFoundError()

        mock_exists.return_value = False
        mock_open_func.side_effect = mock_open_side_effect

        keys = _load_google_keys()
        self.assertEqual(keys, ["envkey1", "envkey2", "envkey3"])

    @patch("os.path.exists")
    @patch("builtins.open")
    @patch.dict(os.environ, {"GOOGLE_API_KEYS": "envkey1, envkey2"}, clear=True)
    def test_load_google_keys_invalid_envgoogle(self, mock_open_func, mock_exists):
        """Test fallback to os.environ when .envgoogle is invalid/doesn't contain key."""
        def mock_open_side_effect(filename, *args, **kwargs):
            if filename == ".envgoogle":
                return mock_open(read_data="INVALID_FORMAT").return_value
            elif filename == "google_keys.txt":
                raise FileNotFoundError()
            return mock_open().return_value

        mock_exists.return_value = True
        mock_open_func.side_effect = mock_open_side_effect

        keys = _load_google_keys()
        self.assertEqual(keys, ["envkey1", "envkey2"])

    @patch("os.path.exists")
    @patch("builtins.open")
    @patch("summarize.logger.warning")
    @patch.dict(os.environ, {"GOOGLE_API_KEYS": "envkey1, envkey2"}, clear=True)
    def test_load_google_keys_exception_envgoogle(self, mock_logger, mock_open_func, mock_exists):
        """Test fallback to os.environ when reading .envgoogle raises an exception."""
        def mock_open_side_effect(filename, *args, **kwargs):
            if filename == ".envgoogle":
                raise PermissionError("Permission denied")
            elif filename == "google_keys.txt":
                raise FileNotFoundError()
            return mock_open().return_value

        mock_exists.return_value = True
        mock_open_func.side_effect = mock_open_side_effect

        keys = _load_google_keys()
        self.assertEqual(keys, ["envkey1", "envkey2"])
        mock_logger.assert_called_once()
        self.assertIn("Error loading .envgoogle", mock_logger.call_args[0][0])

    @patch("os.path.exists")
    @patch("builtins.open")
    @patch.dict(os.environ, clear=True)
    def test_load_google_keys_empty(self, mock_open_func, mock_exists):
        """Test when no keys are found anywhere."""
        def mock_open_side_effect(filename, *args, **kwargs):
            raise FileNotFoundError()

        mock_exists.return_value = False
        mock_open_func.side_effect = mock_open_side_effect

        keys = _load_google_keys()
        self.assertEqual(keys, [])

    @patch("os.path.exists")
    @patch("builtins.open")
    @patch.dict(os.environ, clear=True)
    def test_load_google_keys_empty_elements(self, mock_open_func, mock_exists):
        """Test empty elements are ignored when splitting."""
        def mock_open_side_effect(filename, *args, **kwargs):
            if filename == ".envgoogle":
                return mock_open(read_data="GOOGLE_API_KEYS=key1,,key2\n").return_value
            elif filename == "google_keys.txt":
                raise FileNotFoundError()
            return mock_open().return_value

        mock_exists.return_value = True
        mock_open_func.side_effect = mock_open_side_effect

        keys = _load_google_keys()
        self.assertEqual(keys, ["key1", "key2"])

if __name__ == "__main__":
    unittest.main()
