"""(11/11, P6) Reconciliacao do ledger Bybit: ensaio por omissao, so corrige com as tres provas."""
import copy
import os
import sys
import unittest
import unittest.mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import bybit_ledger_reconciliar as B  # noqa: E402

NOW = 1794359000
AVAX = {"id": "AVAX-SHORT_TURTLE-1792670417", "asset": "AVAX", "pair": "AVAX/USDC", "strategy": "SHORT_TURTLE", "mode": "REAL",
        "side": "SHORT", "issued_at": 1792670400, "status": "OPEN", "opened_at": 1792670580, "entry": 9.233, "executed": False}
FECHADA = {"id": "SEI-SHORT_TURTLE-1", "mode": "REAL", "status": "CLOSED", "executed": True, "pair": "SEI/USDC"}


def leitor(execs=(), saldo=0.0, divida=0.0, ordens=(), falha=None):
    chamadas = []

    def get(path, params):
        chamadas.append((path, dict(params)))
        if falha and falha in path:
            raise B.LeituraFalhou("HTTP 500")
        if path == "/v5/execution/list":
            return {"list": list(execs)}
        if path == "/v5/account/wallet-balance":
            return {"list": [{"coin": [{"coin": "AVAX", "walletBalance": str(saldo), "borrowAmount": str(divida)}]}]}
        if path == "/v5/order/realtime":
            return {"list": list(ordens)}
        raise AssertionError(f"endpoint inesperado {path}")
    get.chamadas = chamadas
    return get


def estado():
    return {"ledger": [copy.deepcopy(AVAX), copy.deepcopy(FECHADA)]}


class Reconciliar(unittest.TestCase):
    def test_ensaio_por_omissao_nao_altera_nada(self):
        st = estado()
        plano = B.correr(st, NOW, get=leitor(), nucleo={})
        self.assertEqual(plano[0]["acao"], "corrigir")
        self.assertEqual(st["ledger"][0]["status"], "OPEN")

    def test_aplica_com_as_tres_provas_e_guarda_trilho(self):
        st = estado()
        B.correr(st, NOW, aplicar=True, get=leitor(), nucleo={})
        r = st["ledger"][0]
        self.assertEqual(r["status"], "CANCELLED")
        self.assertEqual(r["antes"]["status"], "OPEN")
        self.assertTrue(r["reconciliacao"]["prova"]["provado"])
        self.assertIsNone(r["result_r"])
        self.assertEqual(st["ledger"][1], FECHADA)                     # os outros registos ficam iguais

    def test_com_execucao_nao_corrige(self):
        st = estado()
        plano = B.correr(st, NOW, aplicar=True, get=leitor(execs=[{"execId": "1"}]), nucleo={})
        self.assertIn("manter", plano[0]["acao"])
        self.assertEqual(st["ledger"][0]["status"], "OPEN")

    def test_com_divida_ou_saldo_nao_corrige(self):
        for kw in ({"divida": 1.0}, {"saldo": 2.0}):
            st = estado()
            B.correr(st, NOW, aplicar=True, get=leitor(**kw), nucleo={})
            self.assertEqual(st["ledger"][0]["status"], "OPEN", kw)

    def test_nucleo_nao_conta_como_posicao(self):
        st = estado()
        B.correr(st, NOW, aplicar=True, get=leitor(saldo=2.0), nucleo={"AVAX": {"qty": 2.0}})
        self.assertEqual(st["ledger"][0]["status"], "CANCELLED")

    def test_com_ordem_ativa_nao_corrige(self):
        st = estado()
        B.correr(st, NOW, aplicar=True, get=leitor(ordens=[{"orderId": "9"}]), nucleo={})
        self.assertEqual(st["ledger"][0]["status"], "OPEN")

    def test_leitura_falhada_e_prova_incompleta(self):
        for falha in ("execution", "wallet", "realtime"):
            st = estado()
            plano = B.correr(st, NOW, aplicar=True, get=leitor(falha=falha), nucleo={})
            self.assertFalse(plano[0]["prova"]["provado"], falha)
            self.assertEqual(st["ledger"][0]["status"], "OPEN")

    def test_janelas_cobrem_desde_a_emissao(self):
        g = leitor()
        B.correr(estado(), NOW, get=g, nucleo={})
        ex = [p for path, p in g.chamadas if path == "/v5/execution/list"]
        self.assertEqual(ex[0]["startTime"], AVAX["issued_at"] * 1000)
        self.assertGreaterEqual(ex[-1]["endTime"], (NOW - 1) * 1000)
        self.assertTrue(all(p["endTime"] - p["startTime"] <= 7 * 86400 * 1000 for p in ex))

    def test_nucleo_ilegivel_nao_prova_nada(self):
        st = estado()
        with unittest.mock.patch.object(B, "nucleo_do_executor", side_effect=B.LeituraFalhou("sem chave")):
            plano = B.correr(st, NOW, aplicar=True, get=leitor())
        self.assertFalse(plano[0]["prova"]["provado"])
        self.assertEqual(st["ledger"][0]["status"], "OPEN")

    def test_so_endpoints_de_leitura(self):
        src = open(os.path.join(os.path.dirname(__file__), "..", "tools", "bybit_ledger_reconciliar.py")).read()
        for proibido in ("/v5/order/create", "/v5/order/cancel", "/v5/order/amend", "/v5/position", "post("):
            self.assertNotIn(proibido, src)


if __name__ == "__main__":
    unittest.main()
