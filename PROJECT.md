# Project: DvachBot Next-Generation Analytics, Posters, Telegram Hub, Wrapped & WebApp

## Architecture
DvachBot Next-Gen Analytics is designed as a high-performance, non-blocking, multi-channel analytical subsystem operating concurrently with existing DvachBot core operations.

```
                  ┌─────────────────────────────────────────────────────────┐
                  │                 SQLite WAL Database                     │
                  │                 (dvach_bot.db ~1.7GB)                   │
                  └─────────────────────────┬───────────────────────────────┘
                                            │ read-only URI (?mode=ro)
                    ┌───────────────────────┴────────────────────────┐
                    │                                                │
                    ▼                                                ▼
     ┌─────────────────────────────┐                  ┌─────────────────────────────┐
     │   Analytics Engine Core     │                  │   FastAPI WebApp Backend    │
     │     (stats_v2.py /          │                  │        (site_tgach)         │
     │      stats_hub.py)          │                  │                             │
     └──────────────┬──────────────┘                  └──────────────┬──────────────┘
                    │                                                │
          ┌─────────┴─────────┐                            ┌─────────┴─────────┐
          │                   │                            │                   │
          ▼                   ▼                            ▼                   ▼
┌──────────────────┐ ┌──────────────────┐        ┌──────────────────┐ ┌──────────────────┐
│  Visual Posters  │ │  2ch Wrapped     │        │  REST APIs       │ │  Interactive UI  │
│  (1200x675 HD)   │ │  Card Generator  │        │  (/api/stats/*)  │ │  (/app/stats)    │
│  Dark Cyberpunk  │ │  (/my_wrapped)   │        │  Cached < 15ms   │ │  Chart.js/Plotly │
└─────────┬────────┘ └────────┬─────────┘        └──────────────────┘ └──────────────────┘
          │                   │
          └─────────┬─────────┘
                    │
                    ▼
     ┌─────────────────────────────┐
     │  Telegram Hub & Routers     │
     │  (/stats_hub, /deck, etc.)  │
     │  aiogram v3 (buffered I/O)  │
     └─────────────────────────────┘
```

## Feature Inventory
Every feature from ORIGINAL_REQUEST.md mapped to its assigned milestone:

| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| F1 | Economy & Crime Matrix | Heist/robbery matrix, casino RTP / gamblers' graveyard, airdrop speed, wealth tax & Abu yacht fund | M1 | ORIGINAL_REQUEST §R1 |
| F2 | PvP & Bioweapons Radar | Debuff warfare (shit/vomit/flags/curses), tinfoil hat ablation/reflection ROI, schizo-pill psych ward | M1 | ORIGINAL_REQUEST §R1 |
| F3 | Sociology & Drama Graph | Signed directed beef graph ($BII$), board toxicity quotient ($BTQ$), survival curves (Kaplan-Meier), attention parasitism | M1 | ORIGINAL_REQUEST §R1 |
| F4 | Memetics & Vision Analytics | pHash bayano-meter clustering on 60k files, AI vision tag constellation, slang trend drift, pasta & originality index | M1 | ORIGINAL_REQUEST §R1 |
| F5 | Instant Text Snapshot & Sparklines | Sub-100ms rich HTML overview with dynamic 8-level ASCII sparklines ( ▂▃▅▆▇█ ) | M2 | ORIGINAL_REQUEST §R2 |
| F6 | Interactive Inline Category Menu | Keyboard routing `[💰 Экономика]`, `[⚔️ PvP]`, `[🧠 Социология]`, `[🖼 Мемы]`, `[🎴 Мой Срез]`, `[✨ WebApp]` | M2 | ORIGINAL_REQUEST §R2 |
| F7 | Async HD Poster Delivery | Non-blocking background rendering + in-memory `BufferedInputFile` photo delivery on category click | M2 | ORIGINAL_REQUEST §R2 |
| F8 | Personal 2ch Wrapped Card | Spotify Wrapped style user card with archetype classification, combat/financial record, degradation meter | M3 | ORIGINAL_REQUEST §R3 |
| F9 | AI/Heuristic Diagnosis | Sarcastic clinical psychiatric diagnosis & summary of user's 2ch behavior | M3 | ORIGINAL_REQUEST §R3 |
| F10 | FastAPI WebApp Route `/app/stats` | Interactive dashboard with dark cyberpunk theme, time range filters (24h, 7d, 30d, All), board filters | M4 | ORIGINAL_REQUEST §R4 |
| F11 | REST APIs `/api/stats/*` | Fast JSON endpoints (<15ms) with in-memory caching (`FastAPICache`) for all analytics categories | M4 | ORIGINAL_REQUEST §R4 |
| F12 | Interactive Reply Graph & Visuals | Live Plotly/Chart.js network visualization of beef/replies and distribution curves | M4 | ORIGINAL_REQUEST §R4 |
| F13 | Autonomous Verification Suite | Automated tests validating 100% image renders, zero NaNs, memory cleanup `plt.close('all')`, API latencies | M5 | ORIGINAL_REQUEST §R5 |
| F14 | Backward Compatibility Gate | Strict regression testing verifying `/bot_stats`, `/stats`, `/my_stats`, and `periodic_publisher.py` | M5 | ORIGINAL_REQUEST §R5 |

