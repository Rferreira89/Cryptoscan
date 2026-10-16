"""Diretor de Trading: relatorios estruturados e autorizacao das entradas."""
import unittest
from unittest import mock

from engine import consultas, diretor, run

H4 = 14400
NOW = 1_800_000_000 - (1_800_000_000 % H4) + 600     # 10 min depois do fecho de uma vela


def c4(n=200, px=100.0):
    t0 = NOW - 600 - n * H4
    return [{"t": t0 + i * H4, "o": px, "h": px * 1.01, "l": px * 0.99, "c": px, "v": 1}
            for i in range(n)]


def deps(**cores):
    nomes = ["Tendência e estrutura", "Liquidez e smart money", "Volume e fluxo", "Derivados",
             "Suportes e resistências", "Força relativa", "Sobrevenda", "Macroeconomia"]
    return [{"dep": n, "cor": cores.get(n, "amarelo"), "texto": f"leitura de {n}"} for n in nomes]


def row(dep=None, **kw):
    r = {"asset": "SOL", "price": 100.0, "divergence_pct": 0.1, "venue": {"stale": False},
         "timeframes": {"4h": {"status": "VALID"}, "1d": {"status": "VALID"}},
         "departamentos": dep if dep is not None else deps()}
    r.update(kw)
    return r


def dec(side="LONG", strategy="BOUNCE_X30", **plan):
    p = {"entry_zone": [99.0, 100.0], "entry_ref": 100.0, "stop": 95.0,
         "tp": [104.0, 108.0, 112.0], "rr": 2.0}
    if side == "SHORT":
        p.update(entry_zone=[100.0, 101.0], stop=106.0, tp=[96.0, 92.0, 88.0])
    p.update(plan)
    return {"decision": side, "strategy": strategy, "mode": "REAL", "plan": p,
            "trigger": "RSI 4H abaixo de 30"}


class Relatorios(unittest.TestCase):
    def test_campos_obrigatorios(self):
        v = diretor.review(row(), dec(), c4(), None, c4(), NOW)
        self.assertEqual(v["decisao"], "AUTORIZADO")
        self.assertEqual(len(v["relatorios"]), 9)            # lutador + 8 departamentos
        for r in v["relatorios"]:
            for k in ("agente", "ativo", "timeframe", "dados", "direcao", "condicoes",
                      "contra", "estado_dados", "invalidacao"):
                self.assertIn(k, r)
            self.assertTrue(all(z["t"] for z in r["dados"]))  # cada dado com hora
        p = v["relatorios"][0]
        self.assertEqual((p["stop"], p["alvos"][0]), (95.0, 104.0))
        self.assertIn("abaixo de 95", p["invalidacao"][0])


class Regras(unittest.TestCase):
    def test_r1_dados_atrasados_ou_indisponiveis(self):
        v = diretor.review(row(), dec(), c4(), None, None, NOW + 2 * H4)
        self.assertEqual((v["decisao"], v["estado_dados"]), ("REJEITADO", "atrasado"))
        v = diretor.review(row(timeframes={"4h": {"status": "DATA INVALID"}, "1d": {"status": "VALID"}}),
                           dec(), c4(), None, None, NOW)
        self.assertEqual(v["estado_dados"], "indisponivel")
        v = diretor.review(row(divergence_pct=1.5), dec(), c4(), None, None, NOW)
        self.assertEqual(v["decisao"], "REJEITADO")
        # aviso (DEGRADED) continua utilizavel
        v = diretor.review(row(timeframes={"4h": {"status": "DEGRADED"}, "1d": {"status": "VALID"}}),
                           dec(), c4(), None, None, NOW)
        self.assertEqual(v["decisao"], "AUTORIZADO")

    def test_r2_plano(self):
        for bad in (dict(stop=101.0), dict(tp=[99.5]), dict(rr=0.9), dict(stop=None)):
            v = diretor.review(row(), dec(**bad), c4(), None, None, NOW)
            self.assertEqual(v["decisao"], "REJEITADO", bad)
        self.assertEqual(diretor.review(row(), dec("SHORT", "SHORT_X30"), c4(), None, None, NOW)["decisao"],
                         "AUTORIZADO")
        self.assertEqual(diretor.review(row(), dec("SHORT", "SHORT_X30", stop=99.0), c4(), None, None,
                                        NOW)["decisao"], "REJEITADO")

    def test_r3_conflitos_e_premissa_da_familia(self):
        R = "vermelho"
        # sobrevenda: tendencia, volume e forca relativa contra sao a premissa
        d = deps(**{"Tendência e estrutura": R, "Volume e fluxo": R, "Força relativa": R})
        v = diretor.review(row(d), dec(), c4(), None, None, NOW)
        self.assertEqual(v["decisao"], "AUTORIZADO")
        self.assertEqual(len(v["esperado"]), 3)
        # numa estrategia de tendencia, as mesmas leituras rejeitam
        v = diretor.review(row(d), dec(strategy="TURTLE"), c4(), None, None, NOW)
        self.assertEqual(v["decisao"], "REJEITADO")
        d = deps(**{"Liquidez e smart money": R, "Suportes e resistências": R, "Sobrevenda": R})
        self.assertEqual(diretor.review(row(d), dec(), c4(), None, None, NOW)["decisao"], "REJEITADO")

    def test_r4_macro_medo(self):
        v = diretor.review(row(), dec(), c4(), {"estado": "medo"}, None, NOW)
        self.assertEqual(v["decisao"], "REJEITADO")
        v = diretor.review(row(), dec(strategy="BOUNCE_MEDO"), c4(), {"estado": "medo"}, None, NOW)
        self.assertNotIn("macroeconomia em medo: compras suspensas", v["motivos"])

    def test_r5_derivados(self):
        d = deps(**{"Derivados": "vermelho", "Suportes e resistências": "vermelho"})
        v = diretor.review(row(d), dec(), c4(), None, None, NOW)
        self.assertEqual(v["decisao"], "REJEITADO")
        self.assertIn("derivados", v["motivos"][0])


