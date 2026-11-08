"""Tests for the paper-only BTC SMA50 short regime gate."""

import unittest
from datetime import datetime, timedelta, timezone

from tools.research_short_sma50 import (
    DailyBar,
    aggregate_4h_to_daily,
    approve_existing_short_candidate,
)


class TestShortSMA50Research(unittest.TestCase):

    def test_rejects_when_no_existing_short_signal(self):
        result = approve_existing_short_candidate(
            False,
            [],
            [],
        )

        self.assertFalse(result.approved)
        self.assertEqual(
            result.reason,
            "no_existing_short_candidate",
        )

    def test_rejects_insufficient_history(self):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)

        btc = []
        asset = []

        for index in range(40):
            timestamp = start + timedelta(days=index)

            btc.append(
                DailyBar(timestamp, 100, 101, 99, 100)
            )
            asset.append(
                DailyBar(timestamp, 50, 51, 49, 50)
            )

        result = approve_existing_short_candidate(
            True,
            btc,
            asset,
        )

        self.assertFalse(result.approved)
        self.assertEqual(
            result.reason,
            "insufficient_aligned_history",
        )

    def test_discards_incomplete_4h_day(self):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        bars = []

        for hour in (0, 4, 8, 12, 16):
            bars.append(
                DailyBar(
                    start + timedelta(hours=hour),
                    100,
                    105,
                    95,
                    100 + hour,
                )
            )

        result = aggregate_4h_to_daily(
            bars,
            as_of=start + timedelta(days=1),
        )

        self.assertEqual(result, [])

    def test_aggregates_complete_4h_day(self):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        bars = []

        for hour in (0, 4, 8, 12, 16, 20):
            bars.append(
                DailyBar(
                    start + timedelta(hours=hour),
                    100 + hour,
                    110 + hour,
                    90 + hour,
                    101 + hour,
                    10,
                )
            )

        result = aggregate_4h_to_daily(
            bars,
            as_of=start + timedelta(days=1),
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].open, 100)
        self.assertEqual(result[0].close, 121)
        self.assertEqual(result[0].high, 130)
        self.assertEqual(result[0].low, 90)
        self.assertEqual(result[0].volume, 60)


if __name__ == "__main__":
    unittest.main()
