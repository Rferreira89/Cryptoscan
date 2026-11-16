import tempfile
import unittest
from pathlib import Path

from engine import quick_opportunities_data as D


def kline(ts, close="101"):
    return [ts, "100", "102", "99", close, "10", ts + 1799999,
            "1000", 50, "5", "500", "0"]


def bybit_kline(ts, close="101"):
    return [str(ts), "100", "102", "99", close, "10", "1000"]


def okx_kline(ts, close="101", confirm="1"):
    return [str(ts), "100", "102", "99", close, "10", "10", "1000", confirm]


class QuickOpportunitiesDataTests(unittest.TestCase):
    def test_binance_paginates_and_deduplicates(self):
        step = 30 * 60 * 1000
        calls = []
        original = D.PAGE_LIMITS["binance"]
        D.PAGE_LIMITS["binance"] = 2
        def fake_request(url, params):
            calls.append(params["startTime"])
            if len(calls) == 1:
                return [kline(0), kline(step)]
            return [kline(step), kline(2 * step)]
        try:
            rows = D.fetch_binance_history("BTCUSDT", 0, 3 * step,
                                           request=fake_request, pause_seconds=0)
        finally:
            D.PAGE_LIMITS["binance"] = original
        self.assertEqual([r["t"] for r in rows], [0, 1800, 3600])
        self.assertEqual(calls, [0, 2 * step])

    def test_bybit_paginates_30m_spot_klines(self):
        step = 30 * 60 * 1000
        calls = []
        original = D.PAGE_LIMITS["bybit"]
        D.PAGE_LIMITS["bybit"] = 2
        def fake_request(url, params):
            calls.append(params)
            batch = [bybit_kline(0), bybit_kline(step)] if len(calls) == 1 else [
                bybit_kline(step), bybit_kline(2 * step)]
            return {"retCode": 0, "result": {"list": batch}}
        try:
            rows = D.fetch_bybit_history("BTCUSDT", 0, 3 * step,
                                         request=fake_request, pause_seconds=0)
        finally:
            D.PAGE_LIMITS["bybit"] = original
        self.assertEqual([r["t"] for r in rows], [0, 1800, 3600])
        self.assertEqual(calls[0]["category"], "spot")
        self.assertEqual(calls[0]["interval"], "30")

    def test_okx_pages_backwards_and_excludes_unconfirmed_candle(self):
        step = 30 * 60 * 1000
        calls = []
        original = D.PAGE_LIMITS["okx"]
        D.PAGE_LIMITS["okx"] = 2
        def fake_request(url, params):
            calls.append(params)
            batch = [okx_kline(2 * step), okx_kline(step)] if len(calls) == 1 else [
                okx_kline(step), okx_kline(0, confirm="0")]
            return {"code": "0", "data": batch}
        try:
            rows = D.fetch_okx_history("BTCUSDT", 0, 3 * step,
                                       request=fake_request, pause_seconds=0)
        finally:
            D.PAGE_LIMITS["okx"] = original
        self.assertEqual([r["t"] for r in rows], [1800, 3600])
        self.assertEqual(calls[0]["instId"], "BTC-USDT")
        self.assertEqual(calls[0]["bar"], "30m")
        self.assertEqual(int(calls[1]["after"]), step)

    def test_historical_run_saves_venue_specific_report(self):
        step = 30 * 60 * 1000
        history = [kline(i * step) for i in range(80)]
        with tempfile.TemporaryDirectory() as tmp:
            report = D.run_symbol(
                "BTCUSDT", 0, 80 * step, tmp, venue="binance",
                request=lambda *_: history, fee_pct=0, slippage_pct=0)
            self.assertEqual(report["validation"]["status"], "VALID")
            self.assertEqual(report["candles"], 80)
            self.assertEqual(report["venue"], "binance")
            self.assertTrue((Path(tmp) / "binance_BTCUSDT_30m.json").exists())
            self.assertTrue((Path(tmp) / "binance_BTCUSDT_report.json").exists())

    def test_rejects_unaligned_range(self):
        with self.assertRaises(ValueError):
            D.fetch_binance_history("BTCUSDT", 1, 1800000,
                                    request=lambda *_: [])

    def test_rejects_non_usdt_symbol(self):
        with self.assertRaises(ValueError):
            D.fetch_bybit_history("BTCUSDC", 0, 1800000,
                                  request=lambda *_: {})

    def test_unknown_venue_is_rejected(self):
        with self.assertRaises(ValueError):
            D.fetch_history("unknown", "BTCUSDT", 0, 1800000)


if __name__ == "__main__":
    unittest.main()