class Gate(unittest.TestCase):
    def test_rejeita_vira_no_trade_e_fica_registado(self):
        st = {}
        r = row(deps(**{"Derivados": "vermelho", "Sobrevenda": "vermelho"}))
        r["decision"] = dec()
        r["_c4"] = c4()
        diretor.gate(st, [r], {"SOL": c4()}, None, NOW)
        self.assertEqual(r["decision"]["decision"], "NO TRADE")
        self.assertTrue(r["decision"]["reason"].startswith("Diretor de Trading"))
        self.assertEqual(len(st["diretor"]["rejeitados"]), 1)
        # revista de novo no scan seguinte: sem duplicar
        r["decision"] = dec()
        diretor.gate(st, [r], {"SOL": c4()}, None, NOW + 300)
        self.assertEqual(len(st["diretor"]["rejeitados"]), 1)
        self.assertEqual(len(st["diretor"]["decisoes"]), 1)

    def test_autoriza_e_paper_nao_passa(self):
        st = {}
        r = row()
        r["decision"] = dec()
        r["decision_short"] = dict(dec("SHORT", "SHORT_X30"), mode="PAPER")
        diretor.gate(st, [r], {"SOL": c4()}, None, NOW)
        self.assertEqual(r["decision"]["decision"], "LONG")
        self.assertEqual(r["decision"]["diretor"]["decisao"], "AUTORIZADO")
        self.assertNotIn("diretor", r["decision_short"])

    def test_falha_fechada(self):
        st = {}
        r = row()
        r["decision"] = dec()
        with mock.patch.object(diretor, "review", side_effect=ValueError):
            diretor.gate(st, [r], {"SOL": c4()}, None, NOW)
        self.assertEqual(r["decision"]["decision"], "NO TRADE")

    def test_seguimento_das_rejeicoes(self):
        st = {"diretor": {"rejeitados": [
            {"t": NOW - 3 * H4, "ativo": "SOL", "lado": "LONG", "entrada": 100, "stop": 99.5,
             "tp": [110], "estado": "aberto"},
            {"t": NOW - 3 * H4, "ativo": "SOL", "lado": "LONG", "entrada": 100, "stop": 90,
             "tp": [100.5], "estado": "aberto"}]}}
        out = diretor.follow(st, {"SOL": c4()}, NOW)
        self.assertEqual((out["evitou_perda"], out["custou_ganho"]), (1, 1))


class Saidas(unittest.TestCase):
    def test_telegram_e_comando(self):
        v = diretor.review(row(), dec(), c4(), None, None, NOW)
        txt = run.diretor_lines(v)
        self.assertIn("Diretor de Trading: AUTORIZADO", txt)
        st = {}
        r = row()
        r["decision"] = dec()
        diretor.gate(st, [r], {"SOL": c4()}, None, NOW)
        res = {"diretor": diretor.summary(st, NOW)}
        self.assertIn("1 autorizadas", consultas.answer("/diretor", res, st))
        rep = consultas.answer("/diretor SOL", res, st)
        self.assertIn("Estado dos dados", rep)
        self.assertIn("Invalida se", rep)
        self.assertIn("ainda não reviu", consultas.answer("/diretor", {}, {}))


