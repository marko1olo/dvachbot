# Original User Request

## Initial Request — 2026-08-08T14:40:29Z

<USER_REQUEST>
# Teamwork Project Prompt

The Python-based `dvachbot` has recently started experiencing severe lag in its main loop, with `passive_slice` processing times jumping from ~2s to ~9s (⏱ 8.9s). The bot was recently updated to use a new `PostFiles` table for tag lookups instead of full table scans. Identify the new bottleneck in the runtime loop, fix the performance regression, and ensure the recent tag-search optimizations remain intact.

Working directory: `C:\Users\danat\Desktop\dvachbot`
Integrity mode: development

## Requirements

### R1. Identify and Fix the Bottleneck
Profile the `dvachbot` runtime (specifically the `passive_slice` execution path or database queries) to find out why the processing time has spiked. Fix the underlying issue without breaking existing functionality. The CTO (me) suspects it could be a query locking the DB, an unindexed table scan introduced recently, or synchronous I/O blocking the async loop.

### R2. Preserve Recent Optimizations
The recent fix that maps `file_id`s in the `PostFiles` table (instead of `instr()` on `Posts.content`) must not be reverted or broken. DO NOT OVERWRITE WORKING CODE. Be extremely careful.

### R3. Verification Script
Write a small benchmark or log-parsing script that proves the bottleneck is resolved by measuring the execution time of the fixed function or by showing the log times returning to normal (under 3 seconds for `passive_slice`).

## Acceptance Criteria

### Performance Restored
- [ ] A diagnostic/benchmark script is executed and outputs proof that the specific bottleneck has been eliminated.
- [ ] The lag spike in the main loop is eliminated (simulated processing time or specific query time returns to fast levels, < 3 seconds).
- [ ] Tag search remains fast (~30-50ms) and uses the `PostFiles` table correctly (verifiable via `bench_tags.py`).
- [ ] The bot starts up correctly and does not crash due to syntax or logic errors after the fix.
</USER_REQUEST>

## Follow-up — 2026-08-09T11:24:38Z

<USER_REQUEST>
# Teamwork Project Prompt — Draft

Conduct a comprehensive technical and product audit of the `dvachbot` Telegram bot and its companion site `site_tgach`. The goal is to produce a detailed, actionable report with concrete recommendations for improvement, without modifying any source code.

Working directory: C:\Users\danat\Desktop\dvachbot
Integrity mode: development

## Requirements

### R1. Technical Audit
Analyze the codebase and database architecture for performance bottlenecks, security vulnerabilities, and structural flaws (e.g., spaghetti code, missing indexes, inefficient queries).

### R2. Product & UX Audit
Analyze the user experience of both the bot and the web interface (`site_tgach`). Propose new features, gamification mechanics, and UX/UI improvements to increase user engagement.

### R3. Read-Only Constraint
Do not execute any code modifications, dependency installations, or database migrations. Your sole deliverable is an analytical report.

## Acceptance Criteria

### Verification Rubric
- [ ] The final deliverable is a markdown file named `COMPREHENSIVE_AUDIT_REPORT.md` written to the working directory.
- [ ] The report identifies at least 5 specific technical flaws, citing exact file paths and line numbers (or specific database tables/queries).
- [ ] The report proposes at least 3 concrete product/feature enhancements tailored specifically to this project's context (no generic advice).
- [ ] All technical recommendations include a clear "Why this is a problem" and "How to fix it (architecture plan)" section.
</USER_REQUEST>

## Follow-up — 2026-08-12T16:25:39Z

<USER_REQUEST>
# Teamwork Project Prompt — Draft

> Status: Ready for launch — awaiting user approval
> Goal: Craft prompt → get user approval → delegate to teamwork_preview

Investigate the `/sum` command to report which models are currently used, rewrite the auto-roast prompt to be raw and aggressive (removing AI cliches), and disable the unfinished "new modes" by replacing their triggers with a "mode is not active" message.

Working directory: `C:\Users\danat\Desktop\dvachbot`
Integrity mode: development

## Requirements

### R1. Summarization Models Report
Identify which exact AI models (e.g., Llama, ChatGPT, Claude) are currently being used in the `summarize_text_with_hf` (or similar) functions for the `/sum` command. Produce a concise technical report listing the endpoints, models, and any recent changes in the fallback hierarchy. Do not change the code for summarization yet.

