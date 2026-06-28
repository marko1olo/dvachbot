import pytest
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
