# Media Endpoints Challenge & Stress Test Report

## Challenge Summary

**Overall risk assessment**: MEDIUM

Empirical stress testing was conducted against all media endpoint routes (`/files/`, `/file/`, `/thumb/`, `/i/`, `/preview/`, `/{board_id}/src/`, `/{board_id}/thumb/`), CORS headers, failover `skip` parameters, path-passed direct URLs, and filename query parameters. 

All 34 core assertions in `verification_scripts/media_loading_probe.py` passed successfully. However, empirical edge-case mining revealed critical parsing bugs in `skip` parameter failover, redirect code inconsistencies, header injection risks in `Content-Disposition`, and Windows locale encoding crash traps.

---

## Challenges

### [High] Challenge 1: Unstripped Whitespace & Case-Sensitivity in `skip` Parameter Parsing

- **Assumption challenged**: The system properly parses comma-separated mirror identifiers supplied in `?skip=...`.
- **Attack scenario**: A web browser or client application issues a request with whitespace after commas (e.g. `?skip=r2,%20freeimage`) or with non-lowercase characters (e.g. `?skip=R2,FREEIMAGE`).
- **Blast radius**: `site_tgach/main.py:10467` parses `skipped_types = set(skip.split(","))`. Unstripped whitespace creates set items like `' freeimage'`, while un-lowercased items create `'R2'`. As a result, `"freeimage" not in skipped_types` evaluates to `True`, completely bypassing mirror failover and redirecting the client to a mirror that was intended to be skipped.
- **Empirical Stress Result**:
  - `GET /file/test_skip?skip=r2,%20freeimage` -> Redirected to `https://freeimage.host/image.png` instead of `https://img1.pixhost.to/images/1/image.png` [FAIL]
  - `GET /file/test_skip?skip=R2,FREEIMAGE` -> Redirected to `https://r2.cdn.example.com/image.png` instead of skipping R2 [FAIL]
- **Suggested Defense**:
  Update line 10467 in `site_tgach/main.py`:
  ```python
  skipped_types = {s.strip().lower() for s in skip.split(",")} if skip else set()
  ```

---

### [Medium] Challenge 2: Direct URL 301 Permanent Redirect vs Mirror 307 Temporary Redirect & Cache Header Omission

- **Assumption challenged**: Direct URL routing (`file_id.startswith(("http:/", "https:/", ...))`) matches mirror redirect contracts.
- **Attack scenario**: A user requests a direct URL via `/file/http:/example.com/image.png`. The handler returns `HTTP 301 Moved Permanently` without `Cache-Control` / `no_cache_headers`.
- **Blast radius**: HTTP 301 responses are permanently cached by browsers and HTTP proxy caches. If the upstream target URL changes, recovers, or requires retry, client browsers will never re-fetch from the proxy endpoint. Furthermore, 301 redirects alter request methods (POST/HEAD to GET) in legacy HTTP clients, whereas 307 preserves request method and temporary nature.
- **Empirical Stress Result**:
  - `GET /file/http:/example.com/img.png` -> Returned HTTP 301 with `Access-Control-Allow-Origin: *`, missing `Cache-Control: no-store` headers present on 307 responses.
- **Suggested Defense**:
  Change line 10375 in `site_tgach/main.py` from `status_code=301` to `status_code=307` and merge `no_cache_headers`.

---

### [Medium] Challenge 3: Unsanitized `filename` Header Formatting in Proxied Streaming

- **Assumption challenged**: User-supplied `filename` query parameters are safely formatted into HTTP headers.
- **Attack scenario**: An attacker requests a proxied stream with double-quotes or special characters in the filename query param: `?filename=photo.png";+evil="1`.
- **Blast radius**: `site_tgach/main.py:10290` constructs `headers["Content-Disposition"] = f'inline; filename="{filename}"'`. Unescaped quotes allow header parameter manipulation or response header syntax errors.
- **Empirical Stress Result**:
  - `GET /file/probe_stream?...&filename=cool%20picture%20(1).png` -> Formatted as `inline; filename="cool picture (1).png"`. Unquoted injection strings pass directly into header values.
- **Suggested Defense**:
  Sanitize `filename` by stripping quotes/newlines or format using RFC 5987 / `urllib.parse.quote`.

---

### [Medium] Challenge 4: Windows Locale `cp1252` Encoding Crash on `.env` Import

