# -*- coding: utf-8 -*-
import asyncio
import gzip
import json
import os
import re
import shutil
import sqlite3
import subprocess
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest


@pytest.fixture(autouse=True)
def reset_summarize_state():
    import summarize
    summarize._key_cooldowns.clear()
    summarize._key_model_cooldowns.clear()
    summarize._key_global_cooldowns.clear()
    summarize._provider_cooldowns.clear()
    summarize._model_cooldowns.clear()
    summarize._PROVIDER_LAST_REQUEST_TS.clear()
    summarize._SHARED_HTTP_CLIENT = None
    yield
    summarize._key_cooldowns.clear()
    summarize._key_model_cooldowns.clear()
    summarize._key_global_cooldowns.clear()
    summarize._provider_cooldowns.clear()
    summarize._model_cooldowns.clear()
    summarize._PROVIDER_LAST_REQUEST_TS.clear()
    summarize._SHARED_HTTP_CLIENT = None


# =========================================================================
# 1. GRANULAR PER-(KEY, MODEL) COOLDOWNS & TIMEOUT / FALLBACK RESILIENCE
# =========================================================================

def test_token_rotator_granular_model_cooldown():
    from common.token_pool import TokenRotator

    rot = TokenRotator("tok1,tok2", min_interval=0.0, name="TestGemini")
    rot.penalize_token("tok1", duration=120.0, model="gemini-3.6-flash")

    assert rot.is_token_on_cooldown("tok1", model="gemini-3.6-flash") is True
    # Other models on the SAME key must NOT be blocked
    assert rot.is_token_on_cooldown("tok1", model="gemini-3.1-flash-lite") is False
    assert rot.is_token_on_cooldown("tok1") is False

    # Model-filtered token list pushes tok1 to cooling for 3.6-flash only
    tokens_36 = rot.get_all_active_tokens(model="gemini-3.6-flash")
    assert tokens_36 == ["tok2", "tok1"]

    tokens_31_a = rot.get_all_active_tokens(model="gemini-3.1-flash-lite")
    tokens_31_b = rot.get_all_active_tokens(model="gemini-3.1-flash-lite")
    assert set(tokens_31_a) == {"tok1", "tok2"}
    assert tokens_31_a[0] != tokens_31_b[0]  # normal round-robin across both ready keys


@pytest.mark.asyncio
async def test_gemini_429_on_one_model_does_not_halt_provider_and_reuses_keys_on_flash_lite():
    """
    Reproduces the live-log failure (2026-11-25 00:25:04):
    Two consecutive 429s on a single 5-RPM model (gemini-3.6-flash) must NOT halt the entire
    Gemini provider for 5m; instead it must cool down gemini-3.6-flash and succeed on a
    15-RPM model (gemini-3.5-flash-lite / gemini-3.1-flash-lite) using the SAME live keys.
    """
    import summarize

    called_pairs = []

    async def fake_openai_create(**kwargs):
        raise AssertionError("Should not reach OpenAI mock when testing native/mock path")

    mock_client = AsyncMock()

    async def mock_create(**kwargs):
        model = kwargs["model"]
        # Grab api_key from latest AsyncOpenAI call
        api_key = mock_async_openai.call_args.kwargs["api_key"]
        called_pairs.append((model, api_key))
        if model in ("gemini-3.7-flash", "gemini-3.6-flash", "gemini-3.5-flash"):
            raise Exception("429 Resource Exhausted (Rate Limit)")
        choice = MagicMock()
        choice.finish_reason = "stop"
        choice.message.content = "Саммари от >>123456 через живую модель"
        return MagicMock(choices=[choice])

    mock_client.chat.completions.create.side_effect = mock_create

    with patch("summarize.AsyncOpenAI", return_value=mock_client) as mock_async_openai, \
         patch("summarize.google_pool.get_all_active_tokens", return_value=["gkey1", "gkey2"]), \
         patch("summarize.groq_pool.get_all_active_tokens", return_value=["groq1"]), \
         patch("summarize.agentrouter_pool.get_all_active_tokens", return_value=[]):
        res = await summarize.summarize_text_with_hf(
            "Сделай саммари треда",
            "Анон #123456: Проверка гранулярного кулдауна на 429.",
            model_preference="gemini",
        )

    assert ">>123456" in res
    # Provider Gemini must NOT be globally halted because flash-lite succeeded!
    assert "gemini" not in summarize._provider_cooldowns
    # Same keys gkey1/gkey2 were still allowed on the next Gemini model
    succeeded_model, succeeded_key = called_pairs[-1]
    assert succeeded_model.startswith("gemini-")
    assert succeeded_key in ("gkey1", "gkey2")


