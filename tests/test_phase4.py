import copy
import unittest

from engine import config, confluence, regime, risk, signals, strategies, venue
from engine import scanner as S
from engine import sources
from tests.test_analysis import walk

CFG = dict(config.DEFAULTS)
mk = lambda o, h, l, c, v=10.0: {"t": 0, "o": o, "h": h, "l": l, "c": c, "v": v}


def a1d(**k):
    d = {"ok": True, "ema_trend": "UP", "structure": "BULLISH", "close": 110.0,
         "ema50": 100.0, "ema200": 90.0, "adx": 30.0, "atr_pctile": 50,
         "atr": 4.0, "swing_high": 130.0, "swing_low": 95.0, "liquidity": None}
    d.update(k)
    return d


def a4h(**k):
    d = {"ok": True, "ema_trend": "UP", "structure": "BULLISH", "close": 100.0,
         "ema20": 100.5, "ema50": 99.0, "atr": 1.0, "rsi": 48.0, "patterns": [],
         "event": None, "swing_high": 106.0, "swing_low": 97.0,
         "volume": {"rvol": 1.0, "flow_20": 0.05, "divergence": None},
         "liquidity": {"pools_above": [106.0, 109.0], "pools_below": [97.0],
                       "fvg_above": None, "fvg_below": None, "sweep": None,
                       "order_block": None, "equal_highs": None,
                       "equal_lows": None}}
    d.update(k)
    return d


class Format(unittest.TestCase):
    def test_px_str(self):
        f = strategies.px_str
        self.assertEqual(f(4.5758e-06), "0.0000045758")
        self.assertEqual(f(86416.01), "86416")
        self.assertEqual(f(14.889), "14.889")
        self.assertEqual(f(0.2525), "0.2525")
        self.assertEqual(f(176.28), "176.28")


class Regime(unittest.TestCase):
    def test_classes(self):
        c = lambda **k: regime.classify(a1d(**k))["regime"]
        self.assertEqual(c(), "STRONG BULL")
        self.assertEqual(c(adx=18.0), "BULL")
        self.assertEqual(c(ema_trend="DOWN", structure="BEARISH", close=80.0),
                         "STRONG BEAR")
        self.assertEqual(c(ema_trend="MIXED", structure="NEUTRAL", adx=15.0,
                           close=99.0), "RANGE")
        self.assertEqual(c(ema_trend="UP", structure="BEARISH"), "NEUTRAL")
        self.assertEqual(c(structure="UNCLEAR"), "UNCLEAR")
        self.assertEqual(c(ema_trend="MIXED", structure="NEUTRAL", adx=15.0,
                           close=99.0, atr_pctile=97), "HIGH VOLATILITY")
        self.assertEqual(regime.classify(None)["regime"], "UNCLEAR")

    def test_one_indicator_is_not_enough(self):
        # so as medias a subir, estrutura e preco contra: nao e BULL
        r = regime.classify(a1d(structure="BEARISH", close=95.0))["regime"]
        self.assertNotIn(r, regime.BULLISH)


BULL = {"regime": "BULL", "high_volatility": False}


