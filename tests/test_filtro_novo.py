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


if __name__ == "__main__":
    unittest.main()
