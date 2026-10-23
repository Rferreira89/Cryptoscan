import unittest
from engine import liberdade

CFG = {"deposito_mensal": 300, "rendimento_mensal": 2000, "levantamento_pct": 5, "imposto_pct": 28}


class Liberdade(unittest.TestCase):
    def test_etapas_e_anos(self):
        r = liberdade.resumo(355, {"investido": 367.1, "g_usdc": -11.45}, CFG)
        e = {x["rendimento"]: x for x in r["etapas"]}
        self.assertEqual(e[2000]["capital"], 666667)
        self.assertEqual(e[2000]["anos"]["15%"], 23.5)
        self.assertLess(e[500]["anos"]["30%"], e[1000]["anos"]["30%"])

    def test_mensagem_so_ao_domingo_e_uma_vez(self):
        st = {}
        res = {"liberdade": liberdade.resumo(355, {"investido": 367, "g_usdc": -11}, CFG), "evolucao": {"periodos": {"semana": 0.4}}}
        dom = 1792962000            # domingo 25/10/2026 20:20 UTC
        sab = dom - 86400
        self.assertIsNone(liberdade.semanal(st, res, sab))
        txt = liberdade.semanal(st, res, dom)
        self.assertIn("Caminho para a liberdade", txt)
        self.assertIsNone(liberdade.semanal(st, res, dom + 600))


if __name__ == "__main__":
    unittest.main()