class Strategies(unittest.TestCase):
    def c4(self, last, prev=None):
        base = [mk(104, 105, 103, 104)] * 18
        return base + [prev or mk(100.5, 100.8, 99.6, 99.8), last]

    def test_pullback_ready_and_waiting(self):
        ready = strategies.pullback(self.c4(mk(99.8, 101.2, 99.7, 101.0)),
                                    a4h(close=101.0), a1d(), BULL)
        self.assertEqual(ready["state"], "READY")
        self.assertLess(ready["stop"], 99.6)
        wait = strategies.pullback(self.c4(mk(99.8, 100.2, 99.5, 99.7)),
                                   a4h(close=99.7), a1d(), BULL)
        self.assertEqual(wait["state"], "WAITING")

    def test_pullback_needs_bull_regime_and_real_pullback(self):
        c = self.c4(mk(99.8, 101.2, 99.7, 101.0))
        self.assertIsNone(strategies.pullback(
            c, a4h(close=101.0), a1d(), {"regime": "NEUTRAL"}))
        flat = [mk(100, 101, 99.5, 100.5)] * 20
        self.assertIsNone(strategies.pullback(flat, a4h(close=100.5), a1d(), BULL))
        r = strategies.pullback(c, a4h(close=101.0, rsi=70.0), a1d(), BULL)
        self.assertIn("rejected", r)

    def test_breakout_filters(self):
        ev = {"type": "BOS", "direction": "UP", "level": 100.0, "bars_ago": 2}
        c = [mk(99, 99.5, 98.5, 99)] * 30 + [mk(99, 101, 99, 100.8),
                                             mk(100.8, 101, 100.1, 100.3),
                                             mk(100.3, 100.9, 100.2, 100.7)]
        rv = lambda v: (lambda j: v)
        r = strategies.breakout(c, a4h(close=100.7, event=ev), a1d(), BULL, rv(1.8))
        self.assertEqual(r["state"], "READY")
        self.assertEqual(r["stop"], 99.0)
        low = strategies.breakout(c, a4h(close=100.7, event=ev), a1d(), BULL, rv(0.9))
        self.assertIn("LOW VOLUME", low["rejected"])
        fake = strategies.breakout(c, a4h(close=99.5, event=ev), a1d(), BULL, rv(1.8))
        self.assertIn("FAKE BREAKOUT", fake["rejected"])
        ext = strategies.breakout(c, a4h(close=102.0, event=ev), a1d(), BULL, rv(1.8))
        self.assertEqual(ext["state"], "WAITING")       # nao perseguir o preco
        self.assertIn("MOVE EXTENDED", ext["notes"])
        bear = strategies.breakout(c, a4h(close=100.7, event=ev), a1d(),
                                   {"regime": "BEAR"}, rv(1.8))
        self.assertIn("rejected", bear)

    def test_sweep_requires_confirmation(self):
        c = [mk(100, 101, 99.5, 100)] * 30 + [mk(100, 100.2, 98.0, 99.9),
                                              mk(99.9, 100.8, 99.8, 100.6)]
        lq = lambda conf: dict(a4h()["liquidity"], sweep={
            "side": "LOW", "level": 99.0, "bars_ago": 1, "confirmed": conf})
        w = strategies.sweep(c, a4h(close=100.6, liquidity=lq(False)), a1d(), BULL)
        self.assertEqual(w["state"], "WAITING")
        r = strategies.sweep(c, a4h(close=100.6, liquidity=lq(True)), a1d(), BULL)
        self.assertEqual(r["state"], "READY")
        self.assertAlmostEqual(r["stop"], 97.7)
        self.assertIsNone(strategies.sweep(c, a4h(), a1d(), BULL))

    def test_range_only_in_lower_quarter(self):
        rg = {"regime": "RANGE"}
        c = [mk(100, 101, 99, 100)] * 19 + [mk(96, 97.2, 95.8, 97.0)]
        d = a1d(swing_low=95.0, swing_high=130.0)
        r = strategies.range_reversion(c, a4h(close=97.0), d, rg)
        self.assertEqual(r["targets"], [112.5, 130.0])
        self.assertIsNone(strategies.range_reversion(c, a4h(close=115.0), d, rg))
        self.assertIsNone(strategies.range_reversion(c, a4h(close=97.0), d, BULL))


class Risk(unittest.TestCase):
    def setup_(self, **k):
        s = {"strategy": "PULLBACK", "state": "READY", "entry": [99.7, 100.0],
             "stop": 98.0}
        s.update(k)
        return s

    def test_plan_numbers(self):
        p, why = risk.plan(self.setup_(), a4h(), a1d(), CFG)
        self.assertIsNone(why)
        self.assertEqual(p["entry_ref"], 100.0)          # pior preco da zona
        # perda por unidade: 2 + 0.001*(100+98) = 2.198 -> 2.198%
        self.assertAlmostEqual(p["stop_pct"], 2.2, places=1)
        self.assertEqual(p["tp"][0], 106.0)              # liquidez real
        self.assertGreaterEqual(p["rr"], 2.0)
        self.assertTrue(p["tp"][0] < p["tp"][1] < p["tp"][2])
        # 1% de risco / 2.198% de stop = 45.5% -> limitado a 25%
        self.assertEqual(p["position_pct"], 25.0)
        self.assertAlmostEqual(p["risk_pct"], 0.55, places=2)

    def test_risk_never_exceeds_config(self):
        for stop in (99.1, 98.0, 97.0, 96.5):
            p, _ = risk.plan(self.setup_(stop=stop), a4h(), a1d(), CFG)
            if p:
                self.assertLessEqual(p["risk_pct"], CFG["risk_pct"] + 0.01)
                self.assertLessEqual(p["position_pct"], CFG["max_position_pct"])

    def test_rejections(self):
        self.assertIn("curto", risk.plan(self.setup_(stop=99.6), a4h(), a1d(), CFG)[1])
        self.assertIn("largo", risk.plan(self.setup_(stop=95.0), a4h(), a1d(), CFG)[1])
        self.assertIn("invalido", risk.plan(self.setup_(stop=99.9), a4h(), a1d(), CFG)[1])
        near = a4h(liquidity=dict(a4h()["liquidity"], pools_above=[101.0]),
                   swing_high=101.0)
        self.assertIn("POOR R:R", risk.plan(self.setup_(), near, a1d(), CFG)[1])

    def test_projected_targets_are_flagged_and_ordered(self):
        empty = a4h(liquidity=dict(a4h()["liquidity"], pools_above=[]),
                    swing_high=None)
        p, _ = risk.plan(self.setup_(), empty, a1d(swing_high=None), CFG)
        self.assertEqual(p["tp_projected"], [1, 2, 3])
        self.assertAlmostEqual(p["rr_tp1"], 1.0, places=2)
        self.assertAlmostEqual(p["rr"], 2.0, places=2)
        self.assertAlmostEqual(p["rr_tp3"], 3.0, places=2)
        far = a4h(liquidity=dict(a4h()["liquidity"], pools_above=[120.0]),
                  swing_high=None)
        p, _ = risk.plan(self.setup_(), far, a1d(swing_high=None), CFG)
        self.assertTrue(p["tp"][0] < p["tp"][1] < p["tp"][2])