### R2. Auto-Roast Prompt Rewrite
Locate the prompt used for "Автопрожарка" (auto-roasting of voice/video notes). Rewrite the prompt to ensure the output is extremely raw, aggressive, and entirely free of any "AI-style" polite disclaimers or typical ChatGPT phrasing. Fix any grammatical or structural errors in the current prompt.

### R3. Disable "New Modes"
Identify the newly added but unfinished modes/features in the codebase (often referred to as "new modes"). Ensure that these modes cannot be activated by users. If a user attempts to run a command associated with these modes, the bot must reply with a stub message indicating that the mode is currently inactive or unfinished.

## Acceptance Criteria

### Summarization
- [ ] A written report is provided detailing the currently active models for the `/sum` command.

### Auto-Roast
- [ ] The auto-roast prompt has been rewritten.
- [ ] A programmatic test (e.g. running the prompt locally or a static check) confirms the prompt explicitly forbids polite disclaimers and AI cliches.

### New Modes
- [ ] The trigger commands for the unfinished modes return a static "mode is not active" message.
- [ ] The core code for the new modes remains in the repository but is functionally disconnected from user execution.
</USER_REQUEST>

## Follow-up — 2026-08-26T20:40:56Z

<USER_REQUEST>
Audit, verify, and resolve all outdated/duplicate handlers, handler masking conflicts, argument mismatches, and multi-board persistence desynchronizations (active_items, work shifts, inventory, stats, cooldowns across boards) across all bot commands in DvachBot.

Working directory: C:\Users\danat\Desktop\dvachbot
Integrity mode: development

## Requirements

### R1. Exhaustive Audit & Cleanup of All Bot Commands & Dispatcher Routing
- Conduct a systematic audit of all 84+ registered user/admin commands (in main.py and modules like economy_extension.py, ttt_engine.py, dice_duel_engine.py, russian_roulette_pvp.py, votemute_engine.py, stats_hub_router.py, etc.).
- Eliminate all duplicate, outdated stub handlers or conflicting @dp.message(...) / @dp.callback_query(...) decorators that intercept or shadow modular router logic with invalid function signatures.
- Ensure every single command has valid parameter bindings (bot, message, board_id, stream, etc.), error handling, and exact argument alignment.

### R2. Universal Cross-Board Persistence & State Synchronization
- Fix all occurrences where user progress (work shifts, career progression, wardrobe clothing, permanent perks, inventory items, achievements, cooldowns, stats) is isolated or resets to 0 when users switch between boards (/b/, /sex/, /vg/, /po/, /a/, /int/, etc.).
- Ensure _get_user_active_items, shop purchases, inventory updates, and profile inspections consistently aggregate and preserve account-level progression across all board records.

### R3. Autonomous Verification & Zero Regression
- Run static syntax verification (py_compile) and test suites (pytest) across all modules.
- Create automated test cases covering command dispatch, multi-board item inheritance, and shift preservation to prevent future regressions.

## Acceptance Criteria

### Dispatcher & Command Routing
- [ ] No command has duplicate or shadowed handlers in main.py or router modules.
- [ ] All 84+ bot commands execute without TypeError, AttributeError, or unhandled exceptions.
- [ ] Telegram autocomplete list (setup_bot_commands) is 100% synchronized with live router commands.

### Multi-Board Data Consistency
- [ ] Users moving between boards retain all career shifts (work_shifts), unlocked job tiers, achievements, and owned wardrobe items.
- [ ] _get_user_active_items and related DB helpers return consistent unified state across all boards.

### Quality & Test Suite
- [ ] All unit and integration test suites pass with 100% success (pytest tests/).
- [ ] Zero lint/runtime errors on startup and command dispatch.
</USER_REQUEST>

## Follow-up — 2026-08-27T08:14:12Z

<USER_REQUEST>
Music Auto-Roast Engine and Summarize Reasoning/Thinking Tags Sanitization for DvachBot.

Working directory: C:\Users\danat\Desktop\dvachbot
Integrity mode: development

## Requirements

