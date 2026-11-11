import random
import unittest

from tools import n_efetivo_lutadores as N

DAY = 86400


class TestNEfetivo(unittest.TestCase):
    def test_clones_contam_uma_vez(self):
        rng = random.Random(9)
        a = [[d * DAY, "X", rng.gauss(0, 1)] for d in range(200)]
        b = [list(x) for x in a]                          # clone exato
        c = [[d * DAY, "Y", rng.gauss(0, 1)] for d in range(200)]
        r = N.calcular({"A": a, "B": b, "C": c})
        self.assertEqual(r["n_efetivo"]["M"], 3)
        self.assertLess(r["n_efetivo"]["participacao"], 2.2)
        self.assertGreater(r["n_efetivo"]["participacao"], 1.6)
        self.assertEqual(r["pares_mais_correlacionados"][0][:2], ["A", "B"])

    def test_poucos_dados_fica_de_fora(self):
        r = N.calcular({"A": [[0, "X", 1.0]] * 5, "B": [[d * DAY, "X", d % 3] for d in range(50)],
                        "C": [[d * DAY, "X", (d * 7) % 5] for d in range(50)]})
        self.assertNotIn("A", r["lutadores"])


if __name__ == "__main__":
    unittest.main()