if __name__ == "__main__":
    unittest.main()


class Avaliacao(unittest.TestCase):
    def test_deps_chegam_ao_registo_e_contam(self):
        from engine import ledger
        v = diretor.review(row(deps(**{"Derivados": "verde", "Suportes e resistências": "vermelho",
                                        "Tendência e estrutura": "vermelho"})), dec(), c4(), None, None, NOW)
        self.assertEqual(v["deps"]["Derivados"], "favor")
        self.assertEqual(v["deps"]["Suportes e resistências"], "contra")
        self.assertEqual(v["deps"]["Tendência e estrutura"], "esperado")
        st = {"ledger": [{"deps": v["deps"], "status": "CLOSED", "result_r": -1.0},
                         {"deps": v["deps"], "status": "CLOSED", "result_r": 1.5},
                         {"deps": v["deps"], "status": "OPEN", "result_r": None}],
              "diretor": {"rejeitados": [{"deps": v["deps"], "estado": "evitou perda"}]}}
        sb = {t["dep"]: t for t in diretor.scoreboard(st)}
        self.assertEqual((sb["Derivados"]["n"], sb["Derivados"]["acertos"]), (3, 1))
        self.assertEqual(sb["Suportes e resistências"]["acertos"], 2)
        self.assertNotIn("Tendência e estrutura", sb)            # esperado nao conta
        self.assertNotIn("Liquidez e smart money", sb)           # neutro nao conta
        self.assertFalse(sb["Derivados"]["amostra"])
        # o sinal emitido leva as leituras para o registo
        sig = {"asset": "SOL", "pair": "SOL/USDC", "strategy": "BOUNCE_X30", "score": 75,
               "plan": {"entry_zone": [1, 2], "stop": 0.5, "tp": [3], "rr": 2, "risk_pct": 1,
                        "position_pct": 10}, "diretor": {"deps": v["deps"]}}
        s2 = {}
        ledger.apply(s2, [{"event": "ISSUED", "id": "x", "t": NOW, "signal": sig}])
        self.assertEqual(s2["ledger"][0]["deps"], v["deps"])


class SoValidadas(unittest.TestCase):
    def test_por_omissao_estrategias_nao_validadas_ficam_em_papel(self):
        from engine import config
        self.assertFalse(config.DEFAULTS["real_money_unvalidated"])

    def test_tendencia_aberta_a_real_vende_a_real(self):
        from engine import paper_trend as P
        st = {"positions": {"NEAR": {"entry": 10, "stop0": 9, "pair": "NEAR/USDC", "risk_frac": .01}},
              "equity": 1.0, "closed": []}
        ev = []
        P._close(st, ev, "NEAR", 9.5, "TRAIL", 0.0025, NOW, {"real_money_unvalidated": False})
        self.assertTrue(ev[0]["real"])                           # aberta antes da mudanca
        st["positions"]["X"] = {"entry": 10, "stop0": 9, "pair": "X/USDC", "risk_frac": .01, "real": False}
        P._close(st, ev, "X", 9.5, "TRAIL", 0.0025, NOW, {})
        self.assertFalse(ev[1]["real"])


class TendenciaFechadaAMao(unittest.TestCase):
    def test_sem_aviso_de_venda_depois_de_fechei(self):
        from engine import paper_trend as P
        st = {"paper_trend": {"positions": {"NEAR": {"entry": 10, "stop0": 9, "pair": "NEAR/USDC",
                                                       "risk_frac": .01}}, "equity": 1.0, "closed": []},
              "ledger": [{"kind": "1D", "asset": "NEAR", "status": "OPEN", "user_result_r": -0.64}]}
        ev = P.check_stops(st, {"NEAR": 8.5}, {"fee_pct": 0.25}, NOW)
        self.assertEqual(ev[0]["event"], "PAPER_SELL")
        self.assertFalse(ev[0]["real"])


class TravaoSoDinheiroReal(unittest.TestCase):
    def test_nao_executados_nao_contam(self):
        from engine import signals
        cfg = {"max_daily_loss_r": 3.0, "max_weekly_loss_r": 6.0, "cooldown_after_losses": 3}
        sigs = {k: {"id": k, "status": "CLOSED", "mode": "REAL", "closed_at": NOW - 3600 + i, "result_r": -1.0}
                for i, k in enumerate("abcde")}
        self.assertIsNotNone(signals.trading_halt(sigs, cfg, NOW))                # sem registo: conta tudo
        led = [{"id": "a", "executed": False}, {"id": "b", "executed": False},
               {"id": "c", "executed": False}, {"id": "d", "executed": True},
               {"id": "e", "executed": True, "user_result_r": 0.4}]
        self.assertIsNone(signals.trading_halt(sigs, cfg, NOW, led))
        led[2]["executed"] = None                                               # sem resposta: conta
        led[4]["user_result_r"] = None
        self.assertIn("perda diária", signals.trading_halt(sigs, cfg, NOW, led))


