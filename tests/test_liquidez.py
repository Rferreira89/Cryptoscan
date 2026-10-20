import unittest

from engine import liquidez

D = 1_800_000_000 - (1_800_000_000 % 86400)


class HistoricoDeLiquidez(unittest.TestCase):
    def test_amostra_por_hora_e_mediana_ao_mudar_o_dia(self):
        h = {}
        h = liquidez.atualizar(h, {"ENA": [10000, 0.1, False]}, D + 3600)
        h = liquidez.atualizar(h, {"ENA": [99999, 9.9, True]}, D + 3700)      # menos de 1 hora: ignorada
        h = liquidez.atualizar(h, {"ENA": [20000, 0.3, True]}, D + 7300)
        h = liquidez.atualizar(h, {"ENA": [30000, 0.2, False]}, D + 10900)
        self.assertEqual(len(h["hoje"]["amostras"]["ENA"]), 3)
        h = liquidez.atualizar(h, {"ENA": [5000, 0.5, False]}, D + 86400 + 60)
        dia = list(h["dias"])[0]
        self.assertEqual(h["dias"][dia]["ENA"], [20000, 0.2, 0.33])
        self.assertEqual(len(h["hoje"]["amostras"]["ENA"]), 1)
        self.assertEqual(liquidez.atualizar(h, None, D), h)


if __name__ == "__main__":
    unittest.main()
