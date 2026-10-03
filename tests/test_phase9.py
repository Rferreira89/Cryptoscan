import unittest

from engine import config, ledger, short, signals, trade, validation
from engine import scanner as S
from engine import sources, venue
from tests import test_phase4 as T4
from tests.test_analysis import walk

CFG = config.load("nao-existe.json")
PLAN_S = {"stop": 102.0, "tp": [96.0, 92.0, 88.0], "partials": [50, 30, 20]}


class ShortTrade(unittest.TestCase):
    def pos(self, **k):
        return trade.open_position(PLAN_S, 100.0, 0, 0.1, side="SHORT", **k)

    def test_stop_is_minus_one_r_and_gap_is_worse(self):
        p = self.pos()
        ev = trade.step(p, 100.5, 102.5, 99.0, 101.0, 14400)
        self.assertEqual(ev[0]["event"], "STOP")
        self.assertAlmostEqual(p["r"], -1.0, places=3)
        g = self.pos()
        trade.step(g, 104.0, 105.0, 103.0, 104.0, 14400)
        self.assertLess(g["r"], -1.5)

    def test_targets_and_breakeven(self):
        p = self.pos()
        ev = trade.step(p, 99.5, 99.8, 87.0, 88.0, 14400)
        self.assertEqual([e["event"] for e in ev], ["TP1", "TP2", "TP3"])
        exp = (0.5 * (4 - 0.196) + 0.3 * (8 - 0.192) + 0.2 * (12 - 0.188)) / 2.202
        self.assertAlmostEqual(p["r"], exp, places=3)
        p = self.pos()
        trade.step(p, 99.5, 99.8, 95.5, 95.8, 14400)
        self.assertEqual((p["stop"], p["remaining"]), (100.0, 50.0))
        ev = trade.step(p, 97.0, 100.2, 96.5, 99.0, 28800)
        self.assertEqual(ev[0]["event"], "BREAKEVEN")
        self.assertGreater(p["r"], 0)

    def test_stop_first_when_both_in_same_bar_and_slippage_hurts(self):
        p = self.pos()
        trade.step(p, 100.0, 102.1, 95.0, 96.0, 14400)
        self.assertEqual(p["exit_reason"], "STOP")
        a, b = self.pos(), self.pos(slip_pct=0.1)
        for x in (a, b):
            trade.step(x, 100.5, 102.5, 99.0, 101.0, 14400)
        self.assertLess(b["r"], a["r"])
        self.assertLess(b["entry"], a["entry"])      # vende mais barato

    def test_long_is_unchanged(self):
        p = trade.open_position({"stop": 98.0, "tp": [104.0, 108.0, 112.0],
                                 "partials": [50, 30, 20]}, 100.0, 0, 0.1)
        trade.step(p, 99.5, 99.8, 97.5, 98.2, 14400)
        self.assertAlmostEqual(p["r"], -1.0, places=3)


