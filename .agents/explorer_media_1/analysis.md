# Comprehensive Media, Image, and Thumbnail Endpoints Audit Report

**Target Project:** `C:\Users\danat\Desktop\dvachbot`  
**Inspected Module:** `site_tgach\main.py` (FastAPI Application)  
**Date:** 2026-07-29  
**Agent:** `explorer_media_1`  

---

## 1. Executive Summary

An in-depth investigation was performed on `main.py` (root bot script) and `site_tgach\main.py` (FastAPI web server) targeting all media, image, thumbnail, and preview endpoints (`/file/...`, `/thumb/...`, `/i/...`, `/preview/...`, `/files/...`, `/api/media-feed/...`, `/img/random`, `/api/img/next`, `/api/tv/next`, `/api/voice/...`).

### Key Discoveries:
1. **Absence of Legacy 2ch Routes:** Standard media path prefixes `/file/`, `/thumb/`, `/i/`, `/preview/`, `/{board}/src/`, and `/{board}/thumb/` are **NOT registered in FastAPI**. Only `/files/{file_id:path}` exists. Direct requests to standard 2ch media endpoints return **404 Not Found**.
2. **Proxy & Mirror Architecture:** `/files/{file_id:path}` implements a multi-tier fallback cascade (Telegram Direct -> Shadow Telegram -> FreeImage -> ImgBB -> PixHost -> Catbox -> 0x0 -> Original Thumbnail Fallback).
3. **Header Deficiencies:** None of the media responses set `Access-Control-Allow-Origin: *` (CORS headers). Proxied responses use a short 5-minute `Cache-Control` TTL, and `no_cache_headers` constructed at line 10337 is never attached to any response.
4. **Bot Pool Thundering Herd Risk:** When a historical file lacks an owner ID in the database, `get_cached_file_path` probes the entire bot pool in batches of 4 via Telegram `getFile` API requests. Repeated 404 lookups risk triggering Telegram rate limits (429 Too Many Requests) or bot bans.
5. **Dead File Cache Mismatch:** `get_telegram_file` checks Redis key `dead_file:public:{file_id}`, but when a file fails all lookups, `_mark_random_dead_file(file_id)` only updates a local in-memory Python dictionary (`RANDOM_DEAD_FILE_IDS`), leaving Redis key empty.

---

## 2. Comprehensive Endpoint Inventory

| Endpoint Route | HTTP Methods | Function Name | Location (`site_tgach\main.py`) | Purpose & Handling Mechanism |
|---|---|---|---|---|
| `/files/{file_id:path}` | `GET`, `HEAD` | `get_telegram_file` | Line 10313 | Main gateway for media, thumbnails, videos, audio. Resolves Telegram path or mirror links (307 redirect or proxied streaming). |
| `/img/random` | `GET` | `random_image_page` | Line 5614 | HTML page (`random_img.jinja2`) serving random image viewer. |
| `/api/img/next` | `GET` | `api_random_image_next` | Line 5630 | API endpoint returning JSON metadata for endless image feed. |
| `/tv/random` (and `/roulette`, `/roulette/`) | `GET` | `roulette_page` | Line 8741, Line 5570 | HTML page (`roulette.jinja2`) for media roulette player. Redirects from `/roulette`. |
| `/api/tv/next` | `GET` | `api_roulette_next` | Line 8757 | API endpoint returning JSON metadata for media roulette player. |
| `/api/media-feed/{board_id}` | `GET` | `api_get_media_feed` | Line 5549 | Paginated JSON feed of media posts for a given board ID. |
| `/api/voice/{file_id:path}/transcribe` | `GET` | `api_transcribe_voice` | Line 9133 | Fetches audio file and transcribes audio via VoiceTranscriptions cache/API. |
| `/favicon.ico` | `GET` | Inline handler | Line 2243 | Serves favicon file. |
| `/apple-touch-icon.png` & `/{path:path}/apple-touch-icon.png` | `GET` | `apple_touch_icon_proxy` | Line 2248, 2249 | Serves apple touch icon file. |
| `/static` | `GET` | `StaticFiles` Mount | Line 2263 | Serves static assets from `site_tgach/static/`. |

### Missing Routes Audit:
- **`GET /file/{file_id:path}`**: ❌ NOT DEFINED (Returns 404)
- **`GET /thumb/{file_id:path}`**: ❌ NOT DEFINED (Returns 404)
- **`GET /i/{file_id:path}`**: ❌ NOT DEFINED (Returns 404)
- **`GET /preview/{file_id:path}`**: ❌ NOT DEFINED (Returns 404)
- **`GET /{board}/src/{filename}`**: ❌ NOT DEFINED (Returns 404)
- **`GET /{board}/thumb/{filename}`**: ❌ NOT DEFINED (Returns 404)