@pytest.mark.asyncio
async def test_gemini_read_timeout_sets_model_cooldown_and_switches_to_next_gemini_model():
    """ReadTimeout('') on gemini-3.7-flash cools only gemini-3.7-flash and switches to next Gemini model."""
    import summarize

    called_models = []
    mock_client = AsyncMock()

    async def mock_create(**kwargs):
        model = kwargs["model"]
        called_models.append(model)
        if len(called_models) == 1:
            raise httpx.ReadTimeout("")
        choice = MagicMock()
        choice.finish_reason = "stop"
        choice.message.content = "Успешный ответ после таймаута"
        return MagicMock(choices=[choice])

    mock_client.chat.completions.create.side_effect = mock_create

    with patch("summarize.AsyncOpenAI", return_value=mock_client), \
         patch("summarize.google_pool.get_all_active_tokens", return_value=["gkey1", "gkey2"]), \
         patch("summarize.groq_pool.get_all_active_tokens", return_value=["groq1"]), \
         patch("summarize.agentrouter_pool.get_all_active_tokens", return_value=[]):
        res = await summarize.summarize_text_with_hf(
            "Дай ответ",
            "Анон #1001: Тестовое сообщение.",
            model_preference="gemini",
        )

    assert res == "Успешный ответ после таймаута"
    assert len(called_models) == 2
    assert called_models[0] != called_models[1]
    assert called_models[1].startswith("gemini-")
    assert summarize._model_cooldowns.get(called_models[0], 0) > time.time()
    assert "gemini" not in summarize._provider_cooldowns


@pytest.mark.asyncio
async def test_gemini_halts_provider_only_after_all_cascade_models_exhausted():
    """Only when EVERY Gemini model in the cascade fails with 429 does Gemini get halted and Groq takes over."""
    import summarize

    called_models = []
    mock_client = AsyncMock()

    async def mock_create(**kwargs):
        model = kwargs["model"]
        called_models.append(model)
        if model.startswith("gemini-"):
            raise Exception("429 Too Many Requests")
        choice = MagicMock()
        choice.finish_reason = "stop"
        choice.message.content = "Ответ через Groq fallback"
        return MagicMock(choices=[choice])

    mock_client.chat.completions.create.side_effect = mock_create

    with patch("summarize.AsyncOpenAI", return_value=mock_client), \
         patch("summarize.google_pool.get_all_active_tokens", return_value=["gkey1", "gkey2"]), \
         patch("summarize.groq_pool.get_all_active_tokens", return_value=["groq1"]), \
         patch("summarize.agentrouter_pool.get_all_active_tokens", return_value=[]):
        res = await summarize.summarize_text_with_hf(
            "Сделай саммари",
            "Анон #555: Пост в треде.",
            model_preference="gemini",
        )

    assert res == "Ответ через Groq fallback"
    gemini_models_tried = {m for m in called_models if m.startswith("gemini-")}
    # All 5 Gemini models in the 'gemini' cascade must have been attempted before halting provider
    assert gemini_models_tried == {
        "gemini-3.5-flash",
        "gemini-3.5-flash-lite",
        "gemini-3.1-flash-lite",
        "gemini-3.6-flash",
        "gemini-3.7-flash",
    }
    assert "gemini" in summarize._provider_cooldowns
    assert summarize._provider_cooldowns["gemini"] > time.time()


