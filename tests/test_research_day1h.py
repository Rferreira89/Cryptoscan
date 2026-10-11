"""A investigacao do day trade em 1H nao pode ver o futuro."""
import unittest

from tools import research_rlib as R
from tools.research_day1h import TF, signals, trend_4h

H4, DAY = 14400, 86400


def synth1(seed, n=3000, scale_after=None):
    bars, p, x = [], 100.0, seed
    for i in range(n):
        x = (x * 1103515245 + 12345) % 2 ** 31
        r = (x / 2 ** 31 - 0.46) * 0.012
        o, p = p, p * (1 + r)
        k = 3.0 if scale_after is not None and i > scale_after else 1.0
        bars.append({"t": i * TF, "o": o * k, "h": max(o, p) * 1.002 * k,
                     "l": min(o, p) * 0.998 * k, "c": p * k, "v": 1.0})
    return bars


def to4(c1):
    out = []
    for i in range(0, len(c1) - len(c1) % 4, 4):
        b = c1[i:i + 4]
        out.append({"t": b[0]["t"], "o": b[0]["o"], "h": max(x["h"] for x in b),
                    "l": min(x["l"] for x in b), "c": b[-1]["c"], "v": 4.0})
    return out


UP = {d: True for d in range(0, 200)}
A = synth1(5)


class NoLookAhead(unittest.TestCase):
    def test_signals_exist(self):
        self.assertGreater(len(signals(A, to4(A), UP, 1.5, 0.015)), 5)

    def test_truncating_future_changes_no_signal(self):
        sig = signals(A, to4(A), UP, 1.5, 0.015)
        for cut in (1001, 1502, 2203, 2500):
            part = signals(A[:cut], to4(A[:cut]), UP, 1.5, 0.015)
            self.assertEqual(part, {t: s for t, s in sig.items()
                                    if t <= A[cut - 1]["t"] + TF})

    def test_4h_context_is_a_closed_bar(self):
        """Uma vela de 4H ainda aberta no momento da decisao nao conta:
        alterar as velas de 4H que fecham depois da decisao nao muda nada."""
        c4 = to4(A)
        sig = signals(A, c4, UP, 1.5, 0.015)
        t = sorted(sig)[len(sig) // 2]
        alt = [dict(x) for x in c4]
        for x in alt:
            if x["t"] + H4 > t:               # ainda nao fechada em t
                for f in "ohlc":
                    x[f] *= 0.2
        s2 = signals(A, alt, UP, 1.5, 0.015)
        self.assertEqual({k: v for k, v in sig.items() if k <= t},
                         {k: v for k, v in s2.items() if k <= t})
        ts, st = trend_4h(c4)
        self.assertEqual(st[:300], trend_4h(c4[:300])[1])

    def test_future_prices_do_not_change_past_results(self):
        b = synth1(5, scale_after=2000)
        sa = signals(A, to4(A), UP, 1.5, 0.015)
        sb = signals(b, to4(b), UP, 1.5, 0.015)
        lim = A[2000]["t"] + TF
        ca, ta = R.simulate({"X": A}, {"X": sa}, TF, 24 * 3600, max_pos=2)
        cb, tb = R.simulate({"X": b}, {"X": sb}, TF, 24 * 3600, max_pos=2)
        self.assertTrue([t for t in ta if t["exit_t"] <= lim])
        self.assertEqual([t for t in ta if t["exit_t"] <= lim],
                         [t for t in tb if t["exit_t"] <= lim])
        d = lim // DAY
        self.assertEqual([x for x in ca if x[0] < d], [x for x in cb if x[0] < d])

    def test_min_stop_distance_and_single_target(self):
        sig = signals(A, to4(A), UP, 2.0, 0.025)
        _, tr = R.simulate({"X": A}, {"X": sig}, TF, 24 * 3600, max_pos=2)
        for t in tr:
            self.assertGreaterEqual(-t["geo"]["stop"], 0.025)
            self.assertAlmostEqual(t["geo"]["tp"][0], -2.0 * t["geo"]["stop"])
            self.assertEqual(A[t["i"]]["t"] in sig, True)
            self.assertLessEqual(t["exit_t"] - A[t["i"]]["t"], 24 * 3600)


if __name__ == "__main__":
    unittest.main()
