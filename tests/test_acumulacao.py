"""(19/11, decisao do Rui) Carteira de acumulacao da Bybit UE: compras com o dinheiro novo no ativo mais abaixo do peso,
vendas so acima da banda, nada investido enquanto ha trading aberto, nada de dinheiro no resumo publico."""
import unittest

from engine import acumulacao as A
from engine import guarda_publica as G

CFG = {"modo": "sombra", "pesos": {"BTC": 0.70, "ETH": 0.15, "SOL": 0.0375, "LINK": 0.0375, "XRP": 0.0375, "AVAX": 0.0375},
       "banda_pp": 5.0, "ordem_min_usdc": 5.0}
TK = {"BTC": [60000, 59990, 60010, 1], "ETH": [3000, 2999, 3001, 1], "SOL": [150, 149.9, 150.1, 1],
      "LINK": [10, 9.99, 10.01, 1], "XRP": [0.5, 0.499, 0.501, 1], "AVAX": [20, 19.99, 20.01, 1]}


def total(p, lado):
    return round(sum(o["valor"] for o in p["ordens"] if o["lado"] == lado), 2)


class Compras(unittest.TestCase):
    def test_deposito_vai_primeiro_para_o_mais_abaixo_do_peso(self):
        p = A.plano(CFG, {}, TK, 100.0)
        self.assertEqual(p["ordens"][0]["ativo"], "BTC")
        self.assertAlmostEqual(total(p, "comprar"), 100.0)
        self.assertEqual(total(p, "vender"), 0)
        self.assertTrue(all(o["valor"] >= 5.0 for o in p["ordens"]))

    def test_deposito_pequeno_compra_so_o_que_mais_falta(self):
        sal = {"BTC": 70 / 60000, "ETH": 15 / 3000, "SOL": 3.75 / 150, "LINK": 0.375, "XRP": 7.5, "AVAX": 3.75 / 20}
        sal["ETH"] = 5 / 3000                               # ETH muito abaixo do peso
        p = A.plano(CFG, sal, TK, 6.0)
        self.assertEqual([(o["ativo"], o["lado"]) for o in p["ordens"]], [("ETH", "comprar")])
        self.assertEqual(p["ordens"][0]["valor"], 6.0)

    def test_abaixo_do_minimo_nao_ha_ordem(self):
        p = A.plano(CFG, {}, TK, 4.0)
        self.assertEqual(p["ordens"], [])


class Vendas(unittest.TestCase):
    def test_so_vende_acima_da_banda(self):
        dentro = {"BTC": 72 / 60000, "ETH": 15 / 3000, "SOL": 3 / 150, "LINK": 0.3, "XRP": 7, "AVAX": 3 / 20}
        self.assertEqual(total(A.plano(CFG, dentro, TK, 0.0), "vender"), 0)
        fora = dict(dentro, SOL=30 / 150)                     # SOL dispara: ~25% da carteira
        p = A.plano(CFG, fora, TK, 0.0)
        vend = [o for o in p["ordens"] if o["lado"] == "vender"]
        self.assertEqual([o["ativo"] for o in vend], ["SOL"])
        self.assertAlmostEqual(total(p, "comprar"), total(p, "vender"), places=1)   # o vendido compra o que falta

    def test_sem_vendas_por_tendencia(self):
        # a carteira equilibrada com o mercado todo a cair 50% nao vende nada (nao sai do mercado)
        sal = {"BTC": 70 / 60010, "ETH": 15 / 3001, "SOL": 3.75 / 150.1, "LINK": 3.75 / 10.01, "XRP": 3.75 / 0.501,
               "AVAX": 3.75 / 20.01}
        tk = {a: [v[0] / 2, v[1] / 2, v[2] / 2, 1] for a, v in TK.items()}
        p = A.plano(CFG, sal, tk, 0.0)
        self.assertEqual(p["ordens"], [])
        self.assertEqual(p["estado"], "equilibrada")


class Seguranca(unittest.TestCase):
    def test_trading_aberto_reserva_o_usdc(self):
        p = A.plano(CFG, {}, TK, 100.0, posicoes_trading_abertas=1)
        self.assertEqual(p["ordens"], [])
        self.assertEqual(p["estado"], "reservado")
        self.assertIn("reservado", p["motivo"])

    def test_moeda_sem_preco_na_bybit_passa_para_o_btc(self):
        tk = {k: v for k, v in TK.items() if k != "AVAX"}
        alvo, fora = A.pesos_efetivos(CFG, tk)
        self.assertEqual(fora, ["AVAX"])
        self.assertAlmostEqual(alvo["BTC"], 0.7375)
        self.assertAlmostEqual(sum(alvo.values()), 1.0)

    def test_desligado(self):
        self.assertEqual(A.plano(dict(CFG, modo="desligado"), {}, TK, 100.0)["ordens"], [])

    def test_resumo_publico_sem_dinheiro(self):
        p = A.plano(CFG, {"BTC": 0.001}, TK, 100.0)
        pub = A.publico(p)
        self.assertEqual(G.verificar(pub), [])
        self.assertNotIn("valor", str(pub))
        self.assertEqual(pub["ordens"]["comprar"], len(p["ordens"]))


