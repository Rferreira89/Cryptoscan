"""(11/11, P5) Instrumentacao do deslize: livro, previsao em R, analise e recomendacao so com amostra."""
import os
import sys
import unittest

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.join(RAIZ, "tools"))
from engine import qualidade_execucao as Q  # noqa: E402
import recolha_liquidez_okx as L  # noqa: E402

BIDS = [(99.9, 1), (99.5, 2), (99.0, 5), (97.0, 10)]
ASKS = [(100.1, 1), (100.5, 2), (101.0, 5), (103.0, 10)]


class Livro(unittest.TestCase):
    def test_spread_profundidade_e_deslize_dos_dois_lados(self):
        lv = Q.livro(BIDS, ASKS, valor=250)
        self.assertAlmostEqual(lv["spread_bps"], 20.0)
        self.assertGreater(lv["deslize_venda_bps"], 10)                 # anda 3 niveis do lado da venda
        self.assertGreater(lv["deslize_compra_bps"], 10)
        self.assertGreater(lv["prof_2pct"], lv["prof_0.5pct"])

    def test_livro_que_nao_chega_devolve_none_no_deslize(self):
        lv = Q.livro([(1, 1)], [(1.01, 1)], valor=10_000)
        self.assertIsNone(lv["deslize_venda_bps"])

    def test_livro_vazio(self):
        self.assertIsNone(Q.livro([], ASKS))

    def test_previsto_em_r(self):
        lv = {"deslize_venda_bps": 100.0}                                # 1% abaixo do stop
        r = Q.previsto_em_r(lv, entrada=1.0, stop=0.9)                   # risco 10% -> 0.9% / 10% = 0.09R
        self.assertAlmostEqual(r, -0.09, places=3)


class Analise(unittest.TestCase):
    def regs(self, n, desl, prof):
        return [{"ativo": "A", "realizado_stop_r": desl, "previsto_stop_r": desl / 2, "prof_1pct": prof} for _ in range(n)]

    def test_analise_por_ativo(self):
        a = Q.analise(self.regs(3, -0.1, 1000) + [{"ativo": "B", "realizado_stop_r": -0.3}])
        self.assertEqual(a["A"]["n"], 3)
        self.assertEqual(a["B"]["n_com_previsao"], 0)

    def test_um_caso_nao_gera_recomendacao(self):
        self.assertEqual(Q.recomendacao(self.regs(1, -0.22, 500))["decisao"], "amostra insuficiente")

    def test_diferenca_significativa_com_amostra(self):
        import random
        rnd = random.Random(1)
        regs = [{"realizado_stop_r": -0.25 + rnd.uniform(-0.03, 0.03), "prof_1pct": 500} for _ in range(20)]
        regs += [{"realizado_stop_r": -0.02 + rnd.uniform(-0.03, 0.03), "prof_1pct": 50_000} for _ in range(20)]
        r = Q.recomendacao(regs)
        self.assertIn("significativa", r["decisao"])
        self.assertNotIn("sem", r["decisao"])

    def test_sem_diferenca(self):
        import random
        rnd = random.Random(2)
        regs = [{"realizado_stop_r": rnd.uniform(-0.1, 0), "prof_1pct": p} for p in [500] * 20 + [50_000] * 20]
        self.assertEqual(Q.recomendacao(regs)["decisao"], "sem diferenca significativa")


class Recolha(unittest.TestCase):
    def test_so_endpoints_publicos(self):
        with self.assertRaises(ValueError):
            L.publico("/api/v5/trade/order")
        with self.assertRaises(ValueError):
            L.publico("/api/v5/account/balance")

    def test_linha_com_respostas_gravadas(self):
        def ler(path):
            return {"data": [{"bids": [[str(p), str(q), "0", "1"] for p, q in BIDS],
                              "asks": [[str(p), str(q), "0", "1"] for p, q in ASKS]}]}
        ln = L.linha("X-USD_UM_XPERP-1", 1.0, ler, now=1)
        self.assertEqual(ln["ativo"], "X")
        self.assertIn("venda_1000_bps", ln)
        self.assertNotIn("equity", ln)


if __name__ == "__main__":
    unittest.main()
