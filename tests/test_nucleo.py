import unittest
from unittest import mock

from engine import nucleo, executor as X

NOW = 1_800_000_000


def velas(ultimo, n=210, base=100.0):
    return [{"t": NOW - (n - i) * 86400, "c": base} for i in range(n - 1)] + [{"t": NOW - 86400, "c": ultimo}]


class Decisao(unittest.TestCase):
    def test_desligado_so_calcula(self):
        st = {}
        p = nucleo.decidir(st, {"BTC": velas(120), "ETH": velas(80), "SOL": velas(110)}, {"BTC": 120}, 221.6, 195,
                           {"nucleo_ligado": False}, NOW)
        self.assertEqual(p, [])
        self.assertTrue(st["nucleo"]["plano"]["BTC"]["acima"])
        self.assertFalse(st["nucleo"]["plano"]["ETH"]["acima"])
        self.assertEqual(st["nucleo"]["plano"]["BTC"]["alvo_usdc"], round(221.6 * 0.7 / 3, 2))

    def test_ligado_compra_acima_e_vende_abaixo(self):
        st = {"nucleo": {"pos": {"ETH": {"qty": 1.0, "entrada": 90}}, "plano": {}, "pedidos": {}}}
        p = nucleo.decidir(st, {"BTC": velas(120), "ETH": velas(80), "SOL": velas(110)}, {}, 221.6, 100,
                           {"nucleo_ligado": True}, NOW)
        self.assertIn(("nucleo_comprar", "NUCLEO-BTC"), p)
        self.assertIn(("nucleo_vender", "NUCLEO-ETH"), p)
        self.assertIn(("nucleo_comprar", "NUCLEO-SOL"), p)
        self.assertEqual(st["nucleo"]["plano"]["BTC"]["comprar_usdc"], 51.71)
        self.assertEqual(st["nucleo"]["plano"]["SOL"]["comprar_usdc"], 46.29)   # o que resta do USDC livre (98)
        self.assertEqual(nucleo.decidir(st, {"BTC": velas(120)}, {}, 221.6, 100, {"nucleo_ligado": True,
                                        "nucleo_moedas": ["BTC"]}, NOW + 60), [])           # nao repete em 6 horas

    def test_media_de_50_dias_so_btc_valor_todo(self):
        # (01/11) BTC acima da media de 50 dias e abaixo da de 200: com nucleo_dias=50 compra com tudo
        d = [{"t": NOW - (210 - i) * 86400, "c": 200.0 if i < 100 else 100.0} for i in range(209)] + \
            [{"t": NOW - 86400, "c": 120.0}]
        cfg = {"nucleo_ligado": True, "nucleo_moedas": ["BTC"], "nucleo_fracao": 1.0, "nucleo_dias": 50}
        st = {}
        self.assertEqual(nucleo.decidir(st, {"BTC": d}, {"BTC": 120}, 20.0, 20.0, cfg, NOW), [("nucleo_comprar", "NUCLEO-BTC")])
        self.assertEqual(st["nucleo"]["plano"]["BTC"]["comprar_usdc"], 19.6)
        self.assertEqual(st["nucleo"]["plano"]["BTC"]["dias"], 50)
        self.assertEqual(nucleo.decidir({}, {"BTC": d}, {"BTC": 120}, 20.0, 20.0, dict(cfg, nucleo_dias=200), NOW), [])

    def test_sem_historico_nao_decide(self):
        self.assertIsNone(nucleo.sinal(velas(120, n=50)))


