# Technical Analysis: Jinja2 Templates Audit (UI Layer R1)

**Project**: dvachbot (`site_tgach/templates/`)  
**Auditor**: explorer_ui_1  
**Date**: 2026-08-08  
**Scope**: Complete audit of server-side Jinja2 template media rendering (`<img>`, `<video>`, `src`, `poster`, `/files/...` proxy routes, `is_broken`, `file_id`, CSS classes).

---

## 1. Executive Summary

A comprehensive audit of all 30 Jinja2 HTML templates in `site_tgach/templates/` was performed to evaluate server-side media rendering, URL generation, proxy routing, and CSS fallback behavior.

### Key Discoveries:
1. **Disappearing Thumbnails Bug in `catalog.jinja2` & `gallery.jinja2` (CRITICAL)**:
   - `catalog.jinja2` (line 165) and `gallery.jinja2` (line 132) contain restrictive template checks:
     `{% if thread.content.files and thread.content.files[0].thumbnail_url %}`
   - When a valid image file has an `original_url` pointing to `/files/{file_id}` but an empty `thumbnail_url` (`""`), the condition evaluates to **false**.
   - Instead of falling back to `original_url`, `catalog.jinja2` drops to `{% else %}` and renders a text ambient block (`📝`) with no `<img>` tag at all!
   - Similarly, `gallery.jinja2` skips rendering the image element entirely when `thumbnail_url` is empty string `""`.
2. **Proper Local Proxy Routing (`/files/{file_id:path}`)**:
   - Backend serialization in `site_tgach/main.py` (`_process_files_list` & `enrich_extra_data`) populates `original_url` and `thumbnail_url` with local proxy endpoints `/files/{file_id}` or strategic CDN mirrors.
   - Raw Telegram URLs (`https://api.telegram.org/...`) are **not hardcoded** in Jinja2 templates; templates render `{{ file.thumbnail_url or file.original_url }}`.
3. **Lazy Loading Placeholder Strategy**:
   - All main post templates (`board.jinja2`, `thread.jinja2`, `overboard.jinja2`, `chat.jinja2`, `search_results.jinja2`) use a 1x1 transparent GIF data URI as `src`:
     `src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"`
   - Real image URLs are stored in `data-src="{{ file.thumbnail_url or file.original_url }}"` alongside `class="post-image lazy-load"`.
4. **CSS Class & `is_broken` Audit**:
   - Templates apply `blurred-media` when `post.content.is_censored` is True.
   - Templates **do not** hardcode or apply a CSS class named `broken-media`.
   - When backend sets `is_broken: true`, `enrich_extra_data` clears `original_url=""` and `thumbnail_url=""`. `data-src` evaluates to `""`, leaving the loading to frontend JS (`main.src.js` `handleImageError` / `FailedMediaCache`).
5. **Inconsistent Video Note Markup**:
   - OP post video notes in `board.jinja2` and `thread.jinja2` use lazy `<video data-src="{{ file.original_url }}" poster="{{ file.thumbnail_url }}">`.
   - Reply video notes in `thread.jinja2` (line 571) use non-lazy `<video src="{{ file.original_url }}">` without `data-src` or `poster`.
   - Reply video notes in `board.jinja2` (line 508) use an `<img>` tag with `data-src="{{ file.thumbnail_url or '/static/img/vid.png' }}"`.

---

## 2. Template-by-Template Media Audit

### 2.1 `site_tgach/templates/board.jinja2`
- **OP Post Media (lines 324-388)**:
  - **Images/Photos/Stickers**:
    ```jinja2
    <a href="{{ file.original_url }}" class="file-thumb" data-filename="{{ file.filename }}" data-file-id="{{ file.original_file_id }}" data-type="image">
        {% if file.blurhash %}
            <canvas class="blurhash-canvas" data-hash="{{ file.blurhash }}" width="32" height="32"></canvas>
        {% endif %}
        <img src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7" 
            data-src="{{ file.thumbnail_url or file.original_url }}" 
            loading="lazy"
            class="post-image lazy-load{% if post.content.is_censored %} blurred-media{% endif %}" alt="..." referrerpolicy="no-referrer" onload="this.classList.add('loaded')">
        <noscript><img src="{{ file.original_url }}" alt="..."></noscript>
    </a>
    ```
  - **Video Notes (line 355)**:
    ```jinja2
    <video class="post-video video-note lazy-load{% if post.content.is_censored %} blurred-media{% endif %}" 
           data-src="{{ file.original_url }}" 
           poster="{{ file.thumbnail_url }}"
           autoplay loop muted playsinline ... referrerpolicy="no-referrer">
    </video>
    ```
  - **Videos / GIFs / Animations (lines 367-385)**:
    ```jinja2
    <video class="post-image lazy-load{% if post.content.is_censored %} blurred-media{% endif %}" 
           preload="metadata" muted playsinline loop
           data-src="{{ file.original_url }}"
           {% if file.thumbnail_url %}poster="{{ file.thumbnail_url }}"{% endif %} ...>
    </video>
    ```
