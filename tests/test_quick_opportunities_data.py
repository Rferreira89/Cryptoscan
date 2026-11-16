import unittest

from engine.quick_opportunities_data import fetch_binance_history


def kline(ts, close="101"):
    return [ts, "100", "102", "99", close, "10", ts + 1799999,
            "1000", 50, "5", "500", "0"]


class QuickOpportunitiesDataTests(unittest.TestCase):
    def test_paginates_and_deduplicates_in_timestamp_order(self):
        step = 30 * 60 * 1000
        calls = []
        def fake_request(url, params):
            calls.append(params["startTime"])
            if len(calls) == 1:
                return [kline(0), kline(step)]
            return [kline(step), kline(2 * step)]
        rows = fetch_binance_history("BTCUSDT", 0, 3 * step,
                                     request=fake_request, pause_seconds=0)
        self.assertEqual([r["t"] for r in rows], [0, 1800, 3600])
        self.assertEqual(calls, [0])

    def test_rejects_unaligned_range(self):
        with self.assertRaises(ValueError):
            fetch_binance_history("BTCUSDT", 1, 1800000,
                                  request=lambda *_: [])

    def test_rejects_non_usdt_symbol(self):
        with self.assertRaises(ValueError):
            fetch_binance_history("BTCUSDC", 0, 1800000,
                                  request=lambda *_: [])


if __name__ == "__main__":
    unittest.main()
