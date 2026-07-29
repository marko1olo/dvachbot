# HANDOFF REPORT — Fallback & Mirror Image Services Audit

## 1. Observation

Direct observations from auditing source code files under `C:\Users\danat\Desktop\dvachbot\site_tgach`:

1. **Catbox Integration (`site_tgach/catbox.py`)**:
   - `_upload_logic` (lines 64-147) handles `urlupload` (URL source) and `fileupload` (disk file / memory tuple).
   - Userhash rejection check (`_is_invalid_uploader` lines 49-52) disables userhash for 3600 seconds (`_disable_bad_catbox_hash` lines 54-58) and retries payload as anonymous upload (lines 119-123).
   - Dynamic strategy selection: Direct/System transport first, followed by HTTP/SOCKS proxy (`PROXY_URL`, lines 71-74).

2. **0x0.st Integration (`site_tgach/zeroxzero.py`)**:
   - `_post_0x0` (lines 56-100) disables 0x0.st for 6 hours (`ZEROXZERO_COOLDOWN_SECONDS = 21600`) if HTTP 503 response contains `"uploads disabled"` (lines 86-88).
   - Enforces configurable byte payload limit (`ZEROXZERO_MAX_BYTES` = 512MB, line 14).

3. **Pixhost Integration (`site_tgach/pixhost.py`)**:
   - `upload_file_to_pixhost` (lines 26-98) enforces 10MB limit (`PIXHOST_MAX_MB`, line 18) and extension whitelist (`.jpg`, `.jpeg`, `.png`, `.gif`, `.bmp`, `.webp`, line 17).
   - Line 82 assigns `direct_url = show_url`, returning HTML viewer page URL (`https://pixhost.to/show/...`) rather than direct raw image URL (`https://img123.pixhost.to/images/...`).

4. **ImgBB Integration (`site_tgach/imgbb.py`)**:
   - `upload_file_to_imgbb` (lines 29-94) requires `IMGBB_API_KEY` (line 15) and max size 32MB (line 44).
   - Lines 62-66 load the file as bytes and Base64-encodes the entire buffer (`base64.b64encode(file_bytes)`).
   - Returns `None` immediately on HTTP 400 Bad Request (line 82) to avoid key exhaustion.

5. **FreeImage Integration (`site_tgach/freeimage.py`)**:
   - `upload_file_to_freeimage` (lines 25-77) targets `https://freeimage.host/api/1/upload`.
   - **Unreferenced**: `freeimage.py` is not imported in `mirror_worker.py` (lines 11-19), `image_processing.py` (lines 49-55), or `tagging_worker.py`.

6. **Mirror Worker & Dead `file_id` Recovery (`site_tgach/mirror_worker.py`)**:
   - `process_mirror_queue` (lines 327-358) filters allowed types to `['catbox', 'pixhost']` + optional `'0x0'` and `'imgbb'` (lines 341-345).
   - `_process_single_task` (lines 109-326) checks bot state and catches `"file_id_invalid"` / `"wrong file_id"` (lines 188-206).
   - For photos (`AgAC...`) without DB message context (`_find_msg_info`), task is immediately removed as dead (line 201).
   - `_detect_real_ext` (lines 25-42) reads header magic bytes (`JPEG`, `PNG`, `GIF`, `WEBP`, `BMP`) and renames `.dat` files to proper extensions before sending to Pixhost or ImgBB (lines 279-304).

7. **Tagging Worker Fallback (`site_tgach/tagging_worker.py`)**:
   - `download_file_with_fallback` (lines 412-447) limits per-bot download timeout to 45s (`DOWNLOAD_TIMEOUT_PER_BOT`) and total deadline to 120s (`DOWNLOAD_TOTAL_TIMEOUT`). Maintains `TEMP_FAILED_FILES` in memory.

---

## 2. Logic Chain

