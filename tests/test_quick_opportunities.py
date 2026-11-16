import unittest

from engine import quick_opportunities as Q
from engine import sources as S


def candles(n=80, price=100.0, step=0.0, volume=100.0):
    out = []
    for i in range(n):
        c = price + i * step
        out.append({"t": i * Q.BAR_SECONDS, "o": c - 0.1, "h": c + 0.5,
                    "l": c - 0.5, "c": c, "v": volume, "tb": None})
    return out


class QuickOpportunitiesTests(unittest.TestCase):
    def test_all_public_adapters_expose_30m(self):
        self.assertEqual(S.TF_SECONDS["30m"], 1800)
        self.assertEqual(S.Bybit._tf["30m"], "30")
        self.assertEqual(S.OKX._tf["30m"], "30m")
        self.assertEqual(S.KuCoin._tf["30m"], "30min")

    def test_prepare_30m_drops_forming_candle(self):
        data = candles(80)
        now = data[-1]["t"] + Q.BAR_SECONDS + 10
        forming = dict(data[-1], t=now - (now % Q.BAR_SECONDS))
        data.append(forming)
        clean, report = Q.prepare_30m_candles(data, now)
        self.assertEqual(report["status"], "VALID")
        self.assertEqual(len(clean), 80)

    def test_regime_requires_enough_history(self):
        self.assertEqual(Q.classify_regime(candles(20)), "insufficient_data")

    def test_detect_returns_empty_for_short_history(self):
        self.assertEqual(Q.detect_opportunities(candles(30)), [])

    def test_candidates_are_long_or_short_and_have_four_hour_horizon(self):
        data = candles(80)
        data[-1].update({"o": 100.0, "h": 103.2, "l": 99.8,
                         "c": 103.0, "v": 250.0})
        found = Q.detect_opportunities(data, "TEST")
        self.assertTrue(found)
        self.assertIn("volume_breakout", [item["family"] for item in found])
        for item in found:
            self.assertIn(item["side"], ("LONG", "SHORT"))
            self.assertEqual(item["max_hold_bars"], 8)
            self.assertLessEqual(abs(item["target"] - item["signal_close"]),
                                 item["risk_per_unit"] * 2.01)

    def test_simulation_enters_only_next_bar_and_charges_costs(self):
        data = candles(10)
        data[1].update({"o": 100, "h": 100.5, "l": 99.5, "c": 100})
        candidate = {"side": "LONG", "family": "test", "stop": 98,
                     "target": 104}
        result = Q.simulate_candidate(data, 0, candidate, fee_pct=0.1,
                                      slippage_pct=0.05)
        self.assertEqual(result["status"], "CLOSED")
        self.assertEqual(result["entry_index"], 1)
        self.assertGreater(result["costs_r"], 0)
        self.assertAlmostEqual(result["net_r"], result["gross_r"] - result["costs_r"])

    def test_stop_wins_when_stop_and_target_hit_same_bar(self):
        data = candles(4)
        data[1].update({"o": 100, "h": 105, "l": 95, "c": 100})
        candidate = {"side": "LONG", "family": "test", "stop": 98,
                     "target": 104}
        result = Q.simulate_candidate(data, 0, candidate, fee_pct=0,
                                      slippage_pct=0)
        self.assertEqual(result["exit_reason"], "STOP")
        self.assertEqual(result["exit"], 98)

    def test_stop_gap_fills_at_worse_open_price(self):
        data = candles(4)
        data[1].update({"o": 96, "h": 97, "l": 95, "c": 96})
        result = Q.simulate_candidate(data, 0,
                                      {"side": "LONG", "stop": 98, "target": 104},
                                      fee_pct=0, slippage_pct=0)
        self.assertEqual(result["exit_reason"], "STOP")
        self.assertEqual(result["exit"], 96)

    def test_incomplete_horizon_is_not_counted_as_closed_trade(self):
        data = candles(4)
        result = Q.simulate_candidate(data, 0,
                                      {"side": "LONG", "stop": 90, "target": 120})
        self.assertEqual(result["status"], "OPEN_AT_END")

    def test_evaluation_uses_net_r_and_marks_small_samples(self):
        report = Q.evaluate_trades([{"status": "CLOSED", "net_r": 1.0},
                                    {"status": "CLOSED", "net_r": -0.5}],
                                   min_trades=100, bootstrap_samples=100)
        self.assertEqual(report["trades"], 2)
        self.assertFalse(report["adequate_sample"])
        self.assertAlmostEqual(report["mean_net_r"], 0.25)
        self.assertEqual(report["win_rate"], 0.5)
        self.assertEqual(report["max_drawdown_r"], 0.5)

    def test_invalid_side_is_rejected(self):
        result = Q.simulate_candidate(candles(3), 0,
                                      {"side": "FLAT", "stop": 99, "target": 101})
        self.assertEqual(result["status"], "INVALID_SIDE")


if __name__ == "__main__":
    unittest.main()