class Mirror(unittest.TestCase):
    def test_mirror_is_valid_and_reversible(self):
        c = [dict(x, tb=x["v"] * 0.6) for x in walk(50)]
        m = short.mirror(c)
        for a, b in zip(c, m):
            self.assertTrue(b["l"] <= min(b["o"], b["c"]) <= max(b["o"], b["c"]) <= b["h"])
            self.assertAlmostEqual(b["tb"], a["v"] * 0.4)
        back = short.mirror(m)
        for a, b in zip(c, back):
            for k in "ohlc":
                self.assertAlmostEqual(a[k], b[k], places=9)

    def test_real_plan_levels_risk_and_rr(self):
        # espelho de: entrada real 100, stop real 102, objetivos 96/92/88
        pm = {"entry_zone": [1 / 100.3, 1 / 100.0], "stop": 1 / 102.0,
              "tp": [1 / 96.0, 1 / 92.0, 1 / 88.0], "tp_projected": [],
              "leverage": {"reason": "x"}}
        p, why = short.real_plan(pm, CFG, 2.0)
        self.assertIsNone(why)
        self.assertEqual(p["side"], "SHORT")
        self.assertAlmostEqual(p["entry_zone"][0], 100.0)
        self.assertAlmostEqual(p["entry_zone"][1], 100.3)
        self.assertAlmostEqual(p["stop"], 102.0)
        self.assertTrue(p["stop"] > p["entry_zone"][1] > p["entry_zone"][0]
                        > p["tp"][0] > p["tp"][1] > p["tp"][2])
        self.assertAlmostEqual(p["rr"], (8 - 0.192) / 2.202, places=2)
        self.assertEqual(p["position_usdc"], 25.0)
        self.assertAlmostEqual(p["risk_usdc"], 25 * 0.02202, places=2)
        self.assertGreater(p["leverage"]["liquidation_est"], p["stop"])   # acima do stop
        self.assertGreaterEqual(p["leverage"]["liquidation_est"] - 100.0,
                                2.5 * 2.0 - 1e-6)

    def test_real_plan_rejections(self):
        wide = {"entry_zone": [1 / 100.3, 1 / 100.0], "stop": 1 / 112.0,
                "tp": [1 / 80.0, 1 / 70.0, 1 / 60.0]}
        p, why = short.real_plan(wide, CFG)      # stop largo: posicao menor
        self.assertIsNone(why)
        self.assertLess(p["position_usdc"], 25.0)
        self.assertAlmostEqual(p["risk_usdc"], CFG["max_risk_usdc"], places=2)
        poor = {"entry_zone": [1 / 100.3, 1 / 100.0], "stop": 1 / 102.0,
                "tp": [1 / 99.0, 1 / 98.5, 1 / 98.0]}
        self.assertIn("POOR R:R", short.real_plan(poor, CFG)[1])
        bad = {"entry_zone": [1 / 100.3, 1 / 100.0], "stop": 1 / 99.0,
               "tp": [1 / 96.0, 1 / 92.0, 1 / 88.0]}
        self.assertIn("incoerente", short.real_plan(bad, CFG)[1])


def inv(c):
    return short.mirror(c)


