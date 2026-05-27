# TGACH Bot/Site Architecture

Date: 2026-05-12  
Scope: `C:\Users\danat\Desktop\dvachbot`

This document describes the Python Telegram bot and the FastAPI site as they exist now. It separates logical posts on the site from physical Telegram message copies in the bot. That distinction is critical.

## Runtime Processes

- Bot: `start_bot.bat` -> `python bot_watchdog.py` -> `python main.py`
- Site: `start_site.bat` -> `python -m uvicorn site_tgach.main:app --host 127.0.0.1 --port 8000`
- Shared database: `dvach_bot.db`
- Shared database module: `common/database.py`
- Shared configuration: `common/config.py`
- Site entry point: `site_tgach/main.py`
- Bot entry point: `main.py`

`start_bot.bat` is a visible supervisor launcher. `bot_watchdog.py` is the external process supervisor: it starts `main.py`, writes child stdout/stderr to `logs/bot_stdout_utf8.log`, writes supervisor decisions to `logs/bot_supervisor.log`, probes healthcheck from outside the bot process, and restarts the child when health repeatedly fails and logs are stale.

`stop_bot.bat` reads `bot.lock`, walks up through `bot_watchdog.py` / `start_bot.bat`, stops that process tree, and removes the lock. Use it instead of killing random Python processes.

## Core Data Model

### Posts

`Posts` is the logical source of truth for post content.

It stores:

- global `post_num`
- `board_id`
- `author_id`
- serialized `content`
- `timestamp`
- `is_shadow`
- `thread_id`
- `stream`
- site/bot origin markers such as `is_from_site`

The same `post_num` is used on the site and in the bot. This does not mean the site post and every Telegram message copy are the same object.

### Bot Copies

`PostCopies` is the Telegram delivery map:

- `post_num`
- `recipient_id`
- `message_id`

Telegram gives each user a different `message_id` in the private chat with the bot. A real Telegram reply needs the exact `(recipient_id, message_id)` pair. `Posts.post_num` alone is not enough.

Practical rule:

- Site history can render from `Posts`.
- Bot quote text can render from `Posts`.
- Real Telegram reply threading requires `PostCopies`.

If `PostCopies` is deleted for a post, the bot can still show a text quote, but it cannot reconstruct the real Telegram `reply_to_message_id`.

### Channel Copies

`ChannelCopies` maps a logical post to message IDs in archive/storage channels. It has the same retention risk as `PostCopies` for edit/delete operations in channels.

### BroadcastQueue

`BroadcastQueue` is used when a post is created on the site and must be pushed to Telegram users.

Site post flow:

1. `site_tgach/main.py` creates a post with `is_from_site=True`.
2. `common/database.py::create_post()` inserts the logical post into `Posts`.
3. For site-origin posts, `create_post()` also inserts a row into `BroadcastQueue`.
4. Bot background task `site_broadcast_queue_processor()` reads unsent rows via `get_and_clear_broadcast_queue()`.
5. Bot sends the post to active users and records physical copies in `PostCopies`.

This is why site and bot posts share numbering and storage, but bot delivery still needs a second table.

## Bot Post Lifecycle

### User Sends Message To Bot

`main.py::handle_message()` handles normal incoming bot messages.

Main steps:

1. Detect board and user stream.
2. Reject unsupported message types.
3. Check ban/mute/shadow mute.
4. Delete the original user message from the bot chat.
5. Resolve reply target:
   - RAM: `message_to_post[(chat_id, message_id)]`
   - DB: `get_post_info_by_copy(chat_id, message_id)`
   - last fallback: parse visible post number from replied message text/caption
6. Build `content`.
7. Add `quote_info` if the target post is far enough behind current max post.
8. Call `process_shadow_reject()` or `process_new_post()`.

### Normal Post

`process_new_post()`:

1. Applies active board mode transformations via `_apply_mode_transformations()`.
2. Creates logical row in `Posts`.
3. Formats header.
4. Sends the author their own copy.
5. Queues broadcast to other active users via `message_queues[board_id]`.
6. Worker calls `send_message_to_users()`.
7. Sent Telegram message IDs are written to:
   - RAM: `post_to_messages`, `message_to_post`
   - DB: `PostCopies`

### Shadow-Rejected Post

`process_shadow_reject()`:

1. Does not create a real post in `Posts`.
2. Builds a fake header/post number for the muted user only.
3. Sends the post only to that user.
4. Must use the same reply resolver as normal posts, otherwise shadow mute becomes detectable.

