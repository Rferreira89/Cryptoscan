"""(04/11) Agente OKX: segue uma operacao com custos de futuros e calcula o tamanho para 20 USD."""
import unittest
from tools import okx_agente as A


class Agente(unittest.TestCase):
    def test_objetivo_com_custos_de_futuros(self):
        op = {"entrada": 1.0, "stop": 0.9, "alvo": 1.2, "risco": 0.1, "t_fill": 0, "visto": -1}
        fim = A.seguir(op, [{"t": 0, "o": 1.0, "h": 1.05, "l": 0.95, "c": 1.0}, {"t": A.H4, "o": 1.0, "h": 1.21, "l": 0.99, "c": 1.2}])
        self.assertEqual(fim[1], "objetivo")
        self.assertAlmostEqual(fim[0], 2.0 - (0.0002 + 0.0002 * 1.2) / 0.1, places=3)

    def test_stop_na_primeira_vela_so_se_abrir_acima(self):
        op = {"entrada": 1.0, "stop": 0.9, "alvo": 1.2, "risco": 0.1, "t_fill": 0, "visto": -1}
        self.assertEqual(A.seguir(op, [{"t": 0, "o": 0.95, "h": 1.0, "l": 0.85, "c": 0.9}])[1], "stop")

    def test_tamanho_para_20_usd(self):
        nom, mn, cabe = A.tamanho(20.0, 1.0, 0.92, {"ctVal": 1, "minSz": 1})
        self.assertAlmostEqual(nom, 2.5)
        self.assertTrue(cabe)
        self.assertFalse(A.tamanho(20.0, 1.0, 0.92, {"ctVal": 10, "minSz": 1})[2])


if __name__ == "__main__":
    unittest.main()


class Macro(unittest.TestCase):
    def test_entra_so_acima_da_media_a_subir(self):
        from tools import okx_macro as M
        sobe = [{"t": i, "c": 100 + i} for i in range(80)]
        entra, sai, forca, px, m = M.sinal(sobe)
        self.assertTrue(entra)
        self.assertFalse(sai)
        desce = [{"t": i, "c": 200 - i} for i in range(80)]
        entra, sai, *_ = M.sinal(desce)
        self.assertFalse(entra)
        self.assertTrue(sai)
        self.assertIsNone(M.sinal(sobe[:30]))
