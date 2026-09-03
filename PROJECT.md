# Project: dvachbot Ecosystem Overhaul

## Architecture
- **Language & Runtime**: Python 3.11+, asyncio, aiogram / telegram-bot framework.
- **Database**: SQLite (`dvach_bot.db`) with aiosqlite / sqlite3 schema for posts, users, mutes, reports, transactions, stats.
- **Components**:
  - `common/spam_filter.py`: Anti-flood sliding window rate limiters, shadowmute timers, bayan detectors.
  - `handlers/message_router.py`: Ingress routing, shadow-reject processing, fake post generation for all media types.
  - `ai_manager.py` & `cyberchad_tts.py`: Cyberchad voice synthesis (Edge-TTS + DSP presets), spontaneous intervention engine (3600s cooldown), direct reply voice roast generator.
  - `pvp/`, `russian_roulette_pvp.py`, `dice_duel_engine.py`, `ttt_game.py`: PvP game lobbies, dynamic stake selector keyboards, broadcast confirmation flow.
  - `common/bot_helpers.py` (`handle_cyberchad_counter_action`): Counter-reaction and backfire logic for AI target attacks (/shoot, /rob, /shit, /vomit, /pepperspray, /partyvan, /dossier, /bribe).
  - `stats_v2.py`, `stats_generator.py`: Sentiment analysis, moderation forensics, player metrics.

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---|---|---|---|
| F1.1 | Anti-Flood Limits | BURST=8, RATE=15, MINUTE=30, base shadowmute=300s | M1 | ORIGINAL_REQUEST §R1 |
| F1.2 | No Silent Drops | check_spam and repeat checks always deliver ghost posts via process_shadow_reject | M1 | ORIGINAL_REQUEST §R1 |
| F1.3 | All-Media Ghost Delivery | Seamless ghost delivery with fake post numbers for photos, albums, videos, voice notes, video notes, audio, stickers, docs | M1 | ORIGINAL_REQUEST §R1 |
| F1.4 | DB Shadowmute Sync | Ensure handle_audio/voice/video_note & media groups check DB mutes | M1 | survey_explorer_1 |
| F2.1 | Spontaneous Cooldown | Minimum cooldown >= 3600.0s per board for spontaneous Cyberchad interventions | M2 | ORIGINAL_REQUEST §R2 |
| F2.2 | Strictly Voice Messages | Spontaneous interventions deliver voice messages only (no text body) | M2 | ORIGINAL_REQUEST §R2 |
| F2.3 | Direct Reply Roasting | Direct replies/mentions to Cyberchad trigger contextual voice roast replies | M2 | ORIGINAL_REQUEST §R2 |
| F2.4 | Cooldown Decoupling | Direct reply roasts decoupled from spontaneous 3600s board cooldown | M2 | survey_explorer_2 |
| F3.1 | Dynamic Stake Selector | Interactive lobby adapting buttons to balance (50, 100, 250... /2, x2, ВА-БАНК) for /duel, /dice, /ttt, /rr | M3 | ORIGINAL_REQUEST §R3 |
| F3.2 | Direct Amount Commands | Support /duel <amt>, /dice <amt>, /ttt <amt>, /rr <amt> | M3 | ORIGINAL_REQUEST §R3 |
| F3.3 | Challenge Confirmation | Challenges broadcast only after explicit player confirmation | M3 | ORIGINAL_REQUEST §R3 |
| F3.4 | Command Routing Fixes | Route /dice to dice duel lobby and /rr to russian roulette lobby | M3 | survey_explorer_3 |
| F4.1 | /shoot Backfire | 15m ricochet mute on AI attack | M4 | ORIGINAL_REQUEST §R4 |
| F4.2 | /rob Backfire | 500 ₪ fine to Abu Fund on AI attack | M4 | ORIGINAL_REQUEST §R4 |
| F4.3 | /shit & /vomit Backfire | 1 hour self-debuff on AI attack | M4 | ORIGINAL_REQUEST §R4 |
| F4.4 | /pepperspray Backfire | 30 minutes blindness on AI attack | M4 | ORIGINAL_REQUEST §R4 |
| F4.5 | /partyvan Backfire | 2 hours arrest on false report against AI | M4 | ORIGINAL_REQUEST §R4 |
| F4.6 | /dossier Alpha Stats | Alpha-Tier gigachad stats returned for AI | M4 | ORIGINAL_REQUEST §R4 |
| F4.7 | AI Action Routing | Correct wiring of cmd_dossier and cmd_curse/cmd_vomit for target_id == 0 | M4 | survey_explorer_3 |
| F5.1 | Sentiment Forensics | DB inspection of messages, sentiment queries, player sentiment on AI & economy | M5 | ORIGINAL_REQUEST §R5 |
| F5.2 | Moderation Forensics | Inspect reports, mutes, transactions, and moderation audit logs in dvach_bot.db | M5 | ORIGINAL_REQUEST §R5 |
| F6.1 | E2E & Unit Test Pass | 100% passing automated test suite (95+ tests green in pytest) | M6 | ORIGINAL_REQUEST §AC |
| F6.2 | Adversarial Hardening | Tier 5 white-box coverage hardening + Forensic Audit verification | M6 | Project Pattern |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|---|---|---|---|
| M0 | E2E Testing Track | Test harness & multi-tier test suite publishing TEST_READY.md | none | IN_PROGRESS |
| M1 | Anti-Flood & Ghost-Post Delivery | F1.1, F1.2, F1.3, F1.4 | none | IN_PROGRESS |
| M2 | Cyberchad Voice & Roasting | F2.1, F2.2, F2.3, F2.4 | none | IN_PROGRESS |
| M3 | Dynamic PvP Lobby & Staking | F3.1, F3.2, F3.3, F3.4 | none | IN_PROGRESS |
| M4 | AI Counter-Reactions | F4.1, F4.2, F4.3, F4.4, F4.5, F4.6, F4.7 | none | IN_PROGRESS |
| M5 | DB Sentiment & Forensics | F5.1, F5.2 | none | IN_PROGRESS |
| M6 | Final Integration & Audit | F6.1, F6.2 (100% E2E green, Tier 5 hardening, Auditor pass) | M0, M1, M2, M3, M4, M5 | PLANNED |

