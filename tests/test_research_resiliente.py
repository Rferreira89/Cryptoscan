"""A hipotese RESILIENTE (2026-10-16) nao pode ver o futuro."""
import unittest

from tests.test_research_bounce import synth as _synth
from tools import research_rlib as R
from tools.research_resiliente import TF, btc_moves, signals

DAY = 86400
UP = {d: True for d in range(0, 400)}
JUMPS = range(300, 1500, 97)


def btc(scale_after=None):
    bars = _synth(1, scale_after=scale_after)
    for j in JUMPS:                      # velas de queda do BTC (-3%)
        b = bars[j]
        b["c"] = bars[j - 1]["c"] * 0.97
        b["l"] = min(b["l"], b["c"] * 0.998)
    return bars


def run(coin, b):
    return signals(coin, btc_moves(b), UP, 0.025)


class NoLookAhead(unittest.TestCase):
    def test_signals_exist(self):
        s = run(_synth(4), btc())
        self.assertTrue(s)
        for tc in s:
            self.assertIn(tc // TF - 1, JUMPS)

    def test_truncating_future_changes_no_signal(self):
        coin, b = _synth(4), btc()
        full = run(coin, b)
        for cut in (500, 900, 1300):
            part = run(coin[:cut], b[:cut])
            self.assertEqual(part, {t: s for t, s in full.items() if t <= coin[cut - 1]["t"] + TF})

    def test_changing_future_prices_changes_nothing_before(self):
        a, b = _synth(4), _synth(4, scale_after=1000)
        lim = a[1000]["t"] + TF
        sa, sb = run(a, btc()), run(b, btc(scale_after=1000))
        self.assertEqual({t: s for t, s in sa.items() if t <= lim},
                         {t: s for t, s in sb.items() if t <= lim})
        _, ta = R.simulate({"AAA": a}, {"AAA": sa}, TF, DAY)
        _, tb = R.simulate({"AAA": b}, {"AAA": sb}, TF, DAY)
        self.assertEqual([t for t in ta if t["exit_t"] <= lim],
                         [t for t in tb if t["exit_t"] <= lim])

    def test_resilience_rule(self):
        coin, b = _synth(4), btc()
        mv = btc_moves(b)
        for tc in run(coin, b):
            i = tc // TF - 1
            self.assertGreaterEqual(coin[i]["c"] / coin[i - 1]["c"] - 1, 0.25 * mv[coin[i]["t"]])


if __name__ == "__main__":
    unittest.main()
