import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent
LOG_DIR = ROOT / "logs"
STDOUT_LOG = LOG_DIR / "bot_stdout_utf8.log"
SUPERVISOR_LOG = LOG_DIR / "bot_supervisor.log"
HEARTBEAT_LOG = LOG_DIR / "bot_heartbeat.json"
BOT_LOCK = ROOT / "bot.lock"
STOP_REQUEST = ROOT / "bot.stop"
HEALTH_URL = os.environ.get("BOT_HEALTH_URL", "http://127.0.0.1:8080")
HEALTH_TIMEOUT_SEC = float(os.environ.get("BOT_WATCHDOG_HEALTH_TIMEOUT_SEC", "5"))
HEALTH_FAIL_LIMIT = int(os.environ.get("BOT_WATCHDOG_HEALTH_FAIL_LIMIT", "3"))
FORCE_FAIL_LIMIT = int(os.environ.get("BOT_WATCHDOG_FORCE_FAIL_LIMIT", "12"))
SAFE_RESTART_QUEUE_LIMIT = int(
    os.environ.get("BOT_WATCHDOG_SAFE_RESTART_QUEUE_LIMIT", "0")
)
POLL_SEC = float(os.environ.get("BOT_WATCHDOG_POLL_SEC", "15"))
WARMUP_SEC = float(os.environ.get("BOT_WATCHDOG_WARMUP_SEC", "75"))
LOG_STALE_SEC = float(os.environ.get("BOT_WATCHDOG_LOG_STALE_SEC", "120"))
RESTART_DELAY_SEC = float(os.environ.get("BOT_WATCHDOG_RESTART_DELAY_SEC", "5"))
TAIL_READ_BYTES = int(os.environ.get("BOT_WATCHDOG_TAIL_READ_BYTES", "262144"))
HEARTBEAT_STALE_SEC = float(os.environ.get("BOT_WATCHDOG_HEARTBEAT_STALE_SEC", "45"))


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(message: str) -> None:
    LOG_DIR.mkdir(exist_ok=True)
    line = f"[{_now()}] {message}"
    print(line, flush=True)
    with SUPERVISOR_LOG.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def _file_age_sec(path: Path) -> float | None:
    try:
        return max(0.0, time.time() - path.stat().st_mtime)
    except OSError:
        return None


def _read_tail(path: Path, max_bytes: int = TAIL_READ_BYTES) -> str:
    try:
        size = path.stat().st_size
        with path.open("rb") as fh:
            if size > max_bytes:
                fh.seek(size - max_bytes)
            return fh.read().decode("utf-8", errors="replace")
    except OSError:
        return ""


