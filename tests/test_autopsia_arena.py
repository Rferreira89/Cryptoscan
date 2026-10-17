"""A autopsia dos lutadores (tools/autopsia_arena.py) nao pode ver o futuro."""
import unittest

from tests.test_research_bounce import synth
from tools import autopsia_arena as A

H4 = A.H4
UP = {d: True for d in range(0, 400)}


def spy(seen):
    """Sinal simples (fecho acima do maximo anterior a cada 37 velas) que
    regista a ultima vela que lhe foi mostrada."""
    def f(c4):
        seen.append(c4[-1]["t"])
        b, p = c4[-1], c4[-2]
        if (b["t"] // H4) % 37 or b["c"] <= p["h"] * 0.99:
            return None
        return {"stop": b["c"] * 0.95, "tp": [b["c"] * 1.05], "partials": [100],
                "breakeven": True, "hold_s": 3 * 86400}
    return f


class NoLookAhead(unittest.TestCase):
    def test_signal_sees_only_closed_bars(self):
        c4, seen = synth(3), []
        tr = A.walk("AAA", c4, UP, spy(seen), 0, 10 ** 12)
        self.assertTrue(tr)
        for t in tr:                      # entrada na abertura da vela seguinte ao sinal
            self.assertEqual(t["t"], c4[t["i"]]["t"])
            self.assertIn(c4[t["i"] - 1]["t"], seen)
        self.assertLess(max(seen), c4[-1]["t"])

    def test_future_prices_change_nothing_before(self):
        a, b = synth(3), synth(3, scale_after=1000)
        ta = A.walk("AAA", a, UP, spy([]), 0, 10 ** 12)
        tb = A.walk("AAA", b, UP, spy([]), 0, 10 ** 12)
        lim = a[1000]["t"]
        done = lambda tr: [t for t in tr if t["t"] + t["dur_h"] * 3600 <= lim]
        self.assertTrue(done(ta))
        self.assertEqual(done(ta), done(tb))

    def test_truncating_history_keeps_closed_trades(self):
        c4 = synth(3)
        full = A.walk("AAA", c4, UP, spy([]), 0, 10 ** 12)
        cut = c4[:900]
        part = A.walk("AAA", cut, UP, spy([]), 0, 10 ** 12)
        end = cut[-1]["t"] + H4
        self.assertEqual(part, [t for t in full if t["t"] + t["dur_h"] * 3600 <= end])

    def test_window_respected(self):
        c4 = synth(3)
        t0, t1 = c4[400]["t"], c4[1200]["t"]
        for t in A.walk("AAA", c4, UP, spy([]), t0, t1):
            self.assertTrue(t0 <= c4[t["i"] - 1]["t"] + H4 < t1)


if __name__ == "__main__":
    unittest.main()
