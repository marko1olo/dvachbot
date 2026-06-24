import unittest
from unittest.mock import patch
import socket

from japanese_translator import get_dynamic_proxy_url

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

if __name__ == '__main__':
    unittest.main()