# TEST_READY — DvachBot Economy Rebalance (Milestones M1, M2, M3)

## 1. Overview
Comprehensive, opaque-box E2E test suite covering the DvachBot Economy Rebalance across all 4 systematic tiers:
- **Tier 1: Feature Coverage** (Wardrobe stats, TTL expiration, combat effects, lootbox drop tables, duplicate cashback caps, scrap recycling, whale safes, auctions, super-wealth tax).
- **Tier 2: Boundary & Corner Cases** (Permanent vs expired precedence, 0/1/100M balance precision, 7-day protection stacking caps, concurrent auction outbids).
- **Tier 3: Cross-Feature Combinations** (Lootbox drop -> equip -> /rob defense check -> cashback; Auction win -> custom title -> post header badge; Whale safe purchase -> 70% burn -> tax bracket drop).
- **Tier 4: Real-World Workload Simulations** (Monte Carlo 5,000+ case rolls proving RTP $\le 85\%$, anti-autoclicker bankruptcy proof, `/raid_oligarch` currency dilution proof).

---

## 2. Test Execution Summary

### Runner Command:
```bash
.\venv\Scripts\python.exe -m pytest tests/test_econ_e2e_suite.py -v
```

### Metrics:
- **Total Test Cases Collected**: **37**
- **Total Passed**: **37 (100%)**
- **Total Failed**: **0**
- **Execution Duration**: **~2.11 seconds**
- **Database Isolation**: **100% isolated** via `isolated_test_db` (`aiosqlite` temporary WAL instance; zero production DB touch).

---

## 3. Systematic Tier Breakdown

### Tier 1: Feature Coverage (19 Tests)

#### Domain M1: Wardrobe Utility & Combat/Work/Social Integration (7 Tests)
| Test Name | Feature | Description | Result |
|---|---|---|:---:|
| `test_t1_f1_1_wardrobe_stats_aggregation_all_slots` | F1.1 | Aggregates Def, Tox, San across all 4 slots and validates contract structure | ✅ PASS |
| `test_t1_f1_1_wardrobe_ttl_expiration_handling` | F1.1 | Validates that expired non-permanent items provide 0 stats and 0 perks | ✅ PASS |
| `test_t1_f1_2_rob_passive_defense_and_fear` | F1.2 | Validates `P_deflect = min(0.35, Def*0.0025)`, stolen cut `min(0.60, Def/200)`, and Skuf fear (40%) | ✅ PASS |
| `test_t1_f1_3_shit_and_curse_immunities` | F1.3 | Validates Boots / Riot shit immunity, Ward 6 laxative/schizo immunity, and sanity cut | ✅ PASS |
| `test_t1_f1_4_combat_evasion_and_mute_reduction` | F1.4 | Validates Sneakers 30% evasion in `/shoot` and `/partyvan`; Helmet 50% & Riot 70% mute reduction | ✅ PASS |
| `test_t1_f1_5_work_engine_bonuses` | F1.5 | Validates Helmet 0 fines, Bag 8% lootbox drop, and Wasserman salary mult | ✅ PASS |
| `test_t1_f1_6_social_visibility_display` | F1.6 | Validates compact post icon (`🪖 `, `👑 `, etc.) and passport summary formatting | ✅ PASS |

#### Domain M2: Lootbox Drop Tables, Cashback & Scrap Recycling (6 Tests)
| Test Name | Feature | Description | Result |
|---|---|---|:---:|
| `test_t1_f2_1_rebalanced_trash_items_drop_table` | F2.1 | Validates `TRASH_ITEMS` catalog has rebalanced average payout ~14.28 ₪ ($\le 20$ ₪) | ✅ PASS |
| `test_t1_f2_1_rebalanced_premium_junk_drop_table` | F2.1 | Validates `PREMIUM_JUNK` catalog has rebalanced average payout ~90 ₪ ($\le 100$ ₪) | ✅ PASS |
| `test_t1_f2_2_duplicate_cashback_cap_formula` | F2.2 | Validates $\min(0.30 \times \text{CasePrice}, \operatorname{int}(0.20 \times \text{ItemPrice}))$ cap across all weapons | ✅ PASS |
| `test_t1_f2_2_scrap_recycling_fixed_rate` | F2.2 | Validates fixed 35 ₪ scrap recycling for timed duplicates when permanent already owned | ✅ PASS |
| `test_t1_f2_2_bundle_cap_combat_kit` | F2.2 | Validates 80 ₪ bundle cashback cap, preventing the legacy +137 ₪ dual-weapon exploit | ✅ PASS |
| `test_t1_f2_4_non_buyable_status_rewards` | F2.4 | Validates existence of exclusive non-buyable titles and mythic relics in drop pools | ✅ PASS |

