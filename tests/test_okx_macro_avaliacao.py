"""(13/11) Agente macro OKX: abertas avaliadas ao ultimo fecho (custos e financiamento), negociavel na OKX EEA,
resultado por instrumento. So papel."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import okx_macro as M  # noqa: E402


class Avaliacao(unittest.TestCase):
    def test_avaliar(self):
        st = {"abertas": {"XAU": {"t": 0, "entrada": 100.0, "px": 110.0, "t_px": 10 * 86400},
                          "ABC": {"t": 0, "entrada": 50.0}},
              "fechadas": [{"asset": "TSLA", "ret_pct": -5.0}, {"asset": "TSLA", "ret_pct": -3.0}]}
        r = M.avaliar(st, {"XAU", "TSLA"})
        xau = [x for x in r["abertas_avaliadas"] if x["asset"] == "XAU"][0]
        self.assertAlmostEqual(xau["ret_pct"], 100 * (0.10 - 0.002 - 0.003), places=2)
        self.assertTrue(xau["negociavel_eea"])
        self.assertEqual((r["abertas_sem_preco"], r["fechadas_negociaveis_eea"]), (1, 2))
        self.assertEqual(r["por_instrumento"]["TSLA"], {"n": 2, "ret_medio_pct": -4.0})
        self.assertNotIn("usd", str(r).lower())


if __name__ == "__main__":
    unittest.main()
