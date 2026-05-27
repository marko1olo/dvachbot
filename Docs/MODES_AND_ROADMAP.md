# Modes And Roadmap

Scope: bot modes, creative systems, user retention, and future features.  
Date: 2026-05-12

## Current Modes

Active modes are per board. They are switched by commands and auto-disable after about 5 minutes.

Current list:

- Anime: `/anime`, `/nya`, `/kawai`, `/kawaii`
- Zaputin: `/zaputin`, `/z`, `/zov`, `/putin`
- Ukraine: `/slavaukraine`, `/slava_ukraine`, `/ukraine`, `/ukraina`, `/hohol`
- Suka blyat: `/suka_blyat`
- Polish: `/kurwa`, `/polish`, `/poland`
- Warhammer 40K: `/wh40k`, `/waha`, `/warhammer`, `/warhamer`
- Imperial/doreform: `/yer`, `/imperial`, `/imperia`, `/dorev`
- Gopnik: `/gopnik`, `/blyat`, `/gopota`
- Schizo: `/schizo`, `/shiza`, `/shiz`, `/durka`

Implementation:

- flags live in `board_data[board_id]`
- `_activate_mode()` turns on one mode and turns off the rest
- `_apply_mode_transformations()` rewrites text/caption before sending
- visual-capable modes can return `('image', bytes)` for short text
- `mode_visuals.py` renders template images

## Current Quality

Strong:

- modes have real dictionaries and phrase banks
- some modes use visual cards, not only text replacements
- activation/deactivation posts make modes visible as chat events
- mode cooldown prevents constant mode spam
- transforms run in executor, so heavy text work does not directly block the event loop

Weak:

- too much duplicated activation code in `main.py`
- several mode texts are embedded in `main.py` instead of their mode modules
- mode list is duplicated in multiple places
- mode policy is not data-driven
- mode state and mode timer are fragile if future edits add branches
- no per-mode performance timing
- no A/B tracking for retention or user reaction

## Recommended Mode Refactor

Do not rewrite behavior first. Make a registry around the existing behavior.

Target structure:

```python
MODE_REGISTRY = {
    "gopnik": {
        "flag": "gopnik_mode",
        "commands": ("gopnik", "blyat", "gopota"),
        "duration": 300,
        "disabled_boards": {"int"},
        "start_phrases": GOPNIK_PHRASES_START,
        "end_phrases": GOPNIK_PHRASES_END,
        "transform": gopnik_transform,
        "admin_prefix": {"ru": "### АДМИН ###", "en": "### ADMIN ###"},
    },
}
```

Why:

- one activation function
- one deactivation function
- one cooldown path
- one DB settings update path
- easier to add/remove modes without breaking old ones

Rejected approach:

- adding more copy-pasted command functions. That works once and becomes maintenance rot.

## New Mode Ideas

Priority should be high-retention, low-cost, fast to understand.

### 1. Суд Нюрки

Concept:

- chat enters mock-court mode
- every post is formatted as testimony, objection, sentence, exhibit
- replies become “Exhibit A -> Exhibit B”

Cheap implementation:

- text replacement + random courtroom prefix
- no network calls

High-end version:

- visual “case file” cards for short posts
- generated stamp overlays: `ВИНОВЕН`, `ПОШЕЛ НАХУЙ`, `УЛИКА`

### 2. Подводный Архив

Concept:

- deep sea noir mode matching TGACH/Hecton tone
- posts become sonar logs, black box pings, pressure warnings
- old replies are “salvaged fragments”

Cheap:

- deterministic text templates

High:

- dark terminal/sonar visual cards
- fake corrupted telemetry footer

### 3. Радиорубка

Concept:

- all messages become radio transmissions with static, callsigns, interference
- good for chaotic /b/ because it amplifies short messages

Cheap:

- prefix/suffix noise and replacements

High:

- voice-note TTS/radio filter later, only if CPU budget allows

### 4. Бюрократия