Current fix: shadow reject now places `reply_to_post` in `content` and does not pass a global post number as if it were a Telegram `message_id`.

Additional stealth fixes:

- audited shadow reject call sites pass `stream`, so fake posts do not fall back to the wrong language header
- multi-reply paths pass `stream` for both shadow and normal delivery
- `shadow_fake_post_counters[(board_id, user_id)]` keeps fake numbers from repeating during a shadowed burst

Limit: this is not full per-recipient post-number virtualization. A user who posts many fake messages while the public counter barely moves can still create numbering drift. Full concealment would require translating all visible post numbers for that recipient.

## Reply System

There are three reply layers:

1. Logical reply: `content['reply_to_post'] = post_num`
2. Text quote: `content['quote_info']`
3. Telegram native reply: `reply_to_message_id`

Native Telegram replies are best UX, but they are recipient-specific. The bot resolves them in `send_message_to_users()`:

1. If explicit `reply_info` has a message ID for this user, use it.
2. Else if `post_to_messages[reply_to_post][uid]` exists in RAM, use it.
3. Else load `get_post_copies(reply_to_post)` from SQLite and use `db_replies_map[uid]`.
4. If Telegram rejects with `message to be replied not found`, retry without native reply and keep the content visible.

Important: a fallback text quote is not a replacement for `PostCopies`. It only prevents the conversation from becoming unreadable.

Current quick-quote behavior:

- helper: `build_quick_quote_info(reply_to_post)`
- threshold: `QUICK_QUOTE_POST_DISTANCE = 330`
- source: logical `Posts.content`, not Telegram copy state
- supported attachment hints: `photo`, `video`, `animation/GIF`, `document`, `audio`, `voice`, `sticker`, `video_note`, media groups, direct `file_id`, image bytes/URLs, and polls
- applied to normal text/media/audio/voice/video_note posts and multi-reply flows

This means a reply to an older post can still carry a compact quote with attachment summary even when native Telegram reply threading is unavailable for that recipient.

## Memory Model

Hot in-RAM maps:

- `messages_storage`: recent logical posts
- `post_to_messages`: recent `post_num -> recipient -> Telegram message_id`
- `message_to_post`: recent `(recipient, message_id) -> post_num`
- `board_data`: active users, settings, mutes, thread state, mode state, spam trackers
- `message_queues`: per-board outgoing queues

The bot has an `auto_memory_cleaner()` that trims:

- `messages_storage`
- `post_to_messages`
- `message_to_post`
- stale user state
- some global caches

The database keeps the durable truth. RAM is only acceleration and recent context.

## Runtime Telemetry

The bot writes lightweight operational snapshots to:

```text
logs/bot_runtime.log
```

Each `runtime_snapshot` line includes process memory, DB/WAL/SHM file sizes, per-board queue sizes, queued item age, current in-flight fanout, hot RAM map sizes, cooldown/rate map sizes, media group state, pending edit tasks, reaction queue item count, asyncio task count, and GC counters.
Completed board fanouts also write `delivery_result` lines with post number, recipient count, priority/passive split, success/errors/retries, elapsed seconds, `post_age_sec`, `queue_wait_sec`, and `queue_total_sec` when timestamps are available.
Reply-health coverage is refreshed by `reply_coverage_refresh_task()` and cached into `runtime_snapshot.reply_coverage`: total copy rows, distinct posts with copies, min/max covered post, latest-post gap, and per-board spans.

Admin commands:

- `/queues`: RAM queue size for the current board, total/top board queues, live queued age/current fanout, reply copy coverage, DB queue counters, RSS/private memory, weekly-active delivery priority counts, and last delivery timing if a delivery has completed since process start.
- `/debug_memory`: runtime snapshot plus `tracemalloc` allocation lines. First call starts `tracemalloc` if it was not active.

The telemetry is deliberately cheap. It does not call `gc.get_objects()` on a timer. Heavy object distribution remains manual via the older debug path.

The emergency `memory_restarter()` uses `max(RSS, private/USS)` for its limit check. This matters on Windows because private committed memory can be the number that kills the process even when RSS/working set looks lower.

## Current Retention Policy

Configuration in `common/config.py`:

- `DB_POST_LIMIT`: logical post retention/cleanup target in SQLite. Default: `25000`.
- `BOT_POST_CACHE_LIMIT`: how many recent logical posts load into the heavy RAM content cache. Default: `3300`.
- `BOT_COPY_CACHE_POST_LIMIT`: how many recent posts hydrate Telegram copy maps into RAM. Default: `400`.
- `POST_COPY_RETENTION_POSTS`: minimum rolling post window to keep `PostCopies`/`ChannelCopies` in SQLite. Default: `12000`.
- `POST_COPY_RETENTION_DAYS`: minimum age window to keep `PostCopies`/`ChannelCopies` in SQLite. Default: `30`.
- `BOT_PRIORITY_DELIVERY`: enable weekly-active first delivery order. Default: enabled.
- `BOT_WEEKLY_ACTIVE_DAYS`: post activity window for priority delivery. Default: `7`.
- `BOT_WEEKLY_ACTIVE_REFRESH_SEC`: how often the priority list refreshes from SQLite. Default: `900`.
- `BOT_PRIORITY_SPLIT_FANOUT`: send weekly-active recipients first and defer the passive tail. Default: enabled.
- `BOT_PRIORITY_SPLIT_MIN_PASSIVE`: minimum passive tail size before split fanout activates. Default: `30`.
- `BOT_PRIORITY_PASSIVE_SLICE_SIZE`: maximum text passive recipients per passive slice. Default: `90`.
- `BOT_DELIVERY_INITIAL_CHUNK_SIZE`: starting per-phase send chunk size. Default: `12`.
- `BOT_DELIVERY_MIN_CHUNK_SIZE`: minimum chunk size after FloodWait backoff. Default: `3`.
- `BOT_DELIVERY_PER_RECIPIENT_TIMEOUT_SEC`: watchdog around one recipient send task. Default: `20`.
- `BOT_DELIVERY_MAX_RECIPIENT_RETRIES`: maximum retry cycles for one recipient inside one phase. Default: `5`.
- `BOT_EVENT_LOOP_HEALTH_STALE_SEC`: healthcheck stale threshold when the asyncio tick task stops updating. Default: `20`.

This split is intentional:

- hot replies stay fast from RAM
- older replies stay possible through indexed SQLite
- startup does not load millions of copy rows into Python dicts

## Queues And Backpressure

Bot board queues:

```python
message_queues = {board: asyncio.Queue(maxsize=0) for board in BOARDS}
```

This is unbounded. Under CPU saturation or Telegram FloodWait, `/b/` can accumulate delay because one board worker processes posts sequentially and each post fans out to active recipients.

Site WebSocket queue:

```python
app.state.broadcast_queue = asyncio.Queue(maxsize=1000)
```

The site has a bounded real-time broadcast queue. The bot does not yet have the same pressure control.

Current bot mitigation:

- all board queue producers go through `enqueue_board_message()`, which stamps `enqueued_at`
- runtime telemetry records queued oldest/average age and the current in-flight post per board
- completed fanouts record `queue_wait_sec` and `queue_total_sec`
- `weekly_active_refresh_task()` reads authors who wrote visible posts during the last `BOT_WEEKLY_ACTIVE_DAYS`.
- The first priority refresh runs as soon as the background task starts; later refreshes use `BOT_WEEKLY_ACTIVE_REFRESH_SEC`.
- `send_message_to_users()` reorders recipients as `weekly-active -> passive`.
- `message_worker()` can split main-board fanout: active weekly users are delivered first, the passive tail is requeued as `delivery_phase=passive`.
- passive delivery is sliced by `BOT_PRIORITY_PASSIVE_SLICE_SIZE`, so new full posts can jump ahead between passive slices.
- every recipient send task is wrapped by `BOT_DELIVERY_PER_RECIPIENT_TIMEOUT_SEC`, and fanout send methods pass a lower aiogram `request_timeout`, so one stuck Telegram/aiohttp request cannot hold the whole board worker forever.
- one recipient can only cycle through `BOT_DELIVERY_MAX_RECIPIENT_RETRIES` retry attempts in a delivery phase.
- Telegram media URL failures such as `wrong type of the web page content` fall back to text + original link instead of turning the whole phase into media-send errors.
- Passive users are still delivered to; this is not message dropping.
- New non-shadow bot posts mark their author hot immediately, before the next DB refresh.
- `logs/bot_runtime.log` includes `weekly_active_refresh` and `delivery_priority` telemetry.

Healthcheck is now served by a small `ThreadingHTTPServer` outside the bot's asyncio loop. The handler reports `status`, `pid`, `loop_lag_sec`, queue totals, and `post_counter`. If the loop tick is stale, the handler returns HTTP `503` with `status=stale` instead of timing out with the bot loop.

