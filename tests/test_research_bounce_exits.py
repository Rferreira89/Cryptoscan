"""A investigacao do Oversold Bounce com outras saidas (fila do Rui,
hipotese 3) nao pode ver o futuro, e as saidas V2/V3 nao passam o stop
para a entrada."""
import unittest

from tests.test_research_bounce import CR, UP, synth as _synth
from tools import research_rlib as R
from tools.research_bounce import signals
from tools.research_bounce_exits import TF, variant_signals

DAY = 86400


def synth(*a, **k):
    return [dict(x, tb=x["v"] / 2) for x in _synth(*a, **k)]


def comparable(sig, o=None):
    """Sinal sem a funcao do plano (avaliada a um preco fixo)."""
    out = {}
    for t, s in sig.items():
        s = dict(s)
        fn = s.pop("plan_fn", None)
        if fn is not None:
            s["plan_at"] = fn(o if o is not None else s["stop"] * 1.03)
        out[t] = s
    return out


class NoLookAhead(unittest.TestCase):
    def test_same_trigger_as_bounce(self):
        a = synth(2, crashes=CR)
        base = signals(a, UP, 30, False)
        for v in ("V2", "V3"):
            sig = variant_signals(a, UP, 30, v)
            self.assertTrue(sig)
            self.assertEqual(set(sig), set(base))

    def test_truncating_future_changes_no_signal(self):
        full = synth(2, crashes=CR)
        for v in ("V1", "V2", "V3"):
            sig = comparable(variant_signals(full, UP, 30, v))
            for cut in (705, 950, 1200):
                part = comparable(variant_signals(full[:cut], UP, 30, v))
                self.assertEqual(part, {t: s for t, s in sig.items()
                                        if t <= full[cut - 1]["t"] + TF}, v)

    def test_changing_future_prices_changes_nothing_before(self):
        a, b = synth(2, crashes=CR), synth(2, crashes=CR, scale_after=1000)
        lim = a[1000]["t"] + TF
        for v in ("V2", "V3"):
            sa, sb = variant_signals(a, UP, 30, v), variant_signals(b, UP, 30, v)
            self.assertEqual({t: s for t, s in sa.items() if t <= lim},
                             {t: s for t, s in sb.items() if t <= lim})
            _, ta = R.simulate({"AAA": a}, {"AAA": sa}, TF, 3 * DAY)
            _, tb = R.simulate({"AAA": b}, {"AAA": sb}, TF, 3 * DAY)
            self.assertTrue([t for t in ta if t["exit_t"] <= lim])
            self.assertEqual([t for t in ta if t["exit_t"] <= lim],
                             [t for t in tb if t["exit_t"] <= lim])

    def test_v2_v3_geometry(self):
        a = synth(2, crashes=CR)
        for v in ("V2", "V3"):
            sig = variant_signals(a, UP, 30, v)
            _, tr = R.simulate({"AAA": a}, {"AAA": sig}, TF, 3 * DAY)
            self.assertTrue(tr)
            for t in tr:
                g = t["geo"]
                self.assertFalse(g["breakeven"])
                self.assertEqual(g["partials"], [100])
                self.assertAlmostEqual(g["tp"][0], -2 * g["stop"], places=9)
                self.assertLess(a[t["i"]]["o"], sig[a[t["i"]]["t"]]["gate"])

    def test_no_breakeven_after_partial(self):
        bars = [{"t": i * TF, "o": 100.0, "h": 100.5, "l": 99.5, "c": 100.0,
                 "v": 1.0} for i in range(40)]
        bars[7] = dict(bars[7], h=106.0)              # toca o 1.o objetivo
        bars[8] = dict(bars[8], l=99.0)               # volta abaixo da entrada
        plan = {"stop": 95.0, "tp": [105.0, 120.0], "partials": [50, 50]}
        be, _ = R.run_trade(bars, 5, dict(plan, breakeven=True), TF, 3 * DAY)
        nb, _ = R.run_trade(bars, 5, dict(plan, breakeven=False), TF, 3 * DAY)
        self.assertEqual(be["exit_reason"], "BREAKEVEN")
        self.assertEqual(nb["exit_reason"], "TIME")


if __name__ == "__main__":
    unittest.main()