- **Assumption challenged**: Module import of `site_tgach.main` works out-of-the-box on Windows systems.
- **Attack scenario**: Executing python scripts or running CLI tools on Windows without `PYTHONUTF8=1` environment variable set.
- **Blast radius**: `slowapi.Limiter` calls `starlette.config.Config(".env")` which uses system default locale (`cp1252` on Windows). `.env` contains UTF-8 Cyrillic bytes (e.g. at position 6724), causing an immediate `UnicodeDecodeError` during module load.
- **Empirical Stress Result**:
  - `python verification_scripts/media_loading_probe.py` (without `PYTHONUTF8=1`) -> Crashed with `UnicodeDecodeError: 'charmap' codec can't decode byte 0x90` [FAIL]
  - `$env:PYTHONUTF8="1"; python verification_scripts/media_loading_probe.py` -> Passed all 34 checks [PASS]
- **Suggested Defense**:
  Ensure default UTF-8 encoding configuration or explicit file opening in application config loaders.

---

## Stress Test Results Matrix

| Scenario | Target Endpoint | Expected Behavior | Actual Behavior | Result |
|---|---|---|---|---|
| Core Probe (34 Assertions) | `/files/`, `/file/`, `/thumb/`, `/i/`, `/preview/`, `/{board_id}/src/`, `/{board_id}/thumb/` | All 34 checks pass (307, Location, CORS, Stream PNG 200, Dead 404) | 34/34 Checks Passed | **PASS** |
| Multi-skip standard | `/file/test_skip?skip=r2,freeimage` | HTTP 307 -> `https://img1.pixhost.to/...` (pixhost) | HTTP 307 -> pixhost | **PASS** |
| Multi-skip with space | `/file/test_skip?skip=r2,%20freeimage` | HTTP 307 -> pixhost (strip space) | HTTP 307 -> freeimage (unstripped space bypass) | **FAIL** |
| Multi-skip uppercase | `/file/test_skip?skip=R2,FREEIMAGE` | HTTP 307 -> pixhost (case-insensitive) | HTTP 307 -> r2 (case mismatch bypass) | **FAIL** |
| Multi-skip empty element | `/file/test_skip?skip=r2,,freeimage` | HTTP 307 -> pixhost | HTTP 307 -> pixhost | **PASS** |
| Multi-skip trailing comma | `/file/test_skip?skip=r2,` | HTTP 307 -> freeimage | HTTP 307 -> freeimage | **PASS** |
| Direct URL `http:/` | `/file/http:/example.com/img.png` | HTTP 307/301 -> `http://example.com/img.png` | HTTP 301 -> Location: `http://example.com/img.png` | **PASS** |
| Direct URL `https:/` | `/file/https:/r2.cdn.example.com/photo.jpg` | HTTP 307/301 -> `https://r2.cdn.example.com/photo.jpg` | HTTP 301 -> Location: `https://r2.cdn.example.com/photo.jpg` | **PASS** |
| Direct URL CORS | `/file/http:/example.com/img.png` | CORS `Access-Control-Allow-Origin: *` | `Access-Control-Allow-Origin: *` present | **PASS** |
| Path filename in ID | `/files/probe_file_001/custom_name.png?skip=r2` | Splits ID (`probe_file_001`) and filename (`custom_name.png`) | HTTP 307 -> freeimage | **PASS** |
| Explicit `filename` param | `/file/probe_stream?...&filename=my_photo.png` | Stream 200 with `Content-Disposition: inline; filename="my_photo.png"` | `Content-Disposition` header present | **PASS** |
| Missing `filename` param | `/file/probe_stream?...` | Stream 200 with fallback filename | Fallback filename used | **PASS** |
| Empty `filename` param | `/file/probe_stream?...&filename=` | Stream 200 omitting empty header | `Content-Disposition` omitted | **PASS** |
| Special chars in filename | `/file/probe_stream?...&filename=cool%20picture%20(1).png` | Stream 200 with escaped header | Header formatted as `filename="cool picture (1).png"` | **PASS** |
| Dead File Mark | `/file/probe_dead_file_777` | Immediate HTTP 404 | HTTP 404 | **PASS** |
| HEAD method request | HEAD `/file/probe_file_001` | HTTP 307 with headers only | HTTP 307 with Location & CORS | **PASS** |

---

## Unchallenged Areas

- **Live Telegram Bot Downloads**: Actual Telegram API bot token fetching was mocked out in local unit/integration test mode to prevent external network traffic and API token consumption.
- **Physical R2 Storage S3 Credentials**: R2 CDN mirror link availability was tested via mock mirror metadata dictionary returns rather than active AWS S3 / Cloudflare API probes.
