# Fallback and Mirror Image Services Audit Report (`site_tgach`)

## Executive Summary

This report provides an in-depth audit of the fallback and mirror image services within `site_tgach` (`dvachbot` codebase). It covers service initialization, Telegram `file_id` failure detection and recovery, error and timeout handling, retry backoff mechanisms, and identified API flaws or architecture bottlenecks.

---

## 1. Architecture Overview & Component Map

The fallback and mirror image pipeline consists of several interconnected modules:

```
                          ┌────────────────────────┐
                          │ Upload Event / Worker  │
                          └───────────┬────────────┘
                                      │
                   ┌──────────────────┴──────────────────┐
                   ▼                                     ▼
      [Instant Mirrors Task]                    [Mirror Worker Queue]
  `image_processing.py::_upload_mirrors_task`   `mirror_worker.py::process_mirror_queue`
                   │                                     │
     ┌─────────────┼──────────────┐        ┌─────────────┼──────────────┬────────────┐
     ▼             ▼              ▼        ▼             ▼              ▼            ▼
  Catbox         0x0.st          HF      Catbox        0x0.st        Pixhost       ImgBB
(catbox.py)  (zeroxzero.py)  (hf.py)   (catbox.py)  (zeroxzero.py) (pixhost.py)  (imgbb.py)
                                                                                  [Freeimage: Unused!]
```

### Module Responsibilities:
1. **`site_tgach/catbox.py`**: Handles Catbox.moe uploads for URLs (`upload_url_to_catbox`), local disk files (`upload_file_to_catbox`), and raw memory bytes (`upload_bytes_to_catbox`). Supports userhash authentication with fallback to anonymous upload on ban/rejection.
2. **`site_tgach/zeroxzero.py`**: Handles 0x0.st uploads (`upload_url_to_0x0`, `upload_file_to_0x0`, `upload_bytes_to_0x0`). Features endpoint health tracking with a 6-hour cooldown on HTTP 503 "uploads disabled".
3. **`site_tgach/pixhost.py`**: Handles Pixhost.to uploads (`upload_file_to_pixhost`). No API key required. Enforces a 10 MB per-file ceiling (`PIXHOST_MAX_MB`) and restricted format whitelist (`.jpg`, `.jpeg`, `.png`, `.gif`, `.bmp`, `.webp`).
4. **`site_tgach/imgbb.py`**: Handles ImgBB.com uploads (`upload_file_to_imgbb`). Requires `IMGBB_API_KEY`. Enforces a 32 MB ceiling. Encodes images to Base64 strings.
5. **`site_tgach/freeimage.py`**: Handles FreeImage.host / iili.io uploads. **Orphan module** (unreferenced in production mirror workflows).
6. **`site_tgach/mirror_worker.py`**: Asynchronous background worker processing tasks in SQLite `MirrorQueue`. Resolves Telegram bot instances, recovers dead/expired `file_id`s, downloads files locally, inspects magic bytes, and uploads to active mirror providers.
7. **`site_tgach/mirror_health.py`**: Manages Hugging Face repository health states and persistent lockout cooldowns (`HF_LOCKED_COOLDOWN_SECONDS` = 6 hours).
8. **`site_tgach/tagging_worker.py`**: Downloads media for neural network tagging using multi-bot failover loops and timeout protections.

---

## 2. Service Initialization & Invocation Lifecycle

### Phase A: Instant Upload (`image_processing.py::_upload_mirrors_task`)
When a file is uploaded to Telegram via `process_and_upload_image`:
- **Files > 19 MB or Direct Bytes Payload**:
  - `_upload_mirrors_task` executes `asyncio.gather(_catbox_direct(), _hf_direct(), _zeroxzero_direct())`.
  - Byte payloads are pushed directly to Catbox, HuggingFace, and 0x0.st.
- **Files <= 19 MB**:
  - Direct Telegram HTTP file URLs (`https://api.telegram.org/file/bot{bot.token}/{file_path}`) are constructed.
  - URL uploads are dispatched to Catbox (`upload_url_to_catbox`) and 0x0.st (`upload_url_to_0x0`).
  - If instant upload fails or `file_path` cannot be retrieved, tasks are queued into the SQLite `MirrorQueue` table via `add_to_mirror_queue(file_id, mirror_type)`.

### Phase B: Asynchronous Queue Processing (`mirror_worker.py::process_mirror_queue`)
- Polling loop retrieves tasks from `MirrorQueue` where `next_run_at <= time.time()`.
- Active providers determined dynamically:
  - Default active allowed types: `['catbox', 'pixhost']`.
  - Added `'0x0'` if `is_0x0_available()` returns `True`.
  - Added `'imgbb'` if `IMGBB_API_KEY` environment variable is set.
  - **Freeimage is never included in allowed types.**

