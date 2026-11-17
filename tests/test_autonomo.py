"""(17/11) Self-Sustaining Engine em simulacao: Kelly prudente, dimensionamento, tesouraria, sobrevivencia e
isolamento (nunca ordens reais, nunca altera configuracoes)."""
import json
import os
import random
import tempfile
import unittest

from tools import autonomo as A

RAIZ = os.path.join(os.path.dirname(__file__), "..")


class Kelly(unittest.TestCase):
    def test_sem_vantagem_nao_aposta(self):
        rng = random.Random(1)
        rs = [rng.choice([-1, 1]) * 1.0 for _ in range(200)]
        self.assertEqual(A.kelly_prudente(rs)["risco_pct"], 0.0)
        self.assertEqual(A.kelly_prudente([2.0] * 10)["risco_pct"], 0.0)        # amostra curta

    def test_fracao_e_incerteza(self):
        rng = random.Random(2)
        rs = [(2.0 if rng.random() < 0.45 else -1.0) for _ in range(400)]
        k25, k50 = A.kelly_prudente(rs, 0.25), A.kelly_prudente(rs, 0.5)
        self.assertGreater(k25["risco_pct"], 0)
        self.assertAlmostEqual(k50["risco_pct"], 2 * k25["risco_pct"], places=2)
        self.assertLess(k25["risco_pct"], k25["kelly_inteiro_pct"])                 # bem abaixo do Kelly inteiro
        self.assertLess(k25["media_inferior_r"], k25["media_r"])

    def test_correlacao_reduz(self):
        self.assertAlmostEqual(A.ajustar_correlacao(1.0, 1, 0.9), 1.0)
        self.assertLess(A.ajustar_correlacao(1.0, 4, 0.5), A.ajustar_correlacao(1.0, 4, 0.0))

    def test_dimensionar_separa_conceitos_e_respeita_limites(self):
        d = A.dimensionar(8.0, 5.0, 5, 0.5, {"risco_max_pct": 5.0})
        self.assertTrue(d["cortado_pelo_limite_autorizado"])
        self.assertLessEqual(d["nocional_pct"], A.TETO_NOCIONAL_EXPERIMENTAL)        # 4% e teto de NOCIONAL
        self.assertAlmostEqual(d["margem_pct"], d["nocional_pct"] / 5, places=4)
        self.assertLessEqual(d["perda_max_pct"], 5.0)
        d2 = A.dimensionar(0.05, 5.0, 5, 0.5, {"risco_max_pct": 5.0})
        self.assertFalse(d2["cortado_pelo_teto_nocional"])
        self.assertAlmostEqual(d2["risco_pct"], 0.05, places=3)


class Tesouraria(unittest.TestCase):
    def test_break_even_e_ruina(self):
        rs = [0.2] * 50 + [-1.0] * 10 + [1.5] * 10
        t = A.tesouraria(rs, 1.0, 10, custo_mensal_em_capital_pct=0.5)
        m = sum(rs) / len(rs)
        self.assertAlmostEqual(t["retorno_mes_esperado_pct"], round(10 * 1.0 * m, 4))
        self.assertAlmostEqual(t["capital_minimo_em_custos_mensais"], round(100 / (10 * m), 1))
        self.assertEqual(t["estado"], "SUSTENTAVEL EM ESPERANCA")
        self.assertIn("NAO SUSTENTAVEL", A.tesouraria([-0.1] * 20, 1.0, 10)["estado"])

    def test_monte_carlo_custos_e_meses_sem_operacoes(self):
        rs = [0.3, -1.0, 2.0, 0.1] * 20
        a = A.monte_carlo(rs, 1.0, 10, custo_mes_pct=0.0, n=300)
        b = A.monte_carlo(rs, 1.0, 10, custo_mes_pct=2.0, n=300)
        c = A.monte_carlo(rs, 1.0, 10, n=300, meses_sem_ops=6)
        self.assertGreater(a["capital_final_mediana"], b["capital_final_mediana"])
        self.assertGreater(a["capital_final_mediana"], c["capital_final_mediana"])
        self.assertEqual(A.monte_carlo([-1.0] * 5, 20.0, 10, n=50)["risco_ruina_pct"], 100.0)

    def test_stress(self):
        s = A.stress([0.2, -1, 1.5] * 30, 0.5, 8)
        self.assertLessEqual(s["custos_a_dobrar"]["capital_final_mediana"], s["base"]["capital_final_mediana"])


class Sobrevivencia(unittest.TestCase):
    def test_bloqueia_entradas_mas_nunca_abandona_posicoes(self):
        s = A.sobrevivencia([0.5] * 5 + [-1.0] * 9)
        self.assertFalse(s["novas_entradas"])
        self.assertTrue(any("drawdown" in m for m in s["motivos"]))
        self.assertTrue(any("perdas seguidas" in m for m in s["motivos"]))
        self.assertIn("nunca abandonadas", s["posicoes_abertas"])
        self.assertTrue(A.sobrevivencia([0.2, -1, 1.5] * 5)["novas_entradas"])
        self.assertFalse(A.sobrevivencia([0.1] * 5, falhas_execucao=3)["novas_entradas"])

    def test_expectativa_degradada(self):
        s = A.sobrevivencia([1.0] * 20 + [-0.4, 0.0] * 15)
        self.assertTrue(any("expectativa degradada" in m for m in s["motivos"]))


class Isolamento(unittest.TestCase):
    def test_sem_ordens_nem_configuracoes(self):
        for f in ("tools/autonomo.py", "tools/qo_edge.py"):
            with open(os.path.join(RAIZ, f), encoding="utf-8") as fh:
                src = fh.read()
            for proibido in ("okx_exec", "import executor", "engine.executor", "privado(", "BYBIT_TRADE",
                             "open(\"config.json\", \"w\"", "okx_config.json\", \"w\"", "order"):
                self.assertNotIn(proibido, src, f"{f}: {proibido}")

    def test_main_so_em_r_e_percentagens(self):
        st = {"ledger": [{"status": "CLOSED", "mode": "PAPER", "strategy": "X", "result_r": r, "closed_at": i}
                         for i, r in enumerate([0.5, -1, 2, 0.2, -1, 1.1, 0.3, -0.5, 1.8, -1, 0.4, 0.9] * 4)]}
        d = tempfile.mkdtemp()
        p, q = os.path.join(d, "s.json"), os.path.join(d, "o.json")
        with open(p, "w") as f:
            json.dump(st, f)
        out = A.main(p, q)
        self.assertIn("PAPER|X", out["estrategias"])
        with open(q) as f:
            txt = f.read()
        for proibido in ("USD", "USDC", "EUR", "$", "€"):
            self.assertNotIn(proibido, txt)


if __name__ == "__main__":
    unittest.main()
