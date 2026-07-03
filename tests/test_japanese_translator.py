import unittest
from unittest.mock import patch
import socket

from japanese_translator import get_dynamic_proxy_url
import pytest
from japanese_translator import _tag_token_is_blocked, _normalize_tag_token
import japanese_translator

class TestJapaneseTranslator(unittest.TestCase):

    @patch('japanese_translator.socket.create_connection')
    def test_first_port_open(self, mock_create_connection):
        # socket.create_connection succeeds for the first port
        # meaning no exception is raised
        from unittest.mock import MagicMock
        mock_socket = MagicMock()
        mock_create_connection.return_value = mock_socket

        url = get_dynamic_proxy_url()

        self.assertEqual(url, "http://127.0.0.1:2334")
        mock_create_connection.assert_called_once_with(("127.0.0.1", 2334), timeout=0.1)

    @patch('japanese_translator.socket.create_connection')
    def test_all_ports_closed(self, mock_create_connection):
        # socket.create_connection fails for all ports
        mock_create_connection.side_effect = OSError

        url = get_dynamic_proxy_url()

        self.assertIsNone(url)
        self.assertEqual(mock_create_connection.call_count, 5)

    @patch('japanese_translator.socket.create_connection')
    def test_third_port_open(self, mock_create_connection):
        # socket.create_connection fails for the first 2 ports, succeeds for the 3rd
        from unittest.mock import MagicMock
        def side_effect(address, timeout):
            if address[1] in [2334, 12334]:
                raise OSError
            return MagicMock()

        mock_create_connection.side_effect = side_effect

        url = get_dynamic_proxy_url()

        self.assertEqual(url, "http://127.0.0.1:2080")
        self.assertEqual(mock_create_connection.call_count, 3)

def test_normalize_tag_token():
    assert _normalize_tag_token(" SHOTA ") == "shota"
    assert _normalize_tag_token("little boy") == "little_boy"
    assert _normalize_tag_token("-SHOTA") == "-shota"

def test_tag_token_is_blocked():
    # Exact matches from ANIME_HARD_BLOCKED_TAGS
    assert _tag_token_is_blocked("shota") is True
    assert _tag_token_is_blocked("cub") is True
    assert _tag_token_is_blocked("little_girl") is True
    assert _tag_token_is_blocked("underage") is True

    # Prefix matches from ANIME_HARD_BLOCKED_PREFIXES
    assert _tag_token_is_blocked("shotacon") is True
    assert _tag_token_is_blocked("shotacontent") is True

    # Case insensitive and space handling (handled by normalize)
    assert _tag_token_is_blocked(" SHOTA ") is True
    assert _tag_token_is_blocked("Little Girl") is True

    # Negative tags handling (should strip leading '-')
    assert _tag_token_is_blocked("-shota") is True
    assert _tag_token_is_blocked("-cub") is True

    # Unblocked tags
    assert _tag_token_is_blocked("1girl") is False
    assert _tag_token_is_blocked("cat") is False
    assert _tag_token_is_blocked("dog") is False
    assert _tag_token_is_blocked("safe") is False
    assert _tag_token_is_blocked("") is False

def test_tag_token_is_blocked_custom_globals(monkeypatch):
    monkeypatch.setattr(japanese_translator, 'ANIME_HARD_BLOCKED_TAGS', {"test_blocked"})
    monkeypatch.setattr(japanese_translator, 'ANIME_HARD_BLOCKED_PREFIXES', ("test_prefix_",))

    assert _tag_token_is_blocked("test_blocked") is True
    assert _tag_token_is_blocked("test_prefix_something") is True
    assert _tag_token_is_blocked("other_tag") is False

if __name__ == '__main__':
    unittest.main()