class Reforco(unittest.TestCase):
    def test_depois_de_um_deposito_volta_aos_70(self):
        pos = {"BTC": {"qty": 0.5, "entrada": 100}}
        cfg = {"nucleo_ligado": True, "nucleo_moedas": ["BTC"]}
        st = {"nucleo": {"pos": dict(pos), "plano": {}, "pedidos": {}}}
        self.assertEqual(nucleo.decidir(st, {"BTC": velas(120)}, {"BTC": 120}, 333.8, 151, cfg, NOW), [])  # sem o OK
        p = nucleo.decidir(st, {"BTC": velas(120)}, {"BTC": 120}, 333.8, 151, dict(cfg, nucleo_reforcar=True), NOW)
        self.assertEqual(p, [("nucleo_reforcar", "NUCLEO-BTC")])
        self.assertEqual(st["nucleo"]["plano"]["BTC"]["comprar_usdc"], 147.98)   # limitado ao USDC livre (151 x 0,98)
        st2 = {"nucleo": {"pos": {"BTC": {"qty": 1.9, "entrada": 100}}, "plano": {}, "pedidos": {}}}
        self.assertEqual(nucleo.decidir(st2, {"BTC": velas(120)}, {"BTC": 120}, 333.8, 151,
                                        dict(cfg, nucleo_reforcar=True), NOW), [])     # falta pouca: nao mexe

    def test_executor_junta_a_posicao(self):
        ex = {"nucleo": {"BTC": {"qty": 0.0006, "entrada": 80000, "t": 1}}}
        st = {"nucleo": {"plano": {"BTC": {"acima": True, "comprar_usdc": 26.0, "media": 72000}}}}
        msgs = []
        with mock.patch.object(X, "instrument", return_value={"tick": "0.01", "base_step": "0.000001", "min_amt": 5}), \
                mock.patch.object(X, "wallet", return_value={}), mock.patch.object(X, "usdc_free", return_value=150), \
                mock.patch.object(X, "last_price", return_value=82000.0), \
                mock.patch.object(X, "post", return_value={"orderId": "o"}), \
                mock.patch.object(X, "fills", return_value=(82000.0, 0.0003)):
            self.assertEqual(X.do_nucleo_reforcar(st, {"op": "NUCLEO-BTC"}, ex, NOW, lambda t, html=False: msgs.append(t)), "ok")
        self.assertAlmostEqual(ex["nucleo"]["BTC"]["qty"], 0.0009)
        self.assertAlmostEqual(ex["nucleo"]["BTC"]["entrada"], (0.0006 * 80000 + 0.0003 * 82000) / 0.0009, 2)
        self.assertIn("reforcei", msgs[0])
        self.assertEqual(X.do_nucleo_reforcar(st, {"op": "NUCLEO-ETH"}, ex, NOW, msgs.append), "sem posição no núcleo")


