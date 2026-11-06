"""(06/11, P3) Registo unico: forma comum, origens separadas, metricas uniformes e preservacao total dos dados."""
import copy
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
from engine import registo as G  # noqa: E402
import registo_migrar as MG  # noqa: E402

STATE = {
    "ledger": [
        {"id": "PUMP-LIQUIDITY_SWEEP-1", "status": "CLOSED", "executed": True, "real_r": -1.03, "asset": "PUMP", "side": "LONG",
         "strategy": "LIQUIDITY_SWEEP", "opened_at": 100, "closed_at": 200, "reason": "STOP"},
        {"id": "ICP-LIQUIDITY_SWEEP-2", "status": "CLOSED", "executed": True, "real_r": 1.06, "asset": "ICP", "side": "LONG",
         "strategy": "LIQUIDITY_SWEEP", "opened_at": 300, "closed_at": 700000, "reason": "BREAKEVEN", "regime": "BEAR"},
        {"id": "BNB-PULLBACK-3", "status": "CLOSED", "executed": False, "result_r": -1.0, "asset": "BNB", "strategy": "PULLBACK"},
        {"id": "AVAX-SHORT_TURTLE-4", "status": "OPEN", "executed": False},
        {"id": "SEI-SHORT_TURTLE-5", "status": "CLOSED", "executed": True, "real_r": None, "asset": "SEI", "strategy": "SHORT_TURTLE"}],
    "papel_panico": {"fechadas": [{"asset": "CRV", "t_fill": 1, "t_fim": 2, "r": 0.5, "motivo": "alvo"},
                                  {"asset": "ENA", "t_fill": 3, "t_fim": 4, "r": -1.0, "motivo": "stop"}]},
    "paper_shadow": {"closed": [{"asset": "BCH", "strategy": "BOUNCE_X30", "opened_at": 1, "closed_at": 2, "r": -0.9}]},
    "paper_ring": {"BOUNCE_V2": {"closed": [{"asset": "X", "opened_at": 1, "closed_at": 9, "r": 0.2}]}, "VAZIO": {"closed": []}},
}
OKX = {"real": {"hist": [{"asset": "HUMA", "estado": "fechada", "entrada": 0.01858, "stop": 0.0155, "saida": 0.0155, "ordId": "9",
                          "t_fill": 1, "fechado": 2, "ret_pct": -16.58},
                         {"asset": "TRUMP", "estado": "cancelada"}]},
       "fechadas": [{"asset": "HUMA", "t_sig": 1, "r": -1.006, "motivo": "stop", "t_fim": 2}],
       "recuo": {"fechadas": []}}
TFS = {"sinais": {"fechadas": [{"moeda": "DOGE", "t": 1, "t_saida": 2, "R": 0.4, "motivo": "regra", "validado": True}]},
       "conta": {"fechadas": [{"moeda": "DOGE", "t": 1, "t_saida": 2, "R": 0.4, "motivo": "regra", "custos_usd": 0.004, "fund_usd": 0.001}]}}


class Forma(unittest.TestCase):
    def test_origens_e_campos(self):
        ops, _ = MG.migrar(STATE, OKX, TFS)
        por = {(o["estrategia"], o["origem"]) for o in ops}
        self.assertIn(("LIQUIDITY_SWEEP", "real"), por); self.assertIn(("PULLBACK", "sombra"), por)
        self.assertIn(("H40", "real"), por); self.assertIn(("H40", "papel"), por)
        self.assertIn(("TF-SHORT sinais", "papel"), por); self.assertIn(("TF-SHORT conta", "papel"), por)
        self.assertNotIn("AVAX", {o["moeda"] for o in ops})              # abertas nao sao operacoes fechadas
        self.assertNotIn("TRUMP", {o["moeda"] for o in ops})             # canceladas tambem nao
        h = [o for o in ops if o["fonte"] == "okx.real.hist"][0]
        self.assertAlmostEqual(h["R"], -1.0, places=3)                     # R calculado de entrada/stop/saida
        with self.assertRaises(ValueError):
            G.op("X", "imaginaria", "okx", "A", "f", "1", {})

    def test_custos_quando_existem(self):
        ops, _ = MG.migrar(STATE, OKX, TFS)
        c = [o for o in ops if o["estrategia"] == "TF-SHORT conta"][0]["custos"]
        self.assertEqual((c["comissao"], c["financiamento"]), (0.004, 0.001)); self.assertIsNone(c["spread"])


