"""(12/11) Papel continuo transversal: so para a frente, entrada na abertura do dia seguinte quando existir, mesmas
regras do estudo, SHORT so com margem, nada preenchido com o futuro."""
import unittest

from tools import papel_transversal as P

D = 86400


def serie(n, f, v=1e7):
    return [{"t": i * D, "o": f(i), "h": f(i) * 1.01, "l": f(i) * 0.99, "c": f(i), "v": v, "n": 6} for i in range(n)]


class Papel(unittest.TestCase):
    def series(self, n):
        return {"BTC": serie(n, lambda i: 100 * 1.001 ** i), "AAA": serie(n, lambda i: 100 * 1.004 ** i),
                "BBB": serie(n, lambda i: 100 * 0.999 ** i)}

    def test_so_para_a_frente_e_sem_futuro(self):
        s = self.series(300)
        agora = 300 * D + 3600
        e = P.passo({}, s, set(), agora)
        self.assertEqual(e["ultimo_dia"], 299)
        novas = [o for o in e["abertas"] if o["sinal_dia"] == 299]
        self.assertTrue(novas)
        self.assertTrue(all(o["ent"] is None for o in novas))       # o dia 300 ainda nao existe: sem preco de entrada
        self.assertFalse(e["fechadas"])
        # dia seguinte: a entrada passa a ser conhecida
        s2 = self.series(302)
        e2 = P.passo(e, s2, set(), 302 * D + 3600)
        ab = [o for o in e2["abertas"] if o["sinal_dia"] == 299]
        self.assertTrue(all(o["ent"] == s2[o["a"]][300]["o"] for o in ab))

    def test_short_so_com_margem(self):
        s = self.series(300)
        e = P.passo({}, s, set(), 300 * D + 3600)
        self.assertFalse([o for o in e["abertas"] if o["lado"] == "SHORT"])

    def test_fecha_por_tempo_com_r(self):
        s = self.series(300)
        e = P.passo({}, s, set(), 300 * D + 3600)
        s3 = self.series(330)
        e3 = P.passo(e, s3, set(), 330 * D + 3600)
        fechou = [o for o in e3["fechadas"] if o["sinal_dia"] == 299]
        self.assertTrue(fechou)
        self.assertIn("r", fechou[0])
        self.assertIn(fechou[0]["k"], e3["resumo"])

    def test_sem_dinheiro(self):
        e = P.passo({}, self.series(300), set(), 300 * D + 3600)
        self.assertNotIn("usdc", str(e).lower())


if __name__ == "__main__":
    unittest.main()
