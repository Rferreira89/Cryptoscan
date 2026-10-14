"""A investigacao do funding negativo (fila do Rui, hipotese 4) nao pode ver
o futuro: nem velas, nem funding publicado depois do fecho da vela."""
import unittest

from tests.test_research_bounce import synth
from tools.research_funding import TF, f24_series, funding_state, signals

UP = {d: True for d in range(0, 400)}


def funding(n_bars, neg_from=(), seed=5):
    """Liquidacoes de 8h ao longo das velas; negativas perto das quedas."""
    out, x = [], seed
    for k in range(n_bars * TF // 28800):
        t = k * 28800
        x = (x * 1103515245 + 12345) % 2 ** 31
        v = 0.0001 + (x / 2 ** 31 - 0.5) * 0.0001
        if any(a * TF <= t < (a + 12) * TF for a in neg_from):
            v = -0.002
        out.append((t, v))
    return out


CR = (700, 900, 1100, 1300)


class NoLookAhead(unittest.TestCase):
    def setUp(self):
        self.bars = synth(3, crashes=CR)
        self.fr = funding(len(self.bars), CR)

    def test_signals_exist(self):
        self.assertTrue(signals(self.bars, f24_series(self.fr), UP, 10, True))

    def test_truncating_future_changes_nothing(self):
        full = signals(self.bars, f24_series(self.fr), UP, 10, False)
        for cut in (705, 905, 1110):
            tc = self.bars[cut - 1]["t"] + TF
            part = signals(self.bars[:cut],
                           f24_series([x for x in self.fr if x[0] <= tc]),
                           UP, 10, False)
            self.assertEqual(part, {t: s for t, s in full.items() if t <= tc})

    def test_future_funding_is_ignored(self):
        lim = self.bars[1000]["t"] + TF
        fr2 = [(t, v if t <= lim else -0.01) for t, v in self.fr]
        a = signals(self.bars, f24_series(self.fr), UP, 5, False)
        b = signals(self.bars, f24_series(fr2), UP, 5, False)
        self.assertEqual({t: s for t, s in a.items() if t <= lim},
                         {t: s for t, s in b.items() if t <= lim})
        self.assertNotEqual(a, b)

    def test_state_uses_only_published(self):
        f24 = f24_series(self.fr)
        tc = 950 * TF
        st = funding_state(f24, tc, 10)
        st2 = funding_state([x for x in f24 if x[0] <= tc], tc, 10)
        self.assertEqual(st, st2)

    def test_needs_history(self):
        f24 = f24_series(self.fr)
        self.assertIsNone(funding_state(f24, 30 * 86400, 10))


if __name__ == "__main__":
    unittest.main()
