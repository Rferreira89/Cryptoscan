"""(30/10) Modo acelerado: desligado por omissao; meio-Kelly so com as tres condicoes."""
import json
import os
import unittest

from engine import acelerado as A

CAMINHO = os.path.join(os.path.dirname(__file__), "..", "config.json")


def reg(rs, k="PANICO_L10"):
    return [{"strategy": k, "status": "CLOSED", "result_r": r, "executed": True} for r in rs]


BOM = [2.0] * 40 + [-1.0] * 50          # media +0,33R, 90 operacoes


def cfg(**kw):
    c = {"capital_usdc": 1000, "risk_pct_of_capital": 0.5, "real_autorizados": ["PANICO_L10"],
         "modo_acelerado": {"ligado": True}}
    c.update(kw)
    return c


class Acelerado(unittest.TestCase):
    def test_config_real_vem_desligado(self):
        with open(CAMINHO) as f:
            c = json.load(f)
        self.assertTrue(c["modo_acelerado"]["ligado"])          # (30/10) ligado antecipadamente pelo Rui
        self.assertEqual(c["modo_acelerado"]["teto_pct"], 2.5)
        self.assertFalse(c["nucleo_ligado"])                     # (30/10) nucleo desligado pelo Rui
        self.assertEqual(c["real_autorizados"], ["PANICO_L10"])   # (31/10) Rui: 20$ com o valor todo
        self.assertEqual(c["panico_real"], {"modo": "tudo", "max_usdc": 20, "alavancagem": [5, 10]})   # e no modo valor todo o acelerado nao atua
        st = {"ledger": reg(BOM), "papel_panico": {"fechadas": [{"r": r} for r in BOM]}}
        self.assertIs(A.cfg_para("PANICO_L10", st, c), c)

    def test_desligado_nao_muda_nada(self):
        c = cfg(modo_acelerado={"ligado": False})
        self.assertEqual(A.risco_pct("PANICO_L10", {"ledger": reg(BOM)}, c)[0], None)

    def test_precisa_de_autorizacao(self):
        c = cfg(real_autorizados=[])
        self.assertEqual(A.risco_pct("PANICO_L10", {"ledger": reg(BOM)}, c), (None, "estratégia não autorizada"))

    def test_precisa_de_operacoes_suficientes(self):
        pct, why = A.risco_pct("PANICO_L10", {"ledger": reg(BOM[:30] + BOM[-20:])}, cfg())
        self.assertIsNone(pct)
        self.assertIn("50/60", why)

    def test_meio_kelly_com_teto(self):
        pct, why = A.risco_pct("PANICO_L10", {"ledger": reg(BOM)}, cfg())
        self.assertEqual(pct, 2.5)                       # Kelly daria mais: fica no teto
        self.assertIn("meio-Kelly", why)
        c2 = A.cfg_para("PANICO_L10", {"ledger": reg(BOM)}, cfg())
        self.assertEqual(c2["max_risk_usdc"], 25.0)

    def test_vantagem_pequena_da_risco_pequeno(self):
        rs = [2.0] * 36 + [-1.0] * 64                   # media +0,08R
        pct, m, lb = A.kelly(rs)
        self.assertIsNone(pct)                           # o limite inferior nao e positivo
        rs = [2.0] * 380 + [-1.0] * 620                  # +0,14R em 1000 operacoes
        pct, m, lb = A.kelly(rs)
        self.assertTrue(0 < pct < 2.5)

    def test_sem_vantagem_nao_acelera(self):
        pct, why = A.risco_pct("PANICO_L10", {"ledger": reg([2.0] * 30 + [-1.0] * 60)}, cfg())
        self.assertIsNone(pct)
        self.assertIn("sem vantagem", why)

    def test_travoes(self):
        st = {"ledger": reg(BOM), "risco": {"dd": 0.06}}
        self.assertEqual(A.risco_pct("PANICO_L10", st, cfg())[0], 1.25)    # a meio: metade
        st["risco"]["dd"] = 0.11
        self.assertIsNone(A.risco_pct("PANICO_L10", st, cfg())[0])
        st = {"ledger": reg(BOM), "risco": {"reduzido": True}}
        self.assertIsNone(A.risco_pct("PANICO_L10", st, cfg())[0])
        self.assertIsNone(A.risco_pct("PANICO_L10", {"ledger": reg(BOM)}, cfg(risk_reduced=True))[0])

    def test_fora_programa_nao_conta(self):
        led = reg(BOM)
        for r in led[:40]:
            r["fora_programa"] = True
        self.assertIsNone(A.risco_pct("PANICO_L10", {"ledger": led}, cfg())[0])

    def test_papel_do_panico_conta(self):
        st = {"papel_panico": {"fechadas": [{"r": r} for r in BOM]}}
        self.assertEqual(A.risco_pct("PANICO_L10", st, cfg())[0], 2.5)

    def test_resumo(self):
        r = A.resumo({"ledger": reg(BOM)}, cfg())
        self.assertTrue(r["ligado"])
        self.assertEqual(r["estrategias"]["PANICO_L10"]["risco_pct"], 2.5)