class Confluence(unittest.TestCase):
    def sc(self, **k):
        setup = {"strategy": "PULLBACK", "state": "READY"}
        plan = {"stop": 98.0, "tp_projected": [], "rr": 2.5}
        args = dict(a4=a4h(), mtf=None, reg={"regime": "STRONG BULL",
                    "high_volatility": False}, btc="BULL", deriv=None,
                    is_btc=False, changed=False)
        args.update(k)
        return confluence.score(setup, plan, args["a4"], args["mtf"], args["reg"],
                                args["btc"], args["deriv"], args["is_btc"],
                                args["changed"])

    def test_bounds_and_labels(self):
        s = self.sc()
        self.assertTrue(0 <= s["score"] <= 100)
        self.assertEqual(sum(confluence.WEIGHTS.values()), 100)
        self.assertEqual(confluence.classify(49), "NO TRADE")
        self.assertEqual(confluence.classify(50), "WATCHLIST")
        self.assertEqual(confluence.classify(65), "VALID SETUP")
        self.assertEqual(confluence.classify(75), "HIGH QUALITY")
        self.assertEqual(confluence.classify(85), "EXCEPTIONAL CONFLUENCE")

    def test_conflicts_lower_score_and_are_listed(self):
        base = self.sc()["score"]
        crowded = self.sc(deriv={"flags": ["CROWDED_LONGS"], "positioning": None})
        self.assertLess(crowded["score"], base)
        self.assertEqual(len(crowded["conflicts"]), 1)
        many = self.sc(mtf="4H bearish contra 1D bullish", btc="BEAR",
                       a4=a4h(volume={"rvol": 1, "flow_20": -0.1,
                                      "divergence": "BEARISH"}))
        self.assertEqual(len(many["conflicts"]), 3)
        self.assertLess(many["score"], base - 20)

    def test_missing_derivatives_is_neutral_not_bullish(self):
        self.assertEqual(self.sc()["families"]["derivatives"], 0.5)

    def test_regime_transition_reduces_confidence(self):
        self.assertLess(self.sc(changed=True)["score"], self.sc()["score"])


V = {"pair": "X/USDC", "last": 100.0, "volume_usd": 5e6, "spread_pct": 0.05,
     "stale": False, "url": "u"}


class Venue(unittest.TestCase):
    def test_checks(self):
        self.assertEqual(venue.check(None, 100, CFG),
                         (False, ["nao listado na Bybit UE"]))
        self.assertTrue(venue.check(V, 100.2, CFG)[0])
        self.assertFalse(venue.check(dict(V, spread_pct=0.9), 100, CFG)[0])
        self.assertFalse(venue.check(dict(V, volume_usd=10), 100, CFG)[0])
        self.assertFalse(venue.check(dict(V, stale=True), 100, CFG)[0])
        self.assertFalse(venue.check(V, 103.0, CFG)[0])     # preco diverge


def row(a4=None, a1=None, **k):
    r = {"asset": "X", "price": 100.0, "data_status": "VALID",
         "data_quality": 100, "liquidity_score": 80, "derivatives": None,
         "analysis": {"1d": a1 or a1d(), "4h": a4 or a4h(close=101.0),
                      "mtf_conflict": None}}
    r.update(k)
    return r


