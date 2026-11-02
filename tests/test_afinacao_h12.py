"""Afinacao H12: o short da quebra do minimo de N velas so usa velas fechadas,
corre no espelho (fecho real abaixo do minimo das N anteriores), so dispara na
fase pedida e devolve um plano valido (stop 2 ATR42, objetivo k R)."""
import unittest
from unittest import mock

from engine import short as SH
from tools import arena_ringue as AR
from tools.afinacao_h12_short_min55 import GRID, atr_n, short_min

H4 = AR.H4
T0 = 1_600_000_000 - 1_600_000_000 % H4


def series(n=200, ultimo_c=None):
    """Moeda a oscilar entre 98 e 102; a ultima vela fecha em `ultimo_c`."""
    out = []
    for i in range(n):
        mid = 100 + (2 if i % 4 == 0 else -2 if i % 4 == 2 else 0)
        o, c = mid, mid + 0.5
        h, l = max(o, c) + 0.5, min(o, c) - 0.5
        if i == n - 1 and ultimo_c is not None:
            o, c = 100.0, ultimo_c
            h, l = 100.5, min(c, 100.0) - 0.2
        out.append({"t": T0 + i * H4, "o": o, "h": h, "l": l, "c": c, "v": 1.0, "tb": 0.5})
    return out


class H12(unittest.TestCase):
    def setUp(self):
        p = mock.patch.object(AR, "_fase_btc", return_value="lateral")
        self.fase = p.start()
        self.addCleanup(p.stop)

    def test_fires_on_break_of_low(self):
        c4 = series(ultimo_c=95.0)                         # minimo anterior = 97,5
        m4 = SH.mirror(c4)
        s = short_min(*GRID["S1"])(m4)
        self.assertIsNotNone(s)
        e = m4[-1]["c"]
        self.assertLess(s["stop"], e)                      # no espelho, stop abaixo
        risco = e - s["stop"]
        self.assertAlmostEqual(risco, 2 * atr_n(m4), places=9)
        self.assertAlmostEqual(s["tp"][0], e + 2 * risco, places=9)
        self.assertEqual(s["partials"], [100])
        self.assertEqual(s["hold_s"], 3 * AR.DAY)
        self.assertGreater(1 / s["stop"], 95.0)             # stop real acima da entrada
        self.assertLess(1 / s["tp"][0], 95.0)               # objetivo real abaixo
        s5 = short_min(*GRID["S5"])(m4)
        self.assertAlmostEqual(s5["tp"][0], e + 1.5 * risco, places=9)

    def test_no_signal_inside_range(self):
        m4 = SH.mirror(series(ultimo_c=99.0))               # nao quebra o minimo
        self.assertIsNone(short_min(*GRID["S1"])(m4))

    def test_only_in_phase(self):
        m4 = SH.mirror(series(ultimo_c=95.0))
        self.fase.return_value = "subida"
        self.assertIsNone(short_min(*GRID["S1"])(m4))
        self.assertIsNone(short_min(*GRID["S3"])(m4))
        self.fase.return_value = "queda"
        self.assertIsNone(short_min(*GRID["S1"])(m4))
        self.assertIsNotNone(short_min(*GRID["S3"])(m4))

    def test_no_lookahead(self):
        """O sinal na vela i so depende das velas ate i: acrescentar velas
        futuras nao muda o resultado da avaliacao feita em c4[:i+1]."""
        c4 = series(ultimo_c=95.0) + series(30)[:30]
        for x, k in zip(c4[200:], range(30)):
            x["t"] = T0 + (200 + k) * H4
            x["l"], x["c"] = 50.0, 50.0                     # futuro muito diferente
        m4 = SH.mirror(c4)
        f = short_min(*GRID["S1"])
        a = f(m4[:200])
        b = f(SH.mirror(c4[:200]))
        self.assertEqual(a, b)
        self.assertIsNotNone(a)

    def test_level_excludes_current_candle(self):
        """O minimo de referencia e o das N velas ANTERIORES (nao inclui a vela do sinal)."""
        c4 = series(ultimo_c=95.0)
        m4 = SH.mirror(c4)
        s = short_min(55)(m4)
        self.assertIn("97.5", s["gatilho"])


if __name__ == "__main__":
    unittest.main()
