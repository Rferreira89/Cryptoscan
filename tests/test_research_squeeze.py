"""A investigacao de compressao/expansao nao pode ver o futuro."""
import unittest

from tools.research import Series
from tools.research_squeeze import FEE, SLIP, boxes, run_squeeze


def synth(seed, n=420, quiet=()):
    bars, p, x = {}, 100.0, seed
    for d in range(n):
        x = (x * 1103515245 + 12345) % 2 ** 31
        r = (x / 2 ** 31 - 0.46) * 0.05
        for a, b in quiet:
            if a <= d < b:
                r *= 0.05
            if d == b:
                r = 0.06
        o, p = p, p * (1 + r)
        bars[d] = {"t": d * 86400, "o": o, "h": max(o, p) * 1.002,
                   "l": min(o, p) * 0.998, "c": p, "v": 1000.0}
    return bars


def world(cut=None, shock=None):
    raw = {"BTC": synth(1), "AAA": synth(2, quiet=[(340, 352), (385, 397)]),
           "BBB": synth(3, quiet=[(360, 372)])}
    if shock:
        for b in raw.values():
            for d in b:
                if d > shock:
                    for f in "ohlc":
                        b[d][f] *= 3
    if cut is not None:
        raw = {a: {d: v for d, v in b.items() if d <= cut} for a, b in raw.items()}
    return {a: Series(b) for a, b in raw.items()}


CFG = dict(N=10, q=0.4, H=5)
U = ["AAA", "BBB"]


class NoLookAhead(unittest.TestCase):
    def test_truncating_future_changes_nothing(self):
        full, tr = run_squeeze(world(), range(420), U, **CFG)
        self.assertTrue(tr, "o cenario sintetico tem de gerar operacoes")
        for cut in (353, 374, 400):
            part, _ = run_squeeze(world(cut), range(cut + 1), U, **CFG)
            self.assertEqual(part, full[:cut + 1])

    def test_changing_future_prices_changes_nothing_before(self):
        full, tr = run_squeeze(world(), range(420), U, **CFG)
        alt, tr2 = run_squeeze(world(shock=370), range(420), U, **CFG)
        self.assertEqual(alt[:371], full[:371])
        self.assertEqual([t for t in tr if t["exit_d"] <= 370],
                         [t for t in tr2 if t["exit_d"] <= 370])

    def test_box_excludes_signal_day(self):
        s = world()["AAA"]
        hi, lo, pct = boxes(s, 10)
        for i in (250, 352, 400):
            self.assertEqual(hi[i], max(s.h[i - 10:i]))
            self.assertEqual(lo[i], min(s.l[i - 10:i]))
        s2 = world(shock=352)["AAA"]
        self.assertEqual(boxes(s2, 10)[2][:353], pct[:353])

    def test_entry_is_next_open_after_signal(self):
        S = world()
        _, tr = run_squeeze(S, range(420), ["AAA"], **CFG)
        t, s = tr[0], S["AAA"]
        i, j = s.pos[t["entry_d"]], s.pos[t["exit_d"]]
        hi, _, pct = boxes(s, 10)
        self.assertGreater(s.c[i - 1], hi[i - 1])     # sinal no fecho anterior
        self.assertLess(pct[i - 1], 0.4)
        exp = s.o[j] * (1 - SLIP) * (1 - FEE) / (s.o[i] * (1 + SLIP) * (1 + FEE)) - 1
        self.assertAlmostEqual(t["ret"], exp, places=9)


if __name__ == "__main__":
    unittest.main()