class Execucao(unittest.TestCase):
    def test_compra_spot_sem_alavancagem_e_venda(self):
        posts, msgs = [], []
        st = {"nucleo": {"plano": {"BTC": {"acima": True, "comprar_usdc": 51.7, "media": 72464}}}}
        ex = {"ops": {}, "feitos": []}

        def get(path, params=None):
            if "instruments" in path:
                return {"list": [{"lotSizeFilter": {"basePrecision": "0.000001", "quotePrecision": "0.01",
                                                    "minOrderAmt": "5"}, "priceFilter": {"tickSize": "0.01"}}]}
            if "tickers" in path:
                return {"list": [{"lastPrice": "81842.6"}]}
            if "wallet" in path:
                return {"list": [{"coin": [{"coin": "USDC", "walletBalance": "195"}, {"coin": "BTC", "walletBalance": "0.000631"}]}]}
            if "execution" in path:
                side = "Sell" if any(p.get("side") == "Sell" for p in posts) else "Buy"
                return {"list": [{"execQty": "0.000631", "execPrice": "81850", "execFee": "0", "feeCurrency": "USDC", "side": side}]}
            return {}
        with mock.patch.object(X, "get", get), mock.patch.object(X, "post", lambda p, b: posts.append(b) or {"orderId": "o"}), \
                mock.patch.object(X.time, "sleep", lambda s: None):
            self.assertEqual(X.do_nucleo_comprar(st, {"op": "NUCLEO-BTC"}, ex, NOW, lambda t, html=False: msgs.append(t)), "ok")
            self.assertNotIn("isLeverage", posts[0])
            self.assertEqual(posts[0]["side"], "Buy")
            self.assertAlmostEqual(ex["nucleo"]["BTC"]["qty"], 0.000631)
            self.assertEqual(X.do_nucleo_comprar(st, {"op": "NUCLEO-BTC"}, ex, NOW, msgs.append), "já está no núcleo")
            self.assertEqual(X.do_nucleo_vender(st, {"op": "NUCLEO-BTC"}, ex, NOW, lambda t, html=False: msgs.append(t)), "ok")
        self.assertNotIn("BTC", ex["nucleo"])
        self.assertEqual(ex["nucleo_hist"][-1]["moeda"], "BTC")
        self.assertIn("comprei BTC", msgs[0])

    def test_compra_alavancada_2x_e_paga_o_emprestimo(self):
        # (01/11, Rui: "tem de ser alavancado") 2x com margem: compra o dobro, regista o emprestimo e paga-o na venda
        posts, msgs, divida = [], [], [0.0]
        st = {"nucleo": {"plano": {"BTC": {"acima": True, "comprar_usdc": 19.6, "media": 82000, "dias": 50, "alav": 2}}}}
        ex = {"ops": {}, "feitos": []}

        def post(path, body):
            posts.append((path, dict(body)))
            if path == "/v5/order/create" and body.get("side") == "Buy":
                divida[0] = 19.6
            if path == "/v5/order/create" and body.get("side") == "Sell":
                divida[0] = 0.3                                   # a venda abate quase tudo
            return {"orderId": "o"}
        with mock.patch.object(X, "instrument", return_value={"tick": "0.01", "base_step": "0.000001", "min_amt": 5}), \
                mock.patch.object(X, "wallet", return_value={}), mock.patch.object(X, "usdc_free", return_value=20.0), \
                mock.patch.object(X, "usdc_debt", side_effect=lambda w: divida[0]), \
                mock.patch.object(X, "_alavancagem_conta", return_value=2.0), \
                mock.patch.object(X, "last_price", return_value=83000.0), mock.patch.object(X, "post", post), \
                mock.patch.object(X, "held", return_value=0.000471), \
                mock.patch.object(X, "fills", return_value=(83100.0, 0.000471)), mock.patch.object(X.time, "sleep", lambda s: None):
            self.assertEqual(X.do_nucleo_comprar(st, {"op": "NUCLEO-BTC"}, ex, NOW, lambda t, html=False: msgs.append(t)), "ok")
            compra = posts[0][1]
            self.assertEqual(compra["isLeverage"], 1)
            self.assertAlmostEqual(float(compra["qty"]) * 83249, 39.2, delta=0.1)     # o dobro dos 19,6 USDC
            self.assertEqual(ex["nucleo"]["BTC"]["emprestado"], 19.6)
            self.assertIn("Margem 2x", msgs[0])
            self.assertIn("50 dias", msgs[0])
            self.assertEqual(X.do_nucleo_vender(st, {"op": "NUCLEO-BTC"}, ex, NOW, lambda t, html=False: msgs.append(t)), "ok")
        self.assertIn(("/v5/account/repay", {"coin": "USDC", "amount": "0.30"}), posts)

    def test_alavancagem_tem_teto_de_3x(self):
        cfg = {"nucleo_ligado": True, "nucleo_moedas": ["BTC"], "nucleo_fracao": 1.0, "nucleo_alavancagem": 10}
        st = {}
        nucleo.decidir(st, {"BTC": velas(120)}, {"BTC": 120}, 20.0, 20.0, cfg, NOW)
        self.assertEqual(st["nucleo"]["plano"]["BTC"]["alav"], 3.0)

    def test_operacao_ativa_nunca_vende_o_nucleo(self):
        op = {"status": "aberta", "symbol": "SOLUSDC", "asset": "SOL", "entrada": 100, "qty": 0.1,
              "partes": [{"qty": 0.05}, {"qty": 0.05}], "criado": NOW}
        ex = {"ops": {"op1": op}, "nucleo": {"SOL": {"qty": 0.5, "entrada": 104}}}
        vendas = []
        with mock.patch.object(X, "instrument", return_value={"tick": "0.01", "base_step": "0.001"}), \
                mock.patch.object(X, "tpsl_orders", return_value=[]), mock.patch.object(X, "wallet", return_value={}), \
                mock.patch.object(X, "held", return_value=0.6), mock.patch.object(X, "get", return_value={"list": []}), \
                mock.patch.object(X, "sell_all", side_effect=lambda s, q, i, t: vendas.append(q) or None), \
                mock.patch.object(X.time, "sleep", lambda s: None):
            X.do_close({}, {"op": "op1"}, ex, NOW, lambda *a, **k: None)
        self.assertAlmostEqual(vendas[0], 0.1)                              # so a operacao, nao as 0.5 do nucleo


if __name__ == "__main__":
    unittest.main()