def _read_heartbeat() -> dict | None:
    try:
        payload = json.loads(HEARTBEAT_LOG.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            return payload
    except Exception:
        return None
    return None


def _read_lock_pid() -> int | None:
    try:
        text = BOT_LOCK.read_text(encoding="utf-8").strip()
        if text.isdigit():
            return int(text)
    except OSError:
        return None
    return None


def _pid_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
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
        os.kill(pid, 0)
        return True
    except PermissionError:
        return True
    except OSError:
        return False


def _locked_live_bot_pid() -> int | None:
    lock_pid = _read_lock_pid()
    if lock_pid is None or not _pid_exists(lock_pid):
        return None
    heartbeat = _read_heartbeat()
    if heartbeat and int(heartbeat.get("pid") or 0) == lock_pid:
        return lock_pid
    return lock_pid


def _heartbeat_age_sec(payload: dict | None) -> float | None:
    if not payload:
        return None
    try:
        return max(0.0, time.time() - float(payload.get("ts", 0)))
    except Exception:
        return None


def _heartbeat_queue_total(payload: dict | None) -> int | None:
    if not payload:
        return None
    total = payload.get("queues_total")
    if isinstance(total, int):
        return total
    return None


def _heartbeat_is_fresh(payload: dict | None) -> bool:
    heartbeat_age = _heartbeat_age_sec(payload)
    return bool(
        payload
        and heartbeat_age is not None
        and heartbeat_age <= HEARTBEAT_STALE_SEC
        and not bool(payload.get("is_shutting_down"))
    )


def _extract_queue_total_from_log_text(text: str) -> int | None:
    latest: int | None = None
    for match in re.finditer(r"runtime_snapshot (\{.*\})", text):
        try:
            payload = json.loads(match.group(1))
            total = payload.get("queues", {}).get("total")
            if isinstance(total, int):
                latest = total
        except Exception:
            continue

    for match in re.finditer(r"\[runtime\].*?queues=(\d+).*?maps=", text):
        try:
            latest = int(match.group(1))
        except ValueError:
            continue

    return latest


def _extract_queue_total_from_logs() -> int | None:
    latest: int | None = None
    for path in (LOG_DIR / "bot_runtime.log", STDOUT_LOG):
        text = _read_tail(path)
        if not text:
            continue

        extracted = _extract_queue_total_from_log_text(text)
        if extracted is not None:
            latest = extracted

    return latest


def _extract_latest_queue_total() -> int | None:
    heartbeat = _read_heartbeat()
    if _heartbeat_is_fresh(heartbeat):
        heartbeat_total = _heartbeat_queue_total(heartbeat)
        if heartbeat_total is not None:
            return heartbeat_total

    return _extract_queue_total_from_logs()


def _health_probe() -> tuple[bool, str]:
    try:
        with urllib.request.urlopen(HEALTH_URL, timeout=HEALTH_TIMEOUT_SEC) as response:
            body = response.read(4096).decode("utf-8", errors="replace")
            status_code = getattr(response, "status", 200)
            if status_code != 200:
                return False, f"http_{status_code} {body[:300]}"
            try:
                payload = json.loads(body)
            except json.JSONDecodeError:
                return False, f"bad_json {body[:300]}"
            status = payload.get("status")
            if status != "ok":
                return False, f"status={status} body={body[:300]}"
            return True, body[:300]
    except urllib.error.HTTPError as exc:
        body = exc.read(4096).decode("utf-8", errors="replace")
        return False, f"http_error={exc.code} {body[:300]}"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def _kill_tree(process: subprocess.Popen, reason: str) -> None:
    pid = process.pid
    log(f"Killing bot child tree pid={pid}; reason={reason}")
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    else:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
    try:
        BOT_LOCK.unlink()
        log("Removed bot.lock after forced child stop")
    except FileNotFoundError:
        pass
    except OSError as exc:
        log(f"Could not remove bot.lock: {exc}")


def _start_child() -> subprocess.Popen:
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    LOG_DIR.mkdir(exist_ok=True)
    banner = (
        "\n======================================================\n"
        f"[{_now()}] START BOT CHILD\n"
        "======================================================\n"
    )
    print(banner, end="", flush=True)
    stdout_fh = STDOUT_LOG.open("a", encoding="utf-8", buffering=1)
    stdout_fh.write(banner)
    child = subprocess.Popen(
        [sys.executable, "-X", "utf8", "-u", "main.py"],
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    child._stdout_fh = stdout_fh  # type: ignore[attr-defined]
    pump_thread = threading.Thread(
        target=_pump_child_output,
        args=(child, stdout_fh),
        name=f"bot-child-log-pump-{child.pid}",
        daemon=True,
    )
    pump_thread.start()
    child._pump_thread = pump_thread  # type: ignore[attr-defined]
    log(f"Started bot child pid={child.pid}")
    return child


def _stop_requested() -> bool:
    return STOP_REQUEST.exists()


def _pump_child_output(process: subprocess.Popen, stdout_fh) -> None:
    stream = process.stdout
    if stream is None:
        return
    try:
        for line in stream:
            try:
                stdout_fh.write(line)
            except OSError:
                pass
            try:
                print(line, end="", flush=True)
            except Exception:
                pass
    finally:
        try:
            stream.close()
        except OSError:
            pass


def _close_child_log(process: subprocess.Popen) -> None:
    pump_thread = getattr(process, "_pump_thread", None)
    if pump_thread is not None:
        try:
            pump_thread.join(timeout=2)
        except RuntimeError:
            pass
    fh = getattr(process, "_stdout_fh", None)
    if fh is not None:
        try:
            fh.close()
        except OSError:
            pass


def main() -> int:
    LOG_DIR.mkdir(exist_ok=True)
    log("Supervisor started")
    while True:
        if _stop_requested():
            log("Stop request detected before child start; supervisor exits")
            return 0
        live_pid = _locked_live_bot_pid()
        if live_pid:
            log(
                f"bot.lock points to live pid={live_pid}; another bot is already running; supervisor exits"
            )
            log(
                "Existing live bot stdout is not attached to this window; "
                f"delivery stdout log={STDOUT_LOG}"
            )
            log(
                f"Runtime JSON/health log={LOG_DIR / 'bot_runtime.log'}; heartbeat={HEARTBEAT_LOG}"
            )
            log(
                "Use stop_bot.bat for controlled stop, or stop_bot.bat /force only if queue loss is accepted"
            )
            return 0
        child = _start_child()
        start_time = time.time()
        health_failures = 0
        last_heartbeat_notice = 0.0
        try:
            while True:
                return_code = child.poll()
                if return_code is not None:
                    log(f"Bot child exited pid={child.pid} code={return_code}")
                    _close_child_log(child)
                    if _stop_requested():
                        log("Stop request detected after child exit; supervisor exits")
                        return 0
                    live_pid = _locked_live_bot_pid()
                    if return_code == 0 and live_pid:
                        log(
                            f"Child exited normally while bot.lock is owned by live pid={live_pid}; "
                            "supervisor exits instead of restart-looping"
                        )
                        return 0
                    if return_code == 0:
                        log(
                            "Bot child exited normally without stop request; supervisor exits"
                        )
                        return 0
                    break

                uptime = time.time() - start_time
                stdout_age = _file_age_sec(STDOUT_LOG)
                runtime_age = _file_age_sec(LOG_DIR / "bot_runtime.log")

                if uptime >= WARMUP_SEC:
                    heartbeat = _read_heartbeat()
                    if _heartbeat_is_fresh(heartbeat):
                        if health_failures:
                            heartbeat_age = _heartbeat_age_sec(heartbeat)
                            heartbeat_queue_total = _heartbeat_queue_total(heartbeat)
                            log(
                                "Heartbeat restored watchdog confidence after "
                                f"{health_failures} HTTP failures; "
                                f"heartbeat_age={heartbeat_age:.1f}s; "
                                f"heartbeat_queue_total={heartbeat_queue_total}"
                            )
                        health_failures = 0
                        time.sleep(POLL_SEC)
                        continue

                    healthy, details = _health_probe()
                    heartbeat_age = _heartbeat_age_sec(heartbeat)
                    heartbeat_queue_total = _heartbeat_queue_total(heartbeat)
                    heartbeat_fresh = _heartbeat_is_fresh(heartbeat)
                    if healthy:
                        if health_failures:
                            log(
                                f"Health restored after {health_failures} failures: {details}"
                            )
                        health_failures = 0
                    elif heartbeat_fresh:
                        now = time.time()
                        if now - last_heartbeat_notice >= 60:
                            last_heartbeat_notice = now
                            log(
                                "HTTP health failed, but event-loop heartbeat is fresh; "
                                f"heartbeat_age={heartbeat_age:.1f}s; "
                                f"heartbeat_queue_total={heartbeat_queue_total}; details={details}"
                            )
                        health_failures = 0
                    else:
                        health_failures += 1
                        log(
                            "Health failure "
                            f"{health_failures}/{HEALTH_FAIL_LIMIT}: {details}; "
                            f"stdout_age={stdout_age}; runtime_age={runtime_age}"
                        )
                        logs_stale = (
                            stdout_age is None or stdout_age >= LOG_STALE_SEC
                        ) and (runtime_age is None or runtime_age >= LOG_STALE_SEC)
                        stale_status = (
                            "status=stale" in details or "http_error=503" in details
                        )
                        queue_total = _extract_latest_queue_total()
                        queue_safe = (
                            queue_total is None
                            or queue_total <= SAFE_RESTART_QUEUE_LIMIT
                        )
                        force_restart = (
                            health_failures >= FORCE_FAIL_LIMIT and queue_safe
                        )
                        if health_failures >= FORCE_FAIL_LIMIT and not queue_safe:
                            log(
                                "Health still failing, but restart deferred because "
                                f"latest_queue_total={queue_total} > {SAFE_RESTART_QUEUE_LIMIT}"
                            )
                        if health_failures >= HEALTH_FAIL_LIMIT and (
                            logs_stale or stale_status or force_restart
                        ):
                            _kill_tree(child, details)
                            _close_child_log(child)
                            break

                time.sleep(POLL_SEC)
        except KeyboardInterrupt:
            _kill_tree(child, "supervisor_keyboard_interrupt")
            _close_child_log(child)
            raise
        except Exception as exc:
            log(f"Supervisor loop error: {type(exc).__name__}: {exc}")
            _kill_tree(child, "supervisor_exception")
            _close_child_log(child)

        if _stop_requested():
            log("Stop request detected before restart; supervisor exits")
            return 0
        log(f"Restarting after {RESTART_DELAY_SEC}s")
        time.sleep(RESTART_DELAY_SEC)


if __name__ == "__main__":
    raise SystemExit(main())
