# Operations Runbook

Scope: `C:\Users\danat\Desktop\dvachbot`  
Date: 2026-05-12

## Safe Rules

- Do not delete `dvach_bot.db` or its WAL/SHM files.
- Do not run `VACUUM` while bot/site are live.
- Do not clean `PostCopies` manually unless you accept losing native Telegram replies.
- If copying the DB while WAL exists, copy all three files together:
  - `dvach_bot.db`
  - `dvach_bot.db-wal`
  - `dvach_bot.db-shm`
- Prefer readonly diagnostics first.

## Running Components

Bot:

```powershell
C:\Users\danat\Desktop\dvachbot\start_bot.bat
```

Site:

```powershell
C:\Users\danat\Desktop\dvachbot\start_site.bat
```

Stomchat:

```powershell
C:\Users\danat\Desktop\stomchat\start.bat
```

## Process Inspection

Find bot/site/stomchat processes:

```powershell
Get-CimInstance Win32_Process |
  Where-Object { $_.CommandLine -match 'dvachbot|stomchat|site_tgach|start_bot|start_site' } |
  Select-Object ProcessId,ParentProcessId,Name,CreationDate,CommandLine
```

Memory snapshot:

```powershell
Get-Process -Id <PID> |
  Select-Object Id,ProcessName,StartTime,
    @{Name='WS_MB';Expression={[math]::Round($_.WorkingSet64/1MB,1)}},
    @{Name='PM_MB';Expression={[math]::Round($_.PrivateMemorySize64/1MB,1)}},
    CPU,Path
```

Interpretation:

- Working set: memory currently resident in RAM.
- Private memory: memory committed by the process. This is often the better leak alarm.
- CPU is cumulative process CPU seconds, not current percentage.

## Readonly DB Diagnostics

Use readonly mode:

```powershell
@'
import sqlite3
from pathlib import Path
p = Path(r"C:\Users\danat\Desktop\dvachbot\dvach_bot.db")
con = sqlite3.connect(f"file:{p.as_posix()}?mode=ro", uri=True, timeout=10)
con.execute("PRAGMA query_only=ON")
for table in ["Posts", "PostCopies", "Users", "BroadcastQueue", "ChannelCopies"]:
    print(table, con.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
print("quick_check", con.execute("PRAGMA quick_check").fetchone()[0])
con.close()
'@ | python -
```

Copy coverage:

```sql
SELECT COUNT(DISTINCT post_num) FROM PostCopies;
SELECT MIN(post_num), MAX(post_num) FROM PostCopies;
```

Old reply risk:

```sql
SELECT p.post_num
FROM Posts p
WHERE p.board_id='b'
AND NOT EXISTS (SELECT 1 FROM PostCopies pc WHERE pc.post_num=p.post_num)
ORDER BY p.post_num DESC
LIMIT 50;
```

## Compile Check

Run after Python edits:

```powershell
cd C:\Users\danat\Desktop\dvachbot
python -m py_compile main.py common\database.py common\config.py
```

If this fails:

1. Read the exact first syntax/import error.
2. Fix only the changed chunk.
3. Re-run.
4. After 3 failed attempts on an external dependency, revert only your own broken chunk and mark blocked.

## Restart Bot Safely

Use this only after compile passes.

1. Identify bot Python PID and parent `cmd.exe`.
2. Stop the Python child.
3. Let `start_bot.bat` watchdog restart it, or restart the batch manually if the parent was closed.

Example:

```powershell
Get-CimInstance Win32_Process |
  Where-Object { $_.CommandLine -match 'C:\\Users\\danat\\Desktop\\dvachbot\\start_bot.bat|python main.py' } |
  Select-Object ProcessId,ParentProcessId,Name,CommandLine
```

If parent watchdog is alive, stopping only `python main.py` is enough:

```powershell
Stop-Process -Id <python_pid> -Force
```

Then watch for a new Python PID:

```powershell
Start-Sleep -Seconds 8
Get-CimInstance Win32_Process |
  Where-Object { $_.CommandLine -match 'python main.py|start_bot.bat' } |
  Select-Object ProcessId,ParentProcessId,Name,CreationDate,CommandLine
```

## What To Watch After Restart

First 10 minutes:

- process starts cleanly
- no syntax/import errors in console
- memory does not jump into multi-GB immediately
- queue sizes are sane
- users can post
- replies to recent posts still native-reply
- replies to older posts at least quote correctly

Remember: replies to posts whose `PostCopies` were already deleted before this patch cannot be magically restored.

## Queue Lag Incident Procedure

Symptoms:

- users report 10-30 minute delivery delay
- CPU is saturated by unrelated local work
- bot process is alive but queue grows

Immediate actions:

1. Check current CPU pressure.
2. Check bot memory and whether process is swapping.
3. Check `/queues` from admin if available.
4. Check `logs/bot_runtime.log` for `delivery_priority`, `weekly_active_refresh`, and `delivery_result.post_age_sec`.
5. Check `delivery_result.queue_wait_sec` and `delivery_result.queue_total_sec`.
6. In `/queues`, check `Live age/current` to see the oldest RAM-queued post and current fanout.
7. In `/queues`, check `Reply copies` to confirm `PostCopies` still cover latest posts.
8. Avoid restarting during a huge unsent queue unless the queue state is persisted.
9. If queue is in RAM only, restart can drop pending fanout items.

Current mitigation:

