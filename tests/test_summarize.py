import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from summarize import summarize_text_with_hf

# ВАЖНО про обвязку мока AsyncOpenAI.
# _summarize_inner создаёт клиент выражением `client = AsyncOpenAI(...)` и НЕ входит
# в `async with` (иначе __aexit__ закрыл бы общий httpx-клиент из
# get_shared_http_client, и все последующие запросы шли бы по закрытому соединению).
# Поэтому клиент, который видит код, — это ровно `AsyncOpenAI.return_value`.
# Прежняя обвязка вешала мок на `return_value.__aenter__.return_value`, до которого
# код никогда не доходил: `await` по обычному MagicMock падал с
# "object MagicMock can't be used in 'await' expression", исключение съедал
# `except Exception` каскада, и ЛЮБОЙ тест получал финальное "Нейронка сдохла".
# Тесты на успех падали, а тесты на провал зеленели по неверной причине —
# ни одна ветка провайдера (401/413/429) ни разу не исполнялась.


@pytest.fixture(autouse=True)
def reset_summarize_module_state():
    """
    Сбрасывает глобальное состояние summarize между тестами.

    _key_cooldowns живёт на уровне модуля и держит ключ в бане 90 секунд: тест на
    429 иначе оставляет google-key1 в куладауне для всех последующих тестов (и для
    других файлов в общем прогоне), и они молча пропускают модель вместо вызова.
    _SHARED_HTTP_CLIENT после патча httpx.AsyncClient остаётся MagicMock'ом и
    утекает в модульную переменную за границы теста.
    """
    import summarize
    summarize._key_cooldowns.clear()
    summarize._SHARED_HTTP_CLIENT = None
    yield
    summarize._key_cooldowns.clear()
    summarize._SHARED_HTTP_CLIENT = None


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
    mock_async_openai.return_value = mock_client  # код не использует async with, см. комментарий сверху

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
    mock_async_openai.return_value = mock_client  # код не использует async with, см. комментарий сверху
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
    mock_async_openai.return_value = mock_client  # код не использует async with, см. комментарий сверху
    mock_client.chat.completions.create.side_effect = Exception("401 Unauthorized")

    result = await summarize_text_with_hf("Prompt", "Text", model_preference="llama")

    assert result == "Нейронка сдохла. Не удалось сгенерировать саммари."
    # Ровно один раз: 401 на моделях gemini дальше по каскаду не должен выбрасывать
    # ключи из пула groq (ветка summarize.py:239 стоит под provider == "groq").
    mock_remove_token.assert_called_once_with("groq-key")

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
    mock_async_openai.return_value = mock_client  # код не использует async with, см. комментарий сверху

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
    # call_count == 2 сам по себе прошёл бы и при повторе той же модели, а тест
    # называется skips_model — сверяем, что второй заход ушёл на следующую модель.
    calls = mock_client.chat.completions.create.call_args_list
    assert calls[0].kwargs["model"] != calls[1].kwargs["model"]
    # 413 обрезает дамп на 40% с сохранением хвоста (summarize.py:246-248), и
    # укороченный текст реально уезжает в следующий запрос.
    sent_text = calls[1].kwargs["messages"][1]["content"]
    assert sent_text != "Text" and "Text".endswith(sent_text)

@pytest.mark.asyncio
@patch("summarize.httpx.AsyncHTTPTransport")
@patch("summarize.httpx.AsyncClient")
@patch("summarize.AsyncOpenAI")
@patch("summarize._load_google_keys", return_value=["google-key1", "google-key2"])
async def test_summarize_429_switches_key(
    mock_load_google_keys, mock_async_openai, mock_httpx_client, mock_httpx_transport
):
    mock_client = AsyncMock()
    mock_async_openai.return_value = mock_client  # код не использует async with, см. комментарий сверху

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
    # Главное в этом тесте — что ключ СМЕНИЛСЯ. Два вызова были бы и при повторе
    # google-key1, поэтому смотрим api_key, с которым конструировали клиента.
    used_keys = [c.kwargs["api_key"] for c in mock_async_openai.call_args_list]
    assert used_keys == ["google-key1", "google-key2"]
    # Пойманный на 429 ключ уходит в куладаун, иначе остальные модели каскада
    # продолжали бы долбить уже забаненный ключ.
    import summarize
    assert ("gemini", "google-key1") in summarize._key_cooldowns
    assert ("gemini", "google-key2") not in summarize._key_cooldowns

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
    mock_async_openai.return_value = mock_client  # код не использует async with, см. комментарий сверху

    mock_completion = MagicMock()
    mock_completion.choices = [MagicMock()]
    mock_completion.choices[0].message.content = ""
    mock_client.chat.completions.create.return_value = mock_completion

    result = await summarize_text_with_hf("Prompt", "Text", model_preference="llama")

    # It should loop through strategies/models and eventually return failure message
    assert result == "Нейронка сдохла. Не удалось сгенерировать саммари."


