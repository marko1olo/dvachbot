# Comprehensive Technical Analysis: site_tgach Frontend Image/Thumbnail Rendering, API Contracts, and Probe Infrastructure

**Author**: Explorer Subagent (`explorer_media_3`)  
**Date**: 2026-07-29  
**Target Project**: `C:\Users\danat\Desktop\dvachbot`  
**Working Directory**: `C:\Users\danat\Desktop\dvachbot\.agents\explorer_media_3`

---

## 1. Executive Summary

This report presents a thorough, evidence-based investigation into the frontend image and thumbnail rendering pipelines, API contracts, backend URL resolution endpoints, existing test suite/probe infrastructure, and missing verification requirements (specifically for Cloudflare R2 integration) within `site_tgach`.

### Key Findings
1. **Frontend Templates & Rendering**: Images and thumbnails are rendered across 12 Jinja2 templates in `site_tgach/templates/` (`board.jinja2`, `thread.jinja2`, `chat.jinja2`, `catalog.jinja2`, `gallery.jinja2`, etc.). Frontend uses lazy loading (`data-src` attribute with `IntersectionObserver` in `main.js`) and a robust client-side error recovery mechanism named **`MediaRescue`** (`handleImageError` in `site_tgach/static/js/main.js`).
2. **API Contract & URL Construction**:
   - Post objects contain a `content.files` array where each file item has `original_file_id`, `thumbnail_file_id`, `original_url`, `thumbnail_url`, `filename`, `type`, `blurhash`, and `dupe_count`.
   - Primary site file route: `/files/{file_id:path}` (handled by `get_telegram_file` at `site_tgach/main.py:10313`).
   - Mirror URLs are dynamically selected via `_select_mirror_strategically()` based on regional client IP (`is_ru` flag) and mirror availability in DB (`FileRegistry`).
3. **Current Mirror Architecture**:
   - External provider mirrors currently active/supported: Telegram Direct API (`api.telegram.org`), Telegram Shadow, Telegra.ph (thumbnails), FreeImage (`freeimage.host`), ImgBB (`imgbb.com`), PixHost (`pixhost.to`), Catbox (`files.catbox.moe`), and 0x0.st (`0x0.st`). HuggingFace mirror is disabled/deprecated.
4. **Current Test Infrastructure & Probe Capabilities**:
   - `tests/test_select_mirror_strategically.py` tests mirror priority matrix logic.
   - `tests/test_catbox.py` tests invalid uploader string parsing.
   - `status_check.py` provides rich real-time CLI analytics on `FileRegistry` media stats (tagging, pHash, BlurHash, file types).
   - `browser_full_test.txt` / `browser_errors.txt` log automated browser runs.
   - **CRITICAL TEST GAP**: Zero automated unit or integration tests exist for the `/files/{file_id:path}` endpoint handler (`get_telegram_file()`), smart wait loop timeouts, `skip` parameter parsing, 307 redirects, or 404 fallback routing.
5. **R2 Requirement & Missing Verification**:
   - Cloudflare R2 (or S3) is **currently not implemented** in media storage or mirror routing.
   - Integrating R2 requires updating DB schemas, mirror workers (`mirror_worker.py`), strategic mirror selection (`_select_mirror_strategically`), and endpoint redirect logic in `get_telegram_file`.
   - Comprehensive test cases must be added for R2 URL formatting, presigned URL expiration, endpoint proxying/redirects, and automated E2E browser image probes.

---

## 2. Frontend Image & Thumbnail Display Pipeline

### 2.1 Jinja2 Template Integration
All public web views in `site_tgach` derive from Jinja2 templates located in `site_tgach/templates/`. The primary templates rendering media attachments are:
- `site_tgach/templates/board.jinja2` (Board view `/b/`)
- `site_tgach/templates/thread.jinja2` (Thread view `/b/res/{id}.html`)
- `site_tgach/templates/chat.jinja2` (Real-time live board view)
- `site_tgach/templates/catalog.jinja2` (Board catalog view)
- `site_tgach/templates/gallery.jinja2` (Media gallery view)
- `site_tgach/templates/overboard.jinja2` (Global feed)
- `site_tgach/templates/search_results.jinja2` (Search results view)
- `site_tgach/templates/my_posts.jinja2` & `archive_chat.jinja2` / `archive_threads.jinja2`

#### Template Rendering Pattern
Images and thumbnails are attached to posts via `post.content.files`. Jinja2 templates loop over `post.content.files` and construct HTML elements with lazy loading placeholders:

```html
<!-- Example from site_tgach/templates/thread.jinja2:316-320 -->
<a href="{{ file.original_url }}" class="gallery-trigger" data-type="image" 
   data-filename="{{ file.filename }}" data-file-id="{{ file.original_file_id }}">
    <img loading="lazy" 
         src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7" 
         data-src="{{ file.thumbnail_url or file.original_url }}" 
         alt="Image" class="post-thumb">
</a>
```

