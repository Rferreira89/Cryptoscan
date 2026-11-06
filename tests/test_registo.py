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
        ops, _, _ = MG.migrar(STATE, OKX, TFS)
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
        ops, _, _ = MG.migrar(STATE, OKX, TFS)
        c = [o for o in ops if o["estrategia"] == "TF-SHORT conta"][0]["custos"]
        self.assertEqual((c["comissao"], c["financiamento"]), (0.004, 0.001)); self.assertIsNone(c["spread"])


class Metricas(unittest.TestCase):
    def test_uniformes(self):
        ops, _, _ = MG.migrar(STATE, OKX, TFS)
        m = G.tabela(ops)[("LIQUIDITY_SWEEP", "executada")]
        self.assertEqual((m["fechadas"], m["com_r"]), (2, 2)); self.assertAlmostEqual(m["soma_r"], 0.03)
        self.assertAlmostEqual(m["expectativa_r"], 0.015); self.assertAlmostEqual(m["profit_factor"], round(1.06 / 1.03, 3))
        self.assertAlmostEqual(m["queda_max_r"], 1.03); self.assertEqual(m["acerto_pct"], 50.0)
        self.assertEqual(set(m["por_moeda"]), {"PUMP", "ICP"}); self.assertIn("BEAR", m["por_regime"])
        p = G.tabela(ops)[("PANICO_BYBIT", "papel")]
        self.assertAlmostEqual(p["queda_max_r"], 1.0); self.assertAlmostEqual(p["profit_factor"], 0.5)

    def test_sem_r_fica_fora_das_contas(self):
        ops, _, _ = MG.migrar(STATE, OKX, TFS)
        m = G.tabela(ops)[("SHORT_TURTLE", "executada")]
        self.assertEqual((m["fechadas"], m["sem_r"], m["expectativa_r"]), (1, 1, None))

    def test_real_e_simulado_nunca_se_somam(self):
        ops, _, _ = MG.migrar(STATE, OKX, TFS)
        h40 = [o for o in ops if o["estrategia"] == "H40"]
        with self.assertRaises(ValueError):
            G.metricas(h40)
        t = G.tabela(ops)
        self.assertEqual(t[("H40", "executada")]["fechadas"], 1); self.assertEqual(t[("H40", "papel")]["fechadas"], 1)


class Preservacao(unittest.TestCase):
    def test_nada_se_perde(self):
        antes = copy.deepcopy((STATE, OKX, TFS))
        ops, rec, _ = MG.migrar(STATE, OKX, TFS)
        self.assertTrue(all(r["ok"] for r in rec.values()), rec)
        self.assertEqual(rec["state.ledger"]["originais"], 4); self.assertEqual(rec["state.ledger"]["soma_r_migrada"], 0.03)
        self.assertEqual((STATE, OKX, TFS), antes)                        # os originais nao sao alterados
        o = [x for x in ops if x["id_origem"] == "PUMP-LIQUIDITY_SWEEP-1"][0]
        self.assertEqual(o["bruto"], STATE["ledger"][0])                  # registo original inteiro
        o["bruto"]["real_r"] = 99
        self.assertEqual(STATE["ledger"][0]["real_r"], -1.03)             # copia, nao referencia

    def test_reconciliacao_deteta_perdas(self):
        ops, _, _ = MG.migrar(STATE, OKX, TFS)
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


class Completar(unittest.TestCase):
    FORMA = {"lutadores": {"PULLBACK": {"n": 47, "wins": 22, "avg_r": -0.119, "total_r": -5.59, "veredicto": "MORTA"}}}
    LIGA = {"tabela": [{"id": "BOUNCE_AMPLITUDE", "n": 12, "avg_r": 0.72}]}

    def test_classes_e_campos_em_falta(self):
        ops, _, _ = MG.migrar(STATE, OKX, TFS)
        c = {o["id_origem"]: o for o in ops}
        self.assertEqual(c["PUMP-LIQUIDITY_SWEEP-1"]["classe"], "executada")
        self.assertEqual(c["BNB-PULLBACK-3"]["classe"], "sinal_nao_executado")
        self.assertIn("regime", c["PUMP-LIQUIDITY_SWEEP-1"]["em_falta"]); self.assertNotIn("R", c["PUMP-LIQUIDITY_SWEEP-1"]["em_falta"])
        self.assertIn("R", c["SEI-SHORT_TURTLE-5"]["em_falta"])
        with self.assertRaises(ValueError):
            G.op("X", "real", "okx", "A", "f", "1", {}, classe="papel")       # classe tem de combinar com a origem

    def test_r_de_fecho_manual_e_alerta_de_execucao_aberta(self):
        st = {"ledger": [
            {"id": "paper-NEAR-1", "status": "CLOSED", "executed": True, "real_r": None, "user_result_r": -0.64, "result_r": -1.0, "asset": "NEAR", "strategy": "TREND_DAILY"},
            {"id": "SEI-SHORT_TURTLE-2", "status": "CLOSED", "executed": True, "real_r": None, "result_r": 1.307, "real": {"fechada": False, "n": 1}, "asset": "SEI", "strategy": "SHORT_TURTLE"}]}
        ops, _, _ = MG.migrar(st, {}, {})
        near, sei = ops
        self.assertEqual((near["R"], near["r_fonte"], near["R_sinal"]), (-0.64, "user_result_r", -1.0))
        self.assertIsNone(sei["R"]); self.assertEqual(sei["R_sinal"], 1.307); self.assertIn("NAO fechada", sei["alerta"])

    def test_arena_e_liga_preservadas_e_sem_contar_duas_vezes(self):
        st = dict(STATE, arena={"ctrl": {"PUMP-LIQUIDITY_SWEEP-1": [-1.0, 0.5, 2.0]}, "status": {"BREAKOUT": "MORTA"}})
        ops, rec, ag = MG.migrar(st, OKX, TFS, self.FORMA, self.LIGA)
        self.assertTrue(rec["arena.forma"]["ok"]); self.assertTrue(rec["liga"]["ok"]); self.assertTrue(rec["arena.ctrl"]["ok"])
        self.assertEqual(rec["arena.ctrl"]["ligados_a_operacoes"], 1)
        o = [x for x in ops if x["id_origem"] == "PUMP-LIQUIDITY_SWEEP-1"][0]
        self.assertEqual(o["controlo_acaso"]["n"], 3); self.assertEqual(o["R"], -1.03)        # o R da operacao nao muda
        self.assertEqual(len(ops), len(MG.migrar(STATE, OKX, TFS)[0]))                          # agregados nao viram operacoes
        liga = [a for a in ag if a["fonte"] == "liga"][0]; self.assertTrue(liga["derivado_de"])
        self.assertEqual([a for a in ag if a["fonte"] == "arena.forma"][0]["origem"], "investigacao")

    def test_relatorio_semanal_separa_os_blocos(self):
        import relatorio_semanal as RS
        ops, rec, ag = MG.migrar(STATE, OKX, TFS, self.FORMA, self.LIGA)
        t = RS.texto({"ops": ops, "agregados": ag, "reconciliacao": rec}, "2026-S45")
        for titulo in ("Real: operações executadas", "Sinais reais que não chegaram", "Papel", "Sombra", "Investigação: arena", "Liga semanal",
                       "Campos em falta", "Alertas", "Preservação: todas as fontes conferem"):
            self.assertIn(titulo, t)
        bloco_real = t.split("## Real")[1].split("## ")[0]
        self.assertIn("LIQUIDITY_SWEEP", bloco_real); self.assertNotIn("PANICO_BYBIT", bloco_real)
