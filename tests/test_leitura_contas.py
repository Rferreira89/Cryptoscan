"""(11/11) Leitura das contas: so GET, nada de saldos no que e publico, saldos so para o Telegram."""
import inspect
import json
import unittest

from tools import leitura_contas as L


def pedido_falso(chamadas):
    def p(base, path):
        chamadas.append(path)
        if path.startswith("/api/v5/account/config"):
            return {"code": "0", "data": [{"acctLv": "2", "posMode": "net_mode", "perm": "read_only,trade"}]}
        if path.startswith("/api/v5/account/trade-fee"):
            return {"code": "0", "data": [{"maker": "-0.0002", "taker": "-0.0005", "level": "Lv1"}]}
        if path.startswith("/api/v5/account/instruments"):
            return {"code": "0", "data": [{"instId": "DOGE-USD_UM_XPERP-1"}]}
        if path.startswith("/api/v5/public/instruments"):
            return {"code": "0", "data": [{"instId": "DOGE-USD_UM_XPERP-1", "state": "live", "ctVal": "10", "minSz": "1", "lotSz": "1", "lever": "20"},
                                          {"instId": "BTC-USD-251226", "state": "live"}]}
        if path.startswith("/api/v5/market/tickers"):
            return {"code": "0", "data": [{"instId": "DOGE-USD_UM_XPERP-1", "last": "0.07"}]}
        if path.startswith("/api/v5/account/balance"):
            return {"code": "0", "data": [{"totalEq": "123.45", "details": [{"ccy": "USDT", "availBal": "99.9", "eq": "123.45"}]}]}
        if path.startswith("/api/v5/account/positions"):
            return {"code": "0", "data": []}
        return {"code": "1", "msg": "?"}
    return p


class OKX(unittest.TestCase):
    def test_publico_sem_saldos_e_privado_com_saldos(self):
        ch = []
        pub, priv = L.okx(pedido_falso(ch))
        txt = json.dumps(pub)
        self.assertNotIn("123.45", txt)
        self.assertNotIn("99.9", txt)
        self.assertEqual(priv["okx"]["totalEq"], 123.45)
        self.assertIn("DOGE-USD_UM_XPERP-1", pub["xperps"])
        self.assertNotIn("BTC-USD-251226", pub["xperps"])
        self.assertAlmostEqual(pub["xperps"]["DOGE-USD_UM_XPERP-1"]["nocional_minimo_usd"], 0.7)
        self.assertTrue(all("/trade/" not in c for c in ch))

    def test_resumo_privado_tem_cenarios(self):
        pub, priv = L.okx(pedido_falso([]))
        txt = L.resumo_privado(priv, {"okx": pub})
        self.assertIn("123.45", txt)
        self.assertIn("risco 1%", txt)


class SoLeitura(unittest.TestCase):
    def test_sem_escritas(self):
        src = inspect.getsource(L)
        import re
        for proibido in ("POST", "/trade/order", "/v5/order", "cancel", "set-leverage"):
            self.assertNotIn(proibido, src)
        self.assertIsNone(re.search(r"\bprivado\(", src))          # o assinante com metodo da OKX nao e usado

    def test_bybit_recusa_chave_com_negociacao(self):
        class Acc:
            AccountError = Exception
            def get(self, path, params=None):
                return {"readOnly": 0}
            def read_only(self, info):
                return False
        pub, priv = L.bybit(Acc())
        self.assertIn("erro", pub)
        self.assertEqual(priv, {})


if __name__ == "__main__":
    unittest.main()
