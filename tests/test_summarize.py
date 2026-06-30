import pytest
from unittest.mock import patch, mock_open, MagicMock, AsyncMock
import os
import sys

# Ensure the parent directory is in the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from summarize import _load_google_keys, summarize_text_with_hf
from common.token_pool import groq_pool

@pytest.fixture
def mock_env():
    with patch.dict(os.environ, {}, clear=True):
        yield

def test_load_google_keys_envgoogle(mock_env):
    mock_file_content = "GOOGLE_API_KEYS=key1, key2 ,key3\nOTHER_VAR=value"
    with patch("os.path.exists", return_value=True), \
         patch("builtins.open", mock_open(read_data=mock_file_content)):
        keys = _load_google_keys()
        assert keys == ["key1", "key2", "key3"]

def test_load_google_keys_env_fallback(mock_env):
    with patch("os.path.exists", return_value=False), \
         patch.dict(os.environ, {"GOOGLE_API_KEYS": "env_key1, env_key2"}):
        keys = _load_google_keys()
        assert keys == ["env_key1", "env_key2"]

def test_load_google_keys_empty(mock_env):
    with patch("os.path.exists", return_value=False):
        keys = _load_google_keys()
        assert keys == []

@pytest.mark.asyncio
async def test_summarize_success_gemini():
    with patch("summarize._load_google_keys", return_value=["test_key"]), \
         patch("summarize.AsyncOpenAI") as MockOpenAI:

        mock_client = AsyncMock()
        MockOpenAI.return_value.__aenter__.return_value = mock_client
        mock_completion = MagicMock()
        mock_completion.choices = [MagicMock()]
        mock_completion.choices[0].message.content = "This is a summary."
        mock_client.chat.completions.create.return_value = mock_completion

        result = await summarize_text_with_hf("Prompt", "Text", model_preference="gemini")
        assert result == "This is a summary."

@pytest.mark.asyncio
async def test_summarize_success_groq():
    with patch.object(groq_pool, "get_token", return_value="groq_key"), \
         patch("summarize.AsyncOpenAI") as MockOpenAI:

        mock_client = AsyncMock()
        MockOpenAI.return_value.__aenter__.return_value = mock_client
        mock_completion = MagicMock()
        mock_completion.choices = [MagicMock()]
        mock_completion.choices[0].message.content = "<think>Thoughts</think>This is a groq summary."
        mock_client.chat.completions.create.return_value = mock_completion

        result = await summarize_text_with_hf("Prompt", "Text", model_preference="llama")
        assert result == "This is a groq summary."

@pytest.mark.asyncio
async def test_summarize_no_keys():
    with patch("summarize._load_google_keys", return_value=[]):
        result = await summarize_text_with_hf("Prompt", "Text", model_preference="gemini")
        assert result == "Нейронка сдохла. Не удалось сгенерировать саммари."

@pytest.mark.asyncio
async def test_summarize_401_groq():
    with patch.object(groq_pool, "get_token", side_effect=["bad_key", None, None, None, None]), \
         patch.object(groq_pool, "remove_token") as mock_remove, \
         patch("summarize.AsyncOpenAI") as MockOpenAI:

        mock_client = AsyncMock()
        MockOpenAI.return_value.__aenter__.return_value = mock_client
        mock_client.chat.completions.create.side_effect = Exception("401 Unauthorized")

        result = await summarize_text_with_hf("Prompt", "Text", model_preference="qwen")

        assert result == "Нейронка сдохла. Не удалось сгенерировать саммари."
        mock_remove.assert_called_once_with("bad_key")

@pytest.mark.asyncio
async def test_summarize_413_skip_model():
    with patch("summarize._load_google_keys", return_value=["test_key"]), \
         patch("summarize.AsyncOpenAI") as MockOpenAI:

        mock_client = AsyncMock()
        MockOpenAI.return_value.__aenter__.return_value = mock_client

        # First model fails with 413, second succeeds
        mock_completion = MagicMock()
        mock_completion.choices = [MagicMock()]
        mock_completion.choices[0].message.content = "Summary from second model."
        mock_client.chat.completions.create.side_effect = [
            Exception("413 Request Too Large"),
            mock_completion
        ]

        result = await summarize_text_with_hf("Prompt", "Text", model_preference="gemini")
        assert result == "Summary from second model."

@pytest.mark.asyncio
async def test_summarize_429_switch_key():
    with patch("summarize._load_google_keys", return_value=["key1", "key2"]), \
         patch("summarize.AsyncOpenAI") as MockOpenAI:

        mock_client = AsyncMock()
        MockOpenAI.return_value.__aenter__.return_value = mock_client

        # First key fails with 429, second key succeeds
        mock_completion = MagicMock()
        mock_completion.choices = [MagicMock()]
        mock_completion.choices[0].message.content = "Summary with second key."
        mock_client.chat.completions.create.side_effect = [
            Exception("429 Too Many Requests"),  # For key1 direct
            Exception("429 Too Many Requests"),  # For key1 proxy (Wait, strategy loop is inside key loop)
            # Actually, the exception breaks the strategy loop and goes to next key or strategy?
            # Looking at the code:
            # if "429" in err_str: break (this breaks the strategy loop)
            # So it will move to the next api_key
            mock_completion
        ]

        result = await summarize_text_with_hf("Prompt", "Text", model_preference="gemini")
        assert result == "Summary with second key."
