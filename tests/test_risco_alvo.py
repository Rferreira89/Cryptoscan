"""(13/11, B1 e E2) SHORT_TURTLE com risco-alvo 2,5% e validacao do lote no planeamento.
Capital SINTETICO (30). Regras: alvo ao pior preco da ordem, sem USDC emprestado, posicao <= capital, nunca acima do
risco autorizado (teto e livre do agregado), lote/minimo validados antes do executor."""
import unittest

from engine import config, executor as X, promo, risk, scanner


def cfg(aberto=0.0):
    c = dict(config.load("config.json"))
    c["capital_usdc"] = 30.0
    c.update(scanner.compounding(c, [], 0))
    cc = promo.cfg_piloto("SHORT_TURTLE", {"ledger": []}, c, c["piloto"]["inicio"] + 3600)
    return dict(cc, piloto_risco_aberto_pct=aberto)


class Alvo(unittest.TestCase):
    def test_config_de_producao(self):
        c = config.load("config.json")
        self.assertEqual((c["piloto"]["risco_alvo_pct"], c["piloto"]["teto_pct"], c["piloto"]["max_posicoes"]), (2.5, 5, 2))   # (14/11 15:28, Rui: "manter tal como está") 
        self.assertEqual(cfg()["piloto_risco_alvo_pct"], 2.5)

    def test_alvo_ao_pior_preco_sem_emprestimo(self):
        for stop in (3.0, 5.5, 8.0):
            p, why = risk.sizing(stop, stop / 100, 100.0, cfg(), short=True)
            u = p["usdc"]
            self.assertAlmostEqual(u["position_usdc"] * (stop + 0.6) / 100, 30 * 0.025, places=2)
            self.assertEqual((u["borrowed_usdc"], p["leverage"]["use"]), (0.0, 1.0))
            self.assertLessEqual(u["position_usdc"], 30.0)
            self.assertAlmostEqual(u["max_risk_usdc"], 30 * 0.05)        # o autorizado, nao o alvo

    def test_stop_curtissimo_nunca_passa_o_capital(self):
        p, _ = risk.sizing(1.0, 0.01, 100.0, cfg(), short=True)
        self.assertLessEqual(p["usdc"]["position_usdc"], 30.0)

    def test_respeita_o_livre_do_agregado(self):
        p, _ = risk.sizing(5.0, 0.05, 100.0, dict(cfg(4.0), piloto_teto_agregado_pct=5.0), short=True)
        self.assertLessEqual(p["usdc"]["position_usdc"] * (5.0 + 0.6) / 100, 30 * 0.01 + 1e-6)   # so 1% livre

    def test_ordem_minima_quando_o_alvo_nao_chega(self):
        p, _ = risk.sizing(15.0, 0.15, 100.0, cfg(), short=True)
        self.assertEqual(p["usdc"]["position_usdc"], 5.0)               # 5 x 15% = 2,5% do capital: cabe no teto
        p, why = risk.sizing(31.0, 0.31, 100.0, cfg(), short=True)
        self.assertIsNone(p)                                             # 5 x 31% passa os 5% autorizados


class Lote(unittest.TestCase):
    def plano(self, stop_pct, px):
        p, _ = risk.sizing(stop_pct, stop_pct / 100, px, cfg(), short=True)
        d = dict(p["usdc"], side="SHORT", risk_pct=round(p["usdc"]["risk_usdc"] / 30 * 100, 3),
                 position_pct=round(p["usdc"]["position_usdc"] / 30 * 100, 3))
        return d, px * (1 + stop_pct / 100 - 0.005)

    def test_bnb_sobe_um_lote_dentro_do_autorizado(self):
        p, stop = self.plano(15.0, 664.0)
        self.assertIsNone(promo.validar_lote(p, 664.0, [0.001, 0.001, 5.0, 0.01], stop))
        self.assertAlmostEqual(p["lote"]["qtd"], 0.008)
        self.assertGreaterEqual(p["lote"]["qtd"] * p["lote"]["preco_limite"], 5.0)
        self.assertLessEqual(p["lote"]["risco_efetivo"], 30 * 0.05)

    def test_recusa_antes_do_executor_se_o_lote_passa_o_autorizado(self):
        p, stop = self.plano(28.0, 664.0)
        why = promo.validar_lote(p, 664.0, [0.01, 0.01, 5.0, 0.01], stop)       # lote de 0,01 BNB = 6,6 USDC
        self.assertIn("passa o risco autorizado", why)

    def test_executor_confirma_ao_pior_preco(self):
        inst = {"base_step": "0.001", "min_amt": 5.0, "tick": "0.01"}
        with self.assertRaises(X.ExecError) as e:
            X.qty_ordem(20.0, 100.0, inst, 25.0, stop=110.0, max_risk=1.0)      # 0,2 x 10 = 2 > 1
        self.assertIn("risco efetivo", str(e.exception))
        q = X.qty_ordem(9.0, 100.0, inst, 25.0, stop=110.0, max_risk=1.0)
        self.assertLessEqual(X.risco_ordem(q, 100.0, 110.0), 1.0 * 1.001)


if __name__ == "__main__":
    unittest.main()
