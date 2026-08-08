# Handoff Report — Frontend JS Media Rendering Audit

## 1. Observation

Direct code examination of `site_tgach/static/js/main.src.js`, `site_tgach/static/js/main.js`, `site_tgach/templates/board.jinja2`, `site_tgach/templates/thread.jinja2`, and `site_tgach/main.py`:

### Key Locations & Verbatim Code:

1. **`FailedMediaCache` Normalization** (`site_tgach/static/js/main.src.js:218-241`):
   ```javascript
   const FailedMediaCache = {
       _failedUrls: new Set(),
       normalizeUrl(url) {
           if (!url) return '';
           try {
               const loc = (typeof window !== 'undefined' && window.location) ? window.location.href : 'http://localhost';
               const parsed = new URL(url, loc);
               return parsed.origin + parsed.pathname;
           } catch (e) {
               return String(url).split('?')[0].split('#')[0];
           }
       },
       markFailed(url) {
           const key = this.normalizeUrl(url);
           if (key) this._failedUrls.add(key);
       },
       isFailed(url) {
           const key = this.normalizeUrl(url);
           return key ? this._failedUrls.has(key) : false;
       }
   };
   ```

2. **`handleImageError` Failure Handler** (`site_tgach/static/js/main.src.js:11449-11501`):
   ```javascript
   function handleImageError(img) {
       if (!img) return;
       img.onerror = null;
       if (img.dataset.finalError) return;
       img.dataset.finalError = "true";

       const parent = img.closest('.file-thumb, .lazy-media-wrapper, .sticker-wrapper, .catalog-thumb');
       const currentSrc = img.src || img.dataset.src || "";
       const originalUrl = parent ? (parent.href || parent.dataset.src || currentSrc) : (img.dataset.src || currentSrc);

       const renderStaticError = () => {
           img.classList.add('broken-final');
           if (parent) {
               parent.classList.remove('is-loading');
               parent.classList.add('broken-media');
               parent.innerHTML = `<div class="broken-media" title="Media Unavailable" style="...">⚠️ Media Unavailable</div>`;
           } else {
               img.style.display = 'none';
           }
       };

       if (typeof FailedMediaCache !== 'undefined') {
           if (FailedMediaCache.isFailed(originalUrl) || FailedMediaCache.isFailed(currentSrc)) {
               renderStaticError();
               return;
           }
       }
       ...
       if (isLocalFile) {
           if (typeof FailedMediaCache !== 'undefined') {
               FailedMediaCache.markFailed(originalUrl);
               FailedMediaCache.markFailed(currentSrc);
           }
           renderStaticError();
           return;
       }
   ```

3. **`SmartLoader.process` & `onLoadFinished`** (`site_tgach/static/js/main.src.js:14388-14513`):
   - Line 14406 counter underflow:
     ```javascript
     if (!targetSrc || targetSrc.includes('undefined') || targetSrc.includes('null') || (typeof FailedMediaCache !== 'undefined' && FailedMediaCache.isFailed(targetSrc))) {
         ...
         this.activeCount--; // Decrements activeCount BEFORE it was incremented at line 14411!
         if (parent) parent.classList.remove('is-loading');
         this.process();
         return;
     }
     this.activeCount++;
     ```
   - Lines 14498-14509 premature `markFailed`:
     ```javascript
     const baseUrl = img.dataset.src || img.src;
     if (baseUrl && typeof FailedMediaCache !== 'undefined') {
         FailedMediaCache.markFailed(baseUrl);
     }
     img.classList.add('broken-final');
     if (typeof handleImageError === 'function') {
         handleImageError(img);
     }
     ```

4. **`PostRenderer.create` Media Check** (`site_tgach/static/js/main.src.js:11014`):
   ```javascript
   if (typeof FailedMediaCache !== 'undefined' && ((url && FailedMediaCache.isFailed(url)) || (thumbCandidate && FailedMediaCache.isFailed(thumbCandidate)))) {
       imgContent += `<div class="file-thumb broken-media" style="...">⚠️ Media Unavailable</div>`;
       return;
   }
   ```

5. **Jinja2 Templates Media Rendering** (`site_tgach/templates/board.jinja2:331-334`, `site_tgach/templates/thread.jinja2:303-305`):
   ```html
   <img src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7" 
       data-src="{{ file.thumbnail_url or file.original_url }}" 
       loading="lazy"
       class="post-image lazy-load{% if post.content.is_censored %} blurred-media{% endif %}" referrerpolicy="no-referrer" onload="this.classList.add('loaded')">
   ```

---

## 2. Logic Chain

