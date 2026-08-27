# -*- coding: utf-8 -*-
"""
Adversarial Stress Test Suite for Thinking Sanitization & Telegraph AST Payload Limits.
Authored by Challenger 2.

Empirically tests:
1. Malformed and adversarial thinking tokens:
   - Deeply nested tags (<think><think>nested</think></think>, mixed tag nesting).
   - Unclosed tags at EOF and in the middle of text.
   - HTML entities (&lt;think&gt;, &lt;reasoning&gt;, etc.) with mixed casing.
   - Mixed casing (<THINK>, <tHiNk>, <REASONING>, etc.).
   - Conversational prefixes and preambles ("Here's a summary:", "Assistant:", etc.).
   - Attributes inside thinking tags (<think class="secret">...).

2. Telegraph AST payload stress:
   - Massive Cyrillic strings (100,000+ characters, 200,000+ UTF-8 bytes).
   - Deeply nested DOM nodes (20+ levels of formatting tags).
   - Verification that json.dumps(..., ensure_ascii=False) payload is strictly <= 55,000 bytes.
   - CONTENT_TOO_BIG API auto-reduction and multi-attempt recovery.
   - Asymmetric node distributions (massive first node, massive last node, 5000+ tiny nodes).
"""

import json
import pytest
from unittest.mock import MagicMock, patch

from common.text_utils import strip_thinking_tags, clean_ai_thinking
from summarize import (
    _text_to_telegraph_nodes,
    _telegraph_create_page_sync,
    _create_telegraph_page_blocking,
)


# ============================================================================
# 1. Adversarial Thinking Sanitization Stress Tests
# ============================================================================

