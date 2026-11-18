"""(18/11, ordem do Rui) Bybit UE com ate 2 posicoes do piloto SHORT_TURTLE SEM aumentar o risco: o risco somado
das posicoes reais abertas mais o da nova nunca passa o teto agregado (5% da conta) e a segunda so usa o que sobra.
Entradas novas so com a conta confirmada na corretora (leitura recente, ordens lidas, protecoes ativas, nenhuma
posicao fora do registo)."""
import json
import os
import random
import unittest
from unittest import mock

from engine import account, config, promo, risk, scanner
from tests.test_promo import bars, f, state_with, TF

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOW = 1_800_000_000


def aberta(a, risco, side="SHORT", strategy="SHORT_TURTLE", status="OPEN"):
    return {"id": f"{a}-{strategy}-1", "mode": "REAL", "status": status, "executed": True, "asset": a, "risk_pct": risco,
            "strategy": strategy, "side": side, "kind": "4H"}


def cfg_real():
    c = dict(config.load(os.path.join(RAIZ, "config.json")))
    c["capital_usdc"] = 30.0
    c.update(scanner.compounding(c, [], 0))
    return c


def plano(st, stop_frac, c=None, short=True):
    """O plano que o motor faria para um short com stop a stop_frac da entrada, com as posicoes abertas de st."""
    c = c or cfg_real()
    cc = promo.cfg_piloto("SHORT_TURTLE", st, c, c["piloto"]["inicio"] + 3600)
    if cc.get("piloto_bloqueio"):
        return None, cc["piloto_bloqueio"], cc
    p, why = risk.sizing(100.0 * stop_frac, stop_frac, 100.0, cc, short=short)
    return p, why, cc


def risco_pct(p, cap=30.0):
    return 100 * p["usdc"]["risk_usdc"] / cap


class Limites(unittest.TestCase):
    def test_limites_financeiros_em_producao(self):
        c = json.load(open(os.path.join(RAIZ, "config.json")))
        p = c["piloto"]
        self.assertEqual((p["max_posicoes"], p["teto_pct"], p["teto_agregado_pct"], p["risco_alvo_pct"], p["perda_max_r"]),
                         (2, 5, 5, 2.5, -8))
        self.assertEqual((c["risk_pct_of_capital"], c["max_risk_usdc"], c["max_open_positions"], c["nucleo_alavancagem"]),
                         (0.5, 2.5, 4, 1))
        self.assertEqual(promo.RISCO_AGREGADO_MAX, 5.0)


class Orcamento(unittest.TestCase):
    def test_1_segunda_com_o_residual(self):
        st = {"ledger": [aberta("XLM", 2.8)]}
        p, why, cc = plano(st, 0.03)
        self.assertIsNotNone(p, why)
        self.assertEqual(cc["piloto_risco_aberto_pct"], 2.8)
        self.assertLessEqual(2.8 + risco_pct(p), 5.0 + 1e-6)                    # nunca passa o agregado
        self.assertLessEqual(risco_pct(p), 2.5 + 1e-6)                          # nem o alvo por operacao

    def test_2_terceira_bloqueada(self):
        st = {"ledger": [aberta("XLM", 1.0), aberta("SEI", 1.0)]}
        p, why, _ = plano(st, 0.03)
        self.assertIsNone(p)
        self.assertIn("máximo 2", why)

    def test_3_primeira_quase_tudo(self):
        st = {"ledger": [aberta("XLM", 4.95)]}
        p, why, _ = plano(st, 0.03)
        self.assertIsNone(p)
        self.assertIn("agregado", why)

    def test_6_minimo_acima_do_residual(self):
        st = {"ledger": [aberta("XLM", 4.0)]}
        p, why, _ = plano(st, 0.20)                                              # stop largo: o minimo arrisca > 1%
        self.assertIsNone(p)
        self.assertTrue("agregado" in why or "mínima" in why, why)

    def test_16_fecho_liberta(self):
        st = {"ledger": [aberta("XLM", 4.95, status="CLOSED")]}
        p, why, cc = plano(st, 0.03)
        self.assertIsNotNone(p, why)
        self.assertEqual(cc["piloto_risco_aberto_pct"], 0)
        self.assertGreater(risco_pct(p), 2.0)

    def test_18_agregado_nunca_passa(self):
        rng = random.Random(18)
        for _ in range(300):
            n = rng.randint(0, 1)
            st = {"ledger": [aberta(f"C{i}", round(rng.uniform(0.2, 5.0), 2)) for i in range(n)]}
            p, why, cc = plano(st, rng.choice([0.01, 0.02, 0.03, 0.05, 0.1, 0.15]))
            if p:
                aberto = sum(r["risk_pct"] for r in st["ledger"])
                self.assertLessEqual(aberto + risco_pct(p), 5.0 + 1e-6, (aberto, p["usdc"]))
                self.assertLessEqual(p["usdc"]["position_usdc"], 30.0 + 1e-9)    # sem USDC emprestado
                self.assertEqual(p["usdc"]["borrowed_usdc"], 0.0)

    def test_gestor_global_soma_todas_as_estrategias(self):
        st = {"ledger": [aberta("XLM", 2.8), aberta("BTC", 0.5, side="LONG", strategy="TURTLE")]}
        r = promo.risco_aberto(st)
        self.assertEqual((r["pct"], r["moedas"]), (3.3, {"XLM", "BTC"}))         # LONG e SHORT nao se anulam


