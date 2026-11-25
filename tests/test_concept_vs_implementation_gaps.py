# -*- coding: utf-8 -*-
"""
tests/test_concept_vs_implementation_gaps.py

Red-Team verification suite for Concept-vs-Implementation gaps:
1. Zero orphaned callback_data across main.py and all included routers/engines.
2. All BotCommands + advertised commands (/isolation, /tag, /getid) registered.
3. /anime fast timeouts (<= 8s per item) and early partial-pack delivery when 8-9/10 succeed.
4. Quick-menu anime handler tuple-unpacking regression guard.
5. /start (DM & group fallback), /achievements (<=1024 chars, back button), /anon, /getid Zero-PII.
6. AI /roast & Cyberchad JSON parser: <think> stripping, typing indicator, length clamping.
"""

import ast
import asyncio
import re
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parent.parent

INCLUDED_ROUTER_FILES = [
    "main.py",
    "economy_extension.py",
    "stats_hub_router.py",
    "votemute_engine.py",
    "combat_moderation_engine.py",
    "ttt_engine.py",
    "dice_duel_engine.py",
    "russian_roulette_pvp.py",
    "market_engine.py",
    "bank_engine.py",
    "auction_engine.py",
    "criminal_syndicate_engine.py",
    "heist_and_loan_engine.py",
    "handlers/message_router.py",
]

UI_SOURCE_FILES = INCLUDED_ROUTER_FILES + [
    "achievements_engine.py",
    "casino_engine.py",
    "wardrobe_engine.py",
    "lootbox_engine.py",
    "whale_economy_engine.py",
]


