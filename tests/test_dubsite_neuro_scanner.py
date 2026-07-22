import pytest
from unittest.mock import MagicMock
from Dubsite_tgach.neuro_scanner import NeuroScanner
from site_tgach.neuro_poster import NeuroManager

@pytest.mark.asyncio
async def test_dubsite_neuro_scanner_init():
    bot = MagicMock()
    neuro_manager = MagicMock(spec=NeuroManager)

    scanner = NeuroScanner(bot, neuro_manager)

    assert scanner.bot == bot
    assert scanner.neuro == neuro_manager
    assert scanner.client is not None
    assert scanner.client.timeout.read == 30.0

    # Dubsite scanner does not have close() method based on the code shown before