class ShortDecision(unittest.TestCase):
    def setUp(self):
        self._orig = validation.load
        validation.load = lambda: None

    def tearDown(self):
        validation.load = self._orig

    def test_lifecycle_of_a_short_signal(self):
        now = 1_800_000_000
        plan = {"side": "SHORT", "entry_zone": [100.0, 100.3], "entry_ref": 100.0,
                "stop": 102.0, "tp": [96.0, 92.0, 88.0], "partials": [50, 30, 20],
                "rr": 2.4, "risk_pct": 1.1, "position_pct": 50.0, "stop_pct": 2.2,
                "leverage": {"use": 2.0}}
        d = {"decision": "SHORT", "side": "SHORT", "strategy": "PULLBACK_SHORT",
             "mode": "REAL", "score": 70, "score_label": "VALID SETUP",
             "regime": "BULL", "confidence": {}, "conflicts": [], "plan": plan,
             "venue": {"pair": "LINK/USDC", "name": "Bybit EU"}, "notes": ["n"],
             "trigger": "t", "families": {"regime": 1.0}, "checks": []}
        mkrow = lambda px: [{"asset": "LINK", "price": px, "decision": dict(d),
                             "analysis": {}, "data_status": "VALID"}]
        state = {}
        ev = signals.update_state(state, mkrow(99.5), CFG, now)
        self.assertEqual(ev[0]["event"], "ISSUED")
        sig = next(iter(state["signals"].values()))
        self.assertEqual((sig["direction"], sig["status"]), ("SHORT", "ACTIVE"))
        ledger.apply(state, ev)
        self.assertEqual(state["ledger"][0]["side"], "SHORT")
        # preco abaixo da zona: ainda nao entra; sobe ate a zona: entra
        self.assertEqual(signals.track(state, {"LINK": 99.6}, CFG, now + 60), [])
        ev = signals.track(state, {"LINK": 100.1}, CFG, now + 120)
        self.assertEqual(ev[0]["event"], "TRIGGERED")
        self.assertEqual(sig["position"]["side"], "SHORT")
        # desce ao 1.o objetivo, depois volta a entrada: stop na entrada
        ev = signals.track(state, {"LINK": 95.9}, CFG, now + 180)
        self.assertEqual(ev[0]["event"], "TP1")
        ev = signals.track(state, {"LINK": 100.2}, CFG, now + 240)
        self.assertEqual(ev[0]["event"], "BREAKEVEN")
        self.assertGreater(sig["result_r"], 0)

    def test_short_invalidations(self):
        now = 1_800_000_000
        base = {"direction": "SHORT", "asset": "X", "status": "ACTIVE",
                "expires_at": now + 9999, "strategy": "PULLBACK_SHORT",
                "plan": {"entry_zone": [100.0, 100.3], "stop": 102.0,
                         "tp": [96.0, 92.0, 88.0], "partials": [50, 30, 20]}}
        for px, why in ((102.5, "stop"), (95.0, "TP1")):
            st = {"signals": {"k": dict(base)}}
            ev = signals.track(st, {"X": px}, CFG, now)
            self.assertEqual(ev[0]["event"], "INVALIDATED")
            self.assertIn(why, ev[0]["reason"])

    def test_alert_texts(self):
        from engine import run
        sig = {"asset": "LINK", "pair": "LINK/USDC", "venue": "Bybit EU",
               "direction": "SHORT", "mode": "REAL", "strategy": "PULLBACK_SHORT",
               "timeframe": "4H / 1D", "score": 70,
               "plan": {"entry_zone": [100.0, 100.3], "stop": 102.0,
                        "tp": [96.0, 92.0, 88.0], "partials": [50, 30, 20],
                        "rr": 2.4, "risk_pct": 1.1, "stop_pct": 2.2,
                        "position_pct": 50.0, "position_usdc": 25.0,
                        "leverage": {"use": 2.0, "liquidation_est": 145.0,
                                     "reason": "condições normais"}}}
        t = run.alert_text({"event": "ISSUED", "id": "k"}, {"k": sig}, "nota")
        for part in ("SHORT", "emprestado e VENDER", "ACIMA", "recomprar 50%",
                     "25.00 USDC", "145", "nota"):
            self.assertIn(part, t)
        self.assertNotIn("COMPRA —", t)
        t = run.alert_text({"event": "STOP", "id": "k", "price": 102.0, "r": -1.0},
                           {"k": sig}, "")
        self.assertIn("RECOMPRA", t)
        self.assertIn("devolver o empréstimo", t)
        t = run.alert_text({"event": "TP1", "id": "k", "price": 96.0,
                            "sold_pct": 50}, {"k": sig}, "")
        self.assertIn("RECOMPRA PARCIAL", t)
        self.assertIn("Desce o stop", t)

    def test_user_r_for_short(self):
        r = {"side": "SHORT", "result_r": 2.0, "entry": 100.0, "stop": 102.0,
             "exec_price": 99.0, "status": "CLOSED"}
        # sistema: saiu a 96 (+2R). Utilizador vendeu a 99: (99-96)/(102-99)
        self.assertAlmostEqual(ledger.user_r(r), 1.0)

    def test_market_filter_is_mirrored(self):
        r = T4.row()
        d = signals.decide(r, T4.C4, CFG, T4.V, "BULL", False, market_ok=False,
                           suffix=short.SUFFIX)
        self.assertEqual(d["decision"], "NO TRADE")
        self.assertIn("sem shorts de tendência", d["reason"])

    def test_range_trades_on_both_sides_of_the_market_filter(self):
        # ativo lateral, preco no quarto inferior do range: compra permitida
        # mesmo com o BTC abaixo da media de 200 dias
        rng = T4.a1d(ema_trend="MIXED", structure="NEUTRAL", adx=15.0,
                     close=99.0, swing_low=95.0, swing_high=130.0, atr=4.0)
        c = [T4.mk(100, 101, 99, 100)] * 19 + [T4.mk(96, 97.2, 95.8, 97.0)]
        a4 = T4.a4h(close=97.0, atr=1.0, swing_high=112.0,
                    liquidity=dict(T4.a4h()["liquidity"], pools_above=[]))
        r = T4.row(a4=a4, a1=rng, price=97.0)
        v = dict(T4.V, last=97.0)
        d = signals.decide(r, c, CFG, v, "BEAR", False, market_ok=False)
        c4 = [x for x in d["checks"] if x["n"] == 4][0]
        self.assertTrue(c4["ok"])                      # passou o filtro
        self.assertEqual(c4["detail"], "RANGE")
        self.assertNotIn("filtro de mercado", d.get("reason") or "")
        # um setup de tendencia no mesmo contexto continua bloqueado
        t = signals.decide(T4.row(), T4.C4, CFG, T4.V, "BEAR", False,
                           market_ok=False)
        self.assertEqual(t["decision"], "NO TRADE")
        self.assertIn("filtro de mercado", t["reason"])


