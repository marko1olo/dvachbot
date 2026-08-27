# Original User Request

## Initial Request — 2026-08-28T00:08:06+04:00

You are the Lead Project Orchestrator for Dvachbot.

Your working directory is: c:\Users\danat\Desktop\dvachbot\.agents\orchestrator_econ
The repository root is: c:\Users\danat\Desktop\dvachbot
The authoritative request is recorded in: c:\Users\danat\Desktop\dvachbot\ORIGINAL_REQUEST.md

## Mission & Requirements
Implement two major economic systems for Dvachbot:
1. **P2P Flea Market / Bazaar (`/market`, `/bazar`, `/sell`)**:
   - Allow users to list owned items from inventory/wardrobe with a custom price in shekels.
   - Item is locked/escrowed upon listing so it cannot be used or double-sold.
   - Interactive inline marketplace catalog with categories (Weapons, Clothes/Armor, Pharma, Lootboxes), price sorting, and pagination.
   - Instant item purchase: buyer pays shekels, seller receives shekels minus 5% Abu market fee, item transfers to buyer's active items.
   - Ability for seller to cancel active listing and retrieve their item.
   - Seller receives Telegram PM notification when their lot is purchased.

2. **Bank of Abu / Safe (`/bank`, `/deposit`, `/withdraw`)**:
   - Protected safe: funds deposited in the bank cannot be stolen via `/rob` or street attacks.
   - Three deposit tiers with dynamic interest calculation:
     1. Flexible Safe (Сейф Сыча): 0.5% daily yield, withdraw anytime with 1% bank fee.
     2. 3-Day Term (Депозит Скуфа): 2.5% daily yield, 72h lockup, early exit penalty.
     3. High-Yield Pyramid (МММ Абу): 6.0% daily yield, 24h lockup, 3% risk of default/audit.
   - Real-time continuous interest calculation on read/interaction based on elapsed seconds.
   - Interactive inline banking UI with balance overview (wallet vs bank), accrued interest counter, and quick deposit/withdraw presets.

3. **Navigation, Help & Menu Integration**:
   - Integrate `/market` and `/bank` into:
     - Main Trade Hub (`/shop`) navigation buttons.
     - Help menu (`/help`, `help_text.py`) and quick command lists.
     - Profile hub and wallet displays.
   - Full 2ch-themed cynical/toxic humor and authentic imageboard flavor text across all dialogues and error states.

4. **Testing & Quality**:
   - Comprehensive unit and integration test suite passing with 100% green tests.
   - Syntax validation via python -m py_compile across all modified and new files.

Decompose this task, spawn specialist agents (explorers, workers, reviewers, challengers, test writers), maintain plan.md and progress.md in your directory, and deliver verified production-ready implementation. Report back when complete.
