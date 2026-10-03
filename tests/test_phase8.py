import datetime
import unittest

from engine import config, events, inbox, ledger, monitor, review, signals
from engine import validation
from tests import test_phase4 as T4

CFG = dict(config.DEFAULTS, swing_leverage=1.0, max_open_positions=4,
           unvalidated_risk_pct=0.5,
           fixed_position_usdc=None)   # valores de base fixos para os testes
NY = events.NY


def ts(y, m, d, h, mi=0):
    return int(datetime.datetime(y, m, d, h, mi, tzinfo=NY).timestamp())


class Events(unittest.TestCase):
    def test_window(self):
        cpi = ts(2026, 10, 14, 8, 30)
        self.assertIsNone(events.block(cpi - 13 * 3600))
        self.assertEqual(events.block(cpi - 11 * 3600)["name"],
                         "Inflação dos EUA (CPI)")
        self.assertIsNotNone(events.block(cpi + 3600))
        self.assertIsNone(events.block(cpi + 3 * 3600))
        fomc = ts(2026, 10, 28, 14)
        self.assertIn("Fed", events.block(fomc)["name"])

    def test_next_and_stale(self):
        now = ts(2026, 10, 2, 9)
        self.assertEqual(events.next_event(now)["t"], ts(2026, 10, 14, 8, 30))
        self.assertFalse(events.stale(now))
        self.assertTrue(events.stale(ts(2026, 12, 20, 9)))    # sem CPI de 2027
        self.assertEqual([t for _, t in events.ALL], sorted(t for _, t in events.ALL))

    def test_decision_blocked(self):
        orig = validation.load
        validation.load = lambda: None
        self.addCleanup(lambda: setattr(validation, "load", orig))
        d = signals.decide(T4.row(), T4.C4, CFG, T4.V, "BULL", False,
                           block="Decisão da Fed (FOMC) dentro da janela de risco")
        self.assertEqual(d["decision"], "NO TRADE")
        self.assertIn("NEWS RISK", d["reason"])
        d = signals.decide(T4.row(), T4.C4, CFG, T4.V, "BULL", False,
                           disabled={"PULLBACK"})
        self.assertEqual(d["decision"], "NO TRADE")
        self.assertIn("desligada", d["reason"])


def closed(k, r, strat="PULLBACK", **kw):
    rec = {"id": f"i{k}", "kind": "4H", "asset": "LINK", "strategy": strat,
           "mode": "REAL", "status": "CLOSED", "closed_at": k, "result_r": r,
           "risk_pct": 0.5, "entry": 100.0, "stop": 98.0, "issued_at": k}
    rec.update(kw)
    return rec


class Review(unittest.TestCase):
    def test_disable_only_with_sample_and_negative(self):
        st = {"ledger": [closed(k, -0.2) for k in range(29)]}
        self.assertEqual(review.update(st, 1), ({}, []))
        st["ledger"].append(closed(29, -0.2))
        dis, ev = review.update(st, 2)
        self.assertEqual(list(dis), ["PULLBACK"])
        self.assertEqual(ev[0]["event"], "STRATEGY_DISABLED")
        self.assertEqual(review.update(st, 3)[1], [])          # avisa uma vez
        ok = {"ledger": [closed(k, 0.3, "BREAKOUT") for k in range(40)]}
        self.assertEqual(review.update(ok, 1)[0], {})


def cb(data, chat=7, i=1):
    return {"update_id": i, "callback_query": {
        "id": "c", "data": data, "message": {"chat": {"id": chat}}}}


def msg(text, chat=7, i=1):
    return {"update_id": i, "message": {"text": text, "chat": {"id": chat}}}


