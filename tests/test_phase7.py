import unittest

from engine import config, ledger, reports, risk, signals

CFG = dict(config.DEFAULTS, swing_leverage=1.0, max_open_positions=4,
           unvalidated_risk_pct=0.5,
           fixed_position_usdc=None)   # valores de base fixos para os testes
PLAN = {"entry_zone": [99.7, 100.0], "stop": 98.0, "tp": [104.0, 108.0, 112.0],
        "rr": 2.4, "risk_pct": 0.5, "position_pct": 20.0}
SIG = {"asset": "LINK", "pair": "LINK/USDC", "strategy": "PULLBACK",
       "mode": "REAL", "score": 70, "plan": PLAN}


def issued(i, t):
    return {"t": t, "event": "ISSUED", "id": i, "signal": dict(SIG)}


class Ledger(unittest.TestCase):
    def test_full_life_of_a_winner_and_a_loser(self):
        st = {}
        ledger.apply(st, [issued("a", 10), issued("b", 11), issued("c", 12)])
        ledger.apply(st, [{"t": 20, "event": "TRIGGERED", "id": "a", "price": 99.9},
                          {"t": 21, "event": "TRIGGERED", "id": "b", "price": 100.0},
                          {"t": 22, "event": "EXPIRED", "id": "c", "reason": "x"}])
        ledger.apply(st, [{"t": 30, "event": "TP1", "id": "a", "price": 104.0,
                           "sold_pct": 50}])
        self.assertEqual(st["ledger"][0]["tp_hit"], 1)
        ledger.apply(st, [{"t": 40, "event": "TP2", "id": "a", "price": 108.0},
                          {"t": 41, "event": "TP3", "id": "a", "price": 112.0,
                           "r": 2.9},
                          {"t": 42, "event": "STOP", "id": "b", "price": 98.0,
                           "r": -1.0}])
        a, b, c = st["ledger"]
        self.assertEqual((a["status"], a["result_r"], a["tp_hit"], a["reason"]),
                         ("CLOSED", 2.9, 3, "TP3"))
        self.assertEqual((b["status"], b["result_r"]), ("CLOSED", -1.0))
        self.assertEqual(c["status"], "CANCELLED")
        s = ledger.summary(st["ledger"])
        self.assertEqual((s["closed"], s["cancelled"], s["win_rate"]), (2, 1, 50.0))
        self.assertEqual(s["total_r"], 1.9)
        self.assertAlmostEqual(s["capital_pct"], 0.95)      # 1.9R x 0.5%
        self.assertEqual(s["curve"], [[41, 2.9], [42, 1.9]])
        self.assertEqual(s["max_drawdown_r"], 1.0)
        self.assertEqual(s["by_strategy"]["PULLBACK"]["n"], 2)

    def test_daily_trend_and_unknown_ids(self):
        st = {}
        ledger.apply(st, [{"t": 5, "event": "PAPER_BUY", "id": "paper-BTC",
                           "asset": "BTC", "pair": "BTC/USDC", "price": 100.0,
                           "stop": 90.0, "position_pct": 5.0, "risk_pct": 0.5,
                           "real": True},
                          {"t": 6, "event": "TP1", "id": "nope", "price": 1},
                          {"t": 7, "event": "MARKET_FILTER", "id": "market"}])
        self.assertEqual(st["ledger"][0]["status"], "OPEN")
        ledger.apply(st, [{"t": 9, "event": "PAPER_SELL", "id": "paper-BTC",
                           "asset": "BTC", "pair": "BTC/USDC", "price": 120.0,
                           "r": 1.9, "reason": "TRAIL"}])
        self.assertEqual(st["ledger"][0]["result_r"], 1.9)
        self.assertEqual(ledger.summary([])["closed"], 0)

    def test_paper_excluded_from_real_summary(self):
        st = {}
        e = issued("p", 1)
        e["signal"]["mode"] = "PAPER"
        ledger.apply(st, [e, {"t": 2, "event": "TRIGGERED", "id": "p", "price": 100},
                          {"t": 3, "event": "STOP", "id": "p", "price": 98, "r": -1}])
        self.assertEqual(ledger.summary(st["ledger"])["closed"], 0)