- active weekly authors are sent first
- passive recipients are sent afterward
- if `BOT_PRIORITY_SPLIT_FANOUT=1`, active weekly users are delivered first and the passive tail is requeued
- passive tails are sliced by `BOT_PRIORITY_PASSIVE_SLICE_SIZE`, so new posts can run between passive slices instead of waiting behind one long passive fanout
- no recipient is intentionally dropped
- the priority list defaults to visible authors in the last 7 days
- completed fanouts log `post_age_sec`, which measures creation-to-completed-delivery lag
- completed fanouts log `queue_wait_sec`, which measures time spent waiting before delivery started
- completed fanouts log `queue_total_sec`, which measures time from RAM enqueue to delivery completion
- tune with `BOT_WEEKLY_ACTIVE_DAYS`, `BOT_WEEKLY_ACTIVE_REFRESH_SEC`, `BOT_PRIORITY_DELIVERY`, `BOT_PRIORITY_SPLIT_FANOUT`, `BOT_PRIORITY_SPLIT_MIN_PASSIVE`, and `BOT_PRIORITY_PASSIVE_SLICE_SIZE`

Current gap:

- persist per-post fanout progress to DB
- live RAM queue age is visible, but it is still process-local and disappears on restart
- split fanout is best-effort in one process; it reduces perceived lag but is not durable delivery state

## Memory Incident Procedure

Symptoms:

- private memory grows over hours/days
- bot reaches 2-3 GB and crashes
- Windows starts paging heavily

Diagnostics:

```powershell
Get-Process -Id <pid> |
  Select-Object Id,ProcessName,
    @{Name='WS_MB';Expression={[math]::Round($_.WorkingSet64/1MB,1)}},
    @{Name='PM_MB';Expression={[math]::Round($_.PrivateMemorySize64/1MB,1)}},
    CPU
```

Inside bot, admin can try:

```text
/debug_memory
/queues
```

Durable telemetry:

```powershell
Get-Content .\logs\bot_runtime.log -Tail 20
```

The `runtime_snapshot` lines are JSON. Watch `memory.private_mb`, `queues.total`, `queues.oldest`, `queues.in_flight`, `maps.message_to_post`, `maps.shadow_fake_post_counters`, `maps.pending_edit_tasks`, `maps.current_media_groups`, `maps.user_last_thread_action`, `maps.reaction_ratelimit`, `maps.last_poll_creation_time`, `maps.last_poll_vote_time`, `maps.user_hourly_image_count`, `maps.author_reaction_notify_tracker`, and `db_files.wal_mb`.
`delivery_result` lines are JSON too. They show completed fanout duration, `post_age_sec`, `queue_wait_sec`, `queue_total_sec`, recipients, priority/passive split, retries, blocks, and errors.
`reply_coverage` lines show native Telegram reply coverage. Watch `copy_posts`, `min_post`, `max_post`, `gap_from_latest`, and `top_boards`.

Memory knobs:

```text
BOT_POST_CACHE_LIMIT=3300
BOT_COPY_CACHE_POST_LIMIT=400
```

Do not raise `BOT_COPY_CACHE_POST_LIMIT` casually. It multiplies by active recipients and becomes hundreds of thousands of Python dict entries quickly. Older replies still resolve through indexed SQLite `PostCopies`.

Mode CPU knob:

```text
BOT_MODE_PUNCHUP_ENABLED=1
BOT_MODE_PUNCHUP_QUEUE_SHED_SEC=8
BOT_MODE_PUNCHUP_SLOW_LOG_US=2500
```

Set `BOT_MODE_PUNCHUP_ENABLED=0` during CPU/lag incidents to disable only the shared mode punch-up layer. Base mode transforms stay active. Runtime snapshots expose this as `mode_punchup.enabled`.

Current punch-up density: each supported text mode has `55` replacement triggers, `6` prefixes, `6` suffixes, `7` short injections, and `6` signature punchlines. The signature layer is cheap, but it is still part of the message hot path; if queue age rises, prefer `/punchup off` before touching delivery or DB state.

Live admin control:

```text
/punchup
/punchup status
/punchup off
/punchup on
/punchup reset
```

`/punchup off` disables only the extra shared `mode_punchup.py` layer until restart or `/punchup on`. Queue load shedding also skips only that extra layer when board queue/in-flight age crosses `BOT_MODE_PUNCHUP_QUEUE_SHED_SEC`.

Site memory knobs:

```text
SITE_CACHE_CLEANUP_INTERVAL_SEC=300
SITE_FASTAPI_CACHE_MAX_KEYS=5000
SITE_THREAD_VERSION_TTL_SEC=86400
SITE_THREAD_VERSION_MAX_KEYS=5000
SITE_FLOOD_TRACKER_TTL_SEC=60
SITE_SECURITY_MAP_MAX_KEYS=10000
```

Site admin runtime now exposes FastAPI cache size plus request/security-map cardinalities. Watch `runtime.fastapi_cache`, `runtime.request_flood_tracker`, `runtime.known_ips`, `runtime.bot_violations`, `runtime.ip_bans`, and `runtime.ip_troll_configs`.

Known good sample after 2026-05-12 restart:

```text
private_mb ~= 552
messages_storage ~= 3300
message_to_post ~= 631k
queues.total = 0
```

Known sample after reducing hot copy cache to 400 and storing single-message copies as integers:

```text
active bot child PID = 20448
private_mb ~= 486
messages_storage ~= 3300
post_to_messages ~= 368
message_to_post ~= 212k
queues.total = 0
```

Known sample after adding small-map telemetry and filtering site guest IDs before worker in-flight metrics:

```text
active bot child PID = 51640
private_mb ~= 551
messages_storage ~= 3300
post_to_messages ~= 666
message_to_post ~= 409k
small cooldown/rate maps = 0
queues.total = 0
```

Known priority-delivery sample after the later restart:

```text
active bot child PID = 11260
private_mb ~= 579
delivery_priority.enabled = true
weekly_active total = 138
/b/ weekly active = 98
```

Known post-age telemetry sample after the shadow/queue diagnostics restart:

```text
active bot child PID = 18352
private_mb ~= 584
delivery_result #375250: seconds=9.073, post_age_sec=22.602
DB quick_check = ok
```

Known sample after memory-guard restart:

```text
active bot child PID = 66240
private_mb ~= 589.73
message_to_post ~= 623452
queues.total = 0
delivery_result #375273: seconds=7.235, post_age_sec=7.513
DB quick_check = ok
```

