# Backend Media Proxy & Routing Audit Report

## 1. Observation

### Exact File Locations and Line Numbers:
1. **`common/database.py` (lines 7736–7758, 7760–7776)**:
   - `get_failed_files_batch(file_ids)`:
     ```python
     query = f"""
         SELECT file_id, thumbnail_id 
         FROM FileRegistry 
         WHERE (tags IN ('download_failed', 'error', 'error_no_tags', 'error_too_large', 'format_unsupported', 'dead') OR tags LIKE 'error%' OR tags LIKE '%download_failed%') 
           AND (file_id IN ({placeholders}) OR thumbnail_id IN ({placeholders}))
     """
     ```
   - `is_file_permanently_failed(file_id)`:
     ```python
     "SELECT tags FROM FileRegistry WHERE (file_id = ? OR thumbnail_id = ?) AND (tags IN ('download_failed', 'error', 'error_no_tags', 'error_too_large', 'format_unsupported', 'dead') OR tags LIKE 'error%' OR tags LIKE '%download_failed%') LIMIT 1"
     ```

2. **`site_tgach/tagging_worker.py` (lines 791–792, 806–836)**:
   - When AI vision tagging runs on a successfully downloaded image, if the vision tagger returns no tags or an empty response, `tagging_worker.py` assigns `tags = "error_no_tags"`:
     ```python
     if not tags:
         tags = "error_no_tags"
     ```
   - It then updates `FileRegistry`: `UPDATE FileRegistry SET tags = 'error_no_tags' WHERE file_id = ?`.

3. **`site_tgach/main.py` (lines 3412–3556, 3345–3409, 3624–3700, 10454–10681)**:
   - `_process_files_list` (lines 3624–3700): Sets initial `file_info["original_url"]` and `file_info["thumbnail_url"]`. If `thumbnail_file_id` is missing/None, `thumbnail_url` is set to `""`.
   - `_select_mirror_strategically` (lines 3345–3409): Selects regional mirror URL. If no mirror exists for `thumbnail_file_id`, returns `base_thumbnail_url`.
   - `enrich_extra_data` (lines 3412–3556):
     ```python
     is_orig_failed = (
         (fid in failed_set)
         or f.get("is_broken")
         or (f.get("tags") in ("download_failed", "error"))
     )
     if is_orig_failed:
         f["is_broken"] = True
         f["download_failed"] = True
         f["original_url"] = ""
         f["thumbnail_url"] = ""
     ```
   - Endpoint routing (lines 10454–10681): `/files/{file_id:path}` dynamic proxy route checks `is_file_permanently_failed(file_id)`. If true, raises `HTTPException(404, "File permanently unavailable.")`.
   - Route aliases registered: `/files/{file_id:path}`, `/file/{file_id:path}`, `/thumb/{file_id:path}`, `/i/{file_id:path}`, `/preview/{file_id:path}`, `/{board_id}/src/{file_id:path}`, `/{board_id}/thumb/{file_id:path}`.

4. **Dubsite & Route Inspection**:
   - `Dubsite_tgach/main.py` (lines 6388–6483): Contains matching `/files/{file_id:path}` endpoint implementation.
   - Endpoint `/api/media/{file_id}`: **Does NOT exist** in `site_tgach/main.py` or `Dubsite_tgach/main.py`.
   - Static mounting `app.mount("/files", ...)`: **Does NOT exist**. `/static` is mounted via `app.mount("/static", ...)` on line 2380. `/files` is handled dynamically via `@app.api_route("/files/{file_id:path}")`.

---

## 2. Logic Chain

1. **Root Cause of Vanishing Thumbnails**:
   - Step 1: Background worker (`tagging_worker.py`) successfully downloads an image/photo from Telegram.
   - Step 2: The worker processes the image (calculates SHA256, pHash, BlurHash) and attempts AI vision tagging via `get_neuro_tags`.
   - Step 3: If AI vision tagging returns empty/no tags (e.g. rate limit, disabled AI, simple image, or no tags returned), `tagging_worker.py` sets `tags = "error_no_tags"` in `FileRegistry`.
   - Step 4: When FastAPI serves posts, `enrich_extra_data` calls `get_failed_files_batch(all_fids)` from `common/database.py`.
   - Step 5: `get_failed_files_batch` includes `'error_no_tags'` in its SQL `WHERE tags IN ('download_failed', 'error', 'error_no_tags', ...)` filter.
   - Step 6: As a result, `file_id` is added to `failed_set`.
   - Step 7: `enrich_extra_data` marks `is_orig_failed = True`, setting `f["original_url"] = ""` and `f["thumbnail_url"] = ""`, and `f["is_broken"] = True`.
   - Step 8: The post JSON delivered to the frontend contains empty `original_url` and empty `thumbnail_url`.
   - Step 9: The frontend cannot render the thumbnail because `thumbnail_url` is `""`.
   - Step 10: If the frontend tries to request `/files/{file_id}` directly, `/files/{file_id:path}` calls `is_file_permanently_failed(file_id)`, which also matches `tags = 'error_no_tags'` and immediately returns HTTP 404 Not Found!

