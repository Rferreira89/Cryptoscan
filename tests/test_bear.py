"""(13/11, D1) BEAR e ANALYST: objecoes com dados, fonte e hora; analise com amostra minima; nunca bloqueiam."""
import unittest
from unittest import mock

from engine import bear as B
from engine import promo


class Bear(unittest.TestCase):
    def test_objecoes(self):
        obs = B.objecoes({"side": "SHORT", "deriv": {"funding_rate": -0.0002, "oi_chg_24h_pct": -8.0,
                                                     "price_chg_24h_pct": -4.0, "venue": "binance"},
                          "stop_pct": 12.0}, 4, [5.0] * 25, 1000)
        self.assertEqual({o["codigo"] for o in obs}, {"grupo", "funding", "oi", "stop_largo"})
        self.assertTrue(all(o["fonte"] and o["t"] == 1000 for o in obs))
        self.assertEqual(B.objecoes({"side": "LONG", "deriv": {}, "stop_pct": 3.0}, 1, [5.0] * 5, 1), [])

    def test_analista_amostra_insuficiente_e_comparacao(self):
        st = {"bear": {"registos": []}, "sombra_rejeitadas": {"fechadas": []}}
        for i in range(25):
            for com in (True, False):
                k = f"A{i}{com}|S|{i}"
                st["bear"]["registos"].append({"chave": k, "strategy": "S",
                                               "objecoes": [{"codigo": "grupo"}] if com else []})
                st["sombra_rejeitadas"]["fechadas"].append({"chave": k, "r": -0.5 if com else 0.5})
        r = B.analista(st, "S", "grupo")
        self.assertEqual((r["n_com"], r["r_com"], r["r_sem"]), (25, -0.5, 0.5))
        self.assertIn("só observação", r["veredicto"])
        st["bear"]["registos"] = st["bear"]["registos"][:10]
        self.assertIn("amostra insuficiente", B.analista(st, "S", "grupo")["veredicto"])

    def test_nao_bloqueia_no_circuito(self):
        """Com e sem o BEAR as decisoes sao iguais; o BEAR so regista."""
        from tests.test_gestor_risco import NoCircuito
        t = NoCircuito()
        d1, st = t.correr([])
        self.assertEqual(len(st["bear"]["registos"]), 1)
        with mock.patch.object(B, "observar", side_effect=RuntimeError("x")):
            d2, _ = t.correr([])
        self.assertEqual(set(d1), set(d2))
        self.assertEqual(d1["AAA"]["plan"]["risk_pct"], d2["AAA"]["plan"]["risk_pct"])


if __name__ == "__main__":
    unittest.main()