---

## 3. Media Request Pipeline & Mirror Fallback Analysis

Requests to `/files/{file_id:path}` execute the following pipeline:

```
                  Client Request: /files/{file_id:path}
                                    │
                        1. Path & Protocol Normalization
                 (Strips '/', checks http:// -> 301 Redirect)
                                    │
                         2. GeoIP & Country Detection
                         (Determines is_ru flag via IP)
                                    │
                     3. Smart Wait Polling Loop (0.5s - 7.5s)
                    (Polls Redis/DB for new file mirrors)
                                    │
                      4. Mirror Fallback Priority Order
                                    │
        ┌───────────────────────────┴───────────────────────────┐
        │                                                       │
[1. Telegram Direct] (Cached fpath)                       [2. HuggingFace] (Disabled)
 -> 307 Redirect to api.telegram.org                            │
        │                                                       │
[3. Shadow Telegram] (Protected bot token)                [3.1 FreeImage]
 -> 307 Redirect to api.telegram.org                       -> 307 Redirect
        │                                                       │
[3.2 ImgBB]                                               [3.3 PixHost]
 -> 307 Redirect                                           -> 307 Redirect
        │                                                       │
[4. Catbox]                                               [5. 0x0 (zeroxzero)]
 -> If !is_ru: 307 Redirect                                -> If !is_ru: 307 Redirect
 -> If is_ru: Proxy via _proxy_external_url                -> If is_ru: Proxy via _proxy_external_url
        │                                                       │
        └───────────────────────────┬───────────────────────────┘
                                    │
                         5. Thumbnail DB Fallback
                (If AgAC... photo, lookup original file ID)
                                    │
                     6. Dead File Mark & 404 Response
```

---

## 4. HTTP Headers Audit

### Summary of Headers Returned by Media Endpoints:

1. **Direct Redirect Responses (307 Temporary Redirect):**
   - Telegram Direct: `Cache-Control: public, max-age=3600` (1 hour)
   - Mirrors (FreeImage, ImgBB, PixHost, Catbox, 0x0): `Cache-Control: public, max-age=86400` (24 hours)
   - **Defect:** `Access-Control-Allow-Origin: *` is **MISSING**. Browsers executing cross-origin `fetch()` or video streaming fail CORS checks.

2. **Proxied Streaming Responses (`_proxy_protected_telegram_file` & `_proxy_external_url`):**
   - `Content-Type`: Derived from upstream `Content-Type` header, falling back to `mimetypes.guess_type()`, then `application/octet-stream`.
   - `Accept-Ranges`: Set to `bytes`.
   - `Cache-Control`: Set to `public, max-age=300` (5 minutes).
   - `Content-Length`, `Content-Range`, `Last-Modified`, `ETag`: Forwarded from upstream.
   - **Defect 1:** `Access-Control-Allow-Origin: *` is **MISSING**.
   - **Defect 2:** Short Cache-Control TTL (5 min) causes excessive re-fetches for static media.
   - **Defect 3:** `Content-Disposition` header is never included, losing original filename metadata on download.

3. **Unused Code Notice:**
   - At line 10337 in `get_telegram_file`:
     ```python
     no_cache_headers = {
         "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
         "Pragma": "no-cache",
         "Expires": "0",
     }
     ```
     `no_cache_headers` is defined but **NEVER used** anywhere in the function.

---

## 5. Error Handling Audit

1. **Dead File Redis vs Local Cache Discrepancy:**
   - At line 10395, `get_telegram_file` checks `backend.get(f"dead_file:public:{file_id}")`.
   - At line 10511, when lookups fail, `_mark_random_dead_file(file_id)` is invoked.
   - **Failure Mode:** `_mark_random_dead_file` only populates local in-memory dict `RANDOM_DEAD_FILE_IDS`. It **NEVER** writes `dead_file:public:{file_id}` to Redis. As a result, subsequent requests across worker processes ignore previous failures and repeat expensive lookup iterations.

2. **Telegram API Probing Thundering Herd:**
   - In `get_cached_file_path` (lines 10020-10038), if `owner_id` is missing, `try_bot_batch` iterates through ALL registered bot tokens in batches of 4, issuing parallel `getFile` requests to `https://api.telegram.org`.
   - **Failure Mode:** Invalid or expired file IDs trigger dozens of HTTP GET requests to Telegram API per missing file. This causes severe rate-limiting (HTTP 429 FloodWait) from Telegram servers.

