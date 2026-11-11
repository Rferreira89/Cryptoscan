"""(11/11) Funil de frequencia (OKX e Bybit, so copias publicas)."""
import json
import os
import sys
import tempfile
import unittest

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.join(RAIZ, "tools"))
import funil_frequencia as F  # noqa: E402

DIA = 86400
T0 = 1_794_000_000


class Funil(unittest.TestCase):
    def okx(self):
        return {"fechadas": [{"asset": "A", "t_sig": T0, "tipo": "isolado", "r": -1.0},
                             {"asset": "B", "t_sig": T0, "tipo": "mercado", "r": 2.0},
                             {"asset": "C", "t_sig": T0, "tipo": "isolado", "r": -1.0},
                             {"asset": "D", "t_sig": 1_793_000_000, "tipo": "isolado", "r": 1.0}],
                "abertas": {"E": {"t_sig": T0 + 1, "tipo": "isolado"}}, "pend": {},
                "real": {"colocados": [f"B:{T0}"], "avisados": [f"p:A:{T0}", f"x:C:{T0}", f"i:E:{T0 + 1}"]}}

    def test_grupos_e_motivos(self):
        r = F.okx(self.okx())
        g = r["grupos"]
        self.assertEqual(g["colocado em real"]["r_medio_papel"], 2.0)
        self.assertEqual(g["rejeitado: H40 suspensa do real"]["n"], 1)
        self.assertEqual(g["rejeitado: sem X-Perp negociavel"]["soma_r_papel"], -1.0)
        self.assertEqual(g["rejeitado: panico isolado (so mercado todo)"]["fechadas_em_papel"], 0)
        self.assertEqual(g["antes do dinheiro real"]["n"], 1)
        self.assertEqual(r["rejeitados_r_medio_papel"], -1.0)
        self.assertIn("poupou", r["leitura"])

    def test_aviso_sem_prefixo_e_ordem_minima(self):
        o = self.okx()
        o["real"]["avisados"].append(f"A:{T0}")
        o["real"]["avisados"].remove(f"p:A:{T0}")
        self.assertIn("rejeitado: ordem minima obrigava a mais risco", F.okx(o)["grupos"])

    def test_correr_com_pasta_vazia(self):
        with tempfile.TemporaryDirectory() as d:
            r = F.correr(d)
        self.assertEqual(r["okx"]["sinais"], 0)


if __name__ == "__main__":
    unittest.main()
