import math
import random
import unittest

from tools import estatistica_multipla as E

H4 = 4 * 3600


class TestNormal(unittest.TestCase):
    def test_inversa(self):
        for x in (-3.0, -1.2, 0.0, 0.7, 2.5):
            self.assertAlmostEqual(E.phi_inv(E.phi(x)), x, places=6)
        with self.assertRaises(ValueError):
            E.phi_inv(1.0)


class TestMultiplos(unittest.TestCase):
    def test_prob_falso_positivo_do_diario(self):
        self.assertAlmostEqual(E.prob_falso_positivo(26), 0.7364, places=3)
        self.assertEqual(E.prob_falso_positivo(0), 0.0)

    def test_holm_exemplo(self):
        res = E.holm([0.01, 0.04, 0.03, 0.005])
        adj = [round(x[1], 6) for x in res]
        self.assertEqual(adj, [0.03, 0.06, 0.06, 0.02])
        self.assertEqual([x[2] for x in res], [True, False, False, True])

    def test_holm_nunca_mais_permissivo_que_bonferroni_por_teste(self):
        rng = random.Random(1)
        ps = [rng.random() * 0.1 for _ in range(20)]
        for p, pa, _ in E.holm(ps):
            self.assertGreaterEqual(pa, p)

    def test_bh(self):
        res = E.benjamini_hochberg([0.001, 0.008, 0.039, 0.041, 0.042, 0.06, 0.074, 0.205], q=0.05)
        self.assertEqual([x[2] for x in res], [True, True, False, False, False, False, False, False])

    def test_p_acaso_nunca_zero(self):
        self.assertAlmostEqual(E.p_acaso(10, [0.0] * 99), 1 / 100)
        self.assertEqual(E.p_acaso(-10, [0.0] * 99), 1.0)


class TestCorrelacao(unittest.TestCase):
    def test_valores_proprios(self):
        lam = E.valores_proprios([[2.0, 1.0], [1.0, 2.0]])
        self.assertAlmostEqual(lam[0], 3.0, places=6)
        self.assertAlmostEqual(lam[1], 1.0, places=6)

    def test_n_efetivo_extremos(self):
        ident = [[1.0 if i == j else 0.0 for j in range(5)] for i in range(5)]
        r = E.n_efetivo_testes(ident)
        self.assertAlmostEqual(r["nyholt"], 5.0)
        self.assertAlmostEqual(r["participacao"], 5.0)
        uns = [[1.0] * 5 for _ in range(5)]
        r = E.n_efetivo_testes(uns)
        self.assertAlmostEqual(r["nyholt"], 1.0, places=4)
        self.assertAlmostEqual(r["participacao"], 1.0, places=4)

    def test_matriz_dias_vazios_contam_zero(self):
        nomes, m = E.matriz_correlacao({"a": {1: 1.0, 2: -1.0, 3: 1.0}, "b": {1: 1.0, 2: -1.0, 3: 1.0}})
        self.assertAlmostEqual(m[0][1], 1.0)


class TestSharpe(unittest.TestCase):
    def test_psr_e_dsr(self):
        rng = random.Random(3)
        xs = [0.1 + rng.gauss(0, 1) for _ in range(500)]
        p = E.psr(xs)
        self.assertGreater(p, 0.5)
        d1 = E.dsr(xs, 1, 0.01)
        d50 = E.dsr(xs, 50, 0.01)
        self.assertAlmostEqual(d1, p)
        self.assertLess(d50, d1)               # mais tentativas, menos confianca

    def test_sr_max_cresce_com_tentativas(self):
        self.assertLess(E.sr_max_esperado(10, 0.01), E.sr_max_esperado(100, 0.01))
        self.assertEqual(E.sr_max_esperado(1, 0.01), 0.0)


class TestPBO(unittest.TestCase):
    def test_ruido_da_pbo_alta(self):
        rng = random.Random(7)
        m = [[rng.gauss(0, 1) for _ in range(10)] for _ in range(200)]
        r = E.pbo_cscv(m, blocos=8)
        self.assertEqual(r["n_combinacoes"], 70)
        self.assertGreater(r["pbo"], 0.2)

    def test_vantagem_real_da_pbo_baixa(self):
        rng = random.Random(7)
        m = [[rng.gauss(0.5 if j == 0 else 0.0, 1) for j in range(10)] for _ in range(200)]
        self.assertLess(E.pbo_cscv(m, blocos=8)["pbo"], 0.05)

    def test_validacoes(self):
        with self.assertRaises(ValueError):
            E.pbo_cscv([[1.0]], blocos=2)
        with self.assertRaises(ValueError):
            E.pbo_cscv([[1.0, 2.0]] * 10, blocos=3)


class TestEventos(unittest.TestCase):
    def test_bounce_amplitude_tipo(self):
        t0 = 1791504000
        trs = [{"t": t0, "r": 0.5} for _ in range(14)] + [{"t": t0 - 23 * 86400, "r": 2.3},
                                                         {"t": t0 - 23 * 86400 + 8 * 3600, "r": 0.07}]
        r = E.resumo_eventos(trs)
        self.assertEqual(r["n_operacoes"], 16)
        self.assertEqual(r["n_acontecimentos"], 3)
        self.assertEqual(r["maior_acontecimento"], 14)
        r1 = E.resumo_eventos(trs, janela_s=86400)
        self.assertEqual(r1["n_acontecimentos"], 2)

    def test_n_necessario(self):
        self.assertEqual(E.n_necessario(1.0, 0.25), math.ceil(((E.phi_inv(0.95) + E.phi_inv(0.8)) * 4) ** 2))
        self.assertIsNone(E.n_necessario(1.0, 0.0))


def _mercado(n_moedas=10, n_velas=900, seed=2):
    """Moedas com o MESMO caminho de preco (correlacao 1)."""
    rng = random.Random(seed)
    px, path = 100.0, []
    for i in range(n_velas):
        o = px
        px *= math.exp(rng.gauss(0, 0.03))
        path.append({"t": 1700000000 + i * H4, "o": o, "h": max(o, px) * 1.01, "l": min(o, px) * 0.99, "c": px})
    return {f"M{k}": [dict(x) for x in path] for k in range(n_moedas)}


class TestAcasoAgrupado(unittest.TestCase):
    def test_agrupado_e_mais_largo_que_independente(self):
        bars = _mercado()
        geo = {"stop": -0.05, "tp": [0.05], "partials": [100], "breakeven": True, "max_hold_s": 3 * 86400}
        t = bars["M0"][450]["t"]
        trs = [{"t": t, "asset": a, "r": 0.0, "geo": geo} for a in bars]
        ind = E.acaso_agrupado(trs, bars, random.Random(1), reps=300, agrupar=False)
        agr = E.acaso_agrupado(trs, bars, random.Random(1), reps=300, agrupar=True)

        def sd(xs):
            mu = sum(xs) / len(xs)
            return math.sqrt(sum((x - mu) ** 2 for x in xs) / (len(xs) - 1))
        self.assertGreater(sd(agr["medias"]), 2 * sd(ind["medias"]))
        self.assertGreater(agr["p95"], ind["p95"])


if __name__ == "__main__":
    unittest.main()
