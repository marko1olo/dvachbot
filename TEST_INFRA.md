# E2E Test Infra: DvachBot Command Dispatch & Multi-Board State Synchronization

## Test Philosophy
- Opaque-box, requirement-driven, and white-box regression verification.
- Zero tolerances for handler shadowing, unhandled exceptions, or cross-board progression loss.
- Methodology: Category-Partition + BVA + Pairwise Combinatorial + Multi-Board State Simulation + Matplotlib Figure Leak & Concurrency Testing.

## Feature Inventory
| # | Feature | Source | Tier 1 (Feature) | Tier 2 (Boundary) | Tier 3 (Pairwise/Cross) | Tier 4 (Workload/E2E) |
|---|---------|--------|:----------------:|:-----------------:|:-----------------------:|:---------------------:|
| 1 | 84+ User Commands Dispatch | ORIGINAL_REQUEST §R1 | 84 tests | 25 boundary | 15 pairwise | 10 E2E scenarios |
| 2 | 30 Admin Commands Dispatch | ORIGINAL_REQUEST §R1 | 30 tests | 10 boundary | 10 pairwise | 5 E2E scenarios |
| 3 | Autocomplete Alignment | ORIGINAL_REQUEST §R1 | 114 checks | 10 edge cases | 5 pairwise | 5 E2E scenarios |
| 4 | Multi-Board Career / Shifts | ORIGINAL_REQUEST §R2 | 5 tests | 5 edge boards | 5 job interactions | 5 career paths |
| 5 | Multi-Board Weapons & Debuffs | ORIGINAL_REQUEST §R2 | 10 weapon tests | 5 edge cases | 10 PvP duels | 5 PvP workflows |
| 6 | Multi-Board Wardrobe & Sets | ORIGINAL_REQUEST §R2 | 8 wardrobe tests| 5 edge cases | 5 set bonuses | 5 dressing workflows |
| 7 | Exploit Prevention (25x abuse) | ORIGINAL_REQUEST §R2 | 5 exploit tests | 5 race conditions| 5 cooldown checks | 5 abuse scenarios |
| 8 | Concurrency & Memory Safety | ORIGINAL_REQUEST §R3 | 5 concurrency | 5 high load | 5 leak audits | 5 sustained stress |

## Test Architecture
- `tests/test_dispatcher_routing_compliance.py`: Validates zero shadowed handlers, exact parameter binding resolution, autocomplete synchronization, and dry-run dispatch.
- `tests/test_multiboard_state_synchronization.py`: Tests multi-board data aggregation across `/b/`, `/sex/`, `/vg/`, `/po/`, `/a/`, `/int/` for weapons, shifts, gear, achievements, and cooldowns.
- `tests/test_concurrency_and_leak_guards.py`: Tests SQLite WAL concurrent access under `db_lock` and asserts zero matplotlib figure memory leaks.
- `tests/test_e2e_requirements_suite.py`: Starlette/FastAPI requirements test suite.
- Existing 155 unit & integration test files in `tests/`.

## Real-World Application Scenarios (Tier 4)
| # | Scenario | Features Exercised | Complexity |
|---|----------|--------------------|------------|
| 1 | User starts on `/b/`, buys knife and ushanka, switches to `/vg/` to duel, switches to `/sex/` to work | Wardrobe, Weapons, Shop, Career Shifts, Cross-board sync | High |
| 2 | Admin issues ban and unmask on `/threads`, uses `/mega` to pin thread on `/po/`, runs `/stats_hub` | Admin routing, `/threads`, `/mega`, `/stats_hub`, permissions | High |
| 3 | Casino Hub mini-game navigation: `/casino` -> clicks Tic-Tac-Toe, Dice Duel, Russian Roulette | Callback routing, Casino UI, Mini-games | Medium |
| 4 | Multi-board daily bonus & bottle search rate limit enforcement across 6 boards | Cooldown sync, exploit prevention, database atomicity | Medium |
| 5 | 50 concurrent transactions performing simultaneous work shifts, rob actions, and shop buys | SQLite concurrency, WAL mode, `db_lock` integrity | High |