1. **Initialization & Invocation**:
   - Media uploaded to Telegram triggers `_upload_mirrors_task` in `image_processing.py`, attempting direct Catbox/0x0/HF uploads. Failures or delayed tasks are inserted into `MirrorQueue` table in SQLite.
   - `mirror_worker.py` polls `MirrorQueue` every 10 seconds. Active mirror types are dynamically checked based on environment variables (`IMGBB_API_KEY`, `ZEROXZERO_ENABLED`).

2. **Dead `file_id` Detection & Recovery**:
   - If Telegram Bot API rejects a `file_id` (expired or invalid), `mirror_worker.py` queries `Posts` and `ChannelCopies` via `_find_msg_info` to get `(channel_id, message_id)`.
   - If message context is found, it switches to Pyrogram MTProto (`download_file_mtproto`) to recover the file.
   - If no message context exists and the file is a photo (`AgAC...`), MTProto cannot recover it; the task is deleted from `MirrorQueue` as unrecoverable.

3. **Error Handling & Fallbacks**:
   - Catbox detects userhash bans and switches seamlessly to anonymous upload.
   - 0x0.st enforces a 6-hour service-wide pause when HTTP 503 "uploads disabled" occurs.
   - Tasks in `MirrorQueue` use exponential retry backoff (`delay = min(300 * 2^attempt, 3600)` seconds) and are purged after 10 failed attempts.

4. **Identified Defects**:
   - `freeimage.py` is an orphaned module that is never called by any worker or task handler.
   - `pixhost.py` returns HTML page links (`show_url`) instead of raw direct image file URLs, breaking image embeds.
   - `imgbb.py` performs in-memory Base64 encoding for up to 32MB files, creating high RAM usage under high concurrency.

---

## 3. Caveats

- **Network Constraints**: Conducted in CODE_ONLY mode without executing live HTTP requests to external APIs (`catbox.moe`, `0x0.st`, `pixhost.to`, `imgbb.com`, `freeimage.host`).
- **Database State**: Analyzed database query structures in `common/database.py` and `mirror_worker.py`. Did not inspect live sqlite DB data content (`2d2vach_bot.db`).
- **Proxy Configuration**: Assumed standard `PROXY_URL` behavior as defined in code. Live proxy performance was not benchmarked.

---

## 4. Conclusion

The fallback and mirror image services in `site_tgach` feature a robust multi-tier fallback mechanism (Instant URL -> MTProto Download -> HTTP Fallback -> Async Mirror Queue) with solid error handling for dead `file_id`s, exponential backoff, and bot pool failover.

However, three key actionable issues require resolution by the implementation team:
1. **Unused Module**: `freeimage.py` is orphaned and should be integrated into `mirror_worker.py` or pruned.
2. **Broken Direct Image Links**: `pixhost.py` returns `show_url` (HTML viewer page) instead of raw image data.
3. **Memory Optimization**: `imgbb.py` requires Base64 payload streaming/multipart form-data optimization to reduce RAM usage on large image files.

---

## 5. Verification Method

To verify these findings independently:

1. **Orphan `freeimage.py` Verification**:
   - Inspect imports across `site_tgach/mirror_worker.py`, `site_tgach/image_processing.py`, and `site_tgach/tagging_worker.py`.
   - Confirm `upload_file_to_freeimage` is never imported or called.

2. **Pixhost Link Return Verification**:
   - Inspect `site_tgach/pixhost.py` lines 76-84.
   - Observe `direct_url = show_url` where `show_url` is the page URL returned by `https://api.pixhost.to/images`.

3. **Dead `file_id` Recovery Logic Verification**:
   - Inspect `site_tgach/mirror_worker.py` lines 178-206.
   - Confirm `_find_msg_info` lookup and MTProto fallback handling for invalid `file_id`s.

4. **Detailed Report**:
   - Refer to full analysis in `C:\Users\danat\Desktop\dvachbot\.agents\explorer_media_2\analysis.md`.
