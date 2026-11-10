"""(10/11) H57-H59 em dados novos: so dados posteriores ao registo, regras fixas, custos e financiamento, referencia."""
import csv
import os
import random
import tempfile
import unittest

from backtest.estudos.novos import fila_1011 as F

CAMPOS = ["data", "moeda", "validado", "o", "h", "l", "c", "volume_usd", "px_xperp", "px_global",
          "fund_xperp_24h", "oi_usd_global", "oi_xperp"]


def escrever(linhas):
    d = tempfile.mkdtemp()
    with open(os.path.join(d, "2026-12.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, CAMPOS); w.writeheader(); w.writerows(linhas)
    return d


def linha(dia, m, c, oi=1e8, fund=0.0001, o=None, vol=2e7):
    o = o or c
    return {"data": dia, "moeda": m, "validado": 1, "o": o, "h": max(o, c) * 1.01, "l": min(o, c) * 0.99, "c": c,
            "volume_usd": vol, "px_xperp": c, "px_global": c, "fund_xperp_24h": fund, "oi_usd_global": oi, "oi_xperp": 1e6}


class Fila(unittest.TestCase):
    def test_antes_do_registo_nao_conta(self):
        d = escrever([linha("2026-11-09", "A", 1.0)])
        r = F.avaliar(d)
        self.assertTrue(all(x["operacoes"] == 0 for x in r.values()))

    def test_h59_dispara_em_descida_com_oi_a_cair(self):
        rs = random.Random(1)
        L = []
        dias = [f"2026-12-{k:02d}" for k in range(1, 26)]
        for m in range(35):
            px = 100.0
            for i, dia in enumerate(dias):
                px *= 0.995 + rs.gauss(0, 0.001)
                L.append(linha(dia, f"M{m}", px))
        # moeda X: sobe 12% em 3 dias com OI a cair e financiamento positivo, no dia 15
        for i, dia in enumerate(dias):
            c = 100 * (1.04 ** max(0, min(i, 15) - 12)) if i <= 15 else 105
            oi = 1e8 * (0.97 ** max(0, min(i, 15) - 12))
            L.append(linha(dia, "X", c, oi=oi, fund=0.0002))
        por = F.series(L)
        ds = sorted({x["data"] for x in L})
        self.assertIn("X", F.h59(por, ds, 15))
        op = F.operacao(por["X"], ds, 15, "SHORT")
        self.assertIsNotNone(op); self.assertIn("R", op)

    def test_financiamento_em_falta_nao_passa_por_zero(self):
        dias = [f"2026-12-{k:02d}" for k in range(1, 20)]
        L = [linha(d, "A", 100.0) for d in dias]
        L[16]["fund_xperp_24h"] = ""
        por = F.series(L)
        self.assertIsNone(F.operacao(por["A"], sorted(dias), 15, "LONG"))

    def test_holm(self):
        h = F.holm({"a": 0.01, "b": 0.02, "c": 0.04})
        self.assertAlmostEqual(h["a"], 0.03); self.assertAlmostEqual(h["b"], 0.04); self.assertAlmostEqual(h["c"], 0.04)


if __name__ == "__main__":
    unittest.main()
