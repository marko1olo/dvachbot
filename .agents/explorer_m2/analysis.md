# Comprehensive Audit Report: `format_header` Definition and Imports (Requirement R2)

**Target Project**: `dvachbot` (`C:\Users\danat\Desktop\dvachbot`)  
**Auditor**: format_header Explorer (`.agents/explorer_m2`)  
**Date**: 2026-08-08  
**Audit Status**: **VERIFIED / PASS** — `format_header` is properly defined and imported across all active codebase modules. No `NameError` triggers exist.

---

## 1. Executive Summary

Requirement R2 requires an audit of `user_manager.py` (specifically `cmd_anime` and related command functions), `main.py`, and any associated formatting/utility modules to ensure that `format_header` is properly defined and imported. The objective is to guarantee that commands executed in generic or specialized modes do not throw a `NameError`.

### Key Findings:
1. **Canonical Definition**: `format_header` is defined in `post_helpers.py` at line 137 (`async def format_header(board_id: str, post_num: int, author_id: int = 0, stream: str = 'ru') -> str`).
2. **`user_manager.py` Status**: Properly imports `format_header` via explicit import `from post_helpers import format_header` at line 20 (as well as wildcard import `from post_helpers import *` at line 7). All command functions in `user_manager.py` (`cmd_anime` at line 815, `cmd_deanon` at line 1272, `cmd_zaputin` at line 1363, `cmd_suka_blyat` at line 1470) have full access to `format_header`.
3. **`main.py` Status**: Properly imports `format_header` via `from post_helpers import apply_shadow_autoreplace, _format_header_inner, format_header` at line 34. All 28 references to `format_header` in `main.py` (including generic mode commands `cmd_gopnik`, `cmd_kurwa`, `cmd_schizo`, `cmd_slavaukraine`, `cmd_wh40k`, `cmd_yer`, `cmd_summarize`, and admin/system tasks) execute without `NameError`.
4. **Codebase-Wide Verification**: All 10 production runtime modules referencing `format_header` (`post_helpers.py`, `user_manager.py`, `main.py`, `admin_manager.py`, `ai_manager.py`, `bot_helpers.py`, `delivery_manager.py`, `post_processor.py`, `stats_manager.py`, `handlers/message_router.py`) correctly import or define `format_header`.
5. **No Undefined References**: Zero active runtime modules contain unbound references to `format_header`.

---

## 2. Primary Definition & Implementation

### Location: `post_helpers.py` (Lines 137–166)

```python
async def format_header(board_id: str, post_num: int, author_id: int = 0, stream: str = 'ru') -> str:
    """
    Форматирование заголовка с поддержкой VIP префиксов из Теневого Магазина.
    """
    custom_prefix = ""
    if author_id > 0:
        from common.db_pool import get_pool
        import time
        import json
        db = await get_pool()
        has_poop = False
        prefix_str = ""
        async with db.execute("SELECT active_items, custom_prefix, prefix_expires_at FROM Users WHERE user_id = ?", (author_id,)) as c:
            async for row in c:
                if row[0]:
                    try:
                        items = json.loads(row[0])
                        if items.get("shit_until", 0) > int(time.time()):
                            has_poop = True
                    except Exception:
                        import traceback; traceback.print_exc()
                if row[1] and row[2] and int(time.time()) < row[2]:
                    prefix_str = f"<b>{row[1]}</b> "
        if has_poop:
            custom_prefix = "💩 " + prefix_str
        else:
            custom_prefix = prefix_str
                    
    res = await _format_header_inner(board_id, post_num, stream)
    return custom_prefix + res
```

### Delegation:
`format_header` calls `_format_header_inner(board_id, post_num, stream)` defined at line 561 of `post_helpers.py`, which formats post numbers according to stream localization (`ru`, `en`, `jp`).

---

## 3. Module-by-Module Audit

### A. `user_manager.py`
- **Imports**:
  - Line 7: `from post_helpers import *`
  - Line 20: `from post_helpers import format_header`
- **Usages**:
  - Line 815 (`cmd_anime`): `header = await format_header(board_id, pnum)`
  - Line 1272 (`cmd_deanon`): `header_text = await format_header(board_id, pnum)`
  - Line 1363 (`cmd_zaputin`): `header = await format_header(board_id, pnum)`
  - Line 1470 (`cmd_suka_blyat`): `header = await format_header(board_id, pnum)`
- **Verdict**: **SAFE**. `format_header` is explicitly imported. `cmd_anime` and all related commands execute without `NameError`.

### B. `main.py`
- **Imports**:
  - Line 34: `from post_helpers import apply_shadow_autoreplace, _format_header_inner, format_header`