class Leverage(unittest.TestCase):
    def plan(self, stop, lev):
        from tests.test_phase4 import a4h, a1d
        return risk.plan({"strategy": "X", "entry": [99.7, 100.0], "stop": stop},
                         a4h(), a1d(), dict(CFG, swing_leverage=lev))[0]

    def test_no_leverage_is_unchanged(self):
        p = self.plan(98.0, 1.0)
        self.assertEqual(p["leverage"]["use"], 1.0)
        self.assertIsNone(p["leverage"]["liquidation_est"])
        self.assertEqual(p["leverage"]["borrowed_pct"], 0.0)
        self.assertLessEqual(p["position_pct"], CFG["max_position_pct"])

    def test_leverage_scales_position_and_risk_within_bounds(self):
        base, lev = self.plan(98.0, 1.0), self.plan(98.0, 2.0)
        self.assertEqual(lev["leverage"]["use"], 2.0)
        self.assertAlmostEqual(lev["position_pct"], 2 * base["position_pct"], places=1)
        self.assertAlmostEqual(lev["risk_pct"], 2 * base["risk_pct"], places=2)
        # capital proprio em jogo nunca passa o teto por posicao
        self.assertLessEqual(lev["leverage"]["collateral_pct"],
                             CFG["max_position_pct"] + 1e-9)
        self.assertAlmostEqual(lev["leverage"]["collateral_pct"]
                               + lev["leverage"]["borrowed_pct"],
                               lev["position_pct"], places=1)
        # risco por operacao nunca passa risco base x alavancagem
        for stop in (99.1, 98.0, 97.0, 96.5):
            p = self.plan(stop, 3.0)
            if p:
                self.assertLessEqual(p["risk_pct"],
                                     CFG["risk_pct"] * p["leverage"]["use"] + 0.01)

    def test_liquidation_stays_far_from_stop(self):
        for sf in (0.01, 0.03, 0.05, 0.08, 0.12, 0.2, 0.35):
            lv = risk.leverage_for(sf, dict(CFG, swing_leverage=10.0))
            self.assertTrue(1.0 <= lv["use"] <= lv["max_safe"] <= 10.0)
            if lv["use"] > 1:
                liq_dist = 1 / lv["use"] - risk.MMR
                self.assertGreaterEqual(liq_dist, 2.5 * sf - 1e-9)
        # stop muito largo: sem margem
        self.assertEqual(risk.leverage_for(0.35, dict(CFG, swing_leverage=3.0))["use"], 1.0)

    def test_config_bounds_and_backtest_ignores_leverage(self):
        import json, os, tempfile
        d = tempfile.mkdtemp()
        f = os.path.join(d, "c.json")
        json.dump({"swing_leverage": 11}, open(f, "w"))
        with self.assertRaises(ValueError):
            config.load(f)
        self.assertEqual(config.load("nao-existe.json")["swing_leverage"], 10.0)

    def test_alert_lines(self):
        from engine import run
        t = run.invest_line(20.0, 0.5, {"use": 1.0, "reason": "sem margem: x"})
        self.assertIn("Alavancagem: 1x (sem margem) — sem margem: x", t)
        self.assertIn("Investir: 20.0% do capital (risco 0.5%)", t)
        t = run.invest_line(40.0, 1.0, {"use": 2.0, "collateral_pct": 20.0,
                                        "liquidation_est": 55.0,
                                        "reason": "condições normais"})
        for part in ("Alavancagem: 2x — condições normais", "40.0%",
                     "20.0% teus", "risco 1.0%", "55"):
            self.assertIn(part, t)

    def test_per_operation_leverage_only_goes_down(self):
        f = signals.operation_leverage
        cfg = dict(CFG, swing_leverage=2.0)
        plan = {"leverage": {"use": 2.0}}
        bull = {"regime": "BULL", "high_volatility": False}
        ok = {"conflicts": []}
        a1 = {"atr_pctile": 50}
        self.assertEqual(f(cfg, plan, ok, bull, a1, "BULL", False)[0], 2.0)
        self.assertEqual(f(cfg, plan, {"conflicts": ["x"]}, bull, a1, "BULL", False)[0], 1.0)
        self.assertEqual(f(cfg, plan, ok, bull, {"atr_pctile": 95}, "BULL", False)[0], 1.0)
        self.assertEqual(f(cfg, plan, ok, {"regime": "NEUTRAL",
                                            "high_volatility": False}, a1, "BULL", False)[0], 1.0)
        self.assertEqual(f(cfg, plan, ok, bull, a1, "NEUTRAL", False)[0], 1.5)
        self.assertEqual(f(cfg, plan, ok, bull, a1, "NEUTRAL", True)[0], 2.0)   # o proprio BTC
        self.assertEqual(f(cfg, {"leverage": {"use": 1.5}}, ok, bull, a1, "BULL", False)[0], 1.5)
        self.assertEqual(f(CFG, {"leverage": {"use": 1.0}}, ok, bull, a1, "BULL", False)[0], 1.0)
        for args in ((cfg, plan, ok, bull, a1, "BULL", False),
                     (cfg, plan, {"conflicts": ["x"]}, bull, a1, "BEAR", False)):
            lev, why = f(*args)
            self.assertLessEqual(lev, cfg["swing_leverage"])
            self.assertTrue(why)

    def test_decision_carries_leverage_and_reason(self):
        from tests import test_phase4 as T4
        from engine import validation
        orig = validation.load
        validation.load = lambda: None
        self.addCleanup(lambda: setattr(validation, "load", orig))
        cfg = dict(CFG, swing_leverage=2.0)
        d = signals.decide(T4.row(), T4.C4, cfg, T4.V, "BULL", False)
        lv = d["plan"]["leverage"]
        self.assertEqual((lv["use"], d["plan"]["risk_pct"] <= 1.0 + 1e-9), (2.0, True))
        self.assertIn("normais", lv["reason"])
        r = T4.row()
        r["analysis"]["mtf_conflict"] = "1D: médias e estrutura discordam"
        d = signals.decide(r, T4.C4, cfg, T4.V, "BULL", False)
        self.assertEqual(d["plan"]["leverage"]["use"], 1.0)
        self.assertLessEqual(d["plan"]["risk_pct"], 0.5 + 1e-9)
        self.assertIn("conflito", d["plan"]["leverage"]["reason"])


