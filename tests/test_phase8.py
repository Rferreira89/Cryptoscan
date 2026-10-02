import datetime
import unittest

from engine import config, events, inbox, ledger, monitor, review, signals
from engine import validation
from tests import test_phase4 as T4

CFG = dict(config.DEFAULTS)
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
                "leverage": {"max_safe": 3.0}}
        sig = {"asset": "LINK", "pair": "LINK/USDC", "venue": "Bybit EU",
               "strategy": "PULLBACK", "timeframe": "4H / 1D", "score": 70,
               "mode": "REAL", "plan": plan}
        state = {"signals": {"k": sig}, "ledger": [
            {"id": "k", "kind": "4H", "asset": "LINK", "status": "OPEN"}]}
        run.deliver(CFG, state, [{"event": "ISSUED", "id": "k", "t": 1},
                                 {"event": "TP1", "id": "k", "price": 104.0,
                                  "sold_pct": 50}], [("daily", "relatório")])
        self.assertEqual(sent[0], ("relatório", None))
        self.assertIn("Alavancagem: não é necessária", sent[1][0])
        self.assertIn("3x", sent[1][0])
        self.assertEqual(sent[1][1]["inline_keyboard"][0][0]["callback_data"], "x|1|k")
        self.assertIsNone(sent[2][1])
        state["ledger"][0]["executed"] = False
        sent.clear()
        run.deliver(CFG, state, [{"event": "TP2", "id": "k", "price": 108.0,
                                  "sold_pct": 30}])
        self.assertEqual(sent, [])


if __name__ == "__main__":
    unittest.main()