# =========================================================================
# 2. SUMMARY QUALITY, THREAD COMPRESSION, MEDIA-ONLY & HTML SAFETY
# =========================================================================

def test_compress_thread_dump_preserves_op_mid_refs_and_tail():
    from summarize import compress_thread_dump

    op = "Анон #100001 (ОП): Обсуждаем архитектуру базы данных и миграцию на WAL."
    mid_noise = ["Анон: [sticker]" for _ in range(130)]
    mid_key = "Анон #100042 (Ответ на #100001): >>100001 WAL не спасёт без db_lock и PRAGMA busy_timeout."
    tail = [f"Анон #{100100 + i}: Финальный спор про тесты и деплой #{100100 + i} >>100042." for i in range(60)]

    full_dump = "\n".join([op] + mid_noise + [mid_key] + tail)
    assert len(full_dump) > 6000

    compressed = compress_thread_dump(full_dump, max_chars=2500)
    assert len(compressed) <= 2500
    assert "#100001" in compressed  # OP post preserved!
    assert ">>100001" in compressed  # Salient >>post_num mid reply preserved!
    assert "100159" in compressed  # Latest tail post preserved!


def test_html_truncation_and_sanitization_balances_blockquote_and_tags():
    from summarize import safe_truncate_telegram_html, sanitize_summary_html, _create_telegraph_page_blocking

    html_sample = (
        '<b>Разбор треда</b>\n\n'
        '<blockquote expandable>Цитата про >>123456: <i>очень длинный разбор '
        + ("аргументов и фактов " * 200)
        + '</i></blockquote>\n\n<tg-spoiler>спойлер</tg-spoiler>'
    )
    truncated = safe_truncate_telegram_html(html_sample, max_utf16=400)
    assert len(truncated.encode("utf-16-le")) // 2 <= 400
    assert truncated.count("<blockquote") == truncated.count("</blockquote>")
    assert truncated.count("<b>") == truncated.count("</b>")
    assert truncated.count("<i>") == truncated.count("</i>")
    assert not truncated.endswith("<")

    sanitized = sanitize_summary_html(
        "<p><b>Тест</b> & <tg-spoiler>секрет</tg-spoiler> <script>alert(1)</script></p>",
        max_utf16=300,
    )
    assert "<script>" not in sanitized
    assert "<p>" not in sanitized
    assert "<tg-spoiler>секрет</tg-spoiler>" in sanitized
    assert "&amp;" in sanitized

    # Telegraph pre-truncation (>18000 chars) must keep balanced HTML tags
    huge_html = '<b>Заголовок</b>\n\n<blockquote expandable>' + ("Анон >>111 писал про баги. " * 1200) + '</blockquote>'
    captured_nodes = []
    with patch("summarize.get_telegraph_token", return_value="fake-tok"), \
         patch("summarize._telegraph_create_page_sync", side_effect=lambda tok, title, nodes: captured_nodes.append(nodes) or "https://telegra.ph/test"):
        url = _create_telegraph_page_blocking("Test", huge_html)
    assert url == "https://telegra.ph/test"
    assert len(captured_nodes) == 1
    assert any(isinstance(n, dict) and n.get("tag") == "blockquote" for n in captured_nodes[0])


