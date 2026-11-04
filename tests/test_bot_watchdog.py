from unittest.mock import patch
import bot_watchdog


def test_heartbeat_is_fresh():
    # Test None payload
    assert bot_watchdog._heartbeat_is_fresh(None) is False

    # Test empty payload
    assert bot_watchdog._heartbeat_is_fresh({}) is False

    # Test when heartbeat age is None
    with patch("bot_watchdog._heartbeat_age_sec", return_value=None):
        assert bot_watchdog._heartbeat_is_fresh({"ts": 123}) is False

    # Test fresh heartbeat
    with patch(
        "bot_watchdog._heartbeat_age_sec",
        return_value=bot_watchdog.HEARTBEAT_STALE_SEC - 1,
    ):
        assert bot_watchdog._heartbeat_is_fresh({"ts": 123}) is True

    # Test exact boundary fresh heartbeat
    with patch(
        "bot_watchdog._heartbeat_age_sec", return_value=bot_watchdog.HEARTBEAT_STALE_SEC
    ):
        assert bot_watchdog._heartbeat_is_fresh({"ts": 123}) is True

    # Test stale heartbeat
    with patch(
        "bot_watchdog._heartbeat_age_sec",
        return_value=bot_watchdog.HEARTBEAT_STALE_SEC + 1,
    ):
        assert bot_watchdog._heartbeat_is_fresh({"ts": 123}) is False

    # Test fresh heartbeat but is_shutting_down is True
    with patch(
        "bot_watchdog._heartbeat_age_sec",
        return_value=bot_watchdog.HEARTBEAT_STALE_SEC - 1,
    ):
        assert (
            bot_watchdog._heartbeat_is_fresh({"ts": 123, "is_shutting_down": True})
            is False
        )
        assert (
            bot_watchdog._heartbeat_is_fresh({"ts": 123, "is_shutting_down": 1})
            is False
        )


def test_monitor_child_recovers_when_known_worker_lingers():
    from unittest.mock import MagicMock
    child = MagicMock()
    child.pid = 1000
    child.poll.return_value = 0
    mock_lock = MagicMock()

    with patch("bot_watchdog._close_child_log"), \
         patch("bot_watchdog._stop_requested", return_value=False), \
         patch("bot_watchdog._read_lock_pid", return_value=2000), \
         patch("bot_watchdog._locked_live_bot_pid", return_value=2000), \
         patch("bot_watchdog._is_bot_process", side_effect=[True, False]), \
         patch("bot_watchdog._kill_pid_tree") as mock_kill, \
         patch("bot_watchdog.BOT_LOCK", mock_lock):

        should_exit = bot_watchdog._monitor_child(child)
        assert should_exit is False
        mock_lock.unlink.assert_called()


def test_monitor_child_kills_unhealthy_zombie_and_restarts():
    from unittest.mock import MagicMock
    child = MagicMock()
    child.pid = 1000
    child.poll.return_value = 1
    mock_lock = MagicMock()

    with patch("bot_watchdog._close_child_log"), \
         patch("bot_watchdog._stop_requested", return_value=False), \
         patch("bot_watchdog._read_lock_pid", return_value=None), \
         patch("bot_watchdog._locked_live_bot_pid", return_value=9999), \
         patch("bot_watchdog._health_probe", return_value=(False, "http_503")), \
         patch("bot_watchdog._kill_pid_tree") as mock_kill, \
         patch("bot_watchdog.BOT_LOCK", mock_lock):

        should_exit = bot_watchdog._monitor_child(child)
        assert should_exit is False
        mock_kill.assert_called_with(9999, "unhealthy_zombie_cleanup")
        mock_lock.unlink.assert_called()

