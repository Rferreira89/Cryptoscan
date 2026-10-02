import unittest

from engine import backtest as B
from engine import config, stats, trade
from tests.test_analysis import walk

CFG = dict(config.DEFAULTS)
PLAN = {"entry_zone": [99.7, 100.0], "stop": 98.0, "tp": [104.0, 108.0, 112.0],
        "partials": [50, 30, 20], "risk_pct": 1.0}
bar = lambda t, o, h, l, c: {"t": t * 14400, "o": o, "h": h, "l": l, "c": c,
                             "v": 1.0, "tb": 0.5}


class Trade(unittest.TestCase):
    def pos(self, **k):
        return trade.open_position(PLAN, 100.0, 0, 0.1, **k)

    def test_full_loss_is_minus_one_r(self):
        p = self.pos()
        ev = trade.step(p, 99.5, 99.8, 97.5, 98.2, 14400)
        self.assertEqual(ev[0]["event"], "STOP")
        self.assertAlmostEqual(p["r"], -1.0, places=3)     # comissoes incluidas

    def test_gap_through_stop_loses_more_than_one_r(self):
        p = self.pos()
        trade.step(p, 96.0, 97.0, 95.0, 96.5, 14400)
        self.assertLess(p["r"], -1.5)

    def test_stop_before_tp_in_same_bar(self):
        p = self.pos()
        trade.step(p, 100.0, 105.0, 97.9, 104.0, 14400)
        self.assertEqual(p["exit_reason"], "STOP")

    def test_tp1_then_breakeven(self):
        p = self.pos()
        ev = trade.step(p, 100.5, 104.5, 100.2, 104.2, 14400)
        self.assertEqual([e["event"] for e in ev], ["TP1"])
        self.assertEqual((p["remaining"], p["stop"]), (50.0, 100.0))
        ev = trade.step(p, 103.0, 103.5, 99.9, 100.1, 28800)
        self.assertEqual(ev[0]["event"], "BREAKEVEN")
        # 50% a +4 menos comissoes; resto a zero menos comissoes
        self.assertAlmostEqual(p["r"], (0.5 * (4 - 0.204) + 0.5 * (-0.2)) / 2.198,
                               places=3)

    def test_all_targets(self):
        p = self.pos()
        ev = trade.step(p, 100.5, 113.0, 100.2, 112.5, 14400)
        self.assertEqual([e["event"] for e in ev], ["TP1", "TP2", "TP3"])
        self.assertTrue(p["closed"])
        exp = (0.5 * (4 - 0.204) + 0.3 * (8 - 0.208) + 0.2 * (12 - 0.212)) / 2.198
        self.assertAlmostEqual(p["r"], exp, places=3)

    def test_breakeven_optional_and_time_exit(self):
        p = self.pos(breakeven=False)
        trade.step(p, 100.5, 104.5, 100.2, 104.2, 14400)
        self.assertEqual(p["stop"], 98.0)
        p = self.pos()
        ev = trade.step(p, 100.5, 101, 100.2, 100.8, trade.MAX_HOLD_SECONDS + 1)
        self.assertEqual(ev[0]["event"], "TIME")

    def test_slippage_hurts(self):
        a, b = self.pos(), self.pos(slip_pct=0.1)
        for p in (a, b):
            trade.step(p, 99.5, 99.8, 97.5, 98.2, 14400)
        self.assertLess(b["r"], a["r"])


class Simulate(unittest.TestCase):
    cand = {"i": 0, "plan": PLAN}

    def test_fill_then_win(self):
        c = [bar(0, 100, 100, 100, 100), bar(1, 100.2, 100.5, 99.9, 100.3),
             bar(2, 100.3, 113, 100.1, 112)]
        r = B.simulate(self.cand, c, CFG)
        self.assertEqual((r["status"], r["exit"]), ("CLOSED", "TP3"))
        self.assertGreater(r["r"], 2)

    def test_no_tp_credit_on_fill_bar_when_filled_mid_bar(self):
        # abre acima da zona, faz maximo nos TPs e so depois enche a ordem
        c = [bar(0, 100, 100, 100, 100), bar(1, 101, 113, 99.9, 100.5),
             bar(2, 100.5, 100.6, 97.0, 97.5)]
        r = B.simulate(self.cand, c, CFG)
        self.assertEqual(r["exit"], "STOP")

    def test_expired_invalidated_open(self):
        up = [bar(0, 100, 100, 100, 100)] + [bar(k, 101, 102, 100.5, 101.5)
                                             for k in (1, 2, 3, 4)]
        self.assertEqual(B.simulate(self.cand, up, CFG)["status"], "EXPIRED")
        gap = [bar(0, 100, 100, 100, 100), bar(1, 97, 97.5, 96, 96.5)]
        self.assertEqual(B.simulate(self.cand, gap, CFG)["status"], "INVALIDATED")
        run = [bar(0, 100, 100, 100, 100), bar(1, 101, 105, 100.5, 104.5)]
        self.assertEqual(B.simulate(self.cand, run, CFG)["status"], "INVALIDATED")
        op = [bar(0, 100, 100, 100, 100), bar(1, 100, 100.5, 99.9, 100.2)]
        self.assertEqual(B.simulate(self.cand, op, CFG)["status"], "OPEN_AT_END")


