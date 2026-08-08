# Handoff Report — UI Challenger 2 (challenger_ui_2)

## 1. Observation
- **Required Backend Pytest Suite Execution**:
  - Command: `.\venv\Scripts\python.exe -m pytest tests/test_files_endpoint.py tests/test_backup.py tests/test_check_ddos.py`
  - Result: `25 passed, 3 warnings in 20.05s`
  - Breakdown:
    - `tests/test_files_endpoint.py`: 6 passed
    - `tests/test_backup.py`: 3 passed
    - `tests/test_check_ddos.py`: 16 passed

- **Empirical Media Proxy Endpoint & Adversarial Validation Suite**:
  - Test Harness File: `scratch/empirical_proxy_test.py`
  - Execution Command: `.\venv\Scripts\python.exe -m pytest scratch/empirical_proxy_test.py`
  - Result: `8 passed, 1 failed in 20.15s`

- **Functional Test Results (8 Passed)**:
  1. `test_route_aliases_consistency`: Verified 7 route aliases (`/files/`, `/file/`, `/thumb/`, `/i/`, `/preview/`, `/{board}/src/`, `/{board}/thumb/`) return HTTP 307 redirect with CORS `Access-Control-Allow-Origin: *`. (PASS)
  2. `test_binary_payload_and_headers_proxying`: Verified streaming proxy payload delivery with `HTTP 200 OK`, `Content-Type: image/png`, `Cache-Control: public, max-age=86400`, `Access-Control-Allow-Origin: *`, and byte-level payload integrity. (PASS)
  3. `test_fast_fail_database_permanent_failure`: Verified DB permanent failure (`is_file_permanently_failed`) fast-fails with HTTP 404 in `< 0.2s`. (PASS)
  4. `test_fast_fail_redis_dead_file`: Verified Redis dead file flag (`dead_file:public:{file_id}`) fast-fails with HTTP 404 in `< 0.2s` without sleeping through 8 retry attempts. (PASS)
  5. `test_thumbnail_agac_fallback_to_original`: Verified thumbnail fallback via `FileRegistry` DB lookup to original file when thumbnail mirror is missing. (PASS)
  6. `test_direct_original_file_request`: Verified original file requests resolve to configured mirror/telegram URLs. (PASS)
  7. `test_skip_filtering_and_normalization`: Verified `?skip=` parameter filtering and whitespace/case normalization. (PASS)
  8. `test_direct_url_in_file_id_redirect`: Verified embedded direct URLs in `/files/https://...` return HTTP 301 redirect with CORS headers. (PASS)

- **Adversarial Failure Case Discovered (1 Failed)**:
  - Test: `test_cache_poisoning_non_dict_mirrors`
  - Failure Log:
    ```text
    File "C:\Users\danat\Desktop\dvachbot\site_tgach\main.py", line 10540, in get_telegram_file
        hf_candidate = mirrors.get("huggingface")
    AttributeError: 'int' object has no attribute 'get'
    HTTP Request: GET http://testserver/files/poisoned_cache_file_123 "HTTP/1.1 500 Internal Server Error"
    ```
  - Exact Cause: In `site_tgach/main.py` (lines 10526-10532), cached JSON from Redis/FastAPICache is parsed via `json.loads(cached)`. If `cached` contains primitive non-dict JSON (e.g. `"1"` or `"true"` or `"\"str\""`), `json.loads` returns an `int` or string instead of a dictionary. Because there is no `isinstance(mirrors, dict)` validation check, subsequent lines (`mirrors.get("huggingface")`, `mirrors.get("catbox")`, etc.) raise an uncaught `AttributeError: 'int' object has no attribute 'get'`, resulting in an HTTP 500 Internal Server Error.

## 2. Logic Chain
1. The 25 existing unit tests passed cleanly, and all 8 primary functional requirements for media proxying (headers, binary streaming, fast-fail, thumbnail fallback, skip filters) operate properly under normal conditions.
2. However, adversarial empirical testing revealed a critical edge case in `site_tgach/main.py` lines 10526–10540: if non-dict data ever gets written to or returned from the `mirrors:{file_id}` cache key, the `/files/{file_id}` proxy endpoint crashes with an unhandled `AttributeError` (HTTP 500) rather than falling back to empty mirrors (`{}`) or returning a clean HTTP 404.
3. According to the Empirical Challenger Protocol, code containing unhandled HTTP 500 exception paths under invalid/corrupted cache states must be rejected until guarded.

## 3. Caveats
- The 500 crash occurs specifically when corrupted or non-dict JSON is present in the mirror cache key (`mirrors:{file_id}`). Normal dictionary cache values work as expected.
- Remedy for worker: update `site_tgach/main.py` lines 10526-10532 to ensure `mirrors` is forced to `{}` if `not isinstance(mirrors, dict)`:
  ```python
  if cached:
      try:
          mirrors = json.loads(cached)
          if not isinstance(mirrors, dict):
              mirrors = {}
      except Exception:
          mirrors = {}
  ```

## 4. Conclusion
- While core proxy functionality passed 8 out of 8 empirical functional checks, an unhandled HTTP 500 crash was empirically demonstrated during cache type-mismatch testing.
- **VERDICT: REJECT**

## 5. Verification Method
1. Run backend unit test suite:
   `.\venv\Scripts\python.exe -m pytest tests/test_files_endpoint.py tests/test_backup.py tests/test_check_ddos.py`
2. Run empirical proxy validation suite:
   `.\venv\Scripts\python.exe -m pytest scratch/empirical_proxy_test.py`
3. Verify test output shows `test_cache_poisoning_non_dict_mirrors` failure until `isinstance(mirrors, dict)` guard is applied to `site_tgach/main.py`.