class EndToEndShort(unittest.TestCase):
    def test_downtrend_market_runs_and_longs_blocked(self):
        now = 1_800_000_000

        class Src:
            name = "binance"

            def tickers(self):
                t = lambda last: {"base": "", "last": last, "bid": last * 0.9999,
                                  "ask": last * 1.0001, "vol_quote": 5e8,
                                  "chg_pct": -1.0}
                return {"BTC": t(self.last("BTC")), "AAA": t(self.last("AAA"))}

            def series(self, base, tf):
                tfs = sources.TF_SECONDS[tf]
                end = now - now % tfs - tfs
                c = walk(400, seed=len(base) + (7 if tf == "1d" else 0),
                         drift=-0.004)
                return [dict(x, t=end - (399 - i) * tfs, tb=x["v"] * 0.5)
                        for i, x in enumerate(c)]

            def last(self, base):
                return self.series(base, "4h")[-1]["c"]

            def candles(self, base, tf, limit=500):
                return self.series(base, tf)

        src = Src()
        orig = (sources.ALL, venue.fetch, S.add_derivatives, validation.load)
        sources.ALL = [src]
        venue.fetch = lambda q: {a: {"pair": a + "/USDC", "last": src.last(a),
                                     "volume_usd": 5e6, "spread_pct": 0.05,
                                     "stale": False, "url": "u"}
                                 for a in ("BTC", "AAA")}
        S.add_derivatives = lambda rows, now: {"ok": False}
        validation.load = lambda: None
        self.addCleanup(lambda: (setattr(sources, "ALL", orig[0]),
                                 setattr(venue, "fetch", orig[1]),
                                 setattr(S, "add_derivatives", orig[2]),
                                 setattr(validation, "load", orig[3])))
        res, state, events = S.run(now=now, state={}, cfg=dict(CFG))
        self.assertFalse(res["market_filter"]["btc_above_sma200"])
        import json
        json.dumps(res); json.dumps(state); json.dumps(events)
        for r in res["universe"]:
            self.assertNotEqual(r["decision"]["decision"], "LONG")   # filtro
            ds = r["decision_short"]
            self.assertIn(ds["decision"], ("SHORT", "WATCHLIST", "NO TRADE"))
            self.assertEqual(ds["side"], "SHORT")
            if ds.get("plan"):
                p = ds["plan"]
                self.assertGreater(p["stop"], p["entry_zone"][1])
                self.assertLess(p["tp"][0], p["entry_zone"][0])
                self.assertLessEqual(p["risk_usdc"], CFG["max_risk_usdc"] + 0.01)
                self.assertTrue(ds["strategy"].endswith("_SHORT"))
        res2, state, _ = S.run(now=now + 300, state=state, cfg=dict(CFG))
        self.assertLessEqual(len(res2["active_signals"]), CFG["max_open_positions"])


if __name__ == "__main__":
    unittest.main()
