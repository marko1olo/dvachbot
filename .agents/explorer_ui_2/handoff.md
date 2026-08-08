# Handoff Report: Frontend JS Media Rendering & Classes Audit (explorer_ui_2)

## 1. Observation
- Files audited:
  - `site_tgach/static/js/main.src.js` (15,041 lines, 706,493 bytes)
  - `site_tgach/static/js/main.js` (15,041 lines, 706,493 bytes, byte-for-byte identical copy)
  - `site_tgach/templates/catalog.jinja2` (lines 165–195)
  - `site_tgach/templates/thread.jinja2` (lines 299–356)
- Verbatim code defects observed:
  1. `createCatalogCard` (`main.src.js`:11254, 11255, 11266):
     ```javascript
     const mediaUrl = f.original_url || (f.original_file_id ? `/files/${f.original_file_id}` : "");
     const thumbUrl = f.thumbnail_url || (f.thumbnail_file_id ? `/files/${f.thumbnail_file_id}` : "");
     ...
     const vidUrl = f.original_url || '';        // <-- Ignores computed mediaUrl
     const posterUrl = f.thumbnail_url || '';    // <-- Ignores computed thumbUrl
     ...
     const imgUrl = f.thumbnail_url || f.original_url; // <-- Ignores computed thumbUrl/mediaUrl
     ```
  2. `catalog.jinja2`:165:
     ```jinja2
     {% if thread.content.files and thread.content.files[0].thumbnail_url %}
     ```
     Does not fallback to `thumbnail_file_id`, `original_file_id`, or `/files/...` proxy endpoints. Renders text ambient `📝` placeholder if `thumbnail_url` is empty string `""`.
  3. `SmartLoader.process` (`main.src.js`:14455–14461):
     ```javascript
     img.onerror = () => {
         if (parent) {
             parent.classList.remove('is-loading');
             parent.classList.add('broken-media');
             parent.innerHTML = '<div style="font-size:2em; color:#555;">⚠️</div>';
         }
     };
     ```
     Bypasses `handleImageError(img)` and overwrites `<video>` DOM nodes on load error without fallback attempt.
  4. `thread.jinja2`:338–341:
     Video wrapper `.lazy-media-wrapper` missing `data-file-id="{{ file.original_file_id }}"`, breaking `handleImageError` fallback lookup for videos.

---

## 2. Logic Chain
1. **Observation**: Backend endpoints enrich post media objects with `original_file_id` and `thumbnail_file_id` to route media through the local `/files/{file_id:path}` proxy endpoint when external Telegram URLs are sanitized or unavailable (`original_url=""`).
2. **Step 1**: In `createCatalogCard` (`main.src.js`), `mediaUrl` and `thumbUrl` are correctly computed with proxy fallbacks at lines 11248–11249 (`/files/${f.original_file_id}`). However, lines 11254, 11255, and 11266 read `f.original_url` and `f.thumbnail_url` directly. When these fields are empty strings, `vidUrl` and `imgUrl` evaluate to `""`, causing catalog items to fail rendering `<img>` or `<video>` elements and display `⏳` or `🖼️` fallback boxes instead.
3. **Step 2**: In `catalog.jinja2` (SSR), template condition `{% if thread.content.files[0].thumbnail_url %}` checks only raw `thumbnail_url`. It omits proxy fallback (`/files/{file_id}`). Thus, initial server-side HTML for catalog cards renders `📝` text boxes instead of thumbnail image tags whenever `thumbnail_url` is empty.
4. **Step 3**: In `thread.jinja2` (SSR), `data-src` and `poster` attributes use `{{ file.thumbnail_url or file.original_url }}`. If both are empty strings, `data-src=""` is generated. `SmartLoader` scans `data-src=""`, sees empty string, and skips lazy-loading, leaving transparent 1x1 GIF placeholders visible.
5. **Step 4**: In `SmartLoader.process()` (`main.src.js`), inline `img.onerror` for `<video>` elements immediately replaces parent HTML with `<div class="broken-media">⚠️</div>` instead of delegating to `handleImageError(img)` or trying `/files/{file_id}` fallback URLs.
6. **Conclusion**: Resolving these 4 key JS/Jinja2 defects will restore visible 200 OK media rendering across both `/b/catalog/` and `/b/res/*.html` thread pages.

---

## 3. Caveats
- No backend Python code was modified during this read-only audit.
- No direct browser Playwright execution was performed by `explorer_ui_2` (Playwright E2E simulation is assigned to downstream milestones UI-R2 / UI-R3).
- Findings are based strictly on static code audit of `main.src.js`, `main.js`, and Jinja2 templates.

---

## 4. Conclusion
The failure of media thumbnails to render in `site_tgach` is driven by UI-layer template and JS bugs:
1. `createCatalogCard` in `main.src.js` ignores computed `/files/{file_id}` proxy URLs for catalog items.
2. Jinja2 templates (`catalog.jinja2`, `thread.jinja2`) lack `/files/{file_id}` proxy fallback logic.
3. `SmartLoader` video error handling aggressively destroys video DOM elements on error.
4. `thread.jinja2` video wrappers lack `data-file-id` attributes required for `handleImageError` proxy fallback.

Fixing these issues in `main.src.js`, `main.js`, `catalog.jinja2`, and `thread.jinja2` will allow valid thumbnails to load cleanly via `/files/{file_id}` proxy routes without `broken-media` hiding.

---

## 5. Verification Method
1. Inspect `site_tgach/static/js/main.src.js` lines 11248–11268 to verify fix in `createCatalogCard`.
2. Inspect `site_tgach/templates/catalog.jinja2` lines 165–195 and `thread.jinja2` lines 299–356 to verify proxy fallbacks.
3. Run dev server: `python -m site_tgach.main` (or launch via uvicorn).
4. Run Playwright verification script to confirm HTTP 200 responses on `/files/...` and visible `<img src="/files/...">` thumbnail count > 0.
