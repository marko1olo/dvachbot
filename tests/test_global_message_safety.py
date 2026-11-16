import pytest
import asyncio
from typing import Optional, List, Any
from aiogram import types, Bot
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, Chat, User
from aiogram.exceptions import TelegramBadRequest

from common.bot_helpers import (
    smart_split_html,
    safe_send_message,
    safe_answer,
    safe_reply,
    install_message_safety_guard,
    _send_safe_text_message
)

class MockBot:
    def __init__(self):
        self.sent_messages = []

    async def send_message(
        self,
        chat_id: int,
        text: str,
        reply_to_message_id: Optional[int] = None,
        reply_markup: Optional[Any] = None,
        parse_mode: Optional[str] = "HTML",
        disable_web_page_preview: bool = True
    ):
        if len(text) > 4096:
            raise TelegramBadRequest(method="SendMessage", message="Bad Request: message is too long")
        msg = {
            "id": len(self.sent_messages) + 1,
            "chat_id": chat_id,
            "text": text,
            "reply_to_message_id": reply_to_message_id,
            "reply_markup": reply_markup,
            "parse_mode": parse_mode
        }
        self.sent_messages.append(msg)
        return types.Message.model_construct(
            message_id=msg["id"],
            date=None,
            chat=types.Chat(id=chat_id, type="private"),
            text=text
        )


def test_smart_split_html_short_text():
    text = "Short text <= 4000 characters."
    chunks = smart_split_html(text, max_chunk_size=4000)
    assert len(chunks) == 1
    assert chunks[0] == text


def test_smart_split_html_empty():
    assert smart_split_html("", max_chunk_size=4000) == []


def test_smart_split_html_preserves_tags():
    # Construct a long text with tags
    inner = "Line with <b>bold text</b> and <code>some code snippet</code>.\n" * 150
    text = f"<blockquote><b>Header Title</b>\n<i>{inner}</i></blockquote>"
    assert len(text) > 4000

    chunks = smart_split_html(text, max_chunk_size=1500)
    assert len(chunks) > 1

    from html.parser import HTMLParser
    class TagChecker(HTMLParser):
        def __init__(self):
            super().__init__()
            self.stack = []
            self.errors = []
        def handle_starttag(self, tag, attrs):
            self.stack.append(tag)
        def handle_endtag(self, tag):
            if not self.stack or self.stack[-1] != tag:
                self.errors.append(f"Mismatched </{tag}> against stack {self.stack}")
            else:
                self.stack.pop()

    for idx, c in enumerate(chunks):
        assert len(c) <= 1500, f"Chunk {idx+1} exceeds max_chunk_size: {len(c)}"
        checker = TagChecker()
        checker.feed(c)
        assert not checker.errors, f"Chunk {idx+1} has tag mismatch: {checker.errors}"
        assert not checker.stack, f"Chunk {idx+1} has unclosed tags: {checker.stack}"


def test_smart_split_html_long_unbroken_token():
    huge_token = "<b>Hash:</b> <code>" + ("X" * 5000) + "</code>"
    chunks = smart_split_html(huge_token, max_chunk_size=1200)
    assert len(chunks) > 1
    for c in chunks:
        assert len(c) <= 1200


@pytest.mark.asyncio
async def test_safe_send_message_chunking():
    bot = MockBot()
    long_text = "<b>Transaction History</b>\n" + ("• 15.11.2026: +1,000 ₪ bonus payment\n" * 150)
    assert len(long_text) > 4096

    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Next", callback_data="next")]])
    last_msg = await safe_send_message(bot, chat_id=12345, text=long_text, reply_markup=kb, sleep_between=0)

    assert last_msg is not None
    assert len(bot.sent_messages) >= 2
    # Check that all chunks are <= 4096
    for m in bot.sent_messages:
        assert len(m["text"]) <= 4096
    # Check that keyboard is attached ONLY to the last message
    for m in bot.sent_messages[:-1]:
        assert m["reply_markup"] is None
    assert bot.sent_messages[-1]["reply_markup"] == kb


@pytest.mark.asyncio
async def test_safe_send_message_parse_error_fallback():
    class BrokenHTMLBot:
        def __init__(self):
            self.calls = []
        async def send_message(self, chat_id, text, reply_markup=None, parse_mode="HTML", disable_web_page_preview=True):
            self.calls.append({"text": text, "parse_mode": parse_mode})
            if parse_mode == "HTML":
                raise TelegramBadRequest(method="SendMessage", message="Bad Request: can't parse entities in message text: closing tag missing")
            return types.Message.model_construct(message_id=1, date=None, chat=types.Chat(id=chat_id, type="private"), text=text)

    broken_bot = BrokenHTMLBot()
    res = await safe_send_message(broken_bot, chat_id=999, text="<b>Broken unclosed tag", sleep_between=0)
    assert res is not None
    assert len(broken_bot.calls) == 2
    assert broken_bot.calls[0]["parse_mode"] == "HTML"
    assert broken_bot.calls[1]["parse_mode"] is None


@pytest.mark.asyncio
async def test_install_message_safety_guard():
    install_message_safety_guard()
    bot = MockBot()

    # Create mock message and attach bot safely
    msg = types.Message.model_construct(
        message_id=42,
        date=None,
        chat=types.Chat(id=777, type="private"),
        text="/test"
    )
    msg._bot = bot

    huge_text = "<b>Forbes Leaderboard:</b>\n" + ("1. Anon 123 — 1,000,000 ₪ capital\n" * 160)
    assert len(huge_text) > 4096

    # Calling msg.answer with huge_text should NOT throw TelegramBadRequest
    sent = await msg.answer(huge_text)
    assert sent is not None
    assert len(bot.sent_messages) >= 2
    for m in bot.sent_messages:
        assert len(m["text"]) <= 4096


def test_command_aliases_registered():
    import main
    from aiogram.filters import Command

    # Inspect command handlers in main.dp
    registered_cmds = set()
    for handler in main.dp.message.handlers:
        for f in handler.filters:
            cb = getattr(f, "callback", f)
            if isinstance(cb, Command):
                for cmd in cb.commands:
                    registered_cmds.add(cmd.lower())

    # Check newly added aliases
    expected_aliases = [
        "summarize", "саммари", "пересказ",
        "drocheslav", "raid", "mammoth",
        "horoscope_rus", "chertog",
        "slav_trade", "gramota",
        "hyperborea", "vimana",
        "slav_curse", "anathema"
    ]
    for alias in expected_aliases:
        assert alias in registered_cmds, f"Alias '/{alias}' must be registered in main.py message handlers!"