class Inbox(unittest.TestCase):
    def led(self):
        return {"ledger": [{"id": "LINK-PULLBACK-1", "kind": "4H",
                            "asset": "LINK", "status": "OPEN", "stop": 98.0,
                            "entry": 100.0}]}

    def test_buttons_and_price_command(self):
        st = self.led()
        out = inbox.apply(st, [cb("x|1|LINK-PULLBACK-1")], 7)
        self.assertTrue(st["ledger"][0]["executed"])
        self.assertIn("/preco LINK", out[0][0])
        inbox.apply(st, [msg("/preco link 100,5")], 7)
        self.assertEqual(st["ledger"][0]["exec_price"], 100.5)
        inbox.apply(st, [msg("preço LINK 101")], 7)
        self.assertEqual(st["ledger"][0]["exec_price"], 101.0)
        out = inbox.apply(st, [cb("x|0|LINK-PULLBACK-1")], 7)
        self.assertFalse(st["ledger"][0]["executed"])
        self.assertLessEqual(len(inbox.buttons("LINK-LIQUIDITY_SWEEP-1790945000")
                                 ["inline_keyboard"][0][0]["callback_data"]), 64)

    def test_ignores_strangers_and_garbage(self):
        st = self.led()
        self.assertEqual(inbox.apply(st, [cb("x|1|LINK-PULLBACK-1", chat=999),
                                          msg("/preco LINK 1", chat=999)], 7), [])
        self.assertNotIn("executed", st["ledger"][0])
        self.assertEqual(inbox.apply(st, [msg("olá"), msg("/preco LINK abc")], 7), [])
        out = inbox.apply(st, [cb("x|1|nao-existe"), cb("lixo"), msg("/preco XYZ 5")], 7)
        self.assertEqual(len(out), 3)
        self.assertNotIn("executed", st["ledger"][0])

    def test_muted_after_not_executed(self):
        st = self.led()
        e = {"event": "TP1", "id": "LINK-PULLBACK-1"}
        self.assertFalse(inbox.muted(st, e))
        st["ledger"][0]["executed"] = False
        self.assertTrue(inbox.muted(st, e))
        self.assertFalse(inbox.muted(st, {"event": "ISSUED", "id": "LINK-PULLBACK-1"}))
        self.assertFalse(inbox.muted(st, {"event": "MARKET_FILTER", "id": "market"}))


class Journal(unittest.TestCase):
    def test_user_result_with_real_entry_price(self):
        # sistema: entrada 100, stop 98, +2R -> saida 104. Utilizador entrou a 101
        r = closed(1, 2.0, executed=True, exec_price=101.0)
        self.assertAlmostEqual(ledger.user_r(r), 1.0)          # (104-101)/(101-98)
        self.assertEqual(ledger.user_r(closed(1, 2.0)), 2.0)
        led = [r, closed(2, -1.0), closed(3, -1.0, executed=False)]
        v = ledger.view(led)
        self.assertEqual(v["summary"]["closed"], 3)
        self.assertEqual((v["mine"]["closed"], v["mine"]["total_r"]), (1, 1.0))
        self.assertIsNone(ledger.view([closed(1, 1.0)])["mine"])