class MetaMilhao(unittest.TestCase):
    def test_r6_historico_na_fase_do_mercado(self):
        longo = {"BOUNCE_X30": {"por_regime": {"lateral": {"n": 30, "avg_r": -0.2},
                                               "subida": {"n": 30, "avg_r": 0.5}}}}
        v = diretor.review(row(), dec(strategy="BOUNCE_X30_R1"), c4(), None, None, NOW, "lateral", longo)
        self.assertEqual(v["decisao"], "REJEITADO")
        self.assertIn("histórico contra", v["motivos"][0])
        v = diretor.review(row(), dec(), c4(), None, None, NOW, "subida", longo)
        self.assertEqual(v["decisao"], "AUTORIZADO")
        self.assertIn("+0.50R", v["historico"])
        longo["BOUNCE_X30"]["por_regime"]["lateral"]["n"] = 5           # amostra curta: so informa
        self.assertEqual(diretor.review(row(), dec(), c4(), None, None, NOW, "lateral", longo)["decisao"],
                         "AUTORIZADO")

    def test_crescimento_e_ordem_dos_campeoes(self):
        from engine import promo
        st = {"arena": {"status": {}, "mortos": {}, "forma": {"lutadores": {
            "A": {"n": 90, "avg_r": 0.3, "acaso_p95": 0.0},      # 8 ops/mes (teto) -> 2.4R
            "B": {"n": 24, "avg_r": 0.6, "acaso_p95": 0.0}}}}}   # 8 ops/mes -> 4.8R
        self.assertEqual([k for k, _ in promo.qualified(st)], ["B", "A"])
        st["arena"]["forma"]["lutadores"]["B"]["n"] = 21           # 7 ops/mes -> 4.2R
        g = promo.growth(st, {"capital_usdc": 100, "max_risk_usdc": 2, "risk_reduced": True})
        self.assertEqual(g[0]["id"], "B")
        self.assertEqual(g[0]["r_mes"], 4.2)
        self.assertEqual(g[0]["pct_mes"], 4.2)                      # 1% de risco por operacao
        self.assertTrue(g[0]["anos"] > 0)

    def test_depositos_encurtam(self):
        from engine import meta
        m = meta.progress(None, 80)
        d = {(r, x): mm for r, x, mm in m["depositos"]}
        self.assertLess(d[(5, 300)], d[(5, 100)])
        self.assertLess(d[(5, 100)] / 12, 11)


class AvisoTravao(unittest.TestCase):
    def test_textos(self):
        t = run.alert_text({"event": "HALT", "id": "h", "reason": "perda diária de -3.0R atingiu o limite",
                            "until": NOW + 86400, "loss": [-3.0, -3.4]}, {}, "")
        self.assertIn("TRAVÃO DE PERDAS ATIVO", t)
        self.assertIn("-3.40R em 7 dias", t)
        self.assertIn("DESLIGADO", run.alert_text({"event": "HALT_OFF", "id": "x"}, {}, ""))


class EstudoDosStops(unittest.TestCase):
    def test_variantes_do_stop(self):
        from unittest import mock
        from tools import arena_ringue as AR
        from engine import arena, promo
        bars = c4(60)
        base = {"stop": 95.0, "tp": [104.0], "partials": [100], "breakeven": True, "hold_s": 1,
                "atr": 2.0, "gatilho": "RSI"}
        with mock.patch.object(AR, "sig_x30", return_value=dict(base)):
            pav = AR._stop_var(AR.sig_x30, "pavio")(bars)
            liq = AR._stop_var(AR.sig_x30, "liq")(bars)
        self.assertEqual(pav["stop"], 94.0)
        self.assertEqual(pav["tp"], [104.0])                                  # mesmos objetivos
        self.assertAlmostEqual(liq["stop"], min(95.0, 99.0 - 0.4))
        bars[-5]["l"] = 80.0                                                   # liquidez longe demais
        with mock.patch.object(AR, "sig_x30", return_value=dict(base)):
            self.assertIsNone(AR._stop_var(AR.sig_x30, "liq")(bars))
        for k in ("BOUNCE_X30_PAVIO", "BOUNCE_X30_LIQ"):
            self.assertIn(k, AR.NEW_SIGS)
            self.assertIn(k, promo.REAL_OK)                                    # real so depois de qualificar
            self.assertEqual(promo.family(k), "sobrevenda")
            self.assertNotIn(arena.persona(k), ("", None))


