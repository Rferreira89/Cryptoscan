import unittest

from engine import config, risk

CFG = dict(config.DEFAULTS, capital_usdc=50.0, fixed_position_usdc=25.0,
           max_risk_usdc=1.0, swing_leverage=2.0, min_order_usdc=5.0)


def size(stop_pct, **over):
    return risk.sizing(stop_pct, stop_pct / 100, 100.0, dict(CFG, **over))


class RiskCapSizing(unittest.TestCase):
    def test_tight_stop_keeps_full_position(self):
        sz, why = size(1.5)
        self.assertIsNone(why)
        self.assertEqual(sz["usdc"]["position_usdc"], 25.0)
        self.assertEqual(sz["usdc"]["risk_usdc"], 0.38)

    def test_wide_stop_shrinks_position_to_risk_cap(self):
        sz, why = size(6.67)                       # o caso da TIA
        self.assertIsNone(why)
        self.assertAlmostEqual(sz["usdc"]["position_usdc"], 14.99, places=2)
        self.assertEqual(sz["usdc"]["risk_usdc"], 1.0)
        self.assertEqual(sz["partials"], [50, 50, 0])   # partes >= 5 USDC

    def test_risk_never_exceeds_cap(self):
        for sp in (0.5, 1, 2, 3.9, 4.0, 4.1, 5, 8, 12, 15, 18, 19.9):
            sz, why = size(sp)
            self.assertIsNone(why, sp)
            pos = sz["usdc"]["position_usdc"]
            self.assertLessEqual(pos, 25.0)
            self.assertLessEqual(pos * sp / 100, 1.0 + 0.001, sp)   # arredondamento ao centimo

    def test_below_min_order_is_refused_not_rounded_up(self):
        sz, why = size(21.0)                       # 4.76 USDC: nao arredonda
        self.assertIsNone(sz)
        self.assertIn("ordem mínima", why)

    def test_cap_of_two_usdc(self):
        sz, _ = size(6.67, max_risk_usdc=2.0)
        self.assertEqual(sz["usdc"]["position_usdc"], 25.0)

    def test_collateral_and_borrowed_follow_position(self):
        sz, _ = size(8.0)
        u = sz["usdc"]
        self.assertAlmostEqual(u["collateral_usdc"] + u["borrowed_usdc"],
                               u["position_usdc"], places=2)


if __name__ == "__main__":
    unittest.main()
