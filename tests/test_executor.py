"""Execucao com um toque: regras, pedidos, compra simulada (sem rede)."""
import unittest
from unittest import mock

from engine import execucao, executor as X, inbox, run

NOW = 1_800_000_000
PLAN = {"entry_zone": [99.0, 100.0], "stop": 95.0, "tp": [105.0, 110.0, 115.0],
        "partials": [50, 30, 20], "position_usdc": 20.0}


def state(status="ACTIVE", executed=None, issued=NOW - 600):
    rec = {"id": "SOL-BOUNCE_X30-1", "asset": "SOL", "pair": "SOL/USDC", "issued_at": issued,
           "status": "WAITING", "entry_zone": [99, 100], "stop": 95, "tp": PLAN["tp"],
           "risk_usdc": 1.0, "position_usdc": 20.0}
    if executed is not None:
        rec["executed"] = executed
    return {"ledger": [rec], "signals": {"SOL-BOUNCE_X30-1": {"status": status, "mode": "REAL",
                                                               "plan": dict(PLAN)}}}


class Chave(unittest.TestCase):
    def test_permissoes(self):
        ok = {"readOnly": 0, "permissions": {"Spot": ["SpotTrade"], "Wallet": []}, "ips": ["2.28.62.236"]}
        self.assertTrue(X.key_ok(ok)[0])
        self.assertFalse(X.key_ok(dict(ok, readOnly=1))[0])
        self.assertIn("a mais", X.key_ok(dict(ok, permissions={"Spot": ["SpotTrade"], "Wallet": ["Withdraw"]}))[1])
        self.assertIn("a mais", X.key_ok(dict(ok, permissions={"Spot": ["SpotTrade"], "ContractTrade": ["Order"]}))[1])
        # Bybit UE: "Trading" junta spot e derivados; aceite (o programa so faz spot)
        self.assertTrue(X.key_ok(dict(ok, permissions={"Spot": ["SpotTrade"], "Derivatives": ["DerivativesTrade"],
                                                       "Wallet": []}))[0])
        self.assertFalse(X.key_ok(dict(ok, permissions={"Spot": ["SpotTrade"], "Derivatives": ["DerivativesTrade"],
                                                        "Earn": ["Earn"]}))[0])
        self.assertIn("IP", X.key_ok(dict(ok, ips=["*"]))[1])
        self.assertIn("IP", X.key_ok(dict(ok, ips=[]))[1])
        self.assertFalse(X.key_ok(dict(ok, permissions={}))[0])


class Regras(unittest.TestCase):
    def test_partes(self):
        p = X.parts_for(20, [105, 110, 115], [50, 30, 20], 5)
        self.assertEqual([round(q, 2) for q, _ in p], [10.0, 10.0])   # 4 USDC junta-se
        self.assertEqual([tp for _, tp in p], [105, 110])
        self.assertAlmostEqual(sum(q for q, _ in p), 20)
        self.assertEqual(len(X.parts_for(6, [105, 110], [50, 50], 5)), 1)
        self.assertEqual(X.parts_for(4, [105], [100], 5), [])

    def test_arredondar(self):
        self.assertEqual(X.fmt(1.23456, "0.01"), "1.23")
        self.assertEqual(X.fmt(0.000123456, "0.000001"), "0.000123")
        self.assertEqual(X.fmt(105.678, "0.1"), "105.6")

    def test_validacao(self):
        op = "SOL-BOUNCE_X30-1"
        self.assertIsNotNone(X.buy_check(state(), op, 99.5, NOW)[0])
        self.assertIn("zona", X.buy_check(state(), op, 101, NOW)[1])
        self.assertIn("stop", X.buy_check(state(), op, 95.1, NOW)[1])
        self.assertIn("ativo", X.buy_check(state("CLOSED"), op, 99.5, NOW)[1])
        self.assertIn("à mão", X.buy_check(state(executed=True), op, 99.5, NOW)[1])
        self.assertIn("6 horas", X.buy_check(state(issued=NOW - 7 * 3600), op, 99.5, NOW)[1])
        st = state()
        st["signals"][op]["mode"] = "PAPER"
        self.assertIn("papel", X.buy_check(st, op, 99.5, NOW)[1])
        self.assertIn("não encontrada", X.buy_check(st, "XPTO", 99.5, NOW)[1])