@pytest.mark.asyncio
async def test_media_only_and_empty_thread_handling_and_anti_slop_prompt():
    import summarize

    # 1. Empty dump -> empty string, zero LLM calls
    assert await summarize.dispatch_llm_completion("Саммари", "   \n  ") == ""

    # 2. Media-only dump -> honest media summary without LLM hallucination
    media_dump = "Анон: [photo]\nАнон: [sticker]\nАнон: [video]\nАнон: [photo]"
    with patch("summarize._summarize_inner", new_callable=AsyncMock) as mock_inner:
        res = await summarize.dispatch_llm_completion("Сделай саммари треда", media_dump)
    mock_inner.assert_not_called()
    assert "Медиа-тред" in res
    assert "фото: 2" in res

    # 3. Anti-slop + >>post_num grounding injected for summaries, NOT for JSON prompts
    captured_sys = []
    mock_client = AsyncMock()

    async def mock_create(**kwargs):
        captured_sys.append(kwargs["messages"][0]["content"])
        choice = MagicMock()
        choice.finish_reason = "stop"
        choice.message.content = "<b>Суть:</b> >>123456 доказал свою правоту."
        return MagicMock(choices=[choice])

    mock_client.chat.completions.create.side_effect = mock_create

    with patch("summarize.AsyncOpenAI", return_value=mock_client), \
         patch("summarize.groq_pool.get_all_active_tokens", return_value=["groq1"]), \
         patch("summarize.google_pool.get_all_active_tokens", return_value=[]):
        await summarize.dispatch_llm_completion(
            "Сделай саммари треда",
            "Анон #123456: Аргумент по делу.",
            model_preference="groq",
        )
        await summarize.dispatch_llm_completion(
            'Classify post and output valid JSON: {"persona": "x", "reactions": ["👍"]}',
            "Анон: мем смешной",
            model_preference="fast",
        )

    assert len(captured_sys) == 2
    assert ">>123456" in captured_sys[0]
    assert "В этом треде участники обсудили" in captured_sys[0]
    assert "CRITICAL OUTPUT FORMAT RULES" not in captured_sys[1]


# =========================================================================
# 3. MIRROR QUEUE CLEANUP & CATBOX-PAUSED CASCADE FALLBACK
# =========================================================================

@pytest.mark.asyncio
async def test_cleanup_mirror_queue_purges_duplicates_max_attempts_and_stale(tmp_path):
    from site_tgach.mirror_worker import cleanup_mirror_queue, MAX_MIRROR_ATTEMPTS
    from common.db_pool import db_lock

    db_file = tmp_path / "test_mirror.db"
    conn = sqlite3.connect(db_file)
    conn.executescript(
        """
        CREATE TABLE MirrorQueue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id TEXT NOT NULL,
            mirror_type TEXT NOT NULL,
            attempts INTEGER DEFAULT 0,
            next_run_at REAL,
            UNIQUE(file_id, mirror_type)
        );
        CREATE TABLE FileMirrors (
            file_id TEXT NOT NULL,
            mirror_type TEXT NOT NULL,
            mirror_url TEXT NOT NULL,
            PRIMARY KEY (file_id, mirror_type)
        );
        CREATE TABLE PostFiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_num INTEGER,
            original_file_id TEXT,
            thumbnail_file_id TEXT
        );
        """
    )
    now = time.time()
    old_ts = now - 10 * 86400

    # 1. Duplicate (already in FileMirrors for same mirror_type='catbox') -> must be deleted
    conn.execute("INSERT INTO FileMirrors VALUES ('fid_dup', 'catbox', 'https://files.catbox.moe/abc.jpg')")
    conn.execute("INSERT INTO MirrorQueue (file_id, mirror_type, attempts, next_run_at) VALUES ('fid_dup', 'catbox', 0, ?)", (now,))
    conn.execute("INSERT INTO PostFiles (post_num, original_file_id) VALUES (1, 'fid_dup')")

    # 2. Max attempts exceeded -> must be deleted
    conn.execute("INSERT INTO MirrorQueue (file_id, mirror_type, attempts, next_run_at) VALUES ('fid_max', 'catbox', ?, ?)", (MAX_MIRROR_ATTEMPTS + 1, now))
    conn.execute("INSERT INTO PostFiles (post_num, original_file_id) VALUES (2, 'fid_max')")

    # 3. Stale (>7d) with existing external mirror (pixhost) -> must be deleted
    conn.execute("INSERT INTO FileMirrors VALUES ('fid_ext', 'pixhost', 'https://img1.pixhost.to/images/1/x.jpg')")
    conn.execute("INSERT INTO MirrorQueue (file_id, mirror_type, attempts, next_run_at) VALUES ('fid_ext', 'catbox', 1, ?)", (old_ts,))
    conn.execute("INSERT INTO PostFiles (post_num, original_file_id) VALUES (3, 'fid_ext')")

    # 4. Stale (>7d) orphaned (not in PostFiles) -> must be deleted
    conn.execute("INSERT INTO MirrorQueue (file_id, mirror_type, attempts, next_run_at) VALUES ('fid_orphan', 'catbox', 0, ?)", (old_ts,))

    # 5. Legitimate pending task (recent, in PostFiles, no mirror yet) -> must SURVIVE
    conn.execute("INSERT INTO MirrorQueue (file_id, mirror_type, attempts, next_run_at) VALUES ('fid_valid', 'catbox', 1, ?)", (now,))
    conn.execute("INSERT INTO PostFiles (post_num, original_file_id) VALUES (5, 'fid_valid')")

    conn.commit()
    conn.close()

    import aiosqlite
    async with aiosqlite.connect(db_file) as adb:
        with patch("common.db_pool.get_pool", return_value=adb), patch("common.db_pool.db_lock", asyncio.Lock()):
            stats = await cleanup_mirror_queue(batch_size=10, max_batches=10)

        assert stats["already_mirrored"] == 1
        assert stats["max_attempts"] == 1
        assert stats["stale_external"] == 1
        assert stats["orphaned_stale"] == 1

        async with adb.execute("SELECT file_id FROM MirrorQueue") as cur:
            remaining = [r[0] for r in await cur.fetchall()]
        assert remaining == ["fid_valid"]