1. **JSON Schema Analysis**:
   - Backend `enrich_extra_data` in `site_tgach/main.py:3531-3545` and `_process_files_list` in `site_tgach/main.py:3674-3696` populate `p["content"]["files"]` with:
     - `original_url`: e.g. `/files/12345/image.jpg`
     - `thumbnail_url`: e.g. `/files/12345_thumb` (or `""` if no thumbnail file ID exists).
     - `is_broken`: `true` (if download failed).
   - Property names (`original_url`, `thumbnail_url`, `files`) match between backend and frontend Jinja2 templates/JS code. No JSON property name mismatch exists.

2. **Root Cause #1 — Premature Marking of Original Image URL on Thumbnail 404**:
   - When a post renders, `img` tags are rendered with `data-src` pointing to `file.thumbnail_url` (e.g. `/files/12345_thumb`) and wrapped in an `<a>` tag with `href` pointing to `file.original_url` (e.g. `/files/12345/image.jpg`).
   - If the thumbnail `/files/12345_thumb` returns HTTP 404 (e.g., thumbnail generation failed or thumbnail file is missing), `SmartLoader.onLoadFinished` or `handleImageError` is invoked for `img`.
   - `handleImageError` (`main.src.js:11458`) extracts `originalUrl` from `parent.href` (`/files/12345/image.jpg`).
   - `handleImageError` (`main.src.js:11496-11497`) executes:
     `FailedMediaCache.markFailed(originalUrl);`
     `FailedMediaCache.markFailed(currentSrc);`
   - **Crucial flaw**: `handleImageError` marks `originalUrl` (`/files/12345/image.jpg`) as FAILED in `FailedMediaCache`, EVEN THOUGH the full original file physically exists on the server!
   - Because `originalUrl` is now stored in `FailedMediaCache`, all future checks `FailedMediaCache.isFailed(originalUrl)` return `true`.
   - `PostRenderer.create` (`main.src.js:11014`) and `SmartLoader.scan` (`main.src.js:14355`) see `FailedMediaCache.isFailed(originalUrl) === true` and immediately replace the valid original image with a static `⚠️ Media Unavailable` placeholder across the session!

3. **Root Cause #2 — Lack of Fallback from Thumbnail to Original Image URL**:
   - When a thumbnail image fails to load, `handleImageError` does NOT attempt to set `img.src = originalUrl` as a fallback.
   - Instead, it immediately wipes out the `<img>` element and replaces `parent.innerHTML` with `⚠️ Media Unavailable`.
   - If thumbnails fail or are missing, valid full-size media are never given a chance to display as thumbnails.

4. **Root Cause #3 — `SmartLoader` Premature `markFailed` & Order-of-Execution Override**:
   - In `SmartLoader.onLoadFinished` (`main.src.js:14500`), `SmartLoader` calls `FailedMediaCache.markFailed(baseUrl)` BEFORE calling `handleImageError(img)` (`main.src.js:14504`).
   - When `handleImageError(img)` runs, its initial check (`main.src.js:11472`): `if (FailedMediaCache.isFailed(currentSrc))` evaluates to `true` because `SmartLoader` just inserted `currentSrc` into `FailedMediaCache`.
   - As a result, `handleImageError` immediately returns `renderStaticError()`, bypassing any host-skipping or fallback logic that `handleImageError` might have performed.

5. **Root Cause #4 — `FailedMediaCache` Data URI Cache Pollution**:
   - `FailedMediaCache.normalizeUrl(url)` (`main.src.js:224`) executes `new URL(url, loc)` and returns `parsed.origin + parsed.pathname`.
   - For 1x1 GIF placeholder data URIs (`data:image/gif;base64,...`), `parsed.origin` is `"null"`, returning `"nullimage/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"`.
   - If `markFailed` is called with `data:image/gif;...` (which occurs if `img.dataset.src` is missing/empty and `img.src` is passed to `markFailed`), `FailedMediaCache` stores the placeholder URI.
   - Since ALL lazy-loaded images initially have `src="data:image/gif;..."`, every `FailedMediaCache.isFailed(img.src)` call returns `true`, instantly breaking every thumbnail on the page.

6. **Root Cause #5 — `SmartLoader.process` Concurrency Throttling Counter Corruption**:
   - In `SmartLoader.process` (`main.src.js:14406`), `this.activeCount--` is called when an image has a missing or failed `targetSrc`.
   - However, `this.activeCount` was NOT incremented for that image yet (increment occurs on line 14411).
   - This causes `this.activeCount` to go negative (-1, -2, -3...), corrupting concurrency control and breaking queue scheduling.

---

## 3. Caveats

