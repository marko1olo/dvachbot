import unittest
from unittest.mock import patch, MagicMock
import httpx
import asyncio

# Need to mock env vars and aiosqlite before importing site_tgach.importer
import os
os.environ["SECRET_KEY"] = "mock_secret"

# We will just write a test that inspects the file using AST to ensure the fix is present.
import ast

class TestImporterIPv4Fix(unittest.TestCase):
    def test_importer_has_local_address_0_0_0_0(self):
        with open('site_tgach/importer.py', 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read())

        found_local_address = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute) and node.func.attr == 'AsyncHTTPTransport':
                    for kw in node.keywords:
                        if kw.arg == 'local_address' and isinstance(kw.value, ast.Constant) and kw.value.value == '0.0.0.0':
                            found_local_address = True

        self.assertTrue(found_local_address, "AsyncHTTPTransport must be initialized with local_address='0.0.0.0' for OpenVPN compatibility")

if __name__ == '__main__':
    unittest.main()
