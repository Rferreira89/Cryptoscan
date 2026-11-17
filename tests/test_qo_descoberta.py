"""(17/11) Descoberta autonoma: grelha fixa, sem olhar para a frente, Holm sobre todas, redundancia, so papel."""
import gzip
import json
import os
import tempfile
import unittest

from tests.test_qo_edge import serie
from tools import qo_descoberta as Dsc


class Descoberta(unittest.TestCase):
    def test_grelha_fixa_e_lados(self):
        self.assertEqual(len(Dsc.GRELHA) * len(Dsc.LADOS), 40)

    def test_disparo_nao_olha_para_a_frente(self):
        cs = serie(n=400, seed=5)
        P = Dsc.preparar(cs)
        mex = [dict(b) for b in cs]
        for b in mex[301:]:
            b.update(c=b["c"] * 2, h=b["h"] * 2, l=b["l"] * 2, v=b["v"] * 40)
        Q = Dsc.preparar(mex)
        for fam, prm in Dsc.GRELHA:
            for lado in Dsc.LADOS:
                for i in range(150, 300):
                    self.assertEqual(Dsc.dispara(P, i, fam, prm, lado), Dsc.dispara(Q, i, fam, prm, lado), (fam, prm, lado, i))

    def test_welch_e_corr(self):
        self.assertLess(Dsc.welch_p([1.0, 1.1, 0.9] * 20, [0.0, 0.1, -0.1] * 20), 1e-6)
        self.assertGreater(Dsc.welch_p([0.0, 0.1, -0.1] * 20, [1.0, 1.1, 0.9] * 20), 0.99)
        d = {k: float(k % 3) for k in range(30)}
        self.assertAlmostEqual(Dsc.corr(d, d), 1.0)

    def test_corre_e_nunca_aprova_producao(self):
        series = {f"A{k}": serie(n=700, seed=k) for k in range(3)}
        ts = sorted(b["t"] for cs in series.values() for b in cs)
        d = tempfile.mkdtemp()
        p, q = os.path.join(d, "s.json.gz"), os.path.join(d, "o.json")
        with gzip.open(p, "wt") as f:
            json.dump({"series": series, "corte": ts[0] + int(0.6 * (ts[-1] - ts[0]))}, f)
        out = Dsc.main(p, q)
        self.assertEqual(out["variantes"], 40)
        for v in out["resultados"].values():
            self.assertTrue(v["veredicto"].startswith(("CANDIDATA A PAPEL", "AMOSTRA", "REJEITADA", "REDUNDANTE")))
            self.assertNotIn("REAL", v["veredicto"])
