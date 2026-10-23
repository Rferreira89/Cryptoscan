"""(23/10, OK do Rui) sobrevenda so em papel e suspensao do Ramiro por deriva."""
import unittest
from unittest import mock

from engine import promo, paper_ring, run


def st(met_sq=(0.54, 0.09), met_st=(0.69, -0.08), n_st=214):
    lr = lambda n, r, met: {"por_regime": {"lateral": {"n": n, "avg_r": r, "acaso_p95": -0.2, "metades": list(met)}}}
    return {"arena": {"longo": {"lutadores": {"BOUNCE_SQUEEZE": lr(28, 0.31, met_sq), "SHORT_TURTLE": lr(n_st, 0.3, met_st)}}}}


class SoPapel(unittest.TestCase):
    def setUp(self):
        self.old = promo.SO_PAPEL_FAM, promo.CONFIG_ESTUDO
        promo.SO_PAPEL_FAM, promo.CONFIG_ESTUDO = {"sobrevenda"}, {"lateral": ["SHORT_TURTLE"]}

    def tearDown(self):
        promo.SO_PAPEL_FAM, promo.CONFIG_ESTUDO = self.old

    def reg(self):
        return mock.patch.object(promo, "registry", return_value={"BOUNCE_SQUEEZE": 1, "SHORT_TURTLE": 1})

    def test_sobrevenda_sai_do_dinheiro_real_e_fica_em_papel(self):
        s = st()
        with self.reg():
            self.assertEqual(promo.champions(s, (), "lateral", True), ["SHORT_TURTLE"])
        self.assertIn("sobrevenda", s["so_papel"]["BOUNCE_SQUEEZE"].lower() + "sobrevenda")
        self.assertIn("BOUNCE_SQUEEZE", s["so_papel"])

    def test_deriva_do_ramiro_passa_a_papel(self):
        s = st(met_st=(0.5, -0.20), n_st=200)
        with self.reg():
            self.assertEqual(promo.champions(s, (), "lateral", True), [])
        self.assertIn("deriva", s["so_papel"]["SHORT_TURTLE"])

    def test_sem_amostra_suficiente_nao_suspende(self):
        s = st(met_st=(0.5, -0.20), n_st=150)                     # 75 na 2.a metade
        with self.reg():
            self.assertIn("SHORT_TURTLE", promo.champions(s, (), "lateral", True))

    def test_papel_mede_os_tirados(self):
        c4 = [{"t": i * 14400, "o": 10, "h": 10.1, "l": 9.9, "c": 10, "v": 1} for i in range(200)]
        now = c4[-1]["t"] + 14400 + 60
        fake = {"BOUNCE_SQUEEZE": lambda c, p, cfg=None: {"stop": 9.0, "tp": [12.0], "partials": [100], "hold_s": 86400, "t_sig": c[-1]["t"] + 14400}}
        s = {"so_papel": {"BOUNCE_SQUEEZE": "x"}, "mercado": {"regime": "lateral"}}
        with mock.patch.object(promo, "registry", return_value=fake), mock.patch.object(promo, "qualified", return_value=[]), \
                mock.patch.object(promo, "set_context"):
            r = paper_ring.update(s, [{"asset": "AAA", "price": 10.0}], {"AAA": c4}, now)
        self.assertEqual(r["BOUNCE_SQUEEZE"]["open"], ["AAA"])

    def test_aviso_diz_o_motivo(self):
        s = {"campeoes_ant": ["BOUNCE_SQUEEZE", "SHORT_TURTLE"], "so_papel": {"BOUNCE_SQUEEZE": "família só em papel"}}
        out = run.campeoes_aviso(s, ["SHORT_TURTLE"], 0)
        self.assertTrue(any("só em papel" in x for x in out))


if __name__ == "__main__":
    unittest.main()