class Engine(unittest.TestCase):
    def test_daily_only_complete_days(self):
        c = [bar(k, 1, 2, 0.5, 1.5) for k in range(3, 20)]     # comeca a meio do dia
        d = B.daily(c)
        self.assertEqual([x["t"] for x in d], [86400, 172800])
        self.assertEqual(d[0]["v"], 6.0)

    def test_no_lookahead_in_candidates(self):
        """Candidatos ate T nao mudam quando se acrescenta futuro."""
        c = [dict(x, tb=x["v"] * 0.5) for x in walk(1700, seed=5, drift=0.0006)]
        reg = B.regimes(c)
        full = B.candidates("X", c, reg, CFG)
        cut_i = 1500
        part = B.candidates("X", c[:cut_i + 1], B.regimes(c[:cut_i + 1]), CFG)
        key = lambda x: (x["i"], x["strategy"], x["score"],
                         tuple(x["plan"]["tp"]), x["plan"]["stop"])
        self.assertEqual([key(x) for x in full if x["i"] <= cut_i - 6],
                         [key(x) for x in part if x["i"] <= cut_i - 6])


def T(r, t, asset="A", score=70, strat="PULLBACK", dur=86400, status="CLOSED"):
    c = {"asset": asset, "t": t, "score": score, "strategy": strat,
         "n_conflicts": 0, "regime": "BULL", "btc_regime": "BULL"}
    res = {"status": status, "r": r, "entry_t": t, "exit_t": t + dur,
           "risk_pct": 1.0, "exit": "STOP" if r < 0 else "TP3"}
    return c, res


class Alerts(unittest.TestCase):
    def test_texts_for_every_event(self):
        from engine import run, validation
        sig = {"asset": "LINK", "pair": "LINK/USDC", "venue": "Bybit EU",
               "mode": "REAL",
               "strategy": "PULLBACK", "timeframe": "4H / 1D", "score": 72,
               "plan": dict(PLAN, rr=2.4, stop_pct=2.2, position_pct=25.0,
                            risk_pct=0.55)}
        sigs = {"k": sig}
        t = run.alert_text({"event": "ISSUED", "id": "k"}, sigs, "nota")
        for part in ("COMPRA", "LINK/USDC", "99.7", "98", "104", "nota"):
            self.assertIn(part, t)
        self.assertIn("ENTRADA", run.alert_text(
            {"event": "TRIGGERED", "id": "k", "price": 99.9}, sigs, ""))
        t = run.alert_text({"event": "TP1", "id": "k", "price": 104.0,
                            "sold_pct": 50}, sigs, "")
        self.assertIn("VENDA PARCIAL", t)
        self.assertIn("Sobe o stop", t)
        t = run.alert_text({"event": "STOP", "id": "k", "price": 98.0,
                            "r": -1.0}, sigs, "")
        self.assertIn("-1.00R", t)
        self.assertIn("CANCELAR", run.alert_text(
            {"event": "EXPIRED", "id": "k", "reason": "x"}, sigs, ""))
        self.assertIsNone(run.alert_text({"event": "?", "id": "k"}, sigs, ""))
        self.assertIn("SEM BACKTEST", validation.note("NAO_EXISTE"))


