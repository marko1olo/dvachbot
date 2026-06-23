import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from security_status import add_blocker

class TestSecurityStatus(unittest.TestCase):
    def test_add_blocker_positive_count(self):
        blockers = []
        add_blocker(blockers, "code1", 1, "detail1")
        self.assertEqual(len(blockers), 1)
        self.assertEqual(blockers[0], {"code": "code1", "count": 1, "detail": "detail1"})

    def test_add_blocker_zero_count(self):
        blockers = []
        add_blocker(blockers, "code2", 0, "detail2")
        self.assertEqual(len(blockers), 0)

    def test_add_blocker_negative_count(self):
        blockers = []
        add_blocker(blockers, "code3", -1, "detail3")
        self.assertEqual(len(blockers), 0)

    def test_add_blocker_existing_list(self):
        blockers = [{"code": "existing", "count": 5, "detail": "existing_detail"}]
        add_blocker(blockers, "code4", 2, "detail4")
        self.assertEqual(len(blockers), 2)
        self.assertEqual(blockers[0], {"code": "existing", "count": 5, "detail": "existing_detail"})
        self.assertEqual(blockers[1], {"code": "code4", "count": 2, "detail": "detail4"})

if __name__ == '__main__':
    unittest.main()
