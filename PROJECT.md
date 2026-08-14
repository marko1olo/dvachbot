# Project: dvachbot maintenance & hardening

## Architecture
- `ai_manager.py`: Bot AI commands, voice/video note processing (`transcribe_and_roast_voice_note`), `/sum` handler (`cmd_summarize`).
- `summarize.py`: Summarization engine, model cascade, API endpoints (Gemini & Groq).
- `data/text_assets.json` / `patch_text_assets.py`: Static text assets and roast prompts (`ROAST_PROMPTS`).
- `main.py`: Command routing, event handlers, `_trigger_generic_mode`, new modes commands (`/matrix`, `/america`, `/holiday`, `/oldweb`, `/jewish`).
- `new_modes.py`: Unfinished mode transformation logic (`matrix_mode`, `america_mode`, `holiday_mode`, `oldweb_mode`, `jewish_mode`).
- `tests/`: Automated unit test suite (`unittest`/`pytest`).

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Summarization Models Report | Technical report listing endpoints, active models, and fallback hierarchy for `/sum` | M1 | R1 requirement |
| 2 | Auto-Roast Prompt Rewrite | Rewrite prompt to be raw, aggressive, free of AI cliches/disclaimers, fix typos | M2 | R2 requirement |
| 3 | Auto-Roast Programmatic Test | Programmatic test verifying polite disclaimers/cliches are forbidden in auto-roast prompt | M2 | R2 requirement |
| 4 | Disable Unfinished New Modes | Return static "mode is not active" message on triggers for 5 new modes, keeping core code disconnected | M3 | R3 requirement |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| 1 | M1_Summarization_Report | Produce technical report on `/sum` AI models and fallback hierarchy | none | DONE |
| 2 | M2_Auto_Roast_Rewrite_Test | Rewrite auto-roast prompt & implement programmatic assertion test | none | DONE |
| 3 | M3_Disable_New_Modes | Update trigger commands for 5 unfinished modes to return static stub message | none | DONE |

## Interface Contracts
### Auto-Roast Handler ↔ Groq LLM
- Prompt passed to Groq LLM must be raw, aggressive, free of AI cliches or polite disclaimers.
- Must handle both voice notes (`voice`) and video note circles (`video_note`).

### Bot Commands ↔ Mode Router (`main.py`)
- Commands `/matrix`, `/america`, `/holiday`, `/oldweb`, `/jewish` (and aliases) return static stub message `"⚠️ Данный режим не активен и находится в разработке."` without changing `b_data` state or triggering `new_modes.py`.