class ObjetivoSemAnexo(unittest.TestCase):
    def test_programa_vende_no_objetivo_final(self):
        from engine import execucao
        st = {"auto_ops": {"ENA-X-1": "aberta"}}
        execucao.hooks(st, [{"event": "TP1", "id": "ENA-X-1", "sold_pct": 50}], NOW)   # parcial: stop a entrada
        self.assertEqual([r["acao"] for r in st["exec_req"]], ["breakeven"])
        st["exec_req"] = []
        execucao.hooks(st, [{"event": "TP1", "id": "ENA-X-1", "r": 2.1, "price": 0.2474}], NOW)
        self.assertEqual([(r["acao"], r["op"]) for r in st["exec_req"]], [("fechar", "ENA-X-1")])


class Reuniao(unittest.TestCase):
    def test_dialogo_vem_dos_relatorios(self):
        d = deps(**{"Derivados": "verde", "Suportes e resistências": "vermelho", "Sobrevenda": "vermelho",
                    "Liquidez e smart money": "vermelho"})
        v = diretor.review(row(d), dec(), c4(), None, None, NOW)
        L = v["dialogo"]
        self.assertTrue(L[0]["texto"].startswith("Proponho comprar SOL"))
        self.assertEqual(L[1]["de"], "Diretor")
        self.assertIn({"de": "Derivados", "tom": "favor", "texto": "A favor: leitura de Derivados"}, L)
        self.assertEqual(L[-1]["tom"], "rejeita")
        self.assertNotIn("Macroeconomia", [m["de"] for m in L])          # neutro nao fala


class StopNaEntradaNaBybit(unittest.TestCase):
    def test_tp1_pede_breakeven(self):
        from engine import execucao
        st = {"auto_ops": {"ENA-X-1": "aberta"}}
        execucao.hooks(st, [{"event": "TP1", "id": "ENA-X-1", "sold_pct": 0, "price": 0.2061}], NOW)
        self.assertEqual([r["acao"] for r in st["exec_req"]], ["breakeven"])

    def test_breakeven_cancela_e_cria_stop_novo(self):
        from unittest import mock
        from engine import executor as X
        op = {"status": "aberta", "symbol": "ENAUSDC", "asset": "ENA", "entrada": 0.2, "qty": 30.3,
              "partes": [{"stopId": "s1", "filho": "s1", "qty": 30.3}]}
        ex, sent, calls = {"ops": {"op1": op}}, [], []
        inst = {"tick": 0.0001, "base_step": 0.1}

        def post(path, body):
            calls.append((path, body))
            if path == "/v5/order/amend":
                raise X.ExecError("170312 not supported")
            return {"orderId": "novo"}
        with mock.patch.object(X, "instrument", return_value=inst), \
                mock.patch.object(X, "tpsl_orders", return_value=[{"orderId": "s1", "triggerPrice": "0.1816",
                                                                     "qty": "30.3"}]), \
                mock.patch.object(X, "post", side_effect=post), mock.patch.object(X, "wallet", return_value={}), \
                mock.patch.object(X, "held", return_value=30.29), mock.patch.object(X.time, "sleep"):
            self.assertEqual(X.do_breakeven({}, {"op": "op1"}, ex, NOW, sent.append), "ok")
        paths = [c[0] for c in calls]
        self.assertEqual(paths, ["/v5/order/amend", "/v5/order/cancel", "/v5/order/create"])
        self.assertEqual(calls[-1][1]["triggerPrice"], "0.2002")
        self.assertEqual(calls[-1][1]["qty"], "30.2")                       # o que ha na conta
        self.assertEqual(op["partes"][0]["stopId"], "novo")
        self.assertIn("subiu para a entrada", sent[0])


