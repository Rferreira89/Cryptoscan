import unittest
from tools import fetch_derivados as F


class Agrega(unittest.TestCase):
    def test_ultimo_oi_e_medias_por_vela_de_4h(self):
        L = [["2025-01-01 00:00:00", "BTCUSDT", "100", "1000", "0", "2.0", "1.0", "0.8"],
             ["2025-01-01 03:55:00", "BTCUSDT", "120", "1200", "0", "4.0", "3.0", "1.2"],
             ["2025-01-01 04:00:00", "BTCUSDT", "130", "1300", "0", "1.0", "1.0", "1.0"]]
        a = F.agrega(L)
        t0 = 1735689600
        self.assertEqual(sorted(a), [t0, t0 + 14400])
        v = a[t0]
        self.assertEqual((v[0], v[1], v[5]), (120.0, 1200.0, 2))
        self.assertAlmostEqual(v[2] / v[5], 3.0)
        self.assertAlmostEqual(v[4] / v[5], 1.0)
