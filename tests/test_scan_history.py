import unittest

from engine import run


class ScanHistory(unittest.TestCase):
    def test_appends_and_trims_to_seven_days(self):
        now = 2_000_000_000
        state = {"scan_times": [now - 8 * 86400, now - 600, now - 300]}
        self.assertEqual(run.record_scan(state, now),
                         [now - 600, now - 300, now])

    def test_starts_empty_and_ignores_duplicates_and_garbage(self):
        state = {}
        run.record_scan(state, 100)
        state["scan_times"].append("x")
        run.record_scan(state, 100)
        self.assertEqual(state["scan_times"], [100])


if __name__ == "__main__":
    unittest.main()
