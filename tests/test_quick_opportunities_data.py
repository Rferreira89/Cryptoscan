import tempfile
import unittest
from pathlib import Path

from engine import quick_opportunities_data as D


def kline(ts, close="101"):
    return [ts, "100", "102", "99", close, "10", ts + 1799999,
            "1000", 50, "5", "500", "0"]


class QuickOpportunitiesDataTests(unittest.TestCase):
    def test_paginates_and_deduplicates_in_timestamp_order(self):
        step = 30 * 60 * 1000
        calls = []
        original_limit = D.PAGE_LIMIT
        D.PAGE_LIMIT = 2
        def fake_request(url, params):
            calls.append(params["startTime"])
            if len(calls) == 1:
                return [kline(0), kline(step)]
            return [kline(step), kline(2 * step)]
        try:
            rows = D.fetch_binance_history(
                "BTCUSDT", 0, 3 * step, request=fake_request,
                pause_seconds=0)
        finally:
            D.PAGE_LIMIT = original_limit
        self.assertEqual([r["t"] for r in rows], [0, 1800, 3600])
        self.assertEqual(calls, [0, 2 * step])

    def test_historical_backtest_validates_against_requested_end(self):
        step = 30 * 60 * 1000
        history = [kline(i * step) for i in range(80)]
        with tempfile.TemporaryDirectory() as tmp:
            report = D.run_symbol(
                "BTCUSDT", 0, 80 * step, tmp,
                request=lambda *_: history, fee_pct=0, slippage_pct=0)
            self.assertEqual(report["validation"]["status"], "VALID")
            self.assertEqual(report["candles"], 80)
            self.assertTrue((Path(tmp) / "BTCUSDT_30m.json").exists())
            self.assertTrue((Path(tmp) / "BTCUSDT_report.json").exists())

    def test_rejects_unaligned_range(self):
        with self.assertRaises(ValueError):
            D.fetch_binance_history("BTCUSDT", 1, 1800000,
                                    request=lambda *_: [])

    def test_rejects_non_usdt_symbol(self):
        with self.assertRaises(ValueError):
            D.fetch_binance_history("BTCUSDC", 0, 1800000,
                                    request=lambda *_: [])


if __name__ == "__main__":
    unittest.main()