class Monitor(unittest.TestCase):
    def test_tick_tracks_without_issuing(self):
        orig = validation.load
        validation.load = lambda: None
        self.addCleanup(lambda: setattr(validation, "load", orig))
        now = 1_800_000_000
        r = T4.row(asset="LINK")
        r["decision"] = signals.decide(r, T4.C4, CFG, T4.V, "BULL", False)
        state = {}
        ev = signals.update_state(state, [r], CFG, now)
        ledger.apply(state, ev)
        self.assertEqual(monitor.needed_assets(state), {"LINK"})
        ev = monitor.tick(state, {"LINK": 100.9}, CFG, now + 300)
        self.assertEqual([e["event"] for e in ev], ["TRIGGERED"])
        self.assertEqual(state["ledger"][0]["status"], "OPEN")
        ev = monitor.tick(state, {"LINK": 90.0}, CFG, now + 600)
        self.assertEqual(ev[0]["event"], "STOP")
        self.assertEqual(state["ledger"][0]["status"], "CLOSED")
        self.assertEqual(monitor.tick(state, {}, CFG, now + 900), [])
        self.assertEqual(len(state["signals"]), 1)             # nada novo

    def test_prices_median_and_missing(self):
        data = {"a": {"X": {"last": 10.0}}, "b": {"X": {"last": 12.0}},
                "c": {"X": {"last": None}}}
        self.assertEqual(monitor.prices_for({"X", "Y"}, data), {"X": 11.0})

    def test_trend_stop_in_monitor(self):
        from engine import paper_trend as P
        st = {"paper_trend": {"equity": 1.0, "closed": [], "last_day": {},
              "positions": {"BTC": {"entry": 100.0, "stop0": 90.0, "entry_t": 1,
                                    "pair": "BTC/USDC", "position_pct": 5.0,
                                    "risk_frac": 0.005}}}}
        self.assertEqual(P.check_stops(st, {"BTC": 95.0}, CFG, 2), [])
        ev = P.check_stops(st, {"BTC": 89.0}, CFG, 3)
        self.assertEqual((ev[0]["event"], ev[0]["reason"]), ("PAPER_SELL", "STOP"))
        self.assertEqual(st["paper_trend"]["positions"], {})


class Delivery(unittest.TestCase):
    def test_buttons_only_on_buy_alerts_and_mute(self):
        from engine import alerts, run
        sent = []
        orig = (alerts.send, alerts.configured)
        alerts.send = lambda text, markup=None: sent.append((text, markup))
        alerts.configured = lambda: True
        self.addCleanup(lambda: (setattr(alerts, "send", orig[0]),
                                 setattr(alerts, "configured", orig[1])))
        plan = {"entry_zone": [99.7, 100.0], "stop": 98.0, "tp": [104, 108, 112],
                "rr": 2.4, "risk_pct": 0.5, "position_pct": 20.0, "stop_pct": 2.2,
                "leverage": {"use": 2.0, "max_safe": 3.0, "collateral_pct": 10.0,
                             "liquidation_est": 55.0}}
        sig = {"asset": "LINK", "pair": "LINK/USDC", "venue": "Bybit EU",
               "strategy": "PULLBACK", "timeframe": "4H / 1D", "score": 70,
               "mode": "REAL", "plan": plan}
        state = {"signals": {"k": sig}, "ledger": [
            {"id": "k", "kind": "4H", "asset": "LINK", "status": "OPEN"}]}
        run.deliver(CFG, state, [{"event": "ISSUED", "id": "k", "t": 1},
                                 {"event": "TP1", "id": "k", "price": 104.0,
                                  "sold_pct": 50}], [("daily", "relatório")])
        self.assertEqual(sent[0], ("relatório", None))
        self.assertIn("Alavancagem: 2x", sent[1][0])
        self.assertIn("Liquidação estimada", sent[1][0])
        self.assertEqual(sent[1][1]["inline_keyboard"][0][0]["callback_data"], "x|1|k")
        self.assertIsNone(sent[2][1])
        state["ledger"][0]["executed"] = False
        sent.clear()
        run.deliver(CFG, state, [{"event": "TP2", "id": "k", "price": 108.0,
                                  "sold_pct": 30}])
        self.assertEqual(sent, [])


if __name__ == "__main__":
    unittest.main()