#### Domain M3: Whale Sinks, Auctions & Class Wars (6 Tests)
| Test Name | Feature | Description | Result |
|---|---|---|:---:|
| `test_t1_f3_1_whale_safe_exponential_pricing` | F3.1 | Validates progression $P(n) = 50000 \times 1.5^n$ and 70% burn to Abu Yacht Fund | ✅ PASS |
| `test_t1_f3_2_auction_bidding_atomic_escrow` | F3.2 | Validates atomic escrow deduction from user global balance via `db_transaction` | ✅ PASS |
| `test_t1_f3_2_auction_outbid_instant_refund` | F3.2 | Validates immediate, full refund to outbid bidder when a higher bid is placed | ✅ PASS |
| `test_t1_f3_2_auction_anti_sniping_timer` | F3.2 | Validates that bids within 300s of auction end extend `ends_at` by 300 seconds | ✅ PASS |
| `test_t1_f3_3_super_wealth_tax_brackets_and_idle_surcharge` | F3.3 | Validates progressive brackets (0%..5%) and 1.5x idle surcharge for inactive mega-wallets | ✅ PASS |
| `test_t1_f3_3_class_wars_raid_oligarch_vote_threshold_5_workers` | F3.3 | Validates threshold of exactly 5 qualified proletarian votes to trigger `/raid_oligarch` | ✅ PASS |

---

### Tier 2: Boundary & Corner Cases (9 Tests)
| Test Name | Target Boundary | Description | Result |
|---|---|---|:---:|
| `test_t2_wardrobe_expired_vs_permanent_same_item` | Expiration Flag | `is_permanent = True` strictly overrides any expired timestamp (`now - 100000`) | ✅ PASS |
| `test_t2_wardrobe_boundary_timestamp_exact_seconds` | Exact Timestamp | Item expiring at `now` is expired; item expiring at `now + 1` is active | ✅ PASS |
| `test_t2_auction_zero_balance_and_one_shekel` | Zero/Min Wallet | Users with 0 ₪ or 1 ₪ are rejected from placing bids on 10,000 ₪ lots | ✅ PASS |
| `test_t2_auction_insufficient_bid_step_rejection` | Bid Step Edge | Bid under `current_bid + min_bid_step` is strictly rejected | ✅ PASS |
| `test_t2_mega_balance_precision_and_overflow` | Mega-Balances | 100,000,000 ₪ balance maintains full decimal precision under tax and bids | ✅ PASS |
| `test_t2_maximum_duplicate_stacking_protection_caps` | Buff Stacking | Protection buffs (shields/tinfoil) cap at `now + 7 * 86400` (7 days max) | ✅ PASS |
| `test_t2_rapid_concurrent_auction_outbids` | Concurrency Invariant | 5 sequential outbids preserve invariant $\sum \text{balances} + \text{escrow} = \text{const}$ | ✅ PASS |
| `test_t2_negative_auction_bid_and_nan` | Numerical Malice | Negative bids, 0 bids, NaN, and Inf bids are strictly rejected | ✅ PASS |
| `test_t2_corrupted_active_items_safe_recovery` | Data Corruption | Empty, non-existent, or malformed `active_items` recover safely to 0 stats without crash | ✅ PASS |

---