For video, webm, or animated stickers:
```html
<video class="post-sticker" src="{{ file.original_url }}" 
       autoplay loop muted playsinline 
       poster="{{ file.thumbnail_url }}"></video>
```

### 2.2 JavaScript Execution & MediaRescue System
The frontend JS logic resides in `site_tgach/static/js/main.js` (source: `main.src.js`) and Service Worker `site_tgach/static/sw.js`.

1. **Lazy Loading (`SmartLoader`)**:
   - `<img>` elements start with a 1x1 transparent base64 GIF in `src` and the target media URL in `data-src`.
   - `IntersectionObserver` monitors viewport entry and assigns `img.src = img.dataset.src`.
2. **Service Worker Caching (`sw.js`)**:
   - `sw.js` intercepts requests starting with `/files/`:
     ```javascript
     // site_tgach/static/sw.js:87-88
     if (url.pathname.startsWith('/files/')) {
         // Strategy: Cache First with size limits and fallback to network
     }
     ```
3. **Client-Side Media Rescue (`handleImageError`)**:
   - When an `<img>` or `<video>` fails to load (HTTP 4xx, 5xx, or network drop), the `onerror` event triggers `handleImageError(img)` (`main.js:11358-11458`).
   - `handleImageError` identifies the failing mirror host from `img.src` (`freeimage`, `imgbb`, `pixhost`, `catbox`, `0x0`, `telegram`).
   - It appends the failed host to `img.dataset.skippedHosts` and re-requests the image by appending `?skip=failed_host1,failed_host2` to the original URL (e.g. `/files/AgACAg.../image.jpg?skip=freeimage,imgbb`).
   - If 6 consecutive attempts fail (`skipped.length >= 6`), the image is marked as `broken-final`, and a fallback download button (`📂 Скачать`) is inserted into the DOM.

---

## 3. Backend API Contracts & Endpoint Architecture

### 3.1 API Post & File DTO Contract
When fetching posts via REST API (`/api/thread/{board_id}/{thread_id}`, `/api/catalog/{board_id}`, etc.), media files are returned as an array of file dictionaries in `content.files`:

| Field Name | Type | Description |
|---|---|---|
| `original_file_id` | `str` | Telegram file ID or unique string identifier for the original file (e.g., `AgAC...` for photos, `BAAC...` for videos). |
| `thumbnail_file_id` | `str` | Telegram file ID for the thumbnail preview (optional). |
| `original_url` | `str` | Public relative endpoint (`/files/{file_id}/{filename}`) or direct HTTPS mirror link. |
| `thumbnail_url` | `str` | Public URL for thumbnail preview (`https://telegra.ph/...`, mirror link, or `/files/{thumb_id}`). |
| `filename` | `str` | Sanitized filename (e.g. `img_AgAC...jpg`, `vid_...mp4`). |
| `type` | `str` | Media category (`image`, `video`, `audio`, `voice`, `sticker`, `document`, `animation`, `video_note`). |
| `blurhash` | `str` / `null` | Pre-calculated blurhash string for instant blurred low-res placeholder rendering. |
| `dupe_count` | `int` | Counter of duplicate image instances detected across the site database. |

### 3.2 Endpoint URL Construction (`main.py`)

File URL enrichment occurs in three key Python helper functions in `site_tgach/main.py`:
1. `_process_files_list(content)` (`main.py:3525-3594`):
   - Maps raw Telegram file IDs to relative `/files/...` endpoints.
   - If `original_file_id` starts with `http://` or `https://`, `original_url` is left intact.
   - Otherwise, formats `original_url = f"/files/{clean_oid}/{safe_name}"`.
2. `enrich_extra_data(posts, is_ru)` (`main.py:3338-3470`):
   - Queries Redis cache and SQLite `FileRegistry` for file mirrors (`get_mirrors_batch`).
   - Calls `_select_mirror_strategically()` for each file.
3. `_select_mirror_strategically(file_info, mirrors, thumb_mirrors, is_ru)` (`main.py:3282-3335`):
   - Applies regional priority rules (`is_ru` flag derived from MaxMind GeoIP IP lookup):
     - **Thumbnails**: Priority 1 is Telegra.ph (`telegra.ph`), followed by Catbox (`catbox.moe`) for non-RU, or 0x0.st / relative `/files/` fallback.
     - **Originals**: Prioritizes fast external mirrors if valid, falling back to Telegram proxy `/files/`.

### 3.3 Endpoint Request Resolution (`get_telegram_file`)
The primary media endpoint is defined at line 10313 of `site_tgach/main.py`:
`@app.api_route("/files/{file_id:path}", methods=["GET", "HEAD"])`