Concept:

- every post becomes an official memo, complaint, act, requisition
- replies become document references

Cheap:

- Russian clerical replacements
- stamp emoji/text

High:

- image cards as scanned forms

### 5. Архив Двач-Палеонтолога

Concept:

- bot “classifies” anons and posts as extinct internet species
- good for user retention because users like being assigned stupid labels

Cheap:

- random taxonomy per post

High:

- profile/passport integration: user accumulates fake species traits

## Chess Request

User suggestion: chess with funny pictures/characters.

Assessment:

- In-bot full chess is possible but not cheap in UX.
- Telegram bot cannot run peer-to-peer; the server holds game state.
- Rendering the board as images is okay; chess move validation should use an existing Python chess library, not handwritten rules.
- Best first implementation is site-first, bot-linked.

Recommended version:

1. Use `python-chess` for legal moves.
2. Store games in SQLite:
   - game_id
   - white_user_id
   - black_user_id
   - FEN
   - status
   - last_move_at
3. Bot commands:
   - `/chess @user`
   - `/move e2e4`
   - `/board`
4. Site page renders the board and piece skins.
5. Bot sends board image after each move.

Do not implement from scratch. Handwritten chess rules are a bug farm.

## Free/Low-Cost Image Generation Options

Current candidates to prototype behind a strict queue and per-user cooldown:

- Pollinations image endpoint: simple public URL/API workflow, useful for low-friction experiments. Current docs require API keys for generation requests, so treat it as a server-side integration, not a naked public URL in chat.
- Cloudflare Workers AI: production-shaped API with documented free/paid tiers and image models. Good if Cloudflare is already acceptable infrastructure, but it still needs hard bot-side quotas.
- Hugging Face Inference Providers: broad model access, but free capacity is tiny and subject to change. Good for experiments, bad as the only production provider.
- Google Gemini image generation: Gemini built-in image generation exists; Imagen models are marked paid tier in the current Google docs. Use only if key/rate limits are acceptable.
- Existing local/free text/image analysis stack in `stomchat`: reuse only if keys and rate limits are understood.

Reference links checked on 2026-05-12:

- Pollinations API docs: https://github.com/pollinations/pollinations/blob/main/APIDOCS.md
- Cloudflare Workers AI pricing: https://developers.cloudflare.com/workers-ai/platform/pricing/
- Hugging Face Inference Providers pricing: https://huggingface.co/docs/inference-providers/pricing
- Google Gemini image generation: https://ai.google.dev/gemini-api/docs/image-generation

Hard rule:

- never put image generation in the message hot path without a queue
- generate asynchronously
- return “job accepted” quickly
- per-user cooldown
- per-board daily budget
- store generated file IDs after first Telegram upload

Suggested bot commands:

```text
/imagine prompt
/imagine_status
/imagine_cancel
```

MVP:

- text prompt only
- one image
- 60-120 second per-user cooldown
- reject huge prompts
- no retries during high queue lag

## Retention Features

The bot already has profile/passport, stats, wallet/prank, modes, threads, search, polls, random/media commands. Next retention should not be random bloat. It should make users feel the bot remembers the chat.

Recommended:

- weekly active badge in `/passport`
- personal “you were replied to” digest
- top reply chains of the day
- “best thread wreckage” digest
- mode leaderboard:
  - most used mode
  - most replied post during mode
  - mode that caused most activity
- lightweight achievements:
  - first reply
  - first thread OP
  - got 10 replies
  - necropost reply to old post

Do not add heavy AI before queue/memory observability is sane.

## Priority Roadmap

### P0: Reliability

- restart bot after compiled reply fix
- add rotating bot log
- add queue lag telemetry: completed fanouts now log `post_age_sec`, `queue_wait_sec`, and `queue_total_sec`; live oldest queued item/current fanout is visible in runtime snapshots and `/queues`
- add `PostCopies` coverage telemetry: implemented as cached `reply_coverage` and `/queues Reply copies`
- make admin stats operational