3. **Database Timeout Resilience:**
   - Database lookups (`get_file_mirrors`, `get_file_owner_id`, `FileRegistry` query) catch general `Exception` and return fallback defaults (empty dict / None). While resilient against server crashes, database lock contention degrades performance into full bot pool scans.

---

## 6. Detailed Bug & Vulnerability Breakdown

### Bug 1: Missing `/file/`, `/thumb/`, `/i/`, `/preview/`, `/{board}/src/`, `/{board}/thumb/` Route Handlers
- **Severity:** High (Functional Defect / Broken Compatibility)
- **File & Line:** `site_tgach\main.py`
- **Description:** Only `/files/{file_id:path}` is registered. Standard 2ch imageboard media requests to `/file/`, `/thumb/`, `/i/`, `/preview/`, `/{board}/src/`, and `/{board}/thumb/` result in HTTP 404.
- **Remediation:** Add router alias endpoints:
  ```python
  @app.api_route("/file/{file_id:path}", methods=["GET", "HEAD"])
  @app.api_route("/thumb/{file_id:path}", methods=["GET", "HEAD"])
  @app.api_route("/i/{file_id:path}", methods=["GET", "HEAD"])
  @app.api_route("/preview/{file_id:path}", methods=["GET", "HEAD"])
  @app.api_route("/{board_id}/src/{file_id:path}", methods=["GET", "HEAD"])
  @app.api_route("/{board_id}/thumb/{file_id:path}", methods=["GET", "HEAD"])
  async def media_route_alias(file_id: str, request: Request, filename: str = None, skip: str = None):
      return await get_telegram_file(file_id, request, filename, skip)
  ```

### Bug 2: Dead File Cache Desynchronization
- **Severity:** Medium/High (Performance Degradation)
- **File & Line:** `site_tgach\main.py`: 10395, 10511, 512
- **Description:** `_mark_random_dead_file` only populates local dict `RANDOM_DEAD_FILE_IDS`, leaving Redis key `dead_file:public:{file_id}` unpopulated.
- **Remediation:** Update `_mark_random_dead_file` to write to Redis backend asynchronously:
  ```python
  if backend:
      await backend.set(f"dead_file:public:{file_id}", "1", expire=300)
  ```

### Bug 3: Missing CORS (`Access-Control-Allow-Origin`) Headers on Media Responses
- **Severity:** Medium (Frontend / Web Integration Defect)
- **File & Line:** `site_tgach\main.py`: 10163, 10240, 10418, 10445
- **Description:** Media redirects and streaming proxy responses omit `Access-Control-Allow-Origin: *`, breaking cross-origin JS canvas/video elements and external frontends.
- **Remediation:** Inject `"Access-Control-Allow-Origin": "*"` into response headers across `get_telegram_file`, `_proxy_protected_telegram_file`, and `_proxy_external_url`.

### Bug 4: Per-Request `aiohttp.ClientSession` Creation Overhead in Proxies
- **Severity:** Medium (Resource Allocation Bottleneck)
- **File & Line:** `site_tgach\main.py`: 10129, 10207
- **Description:** `_proxy_protected_telegram_file` and `_proxy_external_url` instantiate a new `aiohttp.ClientSession(connector=aiohttp.TCPConnector(limit=1))` on every single proxy request. Under high concurrency, creating and destroying TCP connectors per request causes socket exhaustion and high memory churn.
- **Remediation:** Reuse a shared global `aiohttp.ClientSession` pool.

### Bug 5: Excessive Bot Pool Probing on Invalid File IDs
- **Severity:** High (External API Rate Limit Risk)
- **File & Line:** `site_tgach\main.py`: 10000–10050
- **Description:** `get_cached_file_path` probes every bot in the bot pool when `owner_id` is missing, firing dozens of `getFile` requests per 404 file.
- **Remediation:** Cap bot probing to a maximum of 2 candidates per request and cache negative results immediately.

---

## 7. Verification Steps

1. **Verify Route Availability:**
   - Execute HTTP GET request to `/files/<valid_file_id>` -> Expected: 307 Redirect or 200 OK stream.
   - Execute HTTP GET request to `/file/<valid_file_id>` -> Currently: 404 Not Found.
   - Execute HTTP GET request to `/thumb/<valid_file_id>` -> Currently: 404 Not Found.
2. **Verify CORS Headers:**
   - Execute `curl -I -H "Origin: https://example.com" https://<host>/files/<file_id>` -> Inspect headers for `Access-Control-Allow-Origin: *`.
3. **Verify Proxy Performance & Socket Churn:**
   - Measure open sockets during simultaneous requests to proxied Catbox / Telegram files using `netstat` or `ss`.