def _extract_str_pattern(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return ("const", node.value, node.value)
    if isinstance(node, ast.JoinedStr):
        parts = []
        regex_parts = []
        for val in node.values:
            if isinstance(val, ast.Constant) and isinstance(val.value, str):
                parts.append(val.value)
                regex_parts.append(re.escape(val.value))
            else:
                parts.append("{}")
                regex_parts.append(".*")
        return ("fstr", "".join(parts), "^" + "".join(regex_parts) + "$")
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _extract_str_pattern(node.left)
        right = _extract_str_pattern(node.right)
        return ("binop", left[1] + right[1], "^" + left[2].strip("^$") + right[2].strip("^$") + "$")
    return ("expr", ast.unparse(node), ".*")


def _build_cb_matcher(dec_src: str):
    exact_matches = re.findall(r"F\.data\s*==\s*['\"]([^'\"]+)['\"]", dec_src)
    starts_matches = re.findall(r"F\.data\.startswith\(\s*['\"]([^'\"]+)['\"]\s*\)", dec_src)
    in_matches = []
    for m in re.finditer(r"F\.data\.in_\(\s*[\[\(\{]([^\]\)\}]+)[\]\)\}]\s*\)", dec_src):
        in_matches.extend(re.findall(r"['\"]([^'\"]+)['\"]", m.group(1)))
    regex_matches = re.findall(r"F\.data\.regexp\(\s*r?['\"]([^'\"]+)['\"]", dec_src)
    startswith_tuple = []
    for m in re.finditer(r"F\.data\.startswith\(\s*\(([^\)]+)\)\s*\)", dec_src):
        startswith_tuple.extend(re.findall(r"['\"]([^'\"]+)['\"]", m.group(1)))
    contains_matches = re.findall(r"F\.data\.contains\(\s*['\"]([^'\"]+)['\"]\s*\)", dec_src)
    has_fdata = "F.data" in dec_src

    def matches(sample: str, kind: str) -> bool:
        if not has_fdata:
            return False
        for ex in exact_matches + in_matches:
            if kind == "const":
                if sample == ex:
                    return True
            else:
                if re.match(sample, ex):
                    return True
        for pref in starts_matches + startswith_tuple:
            if sample.startswith(pref):
                return True
        for rx in regex_matches:
            if re.search(rx, sample.replace("{}", "123")):
                return True
        for sub in contains_matches:
            if sub in sample:
                return True
        return False

    return matches, exact_matches + in_matches + starts_matches + startswith_tuple


def _parse_cmd_names(dec_node):
    cmds = []
    for arg in getattr(dec_node, "args", []):
        for sub in ast.walk(arg):
            if isinstance(sub, ast.Call):
                fn = ast.unparse(sub.func)
                if fn == "Command" or fn.endswith(".Command"):
                    for a in sub.args:
                        if isinstance(a, ast.Constant) and isinstance(a.value, str):
                            cmds.append(a.value.lower())
    return cmds


def test_all_generated_callbacks_have_live_handlers():
    """AST census: zero orphaned callback_data across main.py and all included routers/engines."""
    generated = []
    cb_handlers = []
    registered_cmds = set()

    for rel in UI_SOURCE_FILES:
        p = ROOT / rel
        if not p.exists():
            continue
        tree = ast.parse(p.read_text(encoding="utf-8", errors="replace"), filename=str(p))
        is_router = rel in INCLUDED_ROUTER_FILES
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                for kw in node.keywords:
                    if kw.arg == "callback_data":
                        kind, val, rx = _extract_str_pattern(kw.value)
                        generated.append((rel, node.lineno, kind, val, rx))
            if is_router and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name == "handle_unknown_command_spam":
                    continue
                for dec in node.decorator_list:
                    dec_src = ast.unparse(dec)
                    if "callback_query" in dec_src:
                        cb_handlers.append((rel, node.name, dec_src))
                    if ".message(" in dec_src or "Command(" in dec_src:
                        registered_cmds.update(_parse_cmd_names(dec))

    matchers = [(_build_cb_matcher(dec_src), rel, fn) for rel, fn, dec_src in cb_handlers]
    orphans = []
    for rel, line, kind, val, rx in generated:
        if kind == "expr":
            continue
        matched = False
        for (fn_match, literals), _, _ in matchers:
            if kind == "const":
                if fn_match(val, "const"):
                    matched = True
                    break
            else:
                if fn_match(val, "fstr") or fn_match(rx, "fstr"):
                    matched = True
                    break
                if val.startswith("{}") and any(re.match(rx, lit) for lit in literals):
                    matched = True
                    break
        if not matched:
            orphans.append(f"{rel}:{line} [{kind}] {val}")

    assert orphans == [], f"Orphaned callbacks found: {orphans}"
    for required_cmd in ("start", "help", "me", "shop", "casino", "achievements", "anon", "isolation", "tag", "getid", "admin"):
        assert required_cmd in registered_cmds, f"Command /{required_cmd} not registered in active routers"


@pytest.mark.asyncio
async def test_anime_timeout_bounds_and_early_partial_delivery():
    """
    Verify /anime uses fast per-image timeouts (<=8s, not 35s) and delivers
    ready items (e.g. 8-9 of 10) early without blocking on dead/slow hosts.
    """
    import main

    assert main.ANIME_DOWNLOAD_TIMEOUT_SEC <= 8.0
    assert main.ANIME_DOWNLOAD_TOTAL_SEC <= 14.0
    assert main.ANIME_DOWNLOAD_PARALLEL >= 5

    async def make_fetcher(idx: int):
        return f"https://example.com/art_{idx}.jpg"

    fetchers = [lambda i=i: make_fetcher(i) for i in range(10)]

    # 8 items succeed immediately; slots 3 and 7 fail/timeout
    async def mock_bounded_downloads(urls, board_id, user_id, source):
        res = []
        for idx, url in enumerate(urls):
            if "art_3" in url or "art_7" in url:
                res.append((idx, url, None))  # timed out / failed
            else:
                res.append((idx, url, (b"\xff\xd8\xff\xe0" + url.encode("utf-8"), 200)))
        return res

    fetch_call_count = 0
    orig_fetch = main._run_bounded_anime_url_fetches

    async def tracked_fetch(tasks, board_id, user_id, source):
        nonlocal fetch_call_count
        fetch_call_count += 1
        return await orig_fetch(tasks, board_id, user_id, source)

    t0 = time.monotonic()
    with patch("main._run_bounded_anime_url_fetches", side_effect=tracked_fetch), \
         patch("main._run_bounded_anime_downloads", side_effect=mock_bounded_downloads), \
         patch("japanese_translator.record_served_image"):
        collected = await main._collect_stacked_anime_downloads(fetchers, "sex", 7414244332, "command")
    elapsed = time.monotonic() - t0

    assert len(collected) == 8
    assert fetch_call_count == 1, "Should early-return 8/10 after round 0 failure instead of looping refill rounds"
    assert elapsed < 2.0


@pytest.mark.asyncio
async def test_quick_menu_anime_tuple_unpacking_fixed():
    """Quick menu hent/loli buttons no longer fail due to tuple unpacking bug."""
    import main

    cb = MagicMock()
    cb.from_user = SimpleNamespace(id=123456)
    cb.bot = AsyncMock()
    cb.message = MagicMock()
    cb.message.chat = SimpleNamespace(id=123456)
    search_msg = AsyncMock()
    cb.message.answer = AsyncMock(return_value=search_msg)
    cb.answer = AsyncMock()

    main.board_data.setdefault("b", {
        "users": {"active": set(), "banned": set()},
        "mutes": {},
        "shadow_mutes": {},
        "user_settings": {},
    })
    main.user_hourly_image_count[123456] = 0
    main.user_hourly_image_reset[123456] = time.time()

    fake_downloads = [(b"\xff\xd8\xff\xe0img1", "photo", "jpg")]
    with patch("main._collect_stacked_anime_downloads", new=AsyncMock(return_value=fake_downloads)), \
         patch("main.process_new_post", new=AsyncMock(return_value=999)) as mock_post:
        await main._handle_quick_menu_anime(cb, "b", "hent", "ru")

    mock_post.assert_awaited_once()
    search_msg.delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_start_group_dm_forbidden_fallback_and_zero_pii(isolated_test_db):
    """
    1. /start in a group when DM is blocked guides user with a deep-link button instead of silent failure.
    2. /anon and /getid without reply never expose raw Telegram user_id.
    3. build_achievements_content fits within 1024 chars and has menu_main back button.
    """
    import main
    import achievements_engine
    from aiogram.exceptions import TelegramForbiddenError

    uid = 998877665
    main.board_data.setdefault("b", {
        "users": {"active": {uid}, "banned": set()},
        "mutes": {},
        "shadow_mutes": {},
        "user_settings": {},
    })

    # 1. /start in group with DM blocked
    msg = MagicMock()
    msg.from_user = SimpleNamespace(id=uid, username="secret_user", first_name="Secret")
    msg.chat = SimpleNamespace(id=-100123456, type="supergroup")
    msg.text = "/start"
    msg.caption = None
    msg.bot = AsyncMock()
    msg.bot.get_me = AsyncMock(return_value=SimpleNamespace(username="test_tgach_bot"))
    msg.answer = AsyncMock(return_value=AsyncMock())
    msg.delete = AsyncMock()
    state = AsyncMock()

    with patch("banner_manager.send_banner_message", new=AsyncMock(side_effect=TelegramForbiddenError(method=MagicMock(), message="Forbidden"))), \
         patch("main.get_pool", new=AsyncMock(return_value=isolated_test_db)):
        await main.cmd_start(msg, state=state, board_id="b", stream="ru")

    msg.answer.assert_awaited_once()
    hint_text = msg.answer.call_args[0][0]
    hint_kb = msg.answer.call_args[1]["reply_markup"]
    assert "t.me/" in hint_kb.inline_keyboard[0][0].url
    assert str(uid) not in hint_text

    # 2. /getid without reply -> Zero PII
    getid_msg = MagicMock()
    getid_msg.from_user = SimpleNamespace(id=uid)
    getid_msg.reply_to_message = None
    getid_msg.answer = AsyncMock()
    await main.cmd_get_file_id(getid_msg, stream="ru")
    getid_msg.answer.assert_awaited_once()
    getid_out = getid_msg.answer.call_args[0][0]
    assert str(uid) not in getid_out
    assert "Анон-ID" in getid_out

    # 3. /anon -> Zero PII + menu_main back button
    anon_msg = MagicMock()
    anon_msg.from_user = SimpleNamespace(id=uid)
    anon_msg.chat = SimpleNamespace(id=uid)
    anon_msg.answer = AsyncMock()
    with patch("main.get_pool", new=AsyncMock(return_value=isolated_test_db)), \
         patch("main.get_user_global_balance", new=AsyncMock(return_value=500.0)):
        await main.cmd_anon(anon_msg, board_id="b", stream="ru")
    anon_text = anon_msg.answer.call_args[0][0]
    anon_kb = anon_msg.answer.call_args[1]["reply_markup"]
    anon_cbs = [b.callback_data for row in anon_kb.inline_keyboard for b in row]
    assert str(uid) not in anon_text
    assert "menu_main" in anon_cbs

    # 4. achievements_engine -> <= 1024 chars & menu_main back button
    ach_text, ach_kb = achievements_engine.build_achievements_content(uid, {"unlocked_achievements": ["ach_first_work", "ach_work_10"]})
    assert len(ach_text) <= 1024
    assert str(uid) not in ach_text
    ach_cbs = [b.callback_data for row in ach_kb.inline_keyboard for b in row]
    assert "menu_main" in ach_cbs
    assert "shop_main_hub" in ach_cbs


@pytest.mark.asyncio
async def test_ai_manager_and_roast_strip_think_tags_and_typing():
    """
    1. parse_cyberchad_response strips <think>{braces}</think> BEFORE JSON extraction.
    2. cmd_roast emits typing action, strips <think> tags, and enforces <=4096 length.
    """
    import ai_manager
    import main

    raw_with_think = (
        '<think>Internal reasoning with {"text": "leak draft"} and braces {}</think>\n'
        '```json\n{"reply": true, "thought": "ok", "text": "Иди на завод, сыч!"}\n```'
    )
    parsed = ai_manager.parse_cyberchad_response(raw_with_think)
    assert parsed["reply"] is True
    assert parsed["text"] == "Иди на завод, сыч!"
    assert "leak draft" not in parsed["text"]
    assert "<think>" not in parsed["text"]

    # Unclosed <think> tag after text
    raw_unclosed = '{"reply": true, "text": "База."} <think>truncated tail'
    parsed2 = ai_manager.parse_cyberchad_response(raw_unclosed)
    assert parsed2["reply"] is True
    assert "truncated tail" not in parsed2["text"]

    # cmd_roast typing + <think> stripping
    now = time.time()
    main.board_data["b"] = {
        "last_roast_time": 0,
        "users": {"active": set(), "banned": set()},
        "mutes": {},
        "shadow_mutes": {},
    }
    with patch("main.messages_storage", {
        i: {"board_id": "b", "timestamp": now - 10, "content": {"text": f"msg {i}"}}
        for i in range(1, 8)
    }):
        msg = MagicMock()
        msg.from_user = SimpleNamespace(id=55555)
        msg.chat = SimpleNamespace(id=-100999)
        msg.bot = AsyncMock()
        msg.bot.send_chat_action = AsyncMock()
        proc_msg = AsyncMock()
        msg.reply = AsyncMock(return_value=proc_msg)

        llm_out = "<think>secret cot</think><b>Вы все раки</b> " + ("А" * 4500)
        with patch("main.summarize_text_with_hf", new=AsyncMock(return_value=llm_out)):
            await main.cmd_roast(msg, board_id="b", stream="ru")

        msg.bot.send_chat_action.assert_awaited_once_with(chat_id=-100999, action="typing")
        edited_text = proc_msg.edit_text.call_args[0][0]
        assert "secret cot" not in edited_text
        assert "<think>" not in edited_text
        assert len(edited_text) <= 4096
