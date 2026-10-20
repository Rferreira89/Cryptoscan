"""A hipotese IMPULSO_AMPLITUDE (2026-10-20) nao pode ver o futuro."""
import math
import unittest

from tools import research_rlib as R
from tools import research_impulso as I

TF, DAY = I.TF, 86400
UP = {d: True for d in range(0, 400)}


def market(n_coins=22, n=1500, scale_after=None):
    """Moedas com um fator comum lento (ondas) e ruido proprio."""
    out = {}
    for a in range(n_coins):
        bars, p, x = [], 100.0, a + 1
        for i in range(n):
            x = (x * 1103515245 + 12345) % 2 ** 31
            r = 0.012 * math.sin(i / 25.0) + (x / 2 ** 31 - 0.5) * 0.01
            o, p = p, p * (1 + r)
            k = 3.0 if scale_after is not None and i > scale_after else 1.0
            bars.append({"t": i * TF, "o": o * k, "h": max(o, p) * 1.003 * k,
                         "l": min(o, p) * 0.997 * k, "c": p * k, "v": 1000.0})
        out[f"C{a:02d}"] = bars
    return out


def sigs(data, u=0.75):
    return I.all_signals(data, u, UP, True)


def upto(s, lim):
    return {a: {t: v for t, v in d.items() if t <= lim} for a, d in s.items()}


class NoLookAhead(unittest.TestCase):
    def test_signals_exist(self):
        s = sigs(market())
        self.assertGreater(sum(len(v) for v in s.values()), 10)

    def test_truncating_future_changes_no_signal(self):
        data = market()
        full = sigs(data)
        for cut in (500, 900, 1300):
            part = sigs({a: b[:cut] for a, b in data.items()})
            lim = cut * TF            # fecho da ultima vela conhecida
            self.assertEqual(part, upto(full, lim))

    def test_changing_future_prices_changes_nothing_before(self):
        a, b = market(), market(scale_after=1000)
        lim = 1001 * TF
        sa, sb = sigs(a), sigs(b)
        self.assertEqual(upto(sa, lim), upto(sb, lim))
        _, ta = R.simulate(a, sa, TF, 5 * DAY)
        _, tb = R.simulate(b, sb, TF, 5 * DAY)
        self.assertEqual([t for t in ta if t["exit_t"] <= lim],
                         [t for t in tb if t["exit_t"] <= lim])

    def test_thrust_rule(self):
        data = market()
        st = {a: I.above_ma(c) for a, c in data.items()}
        amp = I.breadth(st)
        for t in I.thrusts(amp, 0.75):
            self.assertGreaterEqual(amp[t], 0.75)
            self.assertLess(amp[t - TF], 0.75)
            prev = [amp[x] for x in amp if t - I.LOOK * TF <= x < t]
            self.assertLessEqual(min(prev), I.LOW)
        for a, d in sigs(data).items():
            for tc, s in d.items():
                self.assertTrue(st[a][tc - TF][0])      # moeda acima da SMA20


if __name__ == "__main__":
    unittest.main()
