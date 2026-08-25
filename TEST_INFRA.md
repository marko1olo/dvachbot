# E2E Test Infra: Dvachbot Web Platform (`site_tgach`)

## Test Philosophy
- Opaque-box, requirement-driven testing across R1 through R5.
- Test suites exercise the web platform from external client/browser perspective (HTTP requests, DOM parsing, JavaScript execution).
- Methodology: Category-Partition + BVA + Pairwise Combinatorial + Real-World Workload Testing.

## Feature Inventory & Test Mapping
| # | Feature | Requirement | Tier 1 (Coverage) | Tier 2 (Boundary) | Tier 3 (Cross-Feature) | Tier 4 (Workload) |
|---|---------|-------------|:-----------------:|:-----------------:|:----------------------:|:-----------------:|
| 1 | R1-A: Video Posters | R1 | 5 tests | 5 tests | ✓ | ✓ |
| 2 | R1-B: Video Thumbnails (/thumb/ & ffmpeg) | R1 | 5 tests | 5 tests | ✓ | ✓ |
| 3 | R1-C: Bot Token Probing & Cache De-poisoning | R1 | 5 tests | 5 tests | ✓ | ✓ |
| 4 | R2-A: Tag Search `onerror` Fallback | R2 | 5 tests | 5 tests | ✓ | ✓ |
| 5 | R2-B: Fast Telegram Media Fallback | R2 | 5 tests | 5 tests | ✓ | ✓ |
| 6 | R3-A: Chat Mascot Layering (`--z-mascot: 100`) | R3 | 5 tests | 5 tests | ✓ | ✓ |
| 7 | R3-B: Mascot Pointer-Events Clickability | R3 | 5 tests | 5 tests | ✓ | ✓ |
| 8 | R4-A: Instant Guest Notice Banner Display | R4 | 5 tests | 5 tests | ✓ | ✓ |
| 9 | R4-B: Guest Form Input Disabling | R4 | 5 tests | 5 tests | ✓ | ✓ |
| 10 | R5-A: `FormManager.hideFloating()` Null-Safety | R5 | 5 tests | 5 tests | ✓ | ✓ |
| 11 | R5-B: Keyboard Listeners & Module Exports | R5 | 5 tests | 5 tests | ✓ | ✓ |

## Test Architecture
- **E2E Runner**: Python pytest integration test suite and Node.js DOM / unit test runner.
- **Python Integration Runner**: `.\venv\Scripts\python -m pytest tests/test_e2e_requirements_suite.py`
- **Node.js Unit / DOM Runner**: `node tests/test_form_manager_fe.js`, `node tests/test_frontend_fallback.js`
- **Playwright E2E Runner**: `.\venv\Scripts\python tests/test_browser_e2e.py`

## Real-World Application Scenarios (Tier 4)
| # | Scenario | Features Exercised | Expected Outcome |
|---|----------|--------------------|------------------|
| 1 | Unauthenticated guest opens chat page | R3, R4 | Mascot in foreground, guest notice banner visible, form disabled, post links clickable. |
| 2 | Thread with multiple video attachments loaded | R1 | All video attachments render valid JPEG posters without 404 or video stream mime mismatches. |
| 3 | Tag search gallery with broken third-party CDN mirrors | R2 | Images trigger `handleImageError` and load via fast Telegram fallback proxy without stalling. |
| 4 | User opens, interacts with, and closes floating reply box | R5 | Floating box closes cleanly via button, Escape key, or external triggers without unhandled TypeErrors. |
| 5 | Mobile viewport browsing (`viewport <= 768px`) | R3, R4, R5 | Mascot remains in foreground on mobile, touch/click events pass through to underlying posts. |

## Coverage Thresholds
- Tier 1: ≥5 per feature
- Tier 2: ≥5 per feature (boundary and error conditions)
- Tier 3: Pairwise coverage of feature interactions
- Tier 4: ≥5 realistic application scenarios
- Tier 5: White-box adversarial stress tests
