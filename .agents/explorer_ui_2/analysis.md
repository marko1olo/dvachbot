# Technical Analysis: Frontend JS Media Rendering & Classes Audit (R1 - UI Layer Refactoring)

## Overview
This technical analysis covers the audit of frontend JS media rendering, Jinja2 SSR templates, DOM creation functions, error handlers, lazy-loading logic, and media class toggling in `site_tgach`.

- **Files Examined**:
  - `site_tgach/static/js/main.src.js` (15,041 lines, 706,493 bytes)
  - `site_tgach/static/js/main.js` (15,041 lines, 706,493 bytes, identical copy of `main.src.js`)
  - `site_tgach/templates/catalog.jinja2`
  - `site_tgach/templates/thread.jinja2`
  - `site_tgach/templates/board.jinja2`
  - `site_tgach/static/css/style.src.css`

---

## Key Findings & Identified Bugs

### 1. BUG #1 (CRITICAL): `createCatalogCard` Inconsistent Proxy URL Usage in `main.src.js`
- **Location**: `site_tgach/static/js/main.src.js` lines 11248–11268 (and `main.js`).
- **Code Inspection**:
  ```javascript
  const mediaUrl = f.original_url || (f.original_file_id ? `/files/${f.original_file_id}` : "");
  const thumbUrl = f.thumbnail_url || (f.thumbnail_file_id ? `/files/${f.thumbnail_file_id}` : "");

  if (typeof FailedMediaCache !== 'undefined' && ((mediaUrl && FailedMediaCache.isFailed(mediaUrl)) || (thumbUrl && FailedMediaCache.isFailed(thumbUrl)))) {
      thumbHtml = `<div class="catalog-thumb broken-media"...><span style="font-size:2em">⚠️</span></div>`;
  } else if (isVid) {
      const vidUrl = f.original_url || '';        // <-- BUG! Ignores mediaUrl
      const posterUrl = f.thumbnail_url || '';    // <-- BUG! Ignores thumbUrl
      if (vidUrl) {
          thumbHtml = `<div class="catalog-thumb lazy-media-wrapper"...><video data-src="${vidUrl}" poster="${posterUrl}"...></video></div>`;
      } else {
          thumbHtml = `<div class="catalog-thumb"...><span style="font-size:2em">⏳</span></div>`;
      }
  } else {
      const imgUrl = f.thumbnail_url || f.original_url;  // <-- BUG! Ignores thumbUrl & mediaUrl
      if (imgUrl) {
          thumbHtml = `<div class="catalog-thumb"><img src="..." data-src="${imgUrl}"... ></div>`;
      } else {
          thumbHtml = `<div class="catalog-thumb"...><span style="font-size:2em">🖼️</span></div>`;
      }
  }
  ```
- **Mechanism**: Lines 11248–11249 correctly compute `mediaUrl` and `thumbUrl` using `/files/{file_id}` proxy fallbacks when `original_url` or `thumbnail_url` are missing. However, lines 11254 (`vidUrl`), 11255 (`posterUrl`), and 11266 (`imgUrl`) bypass `mediaUrl` and `thumbUrl` and read raw `f.original_url` and `f.thumbnail_url`!
- **Impact**: When backend returns post objects using `/files/{file_id}` proxy URLs (where `original_url` or `thumbnail_url` are empty strings), `createCatalogCard` evaluates `vidUrl=""` and `imgUrl=""`, falling through to `⏳` and `🖼️` placeholder boxes instead of rendering image `<img data-src="/files/{file_id}">` or `<video data-src="/files/{file_id}">`.

---

### 2. BUG #2: Jinja2 SSR Templates Omit `/files/{file_id}` Proxy Endpoint Fallback
- **Location**:
  - `site_tgach/templates/catalog.jinja2` (lines 165–188)
  - `site_tgach/templates/thread.jinja2` (lines 299–304, 328, 339)
- **Code Inspection (`catalog.jinja2`)**:
  ```jinja2
  {% if thread.content.files and thread.content.files[0].thumbnail_url %}
      <img src="data:image/gif;base64..." data-src="{{ thread.content.files[0].thumbnail_url }}" ...>
  {% elif thread.content.files and thread.content.files[0].type in ['video', 'video_note', 'animation'] %}
      <video class="lazy-load..." data-src="{{ thread.content.files[0].original_url }}" {% if thread.content.files[0].thumbnail_url %}poster="{{ thread.content.files[0].thumbnail_url }}"{% endif %}>
  {% else %}
      <div class="catalog-ambient"><span>📝</span>...</div>
  {% endif %}
  ```
- **Code Inspection (`thread.jinja2`)**:
  ```jinja2
  <a href="{{ file.original_url }}" class="file-thumb" data-filename="{{ file.filename }}" data-file-id="{{ file.original_file_id }}" data-type="image">
      <img loading="lazy" src="data:image/gif;base64..." data-src="{{ file.thumbnail_url or file.original_url }}" ...>
  </a>
  ```