class SmallCapital(unittest.TestCase):
    def plan(self, capital, stop=98.0, lev=1.0):
        from engine import risk
        return risk.plan({"strategy": "X", "entry": [99.7, 100.0], "stop": stop},
                         T4.a4h(), T4.a1d(),
                         dict(CFG, capital_usdc=capital, swing_leverage=lev,
                              risk_pct=0.5))

    def test_partials_follow_order_minimum(self):
        # stop 2.2% e risco 0.5% -> posicao de 22.7% do capital
        p, _ = self.plan(1000)
        self.assertEqual(p["partials"], [50, 30, 20])
        self.assertAlmostEqual(p["position_usdc"], 227.48, delta=0.5)
        p, _ = self.plan(50)                       # 11.4 USDC: so 50/50
        self.assertEqual(p["partials"], [50, 50, 0])
        p, _ = self.plan(30)                       # 6.8 USDC: saida unica
        self.assertEqual(p["partials"], [0, 100, 0])
        p, why = self.plan(19)                     # 4.3 USDC: nao executavel
        self.assertIsNone(p)
        self.assertIn("ordem mínima", why)

    def test_rounds_up_to_minimum_only_when_very_close(self):
        # 22.7% do capital: 21 USDC -> 4.78 (sobe para 5); 19 USDC -> 4.32 (rejeita)
        p, _ = self.plan(21)
        self.assertEqual(p["position_usdc"], 5.0)
        self.assertLessEqual(p["risk_pct"], 0.5 * 1.1 + 0.01)
        self.assertEqual(p["partials"], [0, 100, 0])
        self.assertIsNone(self.plan(19)[0])

    def test_usdc_amounts_with_leverage(self):
        p, _ = self.plan(50, lev=2.0)
        self.assertAlmostEqual(p["collateral_usdc"] + p["borrowed_usdc"],
                               p["position_usdc"], delta=0.011)
        self.assertAlmostEqual(p["collateral_usdc"], p["position_usdc"] / 2, delta=0.011)
        self.assertAlmostEqual(p["risk_usdc"], 50 * p["risk_pct"] / 100, delta=0.01)
        self.assertLessEqual(p["risk_usdc"], 0.51)          # 1% de 50 USDC

    def test_single_exit_and_two_exit_management(self):
        from engine import trade
        plan = {"stop": 98.0, "tp": [104.0, 108.0, 112.0], "partials": [0, 100, 0]}
        pos = trade.open_position(plan, 100.0, 0, 0.1)
        ev = trade.step(pos, 100.5, 104.5, 100.2, 104.2, 14400)
        self.assertEqual((ev[0]["event"], ev[0]["sold_pct"]), ("TP1", 0))
        self.assertEqual((pos["remaining"], pos["stop"]), (100.0, 100.0))
        ev = trade.step(pos, 104.2, 113.0, 104.0, 112.0, 28800)
        self.assertEqual([e["event"] for e in ev], ["TP2"])   # fecha no TP2
        self.assertTrue(pos["closed"])
        self.assertEqual(pos["exit_reason"], "TP2")
        self.assertAlmostEqual(pos["r"], (8 - 0.208) / 2.198, places=3)
        two = trade.open_position(dict(plan, partials=[50, 50, 0]), 100.0, 0, 0.1)
        ev = trade.step(two, 100.5, 113.0, 100.2, 112.0, 14400)
        self.assertEqual([e["event"] for e in ev], ["TP1", "TP2"])
        self.assertEqual(two["exit_reason"], "TP2")

    def test_ledger_and_alerts_for_adapted_exits(self):
        from engine import run
        st = {}
        ledger.apply(st, [{"t": 1, "event": "ISSUED", "id": "a", "signal": {
            "asset": "LINK", "pair": "LINK/USDC", "strategy": "PULLBACK",
            "score": 70, "plan": {"entry_zone": [99.7, 100], "stop": 98,
                                  "tp": [104, 108, 112], "rr": 2.4,
                                  "risk_pct": 1.0, "position_pct": 20,
                                  "position_usdc": 10.0, "risk_usdc": 0.5}}},
            {"t": 2, "event": "TRIGGERED", "id": "a", "price": 100},
            {"t": 3, "event": "TP1", "id": "a", "price": 104, "sold_pct": 0},
            {"t": 4, "event": "TP2", "id": "a", "price": 108, "sold_pct": 100,
             "r": 3.5}])
        r = st["ledger"][0]
        self.assertEqual((r["status"], r["tp_hit"], r["reason"]), ("CLOSED", 2, "TP2"))
        p = {"tp": [104.0, 108.0, 112.0], "partials": [0, 100, 0]}
        t = run.targets_line(p)
        self.assertIn("TP2 108 (vender 100%)", t)
        self.assertNotIn("TP3", t)
        self.assertIn("sobe o stop", t)
        self.assertIn("TP1 104 (vender 50%) · TP2 108 (vender 50%)",
                      run.targets_line(dict(p, partials=[50, 50, 0])))
        sig = {"asset": "LINK", "pair": "LINK/USDC", "venue": "Bybit EU",
               "mode": "REAL", "plan": p}
        t = run.alert_text({"event": "TP1", "id": "k", "price": 104.0,
                            "sold_pct": 0}, {"k": sig}, "")
        self.assertIn("não vendas", t)
        t = run.alert_text({"event": "TP2", "id": "k", "price": 108.0,
                            "sold_pct": 100, "r": 3.5}, {"k": sig}, "")
        self.assertIn("VENDA FINAL", t)
        self.assertIn("+3.50R", t)
        t = run.invest_line(20.0, 1.0, {"use": 2.0, "liquidation_est": 55.0,
                                        "collateral_pct": 10.0}, 10.0)
        self.assertIn("10.00 USDC", t)
        self.assertIn("5.00 USDC teus e 5.00 emprestados", t)

    def test_reduced_leverage_below_minimum_is_rejected_not_a_crash(self):
        orig = validation.load
        validation.load = lambda: None
        self.addCleanup(lambda: setattr(validation, "load", orig))
        cfg = dict(CFG, swing_leverage=2.0, capital_usdc=15.0)
        ok = signals.decide(T4.row(), T4.C4, cfg, T4.V, "BULL", False)
        self.assertEqual(ok["decision"], "LONG")            # 2x: executavel
        r = T4.row()
        r["analysis"]["mtf_conflict"] = "1D: médias e estrutura discordam"
        d = signals.decide(r, T4.C4, cfg, T4.V, "BULL", False)   # conflito -> 1x
        self.assertEqual(d["decision"], "NO TRADE")
        self.assertIn("ordem mínima", d["reason"])
        self.assertNotIn("plan", d)

    def test_capital_command(self):
        st = {"ledger": []}
        out = inbox.apply(st, [msg("/capital 62,5")], 7)
        self.assertEqual(st["capital"], 62.5)
        self.assertIn("62.5", out[0][0])
        inbox.apply(st, [msg("/capital 1")], 7)
        self.assertEqual(st["capital"], 62.5)               # fora dos limites
        inbox.apply(st, [msg("/capital 900", chat=999)], 7)
        self.assertEqual(st["capital"], 62.5)               # estranho ignorado

    def test_trend_skips_below_minimum_order(self):
        from engine import paper_trend as P
        c = [{"t": k * 86400, "o": v, "h": v * 1.01, "l": v * 0.99, "c": v,
              "v": 1.0} for k, v in enumerate([100.0] * 220 + [104.0])]
        rw = [{"asset": "LINK", "price": 104.2, "venue": {"pair": "LINK/USDC"}}]
        self.assertEqual(P.update({}, rw, {"LINK": c}, dict(CFG, capital_usdc=20.0), 1)[1], [])
        ev = P.update({}, rw, {"LINK": c}, dict(CFG, capital_usdc=500.0), 1)[1]
        self.assertEqual(ev[0]["event"], "PAPER_BUY")
        self.assertGreaterEqual(ev[0]["position_usdc"], 5.0)