### P1: Delivery Priority

- weekly active users are now tracked from `Posts`
- recipient fanout is now ordered active/passive in `send_message_to_users()`
- passive delivery is still kept
- still missing persisted fanout progress
- persist fanout progress

### P2: Mode Registry

- data-driven mode registry
- move embedded mode phrases out of `main.py`
- add per-mode timings
- keep all current mode behavior

### P3: Creative Expansion

- add one new cheap mode first
- add image generation queue only after telemetry
- site-first chess prototype if still wanted

## Low/Mid/High/Ultra Scaling

Low-end toaster:

- text-only modes
- no live image generation
- RAM copy cache around 400 posts for Telegram copy maps; heavy logical post cache remains `BOT_POST_CACHE_LIMIT` posts
- SQLite fallback for older replies
- active-user priority fanout

Mid:

- visual mode cards for short posts
- image generation queue with strict cooldown
- 12000 post copy retention

High:

- richer visual templates
- longer copy retention
- more analytics
- background pre-generation of mode assets

Ultra:

- separate fanout service
- separate copy-store/shard
- Redis or disk-backed priority queue

## 2026-05-15 Punch-Up Pass

Changed:

- Added `20260515` phrase/replacement/signature expansions for all 14 punch-up modes.
- Added contextual autoreply groups for image command contracts, style/creative feedback, and visible stdout/process complaints.
- Kept the change text-only. Image source logic, anime/loli tags, ratings, source order, and requested image counts were not changed.

Verification:

```text
mode_punchup_smoke = ok, 14 profiles
contextual_smoke = ok, 27 extension groups
timing short/medium/dense = 0.37ms / 1.31ms / 5.99ms avg
live restart = pid 37088, health HTTP 200, queues_total 0
```
- multiple bot tokens/pools with measured throughput
- image/video generation worker isolated from bot loop

## User Mode Backlog 2026-05-13

Implemented now:

- `/matrix`, aliases `/matrica`, `/matriza`, `/redpill`, `/neo`
  - theme: simulation, operator, agents, green terminal rain
  - implementation: text-only transform in `new_modes.py`
  - hot-path cost: regex replacement with precompiled pattern, no image generation
- `/america`, aliases `/usa`, `/liberty`, `/freedom`
  - theme: liberty, taxes, senate, lobbyists, corporate patriotism
  - implementation rule: satire of institutions and bureaucracy, not a blanket attack on people
- `/holiday`, aliases `/newyear`, `/xmas`, `/christmas`, `/ny`
  - theme: New Year/Christmas, snow, tinsel, mandarins, gift audit
  - can be manually enabled any time; later this can become an automatic December-January seasonal mode
- `/oldweb`, aliases `/oldnet`, `/icq`, `/winamp`, `/forum`
  - theme: forums, ICQ, Winamp, dial-up, guestbook, 88x31 banners, homepages
  - deliberately avoids random modern meme soup; the user feedback was correct that "lemurs/zbagoynich" is not enough to read as old internet
- `/jewish`, aliases `/talmud`, `/odessa`, `/shabbat`, `/rabbi`, `/evrei`, `/evrey`
  - public framing: Talmudic/Odessa debate mode
  - theme: questions, counterquestions, marginal comments, scrolls, protocol rabbi, argument bureaucracy
  - guardrail: no biological/ethnic claims, no collective blame, no conspiracy hooks, no "money-greedy" stereotype loop
  - implementation: text-only transform in `new_modes.py`, same precompiled-regex model as the other new modes

Expanded on 2026-05-13 after user feedback:

- Matrix/America/Holiday/Oldweb received larger replacement dictionaries, more prefixes/suffixes/injections, and higher replacement density (`replace_chance` around `0.62`).
- `/jewish` shipped only under the non-hateful Talmudic debate framing above. The risky version remains rejected: no ethnicity-as-punchline generator.
- All text modes now pass through a cheap `mode_punchup.py` layer after their main transform.
- Punch-up profiles exist for `anime`, `zaputin`, `slavaukraine`, `suka_blyat`, `polish`, `warhammer`, `imperial`, `gopnik`, `schizo`, `matrix`, `america`, `holiday`, `oldweb`, and `jewish`.
- The punch-up layer now has `55` replacement triggers per mode, `6` prefixes, `6` suffixes, `7` injection phrases, and `6` signature punchlines per mode. It does not call the network, does not create files, does not hold per-user memory, and does not touch SQLite.
- 2026-05-14 signature pass: added a low-cost final punchline layer with `signature_chance=0.16` and `max_text_for_signature=1200`.
- Fresh 1200-call local sample on a source-trigger Russian post measured short text at roughly `0.05-0.16ms avg` and `0.09-0.34ms p95`; a 4x repeated sample measured roughly `0.21-0.48ms avg` and `0.34-0.84ms p95`. Rare interpreter/GC max spikes still happen, so do not keep expanding this hot path blindly without per-mode timing.
- Operational rollback: set `BOT_MODE_PUNCHUP_ENABLED=0` to keep the base mode transforms but disable the shared punch-up layer during CPU/lag incidents. Runtime JSON exposes this as `mode_punchup.enabled`.
- Live admin control: `/punchup`, `/punchup status`, `/punchup off`, `/punchup on`, `/punchup reset`.
- Queue load shedding skips only the shared punch-up layer when board queue/in-flight age crosses `BOT_MODE_PUNCHUP_QUEUE_SHED_SEC`.
- Slow punch-up calls are logged as `mode_punchup_slow` when they cross `BOT_MODE_PUNCHUP_SLOW_LOG_US`.
- Anime/media commands now have hard network guardrails after the 2026-05-13 stall: URL fetches are bounded by `BOT_ANIME_URL_FETCH_TIMEOUT_SEC`, `BOT_ANIME_URL_FETCH_TOTAL_SEC`, and `BOT_ANIME_URL_FETCH_PARALLEL`; downloads are bounded by `BOT_ANIME_DOWNLOAD_TIMEOUT_SEC`, `BOT_ANIME_DOWNLOAD_TOTAL_SEC`, and `BOT_ANIME_DOWNLOAD_PARALLEL`.
- These limits intentionally make external media fail fast when APIs/proxies stall. Richer mode visuals should move to a sidecar/cache path, not block the bot event loop.
- 2026-05-14 extra punch-up pass: every shared profile now receives another small vocabulary/signature layer without touching image commands. Local sample after load: `anime_mode` has `8/8/9/9` prefixes/suffixes/injections/signatures and `57` replacement entries; warhammer/polish/slavaukraine/oldweb have `58` replacement entries.
- 2026-05-14 contextual autoreply expansion: Russian `CONTEXTUAL_REPLIES` installs eight new satirical trigger groups for health/deadlock, site/frontend, modes, AI/prompt talk, censorship/moralizing, office work, crypto, and chess. This is independent from mode transforms and can be removed by deleting the `contextual_flavor` install call.
- 2026-05-15 contextual autoreply expansion: added five more RU trigger groups for albums/media groups, media content types, reactions/notifications, polls, and settings/commands. This remains text-only and does not touch image commands, anime/loli source logic, tags, ratings, or requested image counts.
- Live verification after restart: `contextual_replies.groups_ru=92`, `queues_total=0`, `health=HTTP 200`, `runtime pid matches lock`.

Technical notes:

- New modes use the existing one-active-mode model and `Boards.settings` JSON flags; no SQLite schema change.
- New mode flags are reset on restart the same way current mode flags are intentionally reset during `load_state_from_db()`.
- The activation helper only creates one system post, updates `messages_storage`, enqueues a normal fanout, then calls `_activate_mode()`.
- No generated images, no external APIs, no extra long-lived caches.
