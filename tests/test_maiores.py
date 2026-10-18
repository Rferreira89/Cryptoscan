import unittest

from tools import arena_ringue as AR

H4 = 14400


def subida(n=1500, dip=True):
    out, p, t = [], 100.0, 1_600_000_000
    for i in range(n):
        if dip and n - 8 <= i < n - 1:
            c = p * 0.975                      # recuo de 7 velas
        elif dip and i == n - 1:
            c = p * 1.03                       # vela de viragem
        else:
            c = p * (1.002 + (0.004 if i % 2 else -0.003))
        out.append({"t": t, "o": p, "h": max(p, c) * 1.002, "l": min(p, c) * 0.998, "c": c, "v": 1e6, "tb": 6e5})
        p, t = c, t + H4
    return out


class EquipaDasMaiores(unittest.TestCase):
    def setUp(self):
        AR.CTX.pop("daily", None)

    def test_recuo_so_nas_maiores(self):
        c4 = subida()
        AR.CTX["asset"] = "ETH"
        s = AR.sig_maiores_recuo(c4)
        self.assertIsNotNone(s)
        self.assertLess(s["stop"], c4[-1]["c"])
        self.assertGreater(s["tp"][0], c4[-1]["c"])
        AR.CTX["asset"] = "PEPE"
        self.assertIsNone(AR.sig_maiores_recuo(c4))

    def test_sem_tendencia_diaria_nada(self):
        c4 = subida()
        AR.CTX["asset"] = "BTC"
        AR.CTX["daily"] = {"BTC": [{"t": c4[0]["t"] + k * 86400, "o": 1, "h": 1, "l": 1, "c": 1.0}
                                   for k in range(150)]}     # menos de 200 dias
        self.assertIsNone(AR.sig_maiores_recuo(c4))
        AR.CTX.pop("daily")

    def test_funding_negativo_com_preco_a_aguentar(self):
        c4 = subida(dip=False)
        AR.CTX["asset"] = "SOL"
        t = c4[-1]["t"] + H4
        AR.CTX["funding"] = {"SOL": [(t - 3600, -0.0001)]}
        c4[-1] = dict(c4[-1], c=c4[-2]["h"] * 1.01, h=c4[-2]["h"] * 1.012)
        self.assertIsNotNone(AR.sig_maiores_funding(c4))
        AR.CTX["funding"] = {"SOL": [(t - 3600, 0.0001)]}
        self.assertIsNone(AR.sig_maiores_funding(c4))

    def test_registo_e_familia(self):
        from engine import promo, arena
        for k in ("MAIORES_RECUO", "MAIORES_TENDENCIA", "MAIORES_FUNDING", "SHORT_MAIORES_RECUO"):
            self.assertIn(k, AR.SINAIS)
            self.assertIn(k, promo.REAL_OK)
            self.assertNotEqual(arena.persona(k), k)
        self.assertEqual(promo.family("MAIORES_RECUO"), "maiores")
        self.assertEqual(promo.family("SHORT_MAIORES_RECUO"), "short")


if __name__ == "__main__":
    unittest.main()
