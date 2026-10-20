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
