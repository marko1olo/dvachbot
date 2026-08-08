# Handoff Report — explorer_files_proxy

## 1. Observation

### A. Test Execution & Verbatim Error Output
- **Command**: `.\venv\Scripts\python.exe scratch/pw_multiangle_test.py`
- **Result**: FAILED (Exit Code 1)
- **Verbatim Error Output** (from `challenger_ui_v3_1/handoff.md` & `reviewer_ui_v3_2/handoff.md`):
```text
[Request Failed] GET https://api.telegram.org/file/bot8102947050:AAGfpqG6Yh99LR4f7C9Jwb_-DX2lKegBAfY/videos/file_36230 -> net::ERR_ABORTED
[Request Failed] GET https://api.telegram.org/file/bot8102947050:AAGfpqG6Yh99LR4f7C9Jwb_-DX2lKegBAfY/videos/file_36230 -> net::ERR_ABORTED
[Request Failed] GET https://api.telegram.org/file/bot8362632343:AAHLy9UcI568NBjH781p9x7hpAtGlM0rEPE/videos/file_5425 -> net::ERR_ABORTED
[Request Failed] GET https://api.telegram.org/file/bot8349694847:AAFc4Lkykk-qoJaZ6Ry0agqQqBlRAaBCok8/documents/file_7779 -> net::ERR_ABORTED
[Request Failed] GET https://api.telegram.org/file/bot8342803724:AAGksIDLbPxzOn9XhcS5cG5KF9W88K5ibMY/videos/file_5898 -> net::ERR_ABORTED
[Request Failed] GET https://api.telegram.org/file/bot8384397544:AAHqtHb8phgZLHjByUSj_AyNFT7FSnBBcxM/videos/file_145185 -> net::ERR_ABORTED
Traceback (most recent call last):
  File "C:\Users\danat\Desktop\dvachbot\scratch\pw_multiangle_test.py", line 249, in <module>
    main()
  File "C:\Users\danat\Desktop\dvachbot\scratch\pw_multiangle_test.py", line 131, in main
    assert img_info["complete"], f"Catalog image element not complete: {src}"
AssertionError: Catalog image element not complete: http://127.0.0.1:8000/files/AAMCAgADIQYABK9AXMoAAvf_aW4WLQTnl1auvAfcDkrMrJBvdLsAAuyVAAKagHFL5MuW-sFIYzQBAAdtAAM4BA
```

### B. Code Inspection Findings in `site_tgach/main.py`
1. **Direct 307 Redirects to Telegram API in `get_telegram_file`** (`site_tgach/main.py:10593-10611`):
```python
    # 1. Telegram Direct — ПРИОРИТЕТ №1 (Если путь закеширован)
    if "telegram" not in skipped_types:
        info = await get_cached_file_path(file_id, allow_protected_tokens=True)
        if info:
            path, token = info
            return RedirectResponse(
                url=f"https://api.telegram.org/file/bot{token}/{path}",
                status_code=307,
                headers={"Cache-Control": "public, max-age=3600", "Access-Control-Allow-Origin": "*"},
            )

    # 3. Shadow Telegram (Прямой редирект для теневого файла с защищенными токенами)
    if shadow_file_id and "telegram" not in skipped_types:
        info_shadow = await get_cached_file_path(shadow_file_id, allow_protected_tokens=True)
        if info_shadow:
            path, token = info_shadow
            return RedirectResponse(
                url=f"https://api.telegram.org/file/bot{token}/{path}",
                status_code=307,
                headers={"Cache-Control": "public, max-age=3600", "Access-Control-Allow-Origin": "*"},
            )
```

2. **Existing Unused Server-Side Proxy Helper** (`site_tgach/main.py:10248-10336`):
`_proxy_protected_telegram_file(file_id, file_path, token, filename, request)` is already implemented in `main.py`. It uses a shared `aiohttp` session to fetch raw file bytes from `https://api.telegram.org/file/bot{token}/{file_path}` on the server side and streams them back via `StreamingResponse` with `Access-Control-Allow-Origin: *` and proper `Content-Type`. However, `get_telegram_file` was NOT calling it!

3. **Duplicate Override Route Definition** (`site_tgach/main.py:11040-11070`):
```python
@app.get("/files/{file_id:path}")
async def serve_telegram_file_dev(file_id: str):
    ...
    url = f"https://api.telegram.org/file/bot{bot_token}/{file_path}"
    return RedirectResponse(url)
```
A secondary `@app.get("/files/{file_id:path}")` route handler is declared at the bottom of `site_tgach/main.py`. It also returns `RedirectResponse` targeting `api.telegram.org`.

---

## 2. Logic Chain

