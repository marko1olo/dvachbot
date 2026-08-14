# Summarization Models Technical Audit Report (`/sum`)

**Project**: `dvachbot`  
**Target Path**: `C:\Users\danat\Desktop\dvachbot\SUMMARIZATION_MODELS_REPORT.md`  
**Audit Date**: 2026-08-12  
**Author**: M1 Summarization Report Writer (`worker_m1_1`)  
**Status**: Read-Only Audit (No Code Changes Applied)

---

## 1. Executive Summary

This report provides a comprehensive technical audit of the summarization engine powering the `/sum` command in `dvachbot`. The investigation mapped the full command routing pipeline, audited API endpoints and key rotators, evaluated the model fallback cascades in `summarize.py`, analyzed git history regarding past fixes and reverts, and documented operational degradation caused by non-existent model strings.

### Core Audit Findings:
1. **Name-Implementation Disconnect**: The function is named `summarize_text_with_hf()`, but HuggingFace API is **completely inactive**. The original HuggingFace T5 implementation (`rut5_base_sum_gazeta`) has been moved to `scripts/archive/summarize.py`. Active requests route exclusively through OpenAI-compatible REST endpoints to Google Gemini and Groq.
2. **Prevalence of Non-Existent Models**: Out of 8 models configured in the primary `models_cascade` (`summarize.py:119-128`), **7 models are hallucinated or non-existent** (e.g. `gemini-3.6-flash`, `qwen/qwen3.6-27b`).
3. **Single Workhorse Production Model**: `llama-3.3-70b-versatile` on Groq is the **only active, valid model** in the default cascade. Every `/sum` invocation sequentially attempts 7 non-existent endpoints before succeeding on Groq.
4. **Git Revert Loop**: Commit `8a677539` successfully updated `summarize.py` with real Gemini and Groq models, but was immediately reverted 9 minutes later by commit `8c0675e5`, re-introducing the non-existent model strings into production.

---

## 2. Command & Function Mapping

### 2.1 `/sum` Command Entry Point
- **File**: `ai_manager.py`
- **Line 946**: Handler definition:
  ```python
  @router.message(Command("summarize", "sum", "summary", "samamri", "sammary"))
  async def cmd_summarize(message: types.Message, board_id: str | None, stream: str = 'ru'):
  ```
- **Line 959–978**: Cooldown checking (`SUMMARIZE_COOLDOWN = 600` seconds per board).
- **Line 875–944**: Argument parsing via `_parse_summarize_args(text)` extracts paragraph count, length settings, and model preference flags (`gemini`, `llama`, `qwen`, `groq`).
- **Line 1036**: Execution delegation to summarization module:
  ```python
  summary = await summarize_text_with_hf(prompt, chunk, hf_token, model_preference=model_preference)
  ```
- **Line 1060–1080**: Formatted output delivery: posts short output to Telegram directly or creates a Telegraph page (`create_telegraph_page_async()`) if output length $\ge 900$ characters or paragraph count $\ge 5$.

### 2.2 Core Summarization Engine Functions
- **File**: `summarize.py`
- **Lines 71–81 (`summarize_text_with_hf`)**:
  Wrapper function that accepts `(prompt, text_dump, hf_token, model_preference)`. If `model_preference` is `"persona"` or `"persona_gemini"`, it acquires a concurrency lock via `_PERSONA_SEMAPHORE` (max 1 concurrent call). Otherwise, it delegates directly to `_summarize_inner`.
- **Lines 84–161 (`_summarize_inner`)**:
  Core engine function that:
  1. Selects the `models_cascade` based on `model_preference` (`persona`, `summary`/`gemini`, `qwen`, `llama`, or default).
  2. Constructs `system_instruction` with strict Telegram HTML formatting constraints.
  3. Loops through `(model_name, provider)` pairs in `models_cascade`, loading API keys, skipping keys in rate-limit cooldown, and executing requests via `AsyncOpenAI`.

---

## 3. Endpoints & API Providers