## Interface Contracts
### spam_filter ↔ message_router
- `check_spam(user_id, text, board)` -> `(is_spam: bool, reason: str, mute_duration: float)`
- `process_shadow_reject(bot, message, board, reason)` -> delivers fake post to author in PM without board broadcast.

### ai_manager ↔ broadcaster
- `generate_cyberchad_voice(text, preset)` -> `bytes` (Opus audio)
- `trigger_spontaneous_intervention(board)` -> sends voice-only message with cooldown >= 3600s.
- `handle_direct_cyberchad_reply(message, reply_to_post)` -> generates personalized contextual voice roast.

### pvp_lobby ↔ games
- `get_dynamic_stake_keyboard(game_type, balance, current_stake)` -> InlineKeyboardMarkup with dynamic denominations, /2, x2, ALL-IN, Confirm.
- `confirm_and_broadcast_challenge(game_type, user_id, stake)` -> validates balance and publishes to chat.

### common/bot_helpers ↔ handlers
- `handle_cyberchad_counter_action(action, user_id, chat_id, bot)` -> applies specific backfire penalty and sends thematic reply.

## Code Layout
- `common/spam_filter.py`: Anti-flood constants and rate-limiting algorithm
- `handlers/message_router.py`: Message routing and shadow-reject delivery
- `ai_manager.py`: Cyberchad triggers, cooldowns, voice roast prompt and context builder
- `cyberchad_tts.py`: Voice synthesis engine
- `russian_roulette_pvp.py`: Russian roulette commands and lobby
- `dice_duel_engine.py`: Dice duel commands and lobby
- `common/bot_helpers.py`: AI counter-reaction handler
- `stats_v2.py`: Database sentiment and forensics analytics
- `tests/`: Automated pytest suites