class TestAdversarialThinkingSanitization:
    """Stress tests thinking/reasoning token eradication against adversarial edge cases."""

    @pytest.mark.parametrize("nested_input,expected_output", [
        (
            "<think><think>nested think</think></think>Clean text",
            "Clean text"
        ),
        (
            "<think><think><think><think>4-level deep think</think></think></think></think>Clean text",
            "Clean text"
        ),
        (
            "<think><reasoning><thought><reflection>mixed quad-nesting</reflection></thought></reasoning></think>Clean text",
            "Clean text"
        ),
        (
            "<reflection><thought><reasoning><think>reverse quad-nesting</think></reasoning></thought></reflection>Clean text",
            "Clean text"
        ),
    ])
    def test_deeply_nested_thinking_tags(self, nested_input, expected_output):
        """Clean nested tags without intermediate text are thoroughly stripped."""
        assert strip_thinking_tags(nested_input) == expected_output
        assert clean_ai_thinking(nested_input) == expected_output

    def test_nested_tags_interstitial_text_leakage(self):
        """
        Adversarial evaluation: Nested tags with interstitial text.
        Input: <think>pre <think>inner</think> post</think>Clean summary
        Note: The non-greedy regex matches <think>pre <think>inner</think>, leaving ' post</think>'.
        Orphaned tag cleanup strips '</think>', leaving 'postClean summary'.
        """
        input_text = "<think>pre <think>inner</think> post</think>Clean summary"
        result = strip_thinking_tags(input_text)
        assert "<think>" not in result
        assert "</think>" not in result
        assert "Clean summary" in result

    @pytest.mark.parametrize("unclosed_input,expected_output", [
        (
            "Clean summary header\n<think>Unclosed thinking reaching until EOF",
            "Clean summary header"
        ),
        (
            "Valid Russian text\n<reasoning>Не закрытый блок размышлений до конца строки",
            "Valid Russian text"
        ),
        (
            "Start content\n<thought>\nLine 1\nLine 2\nLine 3",
            "Start content"
        ),
        (
            "<reflection>Unclosed reflection right at string start",
            ""
        ),
        (
            "Header\n&lt;think&gt;HTML entity unclosed at EOF",
            "Header"
        ),
        (
            "Header\n&lt;reasoning&gt;HTML entity unclosed reasoning",
            "Header"
        ),
    ])
    def test_unclosed_thinking_tags_at_eof(self, unclosed_input, expected_output):
        """Unclosed thinking tags at end of string are truncated cleanly."""
        assert strip_thinking_tags(unclosed_input) == expected_output
        assert clean_ai_thinking(unclosed_input) == expected_output

    def test_unclosed_thinking_in_middle_of_text(self):
        """
        Unclosed thinking tag in the middle of text truncates from that tag to EOF,
        preventing internal AI thoughts from leaking into the user output.
        """
        input_text = "Paragraph 1: Clean.\n<reasoning>Leaked thought\nParagraph 2: Should not appear"
        res = strip_thinking_tags(input_text)
        assert res == "Paragraph 1: Clean."
        assert "Leaked thought" not in res
        assert "Paragraph 2" not in res

    @pytest.mark.parametrize("entity_input,expected_output", [
        (
            "&lt;think&gt;HTML encoded think&lt;/think&gt;Clean summary",
            "Clean summary"
        ),
        (
            "&lt;reasoning&gt;HTML reasoning&lt;/reasoning&gt;Clean summary",
            "Clean summary"
        ),
        (
            "&lt;thought&gt;HTML thought&lt;/thought&gt;Clean summary",
            "Clean summary"
        ),
        (
            "&lt;reflection&gt;HTML reflection&lt;/reflection&gt;Clean summary",
            "Clean summary"
        ),
        (
            "&lt;THINK&gt;Uppercase entity&lt;/THINK&gt;Clean summary",
            "Clean summary"
        ),
        (
            "&lt;rEaSoNiNg&gt;Mixed case entity&lt;/ReAsOnInG&gt;Clean summary",
            "Clean summary"
        ),
        (
            "&lt;think&gt;&lt;thought&gt;Nested entities&lt;/thought&gt;&lt;/think&gt;Clean summary",
            "Clean summary"
        ),
    ])
    def test_html_entity_thinking_tags(self, entity_input, expected_output):
        """HTML entity escaped thinking tags (&lt;...&gt;) in various casings are completely stripped."""
        assert strip_thinking_tags(entity_input) == expected_output
        assert clean_ai_thinking(entity_input) == expected_output

    @pytest.mark.parametrize("casing_input,expected_output", [
        (
            "<THINK>ALL CAPS THINK</THINK>Clean summary",
            "Clean summary"
        ),
        (
            "<REASONING>ALL CAPS REASONING</REASONING>Clean summary",
            "Clean summary"
        ),
        (
            "<THOUGHT>ALL CAPS THOUGHT</THOUGHT>Clean summary",
            "Clean summary"
        ),
        (
            "<REFLECTION>ALL CAPS REFLECTION</REFLECTION>Clean summary",
            "Clean summary"
        ),
        (
            "<tHiNk>mIxEd cAsE</ThInK>Clean summary",
            "Clean summary"
        ),
        (
            "<ReAsOnInG>mIxEd cAsE</rEaSoNiNg>Clean summary",
            "Clean summary"
        ),
    ])
    def test_mixed_casing_thinking_tags(self, casing_input, expected_output):
        """Thinking tags with any casing combinations are stripped."""
        assert strip_thinking_tags(casing_input) == expected_output
        assert clean_ai_thinking(casing_input) == expected_output

    @pytest.mark.parametrize("attr_input,expected_output", [
        (
            '<think class="ai-thought" data-id="123" score="0.99">Think with attributes</think>Clean summary',
            "Clean summary"
        ),
        (
            '<reasoning type="internal" status="in-progress">Reasoning with attrs</reasoning>Clean summary',
            "Clean summary"
        ),
        (
            '<thought\n  id="thought-1"\n  mode="verbose">Multiline attributes</thought>Clean summary',
            "Clean summary"
        ),
        (
            '&lt;think class="entity-attr"&gt;Entity with attrs&lt;/think&gt;Clean summary',
            "Clean summary"
        ),
    ])
    def test_thinking_tags_with_attributes(self, attr_input, expected_output):
        """Thinking tags containing diverse single-line and multi-line attributes are stripped."""
        assert strip_thinking_tags(attr_input) == expected_output
        assert clean_ai_thinking(attr_input) == expected_output

    @pytest.mark.parametrize("preamble_input,expected_output", [
        (
            "Assistant: Саммари готово.",
            "Саммари готово."
        ),
        (
            "Here is the reasoning: Саммари готово.",
            "Саммари готово."
        ),
        (
            "Here is a summary: Саммари готово.",
            "Саммари готово."
        ),
        (
            "Here's a thinking process: Саммари готово.",
            "Саммари готово."
        ),
        (
            "Thinking Process:\n1. Analyze thread\n2. Extract key drama\n\nИтоговое саммари треда.",
            "Итоговое саммари треда."
        ),
        (
            "Reasoning:\nStep 1: Read audio lyrics\nStep 2: Critique\n\n🎵 <b>Трек:</b> Кал.",
            "🎵 <b>Трек:</b> Кал."
        ),
    ])
    def test_conversational_preambles_and_prefixes(self, preamble_input, expected_output):
        """Conversational preambles and multi-line thinking headers are stripped."""
        assert strip_thinking_tags(preamble_input) == expected_output
        assert clean_ai_thinking(preamble_input) == expected_output

    def test_adversarial_interleaved_tags_and_whitespace(self):
        """Multiple sequential and interleaved thinking blocks are all eradicated."""
        adversarial_blob = (
            "<think>Thought 1</think>\n"
            "Часть 1 саммари.\n"
            "&lt;reasoning&gt;Thought 2&lt;/reasoning&gt;\n"
            "Часть 2 саммари.\n"
            "<THOUGHT>Thought 3</THOUGHT>\n"
            "Часть 3 саммари.\n"
            "<reflection>Thought 4</reflection>"
        )
        cleaned = strip_thinking_tags(adversarial_blob)
        assert "<think>" not in cleaned
        assert "<reasoning>" not in cleaned
        assert "<THOUGHT>" not in cleaned
        assert "<reflection>" not in cleaned
        assert "Часть 1 саммари." in cleaned
        assert "Часть 2 саммари." in cleaned
        assert "Часть 3 саммари." in cleaned