@pytest.mark.asyncio
async def test_mirror_worker_catbox_paused_does_not_freeze_queue_and_skips_existing_external():
    from site_tgach.mirror_worker import _process_single_task

    task = {"id": 99, "file_id": "AgACtest123456", "mirror_type": "catbox", "attempts": 0}
    with patch("site_tgach.mirror_worker.is_catbox_available", return_value=False), \
         patch("site_tgach.mirror_worker.get_file_mirrors", new_callable=AsyncMock, return_value={"pixhost": "https://img1.pixhost.to/x.jpg"}), \
         patch("site_tgach.mirror_worker.remove_mirror_task", new_callable=AsyncMock) as mock_remove, \
         patch("site_tgach.mirror_worker._resolve_file_bot") as mock_bot:
        await _process_single_task(task)

    mock_remove.assert_awaited_once_with(99)
    mock_bot.assert_not_called()


# =========================================================================
# 4. SITE_TGACH BACKEND API CONTRACTS & FRONTEND JS HYGIENE
# =========================================================================

@pytest.mark.asyncio
async def test_api_thread_summary_never_caches_failure_and_vibe_handles_none():
    from starlette.requests import Request
    from site_tgach.main import app, api_thread_summary, vibe_to_icon

    assert vibe_to_icon(None) == "❓ (Неясно)"
    assert vibe_to_icon("") == "❓ (Неясно)"

    mock_backend = AsyncMock()
    mock_backend.get.return_value = None
    mock_neuro = AsyncMock()
    mock_neuro.generate_summary.return_value = "Нейронка сдохла."

    prev_neuro = getattr(app.state, "neuro_manager", None)
    app.state.neuro_manager = mock_neuro
    fake_req = Request({
        "type": "http",
        "method": "GET",
        "path": "/api/summary/100",
        "headers": [],
        "client": ("127.0.0.99", 12345),
        "session": {},
        "app": app,
    })
    fake_req.state.stream = "ru"

    op_post = {"id": 100, "content": {"text": "Длинный ОП-пост с контекстом обсуждения для теста саммари треда." * 2}, "author_id": 1, "timestamp": 1700000000}
    try:
        with patch("site_tgach.main.get_post_count_in_thread", new_callable=AsyncMock, return_value=5), \
             patch("site_tgach.main.FastAPICache.get_backend", return_value=mock_backend), \
             patch("site_tgach.main.get_thread_by_op_post", new_callable=AsyncMock, return_value=(op_post, [])):
            res = await api_thread_summary(100, fake_req)
    finally:
        app.state.neuro_manager = prev_neuro

    assert "Нейронка сдохла" in res["summary"]
    mock_backend.set.assert_not_awaited()