This improves perceived lag during CPU saturation, but it is not full persisted fanout. If the process dies while `message_queues` holds unsent items, those in-RAM queue items are still at risk. The durable end-state is still a persisted delivery job table with per-recipient progress.

## Memory Cleanup Notes

`auto_memory_cleaner()` trims the hot post window using `BOT_POST_CACHE_LIMIT` and removes matching entries from both `post_to_messages` and `message_to_post`.

Additional guard: old one-off reverse lookups from DB fallback can create `(chat_id, message_id) -> post_num` entries that do not exist in `post_to_messages`. The cleaner now prunes `message_to_post` entries whose `post_num` is outside the current hot `messages_storage`/`post_to_messages` window. If a user replies to that old Telegram copy later, SQLite `PostCopies` is still the durable resolver.

`shadow_fake_post_counters` is also bounded by the global cache cleaner and cleared if it grows past the emergency cache threshold.

Small operational maps are TTL-pruned by the cleaner too: hourly image counters, thread-viewer cooldowns, reaction ratelimits, poll cooldowns, and author reaction notification throttles. They are visible in `runtime_snapshot.maps`.

`message_worker()` filters `uid > 0` before live in-flight fanout telemetry. Negative site guest IDs may exist in board user state, but bot fanout metrics count actual Telegram users only.

Nested `board_data` maps are now visible in `runtime_snapshot.board_maps`. This includes spam tracker item counts, reaction-rate item counts, reaction queue items, command cooldown maps, image-spam items, thread locks, and anime daily trackers. The cleaner prunes expired `anime_daily_tracker`, stale `image_spam_tracker`, old `unknown_command_tracker`, and thread locks whose thread no longer exists.

## Modes

Active board modes are flags inside `board_data[board_id]` and persisted in board settings:

- `anime_mode`
- `zaputin_mode`
- `slavaukraine_mode`
- `suka_blyat_mode`
- `polish_mode`
- `warhammer_mode`
- `imperial_mode`
- `gopnik_mode`
- `schizo_mode`

Only one mode should be active at once. `_activate_mode()` clears the other flags and starts an auto-disable task.

Transform dispatcher:

```python
_apply_mode_transformations(content, board_id)
```

Mode modules:

- `zaputin_mode.py`
- `ukrainian_mode.py`
- `polish_mode.py`
- `warhammer_mode.py`
- `imperial_mode.py`
- `gopnik_mode.py`
- `shizo_mode.py`
- `japanese_translator.py`
- `mode_visuals.py`

Several modes can generate visual posts for short text through `mode_visuals.create_visual_post()`.

## Site Architecture Notes

The site uses:

- FastAPI
- Jinja templates
- WebSockets via `ConnectionManager`
- `FastAPICache` with `InMemoryBackend`
- `async_lru` caches for settings and geo-IP
- background workers for imports, mirrors, Hugging Face batches, scanner, backups

Memory-relevant site globals:

- `CAPTCHA_SESSIONS`
- `POST_RATE_LIMITER`
- `SYSTEM_LOGS`
- `BOARD_VERSIONS`
- `THREAD_VERSIONS`
- `site_spam_tracker`
- `URL_STATUS_CACHE`
- `ConnectionManager.active_connections`

Most of these have cleanup or max-size behavior. The highest risk for slow memory growth is still in-process caching plus long-running background tasks, not one obvious infinite list.

Admin site visibility:

- `/api/admin/stats` now includes `process` and `runtime`
- `/api/admin/system_health` now includes `process` and `runtime`
- `process`: PID, RSS/private/VMS MB, threads, open files
- `runtime`: WebSocket connection count/key count, broadcast queue size, captcha sessions, spam tracker size, post-rate limiter size, system log count, spam-word board count, board/thread version map sizes, URL status cache size, request flood tracker size, known IP count, bot violation count, active IP bans, manual troll config count

The site cleanup task removes expired FastAPI cache entries, caps cache cardinality, trims stale thread/url maps, removes stale flood-tracker keys, and clears expired IP ban/troll entries. These are short-lived operational maps; the database remains the durable content source.

Site image processing uses bounded `ThreadPoolExecutor` workers for grimdark transforms and thumbnails. It previously used `ProcessPoolExecutor`, which duplicated large Python/PIL worker processes and left orphan `spawn_main` children after hard restarts. The site lifespan now calls `shutdown_image_executors()` during graceful shutdown.

This is admin-demand telemetry, not an always-on site logger.

