import unittest
from unittest.mock import patch
import os
import asyncio

# Mock environment variables before importing
os.environ['SECRET_KEY'] = 'test_secret_key'
os.environ['BOT_TOKEN'] = 'test_bot_token'
os.environ['OPENAI_API_KEY'] = 'test_openai_api_key'

# Create and set new event loop to avoid Pyrogram/asyncio errors
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

from status_check import format_age

class TestStatusCheck(unittest.TestCase):
    def test_format_age_null_or_zero(self):
        self.assertEqual(format_age(None), "[dim]N/A[/dim]")
        self.assertEqual(format_age(0), "[dim]N/A[/dim]")

    def test_format_age_error_handling(self):
        self.assertEqual(format_age("invalid_string"), "[dim]N/A[/dim]")

    @patch('status_check.time.time')
    def test_format_age_seconds(self, mock_time):
        mock_time.return_value = 1000.0
        self.assertEqual(format_age(970.0), "[green]30s ago[/green]")
        self.assertEqual(format_age(999.0), "[green]1s ago[/green]")
        self.assertEqual(format_age(1000.0), "[green]0s ago[/green]")

    @patch('status_check.time.time')
    def test_format_age_minutes(self, mock_time):
        mock_time.return_value = 10000.0
        self.assertEqual(format_age(10000.0 - 60), "[green]1m ago[/green]")
        self.assertEqual(format_age(10000.0 - 3599), "[green]59m ago[/green]")
        self.assertEqual(format_age(10000.0 - 150), "[green]2m ago[/green]")

    @patch('status_check.time.time')
    def test_format_age_hours(self, mock_time):
        mock_time.return_value = 100000.0
        self.assertEqual(format_age(100000.0 - 3600), "[yellow]1h ago[/yellow]")
        self.assertEqual(format_age(100000.0 - 86399), "[yellow]23h ago[/yellow]")
        self.assertEqual(format_age(100000.0 - 7200), "[yellow]2h ago[/yellow]")

    @patch('status_check.time.time')
    def test_format_age_days(self, mock_time):
        mock_time.return_value = 1000000.0
        self.assertEqual(format_age(1000000.0 - 86400), "[bold red]1d ago[/bold red]")
        self.assertEqual(format_age(1000000.0 - 172800), "[bold red]2d ago[/bold red]")
        self.assertEqual(format_age(1000000.0 - (86400 * 5 + 1000)), "[bold red]5d ago[/bold red]")

if __name__ == '__main__':
    unittest.main()