2. **Secondary Issue — Thumbnail Fallback & Empty `thumbnail_url`**:
   - For single-file media (e.g., direct site uploads or single documents/videos), `file_info` often lacks a separate `thumbnail_file_id`.
   - In `_process_files_list`, if `thumbnail_file_id` is None, `file_info["thumbnail_url"]` is initialized to `""`.
   - `_select_mirror_strategically` retains `thumbnail_url = ""` if no thumbnail mirrors exist in `FileMirrors`.
   - When `is_thumb_failed` is True (e.g. thumbnail Telegram download failed), `enrich_extra_data` sets `thumbnail_url = ""` without falling back to `original_url` or `/files/{original_file_id}`.

3. **Physical File Path Resolution**:
   - There are no physical media files stored on disk under `site_tgach/files/` or `files/`.
   - All media files are stored remotely in Telegram storage channels or external mirrors (R2, Catbox, HuggingFace, 0x0.st, FreeImage, ImgBB, PixHost).
   - FastAPI `/files/{file_id:path}` acts as a dynamic async proxy server, fetching Telegram file paths via Telegram Bot API or redirecting (HTTP 307) to CDN mirrors.

---

## 3. Caveats

1. **Read-Only Inspection**: In accordance with task instructions, no production source code files were edited during this audit.
2. **Database State**: Existing rows in `FileRegistry` already marked with `tags = 'error_no_tags'` will need either a DB cleanup update (`UPDATE FileRegistry SET tags = '' WHERE tags = 'error_no_tags'`) or the removal of `'error_no_tags'` from `get_failed_files_batch` and `is_file_permanently_failed`.
3. **Frontend Dependency**: If frontend code specifically queries `/api/media/{file_id}`, it will encounter 404 since that route is not defined in FastAPI; frontend should use `/files/{file_id}`.

---

## 4. Conclusion

- **Primary Defect**: Over-inclusive failed media filter in `common/database.py` (`get_failed_files_batch` and `is_file_permanently_failed`). Valid media files that downloaded cleanly but received `tags = 'error_no_tags'` from the AI worker are misclassified as permanently broken, causing `enrich_extra_data` to wipe `original_url` and `thumbnail_url` to empty strings.
- **Secondary Defect**: Absence of `thumbnail_url` fallback to `original_url` when `thumbnail_file_id` is missing or when thumbnail download fails independently of the original file.
- **Routing Status**: `/files/{file_id:path}` route and its aliases (`/file/`, `/thumb/`, `/i/`, `/preview/`, `/{board_id}/src/`, `/{board_id}/thumb/`) are correctly defined in `site_tgach/main.py` and `Dubsite_tgach/main.py`. `/api/media/{file_id}` and `app.mount("/files")` do not exist.

---

## 5. Verification Method

To independently verify these findings:

1. **Inspect `common/database.py` lines 7736–7776**:
   - Observe SQL query in `get_failed_files_batch`:
     `WHERE (tags IN ('download_failed', 'error', 'error_no_tags', ...))`
   - Observe SQL query in `is_file_permanently_failed`:
     `WHERE (file_id = ? OR thumbnail_id = ?) AND (tags IN ('download_failed', 'error', 'error_no_tags', ...))`

2. **Inspect `site_tgach/tagging_worker.py` lines 791–792**:
   - Observe fallback tag assignment:
     `if not tags: tags = "error_no_tags"`

3. **Inspect `site_tgach/main.py` lines 3524–3536**:
   - Observe `enrich_extra_data` wiping URL fields when `fid` is in `failed_set`:
     ```python
     if is_orig_failed:
         f["is_broken"] = True
         f["original_url"] = ""
         f["thumbnail_url"] = ""
     ```

4. **Pytest Verification**:
   - Run `pytest tests/test_files_endpoint.py` to confirm route handling behavior.
