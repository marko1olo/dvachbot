import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import unittest
from common.work_engine import WORK_VACANCIES, execute_job_action

class TestWorkEngine(unittest.TestCase):
    def test_all_vacancies_defined(self):
        self.assertGreaterEqual(len(WORK_VACANCIES), 9)
        for job_id, job in WORK_VACANCIES.items():
            self.assertIn("title", job)
            self.assertIn("reward_range", job)
            self.assertIn("cooldown_sec", job)
            self.assertIn("phrases", job)
            self.assertGreaterEqual(len(job["phrases"]), 8, f"Job {job_id} has too few phrases")

    def test_execute_job_action_success_and_cooldown(self):
        items = {}
        success, amount, msg, drop = execute_job_action("bottles", items)
        self.assertTrue(success)
        self.assertGreater(amount, 0)
        self.assertTrue(len(msg) > 0)
        self.assertIn("bottles", items.get("work_cooldowns", {}))

        # Test cooldown immediately after
        success_cd, amount_cd, msg_cd, drop_cd = execute_job_action("bottles", items)
        self.assertFalse(success_cd)
        self.assertEqual(amount_cd, 0)
        self.assertIn("⏳", msg_cd)

    def test_all_jobs_can_execute(self):
        for job_id in WORK_VACANCIES.keys():
            items = {}
            success, amount, msg, drop = execute_job_action(job_id, items)
            self.assertTrue(len(msg) > 0)
            self.assertGreaterEqual(amount, 0)

if __name__ == "__main__":
    unittest.main()
