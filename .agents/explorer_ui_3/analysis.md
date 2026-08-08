# Technical Analysis: CSS Styles & Media Layout Audit (R1 - UI Layer Refactoring)

**Agent**: explorer_ui_3  
**Project**: dvachbot (`site_tgach`)  
**Date**: 2026-08-08  
**Scope**: `site_tgach/static/css/*.css` (`style.src.css`, `style.css`, `style.min.css`), Jinja2 templates (`site_tgach/templates/`), client JS (`site_tgach/static/js/main.src.js`).

---

## 1. Executive Summary

A comprehensive audit of the CSS stylesheets and Jinja2 templates for `site_tgach` was performed to identify why media thumbnails (`img`, `video`) fail to display, render as invisible/black boxes, or get replaced by `.broken-media` placeholders.

Key conclusions:
1. **CSS Default Opacity Gate (`opacity: 0`)**: `.post-image`, `.post-video`, and `.post-sticker` have `opacity: 0` by default in `style.src.css` (lines 554 & 565). They ONLY become visible (`opacity: 1 !important`) if JavaScript adds the `.loaded` class or if a `<video>` tag has a non-empty `poster="..."` attribute.
2. **`body.nsfw-mode` Force-Hiding**: In `style.css` (lines 9950–9980), `body.nsfw-mode` sets `opacity: 0 !important` or `opacity: 0.05 !important` across all `.post-image`, `.post-video`, `.post-sticker`, and `.file-thumb` elements, requiring mouse hover to reveal media.
3. **Template Fallback Defect in `catalog.jinja2`**: `catalog.jinja2` (line 165) strictly checks `{% if thread.content.files and thread.content.files[0].thumbnail_url %}`. If `thumbnail_url` is empty (`""` or `null`) while `original_url` is valid (e.g., `/files/abc.jpg`), `catalog.jinja2` skips rendering `<img>` completely and falls back to a text card (`catalog-ambient` with 📝 icon).
4. **`<video>` Element Visibility Trap**: `<video class="post-image lazy-load">` tags rendered without a `poster` attribute (when `thumbnail_url` is missing) start with `opacity: 0`. If `onloadeddata` does not fire (e.g. `preload="metadata"` or autoplay policy restriction), the video remains at `opacity: 0` (invisible black box).
5. **Early `loaded` Trigger on 1x1 Transparent GIF**: In `board.jinja2` (line 334) and `thread.jinja2` (line 305), `<img>` tags use `src="data:image/gif;base64,..."` with `onload="this.classList.add('loaded')"`. Because the transparent 1x1 GIF loads synchronously during DOM parsing, `.loaded` is added immediately—setting `opacity: 1 !important` on the 1x1 transparent GIF before `SmartLoader` replaces `src` with `data-src`.
6. **`.broken-media` Over-Application**: `.broken-media` replaces inner DOM elements when `FailedMediaCache.isFailed(url)` returns true or when network errors occur. If valid media URLs trigger temporary fetch errors, JS destroys the thumbnail container and injects static `⚠️ Media Unavailable` DOM nodes.

---

## 2. CSS File Inventory & Rule Analysis

### 2.1 CSS Files Searched
- `site_tgach/static/css/style.src.css` (Unminified canonical stylesheet, 10,131 lines)
- `site_tgach/static/css/style.css` (Compiled/active stylesheet)
- `site_tgach/static/css/style.min.css` (Minified stylesheet)

### 2.2 Selectors Affecting Media Elements

