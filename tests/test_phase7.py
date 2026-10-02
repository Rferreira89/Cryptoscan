import unittest

from engine import config, ledger, reports, risk, signals

CFG = dict(config.DEFAULTS)
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
    def test_never_needed_and_liquidation_beyond_stop(self):
        from tests.test_phase4 import a4h, a1d
        for stop in (99.1, 98.0, 97.0, 96.5):
            p, _ = risk.plan({"strategy": "X", "entry": [99.7, 100.0],
                              "stop": stop}, a4h(), a1d(), CFG)
            if not p:
                continue
            lv = p["leverage"]
            self.assertEqual(lv["needed"], 1.0)
            self.assertTrue(1.0 <= lv["max_safe"] <= 3.0)
            if lv["max_safe"] > 1:
                # liquidacao estimada a mais do dobro da distancia do stop
                self.assertGreaterEqual(100.0 - lv["liquidation_est"],
                                        2 * (100.0 - stop))
            self.assertAlmostEqual(lv["collateral_pct"],
                                   p["position_pct"] / lv["max_safe"], places=1)


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