### Tier 3: Cross-Feature Interactions (5 Tests)
| Test Name | Interacting Systems | Description | Result |
|---|---|---|:---:|
| `test_t3_lootbox_drop_equip_rob_defense_cashback` | Case $\to$ Equip $\to$ Combat | Lootbox drops gear $\to$ user equips it $\to$ `/rob` defense check reduces theft $\to$ cashback cap verified | ✅ PASS |
| `test_t3_auction_won_title_awarded_post_header_badge` | Auction $\to$ Social Visibility | Won auction sets custom title $\to$ `post_helpers.format_header` renders `[👑 Золотой Кит]` badge | ✅ PASS |
| `test_t3_whale_safe_burn_to_abu_fund_and_tax_interaction` | Whale Safe $\to$ Tax Sinks | Safe purchase burns 70% to Abu Fund $\to$ drops balance 600k $\to$ 475k $\to$ drops tax bracket 2.5% $\to$ 1.0% | ✅ PASS |
| `test_t3_work_drop_case_open_recycle_cycle` | Work $\to$ Case $\to$ Economy | Work shift with `hat_bag` drops case $\to$ open duplicate knife $\to$ recycled for 45 ₪ into wallet | ✅ PASS |
| `test_t3_gop_skuf_fear_breaks_robber_knife` | Wardrobe $\to$ Combat Backfire | Victim with `set_gop_skuf` fears robber $\to$ robber knife broken, stolen amount = 0 | ✅ PASS |

---

### Tier 4: Real-World Workload Simulations (4 Tests)
| Test Name | Workload / Simulation | Description | Result |
|---|---|---|:---:|
| `test_t4_monte_carlo_trash_lootbox_rtp_under_85` | 5,000 Trash Lootbox Rolls | Proves empirical Cash RTP < 30% and Nominal RTP $\le 85.0\%$ on 5,000 stochastic rolls | ✅ PASS |
| `test_t4_monte_carlo_gold_safe_rtp_under_85` | 5,000 Gold Safe Rolls | Proves empirical Cash RTP < 35% and Nominal RTP $\le 85.0\%$ on 5,000 stochastic rolls | ✅ PASS |
| `test_t4_raid_oligarch_simulation_and_currency_dilution` | Multi-Agent Class War | 1 Oligarch (1M ₪) raided by 5 workers $\to$ 10% taken $\to$ 70k ₪ burned to Abu Fund $\to$ 30k ₪ airdropped | ✅ PASS |
| `test_t4_monte_carlo_anti_autoclicker_continuous_bankruptcy` | Anti-Autoclicker Farm | Automated bot opening 2,000 safes drains balance monotonically to bankruptcy (no infinite farm) | ✅ PASS |

---

## 4. Feature Checklist & Coverage Verification

- [x] **F1.1: Wardrobe Stats Aggregator** (`get_wardrobe_total_stats`) validated with TTL and durability enforcement.
- [x] **F1.2: Passive Defense in `/rob`** (deflection chance `min(0.35, Def*0.0025)`, stolen reduction `min(0.60, Def/200)`, Skuf fear 40%).
- [x] **F1.3: Debuff Reduction** (`feet_boots` & `set_riot_police` shit immunity, `set_ward6` laxative/schizo immunity, sanity cut).
- [x] **F1.4: Combat Evasion & Mute Reduction** (`feet_sneakers` 30% evasion, `hat_helmet` -50%, `set_riot_police` -70%).
- [x] **F1.5: Work Engine Integration** (fine immunity, `hat_bag` 8% lootbox drop, `body_tracksuit` loot bonuses).
- [x] **F1.6: Social Visibility Display** (compact post icons `🪖 `, `👑 `, etc., in posts and `/passport`).
- [x] **F2.1: Rebalanced Drop Tables** (`TRASH_ITEMS` avg ~14.28 ₪, `PREMIUM_JUNK` avg ~90 ₪).
- [x] **F2.2: Duplicate Cashback Overhaul** ($\min(0.30 \times \text{CasePrice}, 0.20 \times \text{ItemPrice})$, 35 ₪ scrap recycling, 80 ₪ bundle cap).
- [x] **F2.3: Mathematical Balance & RTP** (RTP strictly $\le 85.0\%$ on 5,000+ roll Monte Carlo simulations).
- [x] **F2.4: Non-Buyable Status Rewards** (exclusive titles and mythic permanent relics).
- [x] **F3.1: Exponential Whale Safes** ($P(n) = 50000 \times 1.5^n$, 70% burn to `abu_yacht_fund`).
- [x] **F3.2: Atomic Auction System** (atomic escrow via `db_transaction`, instant outbid refund, 300s anti-sniping).
- [x] **F3.3: Abu Wealth Tax & Class Wars** (progressive brackets 0%..5%, 1.5x idle surcharge, `/raid_oligarch` dilution).