| Selector | File & Line | Key Styles / Properties | Effect on Media Visibility |
|---|---|---|---|
| `.post-image, .post-video, .post-sticker` | `style.src.css`: 547–555 | `display: block; width: 100%; height: 100%; max-height: 250px; object-fit: cover; opacity: 0;` | Default state is **100% INVISIBLE** (`opacity: 0`). |
| `.post-image, .post-sticker, .post-video` | `style.src.css`: 564–569 | `opacity: 0; transition: opacity 0.3s ease-in, filter 0.3s ease !important; will-change: opacity; background-color: rgba(0,0,0,0.1);` | Reinforces `opacity: 0`. |
| `.post-image.loaded, .post-sticker.loaded, .post-video.loaded, video[poster]:not([poster=""])` | `style.src.css`: 571–576, 10057 | `opacity: 1 !important; filter: none !important; visibility: visible !important; z-index: 10 !important;` | **ONLY mechanism** to make media visible. |
| `.file-thumb` | `style.src.css`: 535–541 | `display: block; max-width: 250px; min-height: 100px; min-width: 100px; border-radius: 4px; overflow: hidden;` | Outer wrapper container. |
| `.post-files-container:has(.file-thumb:nth-child(2)) .file-thumb` | `style.src.css`: 533 | `max-width: 122px;` | Restricts thumb size when post has multiple files. |
| `.catalog-thumb` | `style.src.css`: 1322–1329 | `width: 100%; height: 180px; position: relative; overflow: hidden;` | Catalog thumbnail container. |
| `.catalog-thumb img` | `style.src.css`: 1332–1338 | `width: 100%; height: 100%; object-fit: cover; object-position: top center;` | Catalog image sizing. |
| `.broken-media` | `style.src.css`: 589–593 | `background-color: var(--bg-button-secondary) !important; border: 1px dashed var(--border-input); display: flex; align-items: center; justify-content: center; flex-direction: column; color: var(--text-secondary); padding: 10px; cursor: not-allowed;` | Failed media replacement card. |
| `body.nsfw-mode .post-image, body.nsfw-mode .post-video, body.nsfw-mode .post-sticker` | `style.css`: 9950–9960 | `opacity: 0 !important; transition: opacity 0.2s ease-in-out !important;` | Forces `opacity: 0 !important` when NSFW mode is active. |
| `body.nsfw-mode .file-thumb:hover .post-image...` | `style.css`: 9962–9966 | `opacity: 1 !important; z-index: 5 !important;` | Hover override for NSFW mode. |
| `body.dim-mode .post-image, body.dim-mode .post-video` | `style.src.css`: 3364–3371 | `filter: grayscale(1); opacity: 0.5;` | Dim mode style reduction. |
| `.spoiler-img` | `style.src.css`: 3373–3377 | `filter: brightness(0.2) contrast(1.2); cursor: pointer;` | Censored/spoiler media dimming. |
| `.file-thumb video.post-image, .file-thumb video.lazy-load` | `style.src.css`: 9262–9264 | `pointer-events: none;` | Prevents native video controls clicks from intercepting lightbox. |
| `.file-thumb:has(.loaded) canvas, .lazy-media-wrapper:has(.loaded) canvas` | `style.src.css`: 10086–10089 | `opacity: 0 !important; pointer-events: none !important;` | Hides blurhash placeholder when `.loaded` is set. |

---

## 3. Specific CSS Hiding Rules Audit

1. **`opacity: 0` on Unloaded Media**:
   - `style.src.css`:554 and 565 set `opacity: 0` for `.post-image`, `.post-video`, and `.post-sticker`.
   - If JS fails to append `.loaded` class to the element, the image stays rendered in DOM but completely invisible to the user.

2. **`display: none` Rules**:
   - `.file-thumb::after`: `display: none;` (spinner hidden by default, shown when `.file-thumb:has(.post-image.is-loading)::after` is active).
   - `.file-thumb:has(.post-image.loaded) canvas.blurhash-canvas`: `display: none !important;` (hides blurhash canvas once loaded).
   - `.d-none`: `display: none !important;`.

3. **NSFW Mode Visibility Suppression**:
   - `body.nsfw-mode .post-image, body.nsfw-mode .post-video`: `opacity: 0 !important;`
   - `body.nsfw-mode .file-thumb:not(:has(.blurhash-canvas)) .post-image`: `opacity: 0.05 !important; filter: brightness(0.2) !important;`

---

## 4. `.broken-media` Styling & Application Audit

### 4.1 Styling Definition
```css
.broken-media {
    background-color: var(--bg-button-secondary) !important;
    border: 1px dashed var(--border-input);
    display: flex; align-items: center; justify-content: center; flex-direction: column;
    color: var(--text-secondary); font-size: 0.9em; padding: 10px; cursor: not-allowed;
}
.broken-media div { font-size: 2em; opacity: 0.5; margin-bottom: 5px; }
.broken-media span { font-size: 0.8em; text-align: center; }
```

### 4.2 Application Triggers in JS (`main.src.js`)
- **`SmartLoader.scan()`** (line 14385): Checks `FailedMediaCache.isFailed(src)`. If true, adds `broken-final` class and sets `parent.innerHTML = '<div class="broken-media">⚠️ Media Unavailable</div>'`.
- **`SmartLoader.enqueue()`** (line 14403): Same check before queueing.
- **`SmartLoader.process()`** (line 14427): If `targetSrc` is empty, null, or contains `"undefined"`, converts container to `.broken-media`.
- **`SmartLoader.onLoadFinished()`** (line 14530): If `img.onerror` fires and fallback sticker conversion fails, replaces element/container with `.broken-media`.
- **`createPostHTML()`** (lines 11015, 11252): If `FailedMediaCache.isFailed(url)` is true during post creation, generates inline HTML:
  ```html
  <div class="file-thumb broken-media" style="...">⚠️ Media Unavailable</div>
  ```

