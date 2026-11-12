"""(11/11) Risco REAL com o capital disponivel: ordem minima, distancia do stop, custos, agregado; planos da
TF-SHORT na OKX (nao ligados); tamanho do piloto Bybit. Dados sinteticos."""
import unittest

from engine import piloto as P
from engine import viabilidade as V


class RiscoReal(unittest.TestCase):
    def test_ordem_minima_impoe_o_risco(self):
        r = V.bybit_min(20, 0.11, 5.0, 0.5, spread=0.001)
        self.assertTrue(r["forcado_pela_ordem_minima"])
        self.assertAlmostEqual(r["perda_usdc"], 5 * (0.11 + 2 * 0.0035 + 0.001), places=4)
        self.assertGreater(r["perda_pct"], 2.5)                  # nunca os 0,5% teoricos

    def test_sem_juro_confirmado_fica_marcado(self):
        self.assertFalse(V.bybit_min(20, 0.1, juro_dia_pct=None)["juro_confirmado"])

    def test_stop_maximo_para_o_teto(self):
        s = V.stop_max_para(20, 0.5)
        self.assertLess(s, 0.02)                                 # com 0,5% so stops < 2% cabem na ordem minima
        r = V.bybit_min(20, s, 5.0, 0.0001, teto_pct=0.5)
        self.assertTrue(r["cabe_no_teto"])

    def test_agregado(self):
        self.assertAlmostEqual(V.agregado([2.0, 2.0, 2.0]), 6.0)
        self.assertAlmostEqual(V.agregado([3.0, 4.0], correlacao=0.0), 5.0)


class PilotoBybit(unittest.TestCase):
    def test_entra_dentro_do_teto_e_recusa_fora(self):
        noc, r = P.sizing_bybit(20, 0.11, 5.0, teto_pct=3.9)
        self.assertEqual(noc, 5.0)
        self.assertLess(r, 3.9)
        noc, motivo = P.sizing_bybit(20, 0.20, 5.0, teto_pct=3.9)
        self.assertIsNone(noc)
        self.assertIn("acima do teto", motivo)

    def test_agregado_bloqueia_a_terceira(self):
        noc, motivo = P.sizing_bybit(20, 0.12, 5.0, teto_pct=3.9, abertas_pct=(3.5, 3.5), teto_agregado_pct=8.0)
        self.assertIsNone(noc)
        self.assertIn("agregado", motivo)

    def test_ordem_minima_maior_que_o_capital(self):
        noc, motivo = P.sizing_bybit(4, 0.05, 5.0, teto_pct=50)
        self.assertIsNone(noc)

    def test_limites_em_r(self):
        self.assertAlmostEqual(P.limites_usdc(20, 20, 0.5), -8.0)


if __name__ == "__main__":
    unittest.main()
