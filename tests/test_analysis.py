import math
import random
import unittest

from engine import analysis as A
from engine import indicators as I
from engine import scanner as S
from engine import structure as ST
from engine import validate as V

TF = 14400
NOW = 1_800_000_000


def walk(n=400, seed=1, drift=0.0):
    rnd, px, out = random.Random(seed), 100.0, []
    for i in range(n):
        o = px
        px = max(1.0, px * (1 + drift + rnd.gauss(0, 0.02)))
        h = max(o, px) * (1 + abs(rnd.gauss(0, 0.005)))
        l = min(o, px) * (1 - abs(rnd.gauss(0, 0.005)))
        out.append({"t": i * TF, "o": o, "h": h, "l": l, "c": px,
                    "v": 100 + rnd.random()})
    return out


def zigzag(points):
    """Velas que passam pelos pontos dados, 6 velas por perna."""
    out, t = [], 0
    for a, b in zip(points, points[1:]):
        for s in range(6):
            o = a + (b - a) * s / 6
            c = a + (b - a) * (s + 1) / 6
            out.append({"t": t * TF, "o": o, "h": max(o, c) + 0.01,
                        "l": min(o, c) - 0.01, "c": c, "v": 1.0})
            t += 1
    return out


class Indicators(unittest.TestCase):
    def test_constant_series(self):
        x = [50.0] * 300
        self.assertAlmostEqual(I.ema(x, 200)[-1], 50.0)
        self.assertAlmostEqual(I.sma(x, 20)[-1], 50.0)
        self.assertEqual(I.rsi(x)[-1], 50.0)

    def test_sma_known(self):
        self.assertEqual(I.sma([1, 2, 3, 4, 5], 3), [None, None, 2, 3, 4])

    def test_ema_known(self):
        # EMA(3) de 1..5: semente 2, k=0.5 -> 3, 4
        self.assertEqual(I.ema([1, 2, 3, 4, 5], 3), [None, None, 2, 3, 4])

    def test_rsi_extremes(self):
        up = [float(i) for i in range(1, 60)]
        self.assertEqual(I.rsi(up)[-1], 100.0)
        self.assertAlmostEqual(I.rsi(up[::-1])[-1], 0.0)
        r = I.rsi([c["c"] for c in walk()])
        self.assertTrue(all(0 <= v <= 100 for v in r if v is not None))

    def test_rsi_wilder_reference(self):
        # Exemplo classico de Wilder (14 periodos): primeiro RSI ~ 70.46
        px = [44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84,
              46.08, 45.89, 46.03, 45.61, 46.28, 46.28, 46.00, 46.03, 46.41,
              46.22, 45.64]
        r = I.rsi(px)
        self.assertAlmostEqual(r[14], 70.46, delta=0.1)
        self.assertAlmostEqual(r[15], 66.25, delta=0.1)

    def test_atr_constant_range(self):
        c = [{"t": i, "o": 10, "h": 11, "l": 9, "c": 10, "v": 1}
             for i in range(50)]
        self.assertAlmostEqual(I.atr(c)[-1], 2.0)

    def test_adx_trend_vs_chop(self):
        trend = [{"t": i, "o": 100 + i, "h": 101.5 + i, "l": 99.5 + i,
                  "c": 101 + i, "v": 1} for i in range(120)]
        chop = [{"t": i, "o": 100, "h": 101 + (i % 2), "l": 99 - (i % 2),
                 "c": 100, "v": 1} for i in range(120)]
        self.assertGreater(I.adx(trend)[-1], 60)
        self.assertLess(I.adx(chop)[-1], 15)

    def test_no_lookahead(self):
        """O valor em i nao pode mudar quando chegam velas futuras."""
        c = walk(320)
        close = [x["c"] for x in c]
        full = {"ema": I.ema(close, 50), "rsi": I.rsi(close),
                "atr": I.atr(c), "adx": I.adx(c)}
        for i in (60, 150, 250, 319):
            cut, cc = c[:i + 1], close[:i + 1]
            part = {"ema": I.ema(cc, 50)[-1], "rsi": I.rsi(cc)[-1],
                    "atr": I.atr(cut)[-1], "adx": I.adx(cut)[-1]}
            for k, v in part.items():
                self.assertAlmostEqual(v, full[k][i], places=9, msg=k)