C4 = [mk(104, 105, 103, 104)] * 18 + [mk(100.5, 100.8, 99.6, 99.8),
                                      mk(99.8, 101.2, 99.7, 101.0)]


class Signals(unittest.TestCase):
    def test_long_and_hierarchy_order(self):
        d = signals.decide(row(), C4, CFG, V, "BULL", False)
        self.assertEqual(d["decision"], "LONG")
        self.assertEqual([c["n"] for c in d["checks"]], list(range(1, 11)))
        self.assertTrue(all(c["ok"] for c in d["checks"]))
        self.assertFalse(d["validated"])
        self.assertIsNone(d["confidence"]["historical_strategy_quality"])
        self.assertEqual(d["venue"]["pair"], "X/USDC")

    def test_critical_failures_give_no_trade(self):
        d = signals.decide(row(data_status="DATA INVALID"), C4, CFG, V, "BULL", False)
        self.assertEqual((d["decision"], len(d["checks"])), ("NO TRADE", 1))
        d = signals.decide(row(), C4, CFG, None, "BULL", False)
        self.assertEqual((d["decision"], d["reason"]),
                         ("NO TRADE", "nao listado na Bybit UE"))
        d = signals.decide(row(a1=a1d(structure="UNCLEAR")), C4, CFG, V, "BULL", False)
        self.assertEqual(d["decision"], "NO TRADE")
        self.assertEqual(d["checks"][-1]["n"], 3)
        d = signals.decide(row(a1=a1d(ema_trend="DOWN", structure="BEARISH",
                                      close=80.0)), C4, CFG, V, "BULL", False)
        self.assertEqual(d["decision"], "NO TRADE")          # sem shorts

    def test_waiting_is_watchlist_never_early_entry(self):
        c = C4[:-1] + [mk(99.8, 100.2, 99.5, 99.7)]
        d = signals.decide(row(a4=a4h(close=99.7)), c, CFG, V, "BULL", False)
        self.assertEqual((d["decision"], d["state"]), ("WATCHLIST", "WAITING"))

    def test_two_conflicts_block(self):
        r = row(a4=a4h(close=101.0, volume={"rvol": 1, "flow_20": -0.1,
                                            "divergence": "BEARISH"}))
        r["analysis"]["mtf_conflict"] = "1D: medias e estrutura discordam"
        d = signals.decide(r, C4, CFG, V, "BULL", False)
        self.assertEqual(d["decision"], "NO TRADE")
        self.assertIn("SIGNAL CONFLICT", d["reason"])

    def _rows(self, n=1):
        out = []
        for i in range(n):
            r = row(asset=f"A{i}")
            r["decision"] = signals.decide(r, C4, CFG, V, "BULL", False)
            out.append(r)
        return out

    def test_lifecycle(self):
        state, now = {}, 1_800_000_000
        rows = self._rows()
        ev = signals.update_state(state, rows, CFG, now)
        self.assertEqual([e["event"] for e in ev], ["ISSUED"])
        sig = next(iter(state["signals"].values()))
        frozen = copy.deepcopy(sig["plan"])
        self.assertEqual(sig["status"], "ACTIVE")
        self.assertIn("features", ev[0])                     # audit log
        # novo scan, mesmo setup: nao duplica nem altera niveis
        rows = self._rows(); rows[0]["price"] = 101.5
        self.assertEqual(signals.update_state(state, rows, CFG, now + 900), [])
        self.assertEqual(len(state["signals"]), 1)
        self.assertEqual(sig["plan"], frozen)
        # preco entra na zona
        rows = self._rows(); rows[0]["price"] = 100.9
        ev = signals.update_state(state, rows, CFG, now + 1800)
        self.assertEqual(ev[0]["event"], "TRIGGERED")

    def test_expiry_and_invalidation(self):
        now = 1_800_000_000
        for price, dt, status in ((101.5, 13 * 3600, "EXPIRED"),
                                  (90.0, 900, "INVALIDATED"),
                                  (120.0, 900, "INVALIDATED")):
            state = {}
            signals.update_state(state, self._rows(), CFG, now)
            rows = self._rows(); rows[0]["price"] = price
            rows[0]["decision"]["decision"] = "NO TRADE"
            ev = signals.update_state(state, rows, CFG, now + dt)
            self.assertEqual(ev[0]["event"], status, price)
            self.assertEqual(len([s for s in state["signals"].values()
                                  if s["status"] == "ACTIVE"]), 0)

    def test_max_simultaneous_signals(self):
        state = {}
        rows = self._rows(5)
        ev = signals.update_state(state, rows, CFG, 1_800_000_000)
        self.assertEqual(len(ev), CFG["max_new_signals"])
        self.assertEqual(sum(r["decision"]["decision"] == "WATCHLIST"
                             for r in rows), 2)

    def test_explain_fields(self):
        r = self._rows()[0]
        e = signals.explain(r)
        self.assertEqual(set(e), {"why", "why_now", "confirms", "invalidates",
                                  "main_risk", "would_change"})