- **Latest Replies Media (lines 474-533)**:
  - Images: Uses `data-src="{{ file.thumbnail_url or file.original_url }}"`.
  - Video Notes (line 508): Renders thumbnail via `<img>` tag with `data-src="{{ file.thumbnail_url or '/static/img/vid.png' }}"`.

### 2.2 `site_tgach/templates/catalog.jinja2`
- **Catalog Card Thumbnail (lines 165-195)**:
  ```jinja2
  {% if thread.content.files and thread.content.files[0].thumbnail_url %}
      <img src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7" 
           data-src="{{ thread.content.files[0].thumbnail_url }}" 
           class="lazy-load{% if thread.content.is_censored %} blurred-media{% endif %}" 
           alt="..." loading="lazy" referrerpolicy="no-referrer">
  {% elif thread.content.files and thread.content.files[0].type in ['video', 'video_note', 'animation'] %}
      <video class="lazy-load{% if thread.content.is_censored %} blurred-media{% endif %}" 
             preload="metadata" muted playsinline loop
             data-src="{{ thread.content.files[0].original_url }}"
             {% if thread.content.files[0].thumbnail_url %}poster="{{ thread.content.files[0].thumbnail_url }}"{% endif %} ...>
      </video>
  {% else %}
      <div class="catalog-ambient">
          <span>📝</span>
          <small>{{ thread.content.text | safe | striptags | truncate(40) }}</small>
      </div>
  {% endif %}
  ```
- **CRITICAL BUG**: `and thread.content.files[0].thumbnail_url` requirement.
  - If `file.thumbnail_url` is `""` or `None`, but `file.original_url` is `"/files/12345.jpg"`, Jinja2 skips the `<img>` block AND the `<video>` block and executes `{% else %}`, rendering text `📝` instead of the image thumbnail!
  - **Fix**: Change condition to:
    `{% if thread.content.files and (thread.content.files[0].thumbnail_url or thread.content.files[0].original_url) %}`
    and use `data-src="{{ thread.content.files[0].thumbnail_url or thread.content.files[0].original_url }}"`.

### 2.3 `site_tgach/templates/thread.jinja2`
- **OP Post Media (lines 298-356)**:
  - Images: `data-src="{{ file.thumbnail_url or file.original_url }}"`.
  - Video Notes: `data-src="{{ file.original_url }}" poster="{{ file.thumbnail_url }}"`.
  - Video/GIF: `data-src="{{ file.original_url }}" {% if file.thumbnail_url %}poster="{{ file.thumbnail_url }}"{% endif %}`.
- **Replies Media (lines 544-588)**:
  - Images: `data-src="{{ file.thumbnail_url or file.original_url }}"`.
  - Video Notes (line 571):
    `<video class="post-video video-note{% if reply.content.is_censored %} blurred-media{% endif %}" src="{{ file.original_url }}" autoplay loop muted playsinline ...>`
    - **INCONSISTENCY**: Uses direct `src` instead of `data-src` lazy loading and omits `poster="{{ file.thumbnail_url }}"`.

### 2.4 `site_tgach/templates/gallery.jinja2`
- **Gallery Grid Items (lines 132-151)**:
  ```jinja2
  {% if file.type in ['image', 'photo', 'sticker', 'gif'] and file.thumbnail_url %}
      <img loading="lazy" src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7" 
           data-src="{{ file.thumbnail_url }}" 
           class="lazy-load" alt="{{ file.filename }}" referrerpolicy="no-referrer">
  ```
- **CRITICAL BUG**: Same as catalog! Requires `and file.thumbnail_url`. If `thumbnail_url` is `""`, image is not rendered in gallery even if `original_url` exists.
- **Fix**: Change to `and (file.thumbnail_url or file.original_url)` and `data-src="{{ file.thumbnail_url or file.original_url }}"`.

### 2.5 `site_tgach/templates/overboard.jinja2`
- **Feed Posts & Latest Replies (lines 198-232, 323)**:
  - Images: `data-src="{{ file.thumbnail_url or file.original_url }}"`.
  - Video/GIF: `data-src="{{ file.original_url }}" {% if file.thumbnail_url %}poster="{{ file.thumbnail_url }}"{% endif %}`.
  - Properly uses fallback `thumbnail_url or original_url`.

