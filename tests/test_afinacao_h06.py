"""Afinacao H6: a variante curta das Tartarugas usa o mesmo gatilho do
TURTLE do ringue, so velas fechadas, e muda apenas stop/objetivos/tempo."""
import unittest

from tools import arena_ringue as AR
from tools.afinacao_h06_turtle_curta import GRID, turtle_core, turtle_var

H4, DAY = AR.H4, AR.DAY


def bars(n=400, brk=380):
    """Lateral com ruido e um rompimento forte na vela `brk`."""
    out, t = [], 1_600_000_000 - 1_600_000_000 % DAY
    for k in range(n):
        p = 100 + (3 if k % 7 < 3 else -3) + (15 if k >= brk else 0)
        out.append({"t": t + k * H4, "o": p, "h": p * 1.01, "l": p * 0.99, "c": p,
                    "v": 1.0, "tb": 0.5})
    return out


class H06(unittest.TestCase):
    def test_same_trigger_as_ringue_turtle(self):
        c = bars()
        base = turtle_var(2.0, (2.0, 5.0), (50, 50), 20, 1.0)
        hits = 0
        for i in range(200, len(c)):
            a, b = AR.sig_turtle(c[:i + 1]), base(c[:i + 1])
            self.assertEqual(bool(a), bool(b))
            if a:
                hits += 1
                self.assertAlmostEqual(a["stop"], b["stop"])
                self.assertEqual(a["tp"], b["tp"])
        self.assertGreaterEqual(hits, 1)

    def test_no_lookahead(self):
        c = bars()
        for i in range(200, len(c) - 1):
            # sinal da vela i so depende de c[:i+1]: mudar o futuro nao muda nada
            fut = [dict(x, c=x["c"] * 3, h=x["h"] * 3) for x in c[i + 1:]]
            self.assertEqual(turtle_core(c[:i + 1]), turtle_core((c[:i + 1] + fut)[:i + 1]))

    def test_short_exits(self):
        c = bars()
        i = 380
        for k, cfg in GRID.items():
            p = turtle_var(*cfg)(c[:i + 1])
            self.assertIsNotNone(p, k)
            self.assertLessEqual(p["hold_s"], 10 * DAY)
            self.assertEqual(len(p["tp"]), len(p["partials"]))
            self.assertLess(p["stop"], c[i]["c"])


if __name__ == "__main__":
    unittest.main()
