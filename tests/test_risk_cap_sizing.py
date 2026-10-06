import unittest

from engine import config, risk

CFG = dict(config.DEFAULTS, capital_usdc=50.0, fixed_position_usdc=25.0,
           max_risk_usdc=1.0, swing_leverage=1.0, min_order_usdc=5.0)


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


class LeveragedSizing(unittest.TestCase):
    """Margem propria de 25 USDC vezes a alavancagem, com o risco limitado."""
    C = dict(swing_leverage=6.0, max_risk_usdc=2.5)

    def test_tight_stop_uses_leverage_up_to_risk_cap(self):
        sz, _ = size(2.0, **self.C)             # 2.5 / 2% = 125 USDC = 5x
        u = sz["usdc"]
        self.assertAlmostEqual(u["position_usdc"], 125.0, places=2)
        self.assertEqual(sz["leverage"]["use"], 5.0)
        self.assertAlmostEqual(u["collateral_usdc"], 25.0, places=2)
        self.assertAlmostEqual(u["risk_usdc"], 2.5, places=2)

    def test_ceiling_of_six(self):
        sz, _ = size(0.5, **self.C)             # o risco deixaria 500 USDC
        self.assertEqual(sz["leverage"]["use"], 6.0)
        self.assertAlmostEqual(sz["usdc"]["position_usdc"], 150.0, places=2)

    def test_risk_and_liquidation_hold_for_every_stop(self):
        for sp in (0.5, 1, 2, 3, 4, 5, 6.67, 8, 12, 19):
            sz, why = size(sp, **self.C)
            self.assertIsNone(why, sp)
            u, lv = sz["usdc"], sz["leverage"]
            self.assertLessEqual(u["position_usdc"] * sp / 100, 2.5 + 0.001)
            self.assertLessEqual(u["collateral_usdc"], 25.0 + 0.3, sp)
            self.assertLessEqual(lv["use"], 6.0)
            if lv["use"] > 1:                   # liquidacao longe do stop
                self.assertGreaterEqual(1 / lv["use"] - risk.MMR,
                                        2.5 * sp / 100 - 1e-9, sp)


class RealFirstTarget(unittest.TestCase):
    def plan(self, **over):
        a = {"atr": 2.0, "liquidity": {"pools_above": over.pop("pools", [])}}
        return risk.plan({"strategy": "X", "entry": [99.7, 100.0], "stop": 97.0},
                         a, {"liquidity": {}}, dict(CFG, **over))

    def test_projected_first_target_is_refused(self):
        p, why = self.plan()
        self.assertIsNone(p)
        self.assertIn("1.º objetivo", why)

    def test_real_level_is_accepted_and_flag_can_be_off(self):
        p, why = self.plan(pools=[106.0])
        self.assertIsNone(why)
        self.assertNotIn(1, p["tp_projected"])
        p, why = self.plan(require_real_tp1=False)
        self.assertIsNone(why)
        self.assertIn(1, p["tp_projected"])


class StaleTrigger(unittest.TestCase):
    """Sinal pronto mas com o preco ja abaixo da zona: nao pode sair."""
    def test_price_below_zone_blocks_signal(self):
        from engine import signals, validation
        from tests import test_phase4 as T4
        orig = validation.load
        validation.load = lambda: None
        self.addCleanup(lambda: setattr(validation, "load", orig))
        cfg = dict(config.DEFAULTS, require_real_tp1=False)
        ok = signals.decide(T4.row(), T4.C4, cfg, T4.V, "BULL", False)
        self.assertIn("plan", ok)
        lo = ok["plan"]["entry_zone"][0]
        d = signals.decide(T4.row(price=lo * 0.97), T4.C4, cfg,
                           dict(T4.V, last=lo * 0.97), "BULL", False)
        self.assertEqual(d["decision"], "NO TRADE")
        self.assertIn("abaixo da zona", d["reason"])


class FirstTargetNotTooFar(unittest.TestCase):
    def plan(self, pool, **over):
        a = {"atr": 2.0, "liquidity": {"pools_above": [pool]}}
        return risk.plan({"strategy": "X", "entry": [99.7, 100.0], "stop": 97.0},
                         a, {"liquidity": {}}, dict(CFG, **over))

    def test_far_first_target_is_refused(self):
        p, why = self.plan(112.0, max_rr_tp1=2.5)  # cerca de 3.7R
        self.assertIsNone(p)
        self.assertIn("demasiado longe", why)

    def test_near_first_target_passes_and_limit_can_be_off(self):
        p, why = self.plan(106.0, max_rr_tp1=2.5)  # cerca de 1.8R
        self.assertIsNone(why)
        self.assertLessEqual(p["rr_tp1"], 2.5)
        p, why = self.plan(112.0, max_rr_tp1=None)
        self.assertIsNone(why)

    def test_live_config_has_the_limit(self):
        self.assertEqual(config.load("config.json")["max_rr_tp1"], 2.5)


