# Project: DvachBot Economy Extensions — P2P Market & Bank of Abu

## Architecture
DvachBot is an async aiogram 3.x Telegram bot architecture with:
- `main.py`: Core dispatcher `dp`, router mounting, lifecycle, `/rob` PVP mechanics, shop hub, wallet hub, help menus.
- `common/database.py`: SQLite migrations and database access under `db_transaction` and `db_lock` (`aiosqlite`).
- `market_engine.py`: P2P Flea Market engine with item escrow, catalog browsing (Weapons, Wardrobe, Pharma, Lootboxes), price sorting, instant purchase, 5% Abu fee, lot cancellation, and seller PM notifications.
- `bank_engine.py`: Bank of Abu / Safe engine with robbery insulation, 3 tiers (Sych 0.5% flex, Skuf 2.5% 3-day lockup, MMM Abu 6.0% 24h risk), continuous per-second interest calculation, deposit/withdraw presets.
- `help_text.py` & `common/bot_helpers.py`: Help menus and interactive navigation buttons.

## Feature Inventory
| # | Feature | Description | Milestone | Source | Status |
|---|---------|-------------|-----------|--------|--------|
| 1 | Database Schema & Tables | `MarketListings` & `BankDeposits` tables, indexes, and atomic helpers in `common/database.py` | M1 | ORIGINAL_REQUEST §1, §2 | PLANNED |
| 2 | P2P Market Engine & Escrow | Item locking, escrow, listing creation, cancel/return, instant buy, 5% Abu fee deduction | M1 | ORIGINAL_REQUEST §1 | PLANNED |
| 3 | Bank of Abu Engine & Math | Real-time continuous interest math, 3 tiers (0.5%, 2.5%, 6.0%), early penalty, 3% pyramid default | M1 | ORIGINAL_REQUEST §2 | PLANNED |
| 4 | Market Telegram Handlers & UI | `/market`, `/bazar`, `/sell`, interactive catalog, categories, price sort, pagination | M2 | ORIGINAL_REQUEST §1 | PLANNED |
| 5 | Bank Telegram Handlers & UI | `/bank`, `/deposit`, `/withdraw`, balance overview (wallet vs safe), presets, refresh | M2 | ORIGINAL_REQUEST §2 | PLANNED |
| 6 | Seller PM Notifications | Direct Telegram PM to seller on purchase with error suppression for blocked bots | M2 | ORIGINAL_REQUEST §1 | PLANNED |
| 7 | Robbery Safe Insulation | Verify Bank safe deposits are excluded from `get_user_global_balance` and immune to `/rob` | M2 | ORIGINAL_REQUEST §2 | PLANNED |
| 8 | Trade Hub (`/shop`) Integration | Add `[🛒 Барахолка P2P]` and `[🏦 Банк Абу]` buttons in `_build_main_shop_hub` | M3 | ORIGINAL_REQUEST §3 | PLANNED |
| 9 | Help Menu & Docs Integration | Add `/market` and `/bank` docs to `help_text.py`, `get_help_keyboard`, quick command list | M3 | ORIGINAL_REQUEST §3 | PLANNED |
| 10| Wallet & Profile Display | Show dual balance (Wallet vs Bank Safe) in `/wallet`, add quick action buttons | M3 | ORIGINAL_REQUEST §3 | PLANNED |
| 11| Authentic 2ch Humor & Styling | Cynical/toxic imageboard tone across all market/bank dialogues and error states | M3 | ORIGINAL_REQUEST §3 | PLANNED |
| 12| E2E Test Suite & py_compile | 100% green tests in `tests/test_p2p_market_engine.py`, `tests/test_bank_of_abu_engine.py`, etc. | M4 | ORIGINAL_REQUEST §4 | PLANNED |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| 1 | M1: Database Schema & Core Engines | `common/database.py`, `market_engine.py`, `bank_engine.py` (logic, math, escrow, transactions) | none | PLANNED |
| 2 | M2: Telegram Routers, Handlers & Notifications | Mount `market_router` & `bank_router` in `main.py`, unshadow `/market`, `/sell`, `/bank`, PM alerts | M1 | PLANNED |
| 3 | M3: Navigation, Shop Hub, Help & Wallet UI | Connect `/shop`, `/help`, `/wallet`, authentic 2ch flavor text and error dialogues | M1, M2 | PLANNED |
| 4 | M4: E2E Verification & Forensic Integrity | Full unit/integration tests, concurrency checks, `py_compile`, forensic audit | M1, M2, M3 | PLANNED |

## Interface Contracts
### `market_engine.py` ↔ `common/database.py`
- `create_market_listing(db, seller_id, seller_board_id, item_type, item_id, item_data, price)` -> `dict` (listing record).
- `cancel_market_listing(db, lot_id, user_id)` -> `(success: bool, item: dict, error_msg: str)`.
- `buy_market_listing(db, lot_id, buyer_id, buyer_board_id)` -> `(success: bool, seller_id: int, price: int, payout: int, fee: int, item: dict, error_msg: str)`.
- `get_market_catalog(db, category=None, sort_order="price_asc", page=1, per_page=5)` -> `(items: list, total_pages: int, total_count: int)`.
- `get_user_listings(db, user_id)` -> `list[dict]`.

### `bank_engine.py` ↔ `common/database.py`
- `create_bank_deposit(db, user_id, board_id, tier_id, amount)` -> `(success: bool, deposit: dict, error_msg: str)`.
- `calculate_deposit_state(deposit, current_ts)` -> `(accrued_interest: float, total_value: float, is_locked: bool, remaining_lock_sec: float)`.
- `withdraw_bank_deposit(db, deposit_id, user_id, board_id, force_early=False)` -> `(success: bool, payout: int, principal: int, interest: int, penalty: int, is_pyramid_default: bool, error_msg: str)`.
- `get_user_bank_summary(db, user_id)` -> `(total_principal: float, total_accrued: float, deposits: list[dict])`.

## Code Layout
- `common/database.py`: Table migrations for `MarketListings`, `BankDeposits`, indices, and transactional helpers.
- `market_engine.py`: Market catalog, escrow logic, purchase handling, listing cancellation, market router & handlers.
- `bank_engine.py`: Bank tiers config, dynamic continuous interest formula, deposit/withdrawal mechanics, bank router & handlers.
- `main.py`: Router inclusion (`dp.include_router(market_router)`, `dp.include_router(bank_router)`), `/shop` buttons, `/wallet` display, `/rob` validation.
- `help_text.py` & `common/bot_helpers.py`: Help menus and keyboard buttons.
- `tests/test_p2p_market_engine.py`: Unit & integration tests for P2P Market.
- `tests/test_bank_of_abu_engine.py`: Unit & integration tests for Bank of Abu.
- `tests/test_econ_menus_and_navigation.py`: Tests for menus, navigation, help, wallet, and routing.