### 2.6 `site_tgach/templates/search_results.jinja2`
- **Tag Search & Post Search (lines 111-131, 163-195)**:
  - Images: `data-src="{{ file.thumbnail_url or file.original_url }}"`.
  - Video/GIF: `data-src="{{ file.original_url }}" {% if file.thumbnail_url %}poster="{{ file.thumbnail_url }}"{% endif %}`.

### 2.7 `site_tgach/templates/chat.jinja2`
- **Chat Posts (lines 236-291)**:
  - Images: `data-src="{{ file.thumbnail_url or file.original_url }}"`.
  - Sticker (line 258): Includes `onerror="handleImageError(this)"`.
  - Video Note (line 263): Uses direct `src="{{ file.original_url }}"`.

---

## 3. Attribute & Route Audit Summary

| Component / Template | Attribute Evaluated | Target Endpoint Format | Fallback Behavior | Audit Finding |
|----------------------|---------------------|------------------------|-------------------|---------------|
| `board.jinja2` (OP) | `img.data-src` | `/files/{file_id}` | `file.thumbnail_url or file.original_url` | PASS |
| `board.jinja2` (OP) | `video.poster` | `/files/{file_id}` | `{% if file.thumbnail_url %}poster=...{% endif %}` | PASS |
| `board.jinja2` (Reply) | `video-note img` | `/files/{file_id}` | `file.thumbnail_url or '/static/img/vid.png'` | PASS (uses static img) |
| `catalog.jinja2` | `img.data-src` | `/files/{file_id}` | `file.thumbnail_url` **ONLY** | **FAIL**: Fails to fallback to `original_url`, hides image |
| `thread.jinja2` (OP) | `img.data-src` | `/files/{file_id}` | `file.thumbnail_url or file.original_url` | PASS |
| `thread.jinja2` (Reply) | `video.src` | `/files/{file_id}` | Direct `src="{{ file.original_url }}"` | WARNING: Non-lazy, missing poster |
| `gallery.jinja2` | `img.data-src` | `/files/{file_id}` | `file.thumbnail_url` **ONLY** | **FAIL**: Fails to fallback to `original_url` |
| `overboard.jinja2` | `img.data-src` | `/files/{file_id}` | `file.thumbnail_url or file.original_url` | PASS |
| `search_results.jinja2`| `img.data-src` | `/files/{file_id}` | `file.thumbnail_url or file.original_url` | PASS |
| `chat.jinja2` | `img.data-src` | `/files/{file_id}` | `file.thumbnail_url or file.original_url` | PASS |

---

## 4. CSS & Error State Audit

1. **CSS Classes**:
   - `blurred-media`: Applied dynamically via `{% if post.content.is_censored %} blurred-media{% endif %}` across all templates.
   - `broken-media`: **Not applied** in any Jinja2 template file.
2. **`is_broken` and `file_id` Handling**:
   - Backend `enrich_extra_data` handles broken media by clearing URLs (`original_url = ""`, `thumbnail_url = ""`) and setting `is_broken = True`.
   - When URLs are empty, `data-src` renders as `""`.
   - Client-side JS `main.src.js` handles empty `data-src` or 404 image load errors by replacing broken `<img>` elements with `⚠️` placeholder icons and recording the URL in `FailedMediaCache`.

---

## 5. Specific Remediation Plan for Implementer

To complete Milestone UI-R1 (Feature 20), the Implementer agent should apply the following precise edits to Jinja2 templates:

1. **`site_tgach/templates/catalog.jinja2` (Line 165)**:
   - Change:
     ```jinja2
     {% if thread.content.files and thread.content.files[0].thumbnail_url %}
         <img src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7" 
              data-src="{{ thread.content.files[0].thumbnail_url }}" 
     ```
   - To:
     ```jinja2
     {% if thread.content.files and (thread.content.files[0].thumbnail_url or thread.content.files[0].original_url) %}
         <img src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7" 
              data-src="{{ thread.content.files[0].thumbnail_url or thread.content.files[0].original_url }}" 
     ```

2. **`site_tgach/templates/gallery.jinja2` (Line 132)**:
   - Change:
     ```jinja2
     {% if file.type in ['image', 'photo', 'sticker', 'gif'] and file.thumbnail_url %}
         <img loading="lazy" src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7" 
              data-src="{{ file.thumbnail_url }}" 
     ```
   - To:
     ```jinja2
     {% if file.type in ['image', 'photo', 'sticker', 'gif'] and (file.thumbnail_url or file.original_url) %}
         <img loading="lazy" src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7" 
              data-src="{{ file.thumbnail_url or file.original_url }}" 
     ```

3. **`site_tgach/templates/thread.jinja2` (Line 571)**:
   - Normalize reply video note tag to include `data-src`, `poster="{{ file.thumbnail_url }}"`, and `lazy-load` class for consistency with OP posts.
