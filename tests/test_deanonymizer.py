import unittest
from deanonymizer import generate_deanon_info, _generate_housing_report

class TestDeanonymizer(unittest.TestCase):
    def test_generate_deanon_info_runs_ru(self):
        result = generate_deanon_info(lang='ru')
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 10)

    def test_generate_deanon_info_runs_en(self):
        result = generate_deanon_info(lang='en')
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 10)
        self.assertIn("[DEANONYMIZATION REPORT]", result)

if __name__ == '__main__':
    unittest.main()
