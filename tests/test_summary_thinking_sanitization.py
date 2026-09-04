# -*- coding: utf-8 -*-
"""
Tests for Summarization Thinking Sanitization, Model Cascades, and Telegraph AST Limits (R2).
Validates:
1. Robust stripping of all <think>, <reasoning>, <thought>, <reflection> tags (raw and HTML encoded, unclosed, multi-line, preambles).
2. Model cascade configuration validity, model preference routing, token limits, and 401/403/413/429 error handling.
3. Telegraph AST payload size limits (<= 55,000 bytes) and CONTENT_TOO_BIG auto-reduction.
"""

import json
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from common.text_utils import strip_thinking_tags, clean_ai_thinking
from summarize import (
    summarize_text_with_hf,
    _telegraph_create_page_sync,
    _summarize_inner,
)


# ============================================================================
# 1. Thinking / Reasoning Tag Sanitization Tests
# ============================================================================

class TestCleanAiThinkingAndTagStripping:
    """Validates stripping of all internal reasoning / thinking tokens."""

    @pytest.mark.parametrize("input_text,expected", [
        (
            "<think>Thinking about what to say...</think>\nЭто краткое содержание треда.",
            "Это краткое содержание треда."
        ),
        (
            "<reasoning>Step 1: Parse the user prompt\nStep 2: Generate response</reasoning>\nИтоговый результат анализа.",
            "Итоговый результат анализа."
        ),
        (
            "<thought>My private thoughts as an LLM</thought>\nОтвет без лишних мыслей.",
            "Ответ без лишних мыслей."
        ),
        (
            "<reflection>Reflecting on the tone</reflection>\nТоксичный двачерский вердикт.",
            "Токсичный двачерский вердикт."
        ),
    ])
    def test_strip_closed_thinking_tags(self, input_text, expected):
        """Closed reasoning/thinking tags in various standard formats are stripped."""
        assert strip_thinking_tags(input_text) == expected
        assert clean_ai_thinking(input_text) == expected

    @pytest.mark.parametrize("input_text,expected", [
        (
            "&lt;think&gt;HTML encoded think block&lt;/think&gt;\nЧистый текст саммари.",
            "Чистый текст саммари."
        ),
        (
            "&lt;reasoning&gt;Encoded reasoning block&lt;/reasoning&gt;\nЧистый ответ.",
            "Чистый ответ."
        ),
        (
            "&lt;thought&gt;Encoded thought&lt;/thought&gt;\nВердикт.",
            "Вердикт."
        ),
        (
            "&lt;reflection&gt;Encoded reflection&lt;/reflection&gt;\nГотово.",
            "Готово."
        ),
    ])
    def test_strip_html_encoded_thinking_tags(self, input_text, expected):
        """HTML entity escaped reasoning tags (&lt;think&gt;...&lt;/think&gt;) are stripped."""
        assert strip_thinking_tags(input_text) == expected
        assert clean_ai_thinking(input_text) == expected

    def test_strip_unclosed_thinking_at_start(self):
        """Unclosed opening thinking tag strips everything after it."""
        unclosed_raw = "<think>I am thinking endlessly and forgot to close the tag..."
        assert strip_thinking_tags(unclosed_raw) == ""

        unclosed_encoded = "&lt;reasoning&gt;Unclosed HTML encoded reasoning block..."
        assert strip_thinking_tags(unclosed_encoded) == ""

    def test_strip_multiline_thoughts_with_preamble(self):
        """Multi-line reasoning blocks starting with conversational preambles are stripped."""
        text_with_preamble = (
            "Thinking Process:\n"
            "1. Read the posts\n"
            "2. Identify key drama\n"
            "3. Format in 2ch slang\n\n"
            "Главная тема треда: Анон поясняет за жизнь в ДС-2."
        )
        assert strip_thinking_tags(text_with_preamble) == "Главная тема треда: Анон поясняет за жизнь в ДС-2."

        text_assistant = "Assistant: Вот саммари треда."
        assert strip_thinking_tags(text_assistant) == "Вот саммари треда."

        text_heres = "Here's a thinking process: Саммари готово."
        assert strip_thinking_tags(text_heres) == "Саммари готово."

    def test_clean_text_untouched(self):
        """Clean Russian and English text without reasoning tags remains 100% untouched."""
        clean_ru = "🎵 <b>Трек:</b> Miyagi — Minor\n📝 <b>Текст:</b> Салют анон.\n🔥 <b>Вердикт:</b> Кал."
        assert strip_thinking_tags(clean_ru) == clean_ru

        clean_en = "Discussion about Python 3.13 features and async performance."
        assert strip_thinking_tags(clean_en) == clean_en

    def test_multi_segment_thinking(self):
        """Multiple thinking blocks interspersed in text are all stripped."""
        multi_segment = (
            "<think>Analyzing part 1</think>"
            "Первая часть саммари.\n"
            "<think>Analyzing part 2</think>"
            "Вторая часть саммари."
        )
        cleaned = strip_thinking_tags(multi_segment)
        assert "<think>" not in cleaned
        assert "</think>" not in cleaned
        assert "Первая часть саммари." in cleaned
        assert "Вторая часть саммари." in cleaned

    def test_none_and_empty_inputs(self):
        """None, empty string, or non-string inputs return empty string safely."""
        assert strip_thinking_tags("") == ""
        assert strip_thinking_tags(None) == ""
        assert clean_ai_thinking("") == ""
        assert clean_ai_thinking(None) == ""