---

## 3. Telegram `file_id` Expiration & Recovery Mechanics

Telegram `file_id`s frequently become stale or restricted (e.g. Bot API tokens changed, photos starting with `AgAC` bound to specific bot instances, or post deletion).

```
                            ┌─────────────────────────────────┐
                            │  bot.get_file(file_id) Request  │
                            └────────────────┬────────────────┘
                                             │
                       ┌─────────────────────┴─────────────────────┐
                       ▼                                           ▼
             [Success: file_path]                      [Exception Caught]
                       │                                           │
                       │                        ┌──────────────────┴──────────────────┐
                       │                        ▼                                     ▼
                       │           "logged out" / "unauthorized"           "file_id_invalid" / "wrong file_id"
                       │                        │                                     │
                       │              Mark Bot Dead in Pool                DB Lookup: `_find_msg_info(file_id)`
                       │                                                              │
                       │                                            ┌─────────────────┴─────────────────┐
                       │                                            ▼                                   ▼
                       │                                   [No Message Context]               [Message Context Found]
                       │                                            │                                   │
                       │                                ┌───────────┴───────────┐                       ▼
                       │                                ▼                       ▼             Try MTProto Recovery
                       │                            Is Photo?              Not Photo?      (download_file_mtproto)
                       │                          (`AgAC...`)               (Document)                  │
                       │                                │                       │            ┌──────────┴──────────┐
                       │                                ▼                       ▼            ▼                     ▼
                       │                            DEAD FILE               DEAD FILE    [Success]             [Failure]
                       │                           Remove Task             Remove Task       │                     │
                       │                                                                     ▼                     ▼
                       └─────────────────────────────────────────────────────────────► Local Disk Download   HTTP Fallback
```

### Detailed Failover Steps:
1. **Bot Resolution**: `_resolve_file_bot(owner_id)` checks `global_bot_pool` for the original uploader bot. If missing or logged out, marks the bot dead and reschedules.
2. **Bot API `get_file` Check**:
   - If error matches `"file_id_invalid"` or `"wrong file_id"`:
     - Calls `_find_msg_info(file_id)` to query the `Posts` and `ChannelCopies` DB tables for `(channel_id, message_id, post_num)`.
     - **Non-photos without context**: Marked permanently DEAD; task removed from `MirrorQueue`.
     - **Photos (`AgAC...`) without message context**: Marked DEAD and task removed. (Pyrogram MTProto cannot download Bot API photo `file_id`s without channel/message context).
     - **With message context**: Triggers MTProto recovery via `download_file_mtproto`.
3. **Multi-tier Download Chain**:
   - **Tier 1 (Direct URL Upload)**: Telegram Bot API HTTP URL passed to mirror API if `public_safe_bot` is available.
   - **Tier 2 (MTProto Download)**: Pyrogram MTProto streams media to a temporary file (`tempfile.mkstemp`).
   - **Tier 3 (HTTP Fallback Download)**: Streaming HTTP `GET` directly from `https://api.telegram.org/file/bot{token}/{file_path}` using `httpx.AsyncClient`.
4. **Magic Bytes Extension Detection (`_detect_real_ext`)**:
   - Telegram downloads often arrive as `.dat` or with generic extensions.
   - Before uploading to strict format-checked mirrors (`Pixhost`, `ImgBB`), `_detect_real_ext` reads the first 12 bytes:
     - `\xFF\xD8\xFF` -> `.jpg`
     - `\x89PNG\r\n\x1a\n` -> `.png`
     - `GIF87a` / `GIF89a` -> `.gif`
     - `RIFF....WEBP` -> `.webp`
     - `BM` -> `.bmp`
   - If a valid image format is detected, `lpath` is renamed with the real extension so Pixhost/ImgBB do not reject it.

---

## 4. Timeout, Retry, and Error Handling Audit