---

## 5. Jinja2 Template & Markup Defect Audit

### 5.1 Defect 1: `catalog.jinja2` Missing Fallback to `original_url`
- **Location**: `site_tgach/templates/catalog.jinja2` (lines 165–172)
- **Code**:
  ```jinja2
  {% if thread.content.files and thread.content.files[0].thumbnail_url %}
      <img src="data:image/gif;base64,..." 
           data-src="{{ thread.content.files[0].thumbnail_url }}" ...>
  {% elif thread.content.files and thread.content.files[0].type in ['video', 'video_note', 'animation'] %}
      ...
  {% else %}
      <div class="catalog-ambient"><span>📝</span>...</div>
  {% endif %}
  ```
- **Analysis**:
  When `thumbnail_url` is empty (`""` or `null`) but `original_url` is valid (e.g. `/files/12345.jpg`), `thread.content.files[0].thumbnail_url` evaluates to false. The template skips rendering `<img>` and displays the `catalog-ambient` text block ("📝").
- **Fix Requirement**: Update `catalog.jinja2` to check `{% if thread.content.files and (thread.content.files[0].thumbnail_url or thread.content.files[0].original_url) %}` and set `data-src="{{ thread.content.files[0].thumbnail_url or thread.content.files[0].original_url }}"`.

### 5.2 Defect 2: Inline `onload="this.classList.add('loaded')"` Premature Trigger
- **Location**: `site_tgach/templates/board.jinja2` (line 334), `thread.jinja2` (line 305)
- **Code**:
  ```html
  <img src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7" 
       data-src="{{ file.thumbnail_url or file.original_url }}" 
       class="post-image lazy-load" 
       onload="this.classList.add('loaded')">
  ```
- **Analysis**:
  The 1x1 base64 GIF in `src` completes loading synchronously when the DOM node is parsed. This fires `onload` immediately, adding `.loaded` to the `<img>` before `SmartLoader` updates `src` to `data-src`. This makes the 1x1 transparent image visible (`opacity: 1 !important`) prematurely.

### 5.3 Defect 3: `<video>` Without `poster` Remains Hidden (`opacity: 0`)
- **Location**: `board.jinja2` (line 375), `thread.jinja2` (line 345), `catalog.jinja2` (line 182), `main.src.js` (lines 11088, 11101)
- **Code**:
  ```html
  <video class="post-image lazy-load" data-src="{{ file.original_url }}" preload="metadata" muted playsinline loop></video>
  ```
- **Analysis**:
  The `<video>` has class `post-image`, giving it default CSS `opacity: 0`. It lacks a `poster` attribute when `thumbnail_url` is missing, so `video[poster]:not([poster=""])` does not match. If `onloadeddata` doesn't trigger, the video is completely invisible.

---

## 6. Actionable Proposals for Implementation Phase

1. **Jinja2 Template Repairs**:
   - `catalog.jinja2`: Change `if thread.content.files[0].thumbnail_url` to `if thread.content.files and (thread.content.files[0].thumbnail_url or thread.content.files[0].original_url)`. Use `data-src="{{ thread.content.files[0].thumbnail_url or thread.content.files[0].original_url }}"`.
   - `board.jinja2` & `thread.jinja2`: Remove premature inline `onload="this.classList.add('loaded')"` from transparent 1x1 GIF `<img src="data:...">`, letting `SmartLoader` handle `.loaded` addition when the actual target image loads. Ensure `<video>` elements get fallback poster or explicit `.loaded` state on metadata load.

2. **CSS Rules Hardening**:
   - Add explicit CSS fallback for visible media when `SmartLoader` is active:
     ```css
     .post-image[data-loaded="true"],
     .file-thumb img.loaded,
     .catalog-thumb img.loaded {
         opacity: 1 !important;
         visibility: visible !important;
     }
     ```
   - Ensure `<video.post-image>` inside `.lazy-media-wrapper` defaults to visible when playing or loaded:
     ```css
     .lazy-media-wrapper video {
         opacity: 1 !important;
     }
     ```

3. **`main.src.js` Media Handling Alignment**:
   - In `SmartLoader.onLoadFinished`, ensure `img.classList.add('loaded')` is dispatched for both images and videos regardless of whether `onloadeddata` or `onload` fired.
