import unittest
from engine import derivhist as D


def row(a, oi, px=10.0, liq=True):
    return {"asset": a, "price": px, "derivatives": {"oi_usd": oi, "funding_rate": 1e-4, "ls_ratio": 1.5,
            "oi_chg_24h_pct": 2.5, "basis_pct": -0.02,
            "liquidations": {"long_usd": 120000, "short_usd": 3000, "complete": liq}}}


class Historico(unittest.TestCase):
    def test_uma_amostra_por_hora_das_maiores(self):
        rows = [row(f"C{i}", 1e6 * (i + 1)) for i in range(25)] + [{"asset": "X", "price": 1}]
        h = D.atualizar({}, rows, 1000)
        self.assertEqual(len(h["moedas"]), D.MAX_MOEDAS)
        self.assertNotIn("C0", h["moedas"])                       # menos dinheiro aberto
        self.assertEqual(h["moedas"]["C24"][0], [1000, 10.0, 25, 100, 150, 120, 3, 250, -20])
        D.atualizar(h, rows, 1000 + 600)                          # menos de 1 h: nada
        self.assertEqual(len(h["moedas"]["C24"]), 1)
        D.atualizar(h, rows, 1000 + 3600)
        self.assertEqual(len(h["moedas"]["C24"]), 2)
        self.assertEqual(D.resumo(h)["amostras"], 40)

    def test_liquidacoes_incompletas_ficam_vazias_e_o_antigo_sai(self):
        h = D.atualizar({}, [row("BTC", 5e9, liq=False)], 0)
        self.assertIsNone(h["moedas"]["BTC"][0][5])
        D.atualizar(h, [row("ETH", 1e9)], D.DIAS * 86400 + 10)
        self.assertNotIn("BTC", h["moedas"])
        self.assertIn("ETH", h["moedas"])


if __name__ == "__main__":
    unittest.main()
