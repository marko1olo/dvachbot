# Handoff Report — explorer_media_1

## 1. Observation
- **Root Telegram Bot (`C:\Users\danat\Desktop\dvachbot\main.py`):** Verified to contain 0 web/HTTP route definitions. Web server is completely self-contained in `site_tgach\main.py`.
- **FastAPI Endpoint Inventory (`site_tgach\main.py`):**
  - Line 10313: `@app.api_route("/files/{file_id:path}", methods=["GET", "HEAD"])` -> `async def get_telegram_file(...)`
  - Line 5614: `@app.get("/img/random")` -> `async def random_image_page(...)`
  - Line 5630: `@app.get("/api/img/next")` -> `async def api_random_image_next(...)`
  - Line 8741 / Line 5570: `@app.get("/tv/random")` & `@app.get("/roulette")` -> `async def roulette_page(...)`
  - Line 8757: `@app.get("/api/tv/next")` -> `async def api_roulette_next(...)`
  - Line 5549: `@app.get("/api/media-feed/{board_id}")` -> `async def api_get_media_feed(...)`
  - Line 9133: `@app.get("/api/voice/{file_id:path}/transcribe")` -> `async def api_transcribe_voice(...)`
  - Line 2263: `app.mount("/static", StaticFiles(...), name="static")`
- **Missing Compatibility Routes:**
  - Automated regex search across all `.py` files in `site_tgach\` returned **0 matches** for path patterns `@app...("/file/`, `@app...("/thumb/`, `@app...("/i/`, `@app...("/preview/`, `@app...("/{board}/src/`, `@app...("/{board}/thumb/`.
- **Header Observations:**
  - Line 10337: `no_cache_headers = {"Cache-Control": "no-store, no-cache..."}` is defined but unused.
  - Lines 10163-10170 (`_proxy_protected_telegram_file`) and Lines 10238-10240 (`_proxy_external_url`): Headers set are `Accept-Ranges`, `Cache-Control: public, max-age=300`, `Content-Length`, `Content-Range`, `Last-Modified`, `ETag`. `Access-Control-Allow-Origin: *` is **absent**.
- **Error Handling & Caching Discrepancy:**
  - Line 10395: `backend.get(f"dead_file:public:{file_id}")` checks Redis for dead files.
  - Line 10511: `_mark_random_dead_file(file_id)` is called when lookups fail.
  - Line 512: `_mark_random_dead_file(file_id)` writes ONLY to local dictionary `RANDOM_DEAD_FILE_IDS[str(file_id)] = now`. It never sets Redis key `dead_file:public:{file_id}`.
- **Telegram Bot Probing:**
  - Lines 10002-10038 (`try_bot_batch` in `get_cached_file_path`): Iterates over `all_bot_tokens` in batches of 4 spawning parallel async tasks calling `_fetch_telegram_path(file_id, token)`.

---

## 2. Logic Chain
1. **From missing route search to 404 finding:**
   - Observation: FastAPI route list shows only `/files/{file_id:path}` is registered, and regex search for `/file/`, `/thumb/`, `/i/`, `/preview/`, `/src/` returned 0 decorator matches.
   - Inference: Standard 2ch imageboard endpoints (`/file/...`, `/thumb/...`, `/i/...`, `/preview/...`, `/{board}/src/...`, `/{board}/thumb/...`) are completely missing from FastAPI. Any client or scraper targeting these legacy routes receives HTTP 404.
2. **From header inspection to CORS vulnerability:**
   - Observation: Neither 307 redirect responses in `get_telegram_file` nor streaming responses in `_proxy_protected_telegram_file` / `_proxy_external_url` set `Access-Control-Allow-Origin`.
   - Inference: Cross-origin browser requests (HTML5 canvas, video element, external JS web clients) attempting to fetch media via these endpoints will be blocked by browser CORS policy.
3. **From dead file code review to caching failure:**
   - Observation: Line 10395 checks Redis key `dead_file:public:{file_id}`, but line 10511 calls `_mark_random_dead_file`, which line 512 shows only modifies local memory dict `RANDOM_DEAD_FILE_IDS`.
   - Inference: Dead files marked by worker processes are never saved to Redis. Subsequent requests in other workers or subsequent API calls hit the cache miss and re-trigger full Telegram/mirror lookups.
4. **From bot pool batch iteration to rate-limit bottleneck:**
   - Observation: `get_cached_file_path` fires parallel `getFile` requests across all bot tokens in batches of 4 when a file has no owner ID.
   - Inference: Non-existent file IDs trigger up to N parallel HTTP requests to Telegram API per 404 lookup, creating a thundering herd that risks triggering Telegram 429 FloodWait or bot token bans.

---

## 3. Caveats
- No live HTTP server was started during this read-only investigation, as per workspace constraints. All observations were derived directly from static source code analysis of `site_tgach\main.py` and project files.

---

## 4. Conclusion
The media serving architecture in `site_tgach\main.py` is functional for valid Telegram file IDs under `/files/{file_id:path}`, but contains critical compatibility gaps, header omissions, and performance bottlenecks:
1. **Broken 2ch Path Compatibility:** Legacy `/file/`, `/thumb/`, `/i/`, `/preview/`, `/{board}/src/`, and `/{board}/thumb/` paths return 404.
2. **Missing CORS Headers:** Missing `Access-Control-Allow-Origin: *` on all media responses.
3. **Dead File Redis Desync:** `_mark_random_dead_file` fails to set Redis key `dead_file:public:{file_id}`.
4. **Telegram Bot Rate-Limit Bottleneck:** Full bot pool scanning on missing owner IDs triggers API flooding.

---

## 5. Verification Method
1. **Inspect Source Locations:**
   - Check `site_tgach\main.py` at line 10313 (`get_telegram_file`) to verify absence of `/file/`, `/thumb/`, `/i/`, `/preview/` decorators.
   - Check lines 10163 and 10238 to verify missing CORS headers.
   - Check line 512 (`_mark_random_dead_file`) vs line 10395 to verify Redis key desync.
2. **Execution Test Commands (Once Server is Running):**
   - Run python script calling `http://localhost:8000/file/test.jpg` -> Verify HTTP 404.
   - Run python script calling `http://localhost:8000/files/test.jpg` -> Verify HTTP 307 / 404 flow.