class ReversaoNoIntervalo(unittest.TestCase):
    @staticmethod
    def intervalo(seed=1, n=130):
        import random
        r, out, p = random.Random(seed), [], 100.0
        t0 = NOW - (NOW % H4) - n * H4
        for i in range(n):
            o = p
            c = min(106, max(94, p + r.uniform(-1.6, 1.6) + (100 - p) * 0.15))
            p = c
            out.append({"t": t0 + i * H4, "o": o, "h": max(o, c) + r.uniform(0.1, 0.8),
                        "l": min(o, c) - r.uniform(0.1, 0.8), "c": c, "v": 1, "tb": 0.5})
        lo = min(x["l"] for x in out[-60:])
        out[-3].update(o=out[-4]["c"], c=lo + 0.4, h=out[-4]["c"] + 0.2, l=lo - 0.8)
        out[-2].update(o=lo + 0.4, c=lo + 0.3, h=lo + 0.8, l=lo - 0.2)
        out[-1].update(o=lo + 0.3, c=lo + 1.6, h=lo + 1.8, l=lo + 0.2)
        return out

    def test_compra_no_fundo_do_intervalo(self):
        from tools import arena_ringue as AR
        from engine import arena, promo
        c = self.intervalo()
        s = AR.sig_intervalo(c)
        self.assertIsNotNone(s)
        self.assertLess(s["stop"], min(x["l"] for x in c[-60:]))          # stop abaixo do intervalo
        self.assertGreater(s["tp"][0], c[-1]["c"])
        self.assertIn("lateral", s["gatilho"])
        self.assertIn("REVERSAO_INTERVALO", AR.NEW_SIGS)
        self.assertIn("REVERSAO_INTERVALO", promo.REAL_OK)
        self.assertEqual(arena.persona("REVERSAO_INTERVALO"), "Inês")

    def test_nao_compra_em_tendencia(self):
        from tools import arena_ringue as AR
        c = [{"t": NOW - (200 - i) * H4, "o": 100 + i, "h": 101.5 + i, "l": 99.5 + i, "c": 101 + i,
              "v": 1, "tb": 0.5} for i in range(200)]
        self.assertIsNone(AR.sig_intervalo(c))


class DiretrizDoObjetivo(unittest.TestCase):
    def test_sem_lucro_perde_o_lugar(self):
        from engine import promo, meta
        led = [{"strategy": "BOUNCE_X30", "status": "CLOSED", "result_r": r, "mode": "REAL",
                "executed": True, "risk_usdc": 1.0} for r in [1.0, -1, -1, 0.5, -1, 1.2, -1, 0.4, -1, 0.5]]
        st = {"ledger": led, "arena": {"forma": {"lutadores": {"BOUNCE_X30": {"avg_r": 0.39}}}}}
        self.assertIn("não é lucrativo", promo.suspended(st)["BOUNCE_X30"])        # media -0.04 em 10
        st["ledger"] = led[:9]
        self.assertEqual(promo.suspended(st), {})                                    # 9: ainda cedo
        led[-1]["result_r"] = 1.0
        led[1]["result_r"] = led[2]["result_r"] = 1.5
        st["ledger"] = led
        self.assertEqual(promo.suspended(st), {})                                    # lucrativo: fica
        c = promo.contribution(st)["BOUNCE_X30"]
        self.assertEqual((c["n"], c["usdc"]), (10, 4.1))
        d = meta.diretrizes(meta.progress(None, 79.4))
        self.assertIn("100 USDC", d[0])
        self.assertTrue(any("lucrativo" in x for x in d))


