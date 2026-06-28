import unittest
from Dubsite_tgach.image_processing import clean_tags_string

class TestCleanTagsString(unittest.TestCase):

    def test_none_input(self):
        self.assertIsNone(clean_tags_string(None))

    def test_empty_string(self):
        self.assertIsNone(clean_tags_string(""))
        self.assertIsNone(clean_tags_string("   "))

    def test_normal_string_extra_spaces(self):
        self.assertEqual(clean_tags_string("tag1,  tag2,   tag3"), "tag1, tag2, tag3")
        self.assertEqual(clean_tags_string("  tag1, tag2  "), "tag1, tag2")

    def test_multiple_commas(self):
        self.assertEqual(clean_tags_string("tag1,,tag2"), "tag1,tag2")
        self.assertEqual(clean_tags_string("tag1, ,tag2"), "tag1,tag2")
        self.assertEqual(clean_tags_string("tag1, , ,tag2"), "tag1,tag2")
        self.assertEqual(clean_tags_string("tag1,,,tag2"), "tag1,tag2")
        self.assertEqual(clean_tags_string("tag1, , ,, ,tag2"), "tag1,tag2")

if __name__ == '__main__':
    unittest.main()
