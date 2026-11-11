import copy
import random
import unittest

from tools import filtro_rentabilidade as F

H4, DAY = 4 * 3600, 86400


def _ops(n=80, mu=0.3, sd=0.5, seed=1, stop=6.0, asset="AAA", lado="LONG", t0=1_700_000_000):
    rng = random.Random(seed)
    out = []
    for i in range(n):
        t = t0 + i * 2 * DAY
        out.append({"asset": asset, "lado": lado, "t": t, "t_fim": t + DAY, "r": round(rng.gauss(mu, sd), 4),
                    "stop_pct": stop})
    return out


class TestCustos(unittest.TestCase):
    def test_spread_acima_do_simulado(self):
        sp = {"AAA": 0.45, "BTC": 0.01}
        self.assertAlmostEqual(F.custo_extra_r({"asset": "AAA", "stop_pct": 5.0}, sp), 0.25 / 5.0)
        self.assertEqual(F.custo_extra_r({"asset": "BTC", "stop_pct": 5.0}, sp), 0.0)
        self.assertAlmostEqual(F.custo_extra_r({"asset": "AAA", "stop_pct": 1.0}, sp), 0.25)   # stop curto: 5x

    def test_juro_do_short(self):
        op = {"asset": "BTC", "stop_pct": 10.0, "lado": "SHORT", "t": 0, "t_fim": 4 * DAY}
        self.assertAlmostEqual(F.custo_extra_r(op, {"BTC": 0.01}), 0.05 * 4 / 10.0)

    def test_custo_total(self):
        self.assertAlmostEqual(F.custo_total_pct("X", {"X": 0.14}), 0.64)

    def test_spreads_de_liquidez(self):
        liq = {"dias": {"d1": {"A": [1, 0.1, 0]}, "d2": {"A": [1, 0.3, 0]}, "d3": {"A": [1, 0.2, 0]}}}
        self.assertAlmostEqual(F.spreads(liq)["A"], 0.2)


class TestEstimador(unittest.TestCase):
    def test_so_conta_operacoes_fechadas(self):
        e = F.Estimador()
        e.juntar({"t": 0, "t_fim": 100, "r": 1.0})
        e.juntar({"t": 0, "t_fim": 500, "r": -1.0})
        e.avancar(200)
        self.assertEqual(e.estimativa()["k"], 1)
        e.avancar(600)
        self.assertEqual(e.estimativa()["k"], 1)         # a mesma vela: um so acontecimento
        self.assertAlmostEqual(e.estimativa()["media_crua"], 0.0)

    def test_encolhimento_para_zero(self):
        e = F.Estimador()
        for i in range(5):
            e.juntar({"t": i * H4, "t_fim": i * H4 + 1, "r": 1.0})
        e.avancar(10 ** 9)
        s = e.estimativa()
        self.assertAlmostEqual(s["mu"], 5 / 15)
        self.assertLess(s["lb"], s["mu"])


class TestDecisao(unittest.TestCase):
    def test_sem_historia_rejeita(self):
        d = F.avaliar({"A": _ops(n=15, mu=2.0)}, {})
        self.assertTrue(all(not r["aceite"] for r in d))
        self.assertEqual(d[-1]["motivo"], "historia insuficiente")

    def test_vantagem_clara_passa_e_negativa_nunca(self):
        d = F.avaliar({"BOA": _ops(mu=0.6, sd=0.4), "MA": _ops(mu=-0.2, sd=0.4, seed=2, asset="BBB")}, {})
        boa = [r for r in d if r["estrategia"] == "BOA"]
        ma = [r for r in d if r["estrategia"] == "MA"]
        self.assertTrue(any(r["aceite"] for r in boa[30:]))
        self.assertFalse(any(r["aceite"] for r in ma))

    def test_stop_curto_e_spread_alto_rejeitam_a_mesma_vantagem(self):
        sp = {"AAA": 0.6}
        largo = F.avaliar({"A": _ops(mu=0.4, sd=0.3, stop=8.0)}, sp)
        curto = F.avaliar({"A": _ops(mu=0.4, sd=0.3, stop=0.8)}, sp)
        self.assertGreater(sum(r["aceite"] for r in largo), 0)
        self.assertEqual(sum(r["aceite"] for r in curto), 0)

    def test_sem_look_ahead(self):
        """Mudar o resultado de operacoes que fecham depois de uma entrada nao
        muda a decisao dessa entrada."""
        ops = _ops(n=60, mu=0.5, sd=0.4)
        d1 = F.avaliar({"A": ops}, {})
        ops2 = copy.deepcopy(ops)
        corte = ops2[40]["t"]
        for o in ops2:
            if o["t_fim"] > corte:
                o["r"] = -5.0
        d2 = F.avaliar({"A": ops2}, {})
        for a, b in zip(d1, d2):
            if a["t"] <= corte:
                self.assertEqual(a["aceite"], b["aceite"])
                self.assertEqual(a["lb"], b["lb"])

    def test_filtro_so_tira_operacoes(self):
        d = F.avaliar({"A": _ops(mu=0.5), "B": _ops(mu=0.0, seed=3, asset="C")}, {"C": 0.5})
        c = F.comparar(d)["total"]
        self.assertEqual(c["aceites"]["n"] + c["rejeitadas"]["n"], c["sem_filtro"]["n"])
        self.assertLessEqual(c["aceites"]["n"], c["sem_filtro"]["n"])

    def test_queda_maxima(self):
        rows = [{"t_fim": i, "r_liquido": x} for i, x in enumerate([1, -1, -1, 2, -3])]
        self.assertEqual(F.queda_maxima(rows), -3.0)

    def test_veredicto_por_estrategia(self):
        r = F.por_estrategia({"POS": _ops(mu=0.5, sd=0.3), "NEG": _ops(mu=-0.5, sd=0.3, seed=4),
                              "ZERO": _ops(n=25, mu=0.0, sd=1.0, seed=5)}, {})
        self.assertEqual(r["POS"]["veredicto"], "POSITIVA")
        self.assertEqual(r["NEG"]["veredicto"], "NEGATIVA")
        self.assertEqual(r["ZERO"]["veredicto"], "INCONCLUSIVA")
        self.assertFalse(r["NEG"]["hoje"]["aceita"])


if __name__ == "__main__":
    unittest.main()