class ExtraEvents(unittest.TestCase):
    def test_asset_specific_and_malformed(self):
        import json, os, tempfile
        t0 = ts(2026, 11, 20, 12)
        good = [{"name": "Desbloqueio SUI", "t": t0, "assets": ["sui"],
                 "before_h": 48},
                {"name": "PCE", "t": t0 + 5 * 86400}]
        f = os.path.join(tempfile.mkdtemp(), "e.json")
        json.dump({"events": good + [{"name": "sem data"}, "lixo",
                                     {"name": "x", "t": "abc"},
                                     {"name": "y", "t": 5}]}, open(f, "w"))
        ex = events.load_extra(f)
        self.assertEqual([e["name"] for e in ex], ["Desbloqueio SUI", "PCE"])
        self.assertEqual(ex[0]["assets"], ["SUI"])
        self.assertIsNone(events.block(t0 - 40 * 3600, None, ex))
        self.assertIsNone(events.block(t0 - 40 * 3600, "LINK", ex))
        self.assertEqual(events.block(t0 - 40 * 3600, "SUI", ex)["name"],
                         "Desbloqueio SUI")
        self.assertIsNone(events.block(t0 - 50 * 3600, "SUI", ex))
        self.assertEqual(events.block(t0 + 5 * 86400 - 3600, "LINK", ex)["name"], "PCE")
        # ficheiro em falta ou corrompido nunca parte o sistema
        self.assertEqual(events.load_extra("/nao/existe.json"), [])
        open(f, "w").write("{isto nao e json")
        self.assertEqual(events.load_extra(f), [])
        json.dump({"events": {"a": 1}}, open(f, "w"))
        self.assertEqual(events.load_extra(f), [])
        self.assertEqual(events.load_extra(), [])            # ficheiro real: vazio

    def test_before_window_is_capped(self):
        ex = [{"name": "z", "t": 2_000_000_000, "assets": ["ALL"], "before_h": 72}]
        import json, os, tempfile
        f = os.path.join(tempfile.mkdtemp(), "e.json")
        json.dump({"events": [{"name": "z", "t": 2_000_000_000, "before_h": 9999}]},
                  open(f, "w"))
        self.assertEqual(events.load_extra(f)[0]["before_h"], 72)