## Milestones

| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Standalone Analytics & Visual Posters Module | Implement `stats_v2.py` / `stats_hub.py` analytics core + 4 HD dark cyberpunk poster generators (1200x675) | none | PLANNED |
| M2 | Telegram Hub & Interactive Menu Handlers | Implement aiogram v3 router for `/stats_hub`, `/deck`, `/stats2`, instant ASCII sparklines, inline callback routing | M1 | PLANNED |
| M3 | Personal "2ch Wrapped" Card Generator | Implement `/my_wrapped` user card generator, archetype classifiers, combat/financial breakdown, sarcastic diagnosis | M1 | PLANNED |
| M4 | Standalone FastAPI WebApp Dashboard | Implement `site_tgach` routes `GET /app/stats`, templates `stats_dashboard.jinja2`, Chart.js/Plotly charts, cached `/api/stats/*` | M1 | PLANNED |
| M5 | E2E Integration, Visual Verification & Adversarial Suite | Comprehensive Tier 1-5 test suite, pixel/font/layout audit, concurrency stress tests, backward compatibility verification | M1, M2, M3, M4 | PLANNED |

## Interface Contracts

### M1 Analytics Core ↔ M2 Telegram Hub
- `async def generate_hub_snapshot() -> Tuple[str, InlineKeyboardMarkup]`: Returns instant HTML formatted text with ASCII sparklines + category buttons.
- `async def render_category_poster(category: str) -> bytes`: Returns raw PNG bytes for `BufferedInputFile(..., filename=f"{category}.png")`.
  - Categories: `"economy"`, `"pvp"`, `"sociology"`, `"memetics"`.

### M1 Analytics Core ↔ M3 2ch Wrapped
- `async def generate_user_wrapped(user_id: int) -> Tuple[bytes, str]`: Returns `(png_bytes, caption_html)`.
- Fallback: Gracefully handles users with low/zero history with custom "Ньюфаг / Призрак" archetype.

### M1 Analytics Core ↔ M4 FastAPI WebApp
- `async def get_stats_data(category: str, timespan: str, board: Optional[str] = None) -> Dict[str, Any]`: Structured dictionary for REST endpoints `/api/stats/{category}`.
- Caching: `@cache(expire=30)` on FastAPI endpoints.

### Concurrency & Threading Contract
- All SQLite queries use read-only URI: `sqlite3.connect("file:dvach_bot.db?mode=ro", uri=True, timeout=15.0)`.
- All Matplotlib figure creations and exports MUST be wrapped in `with matplotlib_guard():` from `common.chart_lock` with explicit `plt.close(fig)` or `plt.close('all')` in a `finally` block.

## Code Layout
- `stats_v2.py` / `stats_hub.py`: Main analytics query engine & Matplotlib/PIL poster rendering engine (Owned by M1).
- `handlers/stats_hub_handlers.py` or `stats_hub_router.py`: Aiogram v3 Telegram commands & callback query handlers (Owned by M2).
- `wrapped_v2.py` or integrated into `stats_hub.py`: Wrapped card generator (Owned by M3).
- `site_tgach/routers/stats_dashboard.py` & `site_tgach/templates/stats_dashboard.jinja2`: FastAPI routes and frontend template (Owned by M4).
- `tests/test_stats_v2.py`, `tests/test_stats_hub_e2e.py`, `tests/test_visual_posters.py`: Test suites (Owned by M5).
- Legacy files (DO NOT MODIFY): `periodic_publisher.py`, `stats_manager.py` (legacy parts), existing command handlers in `main.py` lines 7163, 9858, 13324.
