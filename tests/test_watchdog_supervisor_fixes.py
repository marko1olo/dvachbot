import json
import os
import signal
import subprocess
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import bot_watchdog


@pytest.fixture
def isolated_watchdog_env(tmp_path):
    """
    Provides isolated temporary file paths for all watchdog locks, logs,
    and signaling files so tests run in complete filesystem isolation.
    """
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    heartbeat_file = logs_dir / "bot_heartbeat.json"
    stdout_file = logs_dir / "bot_stdout_utf8.log"
    supervisor_log = logs_dir / "bot_supervisor.log"
    bot_lock_file = tmp_path / "bot.lock"
    bot_restart_file = tmp_path / "bot.restart"
    bot_stop_file = tmp_path / "bot.stop"
    supervisor_lock_file = tmp_path / "supervisor.lock"

    with patch.object(bot_watchdog, "ROOT", tmp_path), \
         patch.object(bot_watchdog, "LOG_DIR", logs_dir), \
         patch.object(bot_watchdog, "HEARTBEAT_LOG", heartbeat_file), \
         patch.object(bot_watchdog, "STDOUT_LOG", stdout_file), \
         patch.object(bot_watchdog, "SUPERVISOR_LOG", supervisor_log), \
         patch.object(bot_watchdog, "BOT_LOCK", bot_lock_file), \
         patch.object(bot_watchdog, "BOT_RESTART_PATH", bot_restart_file), \
         patch.object(bot_watchdog, "STOP_REQUEST", bot_stop_file), \
         patch.object(bot_watchdog, "SUPERVISOR_LOCK", supervisor_lock_file):
        yield {
            "tmp_path": tmp_path,
            "logs_dir": logs_dir,
            "heartbeat": heartbeat_file,
            "bot_lock": bot_lock_file,
            "bot_restart": bot_restart_file,
            "bot_stop": bot_stop_file,
            "supervisor_lock": supervisor_lock_file,
        }


def test_stale_heartbeat_from_old_pid_does_not_trigger_false_soft_restart_kill(isolated_watchdog_env):
    """
    CRITICAL DEFECT REGRESSION TEST:
    When a new bot child starts (PID=2000), a leftover bot_heartbeat.json from an old
    process (PID=1000) with drain_shutdown_requested=True must NOT cause the supervisor
    to arm soft_restart_requested_at and kill the healthy new process.
    """
    env = isolated_watchdog_env

    # 1. Simulate leftover heartbeat from the old process (PID 1000)
    old_heartbeat_payload = {
        "ts": time.time(),
        "pid": 1000,
        "drain_shutdown_requested": True,
        "is_shutting_down": True,
        "queues_total": 0,
    }
    env["heartbeat"].write_text(json.dumps(old_heartbeat_payload), encoding="utf-8")

    # 2. Mock new child with PID 2000
    mock_child = MagicMock(spec=subprocess.Popen)
    mock_child.pid = 2000
    # Simulate child running for 2 loop iterations, then exiting normally
    mock_child.poll.side_effect = [None, None, 0]
    mock_child.wait.return_value = 0

    killed_reasons = []

    def mock_kill_tree(process, reason):
        killed_reasons.append(reason)

    with patch.object(bot_watchdog, "_kill_tree", side_effect=mock_kill_tree), \
         patch.object(bot_watchdog, "_close_child_log"), \
         patch.object(bot_watchdog, "_health_probe", return_value=(True, "ok")), \
         patch.object(bot_watchdog, "_stop_requested", return_value=False), \
         patch.object(bot_watchdog, "_locked_live_bot_pid", return_value=None), \
         patch("time.sleep", return_value=None):

        should_exit = bot_watchdog._monitor_child(mock_child)

        # The child should exit normally without being killed
        assert should_exit is False
        assert "soft_restart_timeout" not in killed_reasons
        assert len(killed_reasons) == 0


def test_matching_pid_drain_shutdown_arms_and_triggers_soft_restart(isolated_watchdog_env):
    """
    Verifies that when the active child (PID=2000) itself sets drain_shutdown_requested=True,
    the supervisor correctly recognizes it, arms the grace period, and forces kill
    only if the grace period expires.
    """
    env = isolated_watchdog_env

    # Active child has PID 2000 and is draining
    current_heartbeat = {
        "ts": time.time(),
        "pid": 2000,
        "drain_shutdown_requested": True,
        "is_shutting_down": False,
        "queues_total": 5,
    }
    env["heartbeat"].write_text(json.dumps(current_heartbeat), encoding="utf-8")

    mock_child = MagicMock(spec=subprocess.Popen)
    mock_child.pid = 2000
    # Process never exits on its own
    mock_child.poll.return_value = None

    killed_reasons = []

    def mock_kill_tree(process, reason):
        killed_reasons.append(reason)

    # Simulate clock advancing past SOFT_RESTART_GRACE_SEC
    fake_time = 1000.0
    def mock_time():
        nonlocal fake_time
        # Advance clock by 100 seconds on subsequent calls
        current = fake_time
        fake_time += 100.0
        return current

    with patch.object(bot_watchdog, "_kill_tree", side_effect=mock_kill_tree), \
         patch.object(bot_watchdog, "_close_child_log"), \
         patch("time.time", side_effect=mock_time):

        should_exit = bot_watchdog._monitor_child(mock_child)

        assert should_exit is False
        assert "soft_restart_timeout" in killed_reasons