class Metricas(unittest.TestCase):
    def test_uniformes(self):
        ops, _ = MG.migrar(STATE, OKX, TFS)
        m = G.tabela(ops)[("LIQUIDITY_SWEEP", "real")]
        self.assertEqual((m["fechadas"], m["com_r"]), (2, 2)); self.assertAlmostEqual(m["soma_r"], 0.03)
        self.assertAlmostEqual(m["expectativa_r"], 0.015); self.assertAlmostEqual(m["profit_factor"], round(1.06 / 1.03, 3))
        self.assertAlmostEqual(m["queda_max_r"], 1.03); self.assertEqual(m["acerto_pct"], 50.0)
        self.assertEqual(set(m["por_moeda"]), {"PUMP", "ICP"}); self.assertIn("BEAR", m["por_regime"])
        p = G.tabela(ops)[("PANICO_BYBIT", "papel")]
        self.assertAlmostEqual(p["queda_max_r"], 1.0); self.assertAlmostEqual(p["profit_factor"], 0.5)

    def test_sem_r_fica_fora_das_contas(self):
        ops, _ = MG.migrar(STATE, OKX, TFS)
        m = G.tabela(ops)[("SHORT_TURTLE", "real")]
        self.assertEqual((m["fechadas"], m["sem_r"], m["expectativa_r"]), (1, 1, None))

    def test_real_e_simulado_nunca_se_somam(self):
        ops, _ = MG.migrar(STATE, OKX, TFS)
        h40 = [o for o in ops if o["estrategia"] == "H40"]
        with self.assertRaises(ValueError):
            G.metricas(h40)
        t = G.tabela(ops)
        self.assertEqual(t[("H40", "real")]["fechadas"], 1); self.assertEqual(t[("H40", "papel")]["fechadas"], 1)


class Preservacao(unittest.TestCase):
    def test_nada_se_perde(self):
        antes = copy.deepcopy((STATE, OKX, TFS))
        ops, rec = MG.migrar(STATE, OKX, TFS)
        self.assertTrue(all(r["ok"] for r in rec.values()), rec)
        self.assertEqual(rec["state.ledger"]["originais"], 4); self.assertEqual(rec["state.ledger"]["soma_r_migrada"], 0.03)
        self.assertEqual((STATE, OKX, TFS), antes)                        # os originais nao sao alterados
        o = [x for x in ops if x["id_origem"] == "PUMP-LIQUIDITY_SWEEP-1"][0]
        self.assertEqual(o["bruto"], STATE["ledger"][0])                  # registo original inteiro
        o["bruto"]["real_r"] = 99
        self.assertEqual(STATE["ledger"][0]["real_r"], -1.03)             # copia, nao referencia

    def test_reconciliacao_deteta_perdas(self):
        ops, _ = MG.migrar(STATE, OKX, TFS)
        falta = [o for o in ops if o["id_origem"] != "PUMP-LIQUIDITY_SWEEP-1"]
        rec = G.reconciliar({"state.ledger": ([r for r in STATE["ledger"] if r["status"] == "CLOSED"], "real_r")}, falta)
        self.assertFalse(rec["state.ledger"]["ok"])

    def test_nao_ligado_a_producao(self):
        raiz = os.path.join(os.path.dirname(__file__), "..")
        for f in ("engine/run.py", "engine/scanner.py", "engine/executor.py", "tools/okx_agente.py", "tools/okx_exec.py"):
            src = open(os.path.join(raiz, f), encoding="utf-8").read()
            self.assertNotIn("import registo", src, f); self.assertNotIn("registo as G", src, f)

if __name__ == "__main__":
    unittest.main()