# ============================================================================
# 2. Model Cascade Validity & Error Recovery Tests
# ============================================================================

class TestModelCascadeValidity:
    """Validates model cascades, routing preferences, token limits, and error handling."""

    VALID_MODELS = {
        "gemini-3.5-flash-lite",
        "gemini-3.1-flash-lite",
        "gemini-3.6-flash",
        "gemini-3.7-flash",
        "qwen/qwen3.8-27b",
        "qwen/qwen3.6-27b",
    }

    @pytest.mark.asyncio
    @patch("summarize.AsyncOpenAI")
    @patch("summarize.google_pool.get_all_active_tokens", return_value=["google-key-01"])
    @patch("summarize.groq_pool.get_all_active_tokens", return_value=["groq-key-01"])
    async def test_all_cascade_models_are_valid(self, mock_groq_pool, mock_google_pool, mock_openai_cls):
        """Every model name queried across all cascade preferences is in the valid approved set."""
        mock_client = AsyncMock()
        mock_openai_cls.return_value = mock_client
        mock_completion = MagicMock()
        mock_completion.choices = [MagicMock(message=MagicMock(content="Успешный ответ"))]
        mock_client.chat.completions.create.return_value = mock_completion

        for pref in ["persona", "fast", "gemini", "qwen", "llama", None]:
            await summarize_text_with_hf("Prompt", "Text", model_preference=pref)
            call_kwargs = mock_client.chat.completions.create.call_args[1]
            model_used = call_kwargs["model"]
            assert model_used in self.VALID_MODELS, f"Invalid model '{model_used}' used for preference '{pref}'"

    @pytest.mark.asyncio
    @patch("summarize.AsyncOpenAI")
    @patch("summarize.groq_pool.get_all_active_tokens", return_value=["groq-key-01"])
    @patch("summarize.google_pool.get_all_active_tokens", return_value=["google-key-01"])
    async def test_qwen_preference_queries_qwen_first(self, mock_google, mock_groq, mock_openai_cls):
        """model_preference='qwen' routes to qwen/qwen3.8-27b first."""
        mock_client = AsyncMock()
        mock_openai_cls.return_value = mock_client
        mock_completion = MagicMock()
        mock_completion.choices = [MagicMock(message=MagicMock(content="Qwen Response"))]
        mock_client.chat.completions.create.return_value = mock_completion

        res = await summarize_text_with_hf("Prompt", "Text", model_preference="qwen")

        assert res == "Qwen Response"
        call_model = mock_client.chat.completions.create.call_args[1]["model"]
        assert call_model == "qwen/qwen3.8-27b"

    @pytest.mark.asyncio
    @patch("summarize.AsyncOpenAI")
    @patch("summarize.groq_pool.get_all_active_tokens", return_value=["groq-key-01"])
    @patch("summarize.google_pool.get_all_active_tokens", return_value=["google-key-01"])
    async def test_llama_preference_routes_to_groq_first(self, mock_google, mock_groq, mock_openai_cls):
        """model_preference='llama' routes to qwen/qwen3.8-27b on Groq first."""
        mock_client = AsyncMock()
        mock_openai_cls.return_value = mock_client
        mock_completion = MagicMock()
        mock_completion.choices = [MagicMock(message=MagicMock(content="Groq Response"))]
        mock_client.chat.completions.create.return_value = mock_completion

        res = await summarize_text_with_hf("Prompt", "Text", model_preference="llama")

        assert res == "Groq Response"
        call_model = mock_client.chat.completions.create.call_args[1]["model"]
        assert call_model == "qwen/qwen3.8-27b"

    @pytest.mark.asyncio
    @patch("summarize.AsyncOpenAI")
    @patch("summarize.google_pool.get_all_active_tokens", return_value=["google-key-01"])
    async def test_gemini_token_parameters(self, mock_google, mock_openai_cls):
        """Gemini queries omit max_tokens (set to None) to avoid artificial truncation."""
        mock_client = AsyncMock()
        mock_openai_cls.return_value = mock_client
        mock_completion = MagicMock()
        mock_completion.choices = [MagicMock(message=MagicMock(content="Gemini Response"))]
        mock_client.chat.completions.create.return_value = mock_completion

        await summarize_text_with_hf("Prompt", "Text", model_preference="gemini")

        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert "max_tokens" not in call_kwargs or call_kwargs.get("max_tokens") is None

    @pytest.mark.asyncio
    @patch("summarize.AsyncOpenAI")
    @patch("summarize.groq_pool.get_all_active_tokens", return_value=["groq-key-01"])
    @patch("summarize.google_pool.get_all_active_tokens", return_value=[])
    async def test_groq_token_parameters_capped(self, mock_google, mock_groq, mock_openai_cls):
        """Groq queries enforce max_tokens <= 6000."""
        mock_client = AsyncMock()
        mock_openai_cls.return_value = mock_client
        mock_completion = MagicMock()
        mock_completion.choices = [MagicMock(message=MagicMock(content="Groq Response"))]
        mock_client.chat.completions.create.return_value = mock_completion

        await summarize_text_with_hf("Prompt", "Text", model_preference="qwen")

        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert "max_tokens" in call_kwargs
        assert call_kwargs["max_tokens"] <= 6000

    @pytest.mark.asyncio
    @patch("summarize.asyncio.sleep", new_callable=AsyncMock)
    @patch("summarize.AsyncOpenAI")
    @patch("summarize.groq_pool.remove_token")
    @patch("summarize.groq_pool.get_all_active_tokens", return_value=["bad-token", "good-token"])
    @patch("summarize.google_pool.get_all_active_tokens", return_value=[])
    async def test_error_401_removes_unauthorized_token(
        self, mock_google, mock_groq, mock_remove_token, mock_openai_cls, mock_sleep
    ):
        """401 error removes unauthorized token from token pool and retries with next token."""
        mock_client_bad = AsyncMock()
        mock_client_bad.chat.completions.create.side_effect = Exception("401 Unauthorized: Invalid API Key")

        mock_client_good = AsyncMock()
        mock_completion = MagicMock()
        mock_completion.choices = [MagicMock(message=MagicMock(content="Recovered Response"))]
        mock_client_good.chat.completions.create.return_value = mock_completion

        mock_openai_cls.side_effect = [mock_client_bad, mock_client_good]

        res = await summarize_text_with_hf("Prompt", "Text", model_preference="qwen")

        assert res == "Recovered Response"
        mock_remove_token.assert_called_once_with("bad-token")

    @pytest.mark.asyncio
    @patch("summarize.asyncio.sleep", new_callable=AsyncMock)
    @patch("summarize.AsyncOpenAI")
    @patch("summarize.google_pool.ban_token")
    @patch("summarize.google_pool.get_all_active_tokens", return_value=["banned-key", "good-key"])
    async def test_error_403_bans_key_and_tries_next_key(
        self, mock_google, mock_ban_token, mock_openai_cls, mock_sleep
    ):
        """403 error bans key from pool and immediately attempts the next key."""
        mock_client_banned = AsyncMock()
        mock_client_banned.chat.completions.create.side_effect = Exception("403 Forbidden: Project Suspended")

        mock_client_good = AsyncMock()
        mock_completion = MagicMock()
        mock_completion.choices = [MagicMock(message=MagicMock(content="Success after 403"))]
        mock_client_good.chat.completions.create.return_value = mock_completion

        mock_openai_cls.side_effect = [mock_client_banned, mock_client_good]

        res = await summarize_text_with_hf("Prompt", "Text", model_preference="gemini")

        assert res == "Success after 403"
        mock_ban_token.assert_called_once_with("banned-key")

    @pytest.mark.asyncio
    @patch("summarize.asyncio.sleep", new_callable=AsyncMock)
    @patch("summarize.AsyncOpenAI")
    @patch("summarize.google_pool.get_all_active_tokens", return_value=["google-key"])
    async def test_error_413_shrinks_input_and_retries(self, mock_google, mock_openai_cls, mock_sleep):
        """413 Request Entity Too Large shrinks input by 40% and retries."""
        mock_client = AsyncMock()
        mock_completion = MagicMock()
        mock_completion.choices = [MagicMock(message=MagicMock(content="Shrunk response"))]

        mock_client.chat.completions.create.side_effect = [
            Exception("413 Request Entity Too Large"),
            mock_completion
        ]
        mock_openai_cls.return_value = mock_client

        large_text = "A" * 10000
        res = await summarize_text_with_hf("Prompt", large_text, model_preference="gemini")

        assert res == "Shrunk response"
        assert mock_client.chat.completions.create.call_count == 2
        # Verify second call passed shorter content
        second_call_messages = mock_client.chat.completions.create.call_args_list[1][1]["messages"]
        assert len(second_call_messages[1]["content"]) == 6000  # 60% of 10000