Known sample after live-queue-age restart:

```text
active bot child PID = 56092
private_mb ~= 609.49
runtime_snapshot queues.in_flight.b = #375314 run=9.6s age=9.6s
delivery_result #375310: queue_wait_sec=10.395, queue_total_sec=18.515
delivery_result #375311: queue_wait_sec=18.585, queue_total_sec=26.168
DB quick_check = ok
```

Known sample after priority split-fanout restart:

```text
active bot child PID = 72112
private_mb ~= 484.66
delivery_priority.split_fanout = true
delivery_priority.split_min_passive = 30
delivery_priority.passive_slice_size = 120
queues.total = 0
message_to_post ~= 210213
DB quick_check = ok
```

Known sample after reply-coverage restart:

```text
active bot child PID = 17352
private_mb ~= 589.08
reply_coverage total_copies = 1231051
reply_coverage copy_posts = 1889
reply_coverage span = 373298..375320
reply_coverage gap_from_latest = 0
/b/ copy_posts = 1660
DB quick_check = ok
```

Known site memory sample after admin-runtime-stats restart:

```text
site uvicorn PID = 68716
root HTTP status = 200
private_mb ~= 604.7 after startup
previous sampled site private_mb ~= 1132.68 before restart
admin stats now include process/runtime containers
```

Known orphan-worker cleanup sample:

```text
orphan PIDs = 37776, 38024
dead parent PID = 1168
private memory reclaimed ~= 983 MiB
site image processing = ThreadPoolExecutor, not ProcessPoolExecutor
site PID after restart = 38420
root HTTP status = 200
spawn_main worker children = none
```

Known bot nested-map telemetry sample:

```text
active bot child PID = 32160
private_mb ~= 553.23
queues.total = 0
board_maps.image_spam_items = 0
board_maps.thread_locks = 0
/b/ #375378 seconds = 9.759
DB quick_check = ok
```

Known stomchat telemetry sample:

```text
stomchat watchdog PID = 10676
stomchat python PID = 26736
private_mb ~= 413.64 after restart
bot.log.1 = old 18.84 MB log
bot.log = new rotating log
runtime_memory pid=26736 rss_mb=211.73 private_mb=412.88
stomat_bot.db quick_check = ok
stomat_archive.db quick_check = ok
stomat_wiki.db quick_check = ok
```

Likely suspects:

- unbounded `message_queues`
- unfinished tasks in `pending_edit_tasks`
- missed media group cleanup
- orphan old-reply reverse cache entries in `message_to_post`; fixed cleaner prunes entries outside the hot post/copy window
- `ROULETTE_EVENTS` only if the JSON config becomes huge; it is not expected to grow at runtime
- site in-memory cache/cardinality
- orphan `multiprocessing.spawn` children from old site image-processing process pools; cleaned once and source removed
- large PIL/image buffers during media commands
- SQLite cache in both bot and site
- stomchat OpenCV/Groq/Telethon process growth; now track with `runtime_memory` in `C:\Users\danat\Desktop\stomchat\bot.log`

Garbage collection note:

- Calling `gc.collect()` more often is not a real fix for retained references.
- If a dict/list/global still references objects, GC cannot free them.
- The correct fix is bounding containers and deleting completed task/media state.

Memory restart guard:

- `memory_restarter()` now checks `max(RSS, private/USS)`.
- On Windows, private memory is often the better "will this process hit the wall?" number than working set alone.
- The limit is still `MEMORY_LIMIT_GB = 3.2` in `main.py`.

## Backup

Manual admin backup exists via admin UI button (`save_all`) and calls `wal_checkpoint(PASSIVE)` before git backup.

Filesystem backup rule:

```powershell
Copy-Item dvach_bot.db     backup\dvach_bot.db
Copy-Item dvach_bot.db-wal backup\dvach_bot.db-wal
Copy-Item dvach_bot.db-shm backup\dvach_bot.db-shm
```

Do not copy only `dvach_bot.db` while WAL exists and expect a complete hot backup.

## Runtime Log

Current state: the bot now writes operational telemetry to `logs/bot_runtime.log`.

Implemented:

- Python `logging` with rotating file handler
- UTF-8 output
- queue and memory structured snapshots
- completed fanout `delivery_result` entries
- background task exception snapshots
- emergency memory-limit snapshot before shutdown

File:

```text
logs/bot_runtime.log
```

Watchdog stdout/stderr:

- `start_bot.bat` now runs `python -X utf8 -u main.py` with `PYTHONUTF8=1` and `PYTHONIOENCODING=utf-8`.
- Early import/startup stdout and stderr are appended to `logs/bot_stdout_utf8.log`.
- The older mixed-encoding file was preserved as `logs/bot_stdout_legacy_mixed_20260513.log`.
- This catches failures that happen before `logs/bot_runtime.log` is initialized without letting a PowerShell pipe encoding path crash the bot.

Still missing: per-reply fallback reason logging.

## Stomchat Ops

Process chain:

```text
cmd.exe start.bat -> python main.py
```

Safe restart pattern:

```powershell
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'stomchat.*main.py|stomchat\\start.bat' }
Stop-Process -Id <python-main-pid> -Force
```

Leave `start.bat` running so the watchdog restarts the bot.

Logs:

- `bot.log` is now rotating.
- `bot.log.1` may contain the old large pre-rotation file.
- Search for `runtime_memory` to see process memory trend.

## Bot Recipient Truth And `/b/` Lag

Do not read `weekly_active` or one delivery phase as the full recipient count.

Current truth fields:

- `recipients.telegram_active_by_board.b` is the real active Telegram recipient count for `/b/`.
- `delivery_result.phase_recipients` is the number sent in the current phase only.
- `delivery_result.original_recipients` is the full logical fanout size for that post.
- `delivery_result.deferred_recipients` is the unsent passive tail requeued after the current phase.

