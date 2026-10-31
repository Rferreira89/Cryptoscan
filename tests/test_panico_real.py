"""(30/10) Compra no panico com dinheiro real: so com autorizacao; pedidos, execucao, saida por tempo, avisos."""
import unittest
from unittest import mock

from engine import auto, execucao, papel_panico as P, promo

H4 = P.H4
T_SIG = 1793304000
NOW = T_SIG + H4 + 600            # dentro da validade (ate T_SIG + 3 velas)
PEND = {"t_sig": T_SIG, "lim": 0.0924, "atr": 0.0024, "funding": -1e-4, "queda_3d_pct": -11.7}
CFG = {"max_risk_usdc": 5.0, "capital_usdc": 1000, "risk_pct_of_capital": 0.5, "max_open_positions": 4,
       "quote": "USDC", "real_autorizados": ["PANICO_L10"], "modo_acelerado": {"ligado": True}}


def estado(**kw):
    st = {"papel_panico": {"pend": {"ALGO": dict(PEND)}, "abertas": {}, "fechadas": []},
          "auto": {"ligado": True, "forcado": True}}
    st.update(kw)
    return st


class Gatilho(unittest.TestCase):
    def setUp(self):
        self.ant = (promo.AUTORIZADOS, execucao.READY)
        promo.AUTORIZADOS, execucao.READY = {"PANICO_L10"}, True

    def tearDown(self):
        promo.AUTORIZADOS, execucao.READY = self.ant

    def test_sem_autorizacao_nao_pede(self):
        promo.AUTORIZADOS = set()
        st = estado()
        self.assertEqual(P.real(st, {"ALGO": 0.0920}, CFG, NOW), [])
        self.assertFalse(st.get("exec_req"))

    def test_lista_antiga_none_tambem_nao_pede(self):
        promo.AUTORIZADOS = None
        self.assertEqual(P.real(estado(), {"ALGO": 0.0920}, CFG, NOW), [])

    def test_execucao_ou_auto_desligados_nao_pedem(self):
        execucao.READY = False
        self.assertEqual(P.real(estado(), {"ALGO": 0.0920}, CFG, NOW), [])
        execucao.READY = True
        self.assertEqual(P.real(estado(auto={"ligado": False}), {"ALGO": 0.0920}, CFG, NOW), [])
        self.assertEqual(P.real(estado(halt={"t": NOW}), {"ALGO": 0.0920}, CFG, NOW), [])

    def test_preco_acima_do_limite_espera(self):
        st = estado()
        self.assertEqual(P.real(st, {"ALGO": 0.0930}, CFG, NOW), [])
        self.assertEqual(P.real(st, {}, CFG, NOW), [])

    def test_limite_tocado_pede_compra_com_plano(self):
        st = estado()
        out = P.real(st, {"ALGO": 0.0921}, CFG, NOW)
        oid = f"PANICO-ALGO-{T_SIG}"
        self.assertEqual(out, [("panico_comprar", oid)])
        p = st["papel_panico"]["real"][oid]
        self.assertEqual(p["risco_usdc"], 5.0)
        self.assertEqual(p["valido_ate"], T_SIG + 3 * H4)
        self.assertEqual(p["sair_em"], NOW // H4 * H4 + 18 * H4)
        self.assertEqual(st["exec_req"][0]["acao"], "panico_comprar")
        self.assertEqual(P.real(st, {"ALGO": 0.0921}, CFG, NOW + 60), [])          # nunca pede duas vezes

    def test_papel_aberto_nao_bloqueia_sinal_real(self):
        st = estado()
        st["papel_panico"]["pend"] = {}
        st["papel_panico"]["pend_real"] = {"ALGO": dict(PEND)}
        out = P.real(st, {"ALGO": 0.0921}, CFG, NOW)
        self.assertEqual(out, [("panico_comprar", f"PANICO-ALGO-{T_SIG}")])

    def test_expirado_nao_pede(self):
        self.assertEqual(P.real(estado(), {"ALGO": 0.0921}, CFG, T_SIG + 3 * H4 + 1), [])

    def test_limite_de_abertas(self):
        st = estado(auto_ops={"a": "aberta", "b": "aberta", "c": "aberta", "d": "aberta"})
        self.assertEqual(P.real(st, {"ALGO": 0.0921}, CFG, NOW), [])
        st = estado()
        st["papel_panico"]["pend"]["ENA"] = dict(PEND, lim=0.1737)
        st["papel_panico"]["pend"]["PYTH"] = dict(PEND, lim=0.0624)
        out = P.real(st, {"ALGO": 0.0921, "ENA": 0.17, "PYTH": 0.06}, CFG, NOW)
        self.assertEqual(len(out), P.MAX_REAIS)

    def test_recusada_tenta_outra_vez_mais_tarde(self):
        st = estado()
        P.real(st, {"ALGO": 0.0921}, CFG, NOW)
        oid = f"PANICO-ALGO-{T_SIG}"
        st["exec_req"] = []
        st["auto_ops"] = {oid: "recusada"}
        self.assertEqual(P.real(st, {"ALGO": 0.0921}, CFG, NOW + 60), [])           # cedo demais
        self.assertEqual(P.real(st, {"ALGO": 0.0921}, CFG, NOW + P.REPETIR_S + 1), [("panico_comprar", oid)])
        self.assertEqual(st["papel_panico"]["real"][oid]["tentativas"], 2)

    def test_saida_por_tempo(self):
        st = estado()
        P.real(st, {"ALGO": 0.0921}, CFG, NOW)
        oid = f"PANICO-ALGO-{T_SIG}"
        st["exec_req"], st["auto_ops"] = [], {oid: "aberta"}
        sair = st["papel_panico"]["real"][oid]["sair_em"]
        self.assertEqual(P.real(st, {"ALGO": 0.095}, CFG, sair - 10), [])
        self.assertEqual(P.real(st, {"ALGO": 0.095}, CFG, sair), [("fechar", oid)])
        self.assertEqual(P.real(st, {"ALGO": 0.095}, CFG, sair + 60), [])

    def test_saida_por_tempo_mesmo_desautorizada(self):
        st = estado()
        P.real(st, {"ALGO": 0.0921}, CFG, NOW)
        oid = f"PANICO-ALGO-{T_SIG}"
        st["exec_req"], st["auto_ops"] = [], {oid: "aberta"}
        promo.AUTORIZADOS = set()                                                   # o Rui tirou a autorizacao
        sair = st["papel_panico"]["real"][oid]["sair_em"]
        self.assertEqual(P.real(st, {}, CFG, sair), [("fechar", oid)])

    def test_acelerado_entra_no_risco(self):
        st = estado(papel_panico={"pend": {"ALGO": dict(PEND)}, "abertas": {},
                                  "fechadas": [{"r": r} for r in [2.0] * 40 + [-1.0] * 50]})
        P.real(st, {"ALGO": 0.0921}, CFG, NOW)
        p = st["papel_panico"]["real"][f"PANICO-ALGO-{T_SIG}"]
        self.assertEqual(p["risco_usdc"], 25.0)
        self.assertEqual(p["acelerado_pct"], 2.5)


class Avisos(unittest.TestCase):
    def c4(self, n=60, base=1.0):
        return [{"t": T_SIG - (n - 1 - i) * H4, "o": base, "h": base * 1.01, "l": base * 0.99, "c": base}
                for i in range(n)]

    def test_papel_avisa_entrada_e_fecho(self):
        st = {"papel_panico": {"pend": {"ALGO": {"t_sig": T_SIG, "lim": 0.995, "atr": 0.01, "funding": -1e-4,
                                                 "queda_3d_pct": -12}}, "abertas": {}, "fechadas": []}}
        c4 = self.c4() + [{"t": T_SIG + H4, "o": 1.0, "h": 1.0, "l": 0.99, "c": 0.995}]
        P.update(st, {"ALGO": c4}, {}, NOW)
        m = P.pop_avisos(st)
        self.assertEqual(len(m), 1)
        self.assertIn("executada em ALGO", m[0])
        self.assertEqual(P.pop_avisos(st), [])
        c4.append({"t": T_SIG + 2 * H4, "o": 1.0, "h": 1.05, "l": 0.99, "c": 1.04})    # objetivo 2R
        P.update(st, {"ALGO": c4}, {}, NOW + H4)
        m = P.pop_avisos(st)
        self.assertIn("fechada (objetivo)", m[0])
        self.assertIn("1 operações", m[0])


class Executor(unittest.TestCase):
    def setUp(self):
        from engine import executor as X
        self.X, self.calls, self.sent = X, [], []

    def post(self, path, body):
        self.calls.append((path, dict(body)))
        return {"orderId": f"o{len(self.calls)}"}

    def correr(self, st, ex, now=NOW, last=0.0921, autorizados=("PANICO_L10",), free=200.0,
               fills=(0.0921, 500.0), attach_falha=False, venda_falha=False):
        X = self.X

        def post(path, body):
            if attach_falha and body.get("stopLoss"):
                raise X.ExecError("TP/SL não suportado")
            if attach_falha and body.get("triggerPrice"):
                raise X.ExecError("stop recusado")
            if venda_falha and body.get("side") == "Sell":
                raise X.ExecError("venda recusada")
            return self.post(path, body)
        ps = [mock.patch.object(X, "instrument", return_value={"tick": "0.0001", "base_step": "0.1", "min_amt": 5.0}),
              mock.patch.object(X, "post", side_effect=post),
              mock.patch.object(X, "wallet", return_value={}),
              mock.patch.object(X, "usdc_free", return_value=free),
              mock.patch.object(X, "usdc_debt", return_value=0.0),
              mock.patch.object(X, "last_price", return_value=last),
              mock.patch.object(X, "fills_or_state", return_value=fills),
              mock.patch.object(X, "_match_children"),
              mock.patch.object(X, "get", return_value={"spotLeverage": "1"}),
              mock.patch.object(X.time, "sleep"),
              mock.patch("engine.config.load", return_value={"real_autorizados": list(autorizados)})]
        for p in ps:
            p.start()
        try:
            return X.do_panico_comprar(st, {"op": f"PANICO-ALGO-{T_SIG}"}, ex, now,
                                       lambda t, html=False: self.sent.append(t))
        finally:
            for p in ps:
                p.stop()

    def plano(self, **kw):
        p = {"asset": "ALGO", "symbol": "ALGOUSDC", "lim": 0.0924, "atr": 0.0024, "risco_usdc": 5.0,
             "t_sig": T_SIG, "valido_ate": T_SIG + 3 * H4, "sair_em": T_SIG + 20 * H4}
        p.update(kw)
        return {"papel_panico": {"real": {f"PANICO-ALGO-{T_SIG}": p}}}

    def test_compra_com_stop_e_objetivo_anexados(self):
        ex = {"ops": {}}
        self.assertEqual(self.correr(self.plano(), ex), "ok")
        compra = [b for p, b in self.calls if b.get("side") == "Buy"][0]
        self.assertEqual(compra["timeInForce"], "IOC")
        self.assertLessEqual(float(compra["price"]), 0.0924 * 1.0031)
        self.assertEqual(compra["stopLoss"], "0.0873")                   # 0.0921 - 2 x 0.0024
        self.assertEqual(compra["takeProfit"], "0.1017")                 # +2R
        usdc = float(compra["qty"]) * float(compra["price"])
        self.assertAlmostEqual(usdc * (0.0048 / 0.0921 + 0.0035), 5.0, delta=0.1)   # perde ~5 USDC no stop
        op = ex["ops"][f"PANICO-ALGO-{T_SIG}"]
        self.assertEqual((op["status"], op["estrategia"]), ("aberta", "PANICO_L10"))
        self.assertIn("Compra no pânico executada", self.sent[-1])

    def test_nao_autorizada_nao_compra(self):
        ex = {"ops": {}}
        self.correr(self.plano(), ex, autorizados=())
        self.assertFalse(self.calls)
        self.assertEqual(ex["ops"][f"PANICO-ALGO-{T_SIG}"]["status"], "recusada")

    def test_preco_fugiu_ou_expirou(self):
        ex = {"ops": {}}
        self.correr(self.plano(), ex, last=0.0935)
        self.assertFalse(self.calls)
        ex = {"ops": {}}
        self.correr(self.plano(), ex, now=T_SIG + 3 * H4 + 5)
        self.assertFalse(self.calls)

    def test_ioc_sem_execucao_fica_recusada(self):
        ex = {"ops": {}}
        self.correr(self.plano(), ex, fills=(None, 0.0))
        self.assertEqual(ex["ops"][f"PANICO-ALGO-{T_SIG}"]["status"], "recusada")

    def test_sem_stop_vende_logo(self):
        ex = {"ops": {}}
        res = self.correr(self.plano(), ex, attach_falha=True)
        self.assertEqual(res, "sem stop: vendida")
        self.assertEqual(ex["ops"][f"PANICO-ALGO-{T_SIG}"]["status"], "fechada")
        self.assertTrue(any(b.get("side") == "Sell" and not b.get("triggerPrice") for p, b in self.calls))

    def test_sem_stop_e_sem_venda_da_alarme(self):
        ex = {"ops": {}}
        self.correr(self.plano(), ex, attach_falha=True, venda_falha=True)
        self.assertIn("SEM STOP", self.sent[-1])
        self.assertEqual(ex["ops"][f"PANICO-ALGO-{T_SIG}"]["status"], "aberta")

    def test_usdc_curto_usa_margem_ate_10x(self):
        ex = {"ops": {}}
        self.correr(self.plano(risco_usdc=25.0), ex, free=30.0)
        alav = [b for p, b in self.calls if p == "/v5/spot-margin-trade/set-leverage"]
        self.assertTrue(alav)
        self.assertLessEqual(int(alav[0]["leverage"]), 10)
        compra = [b for p, b in self.calls if b.get("side") == "Buy"][0]
        self.assertEqual(compra.get("isLeverage"), 1)

    def test_alavancagem_nunca_poe_a_liquidacao_antes_do_stop(self):
        from engine.risk import leverage_for
        ex = {"ops": {}}
        self.correr(self.plano(risco_usdc=500.0, atr=0.0046), ex, free=30.0)    # stop a ~10%
        teto = leverage_for(0.0092 / 0.0921, {"swing_leverage": 10.0})["max_safe"]
        self.assertLess(teto, 10)
        alav = [b for p, b in self.calls if p == "/v5/spot-margin-trade/set-leverage"]
        self.assertTrue(all(int(b["leverage"]) <= teto for b in alav))
        compra = [b for p, b in self.calls if b.get("side") == "Buy"][0]
        usdc = float(compra["qty"]) * float(compra["price"])
        self.assertLessEqual(usdc, 30.0 * 0.98 * teto * 1.004)

    def test_stop_curto_chega_a_10x(self):
        ex = {"ops": {}}
        self.correr(self.plano(risco_usdc=50.0, atr=0.0005), ex, free=10.0)     # stop a ~1%
        alav = [b for p, b in self.calls if p == "/v5/spot-margin-trade/set-leverage"]
        self.assertEqual(alav[0]["leverage"], "10")

    def test_nunca_duas_vezes(self):
        ex = {"ops": {f"PANICO-ALGO-{T_SIG}": {"status": "aberta"}}}
        self.assertEqual(self.correr(self.plano(), ex), "já executada antes")
        self.assertFalse(self.calls)

    def test_estado_publico_nao_executa(self):
        import json
        import os
        import tempfile
        X = self.X
        d = tempfile.mkdtemp()
        sp, ep, op = (os.path.join(d, n) for n in ("s.json", "e.json", "o.json"))
        st = self.plano()
        st["_publico"] = True
        st["exec_req"] = [{"id": "x", "acao": "panico_comprar", "op": f"PANICO-ALGO-{T_SIG}", "t": NOW}]
        with open(sp, "w") as f:
            json.dump(st, f)
        with mock.patch.object(X, "configured", return_value=False), mock.patch.object(X, "post") as pst, \
                mock.patch("engine.alerts.send"):
            try:
                X.main(sp, ep, op)
            except SystemExit:
                pass
            pst.assert_not_called()


class ValorTodo(unittest.TestCase):
    """(31/10, Rui) 20$ com o valor todo: uma operacao de cada vez, posicao = saldo livre ate 20, sem alavancagem."""
    CFGT = dict(CFG, panico_real={"modo": "tudo", "max_usdc": 20})

    def setUp(self):
        self.ant = (promo.AUTORIZADOS, execucao.READY)
        promo.AUTORIZADOS, execucao.READY = {"PANICO_L10"}, True

    def tearDown(self):
        promo.AUTORIZADOS, execucao.READY = self.ant

    def test_uma_de_cada_vez_com_teto(self):
        st = estado()
        st["papel_panico"]["pend"]["ENA"] = dict(PEND, lim=0.1737)
        out = P.real(st, {"ALGO": 0.0921, "ENA": 0.17}, self.CFGT, NOW)
        self.assertEqual(len(out), 1)
        p = next(iter(st["papel_panico"]["real"].values()))
        self.assertEqual(p["tudo_usdc"], 20.0)
        self.assertIsNone(p["risco_usdc"])

    def test_acelerado_nao_mexe(self):
        from engine import acelerado
        st = {"papel_panico": {"fechadas": [{"r": r} for r in [2.0] * 40 + [-1.0] * 50]}}
        self.assertIsNone(acelerado.risco_pct("PANICO_L10", st, self.CFGT)[0])

    def test_executor_compra_o_saldo_sem_alavancagem(self):
        t = Executor("test_compra_com_stop_e_objetivo_anexados")
        t.setUp()
        ex = {"ops": {}}
        st = t.plano(risco_usdc=None, tudo_usdc=20.0)
        self.assertEqual(t.correr(st, ex, free=20.4), "ok")
        compra = [b for p, b in t.calls if b.get("side") == "Buy"][0]
        usdc = float(compra["qty"]) * float(compra["price"])
        self.assertAlmostEqual(usdc, 19.99, delta=0.15)                  # 98% de 20,40 = 19,99
        self.assertNotIn("isLeverage", compra)
        self.assertFalse([b for p, b in t.calls if p == "/v5/spot-margin-trade/set-leverage"])
        self.assertIn("valor todo", t.sent[-1])

    def test_executor_com_mais_saldo_fica_no_teto(self):
        t = Executor("test_compra_com_stop_e_objetivo_anexados")
        t.setUp()
        ex = {"ops": {}}
        t.correr(t.plano(risco_usdc=None, tudo_usdc=20.0), ex, free=500.0)
        compra = [b for p, b in t.calls if b.get("side") == "Buy"][0]
        self.assertLessEqual(float(compra["qty"]) * float(compra["price"]), 20.0 * 1.004)


class SinalComPapelAberto(unittest.TestCase):
    def test_update_cria_pend_real_e_expira(self):
        base = 1.0
        c4 = [{"t": T_SIG - (59 - i) * H4, "o": base, "h": base * 1.01, "l": base * 0.99, "c": base} for i in range(60)]
        st = {"papel_panico": {"pend": {}, "abertas": {"ALGO": {"entrada": 1, "stop": 0.5, "alvo": 2, "risco": 0.5,
                                                              "t_sig": T_SIG - 10 * H4, "t_fill": T_SIG - 9 * H4}},
                               "fechadas": []}}
        with mock.patch.object(P, "sinal", return_value=dict(PEND)):
            P.update(st, {"ALGO": c4}, {}, NOW)
        self.assertIn("ALGO", st["papel_panico"]["pend_real"])
        self.assertNotIn("ALGO", st["papel_panico"]["pend"])
        c4b = c4 + [{"t": T_SIG + k * H4, "o": base, "h": base * 1.01, "l": base * 0.99, "c": base} for k in (1, 2)]
        with mock.patch.object(P, "sinal", return_value=None):
            P.update(st, {"ALGO": c4b}, {}, NOW + 2 * H4)
        self.assertNotIn("ALGO", st["papel_panico"]["pend_real"])


class Alavancagem(unittest.TestCase):
    """(31/10, Rui) valor todo com alavancagem entre 5x e 10x, sem a liquidacao chegar antes do stop."""
    def compra(self, atr, free=20.4, falha_margem=False):
        t = Executor("test_compra_com_stop_e_objetivo_anexados")
        t.setUp()
        ex = {"ops": {}}
        X = t.X
        orig = t.post

        def post(path, body):
            if falha_margem and body.get("isLeverage"):
                raise X.ExecError("170131: Insufficient balance (sem margem)")
            return orig(path, body)
        t.post = post
        st = t.plano(risco_usdc=None, tudo_usdc=20.0, alav=[5, 10], atr=atr)
        res = t.correr(st, ex, free=free)
        compra = [b for p, b in t.calls if b.get("side") == "Buy"][-1]
        alav = [b for p, b in t.calls if p == "/v5/spot-margin-trade/set-leverage"]
        return res, ex["ops"][f"PANICO-ALGO-{T_SIG}"], compra, alav, t.sent

    def test_stop_curto_usa_10x(self):
        res, op, compra, alav, sent = self.compra(atr=0.0009)              # stop ~2%
        self.assertEqual(op["alavancagem"], 10)
        self.assertEqual(alav[0]["leverage"], "10")
        self.assertEqual(compra["isLeverage"], 1)
        self.assertAlmostEqual(float(compra["qty"]) * float(compra["price"]), 199.9, delta=2)
        self.assertIn("alavancagem 10x", sent[-1])

    def test_stop_de_5pc_fica_abaixo_de_10x_e_liquidacao_longe(self):
        res, op, compra, alav, sent = self.compra(atr=0.0024)              # stop ~5,2%
        L = op["alavancagem"]
        self.assertTrue(5 <= L < 10)
        frac = 0.0048 / 0.0921 + 0.0035
        self.assertGreaterEqual(1 / L - 0.05, 1.5 * frac - 1e-9)        # liquidacao a >= 1,5x o stop

    def test_stop_largo_baixa_de_5x_e_avisa(self):
        res, op, compra, alav, sent = self.compra(atr=0.0055)              # stop ~12%
        self.assertLess(op["alavancagem"], 5)
        self.assertIn("abaixo de 5x de propósito", sent[-1])

    def test_sem_margem_compra_sem_alavancagem(self):
        res, op, compra, alav, sent = self.compra(atr=0.0009, falha_margem=True)
        self.assertEqual(res, "ok")
        self.assertNotIn("isLeverage", compra)
        self.assertEqual(op["alavancagem"], 1)
        self.assertIn("não deu margem", sent[-1])


class FechoEAnalise(unittest.TestCase):
    def setUp(self):
        self.ant = (promo.AUTORIZADOS, execucao.READY)
        promo.AUTORIZADOS, execucao.READY = {"PANICO_L10"}, True

    def tearDown(self):
        promo.AUTORIZADOS, execucao.READY = self.ant

    def aberta(self):
        st = estado()
        P.real(st, {"ALGO": 0.0921}, CFG, NOW)
        oid = f"PANICO-ALGO-{T_SIG}"
        st["exec_req"], st["auto_ops"] = [], {oid: "aberta"}
        st["papel_panico"]["real"][oid]["exec"] = {"entrada": 0.0921, "stop": 0.0873, "alvo": 0.1017,
                                                   "status": "aberta", "criado": NOW, "alavancagem": 5}
        return st, oid

    def test_stop_da_bybit_pede_fecho_logo(self):
        st, oid = self.aberta()
        self.assertEqual(P.real(st, {"ALGO": 0.0900}, CFG, NOW + 60), [])
        self.assertEqual(P.real(st, {"ALGO": 0.0870}, CFG, NOW + 120), [("fechar", oid)])
        self.assertEqual(st["papel_panico"]["real"][oid]["motivo_fecho"], "stop")

    def test_objetivo_pede_fecho_logo(self):
        st, oid = self.aberta()
        self.assertEqual(P.real(st, {"ALGO": 0.1020}, CFG, NOW + 60), [("fechar", oid)])

    def test_analise_no_fecho_uma_vez(self):
        st, oid = self.aberta()
        P.real(st, {"ALGO": 0.0870}, CFG, NOW + 120)
        st["auto_ops"][oid] = "fechada"
        st["papel_panico"]["real"][oid]["exec"].update(status="fechada", fechado=NOW + 7200)
        st["papel_panico"]["fechadas"] = [{"asset": "ALGO", "t_sig": T_SIG, "r": -1.02, "motivo": "stop"}]
        P.real(st, {"ALGO": 0.0870}, CFG, NOW + 180)
        m = P.pop_avisos(st)
        self.assertEqual(len(m), 1)
        self.assertIn("Análise", m[0])
        self.assertIn("stop", m[0])
        self.assertIn("5x", m[0])
        self.assertIn("-1.00R", m[0])
        self.assertIn("papel na mesma moeda", m[0])
        P.real(st, {"ALGO": 0.0870}, CFG, NOW + 240)
        self.assertEqual(P.pop_avisos(st), [])

    def test_exec_copiado_do_executor(self):
        st, oid = self.aberta()
        st["papel_panico"]["real"][oid].pop("exec")
        execucao.apply(st, {"ops": {oid: {"status": "aberta", "entrada": 0.0921, "stop": 0.0873, "alvo": 0.1017,
                                          "criado": NOW, "alavancagem": 7}}, "pronto": True})
        self.assertEqual(st["papel_panico"]["real"][oid]["exec"]["alavancagem"], 7)


class Registo(unittest.TestCase):
    def test_acao_registada_e_sem_auto_quando_desligado(self):
        from engine import executor as X
        self.assertIn("panico_comprar", X.ACTIONS)
        self.assertFalse(auto.active({"auto": {"ligado": False}}))


if __name__ == "__main__":
    unittest.main()
