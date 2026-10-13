"""Promocao pela arena: campeao com sinais reais, papel automatico, 1H."""
import unittest
from unittest import mock

from engine import paper_ring, promo, run, trade
from tools import arena_ringue as AR

TF = 14400


def state_with(lut, mortos=None, status=None):
    return {"arena": {"forma": {"lutadores": lut}, "mortos": mortos or {},
                      "status": status or {}}}


def f(n, r, p95):
    return {"n": n, "avg_r": r, "acaso_p95": p95}


CFG = {"fee_pct": 0.25, "risk_pct": 1.0, "max_position_pct": 25.0,
       "swing_leverage": 10.0, "capital_usdc": 85.0, "fixed_position_usdc": 18.82,
       "max_risk_usdc": 2.57, "min_order_usdc": 5.0}


def bars(n=320, t0=1_800_000_000 // TF * TF):
    out = []
    for i in range(n):
        p = 100 - i * 0.05
        out.append({"t": t0 + i * TF, "o": p, "h": p * 1.01, "l": p * 0.99, "c": p, "v": 1})
    return out


class Qualifica(unittest.TestCase):
    def test_regras(self):
        st = state_with({"A": f(26, 0.7, -0.2), "B": f(19, 2.0, 0.1),
                         "C": f(40, 0.2, 0.3), "D": f(30, 0.9, 0.1),
                         "E": f(50, -0.1, -0.5)}, mortos={"D": {}})
        self.assertEqual([k for k, _ in promo.qualified(st)], ["A"])

    def test_campeao_precisa_de_sinal_e_nao_desligado(self):
        st = state_with({"BOUNCE_V2": f(26, 0.7, -0.2), "BOUNCE_G0": f(26, 0.8, -0.2),
                         "SEM_SINAL": f(30, 1.5, 0.1)})
        self.assertEqual(promo.champion(st), "BOUNCE_G0")
        self.assertEqual(promo.champion(st, {"BOUNCE_G0"}), "BOUNCE_V2")
        # lutador novo (de um agente) com sinal: so papel, nunca campeao
        with mock.patch.object(promo, "registry", return_value={"NOVO": lambda *a: None}):
            self.assertIsNone(promo.champion(state_with({"NOVO": f(40, 2.0, 0.1)})))
        self.assertIsNone(promo.champion(state_with({"BOUNCE_G0": f(26, 0.8, -0.2)},
                                                    mortos={"BOUNCE_G0": {}})))


class Plano(unittest.TestCase):
    def test_plano_com_tres_objetivos(self):
        p, why = promo.plan_for({"stop": 95.0, "tp": [103.0, 108.0], "breakeven": True,
                                 "hold_s": 3 * 86400, "atr": 2.0}, 100.0, CFG)
        self.assertIsNone(why)
        self.assertEqual(len(p["tp"]), 3)
        self.assertEqual(len(p["partials"]), 3)
        self.assertEqual(sum(p["partials"]), 100)
        self.assertLessEqual(p["risk_usdc"], 2.57 + 1e-6)
        self.assertEqual(p["max_hold_s"], 3 * 86400)
        self.assertIsNone(promo.plan_for({"stop": 101.0, "tp": [103.0]}, 100.0, CFG)[0])

    def test_tempo_maximo_por_operacao(self):
        pos = trade.open_position({"stop": 90, "tp": [120, 130], "partials": [50, 50],
                                   "max_hold_s": 86400}, 100, 0, 0.25)
        ev = trade.step(pos, 100, 101, 99, 100, 90000, gap=False)
        self.assertTrue(pos["closed"])
        self.assertEqual(ev[-1]["event"], "TIME")


class Decisoes(unittest.TestCase):
    def test_sinal_fresco_vira_compra_real_uma_vez(self):
        c4 = bars()
        now = c4[-1]["t"] + TF + 60
        sig = {"stop": 80.0, "tp": [90.0, 95.0], "partials": [50, 50], "breakeven": True,
               "hold_s": 3 * 86400, "t_sig": c4[-1]["t"] + TF, "atr": 1.5, "gatilho": "x"}
        row = {"asset": "AAA", "price": 84.1,
               "decision": {"decision": "NO TRADE", "venue": {"pair": "AAA/USDC"}}}
        st = state_with({"BOUNCE_G0": f(26, 0.8, -0.2)})
        with mock.patch.object(promo, "registry", return_value={"BOUNCE_G0": lambda c, px, cfg: sig}):
            d = promo.decisions(st, [row], {"AAA": c4}, CFG, now, "BOUNCE_G0", True, lambda a: None)
            self.assertEqual(d["AAA"]["decision"], "LONG")
            self.assertEqual(d["AAA"]["mode"], "REAL")
            self.assertEqual(d["AAA"]["strategy"], "BOUNCE_G0")
            # a mesma vela nao da segundo sinal
            self.assertEqual(promo.decisions(st, [row], {"AAA": c4}, CFG, now, "BOUNCE_G0",
                                             True, lambda a: None), {})
            # evento de risco ou mercado em baixa: nada
            st2 = state_with({"BOUNCE_G0": f(26, 0.8, -0.2)})
            self.assertEqual(promo.decisions(st2, [row], {"AAA": c4}, CFG, now, "BOUNCE_G0",
                                             True, lambda a: "CPI"), {})
            self.assertEqual(promo.decisions(st2, [row], {"AAA": c4}, CFG, now, "BOUNCE_G0",
                                             False, lambda a: None), {})

    def test_texto_do_alerta(self):
        p, _ = promo.plan_for({"stop": 95.0, "tp": [103.0, 108.0], "breakeven": True,
                               "hold_s": 3 * 86400, "atr": 2.0}, 100.0, CFG)
        s = {"asset": "AAA", "pair": "AAA/USDC", "venue": "Bybit EU", "plan": p,
             "strategy": "BOUNCE_G0", "mode": "REAL", "direction": "LONG"}
        txt = run.alert_text({"event": "ISSUED", "id": "x"}, {"x": s}, "nota")
        self.assertIn("Campeão da arena", txt)
        self.assertIn("3 dia", txt)


class PapelAutomatico(unittest.TestCase):
    def test_qualificado_sem_papel_proprio_abre_e_fecha(self):
        c4 = bars()
        now = c4[-1]["t"] + TF + 60
        sig = {"stop": 80.0, "tp": [90.0], "partials": [100], "breakeven": True,
               "hold_s": 86400, "t_sig": c4[-1]["t"] + TF}
        st = state_with({"NOVO": f(25, 0.6, 0.1)})
        rows = [{"asset": "AAA", "price": 84.1}]
        with mock.patch.object(promo, "registry", return_value={"NOVO": lambda c, px, cfg: sig}):
            out = paper_ring.update(st, rows, {"AAA": c4}, now)
            self.assertEqual(out["NOVO"]["open"], ["AAA"])
            later = c4 + [{"t": c4[-1]["t"] + TF * (k + 1), "o": 85, "h": 91, "l": 84,
                           "c": 90, "v": 1} for k in range(2)]
            out = paper_ring.update(st, rows, {"AAA": later}, now + 3 * TF)
            self.assertEqual(out["NOVO"]["n"], 1)
        from engine import arena
        self.assertTrue(any(k == "NOVO" for k, _, _ in arena.trades(st)))


class Ringue1H(unittest.TestCase):
    def test_registo_de_sinais(self):
        self.assertIn("BOUNCE_G0", AR.SINAIS)
        self.assertIsNone(AR.SINAIS["BOUNCE_G0"](bars(), 84.0))   # sem sobrevenda

    def test_1h_sem_look_ahead(self):
        c1 = []
        t0 = 1_800_000_000 // 3600 * 3600
        for i in range(600):
            p = 100 - (i % 120) * 0.3 if (i % 120) < 60 else 82 + (i % 120 - 60) * 0.3
            c1.append({"t": t0 + i * 3600, "o": p, "h": p * 1.004, "l": p * 0.996, "c": p, "v": 1})
        above = {x["t"] // 86400: True for x in c1}
        full = AR.bounce_1h_trades("AAA", c1, above, t0)
        if full:
            cut = full[0][1]["t"] + 2 * 86400
            part = AR.bounce_1h_trades("AAA", [x for x in c1 if x["t"] < cut], above, t0)
            self.assertEqual(round(part[0][1]["r"], 6), round(full[0][1]["r"], 6))


class VariosCampeoes(unittest.TestCase):
    def test_todos_os_qualificados_revistos_dao_sinais(self):
        st = state_with({"BOUNCE_G0": f(26, 0.8, -0.2), "BOUNCE_X30": f(64, 0.4, 0.07),
                         "DIP_TREND": f(42, 0.02, 0.07)})
        self.assertEqual(promo.champions(st), ["BOUNCE_G0", "BOUNCE_X30"])

    def test_melhor_campeao_com_sinal_ganha_a_moeda_e_evento_fica_registado(self):
        c4 = bars()
        now = c4[-1]["t"] + TF + 60
        sig = {"stop": 80.0, "tp": [90.0, 95.0], "partials": [50, 50], "breakeven": True,
               "hold_s": 3 * 86400, "t_sig": c4[-1]["t"] + TF, "atr": 1.5}
        row = {"asset": "AAA", "price": 84.1,
               "decision": {"decision": "NO TRADE", "venue": {"pair": "AAA/USDC"}}}
        reg = {"BOUNCE_G0": lambda c, px, cfg: None, "BOUNCE_X30": lambda c, px, cfg: sig}
        st = {}
        with mock.patch.object(promo, "registry", return_value=reg):
            d = promo.decisions(st, [row], {"AAA": c4}, CFG, now,
                                ["BOUNCE_G0", "BOUNCE_X30"], True, lambda a: None)
            self.assertEqual(d["AAA"]["strategy"], "BOUNCE_X30")
            st2 = {}
            promo.decisions(st2, [row], {"AAA": c4}, CFG, now, ["BOUNCE_X30"], True,
                            lambda a: "CPI")
            self.assertEqual(st2["promo_lost"][0]["asset"], "AAA")

    def test_novos_lutadores_no_ringue(self):
        for k in ("BOUNCE_X30", "DIP_TREND", "CAPITULACAO"):
            self.assertIn(k, AR.SINAIS)
            self.assertIn(k, promo.REAL_OK)
        self.assertIsNone(AR.sig_x30(bars()))
        self.assertIsNone(AR.sig_capitulacao(bars()))

    def test_generico_sem_look_ahead(self):
        import random
        rnd = random.Random(3)
        c4, p = [], 100.0
        t0 = 1_800_000_000 // TF * TF
        for i in range(700):
            p *= 1 + rnd.uniform(-0.03, 0.03)
            c4.append({"t": t0 + i * TF, "o": p, "h": p * 1.015, "l": p * 0.985, "c": p, "v": 1 + rnd.random()})
        above = {x["t"] // 86400: True for x in c4}
        full = AR.generic_trades("AAA", c4, above, t0, "BOUNCE_X30", AR.sig_x30)
        self.assertTrue(full)
        cut = full[0][1]["t"] + 4 * 86400
        part = AR.generic_trades("AAA", [x for x in c4 if x["t"] < cut], above, t0,
                                 "BOUNCE_X30", AR.sig_x30)
        self.assertEqual(round(part[0][1]["r"], 6), round(full[0][1]["r"], 6))


class Admin(unittest.TestCase):
    def test_comandos_da_sessao_aplicados_uma_vez(self):
        import json, os, tempfile
        st = {"ledger": [{"id": "N", "kind": "1D", "asset": "NEAR", "status": "OPEN",
                          "executed": True, "exec_price": 5.92, "entry": 5.9, "stop": 4.69}]}
        d = tempfile.mkdtemp()
        p = os.path.join(d, "admin.json")
        with open(p, "w") as fh:
            json.dump({"comandos": [{"id": "a", "texto": "/fechei NEAR 5.143"},
                                    {"id": "b", "texto": "/capital 83.66"}]}, fh)
        out = run.apply_admin(st, p, now=100)
        self.assertEqual(len(out), 2)
        self.assertEqual(st["capital"], 83.66)
        self.assertEqual(st["ledger"][0]["user_exit"], 5.143)
        self.assertEqual(run.apply_admin(st, p, now=200), [])
        self.assertEqual(run.apply_admin(st, os.path.join(d, "nada.json")), [])


class CadeiaDeQuedas(unittest.TestCase):
    def test_no_maximo_duas_entradas_por_vela(self):
        c4 = bars()
        now = c4[-1]["t"] + TF + 60
        sig = {"stop": 80.0, "tp": [90.0, 95.0], "partials": [50, 50], "breakeven": True,
               "hold_s": 3 * 86400, "t_sig": c4[-1]["t"] + TF, "atr": 1.5}
        rows = [{"asset": a, "price": 84.1,
                 "decision": {"decision": "NO TRADE", "venue": {"pair": a + "/USDC"}}}
                for a in ("AAA", "BBB", "CCC", "DDD")]
        st = {}
        with mock.patch.object(promo, "registry", return_value={"BOUNCE_G0": lambda c, px, cfg: sig}):
            d = promo.decisions(st, rows, {r["asset"]: c4 for r in rows}, CFG, now,
                                ["BOUNCE_G0"], True, lambda a: None)
            self.assertEqual(len(d), 2)
            self.assertEqual(len(st["promo_lost"]), 2)
            self.assertIn("quedas em cadeia", st["promo_lost"][0]["reason"])
            # scan seguinte na mesma vela: nada de novo
            self.assertEqual(promo.decisions(st, rows, {r["asset"]: c4 for r in rows}, CFG,
                                             now + 300, ["BOUNCE_G0"], True, lambda a: None), {})


class FiltrosNovos(unittest.TestCase):
    def test_filtros_e_contexto(self):
        c4 = bars()
        AR.CTX.update(btc=c4, funding={"AAA": [(c4[-1]["t"], -0.0001)]}, asset="AAA")
        self.assertAlmostEqual(AR._btc_ret(c4[-1]["t"] + TF, 6), c4[-1]["c"] / c4[-7]["c"] - 1)
        for k in ("BOUNCE_FLUXO", "BOUNCE_FORTE", "BOUNCE_SQUEEZE", "BOUNCE_ISOLADA"):
            self.assertIn(k, AR.SINAIS)
            self.assertIn(k, promo.REAL_OK)
            self.assertIsNone(AR.NEW_SIGS[k](c4))         # sem sobrevenda: nada
        base = {"stop": 80.0, "tp": [90.0], "partials": [100], "breakeven": True, "hold_s": 1}
        with mock.patch.object(AR, "sig_x30", return_value=dict(base)):
            c = [dict(x) for x in c4]
            c[-1].update(tb=0.4, v=1)
            self.assertIsNone(AR.sig_fluxo(c))
            c[-1].update(tb=0.7, v=1)
            self.assertIsNotNone(AR.sig_fluxo(c))
            self.assertIsNotNone(AR.sig_squeeze(c4))       # funding negativo
            AR.CTX["funding"] = {"AAA": [(c4[-1]["t"], 0.0001)]}
            self.assertIsNone(AR.sig_squeeze(c4))
        AR.CTX.update(btc=None, funding={}, asset=None)