#### Request Resolution Flow:
```
GET /files/{file_id}?skip={skipped_hosts}
  │
  ├─> 1. If file_id is HTTP URL ──────────────> HTTP 301 Redirect to URL
  │
  ├─> 2. Smart Wait Loop (up to 2.5s / 7.5s for video):
  │      Polls Redis / DB for mirror generation (avoids 404 immediately after posting).
  │
  ├─> 3. Check Telegram Direct Path (if "telegram" not in skip):
  │      If path & token cached ──────────────> HTTP 307 Redirect to api.telegram.org
  │
  ├─> 4. Check Telegram Shadow Path ──────────> HTTP 307 Redirect to api.telegram.org
  │
  ├─> 5. Check Direct External Mirrors (if not in skip):
  │      - FreeImage ─────────────────────────> HTTP 307 Redirect to freeimage.host
  │      - ImgBB ─────────────────────────────> HTTP 307 Redirect to imgbb.com
  │      - PixHost ───────────────────────────> HTTP 307 Redirect to pixhost.to
  │
  ├─> 6. Check Region-Sensitive Mirrors:
  │      - Catbox (non-RU) ───────────────────> HTTP 307 Redirect to files.catbox.moe
  │      - Catbox (RU) ───────────────────────> HTTP 200 Proxy via _proxy_external_url()
  │      - 0x0.st (non-RU) ───────────────────> HTTP 307 Redirect to 0x0.st
  │      - 0x0.st (RU) ───────────────────────> HTTP 200 Proxy via _proxy_external_url()
  │
  ├─> 7. Thumbnail Fallback (file_id starts with "AgAC"):
  │      Queries FileRegistry for original_file_id where thumbnail_id = file_id.
  │      If found ────────────────────────────> Retries get_telegram_file(original_id)
  │
  └─> 8. Exhaustion ──────────────────────────> Marks dead file & HTTP 404 "File unavailable."
```

---

## 4. Existing Test Suite & Verification Infrastructure

### 4.1 Unit & Integration Test Inventory
The project contains 96 unit test files in `tests/`. The specific media-related tests are:
1. `tests/test_select_mirror_strategically.py`:
   - Validates `_select_mirror_strategically()` behavior with empty mirrors, HuggingFace mirrors, Catbox mirrors, and `is_ru` toggle.
2. `tests/test_catbox.py`:
   - Validates `_is_invalid_uploader()` string matching for Catbox response parsing.
3. `tests/test_importer.py`:
   - Validates auto-importer media extraction and file ID assignment.
4. `tests/test_mirror_worker_init.py`:
   - Validates background mirror worker initialization parameters.

### 4.2 Probes & Monitoring Infrastructure
1. `status_check.py`:
   - Command-line dashboard using `rich` library.
   - Provides live analytics on `FileRegistry` media stats: total files, percentage with tags, percentage with pHash, percentage with BlurHash, breakdown by media type (image, video, audio, etc.), total thumbnails.
2. `browser_full_test.txt` & `browser_errors.txt`:
   - Output logs from headless browser automated test runs (Playwright/Puppeteer).
   - Verifies 200 OK HTTP responses across all core routes (`/`, `/b/catalog/`, `/about/`, `/rules/`, `/faq/`, `/login`, `/overboard/`, `/b/res/*.html`).
   - Captures console errors (e.g. 401 Unauthorized, broken image rescue logs `[MediaRescue]`).

### 4.3 Identified Critical Test Deficiencies
- **Zero Endpoint Tests for `/files/{file_id:path}`**: There are no unit or integration tests invoking `get_telegram_file()` or requesting `/files/...` endpoints via `httpx.AsyncClient` / FastAPI `TestClient`.
- **Untested Smart Wait Loop**: No tests simulate async mirror generation delays or video waiting timeouts (2.5s vs 7.5s).
- **Untested Client Fallback Protocol**: No automated tests verify that the `skip` query parameter (`?skip=...`) correctly filters out failed mirror providers.
- **Untested Thumbnail Fallback**: No test verifies the `AgAC` database lookup fallback to original file ID when a thumbnail is missing.

---

## 5. R2 Storage Requirement & Missing Verification Plan

### 5.1 Current R2 Implementation Status
Cloudflare R2 (and S3-compatible object storage) is **currently NOT implemented** in the target codebase `C:\Users\danat\Desktop\dvachbot`.
- Existing mirror providers: Telegram Direct, Telegram Shadow, Telegra.ph, FreeImage, ImgBB, PixHost, Catbox, 0x0.st.
- `r2` mentions in existing files are limited to `difflib` variable names (`r2 = ...`) or element bounding rectangle math in JS (`rect.right < r2.left`).