class GuardaDaConta(unittest.TestCase):
    def trade(self, estado="ATIVA", held=-10.0):
        return {"id": "XLM-SHORT_TURTLE-1", "asset": "XLM", "held": held, "stop_found": estado == "ATIVA",
                "protecao": {"estado": estado}}

    def test_9_conta_nao_confirmada(self):
        self.assertIn("não confirmada", promo.bloqueio_conta({}, False, NOW))
        self.assertIsNone(promo.bloqueio_conta({}, None, NOW))                   # quem nao passa a conta: como antes

    def test_ordens_por_ler(self):
        self.assertIn("ordens abertas", promo.bloqueio_conta({}, {"ordens_lidas": False, "trades": []}, NOW))

    def test_8_17_protecao_nao_ativa_bloqueia(self):
        for e in ("NAO_VERIFICADA", "INEXISTENTE", "CANCELADA", "DISPARADA"):
            self.assertIn("proteção de XLM", promo.bloqueio_conta({}, {"ordens_lidas": True, "trades": [self.trade(e)]}, NOW))
        self.assertIsNone(promo.bloqueio_conta({}, {"ordens_lidas": True, "trades": [self.trade("ATIVA")]}, NOW))
        self.assertIsNone(promo.bloqueio_conta({}, {"ordens_lidas": True, "trades": [self.trade("INEXISTENTE", held=0)]}, NOW))

    def test_10_posicao_na_corretora_fora_do_registo(self):
        self.assertIn("sem registo", promo.bloqueio_conta({}, {"ordens_lidas": True, "trades": [],
                                                               "posicoes_sem_registo": ["SEI"]}, NOW))
        ab = [aberta("XLM", 2.8)]
        self.assertEqual(account.posicoes_sem_registo({"XLM": 100.0, "SEI": 50.0, "ICP": 0.001}, ab,
                                                      {"SEI": [0.2], "ICP": [5.0]}), ["SEI"])   # ICP: resto de juro
        self.assertEqual(account.posicoes_sem_registo({"NOVA": 1.0}, ab, {}), ["NOVA"])         # sem preco: conta
        self.assertEqual(account.posicoes_sem_registo({"XLM": 100.0}, ab, {"XLM": [0.13]}), [])

    def test_decisions_respeita_a_guarda(self):
        c4 = bars()
        now = c4[-1]["t"] + TF + 60
        sig = {"stop": 80.0, "tp": [90.0, 95.0], "partials": [50, 50], "breakeven": True,
               "hold_s": 3 * 86400, "t_sig": c4[-1]["t"] + TF, "atr": 1.5, "gatilho": "x"}
        row = {"asset": "AAA", "price": 84.1, "decision": {"decision": "NO TRADE", "venue": {"pair": "AAA/USDC"}}}
        from tests.test_promo import CFG
        for conta, entra in ((False, False), ({"ordens_lidas": True, "trades": [], "posicoes_sem_registo": []}, True),
                             ({"ordens_lidas": True, "trades": [], "posicoes_sem_registo": ["SEI"]}, False)):
            st = state_with({"BOUNCE_G0": f(26, 0.8, -0.2)})
            with mock.patch.object(promo, "registry", return_value={"BOUNCE_G0": lambda c, px, cfg: sig}):
                d = promo.decisions(st, [row], {"AAA": c4}, CFG, now, "BOUNCE_G0", True, lambda a: None, conta=conta)
            self.assertEqual("AAA" in d, entra, conta)
            if not entra:
                self.assertIn("travão da conta", st["promo_lost"][-1]["reason"])


class Duplicados(unittest.TestCase):
    def test_14_uma_posicao_por_moeda(self):
        c4 = bars()
        now = c4[-1]["t"] + TF + 60
        sig = {"stop": 80.0, "tp": [90.0, 95.0], "partials": [50, 50], "breakeven": True,
               "hold_s": 3 * 86400, "t_sig": c4[-1]["t"] + TF, "atr": 1.5, "gatilho": "x"}
        row = {"asset": "AAA", "price": 84.1, "decision": {"decision": "NO TRADE", "venue": {"pair": "AAA/USDC"}}}
        from tests.test_promo import CFG
        st = state_with({"BOUNCE_G0": f(26, 0.8, -0.2)})
        st["ledger"] = [aberta("AAA", 0.5, side="LONG", strategy="OUTRA")]
        with mock.patch.object(promo, "registry", return_value={"BOUNCE_G0": lambda c, px, cfg: sig}):
            d = promo.decisions(st, [row], {"AAA": c4}, CFG, now, "BOUNCE_G0", True, lambda a: None)
        self.assertEqual(d, {})
        self.assertIn("já há uma posição real aberta em AAA", st["promo_lost"][-1]["reason"])


if __name__ == "__main__":
    unittest.main()
