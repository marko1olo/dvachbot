from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent
LOG_DIR = ROOT / "logs"
DB_PATH = ROOT / "dvach_bot.db"
LOCK_PATH = ROOT / "bot.lock"
STOP_PATH = ROOT / "bot.stop"
HEARTBEAT_PATH = LOG_DIR / "bot_heartbeat.json"
RUNTIME_LOG = LOG_DIR / "bot_runtime.log"
STDOUT_LOG = LOG_DIR / "bot_stdout_utf8.log"
SUPERVISOR_LOG = LOG_DIR / "bot_supervisor.log"
HEALTH_URL = "http://127.0.0.1:8080/"


def _read_json(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _read_pid(path: Path) -> int | None:
    try:
        text = path.read_text(encoding="utf-8").strip()
        return int(text) if text.isdigit() else None
    except Exception:
        return None


def _pid_exists(pid: int | None) -> bool:
    if not pid or pid <= 0:
        return False
    if sys.platform == "win32":
        try:
            import ctypes

            process_query_limited_information = 0x1000
            handle = ctypes.windll.kernel32.OpenProcess(
                process_query_limited_information,
                False,
                int(pid),
            )
            if handle:
                ctypes.windll.kernel32.CloseHandle(handle)
                return True
            return False
        except Exception:
            return False
    try:
        import os

        os.kill(pid, 0)
        return True
    except PermissionError:
        return True
    except OSError:
        return False


def _health() -> tuple[str, dict | str]:
    try:
        with urllib.request.urlopen(HEALTH_URL, timeout=3) as response:
            body = response.read(8192).decode("utf-8", errors="replace")
            try:
                return f"HTTP {getattr(response, 'status', 200)}", json.loads(body)
            except json.JSONDecodeError:
                return f"HTTP {getattr(response, 'status', 200)}", body[:300]
    except Exception as exc:
        return "ERROR", f"{type(exc).__name__}: {exc}"


def _read_tail(path: Path, max_bytes: int = 512 * 1024) -> str:
    try:
        size = path.stat().st_size
        with path.open("rb") as fh:
            if size > max_bytes:
                fh.seek(size - max_bytes)
            return fh.read().decode("utf-8", errors="replace")
    except OSError:
        return ""


def _latest_runtime_snapshot() -> dict:
    text = _read_tail(RUNTIME_LOG)
    for line in reversed(text.splitlines()):
        marker = "runtime_snapshot "
        if marker not in line:
            continue
        raw = line.split(marker, 1)[1].strip()
        try:
            payload = json.loads(raw)
            return payload if isinstance(payload, dict) else {}
        except json.JSONDecodeError:
            continue
    return {}


def _latest_delivery_lines(limit: int = 5) -> list[str]:
    text = _read_tail(RUNTIME_LOG)
    lines = [
        line
        for line in text.splitlines()
        if "delivery_result " in line or "delivery_phase_budget_deferred " in line
    ]
    return lines[-limit:]


def _db_counts() -> dict:
    if not DB_PATH.exists():
        return {"error": "db missing"}
    result: dict[str, object] = {}
    try:
        conn = sqlite3.connect(DB_PATH, timeout=5)
        cur = conn.cursor()
        result["quick_check"] = cur.execute("PRAGMA quick_check").fetchone()[0]
        ALLOWED_TABLES = {"Users", "Posts", "PostCopies", "BroadcastQueue"}
        for table in ("Users", "Posts", "PostCopies", "BroadcastQueue"):
            if table in ALLOWED_TABLES:
                # Use of an explicit allow-list mitigates the SQL Injection vulnerability
                # associated with string interpolation of table names.
                result[table] = cur.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        try:
            result["Users_active"] = cur.execute("SELECT COUNT(*) FROM Users WHERE status='active'").fetchone()[0]
            result["Users_banned"] = cur.execute("SELECT COUNT(*) FROM Users WHERE status='banned'").fetchone()[0]
        except sqlite3.OperationalError:
            pass
        try:
            result["BroadcastQueue_unsent"] = cur.execute(
                "SELECT COUNT(*) FROM BroadcastQueue WHERE COALESCE(is_sent_to_tg, 0)=0"
            ).fetchone()[0]
        except sqlite3.OperationalError:
            pass
        try:
            result["DeliveryQueue"] = cur.execute("SELECT COUNT(*) FROM DeliveryQueue WHERE status='pending'").fetchone()[0]
        except sqlite3.OperationalError:
            result["DeliveryQueue"] = "table_missing_until_new_build_starts"
        conn.close()
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


def _fmt_age(ts: object) -> str:
    try:
        return f"{max(0.0, time.time() - float(ts)):.1f}s"
    except Exception:
        return "?"


def _runtime_age_sec(runtime: dict) -> float | None:
    try:
        raw = runtime.get("utc")
        if not isinstance(raw, str) or not raw:
            return None
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds())
    except Exception:
        return None