### 5.2 R2 Integration Architecture Requirements
When Cloudflare R2 storage is introduced for `site_tgach` media loading, it must integrate into four architectural layers:

1. **Database & Mirror Worker Layer**:
   - `FileRegistry` schema / mirror dictionary must support `"r2"` key.
   - `mirror_worker.py` must include an R2 uploader task using `boto3` or `aioboto3` targeting S3 API endpoints (`{account_id}.r2.cloudflarestorage.com`).
2. **Strategic Mirror Selection (`_select_mirror_strategically`)**:
   - R2 should serve as a **Top Priority CDN** for both RU and non-RU users due to its high availability, low latency, and zero egress fees.
   - Priority sequence: R2 -> Telegra.ph (thumbnails) / Telegram Direct -> FreeImage / ImgBB / PixHost -> Catbox / 0x0.
3. **Endpoint Routing (`get_telegram_file`)**:
   - If R2 link exists in `mirrors` and `"r2"` is not in `skip`:
     - Return HTTP 307 redirect to R2 public custom domain (e.g., `https://media.site-tgach.org/{file_id}.jpg`) or presigned URL.
4. **Client Error Recovery (`main.js`)**:
   - Add R2 domain matching to `handleImageError()`:
     ```javascript
     else if (currentSrc.includes("r2.cloudflarestorage.com") || currentSrc.includes("media.site-tgach.org")) failedType = "r2";
     ```

### 5.3 Missing Test Cases & Automated Verification Needs for Image Loading (R2)

To satisfy the R2 verification requirement (R2 requirement), the following test cases must be added:

#### 1. Backend Endpoint Integration Tests (`tests/test_files_endpoint.py`)
- `test_files_endpoint_r2_redirect()`: Verify that when an R2 mirror exists for `file_id`, GET `/files/{file_id}` returns `HTTP 307` with `Location: https://r2.domain.com/{file_id}`.
- `test_files_endpoint_r2_skip()`: Verify that GET `/files/{file_id}?skip=r2` bypasses R2 and redirects to the next available mirror (FreeImage / ImgBB / Telegram).
- `test_files_endpoint_telegram_direct()`: Verify HTTP 307 redirect to Telegram Bot API when cached.
- `test_files_endpoint_thumbnail_agac_fallback()`: Verify `AgAC` thumbnail lookup fallback to original file ID.
- `test_files_endpoint_smart_wait_loop()`: Verify smart wait loop wait time and 404 dead file marking upon exhaustion.

#### 2. R2 Storage & Utility Tests (`tests/test_r2_storage.py`)
- `test_r2_upload_success()`: Test mock R2 upload using `aioboto3` and verify mirror dictionary update in DB.
- `test_r2_url_formatting()`: Verify custom domain vs direct R2 URL generation.
- `test_r2_presigned_url_expiration()`: Verify presigned URL expiry header calculations.
- `test_r2_health_check_fallback()`: Verify automatic failover to secondary mirrors if R2 returns 403, 404, or 503.

#### 3. Automated E2E Browser & HTTP Probe Infrastructure (`verification_scripts/media_loading_probe.py`)
- **HTTP Probe**: Script that queries all active thread and catalog endpoints (`/api/threads/b`, `/api/catalog/b`), extracts all `original_url` and `thumbnail_url` links, and verifies that 100% of media URLs resolve to HTTP 200 or 307 -> 200 OK within 1.5 seconds.
- **Client Fallback E2E Probe**: Headless browser test (Playwright/Puppeteer) that intercepts image network requests, simulates a 500 error on the primary R2/FreeImage host, and asserts that `MediaRescue` successfully appends `?skip=...` and loads the image from the secondary provider without broken image icons.

---

## 6. Synthesis & Next Steps Roadmap

| Component | Current State | Target State (R2 Ready) | Action Required |
|---|---|---|---|
| **Templates** | Render `file.original_url` / `file.thumbnail_url` via Jinja2 | Unchanged (fully compatible) | None |
| **JS Frontend** | Lazy loading + `MediaRescue` (`main.js`) | Updated with R2 host detection | Add R2 domain to `handleImageError` |
| **Mirror Selection** | Prioritizes Telegra.ph / FreeImage / Catbox | R2 as Priority 1 CDN | Update `_select_mirror_strategically()` |
| **Endpoint (`/files/`)** | Proxies/Redirects TG, FreeImage, Catbox, 0x0 | Supports R2 307 Redirects & `skip=r2` | Add R2 branch to `get_telegram_file()` |
| **Test Suite** | Unit test for mirror selection matrix only | Full Endpoint + R2 Test Suite | Create `tests/test_files_endpoint.py` |
| **Probe Infrastructure** | CLI status check + static browser logs | Automated HTTP/E2E Media Probes | Create `verification_scripts/media_loading_probe.py` |

---
*End of Analysis Report.*
