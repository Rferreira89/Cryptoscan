"""(19/11, ordem do Rui, ponto 2A) Bybit UE: saida por tempo da SHORT_TURTLE (XLM) e o fecho que ela pede.

Onde vive o prazo: plan.max_hold_s do sinal -> position.max_hold (engine/trade.open_position), guardado em
state["signals"][id] (cofre cifrado, relido em cada volta). O acompanhamento de 1 minuto (engine/monitor) gera o
evento TIME; engine/execucao.hooks pede "fechar" ao executor da Europa; se o fecho falhar, execucao.apply volta a
pedir de 15 em 15 min enquanto o executor tiver a operacao aberta. O fecho de um short (engine/executor.close_short)
NUNCA pode deixar a divida sem protecao. Nenhum teste fala com a corretora."""
import copy
import unittest
from unittest import mock

from engine import execucao, executor as X, ledger, signals

ABRIU = 1794673986
STOP, TP = 0.15363886803156823, 0.11802986350124031
ID = "XLM-SHORT_TURTLE-1794673840"


def estado_xlm():
    """A posicao XLM como esta guardada no estado (campos copiados de state.json, sem tamanhos)."""
    pos = {"side": "SHORT", "entry": 0.1374, "stop0": STOP, "stop": STOP, "tps": [TP, 0.0958, 0.0958],
           "partials": [100, 0, 0], "remaining": 100.0, "tp_hit": 0, "realized": 0.0, "fee": 0.0025, "slip": 0.0,
           "opened_at": ABRIU, "breakeven": True, "risk_unit": 0.016966, "max_hold": 1728000, "np_s": None,
           "np_done": False, "trail_r": 1.0, "peak": 0.1374, "closed": False, "r": None, "exit_reason": None}
    sig = {"id": ID, "asset": "XLM", "direction": "SHORT", "strategy": "SHORT_TURTLE", "status": "TRIGGERED",
           "mode": "REAL", "plan": {"max_hold_s": 1728000, "stop": STOP, "tp": [TP, 0.0958, 0.0958]}, "position": pos}
    rec = {"id": ID, "asset": "XLM", "mode": "REAL", "status": "OPEN", "executed": True, "auto_exec": True,
           "strategy": "SHORT_TURTLE", "side": "SHORT", "kind": "4H", "stop": STOP, "tp": [TP], "partials": [100, 0, 0]}
    return {"signals": {ID: sig}, "ledger": [rec], "auto_ops": {ID: "aberta"}}


CFG = {"fee_pct": 0.25}


class PrazoPersistido(unittest.TestCase):
    def test_prazo_associado_a_posicao_e_nao_so_documentado(self):
        st = estado_xlm()
        self.assertEqual(st["signals"][ID]["position"]["max_hold"], 20 * 86400)

    def test_antes_dos_20_dias_nada(self):
        st = estado_xlm()
        ev = signals.track(st, {"XLM": 0.138}, CFG, ABRIU + 20 * 86400 - 60)
        self.assertEqual(ev, [])

    def test_aos_20_dias_sai_por_tempo_e_pede_o_fecho(self):
        st = estado_xlm()
        now = ABRIU + 20 * 86400 + 30
        ev = signals.track(st, {"XLM": 0.138}, CFG, now)
        self.assertEqual([e["event"] for e in ev], ["TIME"])
        ledger.apply(st, ev)
        self.assertEqual(st["ledger"][0]["status"], "CLOSED")
        with mock.patch.object(execucao, "sem_capital", return_value=False):
            execucao.hooks(st, ev, now)
        self.assertEqual([(r["acao"], r["op"]) for r in st["exec_req"]], [("fechar", ID)])

    def test_reinicio_o_prazo_sobrevive_ao_estado_gravado(self):
        import json
        st = json.loads(json.dumps(estado_xlm()))                         # gravar e reler (como o cofre)
        ev = signals.track(st, {"XLM": 0.138}, CFG, ABRIU + 21 * 86400)  # o processo esteve parado: sai na 1.a volta
        self.assertEqual([e["event"] for e in ev], ["TIME"])

    def test_fecho_falhado_volta_a_ser_pedido(self):
        st = estado_xlm()
        st["ledger"][0]["status"] = "CLOSED"                               # o sinal ja saiu por tempo
        st["exec_req"] = []
        ex = {"ops": {ID: {"status": "aberta", "lado": "SHORT", "asset": "XLM", "entrada": 0.1371}}, "feitos": [], "log": []}
        now = ABRIU + 20 * 86400 + 1800
        with mock.patch.object(execucao, "sem_capital", return_value=False), mock.patch.object(execucao.time if hasattr(execucao, "time") else X.time, "time", lambda: now):
            execucao.apply(st, ex)
        self.assertIn(("fechar", ID), [(r["acao"], r["op"]) for r in st.get("exec_req") or []])

    def test_sem_preco_nao_sai_mas_sai_quando_volta_o_preco(self):
        st = estado_xlm()
        self.assertEqual(signals.track(st, {}, CFG, ABRIU + 21 * 86400), [])
        self.assertEqual([e["event"] for e in signals.track(st, {"XLM": 0.14}, CFG, ABRIU + 21 * 86400 + 60)], ["TIME"])


