# E2E Test Infra: dvachbot Ecosystem Overhaul

## Test Philosophy
- Opaque-box, requirement-driven. Derived from ORIGINAL_REQUEST.md.
- Methodology: Category-Partition + Boundary Value Analysis + Pairwise Combinatorial + Real-World Workload Testing.

## Feature Inventory & Test Mapping
| # | Feature | Requirement | Tier 1 (Feature) | Tier 2 (Boundary) | Tier 3 (Cross) | Tier 4 (Workload) |
|---|---|---|:---:|:---:|:---:|:---:|
| F1 | Anti-Flood & Ghost Media | R1 | 5 | 5 | ✓ | ✓ |
| F2 | Cyberchad Voice & Roasts | R2 | 5 | 5 | ✓ | ✓ |
| F3 | Dynamic PvP Lobbies | R3 | 5 | 5 | ✓ | ✓ |
| F4 | AI Target Counter-Reactions | R4 | 7 | 5 | ✓ | ✓ |
| F5 | DB Sentiment & Forensics | R5 | 5 | 5 | ✓ | ✓ |

## Test Architecture
- Test Runner: `pytest` with `pytest-asyncio` (`asyncio_mode = "strict"`).
- Test Suite Location: `tests/`
- Mock Framework: Custom async mocks for Telegram Bot, Message, CallbackQuery, SQLite test DB.

## Coverage Goals
- Tier 1: Feature Coverage (>=5 per feature domain)
- Tier 2: Boundary & Corner Cases (rapid bursts, max balance, zero balance, cooldown edges)
- Tier 3: Cross-Feature Interactions (e.g. ghost-muted user entering PvP lobby, direct replying to Cyberchad during flood cooldown)
- Tier 4: Real-World Application Workloads
- Acceptance Threshold: 95+ green tests in pytest suite.
