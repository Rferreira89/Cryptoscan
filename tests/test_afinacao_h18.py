"""H18: controlos ao acaso alternativos (so para a frente e incondicional)."""
import random
import unittest

from engine import arena
from tools import afinacao_h18_controlo as H

H4 = 14400


def barras(n, t0=1_700_000_000):
    out, p = [], 100.0
    rng = random.Random(3)
    for k in range(n):
        o = p
        p = max(1.0, p * (1 + rng.uniform(-0.03, 0.031)))
        out.append({"t": t0 + k * H4, "o": o, "h": max(o, p) * 1.01, "l": min(o, p) * 0.99, "c": p, "v": 1})
    return out


GEO = {"stop": -0.05, "tp": [0.1, 0.25], "partials": [50, 50], "breakeven": True,
       "max_hold_s": 20 * 86400, "trail_r": 1.0}


class TestFaixa(unittest.TestCase):
    def test_para_a_frente_so_depois_da_entrada(self):
        c4 = barras(800)
        t = c4[400]["t"]
        lo, hi = H.faixa(c4, t, "F", 0, 0)
        self.assertEqual(lo, 401)
        self.assertEqual(hi, 400 + arena.WINDOW)

    def test_incondicional_nao_depende_do_sinal(self):
        c4 = barras(800)
        w0, w1 = c4[100]["t"], c4[700]["t"]
        a = H.faixa(c4, c4[200]["t"], "U", w0, w1)
        b = H.faixa(c4, c4[650]["t"], "U", w0, w1)
        self.assertEqual(a, b)
        self.assertEqual(a, (100, 699))

    def test_atual_reproduz_o_ringue(self):
        c4 = barras(800)
        t = c4[400]["t"]
        x = H.controlo(c4, t, GEO, random.Random(5), "S", 0, 0, reps=30)
        y = arena.control_rs(c4, t, GEO, "LONG", random.Random(5), reps=30)
        self.assertEqual(x, y)

    def test_sem_faixa_no_fim(self):
        c4 = barras(300)
        self.assertIsNone(H.faixa(c4, c4[-2]["t"], "F", 0, 0))

    def test_passa(self):
        self.assertTrue(H.passa({"n": 30, "avg_r": 0.2, "acaso_p95": 0.1}, 30))
        self.assertFalse(H.passa({"n": 30, "avg_r": 0.2, "acaso_p95": 0.3}, 30))
        self.assertFalse(H.passa({"n": 29, "avg_r": 0.2, "acaso_p95": 0.1}, 30))
        self.assertFalse(H.passa({"n": 40, "avg_r": -0.1, "acaso_p95": -0.5}, 30))


if __name__ == "__main__":
    unittest.main()
