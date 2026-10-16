"""Afinacao H5: o filtro de regime dos shorts so usa o ultimo dia ja fechado
do BTC (sem look-ahead) e o sinal filtrado e o do ringue."""
import unittest

from tools import arena_ringue as AR
from tools.afinacao_h05_short_queda import gated, gates

H4, DAY = AR.H4, AR.DAY


def btc_bars(days=320, top=200):
    """BTC sobe ate ao dia `top` e depois cai forte (regime de queda no fim)."""
    out, p, t = [], 100.0, 1_600_000_000 - 1_600_000_000 % DAY
    for k in range(days * 6):
        p *= 1.002 if k < top * 6 else 0.994
        out.append({"t": t + k * H4, "o": p, "h": p * 1.002, "l": p * 0.998, "c": p,
                    "v": 1.0, "tb": 0.5})
    return out


class H05(unittest.TestCase):
    def test_gate_ignores_future_days(self):
        full = btc_bars()
        gf = gates(full)
        for cut in (len(full) - 200, len(full) - 7, len(full) - 1):
            gp = gates(full[:cut])
            t_end = full[cut - 1]["t"] + H4          # fecho da ultima vela conhecida
            for name in ("Q", "S"):
                self.assertEqual(gp[name](t_end), gf[name](t_end))

    def test_gate_reaches_queda(self):
        g = gates(btc_bars())
        t_last = btc_bars()[-1]["t"] + H4
        self.assertTrue(g["Q"](t_last))
        self.assertTrue(g["S"](t_last))

    def test_gated_blocks_outside_regime(self):
        calls = []
        f = gated(lambda m4: calls.append(1) or {"ok": 1}, lambda t: False)
        self.assertIsNone(f([{"t": 0}]))
        self.assertEqual(calls, [])
        f = gated(lambda m4: {"ok": 1}, lambda t: True)
        self.assertEqual(f([{"t": 0}]), {"ok": 1})


if __name__ == "__main__":
    unittest.main()
