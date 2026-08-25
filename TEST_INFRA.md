# E2E Test Infra: DvachBot Next-Gen Analytics & WebApp Dashboard

## Test Philosophy
- Opaque-box, requirement-driven, and white-box adversarial verification.
- Zero tolerance for mock bypasses, dummy data facade implementations, or hardcoded strings.
- Concurrency and memory leak safety verification under load.

## Feature Inventory & Test Mapping
| # | Feature | Requirement | Tier 1 (Functional) | Tier 2 (Boundary) | Tier 3 (Pairwise) | Tier 4 (Workload) |
|---|---------|-------------|:-------------------:|:-----------------:|:-----------------:|:-----------------:|
| 1 | F1: Economy & Crime Matrix | ORIGINAL_REQUEST §R1 | 5 | 5 | ✓ | ✓ |
| 2 | F2: PvP & Bioweapons Radar | ORIGINAL_REQUEST §R1 | 5 | 5 | ✓ | ✓ |
| 3 | F3: Sociology & Drama Graph | ORIGINAL_REQUEST §R1 | 5 | 5 | ✓ | ✓ |
| 4 | F4: Memetics & Vision Analytics | ORIGINAL_REQUEST §R1 | 5 | 5 | ✓ | ✓ |
| 5 | F5: ASCII Sparklines Snapshot | ORIGINAL_REQUEST §R2 | 5 | 5 | ✓ | ✓ |
| 6 | F6: Inline Category Menu | ORIGINAL_REQUEST §R2 | 5 | 5 | ✓ | ✓ |
| 7 | F7: Async Poster Delivery | ORIGINAL_REQUEST §R2 | 5 | 5 | ✓ | ✓ |
| 8 | F8: Personal 2ch Wrapped | ORIGINAL_REQUEST §R3 | 5 | 5 | ✓ | ✓ |
| 9 | F9: Sarcastic Diagnosis | ORIGINAL_REQUEST §R3 | 5 | 5 | ✓ | ✓ |
| 10 | F10: WebApp Route `/app/stats` | ORIGINAL_REQUEST §R4 | 5 | 5 | ✓ | ✓ |
| 11 | F11: REST APIs `/api/stats/*` | ORIGINAL_REQUEST §R4 | 5 | 5 | ✓ | ✓ |
| 12 | F12: Interactive Charts/Plotly | ORIGINAL_REQUEST §R4 | 5 | 5 | ✓ | ✓ |
| 13 | F13: Visual Quality & Memory Safety | ORIGINAL_REQUEST §R5 | 5 | 5 | ✓ | ✓ |
| 14 | F14: Backward Compatibility | ORIGINAL_REQUEST §Safety | 5 | 5 | ✓ | ✓ |

## Test Architecture
- **Runner**: `pytest -v tests/` and standalone verification scripts in `tests/`.
- **Image Verifier**: Direct PIL inspection checking image dimensions (1200x675 / 1080x1350), RGBA/RGB channels, non-zero entropy, non-black/non-blank frames, color contrast ratio > 4.5:1, and absence of visual artifacts or NaN text.
- **Latency Benchmarker**: Async HTTP/query benchmarking confirming `/stats_hub` sparklines computation < 100ms and cached `/api/stats/*` < 15ms.
- **Concurrency & WAL Lock Tester**: Simultaneous execution of 50 concurrent read queries alongside mock write transactions to verify zero `database is locked` SQLite OperationalErrors.
- **Memory & Resource Leak Verifier**: 100 iterations of poster rendering with `tracemalloc` to confirm zero figure leaks (`len(plt.get_fignums()) == 0`) and stable RAM usage.
- **Backward Compatibility Test**: Invocation of legacy `/bot_stats`, `/stats`, `/my_stats`, and `periodic_publisher.py` functions to verify identical outputs and zero side-effects.

## Real-World Application Scenarios (Tier 4)
| # | Scenario | Features Exercised | Expected Outcome |
|---|----------|--------------------|------------------|
| 1 | High-Activity Chat Telegram Hub | F1-F7 | Instant sparkline message, responsive keyboard navigation, instant category poster replies |
| 2 | New/Empty User Wrapped Card Request | F8, F9 | Graceful generation of "Newfag / Ghost" archetype card without crash or 500 error |
| 3 | Heavy User (Top Giga-Schizo) Wrapped | F8, F9 | Accurate aggregation of 1000+ posts, top rivalries, accurate weapons/debuffs tally |
| 4 | WebApp Multi-Filter Exploration | F10, F11, F12 | Fast filter switching (24h/7d/30d/All, /b/, /po/, /vg/), live chart rerendering |
| 5 | Concurrent Bot & WebApp Surge | F1-F14 | 20 simultaneous WebApp users + 10 bot commands without database lock contention |
