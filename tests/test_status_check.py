import pytest
import time
from unittest.mock import patch
from status_check import format_age

def test_format_age_empty():
    assert format_age(None) == "[dim]N/A[/dim]"
    assert format_age(0) == "[dim]N/A[/dim]"
    assert format_age("") == "[dim]N/A[/dim]"

@patch('time.time')
def test_format_age_seconds(mock_time):
    mock_time.return_value = 1000
    # Between 0 and 59 seconds
    assert format_age(980) == "[green]20s ago[/green]"
    assert format_age(941) == "[green]59s ago[/green]"

@patch('time.time')
def test_format_age_minutes(mock_time):
    mock_time.return_value = 1000
    # Between 60 and 3599 seconds
    assert format_age(940) == "[green]1m ago[/green]"
    assert format_age(900) == "[green]1m ago[/green]"
    assert format_age(1000 - 3599) == "[green]59m ago[/green]"

@patch('time.time')
def test_format_age_hours(mock_time):
    mock_time.return_value = 10000
    # Between 3600 and 86399 seconds
    assert format_age(10000 - 3600) == "[yellow]1h ago[/yellow]"
    assert format_age(10000 - 3600*2) == "[yellow]2h ago[/yellow]"
    assert format_age(10000 - 86399) == "[yellow]23h ago[/yellow]"

@patch('time.time')
def test_format_age_days(mock_time):
    mock_time.return_value = 1000000
    # 86400 seconds or more
    assert format_age(1000000 - 86400) == "[bold red]1d ago[/bold red]"
    assert format_age(1000000 - 86400*3) == "[bold red]3d ago[/bold red]"

def test_format_age_type_errors():
    # ValueErrors or TypeErrors should safely return N/A
    assert format_age("invalid") == "[dim]N/A[/dim]"
    assert format_age([1, 2, 3]) == "[dim]N/A[/dim]"
    assert format_age({"ts": 12345}) == "[dim]N/A[/dim]"