class Structure(unittest.TestCase):
    def test_bullish(self):
        c = zigzag([100, 110, 105, 118, 112, 126, 120, 124])
        s = ST.analyse(c)
        self.assertEqual(s["trend"], "BULLISH")
        self.assertEqual(s["sequence"][-2:], ["HH", "HL"])

    def test_bearish(self):
        c = zigzag([130, 120, 125, 112, 118, 104, 110, 106])
        self.assertEqual(ST.analyse(c)["trend"], "BEARISH")

    def test_bos_and_choch(self):
        up = zigzag([100, 110, 105, 118, 112, 126, 120, 135])
        ev = ST.analyse(up)["event"]
        self.assertEqual((ev["type"], ev["direction"]), ("BOS", "UP"))
        rev = zigzag([100, 110, 105, 118, 112, 126, 120, 123, 104])
        ev = ST.analyse(rev)["event"]
        self.assertEqual((ev["type"], ev["direction"]), ("CHOCH", "DOWN"))

    def test_pivots_only_after_confirmation(self):
        c = walk(300, seed=7)
        for p in ST.swings(c):
            self.assertLessEqual(p["confirmed_i"], len(c) - 1)
            self.assertEqual(p["confirmed_i"], p["i"] + ST.K)
        # um topo nas ultimas K velas ainda nao pode existir
        c2 = c + [{"t": 300 * TF, "o": 1e6, "h": 1e6, "l": 1e6, "c": 1e6,
                   "v": 1}]
        self.assertFalse(any(p["price"] == 1e6 for p in ST.swings(c2)))

    def test_unclear_when_short(self):
        self.assertEqual(ST.analyse(walk(8))["trend"], "UNCLEAR")

    def test_patterns(self):
        mk = lambda o, h, l, c: {"t": 0, "o": o, "h": h, "l": l, "c": c, "v": 1}
        self.assertIn("ENGULFING_BULL",
                      ST.patterns([mk(10, 10.2, 9.4, 9.5), mk(9.4, 10.6, 9.3, 10.5)]))
        self.assertIn("ENGULFING_BEAR",
                      ST.patterns([mk(9.5, 10.1, 9.4, 10), mk(10.1, 10.2, 9.2, 9.3)]))
        self.assertIn("PIN_BAR_BULL",
                      ST.patterns([mk(10, 10.5, 9.5, 10), mk(10, 10.25, 9, 10.2)]))
        self.assertIn("DOJI", ST.patterns([mk(10, 11, 9, 10), mk(10, 10.5, 9.5, 10.01)]))
        self.assertIn("INSIDE_BAR",
                      ST.patterns([mk(10, 11, 9, 10.5), mk(10.2, 10.6, 9.6, 10.3)]))
        self.assertEqual(ST.patterns([mk(10, 10, 10, 10), mk(10, 10, 10, 10)]), [])
        # vela anterior quase sem corpo: nao e engolfo
        self.assertNotIn("ENGULFING_BULL",
                         ST.patterns([mk(10, 10.5, 9.5, 9.99), mk(9.9, 10.6, 9.8, 10.5)]))


class Analysis(unittest.TestCase):
    def test_short_history_refused(self):
        self.assertFalse(A.timeframe(walk(100))["ok"])

    def test_uptrend_and_downtrend(self):
        self.assertEqual(A.timeframe(walk(400, drift=0.004))["ema_trend"], "UP")
        self.assertEqual(A.timeframe(walk(400, drift=-0.004))["ema_trend"], "DOWN")

    def test_values_finite(self):
        a = A.timeframe(walk(400, seed=3))
        for k in ("ema20", "ema200", "adx", "rsi", "atr_pct"):
            self.assertTrue(math.isfinite(a[k]))

    def test_conflict_flag(self):
        m = A.multi({"1d": walk(400, drift=0.004), "4h": walk(400, drift=-0.004)})
        if m["4h"]["structure"] == "BEARISH":
            self.assertIsNotNone(m["mtf_conflict"])


class FakeSrc:
    def __init__(self, name, candles=None, fail=False):
        self.name, self._c, self._fail = name, candles, fail

    def candles(self, base, tf, limit=500):
        if self._fail:
            from engine.sources import SourceError
            raise SourceError("boom")
        tfs = {"4h": 14400, "1d": 86400}[tf]
        end = NOW - NOW % tfs - tfs          # ultima vela fechada
        n = len(self._c)
        return [dict(c, t=end - (n - 1 - i) * tfs)
                for i, c in enumerate(self._c)]


class Scanner(unittest.TestCase):
    row = {"asset": "X", "sources": ["a", "b"], "divergence_pct": 0.1}

    def test_deep_ok_and_fallback(self):
        c = walk(400)
        d = S.deep_check(dict(self.row), [FakeSrc("a", fail=True),
                                          FakeSrc("b", c)], NOW)
        self.assertIn("DATA SOURCE FALLBACK", d["flags"])
        self.assertEqual(d["timeframes"]["1d"]["source"], "b")
        self.assertTrue(d["analysis"]["1d"]["ok"])

    def test_invalid_data_blocks_analysis(self):
        c = walk(400); c[380]["h"] = c[380]["l"] / 2
        d = S.deep_check(dict(self.row), [FakeSrc("a", c)], NOW)
        self.assertEqual(d["data_status"], V.INVALID)
        self.assertIsNone(d["analysis"])
        self.assertEqual(d["data_quality"], 0)

    def test_all_sources_fail(self):
        d = S.deep_check(dict(self.row), [FakeSrc("a", fail=True)], 10)
        self.assertEqual(d["data_status"], V.INVALID)
        self.assertIsNone(d["analysis"])

    def test_stock_tokens_and_pegs_excluded(self):
        tk = lambda last, chg=1.0: {"base": "", "last": last, "bid": last * 0.9999,
                                    "ask": last * 1.0001, "vol_quote": 5e7,
                                    "chg_pct": chg}
        data = {"binance": {"MSTRB": tk(165.1), "NVDAB": tk(233), "U": tk(0.9996, 0.01),
                            "ARB": tk(0.2), "BNB": tk(600)},
                "okx": {"XMSTR": tk(165.2), "XRP": tk(1.001, 3.0)}}
        self.assertEqual({r["asset"] for r in S.build_universe(data)},
                         {"ARB", "BNB", "XRP"})


if __name__ == "__main__":
    unittest.main()