### R1. Full Music Auto-Roast Engine (`handle_music_roast`)
- Implement automatic 2ch roast for any audio/music track sent to boards (`message.audio`, music documents `.mp3`, `.wav`, `.flac`, `.ogg`, `.m4a`).
- Extract track metadata: artist/performer, track title, file name, duration.
- Transcribe audio sample/lyrics via STT fallback (`Groq Whisper` / `Gemini Audio`).
- Generate a caustic, unhinged imageboard music critique /b/ review analyzing the genre (drill, phonk, dead-inside rap, popsa, k-pop, shanson, anime OST), roasting the user's taste, and rating it (e.g. `0/10 💩` or `Шедевр мочи`).
- Deliver formatted response:
  ```html
  🎵 <b>Трек:</b> {artist} — {title} (<i>{dur_str}</i>)
  📝 <b>Текст / Семпл:</b> <i>«{lyrics_sample}»</i>
  🔥 <b>Рецензия музкритика /b/:</b>
  {roast_text}
  💩 <b>Шкала говноедства:</b> {rating}
  ```

### R2. Complete Reasoning/Thinking Tags Stripping & Summarize Engine Robustness
- Completely eradicate raw AI thinking tokens and tags (`<think>...</think>`, `<reasoning>...</reasoning>`, unclosed thinking prefixes) across `summarize.py` and `ai_manager.py`.
- Fix Gemini & Groq model cascade so valid models (`gemini-2.5-flash`, `gemini-2.0-flash`, `llama-3.3-70b-versatile`, `qwen-2.5-32b`) are queried with valid token parameters.
- Ensure Telegraph page creation never fails with `CONTENT_TOO_BIG` by strictly enforcing AST node payload size limits and automatic chunking.

### R3. Automated Regression & Unit Test Suite
- Add comprehensive pytest tests in `tests/test_music_roast.py` and `tests/test_summary_thinking_sanitization.py`.
- Verify 100% clean compilation via `python -m py_compile` across all files.

## Acceptance Criteria

### Music Auto-Roast
- [ ] Any `audio` message or music file triggers `handle_music_roast` with metadata extraction (artist, title, duration).
- [ ] STT transcription processes the audio bytes with Whisper/Gemini fallback.
- [ ] AI prompt outputs a 1-2 paragraph cynical 2ch critique and rating without polite preamble or quotes.

### Summarize & Reasoning Filter
- [ ] All outputs from reasoning models (Qwen, DeepSeek, Gemini) are 100% stripped of internal thinking processes before display.
- [ ] Telegraph createPage requests are capped <= 55,000 bytes payload and auto-shrink on `CONTENT_TOO_BIG`.
- [ ] `summarize_text_with_hf` returns clean HTML compatible with Telegram.

### Test Verification
- [ ] `python -m py_compile` passes across all repository Python files with 0 errors.
- [ ] `pytest tests/test_music_roast.py tests/test_summary_thinking_sanitization.py tests/test_work_engine.py` passes 100%.

</USER_REQUEST>

## Follow-up — 2026-08-27T08:17:06Z

<USER_REQUEST>
CRITICAL USER REFINEMENT FOR MUSIC AUTO-ROAST:
1. Toxicity Level: The music roast prompt MUST be just as extreme, cynical, caustic, and toxic as the Voice Note roast prompt (authentic 2ch /b/ style, full uncensored slang/profanity, zero polite AI preamble, zero quotes or disclaimers).
2. Analysis Scope: Roast MUST analyze BOTH the lyrics (распознанный через STT текст песни) AND metadata/track context (исполнитель, название трека, звучание/жанр).
3. Message Structure:
   - Header & Track Info: 🎵 <b>Трек:</b> {artist} — {title} (<i>{dur_str}</i>)
   - Transcribed Lyrics / Sample: 📝 <b>Текст / Семпл:</b> <i>«{lyrics_sample}»</i>
   - Brutal AI Teardown: 🔥 <b>Вердикт /b/ музкритика:</b>\n{roast_text}
   - Rating / Diagnosis: 💩 <b>Шкала говноедства:</b> {rating} / 10 (или вердикт)

Incorporate this immediately into the implementation plan, prompt templates, and test assertions!
</USER_REQUEST>

## Follow-up — 2026-08-27T08:25:36Z

<USER_REQUEST>
CRITICAL DIRECTIVE ON MODELS:
DO NOT TOUCH, RENAME, OR DOWNGRADE ANY MODEL NAMES!
The model cascades in summarize.py and elsewhere MUST remain EXACTLY as originally configured:
- gemini-3.5-flash-lite
- gemini-3.1-flash-lite
- gemini-3.6-flash
- gemini-3.7-flash
- qwen/qwen3.6-27b
Do not assume pretraining cutoffs or call them fantasy names. All test assertions and code must respect the existing 3.x model configuration.
</USER_REQUEST>