class WickHitsStop(unittest.TestCase):
    """Um pavio abaixo do stop entre duas leituras fecha a operacao."""
    def state(self):
        from engine import trade
        plan = {"entry_zone": [99.7, 100.0], "entry_ref": 100.0, "stop": 97.0,
                "tp": [104.0, 108.0, 112.0], "partials": [50, 30, 20]}
        pos = trade.open_position(plan, 100.0, 0, 0.25)
        return {"signals": {"k": {"asset": "X", "status": "TRIGGERED",
                                  "direction": "LONG", "strategy": "PULLBACK",
                                  "plan": plan, "position": pos,
                                  "issued_at": 0, "expires_at": 9e9}}}

    def test_without_range_last_price_keeps_it_open(self):
        from engine import signals
        st = self.state()
        signals.track(st, {"X": 99.0}, CFG, 60)
        self.assertEqual(st["signals"]["k"]["status"], "TRIGGERED")

    def test_wick_below_stop_closes_it(self):
        from engine import signals
        st = self.state()
        ev = signals.track(st, {"X": 99.0}, CFG, 60, {"X": (96.5, 99.5)})
        self.assertEqual(st["signals"]["k"]["status"], "CLOSED")
        self.assertEqual(st["signals"]["k"]["close_reason"], "STOP")
        self.assertTrue(any(e["event"] == "STOP" for e in ev))

    def test_ranges_for_survives_failing_sources(self):
        from unittest import mock
        from engine import monitor, sources

        class Bad:
            def candles(self, *a, **k):
                raise sources.SourceError("x")

        class Good:
            def candles(self, *a, **k):
                return [{"t": 1000, "l": 9.0, "h": 11.0},
                        {"t": 1060, "l": 9.5, "h": 12.0}]
        with mock.patch.object(sources, "ALL", [Bad(), Good()]):
            self.assertEqual(monitor.ranges_for({"X": 1000}), {"X": (9.0, 12.0)})
            self.assertEqual(monitor.ranges_for({"X": 1060}), {"X": (9.5, 12.0)})
        with mock.patch.object(sources, "ALL", [Bad()]):
            self.assertEqual(monitor.ranges_for({"X": 1000}), {})

    def test_never_looks_before_the_entry(self):
        from engine import monitor
        st = self.state()
        st["signals"]["k"]["position"]["opened_at"] = 5000
        self.assertEqual(monitor.open_since(st, 5100), {"X": 5000})
        self.assertEqual(monitor.open_since(st, 9000), {"X": 9000 - 360})


class Compounding(unittest.TestCase):
    C = dict(config.DEFAULTS, compound=True, capital_usdc=83.0, stake_pct=30,
             risk_pct_of_capital=3)

    def led(self, r, t=200, executed=True):
        return [{"id": "a", "status": "CLOSED", "executed": executed,
                 "closed_at": t, "result_r": r, "risk_usdc": 2.5}]

    def test_start_is_the_base(self):
        from engine import scanner
        u = scanner.compounding(self.C, [], 100)
        self.assertEqual((u["capital_usdc"], u["fixed_position_usdc"],
                          u["max_risk_usdc"]), (83.0, 24.9, 2.49))

    def test_grows_with_gains_and_shrinks_with_losses(self):
        from engine import scanner
        up = scanner.compounding(self.C, self.led(4.0), 100)       # +10 USDC
        self.assertEqual(up["capital_usdc"], 93.0)
        self.assertGreater(up["fixed_position_usdc"], 24.9)
        dn = scanner.compounding(self.C, self.led(-4.0), 100)      # -10 USDC
        self.assertEqual(dn["capital_usdc"], 73.0)
        self.assertLess(dn["max_risk_usdc"], 2.49)

    def test_ignores_old_and_not_executed(self):
        from engine import scanner
        self.assertEqual(scanner.compounding(self.C, self.led(4.0, t=50), 100)
                         ["capital_usdc"], 83.0)
        self.assertEqual(scanner.compounding(
            self.C, self.led(4.0, executed=False), 100)["capital_usdc"], 83.0)

    def test_off_by_default(self):
        from engine import scanner
        self.assertEqual(scanner.compounding(config.DEFAULTS, self.led(4), 0), {})

    def test_live_config(self):
        c = config.load("config.json")
        self.assertTrue(c["compound"])
        self.assertEqual(c["capital_usdc"], 83)


class RangeDisabled(unittest.TestCase):
    def test_range_is_off_by_default_both_sides(self):
        c = config.load("nao-existe.json")
        self.assertEqual(set(c["disabled_strategies"]),
                         {"RANGE", "RANGE_SHORT"})

    def test_scanner_merges_config_list(self):
        import inspect
        from engine import scanner
        self.assertIn('cfg.get("disabled_strategies")',
                      inspect.getsource(scanner.run))


if __name__ == "__main__":
    unittest.main()