- **Usages** (28 references across command handlers and background tasks):
  - Line 2013 (`board_statistics_broadcaster`): `header = await format_header(board_id, post_num, stream=stream)`
  - Line 2665 (`send_moderation_notice`): `header = await format_header(board_id, post_num)`
  - Line 5608 (`cmd_admin_answer`): `header = await format_header(board_id, pnum, 0)`
  - Line 5896 (`_send_motivation_message`): `header = await format_header(board_id, post_num)`
  - Line 6095 (`dvach_thread_poster`): `header = await format_header(destination_board_id, post_num)`
  - Line 7723 (`cmd_summarize`): `header_text = await format_header(board_id, pnum)`
  - Line 8298 (`cmd_slavaukraine`): `header = await format_header(board_id, pnum)`
  - Line 8349 (`cmd_gopnik`): `header = await format_header(board_id, pnum)`
  - Line 8394 (`cmd_schizo`): `header = await format_header(board_id, pnum)`
  - Line 8454 (`activate_lightweight_mode`): `header = await format_header(board_id, pnum)`
  - Line 8589 (`disable_mode_after_delay`): `header = await format_header(board_id, pnum)`
  - Line 8630 (`cmd_kurwa`): `header = await format_header(board_id, pnum)`
  - Line 8671 (`cmd_wh40k`): `header = await format_header(board_id, pnum)`
  - Line 8712 (`cmd_yer`): `header = await format_header(board_id, pnum)`
  - Line 8752 (`_trigger_generic_mode`): `header = await format_header(board_id, pnum)`
  - Line 9532 (`_notify_new_thread_public`): `header = await format_header(board_id, pnum_notify)`
  - Line 10290/10293 (`thread_lifecycle_manager`): `header = await format_header(board_id, pnum)`
  - Line 12030 (`cmd_anime`): `header = await format_header(board_id, pnum)`
  - Line 12617 (`create_and_send_deanon_post`): `header_text = await format_header(board_id, pnum)`
  - Line 12707 (`cmd_zaputin`): `header = await format_header(board_id, pnum)`
  - Line 12812 (`cmd_suka_blyat`): `header = await format_header(board_id, pnum)`
  - Line 12880 (`cmd_admin_say`): `header = await format_header(board_id, pnum, 0)`
  - Line 15115 (`periodic_board_summary`): `header_base = await format_header(board_id, pnum)`
  - Line 15171 (`periodic_thread_digest`): `header_base = await format_header(board_id, pnum)`
  - Line 15225 (`periodic_newspaper_broadcast`): `header_base = await format_header(board_id, pnum)`
  - Line 15280 (`periodic_shop_broadcast`): `header_base = await format_header(board_id, pnum)`
  - Line 16624 (`schedule_persona_reply`): `header = await format_header(board_id, pnum, 0)`
- **Verdict**: **SAFE**. `format_header` is explicitly imported. All generic mode commands (`cmd_gopnik`, `cmd_kurwa`, `cmd_schizo`, `cmd_slavaukraine`, `cmd_wh40k`, `cmd_yer`, `_trigger_generic_mode`) execute safely.

### C. Other Production Modules
1. `admin_manager.py`: Line 6 has `from post_helpers import *`. Line 71 uses `format_header(board_id, pnum, 0)`. **SAFE**.
2. `ai_manager.py`: Line 25 explicitly imports `format_header`. Lines 522, 1154, 1211, 1254 use `format_header`. **SAFE**.
3. `bot_helpers.py`: Line 11 explicitly imports `format_header`. **SAFE**.
4. `delivery_manager.py`: Line 11 explicitly imports `format_header`. Lines 1165, 1523, 1563 use `format_header`. **SAFE**.
5. `post_processor.py`: Line 27 explicitly imports `format_header`. Line 232 uses `format_header`. **SAFE**.
6. `stats_manager.py`: Line 32 explicitly imports `format_header`. Line 277 uses `format_header`. **SAFE**.
7. `handlers/message_router.py`: Line 36 explicitly imports `format_header`. Line 858 uses `format_header`. **SAFE**.
8. `witching_hour.py`: Line 127 invokes `_main.format_header(...)` where `_main` is the imported `main` module (which exports `format_header`). **SAFE**.
9. `conan.py`: Line 112 receives `format_header` as a positional parameter (`async def conan_roaster(..., format_header, ...)`). Line 150 invokes `format_header`. **SAFE**.

---

## 4. AST Static Analysis Summary

An automated AST scan was performed across all 191 Python files in the repository.

| Module | References to `format_header` | Import / Def Status | Result |
| :--- | :---: | :--- | :--- |
| `post_helpers.py` | 1 | DEFINED (L137) | PASS |
| `user_manager.py` | 4 | IMPORTED (L20) | PASS |
| `main.py` | 28 | IMPORTED (L34) | PASS |
| `admin_manager.py` | 1 | STAR_IMPORTED (L6) | PASS |
| `ai_manager.py` | 4 | IMPORTED (L25) | PASS |
| `bot_helpers.py` | 5 | IMPORTED (L11) | PASS |
| `delivery_manager.py` | 4 | IMPORTED (L11) | PASS |
| `post_processor.py` | 1 | IMPORTED (L27) | PASS |
| `stats_manager.py` | 1 | IMPORTED (L32) | PASS |
| `handlers/message_router.py` | 1 | IMPORTED (L36) | PASS |
| `witching_hour.py` | 1 | MODULE_ATTR (`_main.format_header`) | PASS |
| `conan.py` | 1 | PARAMETER (`format_header`) | PASS |

*Note on Scratch Files*: Files under `scratch/funcs_new/` and `scratch/funcs_old/` are non-executable standalone code snippets stored in scratch workspace directories. They are not active runtime entry points. When assembled into production files (`user_manager.py` or `main.py`), the host module provides the required import.

---

## 5. Conclusion

Requirement R2 is **FULLY SATISFIED**. The definition of `format_header` in `post_helpers.py` and its explicit imports in `user_manager.py` and `main.py` guarantee that both generic mode commands (`cmd_gopnik`, `cmd_kurwa`, `cmd_schizo`, `cmd_slavaukraine`, `cmd_wh40k`, `cmd_yer`) and specialized mode commands (`cmd_anime`, `cmd_zaputin`, `cmd_suka_blyat`, `cmd_deanon`) function correctly without throwing `NameError`.