class Volta(unittest.TestCase):
    def estado(self, livre=50.0, aberta=False):
        st = {"conta_saldos": {"t": 1, "m": {}}, "bybit_tickers": {"t": 1, "m": TK}, "conta_livre": {"t": 1, "usdc": livre},
              "ledger": []}
        if aberta:
            st["ledger"].append({"mode": "REAL", "executed": True, "status": "OPEN", "asset": "XLM"})
        return st

    def test_sombra_avisa_uma_vez_e_nao_pede_ordens(self):
        st, msgs = self.estado(), []
        cfg = {"bybit_modo": "acumulacao", "acumulacao": CFG}
        A.atualizar(st, cfg, 1000, msgs.append)
        A.atualizar(st, cfg, 1300, msgs.append)                  # mesmo plano, pouco tempo depois: nao repete
        self.assertEqual(len(msgs), 1)
        self.assertIn("SOMBRA", msgs[0])
        self.assertEqual(st.get("exec_req") or [], [])
        A.atualizar(st, cfg, 1000 + A.AVISO_S + 1, msgs.append)
        self.assertEqual(len(msgs), 2)

    def test_em_trading_nao_faz_nada(self):
        st = self.estado()
        self.assertIsNone(A.atualizar(st, {"bybit_modo": "trading", "acumulacao": CFG}, 1, None))
        self.assertNotIn("acumulacao_plano", st)

    def test_xlm_aberta_reserva(self):
        st = self.estado(aberta=True)
        pub = A.atualizar(st, {"bybit_modo": "acumulacao", "acumulacao": CFG}, 1, None)
        self.assertTrue(pub["posicoes_de_trading_por_fechar"])
        self.assertEqual(pub["ordens"], {"comprar": 0, "vender": 0})

    def test_estado_privado_fora_do_publico(self):
        from engine import publico
        st = self.estado()
        A.atualizar(st, {"bybit_modo": "acumulacao", "acumulacao": CFG}, 1, None)
        self.assertNotIn("acumulacao_plano", publico.state(st))


if __name__ == "__main__":
    unittest.main()


class Executor(unittest.TestCase):
    """do_acumular: so no modo real, so spot (nunca isLeverage), nada com trading aberto ou dividas."""

    def correr(self, modo="real", ops=None, divida=0.0):
        from unittest import mock
        from engine import executor as X
        posts, msgs = [], []
        plano = {"modo": modo, "t": 1, "ordens": [{"ativo": "BTC", "lado": "comprar", "valor": 20.0},
                                          {"ativo": "SOL", "lado": "vender", "valor": 6.0}]}
        w = {"list": [{"coin": [{"coin": "USDC", "walletBalance": "50", "borrowAmount": str(divida)},
                                {"coin": "SOL", "walletBalance": "1"}]}]}

        def post(path, body):
            posts.append(body)
            return {"orderId": f"o{len(posts)}"}
        with mock.patch.object(X, "get", lambda p, q=None: w), mock.patch.object(X, "post", post), \
                mock.patch.object(X, "wallet", lambda: w), mock.patch.object(X, "last_price", lambda s: 100.0), \
                mock.patch.object(X, "instrument", lambda s: {"min_amt": 1.0, "tick": "0.01", "base_step": "0.0001"}), \
                mock.patch.object(X, "fills", lambda oid, sym, a, side="Buy": (100.0, 0.2 if side == "Buy" else 0.06)):
            ex = {"ops": ops or {}}
            r = X.do_acumular({"acumulacao_plano": plano}, {"op": "acumulacao-1"}, ex, 1, lambda t, html=False: msgs.append(t))
        return r, posts, ex, msgs

    def test_real_vende_primeiro_e_nunca_usa_margem(self):
        r, posts, ex, msgs = self.correr()
        self.assertEqual(r, "ok")
        self.assertEqual([b["side"] for b in posts], ["Sell", "Buy"])
        self.assertEqual(ex["acumulacao_ult_plano"], 1)
        self.assertTrue(all("isLeverage" not in b for b in posts))
        self.assertEqual([x["lado"] for x in ex["acumulacao_log"]], ["vender", "comprar"])

    def test_mesmo_plano_nao_corre_duas_vezes(self):
        from unittest import mock
        from engine import executor as X
        ex = {"ops": {}, "acumulacao_ult_plano": 100}
        r = X.do_acumular({"acumulacao_plano": {"modo": "real", "t": 100, "ordens": [{"ativo": "BTC", "lado": "comprar", "valor": 9}]}},
                          {"op": "x"}, ex, 1, lambda *a, **k: None)
        self.assertIn("já executado", r)

    def test_sombra_nao_envia_nada(self):
        r, posts, _, _ = self.correr(modo="sombra")
        self.assertEqual(posts, [])
        self.assertIn("não está em modo real", r)

    def test_trading_aberto_bloqueia(self):
        r, posts, _, _ = self.correr(ops={"XLM-SHORT_TURTLE-1": {"status": "aberta", "lado": "SHORT"}})
        self.assertEqual(posts, [])
        self.assertIn("trading abertas", r)

    def test_divida_bloqueia(self):
        r, posts, _, msgs = self.correr(divida=3.0)
        self.assertEqual(posts, [])
        self.assertTrue(msgs and "dívida" in msgs[0])

    def test_pedido_so_no_modo_real_sem_trading_aberto(self):
        cfgr = {"bybit_modo": "acumulacao", "acumulacao": dict(CFG, modo="real")}
        st = {"conta_saldos": {"t": 1, "m": {}}, "bybit_tickers": {"t": 1, "m": TK}, "conta_livre": {"t": 1, "usdc": 50.0},
              "ledger": [], "capital_confirmado": True, "bybit_modo": "acumulacao"}
        A.atualizar(st, cfgr, 100, None)
        self.assertEqual([r["acao"] for r in st["exec_req"]], ["acumular"])
        A.atualizar(st, cfgr, 200, None)                                    # sem nova leitura da conta: nao repete
        self.assertEqual(len(st["exec_req"]), 1)
        st["exec_req"] = []
        st["conta_livre"] = {"t": 500, "usdc": 50.0}                         # nova leitura: pode pedir de novo
        A.atualizar(st, cfgr, 600, None)
        self.assertEqual(len(st["exec_req"]), 1)
        st2 = dict(st, exec_req=[], acumulacao_pedido=None,
                   ledger=[{"mode": "REAL", "executed": True, "status": "OPEN", "asset": "XLM"}])
        A.atualizar(st2, cfgr, 300, None)
        self.assertEqual(st2["exec_req"], [])
        st3 = dict(st, exec_req=[], acumulacao_pedido=None)
        A.atualizar(st3, {"bybit_modo": "acumulacao", "acumulacao": CFG}, 400, None)   # sombra
        self.assertEqual(st3["exec_req"], [])