class Concentrated(unittest.TestCase):
    def test_defaults_of_mode_b(self):
        c = config.load("nao-existe.json")
        self.assertEqual((c["max_open_positions"], c["unvalidated_risk_pct"],
                          c["capital_usdc"], c["swing_leverage"]), (2, 1.0, 50.0, 2.0))
        self.assertEqual((c["fixed_position_usdc"], c["max_risk_usdc"]), (25.0, 2.0))

    def test_risk_and_position_caps_at_50_usdc(self):
        orig = validation.load
        validation.load = lambda: None
        self.addCleanup(lambda: setattr(validation, "load", orig))
        cfg = dict(config.load("nao-existe.json"), fixed_position_usdc=None)
        d = signals.decide(T4.row(), T4.C4, cfg, T4.V, "BULL", False)
        p = d["plan"]
        self.assertLessEqual(p["position_usdc"], 25.0 + 1e-9)
        self.assertLessEqual(p["risk_usdc"], 1.0 + 0.01)
        self.assertLessEqual(p["risk_pct"], 2.0 + 0.01)
        r = T4.row()
        r["analysis"]["mtf_conflict"] = "1D: médias e estrutura discordam"
        p1 = signals.decide(r, T4.C4, cfg, T4.V, "BULL", False)["plan"]
        self.assertLessEqual(p1["position_usdc"], 12.5 + 1e-9)      # sem margem
        self.assertLessEqual(p1["risk_usdc"], 0.5 + 0.01)

    def test_two_operations_in_total_including_daily_trend(self):
        orig = validation.load
        validation.load = lambda: None
        self.addCleanup(lambda: setattr(validation, "load", orig))
        cfg = config.load("nao-existe.json")
        rows = []
        for k in range(4):
            r = T4.row(asset=f"A{k}")
            r["decision"] = signals.decide(r, T4.C4, cfg, T4.V, "BULL", False)
            rows.append(r)
        state = {"paper_trend": {"equity": 1.0, "closed": [], "last_day": {},
                 "positions": {"BTC": {"entry": 1, "stop0": 0.9}}}}
        ev = signals.update_state(state, rows, cfg, 1_800_000_000)
        self.assertEqual(len([e for e in ev if e["event"] == "ISSUED"]), 1)
        # e a tendencia diaria nao abre uma terceira
        from engine import paper_trend as P
        c = [{"t": k * 86400, "o": v, "h": v * 1.01, "l": v * 0.99, "c": v,
              "v": 1.0} for k, v in enumerate([100.0] * 220 + [104.0])]
        rw = [{"asset": "LINK", "price": 104.2, "venue": {"pair": "LINK/USDC"}}]
        out = P.update(state, rw, {"LINK": c}, dict(cfg, capital_usdc=500.0),
                       1_800_000_000)[1]
        self.assertEqual(out, [])


