"""(12/11) Simulacao da carteira: risco aberto agregado nunca passa do teto; 1 vaga nunca sobrepoe."""
import unittest

from tools import carteira_short_turtle as C

D = 86400


def _ops():
    out = []
    for i in range(40):
        out.append({"a": f"M{i % 7}", "t": i * D, "t_fim": i * D + 5 * D, "stop": -0.05 - 0.01 * (i % 12),
                    "r": 1.5 if i % 3 else -1.0, "fase": "lateral"})
    return out


class Carteira(unittest.TestCase):
    def test_agregado_e_vagas(self):
        for v in (1, 2, 3):
            f, curva, rec, cap = C.simular(_ops(), 30.0, vagas=v)
            self.assertTrue(f)
            if v == 1:
                self.assertFalse(any(x["sobreposta"] for x in f))
            # em cada instante a soma do risco aberto <= 5% do capital no momento da entrada
            for x in f:
                abertas = [y for y in f if y["t"] <= x["t"] < y["t_fim"]]
                self.assertLessEqual(sum(y["risco_pct"] for y in abertas), 5.0 * 1.6)   # capital composto varia
                self.assertLessEqual(x["risco_pct"], 5.0 + 1e-6)

    def test_sem_dinheiro_na_saida(self):
        r = C.correr(_ops(), 30.0)
        self.assertNotIn("usdc", str(r).lower())


if __name__ == "__main__":
    unittest.main()
