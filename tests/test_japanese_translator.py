import unittest
from japanese_translator import _merge_negative_tags

class TestMergeNegativeTags(unittest.TestCase):
    def test_empty_input(self):
        """Test with no arguments."""
        self.assertEqual(_merge_negative_tags(), [])

    def test_single_group(self):
        """Test with a single group of tags without duplicates."""
        group = ["-shota", "-shotacon", "-boy"]
        self.assertEqual(_merge_negative_tags(group), ["-shota", "-shotacon", "-boy"])

    def test_multiple_groups_with_duplicates(self):
        """Test with multiple groups, ensuring duplicates are removed while maintaining order."""
        group1 = ["-shota", "-boy"]
        group2 = ["-boy", "-male", "-shota"]
        group3 = ["-explicit"]
        self.assertEqual(
            _merge_negative_tags(group1, group2, group3),
            ["-shota", "-boy", "-male", "-explicit"]
        )

    def test_normalization(self):
        """Test normalization: stripping, lowercasing, and replacing spaces with underscores."""
        group1 = ["  -Shota  ", "-BOY", "-Little Boy"]
        group2 = ["-shota", "-boy", "-little_boy"]

        self.assertEqual(
            _merge_negative_tags(group1, group2),
            ["-Shota", "-BOY", "-Little Boy"]
        )

    def test_ignores_empty(self):
        """Test ignoring empty, None, and whitespace-only tags."""
        group = ["-shota", "", None, "   ", "-boy"]
        self.assertEqual(_merge_negative_tags(group), ["-shota", "None", "-boy"])

        group2 = ["-shota", "", "   ", "-boy"]
        self.assertEqual(_merge_negative_tags(group2), ["-shota", "-boy"])

    def test_none_group(self):
        """Test when one of the groups is None."""
        group1 = ["-shota"]
        self.assertEqual(_merge_negative_tags(group1, None, ["-boy"]), ["-shota", "-boy"])

if __name__ == '__main__':
    unittest.main()