class FixedStake(unittest.TestCase):
    def plan(self, stop, lev=2.0, **kw):
        from engine import risk
        cfg = dict(config.load("nao-existe.json"), swing_leverage=lev, **kw)
        return risk.plan({"strategy": "X", "entry": [99.7, 100.0], "stop": stop},
                         T4.a4h(), T4.a1d(), cfg)

    def test_always_25_usdc_with_or_without_margin(self):
        for lev in (1.0, 2.0):
            p, _ = self.plan(98.0, lev)
            self.assertEqual(p["position_usdc"], 25.0)
            self.assertEqual(p["position_pct"], 50.0)
            self.assertEqual(p["partials"], [50, 30, 20])     # 12.5 / 7.5 / 5
            self.assertAlmostEqual(p["collateral_usdc"], 25.0 / lev, places=2)
        p, _ = self.plan(98.0)
        self.assertAlmostEqual(p["risk_usdc"], 25 * 0.02198, places=2)   # 0.55
        self.assertAlmostEqual(p["risk_pct"], 1.1, places=1)

    def test_wide_stop_shrinks_position_to_risk_limit(self):
        from engine import risk
        # stop a 9% -> 25 USDC arriscariam 2.3; a posicao encolhe para 2
        a4 = T4.a4h(atr=4.0, liquidity=dict(T4.a4h()["liquidity"],
                                            pools_above=[130.0, 150.0]),
                    swing_high=130.0)
        cfg = config.load("nao-existe.json")
        p, why = risk.plan({"strategy": "X", "entry": [99.7, 100.0],
                            "stop": 91.0}, a4, T4.a1d(), cfg)
        self.assertIsNone(why)
        self.assertLess(p["position_usdc"], 25.0)
        self.assertAlmostEqual(p["risk_usdc"], 2.0, places=2)
        p, _ = risk.plan({"strategy": "X", "entry": [99.7, 100.0], "stop": 93.0},
                         a4, T4.a1d(), cfg)
        self.assertEqual(p["position_usdc"], 25.0)
        self.assertLessEqual(p["risk_usdc"], 2.0)

    def test_live_decision_and_two_positions_use_whole_capital(self):
        orig = validation.load
        validation.load = lambda: None
        self.addCleanup(lambda: setattr(validation, "load", orig))
        cfg = config.load("nao-existe.json")
        for conflict in (None, "1D: médias e estrutura discordam"):
            r = T4.row()
            r["analysis"]["mtf_conflict"] = conflict
            p = signals.decide(r, T4.C4, cfg, T4.V, "BULL", False)["plan"]
            self.assertEqual(p["position_usdc"], 25.0)
        self.assertEqual(cfg["max_open_positions"] * cfg["fixed_position_usdc"],
                         cfg["capital_usdc"])

    def test_trend_uses_fixed_stake(self):
        from engine import paper_trend as P
        c = [{"t": k * 86400, "o": v, "h": v * 1.01, "l": v * 0.99, "c": v,
              "v": 1.0} for k, v in enumerate([100.0] * 220 + [104.0])]
        rw = [{"asset": "LINK", "price": 104.2, "venue": {"pair": "LINK/USDC"}}]
        ev = P.update({}, rw, {"LINK": c}, config.load("nao-existe.json"), 1)[1]
        self.assertEqual(ev[0]["position_usdc"], 25.0)
