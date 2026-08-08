# Requirement R1 Audit: Telegram File Endpoint Proxy Reversion Analysis

## Executive Summary
This audit inspects `site_tgach/main.py` to evaluate Requirement R1: "Verify Telegram file endpoints (e.g. `/files/`) use HTTP 307 redirects directly to `api.telegram.org` instead of streaming content through the server."

**Verdict**: **PASSED / VERIFIED**.
`site_tgach/main.py` correctly handles `/files/` and related Telegram file routes by issuing **HTTP 307 RedirectResponse** pointing directly to `https://api.telegram.org/file/bot{token}/{path}`. Content streaming through the server for Telegram files has been completely bypassed in favor of direct 307 redirects.

---

## Detailed Findings

### 1. Endpoint Routes & Decorators
In `site_tgach/main.py` (lines 10464–10471), `get_telegram_file` serves all Telegram file requests:
```python
@app.api_route("/files/{file_id:path}", methods=["GET", "HEAD"])
@app.api_route("/file/{file_id:path}", methods=["GET", "HEAD"])
@app.api_route("/thumb/{file_id:path}", methods=["GET", "HEAD"])
@app.api_route("/i/{file_id:path}", methods=["GET", "HEAD"])
@app.api_route("/preview/{file_id:path}", methods=["GET", "HEAD"])
@app.api_route("/{board_id}/src/{file_id:path}", methods=["GET", "HEAD"])
@app.api_route("/{board_id}/thumb/{file_id:path}", methods=["GET", "HEAD"])
async def get_telegram_file(
    file_id: str, request: Request, filename: str = None, skip: str = None, board_id: str = None
):
```
Legacy duplicate handlers (such as `serve_telegram_file_dev`) have been removed (documented at line 11052).

---

### 2. Verification of HTTP 307 Redirect vs. Streaming
When serving a Telegram file, `get_telegram_file` checks for Telegram cached path info via `get_cached_file_path`:

#### Primary Telegram Direct (Lines 10602–10611):
```python
    if "telegram" not in skipped_types:
        info = await get_cached_file_path(file_id, allow_protected_tokens=True)
        if info:
            path, token = info
            return RedirectResponse(
                url=f"https://api.telegram.org/file/bot{token}/{path}",
                status_code=307,
                headers={"Cache-Control": "public, max-age=86400", "Access-Control-Allow-Origin": "*"}
            )
```

#### Shadow Telegram Fallback (Lines 10614–10623):
```python
    if shadow_file_id and "telegram" not in skipped_types:
        info_shadow = await get_cached_file_path(shadow_file_id, allow_protected_tokens=True)
        if info_shadow:
            path, token = info_shadow
            return RedirectResponse(
                url=f"https://api.telegram.org/file/bot{token}/{path}",
                status_code=307,
                headers={"Cache-Control": "public, max-age=86400", "Access-Control-Allow-Origin": "*"}
            )
```

#### Inactive Streaming Helper:
The streaming helper function `_proxy_protected_telegram_file` (defined at line 10248) is **not invoked** anywhere within `get_telegram_file`. All active code paths return a 307 `RedirectResponse`.

---

### 3. URL, Token & Path Construction Verification
1. **File ID Sanitization**:
   - `file_id = file_id.lstrip("/")`
   - If `file_id` contains `/`, it extracts `file_id, path_filename = file_id.split("/", 1)`.
2. **Token & Path Lookup (`get_cached_file_path`)**:
   - Checks Redis/FastAPI cache `fpath:{file_id}`.
   - If missing, queries `get_file_owner_id(file_id)` from database and requests `_fetch_telegram_path(file_id, owner_token)` via Telegram `getFile` API (`https://api.telegram.org/bot{bot_token}/getFile?file_id={file_id}`).
   - If owner fails, probes main bot and known bot pool tokens.
   - Caches discovered `f"{path}|{bot_id}"` for 1 hour.
3. **URL formatting**:
   - `url = f"https://api.telegram.org/file/bot{token}/{path}"`
   - Exact Telegram standard endpoint format.

---

### 4. Syntax & Integrity Checks
- **Python Syntax**: Verified with `python -m py_compile site_tgach/main.py`. Returned exit code `0` (no syntax errors).
- **Error Handling**: Non-existent or permanently failed files raise `HTTPException(status_code=404, detail=...)`. Dead file negative caching prevents repeated failing lookups.

---

## Conclusion
`site_tgach/main.py` is compliant with Requirement R1. All Telegram file requests issue direct HTTP 307 redirects to `api.telegram.org`.
