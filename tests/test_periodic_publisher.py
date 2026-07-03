import unittest
from periodic_publisher import build_stats_media_groups

class TestBuildStatsMediaGroups(unittest.TestCase):
    def test_empty_dict(self):
        self.assertEqual(build_stats_media_groups({}), [])
        self.assertEqual(build_stats_media_groups(None), [])

    def test_less_than_10_items(self):
        stats_data = {f"key{i}": i for i in range(5)}
        result = build_stats_media_groups(stats_data)

        self.assertEqual(len(result), 1)
        self.assertEqual(len(result[0]), 5)
        self.assertEqual(result[0][0], ('key0', 0))

    def test_exactly_10_items(self):
        stats_data = {f"key{i}": i for i in range(10)}
        result = build_stats_media_groups(stats_data)

        self.assertEqual(len(result), 1)
        self.assertEqual(len(result[0]), 10)
        self.assertEqual(result[0][9], ('key9', 9))

    def test_more_than_10_items(self):
        stats_data = {f"key{i}": i for i in range(25)}
        result = build_stats_media_groups(stats_data)

        self.assertEqual(len(result), 3)
        self.assertEqual(len(result[0]), 10)
        self.assertEqual(len(result[1]), 10)
        self.assertEqual(len(result[2]), 5)

if __name__ == '__main__':
    unittest.main()
