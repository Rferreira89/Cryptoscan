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
        self.assertFalse(c["modo_acelerado"]["ligado"])
        self.assertEqual(c["real_autorizados"], [])
        st = {"ledger": reg(BOM)}
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

    def test_ja_ligado_nao_pede(self):
        self.assertEqual(A.marcos({"ledger": reg(BOM)}, cfg()), [])


if __name__ == "__main__":
    unittest.main()
