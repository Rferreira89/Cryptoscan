"""Afinacao H8: o funding medio de 24h so usa liquidacoes ja feitas e o short
dos compradores apinhados devolve um plano valido no espelho."""
import unittest

from engine import short as SH
from tools import arena_ringue as AR
from tools.afinacao_h08_funding import GRID, funding_8h, short_funding_var

H4, DAY = AR.H4, AR.DAY
T0 = 1_600_000_000 - 1_600_000_000 % DAY


def bars(n=200):
    out = []
    for k in range(n):
        p = 100 + (2 if k % 5 < 2 else -2)
        if k == n - 1:
            p = 90                                  # fecho abaixo do minimo anterior
        out.append({"t": T0 + k * H4, "o": p, "h": p * 1.01, "l": p * 0.99, "c": p,
                    "v": 1.0, "tb": 0.5})
    return out


class H08(unittest.TestCase):
    def test_funding_only_past_and_per_8h(self):
        fr = [(T0 + k * 8 * 3600, 0.0001) for k in range(10)]
        t = T0 + 9 * 8 * 3600
        self.assertAlmostEqual(funding_8h(fr, t), 0.0001)
        fut = fr + [(t + 3600, 0.01)]
        self.assertAlmostEqual(funding_8h(fut, t), 0.0001)     # futuro ignorado
        fr4 = [(T0 + k * 4 * 3600, 0.0001) for k in range(20)]
        self.assertAlmostEqual(funding_8h(fr4, T0 + 19 * 4 * 3600), 0.0002)
        self.assertIsNone(funding_8h(fr, t + 2 * DAY))          # sem liquidacao recente

    def test_plan_on_mirror(self):
        c = bars()
        t = c[-1]["t"] + H4
        AR.CTX["asset"] = "XYZ"
        AR.CTX["funding"] = {"XYZ": [(t - 8 * 3600 * k, 0.0005) for k in range(3, -1, -1)]}
        sig = short_funding_var(*GRID["X4G2"])(SH.mirror(c))
        self.assertIsNotNone(sig)
        self.assertLess(1 / sig["stop"], 1e9)
        self.assertGreater(1 / sig["stop"], c[-1]["c"])          # stop real acima da entrada
        self.assertLess(1 / sig["tp"][0], c[-1]["c"])            # objetivo real abaixo
        AR.CTX["funding"] = {"XYZ": [(t - 8 * 3600 * k, 0.0001) for k in range(3, -1, -1)]}
        self.assertIsNone(short_funding_var(*GRID["X4G2"])(SH.mirror(c)))
        AR.CTX["funding"] = {}


if __name__ == "__main__":
    unittest.main()