class Config(unittest.TestCase):
    def test_defaults_safe(self):
        c = config.load("nao-existe.json")
        self.assertEqual((c["risk_pct"], c["direction"], c["quote"]),
                         (1.0, "LONG_ONLY", "USDC"))
        self.assertFalse(c["alerts_unvalidated"])


class EndToEnd(unittest.TestCase):
    """scanner.run completo com fontes simuladas (sem rede)."""

    def test_run_offline(self):
        now = 1_800_000_000

        class Src:
            name = "binance"

            def tickers(self):
                t = lambda last: {"base": "", "last": last, "bid": last * 0.9999,
                                  "ask": last * 1.0001, "vol_quote": 5e8,
                                  "chg_pct": 1.0}
                return {"BTC": t(100.0), "AAA": t(50.0), "NOEU": t(5.0)}

            def candles(self, base, tf, limit=500):
                tfs = sources.TF_SECONDS[tf]
                end = now - now % tfs - tfs
                c = walk(400, seed=len(base), drift=0.002)
                return [dict(x, t=end - (399 - i) * tfs, tb=x["v"] * 0.5)
                        for i, x in enumerate(c)]

        orig = (sources.ALL, venue.fetch, S.add_derivatives)
        sources.ALL = [Src()]
        venue.fetch = lambda q: {"BTC": dict(V, pair="BTC/USDC"),
                                 "AAA": dict(V, pair="AAA/USDC", last=50.0)}
        S.add_derivatives = lambda rows, now: {"ok": False, "error": "offline"}
        self.addCleanup(lambda: (setattr(sources, "ALL", orig[0]),
                                 setattr(venue, "fetch", orig[1]),
                                 setattr(S, "add_derivatives", orig[2])))
        res, state, events = S.run(now=now, state={}, cfg=dict(CFG))
        assets = {r["asset"] for r in res["universe"]}
        self.assertEqual(assets, {"BTC", "AAA"})        # NOEU fora: nao listado
        for r in res["universe"]:
            self.assertIn(r["decision"]["decision"], ("LONG", "WATCHLIST", "NO TRADE"))
            self.assertNotIn("_c4", r)
        import json
        json.dumps(res); json.dumps(state); json.dumps(events)
        self.assertIn("BTC", state["regimes"])
        # segunda passagem com o mesmo estado nao rebenta nem duplica
        res2, state, _ = S.run(now=now + 900, state=state, cfg=dict(CFG))
        self.assertLessEqual(len(res2["active_signals"]), CFG["max_new_signals"])

    def test_venue_down_means_no_trade(self):
        now = 1_800_000_000
        orig = (sources.ALL, venue.fetch, S.add_derivatives)

        class Src:
            name = "binance"

            def tickers(self):
                return {"BTC": {"base": "", "last": 100.0, "bid": 99.99,
                                "ask": 100.01, "vol_quote": 5e8, "chg_pct": 1.0}}

            def candles(self, base, tf, limit=500):
                tfs = sources.TF_SECONDS[tf]
                end = now - now % tfs - tfs
                return [dict(x, t=end - (399 - i) * tfs)
                        for i, x in enumerate(walk(400))]

        def boom(q):
            raise sources.SourceError("coingecko 429")
        sources.ALL, venue.fetch = [Src()], boom
        S.add_derivatives = lambda rows, now: {"ok": False}
        self.addCleanup(lambda: (setattr(sources, "ALL", orig[0]),
                                 setattr(venue, "fetch", orig[1]),
                                 setattr(S, "add_derivatives", orig[2])))
        res, _, events = S.run(now=now, state={}, cfg=dict(CFG))
        self.assertEqual(res["status_global"], "DEGRADED")
        self.assertEqual(res["universe"][0]["decision"]["decision"], "NO TRADE")
        self.assertEqual(events, [])


if __name__ == "__main__":
    unittest.main()