def test_load_google_keys(tmp_path, monkeypatch):
    from summarize import _load_google_keys

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


@pytest.fixture(autouse=True)
def reset_telegraph_token_cache():
    import summarize
    original_cache = summarize._telegraph_token_cache
    summarize._telegraph_token_cache = None
    yield
    summarize._telegraph_token_cache = original_cache

def test_get_telegraph_token_cached(monkeypatch):
    import summarize
    summarize._telegraph_token_cache = "cached_token"
    token = summarize.get_telegraph_token()
    assert token == "cached_token"

def test_get_telegraph_token_env_var(monkeypatch):
    import summarize
    monkeypatch.setenv("TELEGRAPH_TOKEN", "env_token")
    token = summarize.get_telegraph_token()
    assert token == "env_token"
    assert summarize._telegraph_token_cache == "env_token"

def test_get_telegraph_token_file(monkeypatch, tmp_path):
    import summarize

    token_file = tmp_path / "telegraph_token.txt"
    token_file.write_text("file_token")

    monkeypatch.setattr(summarize, "TELEGRAPH_TOKEN_FILE", str(token_file))
    monkeypatch.delenv("TELEGRAPH_TOKEN", raising=False)

    token = summarize.get_telegraph_token()
    assert token == "file_token"
    assert summarize._telegraph_token_cache == "file_token"

def test_get_telegraph_token_generation_success(monkeypatch, tmp_path):
    import summarize
    from unittest.mock import MagicMock

    mock_logger_error = MagicMock()
    monkeypatch.setattr("summarize.logger.error", mock_logger_error)

    mock_makedirs = MagicMock()
    monkeypatch.setattr("summarize.os.makedirs", mock_makedirs)

    token_file = tmp_path / "telegraph_token.txt"
    monkeypatch.setattr(summarize, "TELEGRAPH_TOKEN_FILE", str(token_file))
    monkeypatch.delenv("TELEGRAPH_TOKEN", raising=False)

    # Токен выпрашивается у api.telegra.ph напрямую через requests
    # (_telegraph_create_account_sync); библиотеки html_telegraph_poster в коде нет
    # вообще — она не импортируется ни в одном файле проекта. Прежний мок подменял
    # html_telegraph_poster.TelegraphPoster, до которого управление не доходило, и
    # тест уходил в СЕТЬ: каждый прогон реально создавал аккаунт Telegraph и
    # сравнивал живой access_token со строкой "generated_token".
    mock_create_account = MagicMock(return_value="generated_token")
    monkeypatch.setattr(summarize, "_telegraph_create_account_sync", mock_create_account)

    token = summarize.get_telegraph_token()

    assert token == "generated_token"
    assert summarize._telegraph_token_cache == "generated_token"
    mock_create_account.assert_called_once_with()
    mock_makedirs.assert_called_once_with("data", exist_ok=True)
    assert token_file.read_text(encoding="utf-8") == "generated_token"
    mock_logger_error.assert_not_called()

def test_get_telegraph_token_generation_failure(monkeypatch, tmp_path):
    import summarize
    from unittest.mock import MagicMock

    mock_logger_error = MagicMock()
    monkeypatch.setattr("summarize.logger.error", mock_logger_error)

    token_file = tmp_path / "telegraph_token.txt"
    monkeypatch.setattr(summarize, "TELEGRAPH_TOKEN_FILE", str(token_file))
    monkeypatch.delenv("TELEGRAPH_TOKEN", raising=False)

    # Тот же сдвиг реализации, что и в тесте выше: падать должен именно
    # requests-вызов _telegraph_create_account_sync, иначе обработчик
    # summarize.py:351-352 не достигается и тест бьётся в живой Telegraph.
    mock_create_account = MagicMock(side_effect=Exception("Telegraph API error"))
    monkeypatch.setattr(summarize, "_telegraph_create_account_sync", mock_create_account)

    token = summarize.get_telegraph_token()

    assert token == ""
    assert summarize._telegraph_token_cache is None
    mock_logger_error.assert_called_once()
    assert "Failed to generate Telegraph token" in mock_logger_error.call_args[0][0]
