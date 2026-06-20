import unittest

class TestDeanonymizer(unittest.TestCase):
    def test_import(self):
        try:
            import deanonymizer
            self.assertTrue(True)
        except Exception as e:
            self.fail(f"Import failed: {e}")

if __name__ == '__main__':
    unittest.main()
