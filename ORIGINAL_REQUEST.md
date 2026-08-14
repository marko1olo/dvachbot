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
