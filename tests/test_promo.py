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

    def test_sinal_sem_liquidez_ou_sem_plano_fica_registado(self):
        c4 = bars()
        now = c4[-1]["t"] + TF + 60
        sig = {"stop": 80.0, "tp": [90.0, 95.0], "partials": [50, 50], "breakeven": True,
               "hold_s": 3 * 86400, "t_sig": c4[-1]["t"] + TF, "atr": 1.5}
        mau = dict(sig, stop=85.0)                       # stop acima do preco: sem plano
        illiq = {"asset": "AAA", "price": 84.1,
                 "decision": {"decision": "NO TRADE", "reason": "volume baixo na Bybit UE"}}
        row = {"asset": "BBB", "price": 84.1,
               "decision": {"decision": "NO TRADE", "venue": {"pair": "BBB/USDC"}}}
        st = state_with({"BOUNCE_G0": f(26, 0.8, -0.2), "BOUNCE_V2": f(26, 0.7, -0.2)})
        reg = {"BOUNCE_G0": lambda c, px, cfg: mau, "BOUNCE_V2": lambda c, px, cfg: mau}
        with mock.patch.object(promo, "registry", return_value=reg):
            d = promo.decisions(st, [illiq, row], {"AAA": c4, "BBB": c4}, CFG, now,
                                ["BOUNCE_G0", "BOUNCE_V2"], True, lambda a: None)
        self.assertEqual(d, {})
        why = {x["asset"]: x["reason"] for x in st["promo_lost"]}
        self.assertIn("liquidez: volume baixo", why["AAA"])
        self.assertTrue(why["BBB"].startswith("plano:"))
        self.assertEqual(len(st["promo_lost"]), 2)       # uma vez por moeda, nao por campeao
        # se o 2.o campeao tiver plano, o sinal passa (o 1.o recusado nao bloqueia)
        st = state_with({"BOUNCE_G0": f(26, 0.8, -0.2), "BOUNCE_V2": f(26, 0.7, -0.2)})
        reg["BOUNCE_V2"] = lambda c, px, cfg: sig
        with mock.patch.object(promo, "registry", return_value=reg):
            d = promo.decisions(st, [row], {"BBB": c4}, CFG, now, ["BOUNCE_G0", "BOUNCE_V2"],
                                True, lambda a: None)
        self.assertEqual(d["BBB"]["strategy"], "BOUNCE_V2")

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
            self.assertRegex(st["promo_lost"][0]["reason"], "quedas em cadeia|diversificação")
            # mesma familia na mesma vela = uma so aposta: cada uma leva metade
            ps = [x["plan"] for x in d.values()]
            self.assertTrue(all(p["cluster"]["n"] == 2 for p in ps))
            solo = promo.plan_for(sig, 84.1, CFG)[0]
            for p in ps:
                self.assertLess(p["position_usdc"] if p.get("position_usdc") else p["position_pct"],
                                (solo.get("position_usdc") or solo["position_pct"]) * 0.6)
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


class ReduzirPerdas(unittest.TestCase):
    def test_saida_sem_reacao(self):
        pos = trade.open_position({"stop": 90, "tp": [110, 120], "partials": [50, 50],
                                   "no_react_s": 43200}, 100, 0, 0.25)
        trade.step(pos, 100, 101, 99, 99.5, 3600, gap=False)
        self.assertFalse(pos["closed"])
        ev = trade.step(pos, 99.5, 100, 99, 99.0, 43300, gap=False)
        self.assertTrue(pos["closed"])
        self.assertEqual(ev[-1]["event"], "NOREACT")
        self.assertGreater(pos["r"], -1)                      # perde menos do que o stop
        pos2 = trade.open_position({"stop": 90, "tp": [110], "partials": [100],
                                    "no_react_s": 43200}, 100, 0, 0.25)
        trade.step(pos2, 101, 102, 100.5, 101.5, 43300, gap=False)
        self.assertFalse(pos2["closed"])                      # reagiu: fica

    def test_stop_acompanha_o_lucro(self):
        pos = trade.open_position({"stop": 90, "tp": [105, 140], "partials": [50, 50],
                                   "trail_r": 1.0}, 100, 0, 0.25, breakeven=True)
        trade.step(pos, 101, 106, 101, 105, 1)                # TP1
        trade.step(pos, 105, 125, 112, 124, 2)                # sobe ate 125
        self.assertAlmostEqual(pos["stop"], 115.0, places=6)  # 125 - 1 risco (10)
        trade.step(pos, 124, 124, 114, 115, 3)
        self.assertTrue(pos["closed"])
        self.assertGreater(pos["r"], 0.5)

    def test_duas_perdas_seguidas(self):
        from engine import scanner
        led = [{"executed": True, "status": "CLOSED", "closed_at": 1, "result_r": 1.0},
               {"executed": True, "status": "CLOSED", "closed_at": 2, "result_r": -1.0},
               {"executed": False, "status": "CLOSED", "closed_at": 3, "result_r": 2.0},
               {"executed": True, "status": "CLOSED", "closed_at": 4, "result_r": -0.5}]
        self.assertEqual(scanner.losing_streak(led), 2)
        led.append({"executed": True, "status": "CLOSED", "closed_at": 5, "result_r": 0.3})
        self.assertEqual(scanner.losing_streak(led), 0)

    def test_lutadores_de_gestao(self):
        for k in ("BOUNCE_NOREACT", "BOUNCE_TRAIL", "BOUNCE_HORAS"):
            self.assertIn(k, AR.SINAIS)
            self.assertIn(k, promo.REAL_OK)


