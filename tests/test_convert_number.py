import unittest
from japanese_translator import convert_number

class TestConvertNumber(unittest.TestCase):
    def test_single_digits(self):
        self.assertEqual(convert_number("0"), "零")
        self.assertEqual(convert_number("1"), "一")
        self.assertEqual(convert_number("5"), "五")
        self.assertEqual(convert_number("9"), "九")

    def test_tens(self):
        self.assertEqual(convert_number("10"), "十")
        self.assertEqual(convert_number("11"), "十一")
        self.assertEqual(convert_number("20"), "二十")
        self.assertEqual(convert_number("21"), "二十一")

    def test_hundreds(self):
        self.assertEqual(convert_number("100"), "百")
        self.assertEqual(convert_number("101"), "百一")
        self.assertEqual(convert_number("111"), "百十一")
        self.assertEqual(convert_number("300"), "三百")

    def test_thousands(self):
        self.assertEqual(convert_number("1000"), "千")
        self.assertEqual(convert_number("1001"), "千一")
        self.assertEqual(convert_number("1111"), "千百十一")
        self.assertEqual(convert_number("3000"), "三千")

    def test_large_numbers(self):
        self.assertEqual(convert_number("10000"), "万")
        self.assertEqual(convert_number("10001"), "万一")
        self.assertEqual(convert_number("11111"), "万千百十一")
        self.assertEqual(convert_number("30000"), "三万")
        self.assertEqual(convert_number("100000"), "十万")
        self.assertEqual(convert_number("1000000"), "百万")
        self.assertEqual(convert_number("10000000"), "千万")
        self.assertEqual(convert_number("100000000"), "億")
        self.assertEqual(convert_number("1000000000"), "十億")
        self.assertEqual(convert_number("1000000000000"), "兆")


    def test_edge_cases(self):
        # Exceeds 10**16 - returns string
        self.assertEqual(convert_number("10000000000000000"), "10000000000000000")

        # Invalid number format - returns original string
        self.assertEqual(convert_number("abc"), "abc")
        self.assertEqual(convert_number("12.34"), "12.34")
        self.assertEqual(convert_number(""), "")

if __name__ == '__main__':
    unittest.main()
