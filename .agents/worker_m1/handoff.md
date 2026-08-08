# Handoff Report — worker_m1 (HTML Anchor & Regex Fix)

**Agent**: `worker_m1` (teamwork_preview_worker)  
**Working Directory**: `C:\Users\danat\Desktop\dvachbot\.agents\worker_m1`  
**Date**: 2026-08-08  
**Milestone**: Milestone 1 (M1): HTML Anchor Rendering Fix  

---

## 1. Observation

Direct code observations from backend and frontend files before and after modifications:

1. **Backend `URL_PATTERN` (Before vs After)**:
   - `site_tgach/main.py:823` & `Dubsite_tgach/main.py:298`:
     - *Before*: `URL_PATTERN = re.compile(r'(https?://[^\s<>"\'`]+)')`
     - *After*: `URL_PATTERN = re.compile(r'(https?://[^\s<>"\'`&#;]+)')`
2. **Backend Attribute Sanitization**:
   - `common/text_utils.py:83-84`:
     - *Before*: `valid_a_tag = f'<a href="{val}">'`
     - *After*: `valid_a_tag = f'<a href="{html.escape(val, quote=True)}">'` (with `import html`)
3. **Frontend `formatTextGlobal` linkRegex**:
   - `site_tgach/static/js/main.src.js:227` & `site_tgach/static/js/main.js:227`:
     - *Before*: `const linkRegex = /(?<!["'=])(https?:\/\/[^\s<"']+)/g;`
     - *After*: `const linkRegex = /(?<!["'=])(https?:\/\/[^\s<"'\s&#;]+)/g;`
4. **Frontend `parseTextEffects` Nested Anchor Prevention**:
   - `site_tgach/static/js/main.src.js:11314` & `site_tgach/static/js/main.js:11314`:
     - *Before*:
       ```javascript
       const linkRegex = /(?<!["'=])(https?:\/\/[^\s<"']+)/g;
       html = html.replace(linkRegex, '<a href="$1" target="_blank" rel="noopener" class="auto-link">$1</a>');
       ```
     - *After*:
       ```javascript
       const linkRegex = /(<a\b[^>]*>[\s\S]*?<\/a>)|(?<!["'=])(https?:\/\/[^\s<"'\s&#;]+)/gi;
       html = html.replace(linkRegex, (match, g1, g2) => {
           if (g1) return g1;
           return `<a href="${g2}" target="_blank" rel="noopener" class="auto-link">${g2}</a>`;
       });
       ```

---

## 2. Logic Chain

1. **Step 1 (Root Cause of HTML Entity & Trailing Text Leak)**:
   When post text containing a single quote `'` and Cyrillic text after a URL (e.g. `>>1234 https://domain.com/b/res/343717.html'>ТГАЧ`) passed through `html.escape()`, `'` became `&#039;` (or `&#x27;`) and `>` became `&gt;`. The input string became `&gt;&gt;1234 https://domain.com/b/res/343717.html&#039;&gt;ТГАЧ`.
2. **Step 2 (Regex Matching Over Entity Boundaries)**:
   The old regexes `[^\s<>"'`]` in Python (`URL_PATTERN`) and JavaScript (`linkRegex`) did not exclude `&`, `#`, or `;`. Consequently, the URL match captured `https://domain.com/b/res/343717.html&#039;&gt;ТГАЧ` as the URL string. When placed in `<a href="...">`, the browser HTML parser decoded `&#039;&gt;` back into `'>`, generating the corrupted URL `href="https://domain.com/b/res/343717.html'>ТГАЧ"`.
3. **Step 3 (Fix for Entity Boundaries)**:
   By updating `URL_PATTERN` and `linkRegex` character classes to `[^\s<>"'`&#;]`, the URL matcher stops immediately upon reaching the `&` of any HTML entity boundary (`&#039;`, `&#x27;`, `&gt;`). The matched `$1` is strictly `https://domain.com/b/res/343717.html`, and `&#039;&gt;ТГАЧ` remains outside the anchor tag.
4. **Step 4 (Nested Anchor Prevention in `parseTextEffects`)**:
   In `parseTextEffects`, `container.innerHTML` may already contain `<a href="...">` elements created server-side or by `formatTextGlobal`. Running `linkRegex` blindly on `container.innerHTML` matched URLs inside existing `<a>...</a>` text nodes, generating nested `<a href="..."><a href="...">...</a></a>` elements. Using the regex replacer `/(<a\b[^>]*>[\s\S]*?<\/a>)|(?<!["'=])(https?:\/\/[^\s<"'\s&#;]+)/gi` ensures any existing `<a>` tag block matches group `$1` and is returned untouched, completely preventing nested anchor creation.

---

## 3. Caveats

- **Scope Boundary**: This milestone focused strictly on link parsing, regex hardening, quote sanitization, and double-rendering prevention (R1.1, R1.2, R1.3). Media download 404 fallback (M2) and worker download retries (M3) are handled in separate milestones.
- **Frontend Sync**: Both `main.src.js` AND `main.js` were updated in tandem to guarantee sync across dev and static serving pipelines.

---

## 4. Conclusion

Corrupted HTML anchor generation (`GET /b/res/343717.html'>ТГАЧ, 404`) and nested anchor tags are fully resolved. Both Python backend (`format_post_text`) and JS frontend (`formatTextGlobal`, `parseTextEffects`) now produce clean, uncorrupted, strictly double-quoted HTML anchor tags without entity leaks or trailing text inside `href`.

---

## 5. Verification Method

Independent verification can be executed via the following commands:

1. **Backend Python Test Suite**:
   ```powershell
   $env:PYTHONUTF8=1; python -m unittest tests/test_html_anchors.py
   ```
   *Expected Result*: `Ran 4 tests in 0.001s OK` (0 failures, 0 errors).

2. **Frontend JavaScript Test Suite**:
   ```powershell
   node tests/test_html_anchors_frontend.js
   ```
   *Expected Result*:
   - `✅ All tests passed for main.src.js`
   - `✅ All tests passed for main.js`
   - `🎉 Frontend HTML Anchor Verification Suite Succeeded!`