# ============================================================================
# 2. Adversarial Telegraph AST Payload Limit Stress Tests
# ============================================================================

class TestAdversarialTelegraphASTPayloadLimits:
    """Stress tests Telegraph AST node conversion and strict <= 55,000 byte limit enforcement."""

    @patch("requests.post")
    def test_massive_cyrillic_single_paragraph_payload_limit(self, mock_post):
        """
        Adversarial test: A single massive paragraph of 100,000+ Cyrillic characters (~200,000+ bytes)
        must be safely reduced to strictly <= 55,000 bytes UTF-8 JSON payload.
        """
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"ok": True, "result": {"url": "https://telegra.ph/p-single-massive"}}
        mock_post.return_value = mock_resp

        # 140,000 Cyrillic characters (260,000+ UTF-8 bytes)
        cyrillic_single = "Двачер " * 20000
        assert len(cyrillic_single) > 100000
        assert len(cyrillic_single.encode('utf-8')) > 200000

        nodes = _text_to_telegraph_nodes(cyrillic_single)
        url = _telegraph_create_page_sync(token="tok-test", title="Single Massive Test", content_nodes=nodes)

        assert url == "https://telegra.ph/p-single-massive"
        mock_post.assert_called_once()
        sent_payload_str = mock_post.call_args[1]["data"]["content"]
        sent_payload_bytes = len(sent_payload_str.encode('utf-8'))

        assert sent_payload_bytes <= 55000, f"Payload exceeded 55,000 bytes: {sent_payload_bytes}"
        assert "Текст сокращен из-за лимита Telegraph" in sent_payload_str

    @patch("requests.post")
    def test_massive_cyrillic_multi_paragraph_payload_limit(self, mock_post):
        """
        Adversarial test: 1,000 Cyrillic paragraphs (>250,000 bytes) must be chunked/reduced
        so that json.dumps(nodes, ensure_ascii=False) is strictly <= 55,000 bytes.
        """
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"ok": True, "result": {"url": "https://telegra.ph/p-multi-massive"}}
        mock_post.return_value = mock_resp

        multi_para_html = "\n\n".join([
            f"<p>Абзац {i}: Развернутый анализ треда на Дваче с детальным обсуждением музыки и мнений анонов.</p>"
            for i in range(1000)
        ])
        nodes = _text_to_telegraph_nodes(multi_para_html)
        initial_payload_bytes = len(json.dumps(nodes, ensure_ascii=False).encode('utf-8'))
        assert initial_payload_bytes > 100000

        url = _telegraph_create_page_sync(token="tok-test", title="Multi Massive Test", content_nodes=nodes)

        assert url == "https://telegra.ph/p-multi-massive"
        sent_payload_str = mock_post.call_args[1]["data"]["content"]
        sent_payload_bytes = len(sent_payload_str.encode('utf-8'))

        assert sent_payload_bytes <= 55000, f"Payload exceeded 55,000 bytes: {sent_payload_bytes}"
        assert "Текст сокращен из-за лимита Telegraph" in sent_payload_str

    def test_deeply_nested_dom_nodes_ast_flattener(self):
        """
        Deeply nested DOM nodes (20+ levels of b, i, u, s, code) are parsed into
        valid Telegraph AST nodes conforming to Telegraph API specifications.
        """
        nested_html = "<b><i><u><s><code>" * 5 + "Deeply nested formatted text" + "</code></s></u></i></b>" * 5
        nodes = _text_to_telegraph_nodes(nested_html)

        assert len(nodes) >= 1
        # Root node is a block tag 'p'
        assert nodes[0]["tag"] == "p"
        # Validate JSON serialization without escaping non-ASCII characters
        serialized = json.dumps(nodes, ensure_ascii=False)
        parsed = json.loads(serialized)
        assert isinstance(parsed, list)
        assert "Deeply nested formatted text" in serialized

    @patch("requests.post")
    def test_asymmetric_nodes_massive_first_node(self, mock_post):
        """
        Asymmetric distribution: Node 0 is massive (100,000+ chars) while Node 1 is tiny.
        The auto-reduction algorithm safely prunes Node 0 down to <= 55,000 bytes.
        """
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"ok": True, "result": {"url": "https://telegra.ph/p-asymm-1"}}
        mock_post.return_value = mock_resp

        nodes = [
            {"tag": "p", "children": ["Огромнейший текст в первом блоке " * 8000]},
            {"tag": "p", "children": ["Короткий второй блок"]}
        ]
        url = _telegraph_create_page_sync(token="tok-test", title="Asymm 1", content_nodes=nodes)

        assert url == "https://telegra.ph/p-asymm-1"
        sent_payload_str = mock_post.call_args[1]["data"]["content"]
        sent_payload_bytes = len(sent_payload_str.encode('utf-8'))
        assert sent_payload_bytes <= 55000

    @patch("requests.post")
    def test_asymmetric_nodes_massive_last_node(self, mock_post):
        """
        Asymmetric distribution: Node 0 is tiny while Node 1 is massive (100,000+ chars).
        The auto-reduction algorithm safely prunes Node 1 down to <= 55,000 bytes.
        """
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"ok": True, "result": {"url": "https://telegra.ph/p-asymm-2"}}
        mock_post.return_value = mock_resp

        nodes = [
            {"tag": "p", "children": ["Короткий первый блок"]},
            {"tag": "p", "children": ["Огромнейший текст во втором блоке " * 8000]}
        ]
        url = _telegraph_create_page_sync(token="tok-test", title="Asymm 2", content_nodes=nodes)

        assert url == "https://telegra.ph/p-asymm-2"
        sent_payload_str = mock_post.call_args[1]["data"]["content"]
        sent_payload_bytes = len(sent_payload_str.encode('utf-8'))
        assert sent_payload_bytes <= 55000

    @patch("requests.post")
    def test_thousands_of_tiny_nodes(self, mock_post):
        """5,000 tiny AST nodes exceeding 55,000 bytes total JSON payload are shrunk safely."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"ok": True, "result": {"url": "https://telegra.ph/p-tiny-nodes"}}
        mock_post.return_value = mock_resp

        tiny_nodes = [{"tag": "p", "children": [f"Paragraph #{i}"]} for i in range(5000)]
        url = _telegraph_create_page_sync(token="tok-test", title="Tiny Nodes", content_nodes=tiny_nodes)

        assert url == "https://telegra.ph/p-tiny-nodes"
        sent_payload_str = mock_post.call_args[1]["data"]["content"]
        sent_payload_bytes = len(sent_payload_str.encode('utf-8'))
        assert sent_payload_bytes <= 55000

    @patch("requests.post")
    @patch("time.sleep", return_value=None)
    def test_content_too_big_consecutive_reduction_recovery(self, mock_sleep, mock_post):
        """
        Simulate Telegraph API rejecting payload with CONTENT_TOO_BIG twice in a row,
        verifying that the auto-reduction loop reduces AST payload size on each attempt
        and succeeds on the third attempt with payload <= 55,000 bytes.
        """
        resp_too_big = MagicMock()
        resp_too_big.status_code = 200
        resp_too_big.json.return_value = {"ok": False, "error": "CONTENT_TOO_BIG"}

        resp_ok = MagicMock()
        resp_ok.status_code = 200
        resp_ok.json.return_value = {"ok": True, "result": {"url": "https://telegra.ph/p-recovered-multi"}}

        recorded_payloads = []

        def side_effect_fn(*args, **kwargs):
            content_str = kwargs.get("data", {}).get("content", "")
            recorded_payloads.append(content_str)
            if len(recorded_payloads) == 1:
                return resp_too_big
            elif len(recorded_payloads) == 2:
                return resp_too_big
            return resp_ok

        mock_post.side_effect = side_effect_fn

        nodes = [{"tag": "p", "children": [f"Paragraph item {i} with some content"]} for i in range(50)]
        url = _telegraph_create_page_sync(token="tok-test", title="Recovery Test", content_nodes=nodes)

        assert url == "https://telegra.ph/p-recovered-multi"
        assert len(recorded_payloads) == 3

        # Verify sizes strictly decrease across retries
        size_0 = len(recorded_payloads[0].encode('utf-8'))
        size_1 = len(recorded_payloads[1].encode('utf-8'))
        size_2 = len(recorded_payloads[2].encode('utf-8'))

        assert size_1 < size_0
        assert size_2 < size_1
        assert size_2 <= 55000

    @patch("summarize.get_telegraph_token", return_value="tok-mock")
    @patch("requests.post")
    def test_create_telegraph_page_blocking_100k_chars_integration(self, mock_post, mock_token):
        """
        Integration test: `_create_telegraph_page_blocking` with 100,000+ characters HTML content.
        Validates pre-truncation at character level (<=18000 chars) before AST generation
        and final AST payload <= 55,000 bytes.
        """
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"ok": True, "result": {"url": "https://telegra.ph/p-blocking-100k"}}
        mock_post.return_value = mock_resp

        massive_html = "<p>" + ("Двачер обсуждает музыку в треде. " * 3000) + "</p>"
        assert len(massive_html) > 90000

        url = _create_telegraph_page_blocking("100K Blocking Test", massive_html)

        assert url == "https://telegra.ph/p-blocking-100k"
        sent_payload_str = mock_post.call_args[1]["data"]["content"]
        sent_payload_bytes = len(sent_payload_str.encode('utf-8'))
        assert sent_payload_bytes <= 55000
        assert "Саммари сокращено по лимиту Telegraph" in sent_payload_str
