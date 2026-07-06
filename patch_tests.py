import re

with open("tests/test_get_country_by_ip.py", "r") as f:
    code = f.read()

# Make sure to mock AsyncHTTPTransport correctly
# We need to add mock_transport to the test parameters
code = re.sub(
    r"@patch\('Dubsite_tgach.main.AsyncHTTPTransport'\)\n    async def test_geoip_reader_raises_exception\(self, mock_transport, mock_geoip_reader\):",
    r"async def test_geoip_reader_raises_exception(self, mock_geoip_reader):",
    code
)

code = re.sub(
    r"@patch\('Dubsite_tgach.main.AsyncHTTPTransport'\)\n    async def test_httpx_raises_exception_both_strategies\(self, mock_transport, mock_geoip_reader\):",
    r"async def test_httpx_raises_exception_both_strategies(self, mock_geoip_reader):",
    code
)

code = re.sub(
    r"@patch\('Dubsite_tgach.main.AsyncHTTPTransport'\)\n    async def test_httpx_first_strategy_fails_second_succeeds\(self, mock_transport, mock_geoip_reader\):",
    r"async def test_httpx_first_strategy_fails_second_succeeds(self, mock_geoip_reader):",
    code
)

with open("tests/test_get_country_by_ip.py", "w") as f:
    f.write(code)