Incident sample from 2026-05-13:

```text
/b/ DB active Telegram users = 625
/b/ DB banned Telegram users = 1
/b/ site guests = 3359
weekly active /b/ priority recipients = about 97
example delivery = 91 + 120 + 120 + 120 + 120 + 53 = 624
```

The `91/91` console line means priority phase only. It does not mean `/b/` lost the other users.

The bad `/b/` behavior observed around `2026-05-13 12:59-13:02` was queue starvation, not user deletion. Runtime evidence showed `/b/` passive queue waits above 100 seconds while smaller boards could still complete. This is consistent with one board worker draining a passive tail and media posts.

Mitigation now active:

- `BOT_PRIORITY_PASSIVE_MEDIA_SLICE_SIZE=40` by default
- `BOT_PASSIVE_MAX_PREEMPTIONS=3` by default
- `BOT_DELIVERY_SLOW_PHASE_SEC=10` by default
- `BOT_B_MAX_STACKED_ANIME_IMAGES=10` by default
- `BOT_ANIME_MEDIA_CONCURRENCY=1` by default

Current live verification sample:

```text
bot child PID = 31484
healthcheck HTTP 200
runtime recipients.telegram_active_by_board.b = 625
delivery_priority.passive_media_slice_size = 40
delivery_priority.passive_max_preemptions = 3
anime_media.concurrency = 1
anime_media.b_max_stacked_images = 10
mode_punchup.runtime_enabled = true
mode_punchup.queue_shed_sec = 8.0
SQLite quick_check = ok
```

Known caveat: queued fanout is still process-local RAM. A durable fanout job table is still the correct end-state.

## 2026-05-13 Hidden Watchdog / Media Stall Recovery

Observed failure:

- watchdog process was alive but started as a hidden window
- `bot.lock` pointed to live child PID `31484`, so a second bot window could not start
- healthcheck port `8080` was still listening, but HTTP requests timed out
- `logs/bot_runtime.log` stopped at `2026-05-13 16:50:53`
- `logs/bot_stdout_utf8.log` stopped after external anime/media URL searches on `/sex/`
- process had many TCP `CloseWait` sockets and did not respond as a working bot

Recovery performed:

```text
stopped hidden chain: 60964 -> 36596 -> 31484
removed stale bot.lock
started visible watchdog: cmd /k start_bot.bat
first visible chain: 68260 -> 30504 -> 38448
final visible chain after backlog-drained restart: 69912 -> 2584 -> 32956
healthcheck: HTTP 200
```

Manual stop script:

```text
stop_bot.bat
```

This reads `bot.lock`, finds the owning `start_bot.bat` watchdog chain, stops that process tree, and removes `bot.lock`. Use it when Ctrl+C is unavailable or the window is hidden.

New media guardrails:

- `BOT_ANIME_URL_FETCH_TIMEOUT_SEC=12`
- `BOT_ANIME_URL_FETCH_TOTAL_SEC=35`
- `BOT_ANIME_URL_FETCH_PARALLEL=3`
- `BOT_ANIME_DOWNLOAD_TIMEOUT_SEC=35`
- `BOT_ANIME_DOWNLOAD_TOTAL_SEC=45`
- `BOT_ANIME_DOWNLOAD_PARALLEL=2`
- `BOT_ANIME_API_SESSION_TIMEOUT_SEC=25`
- `BOT_ANIME_SINGLE_API_TIMEOUT_SEC=8`

The bot now wraps stacked anime/media URL fetches and downloads with hard `asyncio.wait_for()` limits. A bad external image API should fail the media command instead of holding the event loop and healthcheck indefinitely.

Follow-up hardening after the repeated live-but-stalled process:

- healthcheck now runs on `ThreadingHTTPServer`, not on the main asyncio loop
- healthcheck response is JSON with `status`, `pid`, `loop_lag_sec`, `stale_after_sec`, `queues_total`, `queues_top`, and `post_counter`
- if the event loop stops ticking for more than `BOT_EVENT_LOOP_HEALTH_STALE_SEC=20`, healthcheck returns `503` with `status=stale` instead of hanging
- delivery now has a per-recipient watchdog: `BOT_DELIVERY_PER_RECIPIENT_TIMEOUT_SEC=20`
- every Telegram send in the fanout path also receives a lower aiogram `request_timeout` cap, so aiohttp cannot sit under only the outer watchdog
- one recipient can be retried at most `BOT_DELIVERY_MAX_RECIPIENT_RETRIES=5` times inside one delivery phase
- `delivery_result` includes `timeouts`
- `delivery_recipient_timeout` and `delivery_recipient_retry_exhausted` are written to `logs/bot_runtime.log`
- bad photo/video/document URLs rejected by Telegram as web content fall back to a text delivery with the original link; this logs `delivery_media_url_text_fallback`

Latest live verification after the follow-up:

```text
visible watchdog chain = 40020 -> 18380 -> 54740
bot.lock = 54740
healthcheck = HTTP 200 JSON
healthcheck sample = {"status":"ok","pid":54740,"loop_lag_sec":0.931,"queues_total":0,"post_counter":375684}
runtime PID = 54740
runtime private_mb = 494.8
runtime delivery_priority.delivery_per_recipient_timeout_sec = 20.0
runtime delivery_priority.delivery_max_recipient_retries = 5
runtime queues.total = 0
/b/ active Telegram users = 625
/b/ active site guests = 3361
SQLite quick_check = ok
Posts = 150638
PostCopies = 1444259
```

Logging correction:

- startup board counts now print `tg_active`, `site_active`, and `active_total` separately
- `/b/ active_total` includes negative site guest IDs; it is not the Telegram fanout count
- current verified `/b/ Telegram active count remains `625`

FloodWait note:

- during catch-up after the stall, `/b/` was live but passive tails showed high queue age because the process had been down and Telegram returned retry/flood waits
- active priority phases continued to complete for new posts
- source is compiled with `BOT_DELIVERY_INITIAL_CHUNK_SIZE=12` and `BOT_DELIVERY_MIN_CHUNK_SIZE=3` to reduce future burst pressure, but do not restart only for this while a RAM queue backlog is still draining

## 2026-05-13 Follow-Up: External Supervisor After Second Live Stall

Correction to the previous section: moving healthcheck to `ThreadingHTTPServer` was not enough by itself. The later process still reached a live-but-unusable state where the PID existed and owned resources, but healthcheck from outside timed out. Treat the old `40020 -> 18380 -> 54740` verification as superseded.

Current control path:

```text
start_bot.bat -> bot_watchdog.py -> main.py
stop_bot.bat stops the whole owning tree from bot.lock
child stdout/stderr -> logs/bot_stdout_utf8.log
supervisor decisions -> logs/bot_supervisor.log
```

Supervisor behavior:

- probes `http://127.0.0.1:8080` from outside `main.py`
- waits `BOT_WATCHDOG_WARMUP_SEC=75` before judging startup health
- restarts after `BOT_WATCHDOG_HEALTH_FAIL_LIMIT=3` failed probes when logs are stale or health returns `status=stale`
- kills only the supervised bot child tree, not the site or other Python services

Latest verification:

```text
visible window cmd.exe = 58728
supervisor chain = 43256 -> 23944
main.py chain = 69868 -> 46488
bot.lock = 46488
health samples = 3/3 HTTP 200, status ok
loop_lag_sec ~= 0.49..0.74
queues.total = 0
post_counter = 375693
private_mb ~= 514.08
SQLite quick_check = ok
Posts = 150649
PostCopies = 1449384
max_post = 375695
/b/ active Telegram users = 625
/b/ active site guests = 3361
/b/ banned Telegram users = 1
```

Interpretation:

- `/b/` users were not deleted.
- `active_total=3987` includes negative site guest IDs; Telegram fanout is `625` active users at the latest DB check.
- Delivery lines like `89/624 phase` mean priority phase out of the full Telegram fanout, not lost recipients.
- The unresolved architectural risk is still RAM-local fanout. A hard kill while `queues.total > 0` can lose queued passive phases. Durable fanout jobs remain the required permanent fix.

## 2026-05-13 Follow-Up: Health Truth, Heartbeat, And Image Command Guardrails

The external supervisor found another real edge: HTTP health can fail while the bot is still delivering `/b/` phases. The supervisor now has a second truth source written by the bot event loop:

- `logs/bot_heartbeat.json`
- updated every ~2 seconds by `event_loop_health_tick_task`
- fields: `ts`, `pid`, `queues_total`, `queues_top`, `post_counter`, `is_shutting_down`
- supervisor knob: `BOT_WATCHDOG_HEARTBEAT_STALE_SEC=15`
- supervisor reads heartbeat before using stale runtime snapshots for queue safety

Health server hardening:

- `ThreadingHTTPServer.daemon_threads = True`
- `request_queue_size = 64`
- per-request socket timeout = `2s`
- HTTP response includes `Connection: close`

Image command guardrails:

- booru queries now include a shared safety negative-tag list for minor-coded/problem tags
- legacy `/loli` command remains accepted for compatibility; the temporary safe cute/chibi alias was reverted. It now uses the loli-tag source mix with non-explicit ratings and no-shota negative tags.
- URL fetch logs no longer print full tag-heavy media URLs; they log source, host, extension, and SHA-12
- download error logs no longer print full URL; they log host, extension, and SHA-12

Latest verification:

```text
visible window cmd.exe = 36128
supervisor chain = 35556 -> 32376
main.py chain = 71836 -> 3456
bot.lock = 3456
health samples = 3/3 HTTP 200, status ok
heartbeat = {"pid":3456,"queues_total":0,"post_counter":375761,"is_shutting_down":false}
runtime private_mb = 497.11
runtime queues.total = 0
site http://127.0.0.1:8000/ = 200
SQLite quick_check = ok
Posts = 150715
PostCopies = 1491101
max_post = 375761
/b/ active Telegram users = 625
/b/ active site guests = 3362
/b/ banned Telegram users = 1
image probe /loli = URL ok
image probe random_anime = URL ok
image probe nsfw_anime = URL ok
```

## 2026-05-13 Follow-Up: Visible Operator Logs Restored

The first external supervisor captured child stdout/stderr only into `logs/bot_stdout_utf8.log`. That preserved early crash evidence, but it made the visible `start_bot.bat` window show mostly supervisor health messages instead of live delivery lines. This was bad operator UX.

Current behavior:

- `bot_watchdog.py` launches `main.py` with `stdout=PIPE`
- a watchdog log-pump thread writes each child line to both the visible console and `logs/bot_stdout_utf8.log`
- supervisor decisions still go to `logs/bot_supervisor.log`
- `logs/bot_heartbeat.json` remains the watchdog's primary liveness source
- HTTP health is now only a fallback when heartbeat is stale/missing, so the watchdog no longer hammers a weak HTTP endpoint while heartbeat is fresh

Latest verification:

```text
compile = ok
visible window cmd.exe = 9380
supervisor chain = 69104 -> 29660
main.py chain = 59488 -> 7972
bot.lock = 7972
heartbeat pid = 7972
heartbeat queues_total = 0
heartbeat post_counter = 375809
bot health = HTTP 200 status ok
health loop_lag_sec = 0.561
port 8080 sockets = Listen 1, TimeWait 1, CloseWait 0
site http://127.0.0.1:8000/ = 200
/b/ tg_active = 625
/b/ site_active = 3362
/b/ banned = 1
deadlock dump file = not created yet because no 30s event-loop stall after restart
```

Operator rule:

