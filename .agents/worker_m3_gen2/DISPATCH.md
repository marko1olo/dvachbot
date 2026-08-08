## 2026-08-08T16:30:32Z

Objective: Fix regression in `site_tgach/main.py` and `tests/test_files_endpoint.py`.

Remediation Tasks:
1. In `site_tgach/main.py` (around lines 10484–10486):
   - Wrap `await is_file_permanently_failed(file_id)` in a `try...except Exception:` block so that if a database connection error, timeout, or thread event loop mismatch occurs, it fails gracefully (logs warning and continues to normal mirror fallback) instead of hanging or crashing the endpoint.
2. In `tests/test_files_endpoint.py`:
   - Update test fixtures or setup so `is_file_permanently_failed` is mocked (e.g. `AsyncMock(return_value=False)`) in `mock_external_deps` or fixture functions, preventing Starlette `TestClient` synchronous thread portal calls from deadlocking `aiosqlite`.
3. Verification & Testing:
   - Run `pytest tests/test_files_endpoint.py -v` and verify ALL tests pass with Exit Code 0 (0 timeouts).
   - Run `pytest tests/test_media_resiliency.py -v` and verify ALL tests pass with Exit Code 0.
   - Run `python -m py_compile` on `site_tgach/main.py` and `tests/test_files_endpoint.py`.