| Service / Module | Timeout Config | Retry Mechanism | Error / Failover Behavior |
| :--- | :--- | :--- | :--- |
| **`catbox.py`** | File: 120s<br>URL: 60s | `httpx.AsyncHTTPTransport(retries=3)` | Checks for `"invalid uploader"` or `"banned"`. Disables `CATBOX_HASH` for 3600s (`_disable_bad_catbox_hash`) and immediately retries as anonymous upload. Sleeps 5s on 429/500/502/503. |
| **`zeroxzero.py`** | File: 180s<br>URL: 90s | `httpx.AsyncHTTPTransport(retries=2)` | On HTTP 503 "uploads disabled", marks service unavailable for 6 hours (`ZEROXZERO_COOLDOWN_SECONDS`). Validates output link format (`https://0x0.st/`). |
| **`pixhost.py`** | File: 60s | `httpx.AsyncHTTPTransport(retries=2)` | Skips files > 10MB or unsupported extensions (`.mp4`, `.webm`, `.ogg`). Returns `show_url` on status 200. |
| **`imgbb.py`** | File: 60s | `httpx.AsyncHTTPTransport(retries=2)` | Skips files > 32MB. Immediately returns `None` on HTTP 400 Bad Request (prevents API key burn). Base64 payload encoding. |
| **`freeimage.py`** | File: 60s | `httpx.AsyncHTTPTransport(retries=2)` | **Orphan Code**. No integration with `mirror_worker.py` or queues. |
| **`mirror_worker.py`** | Task max attempts: 10 | Exponential backoff: `min(300 * 2^attempt, 3600)` sec | Cleans up temporary files in `finally:` block. Checks `existing_mirrors` via `get_file_mirrors` to skip duplicate task execution. |
| **`tagging_worker.py`**| Per Bot: 45s<br>Total: 120s | Iterates pool: `primary_bot` -> `main_bot` -> `active_bots` | Keeps in-memory `TEMP_FAILED_FILES` cooldown dict. Sets `tags='download_failed'` after 3 consecutive failures across all bots. |

---

## 5. Identified Defects, API Discrepancies & Risks

### 1. Orphan Service: `freeimage.py`
- **Finding**: `site_tgach/freeimage.py` contains a complete implementation for FreeImage.host / iili.io uploads, but it is **never imported, referenced, or used** in `mirror_worker.py`, `image_processing.py`, `main.py`, or any backfill script.
- **Impact**: Dead code maintenance overhead; missing out on a functional image fallback host.

### 2. Invalid Direct Image Links: `pixhost.py`
- **Finding**: In `pixhost.py` (lines 76-84), the API returns `show_url` (the HTML web page wrapper, e.g., `https://pixhost.to/show/123/abc.jpg`) and `th_url` (thumbnail). The code assigns `direct_url = show_url` and stores it in `FileMirrors`.
- **Impact**: Any web frontend or API client attempting to embed the Pixhost mirror as an `<img>` tag or video source will load an HTML page instead of raw image bytes, breaking image display. Pixhost direct image links require domain transformation (e.g. `https://img123.pixhost.to/images/123/abc.jpg`).

### 3. Memory Spikes from Base64 Encoding: `imgbb.py`
- **Finding**: `imgbb.py` reads the entire image file into memory (`file_bytes = f.read()`) and converts it to a base64 string (`base64.b64encode(file_bytes).decode("utf-8")`).
- **Impact**: For files up to 32MB, base64 encoding allocates ~43MB string buffers in RAM. With 20 parallel tasks (`SEM = asyncio.Semaphore(20)` in `mirror_worker.py`), concurrent ImgBB uploads can cause severe memory allocation spikes (~1GB RAM) and trigger Python GC pauses.

### 4. Asymmetric Request Timeouts
- **Finding**: Timeout values across uploaders are inconsistent: Catbox (120s), 0x0.st (180s), ImgBB (60s), Pixhost (60s), Freeimage (60s).
- **Impact**: Under slow proxy connections or network congestion, 60s is often insufficient for 10MB-32MB image uploads, causing high failure and retry rates for ImgBB and Pixhost compared to Catbox.

### 5. Telegram Bot Token Redaction Gaps in Log Statements
- **Finding**: `mirror_worker.py` (line 171) constructs `tg_url = f"https://api.telegram.org/file/bot{bot.token}/{file_path}"`. If network errors occur during download or logging prints raw URL strings without filtering, secret bot tokens may leak into log files.

---

## 6. Recommendations & Action Items

1. **Integrate or Deprecate Freeimage**:
   - Add `'freeimage'` to `allowed_types` in `mirror_worker.py` if `FREEIMAGE_API_KEY` is present in `.env`, or remove `site_tgach/freeimage.py` if deprecated.
2. **Fix Pixhost Direct Image URL Construction**:
   - Implement direct image URL parsing in `pixhost.py` (e.g. converting `https://pixhost.to/show/{dir}/{file}` to `https://img{dir}.pixhost.to/images/{dir}/{file}` or parsing `th_url`).
3. **Optimize ImgBB Payload Transmission**:
   - Use multipart form-data file uploads for ImgBB if supported by API, or stream chunked uploads to avoid full base64 string allocations in memory.
4. **Harmonize Timeout Limits**:
   - Standardize upload timeouts across image fallback modules to 90s–120s with configurable `.env` overrides.
