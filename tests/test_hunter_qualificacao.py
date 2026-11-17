"""(17/11) Motor de qualificacao: criterios A/B/C, estados, rejeicoes definitivas, suspensao por degradacao."""
import random
import unittest

try:
    import numpy  # noqa: F401
    from tools.hunter import qualificacao as Q
except ImportError:            # o Hunter precisa de numpy (o scanner corre a suite sem ele)
    Q = None

DIA = 86400


def ops_oos(n=200, media=0.3, dias=60, moedas=40, seed=1):
    rng = random.Random(seed)
    out = []
    for k in range(n):
        out.append({"r": rng.gauss(media, 1.0), "custos_r": 0.05, "t": 1_700_000_000 + (k * dias * DIA) // n,
                    "b": f"M{k % moedas}", "tier": "A", "stop_pct": 2.0, "regime3": "lateral"})
    return out


def papel(n=40, media=0.4, dias=20, seed=2):
    rng = random.Random(seed)
    return [{"r": rng.gauss(media, 0.5), "t_sinal": 1_800_000_000 + k * (dias * DIA) // n, "acontecimento": f"1H@{k}",
             "t_entrada": 1_800_000_000 + k * (dias * DIA) // n, "fechada_em": 1_800_000_000 + k * (dias * DIA) // n + 3600}
            for k in range(n)]


@unittest.skipIf(Q is None, "sem numpy")
class Qualificacao(unittest.TestCase):
    def test_oos_bom_passa(self):
        o = Q.avaliar_oos(ops_oos(), m_total=3)
        self.assertTrue(o["ok"], o["falhas"])

    def test_oos_negativo_poucos_dados_e_holm(self):
        self.assertFalse(Q.avaliar_oos(ops_oos(media=-0.3), 1)["ok"])
        o = Q.avaliar_oos(ops_oos(n=60), 1)
        self.assertTrue(Q.so_dados_insuficientes(o["falhas"]) or not o["ok"])
        self.assertIn("n=60", o["falhas"])
        o = Q.avaliar_oos(ops_oos(media=0.12, seed=4), m_total=200)
        self.assertTrue(any(f.startswith("p_holm") for f in o["falhas"]))

    def test_robustez_e_concentracao(self):
        ops = ops_oos(media=-0.05)
        for o in ops[:5]:
            o["r"] = 30.0                           # o resultado vem todo de 5 operacoes
        q = Q.avaliar_oos(ops, 1)
        self.assertIn("robustez:sem_melhores_operacoes", " ".join(q["falhas"]))
        ops = ops_oos(media=0.0)
        for o in ops:
            if o["b"] == "M1":
                o["r"] = 5.0
        q = Q.avaliar_oos(ops, 1)
        self.assertTrue(any("concentracao:moeda" in f or "sem_moedas" in f for f in q["falhas"]))
        q = Q.avaliar_oos([dict(o, custos_r=2.0) for o in ops_oos(media=0.2)], 1)
        self.assertIn("robustez:custos_mais_25pct", " ".join(q["falhas"]))

    def test_papel_conta_acontecimentos_e_nao_abertas(self):
        p = papel(n=40)
        dup = p + [dict(x, r=x["r"]) for x in p[:20]]             # 2.a entrada no mesmo acontecimento
        self.assertEqual(Q.avaliar_papel(dup)["acontecimentos"], 40)
        self.assertFalse(Q.avaliar_papel(papel(n=40, dias=10))["ok"])     # < 14 dias
        self.assertFalse(Q.avaliar_papel(papel(n=20))["ok"])
        self.assertFalse(Q.avaliar_papel([dict(x, r=None) for x in p])["ok"])   # sem resultado = aberta/sem dados
        self.assertTrue(Q.avaliar_papel(p)["ok"])
        self.assertFalse(Q.avaliar_papel(p, falhas_criticas=1)["ok"])

    def e(self, **kw):
        e = {"id": "x1", "estado": "PAPER_TRADING", "historico": [], "backtest": {"operacoes_por_semana": 20},
             "oos": {**Q.avaliar_oos(ops_oos(), 2)}, "papel": Q.avaliar_papel(papel())}
        e.update(kw)
        return e

    def test_maquina_de_estados(self):
        e = self.e()
        self.assertEqual(Q.decidir(e, True, False, False, [], papel())[0], "VALIDATION")
        self.assertEqual(Q.decidir(e, True, True, False, [], papel())[0], "APPROVED_REAL")
        self.assertEqual(Q.decidir(e, True, True, True, [], papel())[0], "ACTIVE_REAL")
        mau = self.e(oos=Q.avaliar_oos(ops_oos(media=-0.3), 2))
        self.assertEqual(Q.decidir(mau, True, True, True, [], papel())[0], "REJECTED")
        self.assertEqual(Q.decidir(self.e(estado="REJECTED", motivo="x"), True, True, True, [], papel())[0], "REJECTED")
        self.assertEqual(Q.decidir(self.e(id="e495d11739f6"), True, True, True, [], papel())[0], "REJECTED")
        pouco = self.e(papel=Q.avaliar_papel(papel(n=10)))
        self.assertEqual(Q.decidir(pouco, True, False, False, [], papel(n=10))[0], "PAPER_TRADING")
        lenta = self.e(backtest={"operacoes_por_semana": 2})
        self.assertEqual(Q.decidir(lenta, True, False, False, [], papel())[0], "PAPER_TRADING")   # nao gasta o teste

    def test_degradacao_suspende_so_essa(self):
        p = papel(n=40) + [dict(x, r=-1.0, acontecimento=f"1H@n{k}", fechada_em=1_900_000_000 + k) for k, x in enumerate(papel(n=40))]
        e = self.e()
        self.assertEqual(Q.decidir(e, True, True, True, [], p)[0], "SUSPENDED")
        reais = [{"r": -1.5}] * 12
        self.assertEqual(Q.decidir(e, True, True, True, reais, papel())[0], "SUSPENDED")


if __name__ == "__main__":
    unittest.main()
