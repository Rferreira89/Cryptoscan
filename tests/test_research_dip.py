"""A investigacao de compra de quedas nao pode ver o futuro."""
import unittest

from tools.research import SLIP, FEE, Series
from tools.research_dip import run_dip, window


def synth(seed, n=330, crash=None):
    bars, p, x = {}, 100.0, seed
    for d in range(n):
        x = (x * 1103515245 + 12345) % 2 ** 31
        r = (x / 2 ** 31 - 0.47) * 0.04
        if crash and d in crash:
            r = -0.12
        o, p = p, p * (1 + r)
        bars[d] = {"t": d * 86400, "o": o, "h": max(o, p) * 1.01,
                   "l": min(o, p) * 0.99, "c": p, "v": 1000.0}
    return bars


def world(cut=None, shock=None):
    raw = {"BTC": synth(1), "AAA": synth(2, crash={250, 251, 290}),
           "BBB": synth(3, crash={270, 271})}
    if shock:
        for b in raw.values():
            for d in b:
                if d > shock:
                    for f in "ohlc":
                        b[d][f] *= 3
    if cut is not None:
        raw = {a: {d: v for d, v in b.items() if d <= cut} for a, b in raw.items()}
    return {a: Series(b) for a, b in raw.items()}


CFG = dict(k=2, H=5, asset_trend=False)


class NoLookAhead(unittest.TestCase):
    def test_truncating_future_changes_nothing(self):
        full, tr = run_dip(world(), range(330), ["AAA", "BBB"], **CFG)
        self.assertTrue(tr, "o cenario sintetico tem de gerar operacoes")
        for cut in (255, 272, 300):
            part, _ = run_dip(world(cut), range(cut + 1), ["AAA", "BBB"], **CFG)
            self.assertEqual(part, full[:cut + 1])

    def test_changing_future_prices_changes_nothing_before(self):
        full, tr = run_dip(world(), range(330), ["AAA", "BBB"], **CFG)
        alt, tr2 = run_dip(world(shock=280), range(330), ["AAA", "BBB"], **CFG)
        self.assertEqual(alt[:281], full[:281])
        self.assertEqual([t for t in tr if t["exit_d"] <= 280],
                         [t for t in tr2 if t["exit_d"] <= 280])

    def test_entry_is_next_open_after_signal(self):
        S = world()
        _, tr = run_dip(S, range(330), ["AAA"], **CFG)
        t, s = tr[0], S["AAA"]
        i = s.pos[t["entry_d"]]
        self.assertGreaterEqual((s.c[i - 4] - s.c[i - 1]) / s.atr[i - 1], 2)
        j = s.pos[t["exit_d"]]
        exp = s.o[j] * (1 - SLIP) * (1 - FEE) / (s.o[i] * (1 + SLIP) * (1 + FEE)) - 1
        self.assertAlmostEqual(t["ret"], exp, places=9)

    def test_window_is_24_months_with_6_holdout(self):
        import datetime as dt
        e = (dt.date(2026, 10, 1) - dt.date(1970, 1, 1)).days
        d0, ds, d1 = window(e)
        f = lambda d: str(dt.date(1970, 1, 1) + dt.timedelta(days=d))
        self.assertEqual((f(d0), f(ds), f(d1)),
                         ("2024-10-02", "2026-04-02", "2026-10-02"))


if __name__ == "__main__":
    unittest.main()