class Marcos(unittest.TestCase):
    def test_sem_operacoes_nao_avisa(self):
        st = {"papel_panico": {"fechadas": [{"r": 2.0}] * 10}}
        self.assertEqual(A.marcos(st, cfg(real_autorizados=[])), [])

    def test_prova_boa_avisa_deposito_uma_vez(self):
        st = {"papel_panico": {"fechadas": [{"r": r} for r in BOM]}}
        m = A.marcos(st, cfg(real_autorizados=[], modo_acelerado={"ligado": False}))
        self.assertEqual(len(m), 1)
        self.assertIn("DEPOSITAR", m[0])
        self.assertEqual(A.marcos(st, cfg(real_autorizados=[])), [])

    def test_prova_fraca_diz_para_nao_depositar(self):
        st = {"papel_panico": {"fechadas": [{"r": r} for r in [2.0] * 22 + [-1.0] * 40]}}
        m = A.marcos(st, cfg(real_autorizados=[]))
        self.assertIn("NÃO é altura de depositar", m[0])

    def test_acelerado_pronto_pede_ok(self):
        st = {"ledger": reg(BOM)}
        m = A.marcos(st, cfg(modo_acelerado={"ligado": False}))
        self.assertEqual(len(m), 1)
        self.assertIn("liga o acelerado", m[0])
        self.assertIn("2.5%", m[0])
        self.assertEqual(A.marcos(st, cfg(modo_acelerado={"ligado": False})), [])

    def test_ligado_avisa_quando_passa_a_atuar_e_quando_pausa(self):
        st = {"ledger": reg(BOM)}
        m = A.marcos(st, cfg())
        self.assertEqual(len(m), 1)
        self.assertIn("A ATUAR", m[0])
        self.assertEqual(A.marcos(st, cfg()), [])                 # uma vez so
        st["risco"] = {"dd": 0.12}
        m = A.marcos(st, cfg())
        self.assertIn("em pausa", m[0])
        st["risco"] = {"dd": 0.0}
        self.assertIn("A ATUAR", A.marcos(st, cfg())[0])

    def test_ligado_sem_operacoes_fica_calado(self):
        self.assertEqual(A.marcos({"ledger": reg(BOM[:20])}, cfg()), [])


class Tamanho(unittest.TestCase):
    """O limite de perda acelerado chega mesmo ao tamanho da ordem (engine/risk.sizing)."""
    def base(self):
        from engine import config
        c = dict(config.load(), capital_usdc=1000, compound=True, fixed_position_usdc=220,
                 max_risk_usdc=5.0, real_autorizados=["PANICO_L10"], modo_acelerado={"ligado": True},
                 panico_real=None)
        return c

    def test_perda_no_stop_sobe_de_5_para_25(self):
        from engine import risk
        c = self.base()
        st = {"ledger": reg(BOM)}
        normal, _ = risk.sizing(4.0, 0.04, 100.0, c)
        ac, _ = risk.sizing(4.0, 0.04, 100.0, A.cfg_para("PANICO_L10", st, c))
        self.assertAlmostEqual(normal["usdc"]["risk_usdc"], 5.0, places=1)
        self.assertAlmostEqual(ac["usdc"]["risk_usdc"], 25.0, places=1)
        self.assertLessEqual(ac["leverage"]["use"], 10)

    def test_stop_largo_nunca_passa_do_teto(self):
        from engine import risk
        c = self.base()
        ac, _ = risk.sizing(15.0, 0.15, 100.0, A.cfg_para("PANICO_L10", {"ledger": reg(BOM)}, c))
        self.assertLessEqual(ac["usdc"]["risk_usdc"], 25.0 + 1e-6)

    def test_outra_estrategia_fica_normal(self):
        c = self.base()
        self.assertIs(A.cfg_para("SHORT_TURTLE", {"ledger": reg(BOM, "SHORT_TURTLE")}, c), c)

    def test_capital_desconhecido_nao_acelera(self):
        c = dict(self.base(), capital_usdc=None)
        self.assertIs(A.cfg_para("PANICO_L10", {"ledger": reg(BOM)}, c), c)

    def test_registo_vazio_ou_estranho(self):
        c = self.base()
        for st in ({}, {"ledger": None}, {"ledger": [{"strategy": "PANICO_L10"}]}, None):
            self.assertIs(A.cfg_para("PANICO_L10", st, c), c)

    def test_kelly_bordas(self):
        self.assertEqual(A.kelly([]), (None, None, None))
        self.assertEqual(A.kelly([1.0])[0], None)
        self.assertIsNone(A.kelly([0.0] * 100)[0])
        self.assertIsNone(A.kelly([-1.0] * 100)[0])


if __name__ == "__main__":
    unittest.main()
