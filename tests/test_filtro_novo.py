import random
import unittest

from tools import arena_ringue as AR
from engine import promo, arena

DAY = 86400
NOW = 1_800_000_000


def trs(rs, step_days=1.0, asset="AAA", t0=NOW - 300 * DAY):
    return [{"t": int(t0 + i * step_days * DAY), "asset": asset, "r": r} for i, r in enumerate(rs)]


class FiltroNovo(unittest.TestCase):
    def test_dias_distintos_e_reservado(self):
        q = AR.qualidade(trs([0.5] * 40, step_days=0.1), NOW)    # 40 operacoes em 4 dias
        self.assertLessEqual(q["dias"], 5)
        q = AR.qualidade(trs([0.6, -0.2] * 40, step_days=3.5), NOW)
        self.assertGreaterEqual(q["dias"], 30)
        self.assertGreater(q["reservado"]["n"], 0)
        self.assertIsNotNone(q["ic_inf"])

    def test_passa_novo_exige_mais_que_o_atual(self):
        met = [0.3, 0.3]
        poucos_dias = AR.qualidade(trs([0.4] * 25, step_days=0.2), NOW)
        self.assertTrue(AR.passa_atual(25, 0.4, 0.1, met))
        self.assertFalse(AR.passa_novo(25, 0.4, 0.1, met, poucos_dias))
        bom = AR.qualidade(trs([0.9, -0.1] * 15, 9.8) + trs([0.9, -0.1] * 15, 9.8, asset="BBB", t0=NOW - 299 * DAY), NOW)
        self.assertTrue(AR.passa_novo(60, 0.4, 0.1, met, bom))

    def test_lutadores_ao_acaso_raramente_passam(self):
        rng = random.Random(1)
        pares = [(t, [rng.gauss(-0.1, 1) for _ in range(200)]) for t in trs([0] * 60, step_days=4)]
        tst, pa, pn = AR.acaso_teste(pares, 0.25, NOW, rng, reps=200)
        self.assertEqual(tst, 200)
        self.assertLess(pa / tst, 0.1)
        self.assertLessEqual(pn, pa)

    def test_clones_ficam_com_o_melhor(self):
        base = [1.0 if i % 3 == 0 else -0.5 for i in range(60)]
        g = {"A": trs(base, 3), "B": trs([x * 0.9 for x in base], 3), "C": trs(list(reversed(base)), 3)}
        out = {"A": {"por_regime": {"lateral": {"n": 60, "avg_r": 0.3, "passa_atual": True}}},
               "B": {"por_regime": {"lateral": {"n": 60, "avg_r": 0.5}}}, "C": {"avg_r": 0.1}}
        c = AR.clones(g, out, NOW - 300 * DAY, NOW)
        self.assertEqual(c["B"]["de"], "A")                    # A passa o filtro: fica A, mesmo com R menor
        self.assertNotIn("A", c)
        self.assertNotIn("C", c)

    def test_clone_morre_na_arena_e_nao_e_campeao(self):
        lg = {"lutadores": {"BOUNCE_X30": {"por_regime": {"lateral": {"n": 30, "avg_r": .4, "acaso_p95": .1, "metades": [.3, .5]}}},
                            "BOUNCE_TRAIL": {"por_regime": {"lateral": {"n": 30, "avg_r": .5, "acaso_p95": .1, "metades": [.3, .5]}}}},
              "clones": {"BOUNCE_TRAIL": {"de": "BOUNCE_X30", "corr": 0.91}}}
        st = {"arena": {"longo": lg}}
        self.assertEqual([k for k, _ in promo.regime_qualified(st, "lateral")], ["BOUNCE_X30"])
        st = {"arena": {"longo": lg, "status": {}, "forma": {"lutadores": {"BOUNCE_TRAIL": {"n": 5, "avg_r": .2}}}}, "ledger": []}
        arena.update(st, {}, NOW)
        m = st["arena"]["mortos"]["BOUNCE_TRAIL"]
        self.assertIn("clone de", m["motivo"])
        self.assertEqual(st["arena"]["status"]["BOUNCE_TRAIL"], "MORTA")
        r = promo.filtro_novo({"arena": {"longo": dict(lg, lutadores={"BOUNCE_X30": {"por_regime": {"lateral": {
            "passa_atual": True, "passa_novo": False, "qualidade": {"dias": 12}}}}})}})
        self.assertEqual(r["fases"]["lateral"]["atual"], ["BOUNCE_X30"])
        self.assertEqual(r["fases"]["lateral"]["novo"], [])
        old, promo.CONFIG_ESTUDO = promo.CONFIG_ESTUDO, {"lateral": ["SHORT_TURTLE"]}
        try:
            self.assertEqual(promo.filtro_novo({"arena": {"longo": lg}})["estudo"], {"lateral": ["SHORT_TURTLE"]})
        finally:
            promo.CONFIG_ESTUDO = old


if __name__ == "__main__":
    unittest.main()


class CorrecoesAuditoria(unittest.TestCase):
    def test_reservado_por_fase_mesmo_sem_os_ultimos_60_dias(self):
        antigas = trs([0.5, -0.1] * 20, step_days=2, t0=NOW - 300 * DAY)      # tudo antes dos ultimos 60 dias
        q = AR.qualidade(antigas, NOW)
        self.assertEqual(q["reservado"]["n"], 10)                             # 25% de 40
        self.assertEqual(q["antes"]["n"], 30)

    def test_acaso_em_blocos_por_dia_e_limiar_bonferroni(self):
        from engine import hipoteses
        self.assertEqual(hipoteses.quantil(1), 0.95)
        self.assertEqual(hipoteses.quantil(34), round(1 - 0.05 / 34, 4))
        self.assertEqual(hipoteses.quantil(10 ** 6), hipoteses.Q_MAX)
        c = hipoteses.contar()
        self.assertGreaterEqual(c["total"], c["offline"])
        rng = random.Random(3)
        pares = [(t, [rng.gauss(0, 1) for _ in range(200)]) for t in trs([0] * 60, step_days=0.25)]   # 4 por dia
        tst, pa, pn = AR.acaso_teste(pares, 0.25, NOW, rng, reps=100, pk=0.6)
        self.assertEqual(tst, 100)
        self.assertLessEqual(pn, pa)

    def test_aviso_quando_um_campeao_sai(self):
        from engine import run as RUN
        st = {"arena": {"longo": {"clones": {"BOUNCE_SQUEEZE": {"de": "BOUNCE_X30", "corr": 0.82}}}}, "ledger": []}
        self.assertEqual(RUN.campeoes_aviso(st, ["BOUNCE_SQUEEZE"], NOW), [])          # primeira vez: so guarda
        m = RUN.campeoes_aviso(st, ["BOUNCE_X30"], NOW)
        self.assertEqual(len(m), 2)
        self.assertIn("clone de", m[0])
        self.assertIn("Novo campeão", m[1])
        self.assertEqual(RUN.campeoes_aviso(st, ["BOUNCE_X30"], NOW), [])