- **No backend changes analyzed in this report**: Backend media proxy routes in `site_tgach/main.py` (e.g. `/files/{file_id}`) and worker status logic in `site_tgach/tagging_worker.py` are outside frontend JS static analysis scope, but must serve valid HTTP status codes (200 for existing files, 404 for missing files).
- **Static analysis scope**: Findings are derived from code audit of `main.src.js`, `main.js`, `board.jinja2`, `thread.jinja2`, and `main.py`. Execution proof via Playwright will be conducted in downstream tasks.

---

## 4. Conclusion

The disappearance of media thumbnails is caused by **five specific logic flaws in frontend JavaScript** (`site_tgach/static/js/main.src.js` and `site_tgach/static/js/main.js`):

1. **Premature Original URL Marking**: When a thumbnail 404s, `handleImageError` (`line 11496`) marks the full image URL (`parent.href`) as failed in `FailedMediaCache`, breaking valid original images.
2. **Missing Thumbnail Fallback**: `handleImageError` (`line 11449`) lacks fallback logic to swap `img.src` to `originalUrl` when `thumbnail_url` 404s.
3. **Premature `SmartLoader` Failure Marking**: `SmartLoader.onLoadFinished` (`line 14500`) calls `FailedMediaCache.markFailed(baseUrl)` before `handleImageError` executes, triggering early termination in `handleImageError`.
4. **Data URI Cache Pollution**: `FailedMediaCache.normalizeUrl` (`line 220`) does not ignore `data:` URIs, allowing 1x1 GIF placeholders to pollute the cache and disable all images.
5. **Counter Underflow in `SmartLoader`**: `SmartLoader.process` (`line 14406`) decrements `this.activeCount` before incrementing it, corrupting queue state.

### Recommended Frontend Code Fixes (for Implementer Agent):

#### Fix 1: Guard `FailedMediaCache.normalizeUrl` against Data URIs
In `site_tgach/static/js/main.src.js` (and `main.js`) lines 220-229:
```javascript
normalizeUrl(url) {
    if (!url || typeof url !== 'string' || url.startsWith('data:')) return '';
    try {
        const loc = (typeof window !== 'undefined' && window.location) ? window.location.href : 'http://localhost';
        const parsed = new URL(url, loc);
        return parsed.origin + parsed.pathname;
    } catch (e) {
        return String(url).split('?')[0].split('#')[0];
    }
}
```

#### Fix 2: Implement Fallback Chain in `handleImageError` & Prevent Premature Original URL Marking
In `site_tgach/static/js/main.src.js` (and `main.js`) lines 11449-11501:
- When `img.src` (thumbnail URL) fails, check if `originalUrl` is different from `currentSrc`.
- If `originalUrl` is valid and NOT marked in `FailedMediaCache`, attempt loading `originalUrl` (`img.src = originalUrl`) before marking media as broken.
- Only mark `currentSrc` (the specific failed thumbnail URL) in `FailedMediaCache`, NOT `originalUrl`, unless `originalUrl` itself failed to load.

#### Fix 3: Fix `SmartLoader.onLoadFinished` Failure Delegation
In `site_tgach/static/js/main.src.js` (and `main.js`) lines 14498-14509:
- Remove premature `FailedMediaCache.markFailed(baseUrl)` call inside `onLoadFinished`.
- Allow `handleImageError(img)` to evaluate and handle fallback logic first.

#### Fix 4: Fix `SmartLoader.process` Counter Underflow
In `site_tgach/static/js/main.src.js` (and `main.js`) line 14406:
- Remove `this.activeCount--;` from the early exit branch where `activeCount` had not yet been incremented.

#### Fix 5: Refine `PostRenderer.create` `FailedMediaCache` Check
In `site_tgach/static/js/main.src.js` (and `main.js`) line 11014:
- Only render `⚠️ Media Unavailable` if the full original `url` is in `FailedMediaCache`. If only `thumbCandidate` is failed, fallback `thumbCandidate = url` and render the `<img>` tag using `url`.

---

## 5. Verification Method

To verify these fixes:

1. **Files to inspect**:
   - `site_tgach/static/js/main.src.js`
   - `site_tgach/static/js/main.js`

2. **Automated Verification Script**:
   - Run Playwright test script (`scratch_playwright_test.py`) to open `/b/` and a thread containing media.
   - Assert `page.locator('img.post-image, video.post-image').count() > 0`.
   - Verify network requests to `/files/...` return HTTP 200 OK.
   - Take screenshot `scratch/playwright_after.png` and verify visual rendering of thumbnails.

3. **Invalidation Conditions**:
   - If `FailedMediaCache` still stores `data:image/gif;...` keys.
   - If `handleImageError` marks `parent.href` on a thumbnail 404 error without fallback.
   - If `SmartLoader.activeCount` drops below 0.