The old `Dubsite_tgach` copy is not the active site package, but its image processor was also patched away from `ProcessPoolExecutor` to avoid recreating the same orphan-worker failure if someone launches that duplicate by mistake.

## Stomchat Notes

`C:\Users\danat\Desktop\stomchat` is a separate Telethon/OpenCV/Groq summary bot, not the dvachbot fanout process. It has its own databases:

- `stomat_bot.db`
- `stomat_archive.db`
- `stomat_wiki.db`

Recent hardening:

- `bot.log` now rotates through `RotatingFileHandler(5MB, backupCount=5)`.
- `runtime_memory` heartbeat logs process PID, RSS/private/VMS MB, thread count, and open file count every 900 seconds.
- post-restart baseline sample: PID `26736`, private memory about `413.64 MB`.

Do not infer dvachbot leaks from stomchat memory. They are separate Python processes with different workloads.

## Database Safety Rules

Production DB is live. Safe diagnostics:

- open SQLite read-only with `file:path?mode=ro`
- use `PRAGMA query_only=ON`
- avoid `VACUUM` while bot/site are running
- avoid destructive cleanup without a backup
- do not delete `PostCopies` casually; that destroys native Telegram replies

Recommended pre-maintenance sequence:

1. Stop bot first if changing copy/reply code.
2. Let site continue if only bot code changes.
3. Copy `dvach_bot.db`, `dvach_bot.db-wal`, `dvach_bot.db-shm` together if making a filesystem backup while WAL exists.
4. Restart bot.
5. Watch queue size and memory for at least 10 minutes.

## Mode System

Current mode system is still explicit and manual, not a true registry:

- `main.py` owns `MODE_FLAGS`, RAM flags in `board_data`, activation, headers, transform dispatch, cooldowns, and auto-disable.
- `common/database.py` loads mode flags from `Boards.settings`, but intentionally resets them to inactive on startup.
- Phrase/transform modules hold mode-specific text and replacement logic.
- `help_text.py` exposes public mode commands.

New lightweight modes added on 2026-05-13:

- `new_modes.py`
  - `/matrix`
  - `/america`
  - `/holiday`
  - `/oldweb`
  - `/jewish`
- all are text-only
- all use precompiled regex patterns
- all reuse `activate_lightweight_mode()`
- no image generation or external calls are made inside message delivery
- `/jewish` is implemented as Talmudic/Odessa debate style with content guardrails; do not turn it into protected-class stereotype replacement

This is acceptable as a controlled patch. Long-term cleanup should replace duplicated mode lists with a data-driven registry that defines:

- command aliases
- mode flag
- start/end phrases
- header style
- transform callable
- duration
- board restrictions
- safety/content notes

Do not refactor this during a memory/reply incident unless tests and restart window are available.

## Delivery Truth Fields

The bot now separates three different counts that previously looked like one number in console output:

- `recipients.telegram_active_by_board[board]`: active Telegram users loaded for the board.
- `delivery_result.phase_recipients`: recipients attempted in the current delivery phase.
- `delivery_result.original_recipients`: full logical fanout size for the post.
- `delivery_result.deferred_recipients`: passive recipients left for later slices.

This matters for `/b/` because split fanout intentionally sends weekly-active users first, then passive users in slices. A line like `91/91` is a priority phase, not the full board population.

Current split-fanout controls:

- `BOT_PRIORITY_SPLIT_FANOUT`
- `BOT_PRIORITY_PASSIVE_SLICE_SIZE`
- `BOT_PRIORITY_PASSIVE_MEDIA_SLICE_SIZE`
- `BOT_PASSIVE_MAX_PREEMPTIONS`
- `BOT_DELIVERY_SLOW_PHASE_SEC`

Current media-load controls:

- `BOT_ANIME_MEDIA_CONCURRENCY`
- `BOT_B_MAX_STACKED_ANIME_IMAGES`
- `BOT_ANIME_REFILL_ROUNDS`

Image command count integrity:

- stacked commands build one fetch slot per requested image, capped by the board maximum;
- URL fetch and download are bounded by per-item and total timeouts;
- if a slot fails, `_collect_stacked_anime_downloads()` retries only missing slots for `BOT_ANIME_REFILL_ROUNDS`;
- refill logs `anime_media_refill` with target, ready count, and missing count.

## Raw Health Responder

The current health responder is `_RawHealthcheckServer`, not aiohttp and not `ThreadingHTTPServer`.

Current behavior:

- accepts on a dedicated thread outside the bot event loop;
- returns the same JSON health body used by supervisor checks;
- sends `HTTP/1.1`, `Content-Length`, `Connection: close`;
- explicitly shuts down the socket after `sendall()` so PowerShell, urllib, and raw HTTP/1.1 clients do not hang waiting for EOF.

The live 2026-05-13 verification showed `/b/` had `625` active Telegram users in SQLite and runtime telemetry, while a typical split delivery at that time was `91 + 120 + 120 + 120 + 120 + 53/54`. The old scary number was a phase count. The later default text passive slice is `90` to reduce Telegram/FloodWait pressure.

The remaining architectural gap is unchanged: fanout progress is not durable. A crash or hard kill during a backlog can lose queued RAM work. The correct next architecture is a durable fanout job table with per-recipient progress and retry state.

## External Bot Supervisor

Added on 2026-05-13 after the in-process threaded healthcheck still proved insufficient. The repeated failure mode was a live PID that owned `bot.lock` and port `8080`, but no longer serviced the bot correctly.

Supervisor files:

- `bot_watchdog.py`
- `start_bot.bat`
- `stop_bot.bat`
- `logs/bot_supervisor.log`
- `logs/bot_stdout_utf8.log`

Supervisor knobs:

- `BOT_HEALTH_URL`, default `http://127.0.0.1:8080`
- `BOT_WATCHDOG_HEALTH_TIMEOUT_SEC`, default `5`
- `BOT_WATCHDOG_HEALTH_FAIL_LIMIT`, default `3`
- `BOT_WATCHDOG_POLL_SEC`, default `15`
- `BOT_WATCHDOG_WARMUP_SEC`, default `75`
- `BOT_WATCHDOG_LOG_STALE_SEC`, default `120`
- `BOT_WATCHDOG_RESTART_DELAY_SEC`, default `5`

Restart condition:

- child process has exited, or
- healthcheck fails repeatedly and both runtime/stdout logs are stale, or
- healthcheck explicitly returns `status=stale` / HTTP `503`

Latest verified chain after deployment:

```text
start window cmd.exe = 58728
supervisor shim/processes = 43256 -> 23944
main.py shim/processes = 69868 -> 46488
bot.lock = 46488
healthcheck = HTTP 200, status ok
health sample = {"status":"ok","pid":46488,"loop_lag_sec":0.487,"queues_total":0,"post_counter":375693}
runtime private_mb ~= 512-514
/b/ active Telegram users = 625
/b/ active site guests = 3361
SQLite quick_check = ok
Posts = 150649
PostCopies = 1449384
max_post = 375695
```

### Heartbeat Fallback And Image Command Safety

Follow-up on 2026-05-13: HTTP health was observed failing while `/b/` delivery was still making progress. The control plane now has a second process-external truth source:

- `main.py` writes `logs/bot_heartbeat.json` from `event_loop_health_tick_task`
- `bot_watchdog.py` reads the heartbeat before trusting stale runtime queue snapshots
- heartbeat reports `pid`, `queues_total`, `queues_top`, `post_counter`, and `is_shutting_down`
- `BOT_WATCHDOG_HEARTBEAT_STALE_SEC` controls heartbeat freshness

The HTTP health server remains useful, but the supervisor no longer has to infer queue safety from old runtime snapshots alone.

Anime/image commands now have bounded and redacted source handling:

- existing per-source negative tags are applied to booru API queries
- post metadata is filtered for blocked safety tags before selecting a media URL
- legacy `/loli` command is a compatibility command using the loli-tag source mix with non-explicit ratings and no-shota negative tags; the temporary safe cute/chibi alias was reverted
- source query logs use `rating` and `qhash`, not full query tags
- success/download logs use source, host, extension, and SHA-12 instead of full media URLs

Current verified chain:

```text
start window cmd.exe = 36128
supervisor shim/processes = 35556 -> 32376
main.py shim/processes = 71836 -> 3456
bot.lock = 3456
healthcheck = HTTP 200, status ok
heartbeat queues_total = 0
runtime private_mb = 497.11
/b/ active Telegram users = 625
/b/ active site guests = 3362
SQLite quick_check = ok
Posts = 150715
PostCopies = 1491101
max_post = 375761
```

### Visible Log Pump

Follow-up on 2026-05-13: the external supervisor originally redirected child stdout/stderr only to `logs/bot_stdout_utf8.log`. That made the visible console show supervisor health messages but not the bot's delivery lines.

Current supervisor logging:

- `main.py` stdout/stderr is piped into `bot_watchdog.py`
- a daemon pump thread writes every child line to the visible console and `logs/bot_stdout_utf8.log`
- `logs/bot_supervisor.log` remains supervisor-only
- watchdog liveness now checks fresh `logs/bot_heartbeat.json` before probing HTTP health

Current verified chain:

```text
start window cmd.exe = 9380
supervisor shim/processes = 69104 -> 29660
main.py shim/processes = 59488 -> 7972
bot.lock = 7972
heartbeat queues_total = 0
bot health = HTTP 200 status ok
port 8080 sockets = Listen 1, TimeWait 1, CloseWait 0
/b/ active Telegram users = 625
/b/ active site guests = 3362
```

The bot also has an in-process stall dump thread. If the event-loop heartbeat stops for `30s`, it writes all Python thread stacks to `logs/bot_deadlock_watchdog.log`. This is forensic evidence only; the external supervisor is still the recovery boundary.

### Raw Health Responder

Follow-up on 2026-05-14: `ThreadingHTTPServer` was still not reliable enough. A live process accepted TCP connections on `8080`, but `/health` sometimes timed out while heartbeat and delivery were alive.

Current health server:

- `main.py` uses `_RawHealthcheckServer`
- it is a tiny socket responder thread, not `BaseHTTPRequestHandler`
- response body is still the same JSON: `status`, `pid`, `loop_lag_sec`, `stale_after_sec`, `queues_total`, `queues_top`, `post_counter`
- watchdog still prefers fresh `logs/bot_heartbeat.json` before HTTP probing

Current verified chain:

```text
start window cmd.exe = 59928
supervisor shim/processes = 47372 -> 42924
main.py shim/processes = 10272 -> 2564
health = 5/5 HTTP 200 status ok
raw socket health = 5/5 HTTP/1.0 200 OK
heartbeat queues_total = 0
anime_media.b_max_stacked_images = 10
```

### Stall Threshold And Telemetry Cache

Follow-up on 2026-05-14: a later dump showed the event loop blocked inside runtime telemetry while reading DB/WAL file sizes with `os.path.getsize()`. That is now moved behind a cached snapshot:

- `_read_db_file_snapshot_uncached()` performs the blocking filesystem reads
- `_refresh_db_file_snapshot_cache()` runs it through the warmed executor with a `1.5s` timeout
- `_collect_runtime_snapshot()` reads the cached DB-size values and includes `updated_at`, `age_sec`, and `stale`

Health/stall defaults are now less noisy:

- `BOT_EVENT_LOOP_HEALTH_STALE_SEC=45`
- `BOT_EVENT_LOOP_DUMP_STALE_SEC=45`
- `BOT_WATCHDOG_HEARTBEAT_STALE_SEC=45`

Reason: Telegram/aiohttp can produce recoverable SSL stalls around `35s`; they are worth logging, but they are not the same as a multi-minute deadlock.

### Delivery Phase Budgets

Follow-up on 2026-05-14: split fanout now has wall-clock guardrails for priority and passive delivery phases.

- Priority recipients still go first.
- Passive recipients are still delivered in slices.
- `BOT_PRIORITY_PHASE_BUDGET_SEC=45` limits one priority call.
- `BOT_PASSIVE_PHASE_BUDGET_SEC=25` limits one passive/passive_slice call.
- If a call exceeds budget, `send_message_to_users()` returns a `DeliveryResults` object with `remaining_recipients`.
- `message_worker()` merges those remaining recipients back into the passive deferred set and requeues them through the existing board queue.
- Delivery metrics include `budget_deferred`, `interrupted_reason`, and `phase_budget_sec`.

This does not reduce the target fanout. It prevents one Telegram-side stall from monopolizing the board worker.

Single-media passive deliveries use the same lower media slice budget as albums:

- `photo`
- `video`
- `animation`
- `document`
- `audio`
- `voice`
- `sticker`
- `video_note`
- `media_group`

These content types use `BOT_PRIORITY_PASSIVE_MEDIA_SLICE_SIZE` instead of the larger text slice. The full fanout count is preserved; only passive phase size changes.

Passive preemption has one fairness guard: a passive item is only pushed behind newer full posts when its remaining recipient set is larger than the current slice size. Final one-slice tails are allowed to finish. This keeps priority delivery responsive without making old posts orbit the queue for a tiny final tail.

Adaptive passive pressure sizing:

- `BOT_PRIORITY_PRESSURE_SLICE_AGE_SEC`, default `600`
- `BOT_PRIORITY_PRESSURE_PASSIVE_SLICE_SIZE`, default `60`
- `BOT_PRIORITY_PRESSURE_PASSIVE_MEDIA_SLICE_SIZE`, default `25`

When a board queue's oldest item is older than the pressure age, passive fanout uses the lower pressure slice size. This does not reduce recipients; it reduces the wall-clock risk of one passive phase under Telegram/network pressure.

### Album State Keys

Telegram album assembly is process-local until the album timer fires. Internal album maps use `chat_id:media_group_id` as the key:

- `sent_media_groups`
- `current_media_groups`
- `media_group_timers`

Reason: the raw Telegram `media_group_id` is not a sufficient process-wide key when multiple chats/boards are active. Namespacing by chat prevents duplicate suppression, timer cancellation, or assembly state from crossing chats. This changes only internal bookkeeping; album order, caption handling, Telegram chunk size, and media type support are unchanged.

## Native Media Startup Warmup

The bot imports Pillow and numpy at process start because several hot paths need them:

- image resize before Telegram upload
- `/wipe` image generation
- anime/media command post-processing
- graph/stat image generation

`main.py` now calls `warm_native_media_stack()` during startup, after executor warmup and before DB/bot initialization. The probe initializes Pillow plugins, opens a tiny PNG, touches `numpy.asarray`, and touches `numpy.random`.

Reason: previous crash/stall evidence showed lazy Pillow plugin import and numpy random import inside worker threads during live operation. This warmup does not change media command semantics; it only moves native initialization cost and loader risk into the visible startup phase.

### Health Client Isolation

The raw health listener now accepts sockets in one thread and handles each client in a short-lived daemon thread. The goal is blunt: a broken client, a slow read, or an unexpected serialization error must not kill the whole health path.

Failure markers:

- `healthcheck_client_failed`: one client handler failed and was closed.
- `healthcheck_dispatch_failed`: the listener accepted a socket but failed to start the handler.

The external watchdog still treats fresh heartbeat as stronger evidence than noisy HTTP health.

### Controlled Stop Drain

`bot.stop` is now a controlled-stop request, not just a force-kill marker for the batch wrapper.

Runtime behavior:

- `controlled_stop_watcher_task()` detects `bot.stop`.
- polling is stopped first, so new Telegram updates stop entering handlers.
- background delivery workers remain alive while `wait_for_delivery_queues_to_drain()` waits for RAM queues and `current_deliveries` to empty.
- `site_posts_broadcaster()` pauses while drain is requested, so website broadcast rows are not pulled out of SQLite during shutdown.
- after drain completes or times out, the normal shutdown path closes healthcheck, DB/WAL, sessions, and executors.

Operational knobs:

- `BOT_CONTROLLED_STOP_DRAIN_TIMEOUT_SEC`, default `900`
- `BOT_CONTROLLED_STOP_LOG_INTERVAL_SEC`, default `10`
- `BOT_STOP_WAIT_SEC` for `stop_bot.bat`, default `930`

If `stop_bot.bat` times out while waiting, it does not hard-kill by default. `stop_bot.bat /force` still performs the old immediate hard process-tree stop. Use that only when the child is genuinely stuck and queue loss is accepted.

### Durable Passive Delivery Queue

Follow-up on 2026-05-15: passive fanout tails can now be mirrored into SQLite before they are put back into the RAM board queue.

Table:

- `DeliveryQueue`
- pending passive item id, board id, post number, recipient list JSON, content JSON, phase, original recipient count, timestamps, attempt count

Runtime behavior:

- only `delivery_phase=passive` items are persisted
- thread deliveries are skipped
- items with inline keyboard objects are skipped
- items containing volatile bytes/InputFile payloads are skipped
- `PostCopies` remains the source of truth for already delivered recipients
- on startup, pending durable items are restored into RAM after subtracting recipients already present in `PostCopies`
- when a durable item finishes, its DB row is deleted

The design is intentionally conservative. It reduces restart loss for passive tails but it is not exactly-once delivery. A process crash after Telegram accepts a send and before `PostCopies` is written can still create a duplicate on restore. The chosen failure mode is possible duplicate over silent recipient loss.

Operational switch:

- `BOT_DURABLE_DELIVERY_QUEUE`, default `1`

Logs and admin surfaces:

- `delivery_durable_saved`
- `delivery_durable_deleted`
- `delivery_durable_restore`
- `/queues` shows DB pending durable items and restore/save/delete counters