class VendaADescoberto(unittest.TestCase):
    def setUp(self):
        from engine import executor as X
        self.X = X
        self.inst = {"tick": "0.01", "base_step": "0.001", "min_amt": 5.0, "quote_step": "0.01"}
        self.calls = []
        self.debt = {"v": 0.0}

    def post(self, path, body):
        self.calls.append((path, dict(body)))
        if path == "/v5/order/create" and body.get("side") == "Sell":
            self.debt["v"] += float(body["qty"])
        if path == "/v5/order/create" and body.get("side") == "Buy" and "triggerPrice" not in body:
            self.debt["v"] = 0.0
        return {"orderId": f"o{len(self.calls)}"}

    def patches(self, **kw):
        from unittest import mock
        X = self.X
        ps = [mock.patch.object(X, "instrument", return_value=self.inst),
              mock.patch.object(X, "post", side_effect=self.post),
              mock.patch.object(X, "wallet", return_value={}),
              mock.patch.object(X, "usdc_free", return_value=70.0),
              mock.patch.object(X, "coin_debt", side_effect=lambda w, c: self.debt["v"]),
              mock.patch.object(X, "held", return_value=0.0),
              mock.patch.object(X, "tpsl_orders", return_value=[]),
              mock.patch.object(X, "fills", side_effect=lambda oid, sym, b, side="Buy": (100.0, 0.06)),
              mock.patch.object(X, "get", return_value={"spotLeverage": "2"}),
              mock.patch.object(X.time, "sleep")]
        for k, v in kw.items():
            ps.append(mock.patch.object(X, k, return_value=v))
        return ps

    def run_with(self, fn, *a, **kw):
        ps = self.patches(**kw)
        for p in ps:
            p.start()
        try:
            return fn(*a)
        finally:
            for p in ps:
                p.stop()

    def test_vende_recompra_e_devolve(self):
        X, sent = self.X, []
        snd = lambda t, html=False: sent.append(t)
        sig = {"status": "ACTIVE", "mode": "REAL", "plan": {"entry_zone": [99.5, 100.5], "stop": 106.0,
               "tp": [94.0, 90.0, 90.0], "partials": [0, 100, 0], "position_usdc": 6.0}}
        st = {"signals": {"op1": sig}, "ledger": [{"id": "op1", "asset": "SOL", "pair": "SOL/USDC",
                                                   "side": "SHORT", "issued_at": NOW}]}
        ex = {"ops": {}}
        res = self.run_with(X.do_short, st, {"op": "op1"}, ex, NOW, snd, last_price=100.0)
        self.assertEqual(res, "ok")
        sell = [b for p, b in self.calls if b.get("side") == "Sell"][0]
        self.assertEqual((sell["isLeverage"], sell["stopLoss"], sell["takeProfit"]), (1, "106.00", "90.00"))
        op = ex["ops"]["op1"]
        self.assertEqual(op["lado"], "SHORT")
        self.assertIn("venda a descoberto", sent[0])
        self.calls.clear()
        self.run_with(X.do_close, st, {"op": "op1"}, ex, NOW + 60, snd)
        buy = [b for p, b in self.calls if b.get("side") == "Buy"][0]
        self.assertEqual((buy["isLeverage"], buy["marketUnit"]), (1, "baseCoin"))
        self.assertEqual(ex["ops"]["op1"]["status"], "fechada")
        self.assertIn("Recomprei", sent[-1])

    def test_recusa_fora_da_zona_e_botao_so_com_teste(self):
        from engine import execucao, run
        X = self.X
        sig = {"status": "ACTIVE", "mode": "REAL", "plan": {"entry_zone": [99.5, 100.5], "stop": 106.0,
               "tp": [94.0]}}
        st = {"signals": {"op1": sig}, "ledger": [{"id": "op1", "issued_at": NOW}]}
        self.assertIn("saiu da zona", X.short_check(st, "op1", 97.0, NOW)[1])
        self.assertIn("colado ao stop", X.short_check(st, "op1", 105.9, NOW)[1])
        self.assertIsNone(X.short_check(st, "op1", 100.0, NOW)[1])
        s0 = {}
        execucao.apply(s0, {"pronto": True, "teste": {"passos": ["compra ok", "venda ok"]}})
        self.assertTrue(execucao.READY)
        self.assertFalse(execucao.READY_SHORT)
        e = {"event": "ISSUED", "id": "op1", "asset": "SOL"}
        self.assertNotIn("e|", str(run.markup_for(e, {"direction": "SHORT", "plan": {}}, True)))
        bad = ["venda a descoberto 0.00007 BTC a 1 (anexo: sim)", "recompra ok", "dívida 0"]
        execucao.apply(s0, {"pronto": True, "teste": {"passos": ["compra ok", "venda ok"]},
                            "teste_short": {"passos": bad}})
        self.assertFalse(execucao.READY_SHORT)                    # protecao nao cancelada
        execucao.apply(s0, {"pronto": True, "teste": {"passos": ["compra ok", "venda ok"]},
                            "teste_short": {"passos": bad[:1] + ["cancelar proteção (Bidirectional): ok"] + bad[1:]}})
        self.assertTrue(execucao.READY_SHORT)
        self.assertIn("e|", str(run.markup_for(e, {"direction": "SHORT", "plan": {}}, True)))
        execucao.READY = execucao.READY_SHORT = False


class CodigoDeConduta(unittest.TestCase):
    def test_codigo_e_principio_na_rejeicao(self):
        from engine import meta
        self.assertEqual(len(meta.codigo()), 8)
        v = diretor.review(row(), dec(), c4(), {"estado": "medo"}, None, NOW)
        self.assertIn("Princípio: 1. Primeiro proteger", v["dialogo"][-1]["texto"])
        self.assertEqual(diretor.principle(["histórico contra: x"]), "3. Só entrar com vantagem provada")
        self.assertIn("Código de conduta", consultas.answer("/codigo", {}, {}))