class CompraSimulada(unittest.TestCase):
    def test_compra_em_partes(self):
        posts, msgs = [], []

        def fake_get(path, params=None):
            if "tickers" in path:
                return {"list": [{"lastPrice": "99.5"}]}
            if "instruments" in path:
                return {"list": [{"lotSizeFilter": {"basePrecision": "0.001", "quotePrecision": "0.01",
                                                    "minOrderAmt": "5"}, "priceFilter": {"tickSize": "0.01"}}]}
            if "wallet" in path:
                return {"list": [{"coin": [{"coin": "USDC", "walletBalance": "50"}]}]}
            if "execution" in path:
                return {"list": [{"execQty": "0.1", "execPrice": "99.6", "execFee": "0.0001",
                                  "feeCurrency": "SOL"}]}
            return {}

        def fake_post(path, params):
            posts.append(params)
            return {"orderId": f"o{len(posts)}"}
        ex = {"ops": {}, "feitos": []}
        with mock.patch.object(X, "get", fake_get), mock.patch.object(X, "post", fake_post):
            r = X.do_buy(state(), {"op": "SOL-BOUNCE_X30-1"}, ex, NOW,
                         lambda t, html=False: msgs.append(t))
        self.assertEqual(r, "ok")
        self.assertEqual(len(posts), 2)
        self.assertEqual(posts[0]["takeProfit"], "105.00")
        self.assertEqual(posts[0]["stopLoss"], "95.00")
        self.assertEqual(posts[0]["marketUnit"], "quoteCoin")
        self.assertEqual(posts[0]["qty"], "10.00")
        o = ex["ops"]["SOL-BOUNCE_X30-1"]
        self.assertEqual(o["status"], "aberta")
        self.assertAlmostEqual(o["qty"], 0.1998)
        self.assertIn("Executado: SOL", msgs[0])

    def test_recusa_fora_da_zona_nao_compra(self):
        posts, msgs = [], []
        with mock.patch.object(X, "get", lambda p, q=None: {"list": [{"lastPrice": "103"}]}), \
                mock.patch.object(X, "post", lambda p, q: posts.append(q)):
            X.do_buy(state(), {"op": "SOL-BOUNCE_X30-1"}, {"ops": {}, "feitos": []}, NOW,
                     lambda t, html=False: msgs.append(t))
        self.assertEqual(posts, [])
        self.assertIn("Nada foi comprado", msgs[0])


class LadoDoScanner(unittest.TestCase):
    def tearDown(self):
        execucao.READY = False

    def test_pedidos_e_ganchos(self):
        st = state()
        self.assertIsNotNone(execucao.request(st, "comprar", "SOL-BOUNCE_X30-1", NOW))
        self.assertIsNone(execucao.request(st, "comprar", "SOL-BOUNCE_X30-1", NOW))
        self.assertTrue(execucao.due(st, NOW))
        self.assertFalse(execucao.due(st, NOW + 10))
        self.assertTrue(execucao.due(st, NOW + 400))          # repete se nao foi feito
        rid = st["exec_req"][0]["id"]
        ex = {"pronto": True, "feitos": [rid], "ops": {"SOL-BOUNCE_X30-1": {"status": "aberta", "entrada": 99.6}}}
        execucao.apply(st, ex)
        self.assertFalse(execucao.READY)                  # sem teste real aprovado
        ex["teste"] = {"passos": ["compra 5.25 USDC: ok", "venda: 0.0001 BTC a 1"]}
        execucao.apply(st, ex)
        self.assertTrue(execucao.READY)
        self.assertEqual(st["exec_req"], [])
        rec = st["ledger"][0]
        self.assertTrue(rec["executed"] and rec["auto_exec"])
        self.assertEqual(rec["exec_price"], 99.6)
        execucao.hooks(st, [{"event": "TP1", "id": "SOL-BOUNCE_X30-1"},
                            {"event": "TIME", "id": "OUTRA"}], NOW)
        self.assertEqual([r["acao"] for r in st["exec_req"]], ["breakeven"])

    def test_botao_e_parar(self):
        e = {"event": "ISSUED", "id": "SOL-BOUNCE_X30-1", "asset": "SOL", "t": 1}
        self.assertNotIn("e|", str(run.markup_for(e, {}, True)))
        execucao.READY = True
        m = run.markup_for(e, {}, True)
        self.assertEqual(m["inline_keyboard"][0][0]["callback_data"], "e|SOL-BOUNCE_X30-1")
        st = state()
        ups = [{"update_id": 1, "callback_query": {"id": "c", "data": "e|SOL-BOUNCE_X30-1",
                                                   "message": {"chat": {"id": 7}}}},
               {"update_id": 2, "message": {"chat": {"id": 7}, "text": "/parar", "date": NOW}}]
        out = inbox.apply(st, ups, "7", {})
        self.assertIn("Pedido recebido", out[0][0])
        self.assertIn("paragem", out[1][0])
        self.assertEqual([r["acao"] for r in st["exec_req"]], ["comprar", "parar"])

    def test_sem_chave_nao_aceita(self):
        st = state()
        ups = [{"update_id": 1, "callback_query": {"id": "c", "data": "e|SOL-BOUNCE_X30-1",
                                                   "message": {"chat": {"id": 7}}}}]
        out = inbox.apply(st, ups, "7", {})
        self.assertIn("ainda não está ligada", out[0][0])
        self.assertNotIn("exec_req", st)


if __name__ == "__main__":
    unittest.main()
