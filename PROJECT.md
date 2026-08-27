# Project: DvachBot Career Work Engine Restoration & Codebase Audit

## Architecture
DvachBot is an aiogram 3.x Telegram bot architecture with:
- `main.py`: Core dispatcher `dp`, bot lifecycle, commands, inline callbacks, photo banner dispatch.
- `common/work_engine.py`: Career progression engine with 16 endgame vacancies (up to 620 shifts), dynamic salary formulas, risk penalties, gear buffs, wardrobe sets, milestone achievements, and rare item drops.
- `economy_extension.py`: Economy router with side hustles (bottles, sell mother), shekel transactions, and inventory helpers.
- Sub-routers: `stats_hub_router.py`, `votemute_engine.py`, `ttt_engine.py`, `dice_duel_engine.py`, `russian_roulette_pvp.py`, `casino_engine.py`, `banner_manager.py`.
- Storage: SQLite database with JSON-serialized `Users.active_items` for persistence across multiboards (`/b/`, `/sex/`, `/vg/`, etc.).

## Feature Inventory
| # | Feature | Description | Milestone | Source | Status |
|---|---------|-------------|-----------|--------|--------|
| 1 | 16 Career Vacancies | All 16 endgame tiers up to 620 shifts in `WORK_VACANCIES` | M1 | d52a9b33 / Survey | DONE |
| 2 | Dynamic Salary & Jackpots | Base salary range + gear buffs + 4% x2-x3 jackpots | M1 | Survey | DONE |
| 3 | Gear & Wardrobe Set Buffs | Wasserman set (+40%), Skuf set (+35%), Neo (+25%), Riot Police (0% fine), Anime (2x drop) | M1 | Survey | DONE |
| 4 | Item Drop System | Correct drop key parsing (trash_lootbox, gold_safe, tinfoil_hat, broom, guns) | M1 | Survey | DONE |
| 5 | Side Hustle Integration | Clean inline options for bottles / mother on career card without replacing it | M1 | Survey | DONE |
| 6 | Work Card Formatting | Photo banner caption limit <= 1024 chars with status badges (✅/⏳/🔒) | M1 | Survey | DONE |
| 7 | Command Unshadowing | Decorate `main.py:cmd_work` and deconflict `economy_extension.py:cmd_work_menu` | M2 | Survey | DONE |
| 8 | 114+ Commands Health | Verify all 114 commands in `setup_bot_commands` route to active live handlers | M2 | Survey | DONE |
| 9 | Multi-board Persistence | `work_shifts`, `work_cooldowns`, gear, and items persist across `/b/`, `/sex/`, `/vg/` | M2 | Survey | DONE |
| 10 | Career Unit Test Suite | Comprehensive tests in `tests/test_work_engine.py` for all 16 tiers, buffs, drops | M3 | Survey | DONE |
| 11 | Dispatch & Multiboard Tests | Tests in `tests/test_command_dispatch_and_multiboard.py` for routing & persistence | M3 | Survey | DONE |
| 12 | Zero-Regression Suite | `py_compile` on 100% files and 100% test pass on core test suites | M3 | Survey | DONE |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| 1 | M1: Work Engine Restoration & Enrichment | Restore `/work` handler, 16 tiers, drop table handling, gear buffs, side hustles, compact banner caption | none | DONE |
| 2 | M2: Codebase Shadowing & Handler Routing | Deconflict command decorators, eliminate handler shadowing, verify all 114+ commands | M1 | DONE |
| 3 | M3: Automated Verification & Test Suite | Expand `test_work_engine.py`, `test_command_dispatch_and_multiboard.py`, `py_compile` verification | M1, M2 | DONE |

## Interface Contracts
### `common/work_engine.py` ↔ `main.py`
- `WORK_VACANCIES`: Dictionary of 16 vacancies with keys: `name`, `desc`, `tier_name`, `req_shifts`, `base_min`, `base_max`, `cooldown_sec`, `penalty_shekels`, `risk_pct`, `drop_item`, `drop_chance`, `drop_name`, `fail_phrase`, `jackpot_phrase`.
- `execute_job_action(job_id, current_shifts, active_cooldown_until, user_inventory, wardrobe_equipped)` -> `dict` containing: `success`, `payout`, `cooldown_sec`, `new_shifts`, `penalty`, `dropped_item`, `is_jackpot`, `achievements_unlocked`, `message`, `error`.
- `_build_work_card(user_id, active_items)` -> `(text_caption: str, keyboard: InlineKeyboardMarkup)` where `len(text_caption) <= 1024`.

### `main.py` ↔ `economy_extension.py`
- `cmd_work` in `main.py` handles `@dp.message(Command("work", "job", "работа", "биржа", "earn", "bomj", "economy", ignore_case=True, ignore_mention=True))`.
- `economy_extension.py` handles side hustle callbacks (`work_bottles`, `work_sell_mother`) or delegates cleanly without intercepting top-level `/work` commands.

## Code Layout
- `common/work_engine.py`: Vacancy definitions, career mechanics, gear buffs, drops, achievements.
- `main.py`: `cmd_work`, `_build_work_card`, `cb_work_do`, `cb_work_refresh`, `cb_work_main_hub`, command setup `setup_bot_commands`.
- `economy_extension.py`: `economy_router`, `cb_work_action` (`work_bottles`, `work_sell_mother`).
- `tests/test_work_engine.py`: Tests for 16 career tiers, formulas, gear buffs, drop tables, achievements.
- `tests/test_command_dispatch_and_multiboard.py`: Tests for command routing, 114 commands, and multiboard persistence.
- `tests/test_economy_work.py`: Tests for economy integration and side hustles.