class ModoAutomatico(unittest.TestCase):
    def prova(self, n=20, falha=False, r=0.8, travao=True, be=True):
        ops = {f"A{i}-X-{i}": {"status": "fechada", "entrada": 1.0, "partes": [{}],
                               **({"erro": "x"} if falha and i == 0 else {})} for i in range(n)}
        st = {"ledger": [{"id": k, "auto_exec": True, "status": "CLOSED", "result_r": r} for k in ops]}
        from engine import auto
        auto.observe(st, {"ops": ops, "log": [{"acao": "breakeven", "res": "ok"}] if be else []},
                     [{"event": "HALT"}] if travao else [])
        return st

    def test_so_liga_com_a_prova_e_o_ok(self):
        from engine import auto
        st = self.prova(n=12)
        self.assertFalse(auto.ready(st))
        self.assertIn("Falta", auto.turn(st, True, NOW))
        self.assertFalse(auto.active(st))
        for kw in ({"falha": True}, {"r": -0.2}, {"travao": False}, {"be": False}):
            self.assertFalse(auto.ready(self.prova(**kw)), kw)
        st = self.prova()
        self.assertTrue(auto.ready(st))
        self.assertFalse(auto.active(st))                           # falta o OK do Rui
        self.assertIn("LIGADO", auto.turn(st, True, NOW))
        self.assertTrue(auto.active(st))
        auto.turn(st, False, NOW)
        self.assertFalse(auto.active(st))

    def test_escolhe_so_compras_autorizadas_e_ate_2_por_dia(self):
        from engine import auto, execucao
        st = self.prova()
        auto.turn(st, True, NOW)
        execucao.READY, execucao.READY_SHORT = True, True
        try:
            def sig(i, **kw):
                s = {"mode": "REAL", "score_label": "campeão da arena", "direction": "LONG",
                     "diretor": {"decisao": "AUTORIZADO"}, "plan": {}}
                s.update(kw)
                return {"event": "ISSUED", "id": f"S{i}", "signal": s}
            ev = [sig(0, diretor={"decisao": "REJEITADO"}), sig(1, direction="SHORT"),
                  sig(2, score_label="outro"), sig(3), sig(4), sig(5)]
            self.assertEqual(auto.pick(st, ev, NOW), ["S3", "S4"])
            self.assertTrue(ev[3]["auto"])
            self.assertEqual(auto.pick(st, [sig(6)], NOW + 60), [])            # limite do dia
            self.assertEqual(auto.pick(st, [sig(7)], NOW + 86400 + 60), ["S7"])
        finally:
            execucao.READY = execucao.READY_SHORT = False

    def test_telegram(self):
        from engine import inbox
        st = {"ledger": []}
        out = inbox.apply(st, [{"update_id": 1, "message": {"chat": {"id": 7}, "text": "/auto", "date": NOW}}], "7")
        self.assertIn("Modo automático", out[0][0])
        out = inbox.apply(st, [{"update_id": 2, "message": {"chat": {"id": 7}, "text": "/auto ligar", "date": NOW}}], "7")
        self.assertIn("Ainda não posso", out[0][0])


class EntradaNaoEPerda(unittest.TestCase):
    def test_breakeven_nao_conta_para_o_travao(self):
        from engine import signals, scanner
        cfg = {"max_daily_loss_r": 3.0, "max_weekly_loss_r": 6.0, "cooldown_after_losses": 3}
        mk = lambda i, r: {"id": f"s{i}", "status": "CLOSED", "mode": "REAL", "closed_at": NOW - 7200 + i, "result_r": r}
        sigs = {f"s{i}": mk(i, r) for i, r in enumerate([-1.0, -1.0, -0.05])}
        self.assertIsNone(signals.trading_halt(sigs, cfg, NOW))
        sigs["s3"] = mk(3, -0.9)
        self.assertIn("perdas seguidas", signals.trading_halt(sigs, cfg, NOW))
        led = [{"executed": True, "status": "CLOSED", "result_r": r, "closed_at": i}
               for i, r in enumerate([0.8, -1.0, -0.05])]
        self.assertEqual(scanner.losing_streak(led), 1)

    def test_sem_divisao_vende_tudo_no_tp1(self):
        from engine import promo, config
        cfg = dict(config.DEFAULTS, capital_usdc=80, fixed_position_usdc=6, max_risk_usdc=1.0,
                   swing_leverage=1.0, min_order_usdc=5.0)
        sig = {"stop": 90.0, "tp": [104.0, 120.0], "partials": [50, 50], "breakeven": True, "hold_s": 1}
        p, why = promo.plan_for(sig, 100.0, cfg)
        self.assertIsNotNone(p, why)
        self.assertEqual(p["partials"][0], 100)
        self.assertEqual(p["tp"][0], 104.0)