- Watch the visible `start_bot.bat` window for live startup and delivery logs.
- Use `logs/bot_stdout_utf8.log` as the persistent copy of that same bot output.
- Use `logs/bot_supervisor.log` only for watchdog decisions.
- Use `stop_bot.bat` for controlled shutdown.

Additional deadlock forensics:

- `main.py` now starts an event-loop stall watchdog thread.
- If `event_loop_health_tick_task` stops ticking for `BOT_EVENT_LOOP_DUMP_STALE_SEC=30`, the process writes all Python thread stacks to `logs/bot_deadlock_watchdog.log`.
- The dump cooldown is `BOT_EVENT_LOOP_DUMP_COOLDOWN_SEC=120`.
- If this file appears, inspect it before deleting it; it is the next hard evidence source for event-loop stalls.

## 2026-05-14 Operator Revert: Anime Scope And Raw Health

User-requested revert:

- `BOT_B_MAX_STACKED_ANIME_IMAGES` is back to default `10`.
- temporary `/loli` safe cute/chibi alias was reverted.
- `/loli` uses the loli-tag source mix with non-explicit ratings and no-shota negative tags.
- broad yande.re/konachan negative tag injection was removed.
- retained useful stability work: URL/download timeouts, bounded parallelism, redacted URL logging, heartbeat, and supervisor.

Healthcheck correction:

- `ThreadingHTTPServer` still produced a bad live shape: TCP accepted connections, but `/health` sometimes timed out while heartbeat and delivery were alive.
- `main.py` now uses `_RawHealthcheckServer`, a tiny socket responder thread returning the same JSON body.
- verified after restart: five `Invoke-WebRequest` samples returned `status=ok`; five raw socket samples returned `HTTP/1.0 200 OK` in `0.004..0.039s`.

Latest verification:

```text
visible chain = 59928 -> 47372 -> 42924 -> 10272 -> 2564
bot pid = 2564
health = {"status":"ok","pid":2564,"queues_total":0,"post_counter":375951}
heartbeat queues_total = 0
site 8000 = HTTP 200
SQLite quick_check = ok
/b/ active total = 3986
/b/ Telegram active in runtime = 623
sex active total = 616
Posts = 150905
PostCopies = 1614691
anime_media.b_max_stacked_images = 10
```

## 2026-05-14 Operator Revert Follow-Up: `/loli` Count Integrity

Additional correction:

- removed the unreachable old `/loli` `chibi` fallback block from `japanese_translator.py`;
- `/loli` runtime path is only the restored loli-tag source mix plus non-explicit/no-shota negatives and generic fallback APIs;
- added bounded image refill: `BOT_ANIME_REFILL_ROUNDS=2` by default;
- if one requested image fails at URL fetch or download, the command retries the missing slot instead of silently sending fewer images after the first failed API;
- refill is bounded by existing URL/download total timeouts and logs `anime_media_refill` when it happens.

Current live verification after restart:

```text
bot.lock = 60036
health raw socket = 5/5 HTTP/1.0 200 OK, 0.028..0.161s
heartbeat = pid 60036, queues_total 0, post_counter 375977
runtime anime_media.refill_rounds = 2
runtime anime_media.b_max_stacked_images = 10
site 8000 = HTTP 200
SQLite quick_check = ok
/b/ tg_active = 623
/b/ site_active = 3362
/b/ active_total = 3986
/b/ banned = 1
/sex/ tg_active = 229
/sex/ site_active = 386
/sex/ active_total = 616
Posts = 150931
PostCopies = 1630474
```

Recipient count rule:

- `delivery_result.original_recipients` is Telegram fanout only.
- `/b/` current Telegram fanout is about `622-623`.
- `/b/ active_total=3986` includes site guest ids and is not expected to appear in Telegram delivery phase counts.
- A line like `87/87 phase (87/622, def 535)` means priority phase `87`, remaining Telegram recipients `535`; it does not mean users were deleted.

## 2026-05-14 Health Close Fix

The raw health server responded to simple socket probes, but HTTP/1.1 clients such as PowerShell `Invoke-WebRequest` and Python `urllib` could wait for connection close. The response now uses `HTTP/1.1`, `Connection: close`, and an explicit `socket.shutdown()` after `sendall()`.

Current verification:

```text
visible chain = 43556 -> 10196 -> 66836 -> 32288
bot.lock = 32288
PowerShell Invoke-WebRequest /health = HTTP 200
Python urllib /health = 3/3 HTTP 200, 0.002..0.114s
raw socket HTTP/1.1 keep-alive request = 3/3 HTTP 200, 0.006..0.021s
heartbeat = pid 32288, queues_total 0, post_counter 375978
runtime private_mb ~= 507-512
runtime anime_media.refill_rounds = 2
runtime anime_media.b_max_stacked_images = 10
SQLite quick_check = ok
/b/ tg_active = 623
/b/ site_active = 3362
/b/ active_total = 3986
/sex/ active_total = 616
Posts = 150932
PostCopies = 1631097
```

Log encoding note:

- `logs/bot_stdout_utf8.log` after `2026-05-14 05:02:01` reads back as valid UTF-8 through Python.
- If PowerShell displays mojibake, use `Get-Content -Encoding UTF8` or inspect with Python; the persisted file is not currently corrupted.

## 2026-05-14 Health/Stall Interpretation Update

The visible console is expected to show child delivery lines because `bot_watchdog.py` tees child stdout to both the window and `logs/bot_stdout_utf8.log`. `logs/bot_supervisor.log` remains supervisor-only.

Current liveness defaults:

- `BOT_EVENT_LOOP_HEALTH_STALE_SEC=45`
- `BOT_EVENT_LOOP_DUMP_STALE_SEC=45`
- `BOT_WATCHDOG_HEARTBEAT_STALE_SEC=45`

Why: fresh dumps showed recoverable Telegram/aiohttp SSL stalls around `35s`. Treating those as `20s` health failures created scary but non-actionable logs. A real multi-minute deadlock is still caught by stale heartbeat plus repeated watchdog failures.

