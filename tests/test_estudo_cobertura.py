"""(19/11) Estudo de cobertura por regime: sem futuro, entrada na vela seguinte, custos da Bybit UE nos dois lados."""
import unittest

from tools import estudo_cobertura_regimes as EC

H4 = 14400


def velas(n, p=1.0):
    return [{"t": k * H4, "o": p, "h": p * 1.001, "l": p * 0.999, "c": p, "v": 1.0, "tb": 0.5} for k in range(n)]


class Simulacao(unittest.TestCase):
    def test_short_stop_com_salto_e_custos(self):
        c = velas(20)
        c[2].update(o=1.2, h=1.25)                       # abre acima do stop
        s = EC.simular(c, 0, -1, 1.1, None, 5 * 86400, 0.0)
        self.assertEqual(s["motivo"], "stop")
        self.assertLess(s["r"], -1)

    def test_juro_so_nos_shorts(self):
        c = velas(60)
        a = EC.simular(c, 0, -1, 1.5, None, 5 * 86400, 0.001)
        b = EC.simular(c, 0, -1, 1.5, None, 5 * 86400, 0.0)
        self.assertLess(a["r"], b["r"])
        L1 = EC.simular(c, 0, 1, 0.5, None, 5 * 86400, 0.001)
        L2 = EC.simular(c, 0, 1, 0.5, None, 5 * 86400, 0.0)
        self.assertEqual(L1["r"], L2["r"])

    def test_objetivo_a_menos_de_1r_nao_entra(self):
        c = velas(20)
        self.assertIsNone(EC.simular(c, 0, -1, 1.1, 0.95, 3 * 86400, 0.0))


class Regime(unittest.TestCase):
    def test_trocas_contadas(self):
        reg = {k * 86400: r for k, r in enumerate(["lateral"] * 10 + ["subida"] * 3 + ["lateral"] * 10)}
        e = EC.estudo_regime(reg)
        self.assertEqual(e["trocas"], 2)
        self.assertEqual(e["trocas_em_menos_de_7_dias"], 1)


if __name__ == "__main__":
    unittest.main()
