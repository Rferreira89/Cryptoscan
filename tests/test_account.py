import os
import unittest
from unittest import mock

from engine import account as A

LED = [{"id": "P1", "kind": "4H", "asset": "PUMP", "pair": "PUMP/USDC",
        "status": "OPEN", "executed": True, "stop": 0.005, "issued_at": 1000},
       {"id": "E1", "kind": "4H", "asset": "ENA", "pair": "ENA/USDC",
        "status": "OPEN", "executed": False, "stop": 0.19, "issued_at": 1000},
       {"id": "W1", "kind": "4H", "asset": "WLD", "status": "CLOSED"}]


class Account(unittest.TestCase):
    def test_assinatura_conhecida(self):
        # HMAC-SHA256 hex de "1key5000a=1" com o segredo "s"
        import hashlib, hmac
        exp = hmac.new(b"s", b"1key5000a=1", hashlib.sha256).hexdigest()
        self.assertEqual(A.sign("s", "1", "key", "5000", "a=1"), exp)

    def test_so_leitura(self):
        self.assertTrue(A.read_only({"readOnly": 1}))
        self.assertTrue(A.read_only({"readOnly": "1"}))
        self.assertFalse(A.read_only({"readOnly": 0}))
        self.assertFalse(A.read_only({}))

    def test_moedas_e_usdc(self):
        w = {"list": [{"coin": [
            {"coin": "USDC", "walletBalance": "40.5", "availableToWithdraw": "30.25"},
            {"coin": "PUMP", "walletBalance": "1900"},
            {"coin": "BTC", "walletBalance": "0"}]}]}
        self.assertEqual(A.coins(w), {"USDC": 40.5, "PUMP": 1900.0})
        self.assertEqual(A.usdc_free(w), 30.25)

    def test_stop_e_entrada(self):
        orders = [{"symbol": "PUMPUSDC", "side": "Sell", "triggerPrice": "0.00498"},
                  {"symbol": "PUMPUSDC", "side": "Sell", "triggerPrice": "0",
                   "price": "0.0075"},
                  {"symbol": "ICPUSDC", "side": "Sell", "triggerPrice": "2.8"}]
        execs = [{"symbol": "PUMPUSDC", "side": "Buy", "execQty": "1000",
                  "execPrice": "0.0062", "execTime": "2000000"},
                 {"symbol": "PUMPUSDC", "side": "Buy", "execQty": "1000",
                  "execPrice": "0.0064", "execTime": "2000000"},
                 {"symbol": "PUMPUSDC", "side": "Buy", "execQty": "5",
                  "execPrice": "0.001", "execTime": "100"}]   # antes do sinal
        rows = A.check_trades(LED, {"PUMP": 2000.0}, orders, execs, 3000)
        self.assertEqual([r["id"] for r in rows], ["P1"])   # ENA nao executada
        r = rows[0]
        self.assertTrue(r["held"] and r["stop_found"])
        self.assertEqual(r["stop_px"], 0.00498)
        self.assertAlmostEqual(r["fill_px"], 0.0063)
        self.assertAlmostEqual(r["stop_gap_pct"], -0.4)

    def test_sem_stop(self):
        rows = A.check_trades(LED, {}, [], [], 3000)
        self.assertFalse(rows[0]["stop_found"])
        self.assertFalse(rows[0]["held"])

    def test_sem_chave_nao_faz_pedidos(self):
        with mock.patch.dict(os.environ, {"BYBIT_API_KEY": "", "BYBIT_API_SECRET": ""}):
            self.assertEqual(A.snapshot({}, 5)["error"], "sem chave")

    def test_recusa_chave_com_escrita(self):
        with mock.patch.dict(os.environ, {"BYBIT_API_KEY": "k", "BYBIT_API_SECRET": "s"}), \
                mock.patch.object(A, "get", return_value={"readOnly": 0}) as g:
            snap = A.snapshot({"ledger": LED}, 5)
        self.assertFalse(snap["ok"])
        self.assertIn("NÃO é só de leitura", snap["error"])
        self.assertEqual(g.call_count, 1)        # nao le mais nada


if __name__ == "__main__":
    unittest.main()