@pytest.mark.asyncio
async def test_api_get_meta_handles_missing_content_attr_and_invalid_host():
    from fastapi_cache import FastAPICache
    from fastapi_cache.backends.inmemory import InMemoryBackend
    from site_tgach.main import api_get_meta

    FastAPICache.init(InMemoryBackend(), prefix="fastapi-cache")

    # Missing hostname -> 400
    resp_bad = await api_get_meta("http:///nohost")
    assert resp_bad.status_code == 400

    # Mock HTML where <meta property="og:title"> has NO content attribute
    fake_html = b"<html><head><title>Safe Page</title><meta property='og:title'><meta property='og:description'></head></html>"

    class FakeResp:
        status_code = 200
        async def aiter_bytes(self):
            yield fake_html
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            return False

    class FakeClient:
        def stream(self, method, url):
            return FakeResp()
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            return False

    fake_addr = [(2, 1, 6, "", ("93.184.216.34", 443))]
    with patch("site_tgach.main.socket.getaddrinfo", return_value=fake_addr), \
         patch("site_tgach.main.httpx.AsyncClient", return_value=FakeClient()):
        res = await api_get_meta("https://example.com/article")

    assert res["title"] == "Safe Page"
    assert res["description"] is None


def test_site_tgach_main_js_technical_fixes_and_bundle_sync():
    js_dir = Path("site_tgach/static/js")
    main_js = (js_dir / "main.js").read_text(encoding="utf-8")
    main_src = (js_dir / "main.src.js").read_text(encoding="utf-8")
    main_min = (js_dir / "main.min.js").read_text(encoding="utf-8")

    assert main_js == main_src == main_min

    with gzip.open(js_dir / "main.js.gz", "rt", encoding="utf-8") as f:
        assert f.read() == main_js
    with gzip.open(js_dir / "main.min.js.gz", "rt", encoding="utf-8") as f:
        assert f.read() == main_min

    # VideoPopupManager listener cleanup + video unload
    assert "window.removeEventListener('mousemove', this._dragMove);" in main_js
    assert "this.video.removeAttribute('src');" in main_js
    # WSManager initializes addedNodes instead of empty fragment
    assert "const addedNodes = Array.from(fragment.children);" in main_js
    assert "fragment.querySelectorAll('.new-post-animation')" not in main_js
    # Mobile QuickQuote + null guard
    assert "document.addEventListener('touchend', scheduleSelectionCheck" in main_js
    assert "const rect = main ? main.getBoundingClientRect() : null;" in main_js

    node_cmd = shutil.which("node")
    if node_cmd:
        proc = subprocess.run([node_cmd, "--check", str(js_dir / "main.js")], capture_output=True, text=True)
        assert proc.returncode == 0, proc.stderr


def test_site_tgach_api_endpoint_guards_present():
    src = Path("site_tgach/main.py").read_text(encoding="utf-8")
    assert "page: int = Query(0, ge=0, le=1000)" in src
    assert 'BOARD_VERSIONS.get(board_id, 0)' in src
    assert 'clean_nums = list(dict.fromkeys(post_nums))[:200]' in src
    assert 'if board_id != "overboard" and board_id not in BOARD_CONFIG:' in src