Recipient-count reading:

- `/b/ startup active_total` includes Telegram users plus site guests.
- `/b/ delivery original_recipients` is Telegram fanout only.
- Current verified `/b/ shape: `tg_active=623`, `site_active=3364`, `active_total=3988`, live delivery around `84/622 priority` and `120/622 passive_slice`.

Current health verification after restart:

```text
bot.lock = 4264
PowerShell /health = HTTP 200
health stale_after_sec = 45.0
queues_total = 0
```

## 2026-05-14 Passive Budget / Health Isolation

Delivery guardrail:

- `BOT_PRIORITY_PHASE_BUDGET_SEC=45` caps a single priority phase.
- `BOT_PASSIVE_PHASE_BUDGET_SEC=25` caps a single passive/passive_slice phase.
- If a phase hits the cap, remaining recipients are logged as `budget_deferred` and requeued through the normal board queue.
- This is not recipient loss. It is a brake against one Telegram/FloodWait stall blocking newer `/b/` work.

Read delivery logs like this:

- `original_recipients=623` is the full Telegram fanout for that post.
- `phase_recipients=120` is the current passive slice.
- `deferred_recipients=419` is the planned remaining fanout after this slice.
- `budget_deferred>0` means this phase was interrupted by the wall-clock budget and the unsent recipients were requeued.
- In `delivery_passive_deferred`, `requested_now` is attempted recipients for the phase and `sent_now` is actual delivered recipients.

Health guardrail:

- The raw health socket listener now isolates each client in its own short-lived daemon thread.

## 2026-05-15 Health / Visible Window Check

Use `curl.exe --max-time 5 -s http://127.0.0.1:8080/` for the fastest local health truth. PowerShell `Invoke-WebRequest` can occasionally hang on the client side even when the bot event-loop heartbeat and raw health endpoint are fresh.

Operational rule:

- Trust the JSON `pid` from health and `logs/bot_heartbeat.json`.
- `bot.lock` must match the active child pid.
- A visible `cmd.exe /k start_bot.bat` window should exist for the live bot.
- If `start_bot.bat` finds an already running hidden child, it exits without attaching to that stdout and prints the exact paths to `logs/bot_stdout_utf8.log`, `logs/bot_runtime.log`, and `logs/bot_heartbeat.json`.
- Do not kill unrelated `python -X utf8 -u main.py` processes unless `bot.lock`, health pid, or the process tree proves they are the live dvachbot child.
- `healthcheck_client_failed` means one probe failed.
- `healthcheck_dispatch_failed` means the listener could not start the client handler.
- A fresh `logs/bot_heartbeat.json` is still the primary proof that the event loop is alive if HTTP health is noisy.

## 2026-05-15 Native Media Warmup

Why it exists:

- Old crash/stall evidence showed live worker paths touching Pillow plugin import, `PIL.Image.open`, and `numpy.random` during image resize/wipe/media handling.
- On Windows, lazy native initialization during live traffic is a bad place to discover loader/SSL/proactor stalls.

Current behavior:

- Startup now runs `warm_native_media_stack()` after executor warmup and before DB/bot initialization.
- Expected visible line:

```text
✓ Native media stack warmed: pillow_plugins=<n> numpy_random=ok elapsed=<ms>ms
```

Operator notes:

- This is only startup warmup. It does not change anime source tags, `/loli`, ratings, request counts, or refill behavior.
- If startup ever prints `Native media warmup failed`, the bot can still continue, but image commands/resizers may again pay lazy import cost during live traffic.
- Check `logs/bot_fatal_crash.log` and `logs/bot_deadlock_watchdog.log` first if native crashes return.

Verified restart sample:

```text
bot.lock = 67256
visible bot chain = 5504 -> 49760 -> 62292 -> 62488 -> 67256
health = HTTP 200, queues_total=0
heartbeat = pid 67256, queues_total 0
startup warmup = pillow_plugins=43 numpy_random=ok elapsed=159.7ms
/b/ tg_active = 625
/b/ active_total = 3991
/b/ delivery #376744 = 89/624 priority + 120/624 passive slices + 55/55 final passive
runtime anime_media.b_max_stacked_images = 10
runtime anime_media.refill_rounds = 2
SQLite quick_check = ok
site /healthz = HTTP 200
```

## 2026-05-15 Passive Media Slices

Delivery slice rule:

- Text passive fanout uses `BOT_PRIORITY_PASSIVE_SLICE_SIZE`, default `90`.
- Media passive fanout uses `BOT_PRIORITY_PASSIVE_MEDIA_SLICE_SIZE`, default `40`.
- Media means `photo`, `video`, `animation`, `document`, `audio`, `voice`, `sticker`, `video_note`, and `media_group`.
- Under pressure, when the board queue oldest item exceeds `BOT_PRIORITY_PRESSURE_SLICE_AGE_SEC=600`, passive slices downshift to `BOT_PRIORITY_PRESSURE_PASSIVE_SLICE_SIZE=60` for text and `BOT_PRIORITY_PRESSURE_PASSIVE_MEDIA_SLICE_SIZE=25` for media.

Why:

- Telegram media sends are heavier than text sends.
- A live `/b/` video proved the old code was still using `120` for single `ContentType.VIDEO`, causing repeated timeout/retry phases and `phase_budget_guard`.
- Smaller media slices do not reduce recipients. They reduce the blast radius of one media/FloodWait stall.

How to read logs:

- `original_recipients` is still full Telegram fanout.
- `phase_recipients` for media passive phases should be around `40` after restart.
- Text passive phases should be around `90` after the text-slice downshift is deployed, or `60` under queue-age pressure. Older logs can still show `120`.
- Media passive phases should be around `40`, or `25` under queue-age pressure.
- Passive final tails that already fit in one slice should not log `delivery_passive_preempted`; they should complete as `phase=passive`.