class FechoDoShortNuncaFicaSemProtecao(unittest.TestCase):
    """close_short: le a divida ANTES de cancelar a protecao; se a recompra falhar, repoe o stop."""

    def setUp(self):
        self.op = {"symbol": "XLMUSDC", "asset": "XLM", "lado": "SHORT", "status": "aberta", "qty": 36.8,
                   "emprestado_moeda": 36.8, "stop": 0.1536, "partes": [{"filho": "P1"}], "criado": ABRIU}
        self.ex = {"ops": {ID: self.op}}
        self.req = {"op": ID, "acao": "fechar"}
        self.chamadas = []
        self.divida = 36.8
        self.prot = [{"orderId": "P1", "_flt": "Order"}]
        self.px = 1.0

    def correr(self, carteira_falha=False, recompra_falha=False):
        def get(path, q=None):
            if path == "/v5/account/wallet-balance":
                if carteira_falha and q.get("accountType") == "UNIFIED":
                    raise X.ExecError("timeout")
                if q.get("accountType") == "SPOT":
                    return {"list": [{"coin": []}]}                     # a conta errada: sem divida visivel
                return {"list": [{"coin": [{"coin": "XLM", "borrowAmount": str(self.divida), "walletBalance": "0"}]}]}
            return {"list": []}

        def cancel(sym, o):
            self.chamadas.append(("cancelar", o["orderId"]))
            self.prot = [p for p in self.prot if p["orderId"] != o["orderId"]]

        def buy_back(sym, qty, inst, tag):
            self.chamadas.append(("recomprar", round(qty, 1)))
            if recompra_falha:
                raise X.ExecError("10001 sem liquidez")
            self.divida = 0.0
            return "B1"

        def stop_buy(sym, qty, stop, inst, tag):
            self.chamadas.append(("repor_stop", round(qty, 1), stop))
            self.prot.append({"orderId": "S2", "_flt": "tpslOrder"})
            return "S2"

        with mock.patch.object(X, "get", get), mock.patch.object(X, "cancel", cancel), \
                mock.patch.object(X, "buy_back", buy_back), mock.patch.object(X, "stop_order_buy", stop_buy), \
                mock.patch.object(X, "instrument", lambda s: {"base_step": "0.1", "tick": "0.0001", "min_amt": 5.0}), \
                mock.patch.object(X, "last_price", lambda s: self.px), \
                mock.patch.object(X, "tpsl_orders", lambda s: list(self.prot)), \
                mock.patch.object(X, "fills", lambda *a, **k: (0.138, 36.8)), \
                mock.patch.object(X, "repay_coin", lambda *a: None), mock.patch.object(X.time, "sleep", lambda s: None):
            msgs = []
            try:
                res = X.close_short({}, self.req, self.ex, ABRIU + 20 * 86400, msgs.append, "tempo")
            except X.ExecError as e:
                res = f"erro: {e}"
        return res

    def test_fecho_normal(self):
        res = self.correr()
        self.assertEqual(res, "ok")
        self.assertEqual(self.op["status"], "fechada")
        self.assertEqual([c[0] for c in self.chamadas], ["cancelar", "recomprar"])

    def test_divida_por_confirmar_nao_toca_na_protecao(self):
        res = self.correr(carteira_falha=True)
        self.assertTrue(str(res).startswith("erro"), res)
        self.assertEqual(self.chamadas, [])                                # protecao intacta
        self.assertEqual(self.op["status"], "aberta")
        self.assertEqual([p["orderId"] for p in self.prot], ["P1"])

    def test_recompra_abaixo_do_minimo_compra_o_minimo(self):
        self.px = 0.138                                     # 36,8 XLM a 0,138 = 5,08 USDC: abaixo do piso de 6
        res = self.correr()
        self.assertEqual(res, "ok")
        q = [c for c in self.chamadas if c[0] == "recomprar"][0][1]
        self.assertGreaterEqual(q * 0.138, 6.0 - 0.01)

    def test_recompra_falhada_repoe_o_stop(self):
        res = self.correr(recompra_falha=True)
        self.assertTrue(str(res).startswith("erro"), res)
        self.assertEqual(self.op["status"], "aberta")
        self.assertIn(("repor_stop", 36.8, 0.1536), self.chamadas)
        self.assertTrue(self.prot, "a divida ficou sem protecao")
        self.assertIn("S2", [p.get("stopId") for p in self.op["partes"]])  # o fecho seguinte encontra-o e cancela-o


if __name__ == "__main__":
    unittest.main()