class Stats(unittest.TestCase):
    def test_select_rules(self):
        items = [T(1, 0), T(1, 1000),                     # mesmo ativo ocupado
                 T(1, 2000, "B", score=60),               # score baixo
                 T(1, 3000, "C"), T(1, 3000, "D"), T(1, 3000, "E"),
                 T(1, 3000, "F", score=90)]               # limite de 4 em aberto
        c, r = [x[0] for x in items], [x[1] for x in items]
        got = stats.select(c, r, CFG)
        self.assertEqual([t["asset"] for t in got], ["A", "F", "C", "D"])
        only = stats.select(c, r, CFG, strategies=["RANGE"])
        self.assertEqual(only, [])

    def test_metrics_known_values(self):
        tr = [dict(*[{**a, **b}]) for a, b in
              [T(2, 0), T(-1, 10 ** 5), T(-1, 2 * 10 ** 5), T(3, 3 * 10 ** 5)]]
        m = stats.metrics(tr)
        self.assertEqual((m["n"], m["win_rate"]), (4, 50.0))
        self.assertEqual((m["avg_win_r"], m["avg_loss_r"]), (2.5, -1.0))
        self.assertEqual(m["expectancy_r"], 0.75)
        self.assertEqual(m["profit_factor"], 2.5)
        self.assertEqual(m["longest_loss_streak"], 2)
        self.assertAlmostEqual(m["max_drawdown_pct"], 1.99, places=1)
        # expectancy = acerto x ganho medio - falha x perda media
        self.assertAlmostEqual(0.5 * 2.5 - 0.5 * 1.0, m["expectancy_r"])
        self.assertEqual(stats.metrics([]), {"n": 0})

    def test_monte_carlo_and_ci(self):
        tr = [{**a, **b} for a, b in [T(2 if k % 3 == 0 else -1, k * 10 ** 5)
                                      for k in range(60)]]
        mc = stats.monte_carlo(tr)
        self.assertLessEqual(mc["return_pct"]["p5"], mc["return_pct"]["p50"])
        self.assertLessEqual(mc["max_drawdown_pct"]["p50"],
                             mc["max_drawdown_pct"]["p95"])
        self.assertIsNone(stats.monte_carlo(tr[:5]))
        ci = stats.boot_ci([t["r"] for t in tr])
        self.assertLess(ci[0], 0.0)
        self.assertGreater(ci[1], 0.0)          # vantagem nao demonstrada

    def test_walk_forward_uses_only_past(self):
        # estrategia boa no 1o ano e ma no 2o: o WF tem de sofrer no teste
        Y = 365 * 86400
        items = [T(1.0, k * Y // 60, f"A{k}") for k in range(60)] + \
                [T(-1.0, Y + k * Y // 60, f"B{k}") for k in range(60)]
        c, r = [x[0] for x in items], [x[1] for x in items]
        folds, oos = stats.walk_forward(
            c, r, CFG, 0, 2 * Y, Y, Y // 4,
            [{"min_score": 65, "strategies": None}])
        self.assertEqual(folds[0]["chosen"]["min_score"], 65)
        self.assertLess(folds[0]["test_expectancy"], 0)
        self.assertTrue(all(t["t"] >= Y for t in oos))


if __name__ == "__main__":
    unittest.main()


class PaperTrend(unittest.TestCase):
    def daily(self, closes, t0=0):
        return [{"t": t0 + k * 86400, "o": c, "h": c * 1.01, "l": c * 0.99,
                 "c": c, "v": 1.0} for k, c in enumerate(closes)]

    def test_market_filter_flip_alerts_once(self):
        from engine import paper_trend as P
        st = {}
        up = self.daily([100.0] * 199 + [120.0])
        info, ev = P.market_filter(up, st, 1)
        self.assertTrue(info["btc_above_sma200"])
        self.assertEqual(ev, [])                       # primeiro registo: sem alerta
        self.assertEqual(P.market_filter(up, st, 2)[1], [])
        dn = self.daily([100.0] * 199 + [80.0])
        info, ev = P.market_filter(dn, st, 3)
        self.assertFalse(info["btc_above_sma200"])
        self.assertEqual(ev[0]["event"], "MARKET_FILTER")
        self.assertEqual(P.market_filter(None, st, 4), (None, []))

    def test_buy_trail_stop_and_once_per_day(self):
        from engine import paper_trend as P
        st = {}
        c = self.daily([100.0] * 220 + [104.0])        # quebra do maximo de 20d
        row = lambda px: [{"asset": "LINK", "price": px,
                           "venue": {"pair": "LINK/USDC"}}]
        s, ev = P.update(st, row(104.2), {"LINK": c}, CFG, 10)
        self.assertEqual(ev[0]["event"], "PAPER_BUY")
        pos = st["paper_trend"]["positions"]["LINK"]
        self.assertLess(pos["stop0"], pos["entry"])
        self.assertLessEqual(pos["risk_frac"], 0.0101)
        # mesmo dia, novo scan: nao volta a comprar nem a avaliar
        self.assertEqual(P.update(st, row(104.5), {"LINK": c}, CFG, 20)[1], [])
        # stop intradiario
        s, ev = P.update(st, row(pos["stop0"] * 0.99), {"LINK": c}, CFG, 30)
        self.assertEqual((ev[0]["event"], ev[0]["reason"]), ("PAPER_SELL", "STOP"))
        self.assertLess(ev[0]["r"], -0.9)
        self.assertLess(s["equity_pct"], 0)
        self.assertEqual(s["n"], 1)

    def test_filters(self):
        from engine import paper_trend as P
        c = self.daily([100.0] * 220 + [104.0])
        mk = lambda a, px, v={"pair": "X/USDC"}: [{"asset": a, "price": px,
                                                   "venue": v}]
        self.assertEqual(P.update({}, mk("PEPE", 104.2), {"PEPE": c}, CFG, 1)[1], [])
        self.assertEqual(P.update({}, mk("LINK", 104.2, None), {"LINK": c}, CFG, 1)[1], [])
        self.assertEqual(P.update({}, mk("LINK", 112.0), {"LINK": c}, CFG, 1)[1], [])  # tarde
        below = self.daily([200.0] * 180 + [100.0] * 40 + [104.0])   # abaixo da SMA200
        self.assertEqual(P.update({}, mk("LINK", 104.2), {"LINK": below}, CFG, 1)[1], [])

    def test_alert_texts(self):
        from engine import run
        t = run.alert_text({"event": "PAPER_BUY", "id": "p", "asset": "LINK",
                            "pair": "LINK/USDC", "price": 14.2, "stop": 12.9,
                            "position_pct": 10.0}, {}, "")
        self.assertIn("PAPEL", t)
        self.assertIn("não validado", t)
        t = run.alert_text({"event": "MARKET_FILTER", "id": "market",
                            "above": False, "close": 80000, "sma200": 85000},
                           {}, "")
        self.assertIn("ABAIXO", t)