## 2026-05-15 Album State Keys

Album assembly state is keyed by `chat_id:media_group_id`.

Operational meaning:

- Raw `media_group_id` alone is not treated as globally unique inside the bot process.
- `current_media_groups` and `media_group_timers` counts in runtime snapshots are still counts, not recipient counts.
- If a restart is needed while `current_media_groups>0`, the currently assembling album can still be lost because album assembly is RAM state.
- Do not restart only to deploy album bookkeeping changes while `/b/` has a non-zero RAM fanout queue.

## 2026-05-15 Controlled Stop Drain

Normal controlled stop:

```bat
stop_bot.bat
```

What should happen after the controlled-drain build is deployed:

- `stop_bot.bat` writes `bot.stop`.
- bot logs `controlled_stop_requested`.
- polling stops first.
- RAM delivery queues keep draining.
- runtime log emits `controlled_stop_drain_wait` until queues/in-flight are empty.
- bot exits cleanly, removes `bot.lock`, and the supervisor exits.

Force stop:

```bat
stop_bot.bat /force
```

Use `/force` only when the process is stuck and queued RAM fanout loss is acceptable.

Knobs:

- `BOT_CONTROLLED_STOP_DRAIN_TIMEOUT_SEC=900`
- `BOT_CONTROLLED_STOP_LOG_INTERVAL_SEC=10`
- `BOT_STOP_WAIT_SEC=930` for the batch wrapper wait

Important: a process started before this feature still does not know how to drain on `bot.stop`; for that old child, wait for `queues_total=0` before restart or accept that force stop can drop RAM passive tails.

If `stop_bot.bat` times out, it does not hard-kill by default. Run `stop_bot.bat /force` only after deciding that RAM queue loss is acceptable.

## 2026-05-15 Durable Passive Delivery

After the durable-delivery build is deployed, passive tails are mirrored in SQLite table `DeliveryQueue`.

What to expect:

- `/queues` shows `Durable delivery: enabled=True DB pending=<n> ...`
- runtime log emits `delivery_durable_saved` when a passive tail is persisted
- runtime log emits `delivery_durable_deleted` when that tail finishes
- startup emits `delivery_durable_restore` if pending DB rows are restored into RAM

Rules:

- This protects only safe passive fanout items.
- It intentionally skips thread items, inline keyboard objects, and volatile byte/InputFile payloads.
- `PostCopies` is used to subtract recipients who already received the post.
- This is not exact-once delivery after a hard crash. If Telegram accepted a message but the process died before saving `PostCopies`, restore can duplicate that recipient. This is still better than silently losing an entire passive tail.

Switch:

```text
BOT_DURABLE_DELIVERY_QUEUE=1
```

Set it to `0` only if durable restore itself is suspected. Existing pending rows remain in SQLite until a build with durable delivery enabled restores or clears them.

## 2026-05-15 Live Status And Log Tail

Use this when the bot is alive but the visible window is not showing delivery logs:

```bat
bot_live_status.bat
```

It prints:

- `bot.lock` pid and whether that pid exists
- `bot.stop` presence
- heartbeat pid, heartbeat age, RAM queue total/top
- HTTP health JSON
- last runtime snapshot queue/in-flight data
- live runtime slice knobs, including whether durable delivery is deployed in the current child
- SQLite `quick_check`, core table counts, and `DeliveryQueue` state
- exact paths for stdout/runtime/supervisor/heartbeat logs
- last delivery result lines

Tail logs directly:

```bat
tail_bot_logs.bat runtime
tail_bot_logs.bat stdout
tail_bot_logs.bat supervisor
tail_bot_logs.bat heartbeat
```

`runtime` is the main truth for `delivery_result`, `delivery_phase_budget_deferred`, `runtime_snapshot`, and future `delivery_durable_*` events. `stdout` is the visible console stream mirrored by the watchdog. These commands do not stop or restart the bot.

## 2026-05-15 Follow-Up: Visible Window, PID Truth, And UTF-8 Tail

Observed problem:

- a second manual `start_bot.bat` attempt can leave a useless `cmd /k` window after the child exits because another live `bot.lock` already exists
- older supervisor code treated normal child exit code `0` as restartable unless `bot.stop` was present
- `bot_live_status.py` could report a stale runtime snapshot from an old PID during startup, before the new child emitted its first `runtime_snapshot`
- `Get-Content` without `-Encoding UTF8` made `bot_stdout_utf8.log` look mojibake even though the file itself was valid UTF-8

Fixes:

- `bot_watchdog.py` now exits instead of restart-looping when the child exits with code `0`.
- Windows PID checks in `bot_watchdog.py` and `bot_live_status.py` now use `OpenProcess`, not slow `tasklist` parsing.
- `bot_live_status.py` prints `runtime pid ... matches lock` or `STALE/OLD PID`.
- `bot_live_status.py` prints `Users_active`, `Users_banned`, and `BroadcastQueue_unsent`; old sent broadcast rows no longer look like a live backlog.
- `tail_bot_logs.bat` tails with `-Encoding UTF8`.
- `start_bot.bat` remains the normal visible one-window launcher. Closing that window stops the bot tree. `stop_bot.bat` is only the controlled/fallback stop path.

Latest verification after controlled restart:

```text
visible cmd = 63324
supervisor chain = 61500 -> 37748
main.py chain = 58852 -> 19668
bot.lock = 19668
health = HTTP 200
heartbeat pid = 19668
runtime pid = 19668 matches lock
queues_total = 0
DeliveryQueue pending = 0
BroadcastQueue_unsent = 0
/b/ telegram_active = 625
contextual groups_ru = 92
stdout file UTF-8 = valid
```

Fresh warning note:

- `bot_supervisor.log` contains one `status=stale` line at `2026-05-15 21:35:07` during the controlled stop of the old child `47248`.
- The child then exited cleanly and the new child is healthy.
