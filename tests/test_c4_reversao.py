"""C4: sem futuro (entrada na abertura seguinte; regime e indicadores so ate ao dia do sinal), stop com salto."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backtest", "estudos"))
import c4_reversao as C  # noqa: E402


def serie(closes):
    return [(i * 86400, c, c * 1.01, c * 0.99, c) for i, c in enumerate(closes)]


class TestC4(unittest.TestCase):
    def setUp(self):
        base = [100 + 0.1 * i for i in range(260)]
        self.I = C.indicadores(serie(base + [120, 119, 118, 117, 118.5, 119]))

    def test_sinal_v3_so_com_passado(self):
        t = 262                                       # 3.o fecho seguido em baixa (120 < 125.9, 119, 118)
        self.assertTrue(C.sinal(self.I, t, "V3", "LONG"))
        self.assertFalse(C.sinal(self.I, t - 1, "V3", "LONG"))

    def test_entrada_na_abertura_seguinte_e_saida_no_primeiro_fecho_em_alta(self):
        r, j = C.operacao(self.I, 262, "V3", "LONG")
        self.assertEqual(j, 264)                      # entra a 117 (abertura de 263); 1.o fecho em alta: 118.5
        risco = 2 * self.I["atr"][262]
        bruto = (118.5 - 117) / risco
        self.assertLess(r, bruto)                     # custos descontados
        self.assertGreater(r, 0)

    def test_stop_no_salto_sai_na_abertura(self):
        d = serie([100 + 0.1 * i for i in range(260)] + [120, 119, 118, 117])
        d.append((264 * 86400, 117, 117.5, 116.5, 117))
        d.append((265 * 86400, 100, 100.5, 99.5, 100))  # salto muito abaixo do stop
        I = C.indicadores(d)
        r, j = C.operacao(I, 262, "V3", "LONG")
        self.assertEqual(j, 265)
        self.assertLess(r, -1.0)                      # pior do que o stop: saiu na abertura

    def test_holm(self):
        self.assertEqual(C.holm([0.01, 0.04]), [0.02, 0.04])


if __name__ == "__main__":
    unittest.main()
