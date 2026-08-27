#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dvachbot Fast Log Audit Tool
Analyzes the tails of:
- logs/bot_fatal_crash.log
- logs/bot_deadlock_watchdog.log
- logs/bot_runtime.log
- logs/bot_stdout_utf8.log
"""

import os
import sys
import re
import json
import argparse
from datetime import datetime
from collections import Counter, defaultdict

try:
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

DEFAULT_LOGS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")


def read_tail_lines(filepath: str, n_lines: int = 10000) -> list[str]:
    """Efficiently reads the last n_lines from a large file using reverse chunk seeking."""
    if not os.path.exists(filepath):
        return []
    
    chunk_size = 262144  # 256KB chunks
    lines = []
    with open(filepath, "rb") as f:
        f.seek(0, os.SEEK_END)
        file_size = f.tell()
        buffer = bytearray()
        pos = file_size
        
        while pos > 0 and len(lines) <= n_lines:
            read_size = min(chunk_size, pos)
            pos -= read_size
            f.seek(pos)
            chunk = f.read(read_size)
            buffer = chunk + buffer
            lines = buffer.split(b"\n")
            if len(lines) > n_lines:
                break
                
    decoded = []
    for raw in lines[-n_lines:]:
        try:
            decoded.append(raw.decode("utf-8", errors="replace").rstrip("\r\n"))
        except Exception:
            decoded.append(raw.decode("latin-1", errors="replace").rstrip("\r\n"))
    return decoded


def audit_fatal_crashes(logs_dir: str) -> dict:
    filepath = os.path.join(logs_dir, "bot_fatal_crash.log")
    res = {"path": filepath, "exists": os.path.exists(filepath), "total_armed": 0, "crashes": []}
    if not res["exists"]:
        return res

    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()

    crash_matches = list(re.finditer(
        r"(=== FATAL CRASH WATCH ARMED pid=(\d+) ts=([0-9.]+) ===)(.*?)(?==== FATAL CRASH WATCH ARMED|\Z)",
        content,
        re.DOTALL
    ))
    res["total_armed"] = len(crash_matches)

    for m in crash_matches:
        pid = m.group(2)
        ts = float(m.group(3))
        body = m.group(4).strip()
        if body:
            dt = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
            lines = body.splitlines()
            header = lines[0] if lines else "Unknown Crash"
            frames = [l.strip() for l in lines if "File " in l]
            res["crashes"].append({
                "timestamp": dt,
                "epoch": ts,
                "pid": pid,
                "exception": header,
                "top_frame": frames[0] if frames else "N/A",
                "bottom_frame": frames[-1] if frames else "N/A",
                "full_trace": body[:1500]
            })
    return res


def audit_deadlocks(logs_dir: str) -> dict:
    filepath = os.path.join(logs_dir, "bot_deadlock_watchdog.log")
    res = {"path": filepath, "exists": os.path.exists(filepath), "restarts": []}
    if not res["exists"]:
        return res

    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    restart_indices = [i for i, l in enumerate(lines) if "EMERGENCY DEADLOCK AUTO-RESTART" in l]
    for idx in restart_indices:
        header = lines[idx].strip()
        m = re.search(r"ts=([0-9.]+)\s+lag=([0-9.]+)s", header)
        ts_str = ""
        lag = 0.0
        if m:
            epoch = float(m.group(1))
            lag = float(m.group(2))
            ts_str = datetime.fromtimestamp(epoch).strftime("%Y-%m-%d %H:%M:%S")

        stack = []
        for k in range(idx + 1, min(len(lines), idx + 80)):
            l = lines[k].rstrip()
            if "EMERGENCY RESTART TRIGGERED" in l:
                break
            if any(term in l for term in ["Thread 0x", "File ", "line "]):
                stack.append(l.strip())

        res["restarts"].append({
            "timestamp": ts_str,
            "header": header,
            "lag_sec": lag,
            "frames_sample": stack[:8]
        })
    return res


def audit_tail_log(filepath: str, n_lines: int = 10000) -> dict:
    res = {
        "path": filepath,
        "exists": os.path.exists(filepath),
        "lines_analyzed": 0,
        "time_range": {"first": "", "last": ""},
        "counts": {
            "CRITICAL": 0,
            "ERROR": 0,
            "WARNING": 0,
            "TG_BAD_REQUEST": 0,
            "TG_FLOOD": 0,
            "DB_ISSUE": 0
        },
        "top_errors": [],
        "top_warnings": [],
        "tracebacks": []
    }
    if not res["exists"]:
        return res

    lines = read_tail_lines(filepath, n_lines)
    res["lines_analyzed"] = len(lines)
    if lines:
        res["time_range"]["first"] = lines[0][:40]
        res["time_range"]["last"] = lines[-1][:40]

    err_counter = Counter()
    err_samples = {}
    warn_counter = Counter()
    warn_samples = {}
    tb_map = {}

    in_tb = False
    cur_tb = []

    for idx, line in enumerate(lines):
        up = line.upper()

        if "TRACEBACK (MOST RECENT CALL LAST):" in up:
            in_tb = True
            cur_tb = [line]
            continue
        if in_tb:
            cur_tb.append(line)
            if not line.startswith(" ") and any(e in line for e in ["Error", "Exception"]):
                tb_text = "\n".join(cur_tb)
                last_line = line.strip()
                if last_line not in tb_map:
                    tb_map[last_line] = tb_text
                in_tb = False
                cur_tb = []
            elif len(cur_tb) > 60:
                tb_text = "\n".join(cur_tb)
                last_line = cur_tb[-1].strip()
                if last_line not in tb_map:
                    tb_map[last_line] = tb_text
                in_tb = False
                cur_tb = []

        if "CRITICAL" in up:
            res["counts"]["CRITICAL"] += 1
        elif "ERROR" in up:
            res["counts"]["ERROR"] += 1
        elif "WARNING" in up:
            res["counts"]["WARNING"] += 1

        if any(term in up for term in ["TELEGRAMBADREQUEST", "BAD REQUEST"]):
            res["counts"]["TG_BAD_REQUEST"] += 1
        if any(term in up for term in ["FLOOD", "RETRY_AFTER", "429 TOO MANY REQUESTS"]):
            res["counts"]["TG_FLOOD"] += 1
        if any(term in up for term in ["OPERATIONALERROR", "DATABASE IS LOCKED", "DISK I/O", "DATABASE DISK IMAGE IS MALFORMED", "SQLITE_BUSY"]):
            res["counts"]["DB_ISSUE"] += 1

        if "ERROR" in up or "CRITICAL" in up:
            clean = re.sub(r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(,\d+)?\s*", "", line)
            clean = re.sub(r"\b\d+\b", "[N]", clean)
            err_counter[clean] += 1
            if clean not in err_samples:
                err_samples[clean] = line

        elif "WARNING" in up:
            clean = re.sub(r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(,\d+)?\s*", "", line)
            clean = re.sub(r"\b\d+\b", "[N]", clean)
            warn_counter[clean] += 1
            if clean not in warn_samples:
                warn_samples[clean] = line

    for pat, cnt in err_counter.most_common(15):
        res["top_errors"].append({"count": cnt, "sample": err_samples[pat]})

    for pat, cnt in warn_counter.most_common(15):
        res["top_warnings"].append({"count": cnt, "sample": warn_samples[pat]})

    for exc_line, full_tb in tb_map.items():
        res["tracebacks"].append({"exception": exc_line, "traceback": full_tb})

    return res


def print_report(fatal_data: dict, deadlock_data: dict, rt_data: dict, stdout_data: dict):
    print("=" * 80)
    print("           DVACHBOT COMPREHENSIVE LOG AUDIT REPORT")
    print("=" * 80)
    print(f"Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # 1. Fatal Crashes
    print("\n" + "-" * 80)
    print(f"1. FATAL CRASH WATCH (bot_fatal_crash.log)")
    print("-" * 80)
    print(f"File: {fatal_data['path']} (Armed runs: {fatal_data['total_armed']})")
    if not fatal_data["crashes"]:
        print("✅ No fatal crashes recorded in log.")
    else:
        print(f"⚠️ Total Fatal Crashes Recorded: {len(fatal_data['crashes'])}")
        for i, c in enumerate(fatal_data["crashes"], 1):
            print(f"  [{i}] {c['timestamp']} (PID {c['pid']}): {c['exception']}")
            print(f"      Top:    {c['top_frame']}")
            print(f"      Bottom: {c['bottom_frame']}")

    # 2. Deadlocks
    print("\n" + "-" * 80)
    print("2. DEADLOCK & STALL WATCHDOG (bot_deadlock_watchdog.log)")
    print("-" * 80)
    print(f"File: {deadlock_data['path']}")
    if not deadlock_data["restarts"]:
        print("✅ No emergency deadlock restarts recorded.")
    else:
        print(f"🚨 Emergency Deadlock Restarts: {len(deadlock_data['restarts'])}")
        for i, r in enumerate(deadlock_data["restarts"], 1):
            print(f"  [{i}] {r['timestamp']} | {r['header']}")
            for f in r["frames_sample"][:4]:
                print(f"      {f}")

    # 3. Runtime Log
    print("\n" + "-" * 80)
    print("3. BOT RUNTIME LOG (bot_runtime.log)")
    print("-" * 80)
    print(f"File: {rt_data['path']}")
    print(f"Lines analyzed: {rt_data['lines_analyzed']}")
    print(f"Time span: {rt_data['time_range']['first']} -> {rt_data['time_range']['last']}")
    print("Event Counts:", rt_data["counts"])
    if rt_data["top_errors"]:
        print("\nTop Errors in bot_runtime.log:")
        for item in rt_data["top_errors"][:5]:
            print(f"  [{item['count']}x] {item['sample']}")

    # 4. Stdout Log
    print("\n" + "-" * 80)
    print("4. BOT STDOUT UTF-8 LOG (bot_stdout_utf8.log)")
    print("-" * 80)
    print(f"File: {stdout_data['path']}")
    print(f"Lines analyzed from tail: {stdout_data['lines_analyzed']}")
    print(f"Time span: {stdout_data['time_range']['first']} -> {stdout_data['time_range']['last']}")
    print("Event Counts:", stdout_data["counts"])
    
    if stdout_data["top_errors"]:
        print("\nTop Errors in bot_stdout_utf8.log:")
        for item in stdout_data["top_errors"][:8]:
            print(f"  [{item['count']}x] {item['sample']}")

    if stdout_data["top_warnings"]:
        print("\nTop Warnings in bot_stdout_utf8.log:")
        for item in stdout_data["top_warnings"][:8]:
            print(f"  [{item['count']}x] {item['sample']}")

    if stdout_data["tracebacks"]:
        print(f"\nUnique Tracebacks Found ({len(stdout_data['tracebacks'])}):")
        for i, tb in enumerate(stdout_data["tracebacks"], 1):
            print(f"\n  --- Traceback #{i}: {tb['exception']} ---")
            lines = tb["traceback"].splitlines()
            user_frames = [l for l in lines if "dvachbot" in l]
            for uf in user_frames[-3:]:
                print(f"    {uf.strip()}")
            print(f"    {lines[-1].strip()}")

    print("\n" + "=" * 80)


def main():
    parser = argparse.ArgumentParser(description="dvachbot Fast Log Audit Tool")
    parser.add_argument("--logs-dir", default=DEFAULT_LOGS_DIR, help="Path to logs directory")
    parser.add_argument("--lines", type=int, default=10000, help="Number of tail lines to inspect")
    parser.add_argument("--json", action="store_true", help="Output results in JSON format")
    args = parser.parse_args()

    fatal = audit_fatal_crashes(args.logs_dir)
    deadlock = audit_deadlocks(args.logs_dir)
    rt = audit_tail_log(os.path.join(args.logs_dir, "bot_runtime.log"), args.lines)
    stdout = audit_tail_log(os.path.join(args.logs_dir, "bot_stdout_utf8.log"), args.lines)

    if args.json:
        print(json.dumps({
            "fatal_crash": fatal,
            "deadlock_watchdog": deadlock,
            "bot_runtime": rt,
            "bot_stdout_utf8": stdout
        }, ensure_ascii=False, indent=2))
    else:
        print_report(fatal, deadlock, rt, stdout)


if __name__ == "__main__":
    main()
