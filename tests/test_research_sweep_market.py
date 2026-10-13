"""O sucessor SWEEP_MERCADO nao pode ver o futuro: o sinal da vela i so usa
o candidato decidido no fecho de i e o dia do BTC ja fechado; a entrada e na
abertura de i+1 e, na variante B, so se essa abertura estiver no topo da
zona de entrada ou abaixo."""
import unittest

from tools import research_rlib as R
from tools.research_sweep_market import TF, signals

DAY = 86400


def bars(n=60, p=100.0):
    return [{"t": 10 * DAY + i * TF, "o": p, "h": p * 1.01, "l": p * 0.99,
             "c": p, "v": 1.0} for i in range(n)]


def cand(c4, i, strategy="LIQUIDITY_SWEEP", score=80, top=100.5):
    return {"i": i, "t": c4[i]["t"] + TF, "strategy": strategy,
            "score": score, "plan": {"entry_zone": [99.0, top],
                                     "stop": 95.0, "tp": [106.0, 112.0],
                                     "partials": [50, 50]}}


UP = {d: True for d in range(0, 100)}


class SweepMarket(unittest.TestCase):
    def test_entry_at_next_open_only(self):
        c4 = bars(250)
        sig = signals([cand(c4, 20)], c4, UP, "A", min_score=70)
        self.assertEqual(list(sig), [c4[21]["t"]])
        _, tr = R.simulate({"AAA": c4}, {"AAA": sig}, TF, 30 * DAY)
        self.assertTrue(tr)
        self.assertEqual(tr[0]["i"], 21)

    def test_filters(self):
        c4 = bars()
        cs = [cand(c4, 10, strategy="PULLBACK"), cand(c4, 20, score=60)]
        self.assertEqual(signals(cs, c4, UP, "A", min_score=70), {})
        c = cand(c4, 30)
        day = (c["t"] - DAY) // DAY              # ultimo dia fechado
        self.assertEqual(signals([c], c4, {d: d != day for d in UP}, "A",
                                 min_score=70), {})
        self.assertTrue(signals([c], c4, {d: d <= day for d in UP}, "A",
                                min_score=70))

    def test_variant_b_needs_open_inside_zone(self):
        c4 = bars()
        above = signals([cand(c4, 20, top=99.5)], c4, UP, "B", min_score=70)
        inside = signals([cand(c4, 20, top=100.5)], c4, UP, "B", min_score=70)
        a = signals([cand(c4, 20, top=99.5)], c4, UP, "A", min_score=70)
        self.assertIsNone(R.plan_at(next(iter(above.values())), 100.0))
        self.assertIsNotNone(R.plan_at(next(iter(inside.values())), 100.0))
        self.assertIsNotNone(R.plan_at(next(iter(a.values())), 100.0))

    def test_future_prices_do_not_change_past_trades(self):
        c4 = bars(200)
        c4[25] = dict(c4[25], h=107.0)
        cs = [cand(c4, 20), cand(c4, 120)]
        other = [dict(x) for x in c4]
        for x in other[100:]:
            for f in "ohlc":
                x[f] *= 1.5
        sa = signals(cs, c4, UP, "A", min_score=70)
        sb = signals(cs, other, UP, "A", min_score=70)
        _, ta = R.simulate({"AAA": c4}, {"AAA": sa}, TF, 30 * DAY)
        _, tb = R.simulate({"AAA": other}, {"AAA": sb}, TF, 30 * DAY)
        lim = c4[100]["t"]
        first = [t for t in ta if t["exit_t"] <= lim]
        self.assertTrue(first)
        self.assertEqual(first, [t for t in tb if t["exit_t"] <= lim])


if __name__ == "__main__":
    unittest.main()
