"""(21/11) Familia venda_repique (short para o piloto): so SHORT, sem olhar para a frente, so em tendencia de baixa."""
import unittest

import numpy as np

from tools.hunter import familias as F

P = {"ema": 50, "k": 6, "x": 0.03, "tendencia": 300}


def serie(n=600, seed=3):
    rng = np.random.default_rng(seed)
    c = 100 * np.exp(np.cumsum(rng.normal(-0.002, 0.02, n)))
    h = c * (1 + np.abs(rng.normal(0, 0.01, n)))
    return {"c": c, "h": h, "o": c, "l": c * 0.99, "v": np.ones(n)}


class VendaRepique(unittest.TestCase):
    def test_so_short(self):
        lg, sh = F.venda_repique(serie(), {}, P)
        self.assertEqual(len(lg), 0)
        self.assertGreater(len(sh), 0)

    def test_sem_olhar_para_a_frente(self):
        S = serie()
        _, sh = F.venda_repique(S, {}, P)
        for corte in (450, 520, 580):
            S2 = {k: v[:corte] for k, v in S.items()}
            _, sh2 = F.venda_repique(S2, {}, P)
            self.assertEqual(sh2.tolist(), [i for i in sh.tolist() if i < corte])

    def test_condicoes(self):
        S = serie()
        _, sh = F.venda_repique(S, {}, P)
        e, t = F._ema(S["c"], 50), F._ema(S["c"], 300)
        for i in sh:
            self.assertTrue(i >= 300 and S["c"][i] < t[i] and S["h"][i] >= e[i] and S["c"][i] < e[i])
            self.assertGreater(S["c"][i] / S["c"][i - 6] - 1, 0.03)

    def test_em_subida_nao_vende(self):
        n = 600
        c = 100 * np.exp(np.linspace(0, 1.5, n)) * (1 + 0.03 * np.sin(np.arange(n) / 3))
        S = {"c": c, "h": c * 1.01, "o": c, "l": c * 0.99, "v": np.ones(n)}
        self.assertEqual(len(F.venda_repique(S, {}, P)[1]), 0)

    def test_registada(self):
        self.assertIn("venda_repique", F.FAMILIAS)
        self.assertIn("venda_repique", F.HIPOTESES)
        self.assertEqual(F.GRUPO["venda_repique"], "G")


if __name__ == "__main__":
    unittest.main()