def series(vals, t0=0):
    return [{"t": t0 + k * 86400, "c": v} for k, v in enumerate(vals)]


class Correlation(unittest.TestCase):
    def test_values(self):
        import random
        rnd = random.Random(1)
        a = [100.0]
        for _ in range(70):
            a.append(a[-1] * (1 + rnd.gauss(0, 0.03)))
        same = [x * 2 for x in a]
        inv = [100.0]
        for k in range(1, len(a)):
            inv.append(inv[-1] * (2 - a[k] / a[k - 1]))
        c = signals.correlation
        self.assertAlmostEqual(c(series(a), series(same)), 1.0, places=6)
        self.assertLess(c(series(a), series(inv)), -0.99)
        self.assertIsNone(c(series(a[:10]), series(same[:10])))
        self.assertIsNone(c(None, series(a)))

    def test_blocks_third_correlated_position(self):
        from tests import test_phase4 as T4
        from engine import validation
        orig = validation.load
        validation.load = lambda: None
        self.addCleanup(lambda: setattr(validation, "load", orig))
        import random
        rnd = random.Random(2)
        base = [100.0]
        for _ in range(70):
            base.append(base[-1] * (1 + rnd.gauss(0, 0.03)))
        daily = {f"A{k}": series([x * (k + 1) for x in base]) for k in range(4)}
        rows = []
        for k in range(4):
            r = T4.row(asset=f"A{k}")
            r["decision"] = signals.decide(r, T4.C4, CFG, T4.V, "BULL", False)
            rows.append(r)
        state = {}
        ev = signals.update_state(state, rows, CFG, 1_800_000_000, daily)
        self.assertEqual(len([e for e in ev if e["event"] == "ISSUED"]), 2)
        self.assertIn("correlacionada", rows[2]["decision"]["reason"])


RES = {"status_global": "OK", "sources": {"binance": {"ok": True}},
       "venue_source": {"ok": True}, "halt": None,
       "market_filter": {"btc_above_sma200": True, "distance_pct": 18.9},
       "market_regime": {"btc": "STRONG BULL"},
       "counts": {"deep_checked": 40, "long": 0, "watchlist": 1},
       "universe": [{"asset": "AAVE", "decision": {
           "decision": "WATCHLIST", "plan": {"rr": 2}, "score": 58,
           "strategy": "BREAKOUT", "reason": "reteste de 176-178"}}]}


class Reports(unittest.TestCase):
    def ts(self, y, m, d, h):
        import datetime
        return int(datetime.datetime(y, m, d, h, 0, tzinfo=reports.TZ).timestamp())

    def test_daily_once_after_8_lisbon_and_weekly_on_monday(self):
        st = {}
        self.assertEqual(reports.due(RES, st, self.ts(2026, 10, 3, 7)), [])
        out = reports.due(RES, st, self.ts(2026, 10, 3, 8))        # sabado
        self.assertEqual([k for k, _ in out], ["daily"])
        self.assertIn("AAVE", out[0][1])
        self.assertIn("acima", out[0][1])
        self.assertEqual(reports.due(RES, st, self.ts(2026, 10, 3, 12)), [])
        out = reports.due(RES, st, self.ts(2026, 10, 5, 9))        # segunda
        self.assertEqual([k for k, _ in out], ["daily", "weekly"])
        self.assertIn("Nenhuma operação fechada", out[1][1])

    def test_health_alert_only_on_change(self):
        st = {"reports": {"daily": "x"}}
        t = self.ts(2026, 10, 3, 3)
        bad = dict(RES, status_global="DEGRADED",
                   sources={"binance": {"ok": False, "error": "x"}})
        out = reports.due(bad, st, t)
        self.assertEqual(out[0][0], "health")
        self.assertIn("binance", out[0][1])
        self.assertEqual(reports.due(bad, st, t + 900), [])
        self.assertIn("recuperado", reports.due(RES, st, t + 1800)[0][1])


if __name__ == "__main__":
    unittest.main()
