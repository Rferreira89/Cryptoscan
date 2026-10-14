"""A investigacao da quebra com compradores agressivos (fila do Rui,
hipotese 5) nao pode ver o futuro."""
import unittest

from tests.test_research_bounce import synth as _synth
from tools import research_rlib as R
from tools.research_taker_breakout import TF, signals

DAY = 86400
UP = {d: True for d in range(0, 400)}


def synth(seed, n=1500, scale_after=None):
    bars = _synth(seed, n=n, scale_after=scale_after)
    x = seed
    for k, b in enumerate(bars):
        x = (x * 1103515245 + 12345) % 2 ** 31
        b["v"] = 1000.0 * (3.0 if k % 37 == 0 else 1.0)
        b["tb"] = b["v"] * (0.4 + 0.3 * x / 2 ** 31)
    return bars


class NoLookAhead(unittest.TestCase):
    def test_signals_exist(self):
        self.assertTrue(signals(synth(9), UP, 0.55))

    def test_truncating_future_changes_no_signal(self):
        full = synth(9)
        sig = signals(full, UP, 0.55)
        for cut in (400, 800, 1200):
            part = signals(full[:cut], UP, 0.55)
            self.assertEqual(part, {t: s for t, s in sig.items()
                                    if t <= full[cut - 1]["t"] + TF})

    def test_changing_future_prices_changes_nothing_before(self):
        a, b = synth(9), synth(9, scale_after=1000)
        lim = a[1000]["t"] + TF
        sa, sb = signals(a, UP, 0.55), signals(b, UP, 0.55)
        self.assertEqual({t: s for t, s in sa.items() if t <= lim},
                         {t: s for t, s in sb.items() if t <= lim})
        _, ta = R.simulate({"AAA": a}, {"AAA": sa}, TF, 3 * DAY)
        _, tb = R.simulate({"AAA": b}, {"AAA": sb}, TF, 3 * DAY)
        self.assertEqual([t for t in ta if t["exit_t"] <= lim],
                         [t for t in tb if t["exit_t"] <= lim])

    def test_rules(self):
        a = synth(9)
        for tc, s in signals(a, UP, 0.60).items():
            i = tc // TF - 1
            self.assertGreaterEqual(a[i]["tb"] / a[i]["v"], 0.60)
            self.assertGreater(a[i]["c"], max(x["h"] for x in a[i - 20:i]))
            self.assertLess(s["stop"], a[i]["c"])


if __name__ == "__main__":
    unittest.main()
