"""Afinacao H4: os sinais do Bounce RSI 30 usados no teste do tempo maximo
sao os do ringue (tools/arena_ringue.sig_x30) e nao veem o futuro."""
import unittest

from tests.test_research_bounce import CR, UP, synth
from tools import arena_ringue as AR
from tools.afinacao_h04_tempo import TF, window, x30_signals


class H04(unittest.TestCase):
    def test_same_as_ring(self):
        a = synth(2, crashes=CR)
        sig = x30_signals(a, UP)
        self.assertTrue(sig)
        for t, s in sig.items():
            i = next(k for k, b in enumerate(a) if b["t"] + TF == t)
            ring = AR.sig_x30(a[:i + 1])
            self.assertEqual(s["stop"], ring["stop"])
            self.assertEqual(s["tp"], ring["tp"])

    def test_truncating_future_changes_no_signal(self):
        full = synth(2, crashes=CR)
        sf = x30_signals(full, UP)
        for cut in (len(full) // 2, len(full) - 40):
            part = x30_signals(full[:cut], UP)
            for t, s in part.items():
                self.assertEqual(s, sf[t])

    def test_window_18_months(self):
        d0, ds, d1 = window(20000)
        self.assertTrue(540 <= d1 - d0 <= 552)
        self.assertTrue(180 <= d1 - ds <= 186)


if __name__ == "__main__":
    unittest.main()