# ============================================================================
# 3. Telegraph AST Payload Limits & Resilience Tests
# ============================================================================

class TestTelegraphASTPayloadLimitsAndResilience:
    """Validates Telegraph AST node conversion, 55,000 byte limit, and CONTENT_TOO_BIG recovery."""

    @patch("requests.post")
    def test_telegraph_payload_within_55k_limit(self, mock_post):
        """Large AST nodes exceeding 55,000 bytes are pre-shrunk before API dispatch."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"ok": True, "result": {"url": "https://telegra.ph/page-test-01"}}
        mock_post.return_value = mock_resp

        # Create massive node list (> 100,000 bytes)
        massive_nodes = [{"tag": "p", "children": [f"Paragraph text chunk {i} " * 50]} for i in range(100)]
        initial_size = len(json.dumps(massive_nodes, ensure_ascii=False).encode('utf-8'))
        assert initial_size > 55000

        url = _telegraph_create_page_sync(token="test-token", title="Big Summary", content_nodes=massive_nodes)

        assert url == "https://telegra.ph/page-test-01"
        mock_post.assert_called_once()
        sent_payload = mock_post.call_args[1]["data"]
        sent_content = sent_payload["content"]
        sent_size = len(sent_content.encode('utf-8'))

        assert sent_size <= 55000
        assert "Текст сокращен из-за лимита Telegraph" in sent_content

    @patch("requests.post")
    @patch("time.sleep", return_value=None)
    def test_telegraph_content_too_big_auto_reduction_retry(self, mock_sleep, mock_post):
        """When Telegraph API returns CONTENT_TOO_BIG error, nodes are shrunk by 40% and retried."""
        mock_resp_err = MagicMock()
        mock_resp_err.status_code = 200
        mock_resp_err.json.return_value = {"ok": False, "error": "CONTENT_TOO_BIG"}

        mock_resp_ok = MagicMock()
        mock_resp_ok.status_code = 200
        mock_resp_ok.json.return_value = {"ok": True, "result": {"url": "https://telegra.ph/page-recovered"}}

        mock_post.side_effect = [mock_resp_err, mock_resp_ok]

        nodes = [{"tag": "p", "children": [f"Node paragraph {i}"]} for i in range(20)]
        url = _telegraph_create_page_sync(token="test-token", title="Summary Title", content_nodes=nodes)

        assert url == "https://telegra.ph/page-recovered"
        assert mock_post.call_count == 2
        # Verify second call had reduced content
        second_call_content = mock_post.call_args_list[1][1]["data"]["content"]
        assert "Текст сокращен из-за лимита Telegraph" in second_call_content

    @patch("requests.post")
    def test_telegraph_ast_schema_conformance(self, mock_post):
        """Telegraph AST node schema with standard tags is valid JSON with ensure_ascii=False."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"ok": True, "result": {"url": "https://telegra.ph/page-schema"}}
        mock_post.return_value = mock_resp

        valid_nodes = [
            {"tag": "h3", "children": ["Заголовок саммари"]},
            {"tag": "p", "children": [{"tag": "b", "children": ["Жирный текст: "]}, "Обычный текст саммари."]},
            {"tag": "blockquote", "children": ["Цитата из треда /b/."]},
        ]

        url = _telegraph_create_page_sync(token="test-token", title="Schema Page", content_nodes=valid_nodes)

        assert url == "https://telegra.ph/page-schema"
        sent_content = mock_post.call_args[1]["data"]["content"]
        parsed = json.loads(sent_content)
        assert len(parsed) == 3
        assert parsed[0]["tag"] == "h3"
        assert parsed[1]["children"][0]["tag"] == "b"