class AuditoriaOutubro(unittest.TestCase):
    def test_dinheiro_real_so_com_ganho_minimo(self):
        st = state_with({"BOUNCE_G0": f(30, 0.40, -0.2), "DIP_TREND": f(80, 0.08, -0.1)})
        with mock.patch.object(promo, "registry", return_value={"BOUNCE_G0": 1, "DIP_TREND": 1}):
            self.assertEqual(promo.champions(st), ["BOUNCE_G0"])
            self.assertIn("DIP_TREND", [k for k, _ in promo.qualified(st)])   # continua qualificado

    def test_arena_so_em_moedas_negociaveis(self):
        from tools import arena_ringue as AR
        cfg = {"max_venue_spread_pct": 0.30, "min_venue_volume_usd": 5000}
        v = lambda vol, sp, stale=False: {"last": 1.0, "volume_usd": vol, "spread_pct": sp, "stale": stale}
        ok, fora = AR.liquid({"ETH": v(1e6, 0.02), "FIL": v(3000, 0.02), "WIF": v(9e4, 0.4),
                              "S": v(9e4, 0.05, True)}, cfg)
        self.assertEqual(ok, ["BTC", "ETH"])
        self.assertEqual(fora, ["FIL", "S", "WIF"])


class Semana1Validacao(unittest.TestCase):
    def test_fora_da_amostra_e_custo_real(self):
        from tools import arena_ringue as AR
        now = 100 * 86400
        g = {"stop": -0.04}
        trs = [{"asset": "A", "t": now - 60 * 86400, "r": 0.5, "geo": g} for _ in range(10)] + \
              [{"asset": "A", "t": now - 5 * 86400, "r": -0.2, "geo": g} for _ in range(6)]
        v = AR.validacao(trs, now, {"A": 0.6})
        self.assertEqual(v["dentro"]["n"], 10)
        self.assertEqual(v["fora"]["n"], 6)
        self.assertAlmostEqual(v["dentro"]["avg_r_liq"], 0.5 - 0.004 / 0.04, places=3)
        self.assertFalse(v["passa"])                      # fora da amostra perde
        trs[-6:] = [dict(t, r=0.4) for t in trs[-6:]]
        self.assertTrue(AR.validacao(trs, now, {"A": 0.2})["passa"])

    def test_metricas_da_carteira(self):
        from tools import auditoria_sinais as A
        sig = [{"passa": True, "r": r} for r in (1.0, -1.0, -1.0, 2.0)] + [{"filtro": "x", "r": 5}]
        m = A.metricas(sig, 30, 1.5)
        self.assertEqual((m["n"], m["total_r"], m["drawdown_max_r"]), (4, 1.0, 2.0))
        self.assertEqual(m["ops_mes"], 4.0)
        self.assertLess(m["ruina_50pct"], 0.05)
        self.assertEqual(A.metricas([], 30, 1.5), {"n": 0})


