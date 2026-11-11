"""(11/11) Risco REAL com o capital disponivel: ordem minima, distancia do stop, custos, agregado; planos da
TF-SHORT na OKX (nao ligados); tamanho do piloto Bybit. Dados sinteticos."""
import inspect
import unittest

from engine import piloto as P
from engine import viabilidade as V
from tools import okx_tfshort_plano as TP


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


class TFShortOKX(unittest.TestCase):
    INFO = {"inst": "DOGE-USD_UM_XPERP-1", "ctVal": 10.0, "minSz": 1.0, "lotSz": 1.0, "tick": 0.00001, "lever": 20}
    SIG = {"entrada": 0.0716, "atr": 0.0036, "w": 0.09, "t": 1793923200}

    def test_desligado_por_omissao(self):
        corpo, motivo = TP.plano_entrada("DOGE", self.SIG, self.INFO, 20.0, {})
        self.assertIsNone(corpo)
        self.assertIn("desligado", motivo)

    def test_short_com_stop_anexado_e_risco_real(self):
        corpo, res = TP.plano_entrada("DOGE", self.SIG, self.INFO, 20.0, {}, {"tfshort_real": True})
        self.assertEqual(corpo["side"], "sell")
        self.assertEqual(corpo["tdMode"], "isolated")
        self.assertGreater(float(corpo["attachAlgoOrds"][0]["slTriggerPx"]), self.SIG["entrada"])
        self.assertEqual(res["contratos"], 2.0)
        self.assertLess(res["risco_pct_no_stop"], 1.5)

    def test_minimo_do_contrato_nao_sobe_o_tamanho(self):
        info = dict(self.INFO, ctVal=1000.0)
        corpo, motivo = TP.plano_entrada("DOGE", self.SIG, info, 20.0, {}, {"tfshort_real": True})
        self.assertIsNone(corpo)
        self.assertIn("minimo do contrato", motivo)

    def test_tetos_de_posicoes_e_exposicao(self):
        cheio = {f"M{i}": {"nocional": 1.0} for i in range(5)}
        self.assertIn("maximo", TP.plano_entrada("DOGE", self.SIG, self.INFO, 20.0, cheio, {"tfshort_real": True})[1])
        grande = {"X": {"nocional": 9.5}}
        self.assertIn("exposicao", TP.plano_entrada("DOGE", self.SIG, self.INFO, 20.0, grande, {"tfshort_real": True})[1])

    def test_saida_so_reduz(self):
        s = TP.plano_saida("DOGE", self.INFO, 2.0)
        self.assertEqual(s["side"], "buy")
        self.assertTrue(s["reduceOnly"])

    def test_nada_ligado_a_execucao(self):
        import os
        raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(raiz, "tools", "okx_exec.py"), encoding="utf-8") as f:
            self.assertNotIn("okx_tfshort_plano", f.read())
        for m in (TP, V):
            src = inspect.getsource(m)
            for proibido in ("privado(", "urlopen", "/api/v5/trade"):
                self.assertNotIn(proibido, src)


if __name__ == "__main__":
    unittest.main()
