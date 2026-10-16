import pytest
from common.json_utils import fast_json_loads, fast_json_dumps

def test_fast_json_loads_valid():
    assert fast_json_loads('{"a": 1, "b": "test"}') == {"a": 1, "b": "test"}
    assert fast_json_loads(b'[1, 2, 3]') == [1, 2, 3]

def test_fast_json_loads_empty():
    assert fast_json_loads("") is None
    assert fast_json_loads(b"") is None
    assert fast_json_loads(None) is None

def test_fast_json_loads_invalid():
    # Use general Exception to catch both json.JSONDecodeError and orjson.JSONDecodeError
    with pytest.raises(Exception):
        fast_json_loads("{invalid json}")

def test_fast_json_dumps_valid():
    dumped = fast_json_dumps({"a": 1, "b": "test"})
    # Parse back to check semantic equality, as string formatting might differ slightly
    assert fast_json_loads(dumped) == {"a": 1, "b": "test"}

def test_fast_json_dumps_default():
    from datetime import datetime
    dt = datetime(2023, 1, 1, 12, 0, 0)
    dumped = fast_json_dumps({"time": dt})
    assert "2023-01-01 12:00:00" in dumped
