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


class ResultadoReal(unittest.TestCase):
    """Fase 1 (20/10): o resultado real vem das execucoes da Bybit."""
    def test_long_fechado_com_comissoes(self):
        from engine import account, ledger
        T = 1_800_000_000
        led = [{"id": "ENA-X-1", "kind": "4H", "asset": "ENA", "pair": "ENA/USDC", "issued_at": T,
                "status": "CLOSED", "closed_at": T + 7200, "result_r": 0.15, "risk_usdc": 1.66}]
        ex = lambda side, q, px, fee, cur, dt: {"symbol": "ENAUSDC", "side": side, "execQty": str(q),
                                               "execPrice": str(px), "execFee": str(fee),
                                               "feeCurrency": cur, "execTime": str((T + dt) * 1000)}
        execs = [ex("Buy", 100, 0.1882, 0.1, "ENA", 60),                 # comissao paga em ENA
                 ex("Sell", 49.95, 0.195, 0.0097, "USDC", 3600),
                 ex("Sell", 49.95, 0.1882, 0.0094, "USDC", 7000),
                 ex("Buy", 50, 0.2, 0, "USDC", 9 * 3600)]                 # fora da janela
        r = account.real_results(led, execs, T + 8000)["ENA-X-1"]
        self.assertTrue(r["fechada"])
        self.assertEqual(r["n"], 3)
        esperado = 49.95 * 0.195 + 49.95 * 0.1882 - 100 * 0.1882 - 0.0191
        self.assertAlmostEqual(r["pnl_usdc"], round(esperado, 4), places=4)
        self.assertAlmostEqual(r["comissoes_usdc"], 0.0191 + 0.1 * 0.1882, places=4)
        v = ledger.apply_real(led, {"ENA-X-1": r})
        self.assertEqual(v["n"], 1)
        self.assertAlmostEqual(led[0]["real_r"], round(r["pnl_usdc"] / 1.66, 2))
        # uma leitura parcial mais tarde nao apaga o resultado ja fechado
        ledger.apply_real(led, {"ENA-X-1": dict(r, fechada=False, pnl_usdc=None)})
        self.assertTrue(led[0]["real"]["fechada"])

    def test_aberta_sem_resultado_e_sem_execucao_ignorada(self):
        from engine import account
        T = 1_800_000_000
        led = [{"id": "XPL-X-1", "kind": "4H", "asset": "XPL", "pair": "XPL/USDC", "issued_at": T, "status": "OPEN"},
               {"id": "SOL-X-1", "kind": "4H", "asset": "SOL", "pair": "SOL/USDC", "issued_at": T, "status": "OPEN"}]
        execs = [{"symbol": "XPLUSDC", "side": "Buy", "execQty": "300", "execPrice": "0.0768", "execFee": "0.3",
                  "feeCurrency": "XPL", "execTime": str((T + 60) * 1000)}]
        out = account.real_results(led, execs, T + 3600)
        self.assertFalse(out["XPL-X-1"]["fechada"])
        self.assertIsNone(out["XPL-X-1"]["pnl_usdc"])
        self.assertNotIn("SOL-X-1", out)


class RecuperarAntigas(unittest.TestCase):
    def test_le_as_execucoes_da_altura_em_janelas_de_7_dias(self):
        from unittest import mock
        from engine import account as A
        now = 1_800_000_000
        r = {"id": "PUMP-1", "kind": "4H", "executed": True, "mode": "REAL", "status": "CLOSED", "asset": "PUMP",
             "pair": "PUMP/USDC", "issued_at": now - 20 * 86400, "closed_at": now - 11 * 86400, "risk_usdc": 2.5}
        pedidos = []
        def get(path, prm):
            pedidos.append(prm)
            if prm["startTime"] // 1000 < r["issued_at"] + 3600:
                return {"list": [{"symbol": "PUMPUSDC", "side": "Buy", "execQty": "1000", "execPrice": "0.0062",
                                  "execFee": "0.006", "feeCurrency": "USDC", "execTime": str((r["issued_at"] + 60) * 1000)}]}
            return {"list": [{"symbol": "PUMPUSDC", "side": "Sell", "execQty": "1000", "execPrice": "0.0050",
                              "execFee": "0.005", "feeCurrency": "USDC", "execTime": str((r["closed_at"]) * 1000)}]}
        with mock.patch.object(A, "get", get):
            out = A.recuperar([r, dict(r, id="X", real={"fechada": True})], now)
        self.assertEqual(list(out), ["PUMP-1"])
        self.assertEqual(len(pedidos), 2)                       # 9 dias = 2 janelas
        self.assertTrue(out["PUMP-1"]["fechada"])
        self.assertAlmostEqual(out["PUMP-1"]["pnl_usdc"], 5.0 - 6.2 - 0.011, 3)


class VerificacaoOrdens(unittest.TestCase):
    def test_tp_e_aviso_diario(self):
        from engine import account as A, run as RUN
        orders = [{"symbol": "XPLUSDC", "side": "Sell", "triggerPrice": "0.0725"},
                  {"symbol": "XPLUSDC", "side": "Sell", "takeProfit": "0.0813", "stopLoss": "0.0725", "triggerPrice": "0"}]
        self.assertEqual(A.tp_for(orders, "XPLUSDC", "LONG", 0.0768), 1)
        self.assertEqual(A.tp_for(orders[:1], "XPLUSDC", "LONG", 0.0768), 0)    # o stop nao conta como objetivo
        conta = {"trades": [{"id": "XPL-1", "asset": "XPL", "held": True, "stop_found": True, "tp_n": 0}]}
        st = {}
        ex_prog = {"ops": {"XPL-1": {"status": "aberta", "partes": [{"anexo": False}, {"anexo": False}]}}}
        self.assertEqual(RUN.ordens_watch(st, conta, ex_prog, 1000), [])      # o programa sabe que vende
        ex_anexo = {"ops": {"XPL-1": {"status": "aberta", "partes": [{"anexo": True}]}}}
        m = RUN.ordens_watch(st, conta, ex_anexo, 1000)
        self.assertEqual(len(m), 1)
        self.assertIn("sem objetivo", m[0])
        self.assertEqual(RUN.ordens_watch(st, conta, ex_anexo, 2000), [])     # uma vez por dia
        self.assertEqual(st["ordens_ok"]["posicoes"], 1)