| Provider / Service | Base URL / Endpoint | Authentication / Loading Mechanism | Key Environment Variables | Status |
| :--- | :--- | :--- | :--- | :--- |
| **Google Gemini** | `https://generativelanguage.googleapis.com/v1beta/openai/` | `_load_google_keys()` checks `.envgoogle` first, falls back to `GOOGLE_API_KEYS` in `.env` | `GOOGLE_API_KEYS` | **Active** (via OpenAI compatibility layer) |
| **Groq API** | `https://api.groq.com/openai/v1` | Rotated via `groq_pool` (`TokenRotator` instance) | `GROQ_API_KEYS` | **Active** |
| **HuggingFace API** | `https://api-inference.huggingface.co/models/...` | Archived/Unused in active path | `HF_TOKEN`, `HF_TOKENS` | **Dormant / Archived** (`scripts/archive/summarize.py`) |
| **Telegraph API** | `https://api.telegra.ph/` | `get_telegraph_token()` | `TELEGRAPH_TOKEN` | **Active** (Long summary rendering) |

*Note*: The parameter `hf_token` passed to `summarize_text_with_hf` and `_summarize_inner` is legacy code and is completely unreferenced inside `_summarize_inner`.

---

## 4. Model Fallback Cascade Table

The default model fallback cascade in `summarize.py:119-128` defines the sequential order of API calls when `/sum` is executed without explicit model preference flags:

| Priority | Model String (`model_name`) | Provider | Real API Validity | Execution Behavior in `_summarize_inner` |
| :---: | :--- | :--- | :--- | :--- |
| **1** | `gemini-3.6-flash` | Gemini | ❌ **Non-existent / Hallucinated** | Fails with HTTP 404 / Invalid Model Error; logs warning and moves to Priority 2. |
| **2** | `gemini-3.5-flash` | Gemini | ❌ **Non-existent / Hallucinated** | Fails with HTTP 404 / Invalid Model Error; logs warning and moves to Priority 3. |
| **3** | `gemini-2.5-flash` | Gemini | ❌ **Non-existent / Hallucinated** | Fails with HTTP 404 / Invalid Model Error; logs warning and moves to Priority 4. |
| **4** | `qwen/qwen3.6-27b` | Groq | ❌ **Non-existent / Hallucinated** | Fails on Groq API with 404; logs warning and moves to Priority 5. |
| **5** | `gemini-3.5-flash-lite` | Gemini | ❌ **Non-existent / Hallucinated** | Fails with HTTP 404 / Invalid Model Error; logs warning and moves to Priority 6. |
| **6** | `gemini-3.1-flash-lite` | Gemini | ❌ **Non-existent / Hallucinated** | Fails with HTTP 404 / Invalid Model Error; logs warning and moves to Priority 7. |
| **7** | `gemini-2.5-flash-lite` | Gemini | ❌ **Non-existent / Hallucinated** | Fails with HTTP 404 / Invalid Model Error; logs warning and moves to Priority 8. |
| **8** | `llama-3.3-70b-versatile` | Groq | ✅ **Valid Production Model** | **Succeeds**. Generates and returns summary. |

### Operational Impact of Cascade Misconfiguration:
Because priorities 1 through 7 specify non-existent model strings, every call to `/sum` experiences:
- 7 consecutive failing REST requests prior to reaching Priority 8.
- Added latency from round-trip HTTP error responses and fallback loop handling.
- Useless log noise for failed model attempts.

---

## 5. Git History & Reverted Fixes Analysis

A detailed inspection of the git commit history for `summarize.py` revealed prior recognition of this flaw and an immediate revert:

### Commit `8a6775390ee2c9e4ddf1e0f082dbb2e345c9b871`
- **Date**: Sat Aug 8 16:18:46 2026 +0400
- **Author**: marko1olo <barsukdana@gmail.com>
- **Subject**: `Fix hallucinated and decommissioned LLM models in summarize cascade`
- **Changes**: Replaced non-existent model strings in `summarize.py` with real, production-ready models:
  - `gemini-2.0-flash`
  - `gemini-1.5-flash`
  - `gemini-1.5-flash-8b`
  - `gemini-2.0-flash-lite`
  - `llama-3.1-8b-instant`
  - `llama-3.3-70b-versatile`

### Commit `8c0675e595c69d69a9ff80ef411c39d535a232e3`
- **Date**: Sat Aug 8 16:27:58 2026 +0400 (9 minutes later)
- **Author**: marko1olo <barsukdana@gmail.com>
- **Subject**: `Revert "Fix hallucinated and decommissioned LLM models in summarize cascade"`
- **Changes**: Exact revert of `8a677539`, restoring all 7 non-existent/hallucinated model strings back into `summarize.py`.

---

## 6. Code Freeze Compliance Notice

Per task constraints (**Requirement 5**), **no code modifications have been made** in `summarize.py`, `ai_manager.py`, or any other file. All findings in this report reflect the exact state of the production codebase as of 2026-08-12.
