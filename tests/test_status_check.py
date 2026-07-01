import pytest
from unittest.mock import patch, MagicMock
from status_check import get_system_health

def test_get_system_health_success():
    with patch("status_check.psutil") as mock_psutil:
        mock_psutil.cpu_percent.return_value = 10.5
        mock_vm = MagicMock()
        mock_vm.percent = 20.0
        mock_psutil.virtual_memory.return_value = mock_vm
        mock_disk = MagicMock()
        mock_disk.percent = 30.5
        mock_psutil.disk_usage.return_value = mock_disk

        result = get_system_health()
        assert result == {"cpu": 10.5, "ram": 20.0, "disk": 30.5}

def test_get_system_health_psutil_none():
    with patch("status_check.psutil", None):
        result = get_system_health()
        assert result == {"cpu": "N/A", "ram": "N/A", "disk": "N/A"}

def test_get_system_health_exception():
    with patch("status_check.psutil") as mock_psutil:
        mock_psutil.cpu_percent.side_effect = Exception("Test Exception")

        result = get_system_health()
        assert result == {"cpu": "Error", "ram": "Error", "disk": "Error"}
