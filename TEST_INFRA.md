# E2E Test Infrastructure: DvachBot Economy Rebalance

## 1. Test Philosophy & Methodology
The test suite for the Economy Rebalance (Wardrobe Utility, Lootbox Overhaul, and Whale Money Sinks) follows an **opaque-box, requirement-driven** methodology derived directly from `PROJECT.md` and `ORIGINAL_REQUEST.md`:
- **Category-Partitioning**: Input parameter space (item slots, tiers, case types, wealth brackets, auction states) is partitioned into equivalence classes.
- **Boundary Value Analysis (BVA)**: Focus on critical transitions (expiration timestamp `now - 1` vs `now + 1`, 0 balance, 1 shekel, mega-balances up to 100,000,000 ₪, anti-sniping threshold 300s, max duplicate stacking).
- **Pairwise & Combinatorial Testing**: Interactions between equipment perks, combat commands (`/rob`, `/shit`, `/curse`, `/shoot`, `/partyvan`), job shifts (`/work`), and case drops.
- **Real-World Workloads & Monte Carlo Proofs**: 5,000+ stochastic rolls validating that empirical Return-To-Player (RTP) is strictly $\le 85\%$, and class war `/raid_oligarch` currency dilution models.

## 2. Feature Inventory & Test Tier Mapping

| # | Feature | Requirement | Tier 1 (Feature) | Tier 2 (Boundary) | Tier 3 (Cross) | Tier 4 (Workload) |
|---|---|---|:---:|:---:|:---:|:---:|
| **F1.1** | Wardrobe Stats Aggregator (`get_wardrobe_total_stats`) | R1 | ✅ (5+ tests) | ✅ | ✅ | — |
| **F1.2** | Passive Defense in `/rob` (Deflect, Squeeze, Fear) | R1 | ✅ (5+ tests) | ✅ | ✅ | — |
| **F1.3** | Debuff Reduction (`/shit`, `/curse`, Sanity reduction) | R1 | ✅ (5+ tests) | ✅ | — | — |
| **F1.4** | Combat Evasion & Mute Cut (`/shoot`, `/partyvan`) | R1 | ✅ (5+ tests) | ✅ | — | — |
| **F1.5** | Work Engine Integration (Immunity, 8% case, 2x loot) | R1 | ✅ (5+ tests) | — | ✅ | — |
| **F1.6** | Social Visibility (Icons in posts, passport summary) | R1 | ✅ (5+ tests) | — | ✅ | — |
| **F2.1** | Rebalanced Drop Tables (`TRASH_ITEMS`, `PREMIUM_JUNK`) | R2 | ✅ (5+ tests) | — | — | — |
| **F2.2** | Duplicate Cashback Cap & Scrap Recycling (35 ₪) | R2 | ✅ (5+ tests) | ✅ | ✅ | — |
| **F2.3** | EV / RTP Mathematical Balance (RTP $\le 85\%$) | R2 | ✅ (5+ tests) | — | — | ✅ (Monte Carlo 5k+) |
| **F2.4** | Non-Buyable Status Rewards (Titles, Mythics) | R2 | ✅ (5+ tests) | — | ✅ | — |
| **F3.1** | Exponential Whale Safes ($P(n) = 50000 \times 1.5^n$) | R3 | ✅ (5+ tests) | ✅ | ✅ | — |
| **F3.2** | Atomic Auction System (Escrow, Refund, Anti-sniping) | R3 | ✅ (5+ tests) | ✅ | ✅ | — |
| **F3.3** | Abu Wealth Tax & Class Wars (`/raid_oligarch`) | R3 | ✅ (5+ tests) | ✅ | ✅ | ✅ (Class War Dilution) |

## 3. Directory Layout & Test Organization
```
tests/
├── conftest.py                       # Hardened isolation guards, isolated_test_db fixture
├── test_econ_e2e_suite.py            # Primary 4-Tier E2E Economy Rebalance Suite
│   ├── TestTier1FeatureCoverage      # Unit & integration verification for F1.1-F3.3
│   ├── TestTier2BoundaryCases        # Boundaries, edges, overflow, rapid outbids
│   ├── TestTier3CrossFeature         # Cross-system interactions (case -> equip -> rob)
│   └── TestTier4WorkloadSimulation   # Monte Carlo 5k+ runs, /raid_oligarch dilution
```

## 4. Test Runner & Execution Commands
Execution strictly targets the isolated temporary SQLite database fixture (`isolated_test_db`):

```bash
# Run the complete Economy Rebalance E2E Suite
.\venv\Scripts\python.exe -m pytest tests/test_econ_e2e_suite.py -v

# Run specific tiers
.\venv\Scripts\python.exe -m pytest tests/test_econ_e2e_suite.py -k "Tier1" -v
.\venv\Scripts\python.exe -m pytest tests/test_econ_e2e_suite.py -k "Tier2" -v
.\venv\Scripts\python.exe -m pytest tests/test_econ_e2e_suite.py -k "Tier3" -v
.\venv\Scripts\python.exe -m pytest tests/test_econ_e2e_suite.py -k "Tier4" -v
```

## 5. Security & Isolation Constraints
1. **Zero Access to Production DB**: All tests use `isolated_test_db` from `tests/conftest.py`. Any attempt to connect to `dvach_bot.db` triggers a hard `RuntimeError`.
2. **Telegram API Mocking**: All outbound network requests to `api.telegram.org` are blocked at the socket / session layer.
3. **Deterministic Seed Control**: Stochastic Monte Carlo tests use fixed pseudo-random seeds or high-sample law-of-large-numbers bounds ($N \ge 5000$) to eliminate test flakiness.