1. **Root Cause of `net::ERR_ABORTED`**:
   - Web browser loads `<img src="http://127.0.0.1:8000/files/{file_id}">`.
   - FastAPI server matches `/files/{file_id}` and executes `get_telegram_file()` or `serve_telegram_file_dev()`.
   - When cached Telegram path info is present, the handler returns `307 Temporary Redirect` with `Location: https://api.telegram.org/file/bot{token}/{path}`.
   - Headless Chromium follows the 307 redirect and sends an HTTP GET directly to `api.telegram.org`.
   - In Chromium headless test environments (and restricted client networks), client-side requests to `api.telegram.org` fail due to network restrictions, lack of Telegram API access, or connection resets, resulting in `net::ERR_ABORTED`.
   - Because the HTTP request to `api.telegram.org` fails, the browser cannot load or decode the image bytes.
   - The DOM `<img>` element remains in an incomplete state (`img.complete == False`, `img.naturalWidth == 0`).
   - Playwright E2E assertion `assert img_info["complete"]` fails with `AssertionError`.

2. **Security & Protocol Vulnerability**:
   - Returning HTTP 307 redirects to `https://api.telegram.org/file/bot{token}/{path}` exposes sensitive Telegram Bot API tokens to client browser network traffic.

3. **Remediation Rationale**:
   - Proxying/streaming the file bytes directly from Telegram API via server-side `aiohttp` using `_proxy_protected_telegram_file` avoids client-side 307 redirects entirely.
   - The client browser receives HTTP 200 OK directly from `http://127.0.0.1:8000/files/...` with correct `Content-Type` (e.g., `image/jpeg`, `image/png`, `video/mp4`) and CORS headers.
   - Bot tokens remain hidden on the server.
   - If Telegram API is unreachable or fetch fails, a fallback handler returns an image fallback or clean 404, preventing test hangs or unhandled client errors.

---

## 3. Caveats

- Unit tests in `tests/test_files_endpoint.py` mock `get_cached_file_path` returning `None` by default and test R2 mirror redirects. Any unit test that expects 307 redirect specifically for Telegram will need to be updated to assert 200 OK streaming response.
- Telegram Bot API file URLs (`/file/bot<token>/<path>`) expire after ~1 hour. Server-side proxying automatically handles this as long as `get_cached_file_path` refreshes expired paths.

---

## 4. Conclusion

- **Verdict**: Immediate fix required in `site_tgach/main.py`.
- **Actionable Remediation**: Replace 307 redirects to `api.telegram.org` in `get_telegram_file()` with server-side streaming calls to `_proxy_protected_telegram_file()`, eliminate duplicate `serve_telegram_file_dev()` route at line 11040, and ensure fallback MIME typing.

---

## 5. Verification Method

1. Run unit test suite:
   ```powershell
   .\venv\Scripts\python.exe -m pytest tests/test_files_endpoint.py
   ```
2. Run Playwright multi-angle UI verification:
   ```powershell
   .\venv\Scripts\python.exe scratch/pw_multiangle_test.py
   ```
3. Invalidation condition: Any network request to `api.telegram.org` recorded in browser network logs, or `img.complete == False` / `net::ERR_ABORTED` in Chromium.

---

## 6. Step-by-Step Instructions for `worker_files_proxy`

### Step 1: Update `site_tgach/main.py` `get_telegram_file`
In `site_tgach/main.py` (around lines 10591-10612), replace:
```python
    # 1. Telegram Direct — ПРИОРИТЕТ №1 (Если путь закеширован)
    if "telegram" not in skipped_types:
        info = await get_cached_file_path(file_id, allow_protected_tokens=True)
        if info:
            path, token = info
            try:
                return await _proxy_protected_telegram_file(file_id, path, token, filename, request)
            except HTTPException:
                logger.warning(f"Proxying Telegram file {file_id} failed, attempting next mirror")

    # 3. Shadow Telegram (Прямой редирект для теневого файла с защищенными токенами)
    if shadow_file_id and "telegram" not in skipped_types:
        info_shadow = await get_cached_file_path(shadow_file_id, allow_protected_tokens=True)
        if info_shadow:
            path, token = info_shadow
            try:
                return await _proxy_protected_telegram_file(shadow_file_id, path, token, filename, request)
            except HTTPException:
                logger.warning(f"Proxying Shadow Telegram file {shadow_file_id} failed, attempting next mirror")
```

### Step 2: Ensure Proper MIME Type Resolution in `_proxy_protected_telegram_file`
In `site_tgach/main.py` (around lines 10286-10290), enhance guessed MIME type fallback:
```python
        guessed_type = mimetypes.guess_type(filename or file_path)[0]
        media_type = resp.headers.get("Content-Type")
        if not media_type or media_type == "application/octet-stream":
            if file_id.startswith("AgAC") or file_path.endswith((".jpg", ".jpeg")):
                guessed_type = "image/jpeg"
            elif file_path.endswith(".png"):
                guessed_type = "image/png"
            elif file_path.endswith(".mp4"):
                guessed_type = "video/mp4"
            media_type = guessed_type or media_type or "image/jpeg"
```

### Step 3: Remove Duplicate Route at Line 11040
In `site_tgach/main.py`, remove or comment out `serve_telegram_file_dev` (`lines 11040-11070`), which overrides `/files/{file_id:path}` with legacy 307 redirects to `api.telegram.org`.

### Step 4: Execute & Verify
Run `.\venv\Scripts\python.exe -m pytest tests/test_files_endpoint.py` and `.\venv\Scripts\python.exe scratch/pw_multiangle_test.py`. Confirm Exit Code 0 and zero `net::ERR_ABORTED` errors.