- **Mechanism**: The SSR Jinja2 templates check only `file.thumbnail_url` and `file.original_url`. They do NOT check `file.thumbnail_file_id` or `file.original_file_id` (or construct `/files/${file_id}`).
- **Impact**:
  - In catalog SSR (`catalog.jinja2`), if `thumbnail_url` is empty, Jinja2 skips the `<img>` tag completely and renders the `📝` ambient text placeholder.
  - In thread SSR (`thread.jinja2`), if `thumbnail_url` and `original_url` are empty strings, `data-src=""` is generated. `SmartLoader` sees empty `data-src` and skips lazy-loading, leaving a transparent 1x1 GIF placeholder visible on screen.

---

### 3. BUG #3: `SmartLoader` Video Error Handler Destroys DOM Without Proxy Fallback
- **Location**: `site_tgach/static/js/main.src.js` lines 14455–14461.
- **Code Inspection**:
  ```javascript
  img.onerror = () => {
      if (parent) {
          parent.classList.remove('is-loading');
          parent.classList.add('broken-media');
          parent.innerHTML = '<div style="font-size:2em; color:#555;">⚠️</div>';
      }
  };
  ```
- **Mechanism**: When `<video>` elements are processed by `SmartLoader.process()`, `img.onerror` is assigned an inline handler that immediately wipes out `parent.innerHTML` with a static `⚠️` placeholder div and adds `broken-media`. Unlike images, `<video>` elements in `SmartLoader` DO NOT delegate to `handleImageError(img)` and DO NOT attempt a proxy `/files/{file_id}` fallback.
- **Impact**: Any transient media network error or poster failure on `<video>` permanently destroys the video DOM element and replaces it with `⚠️`.

---

### 4. BUG #4: `handleImageError` `data-file-id` Attribute Mismatch
- **Location**: `site_tgach/static/js/main.src.js` lines 11494–11500 and `site_tgach/templates/thread.jinja2` lines 338–341.
- **Code Inspection**:
  ```javascript
  const fileId = img.dataset.fileId || (parent ? parent.dataset.fileId : null);
  if (fileId) {
      const localUrl = `/files/${fileId}`;
      ...
  }
  ```
- **Mechanism**: When `handleImageError` fires for a failed thumbnail, it attempts a fallback to `/files/${fileId}`. However, `thread.jinja2` places `data-file-id` ONLY on image `<a>` tags (line 299). Video wrappers `<div class="file-thumb lazy-media-wrapper">` (lines 338–341) do NOT include `data-file-id="{{ file.original_file_id }}"`.
- **Impact**: Fallback proxy endpoint resolution fails for video wrappers because `fileId` evaluates to `null`.

---

### 5. BUG #5: Unbounded Permanent Lock in `FailedMediaCache` Across Re-renders
- **Location**: `site_tgach/static/js/main.src.js` lines 218–241, 11014–11018, 11251–11252, 11363–11372, 11474–11479, 14385–14394, 14403–14411, 14427–14435.
- **Code Inspection**:
  - `FailedMediaCache` stores normalized URLs (`parsed.origin + parsed.pathname`) in an in-memory `Set`.
  - When `FailedMediaCache.markFailed(url)` is called (e.g. on a 404 from Telegram download worker before download completes), the URL `/files/{file_id}` is stored permanently for the browser session.
  - Across 5 different locations in `main.src.js` (`renderPost`, `createCatalogCard`, `initializePostFeatures`, `handleImageError`, `SmartLoader`), any media URL present in `FailedMediaCache` causes JS to immediately add class `broken-media` and overwrite `parent.innerHTML` with `<div class="broken-media"...>⚠️ Media Unavailable</div>`.
- **Impact**: If a file is requested before backend finished downloading it or during a brief network glitch, `FailedMediaCache` permanently locks out the thumbnail. Even after backend finishes downloading the file and `/files/{file_id}` starts returning 200 OK, frontend DOM updates will NEVER retry loading the media until a full hard browser refresh occurs.

---

## Summary of Handoff Proposals for Implementer

1. **Fix `createCatalogCard` in `main.src.js`**:
   - Change `vidUrl` to use `mediaUrl`.
   - Change `posterUrl` to use `thumbUrl`.
   - Change `imgUrl` to use `thumbUrl || mediaUrl`.

2. **Fix Jinja2 SSR Templates (`catalog.jinja2`, `thread.jinja2`)**:
   - In `catalog.jinja2`: Calculate `thumb_url = thread.content.files[0].thumbnail_url or (('/files/' ~ thread.content.files[0].thumbnail_file_id) if thread.content.files[0].thumbnail_file_id else ('/files/' ~ thread.content.files[0].original_file_id if thread.content.files[0].original_file_id else thread.content.files[0].original_url))`
   - In `thread.jinja2`: Ensure `data-src` and `poster` use fallback `/files/{thumbnail_file_id}` or `/files/{original_file_id}`.
   - Add `data-file-id="{{ file.original_file_id }}"` to `.lazy-media-wrapper` divs in `thread.jinja2`.

3. **Fix `SmartLoader` Video Error Handler**:
   - In `SmartLoader.process()`, change `<video>` error handler to invoke `handleImageError(img)` instead of overwriting `parent.innerHTML` directly.

4. **Sync `main.js` with `main.src.js`**:
   - Ensure changes made to `main.src.js` are mirrored in `main.js`.
