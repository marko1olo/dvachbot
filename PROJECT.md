# Project: DvachBot Economy Rebalance

## Architecture
- **Language & Runtime**: Python 3.11+, asyncio, aiogram 2.x/3.x, SQLite WAL.
- **Core Components**:
  - `wardrobe_engine.py`: Wardrobe catalog, set bonuses, and centralized `get_wardrobe_total_stats()` with TTL and durability enforcement.
  - `combat_moderation_engine.py`: Central combat formulas, mute duration, and backfire calculations integrated with wardrobe stats.
  - `main.py`: Command handlers for `/rob`, `/shit`, `/curse`, `/shoot`, `/partyvan`, `/wardrobe`, `/inventory`, `/passport`, `/me`.
  - `common/work_engine.py`: Job actions, shift payouts, item drops, and fine calculation integrated with wardrobe perks.
  - `post_helpers.py`: Post formatting and social status badge display for posts and threads.
  - `lootbox_engine.py`: Case roll engines (`roll_trash_lootbox`, `roll_gold_safe`, `roll_whale_safe`), drop tables (`TRASH_ITEMS`, `PREMIUM_JUNK`), duplicate cashback caps, scrap recycling, and jackpot logic.
  - `whale_economy_engine.py` / `auction_engine.py`: Whale safes, auction system (`Auctions`, `AuctionBids`), super-wealth tax, and `/raid_oligarch`.
  - `common/db_pool.py` & `common/database.py`: Atomic WAL transactions (`db_transaction`), LazyLock, and balance persistence.

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---|---|---|---|
| F1.1 | Wardrobe Stats Aggregator | `get_wardrobe_total_stats()` with strict TTL and durability validation | M1 | ORIGINAL_REQUEST §R1 |
| F1.2 | Passive Defense in /rob | Deflect chance `P_deflect = min(0.35, Def * 0.0025)`, stolen reduction `min(0.60, Def / 200)`, and `set_gop_skuf` fear | M1 | ORIGINAL_REQUEST §R1 |
| F1.3 | Debuff Reduction /shit /curse | Full shit immunity for `feet_boots` and `set_riot_police`; tinfoil reflect; sanity-based debuff duration reduction | M1 | ORIGINAL_REQUEST §R1 |
| F1.4 | Combat Evasion & Mute Reduction | `feet_sneakers` evasion (30%) in `/shoot` and `/partyvan`; `hat_helmet` (-50%) and `set_riot_police` (-70%) mute reduction | M1 | ORIGINAL_REQUEST §R1 |
| F1.5 | Work Engine Integration | Fix infinite durability bug; `hat_helmet` zero work fines; `hat_bag` 8% lootbox drop; `body_tracksuit` 2x loot drop | M1 | ORIGINAL_REQUEST §R1 |
| F1.6 | Social Visibility Display | 2-3 char icon for equipped hat/set in `format_header` and `format_thread_post_header`; wardrobe block in `/passport` and `/inventory` | M1 | ORIGINAL_REQUEST §R1 |
| F2.1 | Rebalanced Drop Tables | Rebalance `TRASH_ITEMS` (avg ~14.28 ₪) and `PREMIUM_JUNK` (avg ~90 ₪) to eliminate inflated baseline cash | M2 | ORIGINAL_REQUEST §R2 |
| F2.2 | Duplicate Cashback Overhaul | Cap duplicate cashback at `min(0.30 * CasePrice, int(ItemPrice * 0.20))`; eliminate dual weapon cash stack; 35 ₪ scrap conversion | M2 | ORIGINAL_REQUEST §R2 |
| F2.3 | EV / RTP Mathematical Balance | Strict RTP <= 85% for Trash Lootbox (52.8%) and Gold Safe (62.1%) with low-probability jackpot thrills | M2 | ORIGINAL_REQUEST §R2 |
| F2.4 | Non-Buyable Status Rewards | Exclusive titles (`[Золотой Кит]`, `[Шекелевый Барон]`, `[Сборщик Стеклотары]`, `[Король Помойки]`) and rare relics | M2 | ORIGINAL_REQUEST §R2 |
| F3.1 | Exponential Whale Safes | High-level Whale Safes ($P(n) = 50000 \times 1.5^n$), RTP <= 65%, 70% burn to Abu Yacht Fund, prestige drops | M3 | ORIGINAL_REQUEST §R3 |
| F3.2 | Atomic Auction System | Unique slots/roles/boards auctions, `Auctions` & `AuctionBids` tables, atomic escrow & outbid refund, anti-sniping | M3 | ORIGINAL_REQUEST §R3 |
| F3.3 | Abu Wealth Tax & Class Wars | Progressive wealth tax tiers, 1.5x idle surcharge for inactive mega-wallets, collaborative `/raid_oligarch` raid | M3 | ORIGINAL_REQUEST §R3 |
| F4.1 | Wardrobe & Combat Tests | Test coverage for equipment stats, TTL expiration, /rob, /shit, /curse, /shoot, /work | M4 | ORIGINAL_REQUEST §AC |
| F4.2 | Lootbox & Cashback Tests | Test coverage for drop tables, cashback limits, Monte-Carlo EV/RTP <= 85% verification | M4 | ORIGINAL_REQUEST §AC |
| F4.3 | Whale Sinks & Auction Tests | Test coverage for whale safes, auctions, wealth tax, concurrency safety | M4 | ORIGINAL_REQUEST §AC |
| F4.4 | Full E2E & WAL Concurrency Pass | Complete pytest execution with 0 regressions and transaction integrity under SQLite WAL | M4 | ORIGINAL_REQUEST §AC |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|---|---|---|---|
| M1 | Wardrobe Utility & Social Visibility | F1.1, F1.2, F1.3, F1.4, F1.5, F1.6 | none | IN_PROGRESS |
| M2 | Lootbox Overhaul & EV/RTP Anti-Exploit | F2.1, F2.2, F2.3, F2.4 | none | PLANNED |
| M3 | Whale Money Sinks & Currency Dilution | F3.1, F3.2, F3.3 | M1, M2 | PLANNED |
| M4 | Comprehensive E2E Testing & Coverage Hardening | F4.1, F4.2, F4.3, F4.4 | M1, M2, M3 | PLANNED |