def test_start_child_cleans_stale_heartbeat_restart_flag_and_dead_lock(isolated_watchdog_env):
    """
    Verifies that _start_child() cleans:
    1. BOT_RESTART_PATH (bot.restart)
    2. HEARTBEAT_LOG (bot_heartbeat.json)
    3. BOT_LOCK (bot.lock) if it points to a non-existent process
    """
    env = isolated_watchdog_env

    # Create stale artifacts
    env["bot_restart"].write_text("scheduled_restart", encoding="utf-8")
    env["heartbeat"].write_text(json.dumps({"pid": 9999, "ts": 12345}), encoding="utf-8")
    env["bot_lock"].write_text("88888", encoding="utf-8")

    assert env["bot_restart"].exists()
    assert env["heartbeat"].exists()
    assert env["bot_lock"].exists()

    mock_proc = MagicMock(spec=subprocess.Popen)
    mock_proc.pid = 3000
    mock_proc.stdout = None

    with patch("subprocess.Popen", return_value=mock_proc), \
         patch.object(bot_watchdog, "_is_bot_process", return_value=False), \
         patch.object(bot_watchdog, "_pump_child_output"):

        child = bot_watchdog._start_child()
        assert child.pid == 3000

        # All stale files must be eradicated before child start
        assert not env["bot_restart"].exists()
        assert not env["heartbeat"].exists()
        assert not env["bot_lock"].exists()


def test_supervisor_lock_acquire_and_release(isolated_watchdog_env):
    """
    Verifies mutual exclusion and clean cleanup of supervisor.lock.
    """
    env = isolated_watchdog_env

    # 1. Clean acquire
    assert bot_watchdog._acquire_supervisor_lock() is True
    assert env["supervisor_lock"].exists()
    assert env["supervisor_lock"].read_text(encoding="utf-8").strip() == str(os.getpid())

    # 2. Attempt acquire by same process (re-entrant / idempotent)
    assert bot_watchdog._acquire_supervisor_lock() is True

    # 3. Clean release
    bot_watchdog._release_supervisor_lock()
    assert not env["supervisor_lock"].exists()

    # 4. Another PID trying to release must not delete active lock
    env["supervisor_lock"].write_text("999999", encoding="utf-8")
    bot_watchdog._release_supervisor_lock()
    assert env["supervisor_lock"].exists()
    assert env["supervisor_lock"].read_text(encoding="utf-8").strip() == "999999"


def test_monitor_child_keyboard_interrupt_cleans_locks_and_kills_child(isolated_watchdog_env):
    """
    Verifies that when KeyboardInterrupt / termination signal arrives,
    lingering child process is terminated and bot.lock is cleared.
    """
    env = isolated_watchdog_env
    env["bot_lock"].write_text("2000", encoding="utf-8")

    mock_child = MagicMock(spec=subprocess.Popen)
    mock_child.pid = 2000
    # Simulate child lingering and timing out on wait(5.0)
    mock_child.poll.side_effect = KeyboardInterrupt
    mock_child.wait.side_effect = subprocess.TimeoutExpired(cmd="bot", timeout=5.0)

    killed_reasons = []

    def mock_kill_tree(process, reason):
        killed_reasons.append(reason)
        # _kill_tree unlinks lock
        env["bot_lock"].unlink(missing_ok=True)

    with patch.object(bot_watchdog, "_kill_tree", side_effect=mock_kill_tree), \
         patch.object(bot_watchdog, "_close_child_log"):

        should_exit = bot_watchdog._monitor_child(mock_child)

        assert should_exit is True
        assert "supervisor_keyboard_interrupt" in killed_reasons
        assert not env["bot_lock"].exists()


def test_heartbeat_is_fresh_pid_and_shutdown_matrix():
    """
    Verifies the complete freshness matrix:
    - Fresh heartbeat matching PID -> True
    - Fresh heartbeat with mismatched PID -> False
    - Stale heartbeat -> False
    - Draining shutdown (drain_shutdown_requested=True) -> True
    - Hard shutdown without drain -> False
    """
    now = time.time()

    with patch("bot_watchdog._heartbeat_age_sec", return_value=5.0):
        # 1. Matching PID
        assert bot_watchdog._heartbeat_is_fresh({"ts": now, "pid": 1000}, expected_pid=1000) is True

        # 2. Mismatched PID
        assert bot_watchdog._heartbeat_is_fresh({"ts": now, "pid": 9999}, expected_pid=1000) is False

        # 3. No expected PID specified (backwards compatible)
        assert bot_watchdog._heartbeat_is_fresh({"ts": now, "pid": 9999}) is True

        # 4. Graceful drain shutdown: fresh even if is_shutting_down=True
        assert bot_watchdog._heartbeat_is_fresh({
            "ts": now,
            "pid": 1000,
            "is_shutting_down": True,
            "drain_shutdown_requested": True,
        }, expected_pid=1000) is True

        # 5. Non-graceful shutdown: False
        assert bot_watchdog._heartbeat_is_fresh({
            "ts": now,
            "pid": 1000,
            "is_shutting_down": True,
            "drain_shutdown_requested": False,
        }, expected_pid=1000) is False

    with patch("bot_watchdog._heartbeat_age_sec", return_value=bot_watchdog.HEARTBEAT_STALE_SEC + 10.0):
        # 6. Truly stale age is always False
        assert bot_watchdog._heartbeat_is_fresh({"ts": now - 100.0, "pid": 1000}, expected_pid=1000) is False
