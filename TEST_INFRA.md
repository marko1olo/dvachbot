# E2E Test Infra: DvachBot Economy Extensions (P2P Market & Bank of Abu)

## Test Philosophy
- Opaque-box, requirement-driven, and transaction-atomic verification.
- Zero tolerances for money duplication, negative balances, orphaned escrowed items, stolen bank deposits, or unhandled exceptions.
- Methodology: Category-Partition + BVA + Pairwise Combinatorial + Concurrency Stress Testing + 100% Syntax Verification (`py_compile`).

## Feature Inventory
| # | Feature | Source | Tier 1 (Feature) | Tier 2 (Boundary) | Tier 3 (Pairwise/Cross) | Tier 4 (Workload/E2E) |
|---|---------|--------|:----------------:|:-----------------:|:-----------------------:|:---------------------:|
| 1 | P2P Market Listing & Escrow | ORIGINAL_REQUEST §1 | 5 tests | 5 edge items | 5 cancel/relist | 5 market workflows |
| 2 | P2P Instant Buy & 5% Abu Fee | ORIGINAL_REQUEST §1 | 5 tests | 5 fee roundings | 5 balance boundaries | 5 trade workflows |
| 3 | Market Pagination & Categories | ORIGINAL_REQUEST §1 | 5 tests | 5 empty/overflow | 5 sorting orders | 5 catalog browsing |
| 4 | Seller PM Notifications | ORIGINAL_REQUEST §1 | 5 tests | 5 error suppressions | 5 multi-item sales | 5 notification runs |
| 5 | Bank Safe & /rob Protection | ORIGINAL_REQUEST §2 | 5 tests | 5 zero balance | 5 rob attack attempts | 5 safe isolation |
| 6 | 3 Bank Deposit Tiers & Rates | ORIGINAL_REQUEST §2 | 5 tests | 5 rate checks | 5 tier comparisons | 5 deposit mixes |
| 7 | Continuous Per-Second Interest | ORIGINAL_REQUEST §2 | 5 tests | 5 micro-seconds | 5 multi-day steps | 5 interest lifecycles |
| 8 | Bank Lockup & Early Exit Penalty | ORIGINAL_REQUEST §2 | 5 tests | 5 exact maturity | 5 penalty calculations | 5 early withdrawals |
| 9 | 3% Pyramid Risk of Default | ORIGINAL_REQUEST §2 | 5 tests | 5 default payouts | 5 seed distributions | 5 high-yield runs |
| 10| Menu, Help & Wallet Integration | ORIGINAL_REQUEST §3 | 5 tests | 5 missing data | 5 routing checks | 5 full menu loops |
| 11| Syntax & Compilation Safety | ORIGINAL_REQUEST §4 | 5 py_compile | 5 import audits | 5 router conflicts | 5 clean builds |

## Test Architecture
- `tests/test_p2p_market_engine.py`: Tests for market listing creation, item escrowing, double-sell prevention, instant purchase, 5% fee calculation, seller payout, cancellation and item restoration, category filtering (Weapons, Wardrobe, Pharma, Lootboxes), price sorting, and seller PM notifications.
- `tests/test_bank_of_abu_engine.py`: Tests for Bank deposits, robbery insulation against `/rob`, 3 tiers (Sych 0.5% flex, Skuf 2.5% 3-day lockup, MMM Abu 6.0% 24h risk), dynamic continuous per-second interest accrual, lockup enforcement, early withdrawal penalties, and 3% pyramid default handling.
- `tests/test_econ_menus_and_navigation.py`: Tests for `/shop` Trade Hub buttons, `/help` docs and buttons, `/wallet` dual balance display, command routing, and callback query dispatching.

## Coverage Thresholds
- Tier 1: >=5 tests per feature area (Total >= 55)
- Tier 2: Boundary value analysis (Zero balances, 1 shekel minimum, fractional rounding, exact lockup seconds, 0 items)
- Tier 3: Cross-feature combinations (Escrowing while in bank, depositing sales revenue, robbed while trading)
- Tier 4: Real-world user journeys (Full buy-sell-deposit-withdraw cycles)
- Total tests: >= 80 comprehensive automated tests.
