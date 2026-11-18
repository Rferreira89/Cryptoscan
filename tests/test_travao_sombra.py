"""(18/11) Travao do papel em modo sombra: regista K4 e K8 ao lado da regra ativa, sem mudar nada."""
import random
import unittest
from unittest import mock

from engine import paper_ring, promo, travao_sombra as T
from tests.test_promo import bars, f, state_with, TF


def fechadas(rs):
    return [{"asset": "AAA", "r": r, "opened_at": i, "closed_at": i + 1} for i, r in enumerate(rs)]


class Estatisticas(unittest.TestCase):
    def test_regras(self):
        rng = random.Random(1)
        fraca = [rng.choice([-1.0, 2.0]) - 0.45 for _ in range(25)]     # perto de zero, media negativa
        e = T.estatisticas(fraca)
        d = T.decisoes(e)
        self.assertEqual(d["ativa"], e["r_medio"] < 0)
        self.assertFalse(d["K8"])                                          # n < 30
        ma = [-1.0] * 30
        ma[0] = -0.9
        d = T.decisoes(T.estatisticas(ma))
        self.assertTrue(d["ativa"] and d["K4"] and d["K8"])
        self.assertEqual(T.decisoes(T.estatisticas([0.1] * 5)), {"ativa": False, "K4": False, "K8": False})

    def test_t_e_bayes(self):
        rs = [1.0, -1.0, 0.5, -0.5] * 10
        e = T.estatisticas(rs)
        self.assertAlmostEqual(e["t_stat"], 0.0, places=6)
        self.assertAlmostEqual(e["p_negativa"], 0.5, places=3)

    def test_primeiro_corte_fica_registado(self):
        st = {}
        T.registar(st, "X", fechadas([-1.0] * 19), 100)
        self.assertEqual(st["travao_sombra"]["X"]["primeiro_corte"], {})
        T.registar(st, "X", fechadas([-1.0] * 19 + [-0.9]), 200)
        self.assertEqual(st["travao_sombra"]["X"]["primeiro_corte"]["ativa"]["n"], 20)
        T.registar(st, "X", fechadas([-1.0] * 19 + [-0.9] + [2.0] * 30), 300)    # recupera: a 1.a vez fica
        self.assertEqual(st["travao_sombra"]["X"]["primeiro_corte"]["ativa"]["t"], 200)
        self.assertFalse(st["travao_sombra"]["X"]["decisoes"]["ativa"])

    def test_nunca_levanta(self):
        self.assertIn("erro", T.registar(None, "X", [], 1))


class NaoMudaOPapel(unittest.TestCase):
    def test_kill_ativo_igual_com_a_sombra(self):
        c4 = bars()
        now = c4[-1]["t"] + TF + 60
        perdas = fechadas([-1.0] * 20 + [-0.5] * 5)
        for com_sombra in (True, False):
            st = state_with({"NOVO": f(25, 0.6, 0.1)})
            st.setdefault("paper_ring", {})["NOVO"] = {"open": {}, "closed": list(perdas), "last": {}}
            with mock.patch.object(promo, "registry", return_value={"NOVO": lambda c, px, cfg: None}), \
                    mock.patch.object(T, "registar", T.registar if com_sombra else (lambda *a, **k: None)):
                paper_ring.update(st, [{"asset": "AAA", "price": 84.1}], {"AAA": c4}, now)
            self.assertIn("NOVO", st["papel_kill"])                         # a regra ativa continua a cortar
            if com_sombra:
                s = st["travao_sombra"]["NOVO"]
                self.assertEqual(s["n"], 25)
                self.assertTrue(s["decisoes"]["ativa"])
                self.assertEqual(set(s["primeiro_corte"]), {"ativa", "K4"})   # K8 so com n >= 30
            else:
                self.assertNotIn("travao_sombra", st)

    def test_sombra_que_falha_nao_para_o_papel(self):
        c4 = bars()
        now = c4[-1]["t"] + TF + 60
        st = state_with({"NOVO": f(25, 0.6, 0.1)})
        with mock.patch.object(promo, "registry", return_value={"NOVO": lambda c, px, cfg: None}), \
                mock.patch.object(T, "estatisticas", side_effect=RuntimeError("x")):
            out = paper_ring.update(st, [{"asset": "AAA", "price": 84.1}], {"AAA": c4}, now)
        self.assertIn("NOVO", out)


if __name__ == "__main__":
    unittest.main()
