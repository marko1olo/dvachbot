import os
import sys
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from status_check import format_queue_value

class TestStatusCheck(unittest.TestCase):
    def test_format_queue_value_none(self):
        self.assertEqual(format_queue_value(None), "N/A")

    def test_format_queue_value_float(self):
        self.assertEqual(format_queue_value(3.14159), "[green]3.1[/green]")
        self.assertEqual(format_queue_value(101.5), "[bold yellow]101.5[/bold yellow]")

    def test_format_queue_value_string(self):
        self.assertEqual(format_queue_value("N/A"), "[bold red]N/A[/bold red]")
        self.assertEqual(format_queue_value("Error"), "[bold red]Error[/bold red]")

    def test_format_queue_value_large_number(self):
        self.assertEqual(format_queue_value(1001), "[bold red]1,001[/bold red]")
        self.assertEqual(format_queue_value(500000), "[bold red]500,000[/bold red]")

    def test_format_queue_value_medium_number(self):
        self.assertEqual(format_queue_value(101), "[bold yellow]101[/bold yellow]")
        self.assertEqual(format_queue_value(1000), "[bold yellow]1,000[/bold yellow]")

    def test_format_queue_value_small_number(self):
        self.assertEqual(format_queue_value(100), "[green]100[/green]")
        self.assertEqual(format_queue_value(0), "[green]0[/green]")
        self.assertEqual(format_queue_value(42), "[green]42[/green]")
        self.assertEqual(format_queue_value(-10), "[green]-10[/green]")

if __name__ == '__main__':
    unittest.main()