def _fmt_runtime_age(runtime: dict) -> str:
    age = _runtime_age_sec(runtime)
    return "?" if age is None else f"{age:.1f}s"


def _runtime_pid(runtime: dict) -> int | None:
    try:
        memory = runtime.get("memory")
        if not isinstance(memory, dict):
            return None
        pid = memory.get("pid")
        return int(pid) if pid is not None else None
    except Exception:
        return None


def _print_json() -> None:
    health_status, health_payload = _health()
    runtime = _latest_runtime_snapshot()
    lock_pid = _read_pid(LOCK_PATH)
    runtime_pid = _runtime_pid(runtime)
    payload = {
        "lock_pid": lock_pid,
        "lock_pid_exists": _pid_exists(lock_pid),
        "bot_stop_exists": STOP_PATH.exists(),
        "heartbeat": _read_json(HEARTBEAT_PATH),
        "health_status": health_status,
        "health": health_payload,
        "runtime_pid": runtime_pid,
        "runtime_pid_matches_lock": bool(lock_pid and runtime_pid == lock_pid),
        "runtime_age_sec": _runtime_age_sec(runtime),
        "runtime": runtime,
        "db": _db_counts(),
        "logs": {
            "stdout": str(STDOUT_LOG),
            "runtime": str(RUNTIME_LOG),
            "supervisor": str(SUPERVISOR_LOG),
            "heartbeat": str(HEARTBEAT_PATH),
        },
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def main() -> int:
    if any(arg.lower() == "--json" for arg in sys.argv[1:]):
        _print_json()
        return 0

    heartbeat = _read_json(HEARTBEAT_PATH)
    health_status, health_payload = _health()
    runtime = _latest_runtime_snapshot()
    queues = runtime.get("queues", {}) if isinstance(runtime, dict) else {}
    delivery_priority = runtime.get("delivery_priority", {}) if isinstance(runtime, dict) else {}
    durable = runtime.get("durable_delivery", {}) if isinstance(runtime, dict) else {}
    db = _db_counts()
    lock_pid = _read_pid(LOCK_PATH)
    runtime_pid = _runtime_pid(runtime)
    runtime_match_note = "matches lock" if lock_pid and runtime_pid == lock_pid else "STALE/OLD PID"

    print("TGACH BOT LIVE STATUS")
    print("=" * 72)
    print(f"bot.stop: {'EXISTS' if STOP_PATH.exists() else 'absent'}")
    print(f"bot.lock pid: {lock_pid} exists={_pid_exists(lock_pid)}")
    print(
        "heartbeat: "
        f"pid={heartbeat.get('pid')} age={_fmt_age(heartbeat.get('ts'))} "
        f"queues={heartbeat.get('queues_total')} top={heartbeat.get('queues_top')}"
    )
    print(f"health: {health_status} {health_payload}")
    print(
        "runtime snapshot: "
        f"utc={runtime.get('utc')} age={_fmt_runtime_age(runtime)} "
        f"pid={runtime_pid} {runtime_match_note}"
    )
    print(
        "runtime queues: "
        f"total={queues.get('total')} top={queues.get('top')} "
        f"oldest={queues.get('oldest')} in_flight={queues.get('in_flight')}"
    )
    print(
        "priority config from live runtime: "
        f"slice={delivery_priority.get('passive_slice_size')}/"
        f"{delivery_priority.get('passive_media_slice_size')} "
        f"pressure={delivery_priority.get('pressure_slice_age_sec')}:"
        f"{delivery_priority.get('pressure_passive_slice_size')}/"
        f"{delivery_priority.get('pressure_passive_media_slice_size')}"
    )
    print(f"durable delivery from live runtime: {durable or 'not deployed in current child'}")
    print(f"db: {db}")
    print("-" * 72)
    print("truth logs:")
    print(f"  stdout:     {STDOUT_LOG}")
    print(f"  runtime:    {RUNTIME_LOG}")
    print(f"  supervisor: {SUPERVISOR_LOG}")
    print(f"  heartbeat:  {HEARTBEAT_PATH}")
    print("-" * 72)
    print("last delivery facts:")
    for line in _latest_delivery_lines():
        print(line[:1000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
