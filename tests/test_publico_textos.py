"""(05/11, auditoria do Rui) as copias publicas tambem limpam valores em moeda escritos dentro de textos."""
import unittest
from engine import publico


class Textos(unittest.TestCase):
    def test_diretriz_com_o_que_falta(self):
        t = "O objetivo é para ser atingido: levar a carteira a 100 USDC (faltam 77.55 USDC), e depois ao seguinte."
        self.assertNotIn("77.55", publico.limpar_texto(t)); self.assertNotIn("100 USDC", publico.limpar_texto(t))

    def test_motivo_com_tamanho_da_posicao(self):
        r = publico.state({"x": [{"reason": "plano: posição de 4.11 USDC abaixo da ordem mínima de 5 USDC com o capital atual"}]})
        self.assertNotIn("4.11", str(r)); self.assertIn("[valor]", str(r))

    def test_outros_textos_ficam_iguais(self):
        for t in ("RSI 30 na vela de 4H", "BTCUSDC acima da media de 200 dias", "2026-11-05 21:30", "stop 2xATR", "risco 1%"):
            self.assertEqual(publico.limpar_texto(t), t)

    def test_varios_formatos(self):
        for t in ("1 200,50 USD", "-3.92 USDC", "20 €", "5USDT", "0,45 EUR"):
            self.assertEqual(publico.limpar_texto(t), "[valor]", t)

    def test_scan_publico(self):
        out = publico.scan({"diretrizes": ["levar a carteira a 100 USDC (faltam 77.55 USDC)"], "conta": {"equity": 22}})
        self.assertNotIn("conta", out); self.assertNotIn("77.55", str(out)); self.assertTrue(out["_publico"])


if __name__ == "__main__":
    unittest.main()