## Interface Contracts
### wardrobe_engine ↔ combat / work / profile
- `get_wardrobe_total_stats(active_items: Dict[str, Any]) -> Dict[str, Any]`:
  Validates item expiration (`is_permanent or expires > now`).
  Returns dictionary:
  - `total_defense: int`
  - `total_toxicity: int`
  - `total_sanity: int`
  - `rob_deflect_chance: float`
  - `rob_stolen_reduction_pct: float`
  - `rob_fear_chance: float`
  - `evasion_chance: float`
  - `mute_reduction_pct: int`
  - `debuff_reduction_pct: float`
  - `shit_immunity: bool`
  - `laxative_immunity: bool`
  - `schizo_immunity: bool`
  - `work_fine_immunity: bool`
  - `salary_mult: float`
  - `tips_mult: float`
  - `cooldown_mult: float`
  - `lootbox_flat_chance: float`
  - `lootbox_drop_mult: float`
  - `compact_post_icon: str`
  - `stealth_profile: bool`
  - `active_set_name: Optional[str]`
  - `active_set_desc: Optional[str]`
  - `equipped_items_summary: str`

### lootbox_engine ↔ economy
- `calculate_duplicate_cashback(case_price: int, item_price: int, is_weapon: bool = False) -> int`:
  Returns `min(int(case_price * 0.30), int(item_price * 0.20))`.
- `roll_trash_lootbox(active_items: dict) -> dict`:
  Cash EV ~25.32 ₪, Nominal EV ~79.24 ₪ (RTP 52.83% <= 85%).
- `roll_gold_safe(active_items: dict) -> dict`:
  Cash EV ~113.80 ₪, Nominal EV ~310.40 ₪ (RTP 62.08% <= 85%).
- `roll_whale_safe(user_id: int, open_count_today: int, active_items: dict) -> dict`:
  Calculates price $50000 \times 1.5^n$, burns 70% to `abu_yacht_fund`, RTP <= 65%.

### auctions ↔ database & economy
- `place_auction_bid(auction_id: int, user_id: int, bid_amount: int) -> dict`:
  Atomic escrow deduction via `db_transaction`, refunds outbid user immediately, extends auction by 300s if within anti-sniping window.

## Code Layout
- `wardrobe_engine.py`: Wardrobe catalog, set bonuses, stats aggregator `get_wardrobe_total_stats()`.
- `combat_moderation_engine.py`: `calculate_combat_duration_and_backfire()` updated with wardrobe stats.
- `main.py`: Handlers `cmd_rob`, `cmd_shit`, `cmd_curse`, `cmd_shoot`, `cmd_partyvan`, `cmd_passport`, `cmd_inventory`.
- `common/work_engine.py`: `execute_job_action()`, work buffs, fine immunity, lootbox drops.
- `post_helpers.py`: `format_header()` and `format_thread_post_header()` social badge formatting.
- `lootbox_engine.py`: Drop tables, roll functions, cashback calculation, scrap recycling.
- `whale_economy_engine.py`: Whale safes, auction logic, wealth tax, and `/raid_oligarch`.
- `common/database.py`: Balance helpers, auction tables, wealth tax execution.
- `tests/`: Pytest suites (`test_wardrobe_combat_utility.py`, `test_lootbox_rebalance.py`, `test_whale_money_sinks.py`).