class ResumoSemanal(unittest.TestCase):
    """(19/11) Resumo semanal da carteira so no Telegram (dinheiro nunca nos ficheiros publicos), uma vez por semana."""
    DOM = 1_800_000_000 - (1_800_000_000 % 86400) + 20 * 3600       # hora 20 UTC desse dia

    def domingo(self):
        import time as _t
        t = self.DOM
        while _t.gmtime(t).tm_wday != A.RESUMO_DIA:
            t += 86400
        return t

    def estado(self):
        return {"conta_saldos": {"t": 1, "m": {"BTC": 70 / 60000, "ETH": 29 / 3000}}, "bybit_tickers": {"t": 1, "m": TK},
                "conta_livre": {"t": 1, "usdc": 1.0}, "ledger": [], "capital_confirmado": True,
                "acumulacao_log": [{"t": 0, "ativo": "BTC", "lado": "comprar", "preco": 60000, "qty": 0.001, "usdc": 60.0}]}

    def test_domingo_envia_uma_vez(self):
        st, msgs, t = self.estado(), [], self.domingo()
        st["acumulacao_log"].append({"t": t - 86400, "ativo": "ETH", "lado": "comprar", "preco": 3000, "qty": 0.01, "usdc": 30.0})
        cfg = {"bybit_modo": "acumulacao", "acumulacao": dict(CFG, modo="real")}
        A.atualizar(st, cfg, t, msgs.append)
        A.atualizar(st, cfg, t + 600, msgs.append)
        self.assertEqual(len(msgs), 1)
        m = msgs[0]
        self.assertIn("resumo semanal", m)
        self.assertIn("comprar ETH 30.00 USDC", m)
        self.assertNotIn("comprar BTC", m.split("últimos 7 dias")[1].split("\n")[0])   # a compra antiga nao e desta semana
        self.assertIn("90.00 USDC", m)                                                   # aplicado desde o inicio
        self.assertIn("BTC", m.split("pesos")[1])
        A.atualizar(st, cfg, t + 7 * 86400, msgs.append)                                   # domingo seguinte
        self.assertEqual(len(msgs), 2)

    def test_fora_de_domingo_e_na_sombra_nao_envia(self):
        t = self.domingo()
        msgs = []
        A.resumo_semanal(self.estado(), dict(CFG, modo="real"), t - 2 * 86400, msgs.append)
        A.resumo_semanal(self.estado(), CFG, t, msgs.append)                              # sombra
        self.assertEqual(msgs, [])

    def test_registo_e_resumo_fora_do_publico(self):
        from engine import execucao, publico
        st = self.estado()
        execucao.apply(st, {"ops": {}, "acumulacao_log": [{"t": 5, "ativo": "BTC", "lado": "comprar", "qty": 1, "usdc": 9.0}]})
        self.assertEqual(st["acumulacao_log"][-1]["t"], 5)
        st["acumulacao_resumo"] = {"t": 1}
        pub = publico.state(st)
        self.assertNotIn("acumulacao_log", pub)
        self.assertNotIn("acumulacao_resumo", pub)