class Semana1Carteira(unittest.TestCase):
    def test_variantes_de_carteira(self):
        from tools import auditoria_sinais as A
        mk = lambda t, a, r: {"t": t, "ativo": a, "rank": 0, "familia": "sobrevenda", "r": r, "fim": t + 10}
        cands = [mk(1, "A", 1.0), mk(1, "B", 1.0), mk(1, "C", -1.0), mk(20, "D", 0.5)]
        self.assertEqual(len(A.carteira_com(cands, 4, 2, 1)), 2)
        self.assertEqual(len(A.carteira_com(cands, 4, 4, 4)), 4)
        self.assertEqual(len(A.carteira_com(cands, 1, 4, 4)), 2)
        v = A.comparar([dict(c, t=c["t"] + 10**6) for c in cands], 365, 1.5, 0)
        self.assertEqual(v["ultimos_90d"]["4/4/2"]["n"], 3)


class CampeoesPorFase(unittest.TestCase):
    def st(self):
        lr = lambda n, r, p95, met: {"por_regime": {"queda": {"n": n, "avg_r": r, "acaso_p95": p95, "metades": met}}}
        return {"arena": {"forma": {"lutadores": {}}, "longo": {"lutadores": {
            "SHORT_X30": lr(113, 0.35, 0.10, [0.3, 0.4]),
            "SHORT_ISOLADA": lr(96, 0.29, 0.12, [0.5, -0.1]),     # uma metade a perder
            "SHORT_FLUXO": lr(42, 0.18, 0.24, [0.2, 0.2]),        # nao bate o acaso
            "SHORT_TURTLE": lr(229, 0.10, 0.05, [0.1, 0.1])}}}}   # abaixo de 0,15R

    def test_so_quem_prova_na_fase(self):
        self.assertEqual([k for k, _ in promo.regime_qualified(self.st(), "queda")], ["SHORT_X30"])
        self.assertEqual(promo.regime_qualified(self.st(), "subida"), [])
        self.assertEqual(promo.regime_qualified(self.st(), None), [])
        sem_metades = self.st()
        del sem_metades["arena"]["longo"]["lutadores"]["SHORT_X30"]["por_regime"]["queda"]["metades"]
        self.assertEqual(promo.regime_qualified(sem_metades, "queda"), [])

    def test_so_com_o_ok_e_so_shorts_com_o_btc_em_baixa(self):
        reg = {"SHORT_X30": 1, "BOUNCE_G0": 1}
        with mock.patch.object(promo, "registry", return_value=reg):
            self.assertEqual(promo.champions(self.st(), (), "queda"), [])
            self.assertEqual(promo.champions(self.st(), (), "queda", True), ["SHORT_X30"])
        c4 = bars()
        now = c4[-1]["t"] + TF + 60
        row = {"asset": "AAA", "price": 84.1,
               "decision": {"decision": "NO TRADE", "venue": {"pair": "AAA/USDC"}}}
        longo = {"stop": 80.0, "tp": [90.0], "partials": [100], "hold_s": 86400, "t_sig": c4[-1]["t"] + TF}
        st = state_with({"BOUNCE_G0": f(26, 0.8, -0.2)})
        with mock.patch.object(promo, "registry", return_value={"BOUNCE_G0": lambda c, px, cfg: longo}):
            self.assertEqual(promo.decisions(st, [row], {"AAA": c4}, CFG, now, ["BOUNCE_G0"], False,
                                             lambda a: None), {})


class ContasDoMes(unittest.TestCase):
    def test_quem_nao_paga_as_contas_perde_o_lugar(self):
        st = state_with({"BOUNCE_HORAS": f(44, 0.37, -0.0), "BOUNCE_X30": f(59, 0.42, -0.03)})
        lut = st["arena"]["forma"]["lutadores"]
        lut["BOUNCE_HORAS"]["validacao"] = {"fora": {"n": 20, "avg_r_liq": -0.171}}
        lut["BOUNCE_X30"]["validacao"] = {"fora": {"n": 27, "avg_r_liq": 0.147}}
        sus = promo.suspended(st)
        self.assertIn("contas do mês", sus["BOUNCE_HORAS"])
        self.assertNotIn("BOUNCE_X30", sus)
        with mock.patch.object(promo, "registry", return_value={"BOUNCE_HORAS": 1, "BOUNCE_X30": 1}):
            self.assertEqual(promo.champions(st), ["BOUNCE_X30"])
        lut["BOUNCE_HORAS"]["validacao"] = {"fora": {"n": 3, "avg_r_liq": -1.0}}   # poucas: ainda nao se cobra
        self.assertNotIn("BOUNCE_HORAS", promo.suspended(st))
