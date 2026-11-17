"""(17/11) Calibracao OKX: operacoes do mesmo sinal (mesma vela de 4H) nao sao independentes. O desempenho passa a
mostrar quantas velas de sinal ha e o intervalo de 95% agrupado por vela, sem mudar o alerta nem as decisoes."""
import unittest

from tools import okx_agente as A


def op(t, r, tipo="mercado"):
    return {"asset": "X", "t_sig": t, "r": r, "tipo": tipo}


class IcPorSinal(unittest.TestCase):
    def test_grupo_grande_alarga_intervalo(self):
        # 15 operacoes de um so panico (todas -1R) mais 6 sinais soltos
        f = [op(1, -1.0) for _ in range(15)] + [op(t, r) for t, r in ((2, 2.0), (3, -1.0), (4, 1.0), (5, -1.0),
                                                                      (6, 2.0), (7, -1.0))]
        d = A.metricas_sinais(f)
        self.assertEqual(d["n"], 21)
        self.assertEqual(d["sinais"], 7)
        lo, hi = d["ic95"]
        glo, ghi = d["ic95_sinais"]
        self.assertLess(glo, lo)
        self.assertGreater(ghi, hi)
        self.assertAlmostEqual((glo + ghi) / 2, d["r_medio"], places=2)

    def test_independentes_parecido_com_o_normal(self):
        f = [op(t, r) for t, r in enumerate([1, -1, 2, -1, -1, 0.5, -1, 2, -1, 1.5])]
        d = A.metricas_sinais(f)
        self.assertEqual(d["sinais"], 10)
        lo, hi = d["ic95"]
        glo, ghi = d["ic95_sinais"]
        # com um sinal por operacao o intervalo agrupado e o habitual
        self.assertAlmostEqual(glo, lo, places=3)
        self.assertAlmostEqual(ghi, hi, places=3)

    def test_poucos_sinais_sem_intervalo(self):
        d = A.metricas_sinais([op(1, -1.0), op(1, 2.0), op(2, -1.0)])
        self.assertEqual(d["sinais"], 2)
        self.assertIsNone(d["ic95_sinais"])

    def test_vazio(self):
        self.assertEqual(A.metricas_sinais([]), {"n": 0})

    def test_alerta_igual_mas_com_grupos(self):
        f = [op(1, -1.0) for _ in range(15)] + [op(t, -1.0 if t % 2 else 0.5) for t in range(2, 9)]
        st = {"fechadas": f, "desempenho": {"mercado": A.metricas_sinais(f)}}
        antes = A.metricas([x["r"] for x in f])
        self.assertEqual(st["desempenho"]["mercado"]["ic95"], antes["ic95"])   # decisao usa o mesmo intervalo
        m = A.alerta_vantagem(st)
        self.assertIn("🚨", m)
        self.assertIn("8 velas de sinal", m)


if __name__ == "__main__":
    unittest.main()
