"""(13/11, A3) Estados das ordens e reconciliacao: a BNB recusada (executed False) sai de OPEN, nao ocupa vaga nem
risco, passa para a sombra; uma posicao executada nunca e tocada."""
import unittest

from engine import execucao as E
from engine import promo


def rec(i, **k):
    return dict({"id": i, "mode": "REAL", "asset": "BNB", "strategy": "SHORT_TURTLE", "side": "SHORT", "status": "OPEN",
                 "entry": 664.21, "stop": 708.23, "tp": [591.2, 507.4, 507.4], "partials": [100, 0, 0],
                 "issued_at": 1794484833, "opened_at": 1794484986, "risk_pct": 1.63, "position_pct": 22.3}, **k)


class Estados(unittest.TestCase):
    def test_bnb_recusada_sai_de_open_e_vai_para_a_sombra(self):
        st = {"ledger": [rec("bnb", executed=False, recusada="/v5/order/create: 170140 Order value exceeded lower limit."),
                         rec("btc", asset="BTC", executed=True, exec_price=71512.5, entry=71673.6, stop=75621.2,
                             tp=[64987.6, 56975.9, 56975.9])],
              "signals": {"bnb": {"status": "TRIGGERED", "plan": {"max_hold_s": 20 * 86400}},
                          "btc": {"status": "TRIGGERED", "plan": {}}}}
        ex = {"ops": {"bnb": {"status": "recusada", "erro": "170140"},
                      "btc": {"status": "aberta", "entrada": 71512.5, "qty": 0.0001}}}
        feitas = E.reconciliar_ordens(st, ex, 1794500000)
        self.assertEqual(feitas, ["bnb"])
        bnb, btc = st["ledger"]
        self.assertEqual((bnb["status"], bnb["estado_ordem"], bnb["reason"]), ("CANCELLED", "RECUSADA", "NAO_EXECUTADA"))
        self.assertEqual(st["signals"]["bnb"]["status"], "CANCELLED")
        self.assertEqual((btc["status"], btc["estado_ordem"]), ("OPEN", "EXECUTADA"))   # a real nao e tocada
        self.assertEqual(st["signals"]["btc"]["status"], "TRIGGERED")
        som = list(st["sombra_rejeitadas"]["abertas"].values())
        self.assertEqual((len(som), som[0]["filtro"]), (1, "execução"))
        r = promo.risco_aberto(st)
        self.assertEqual((r["pct"], r["moedas"]), (1.63, {"BTC"}))            # a recusada nao conta no risco
        self.assertEqual(E.reconciliar_ordens(st, ex, 1794500100), [])       # idempotente

    def test_estados(self):
        self.assertEqual(E.estado_ordem({"id": "a"}, None, set()), "SINAL")
        self.assertEqual(E.estado_ordem({"id": "a"}, None, {"a"}), "ORDEM_ENVIADA")
        self.assertEqual(E.estado_ordem({"id": "a"}, {"status": "pendente"}, set()), "ORDEM_ENVIADA")
        self.assertEqual(E.estado_ordem({"id": "a"}, {"status": "verificar"}, set()), "ORDEM_ENVIADA")
        self.assertEqual(E.estado_ordem({"id": "a"}, {"status": "cancelada"}, set()), "CANCELADA")
        self.assertEqual(E.estado_ordem({"id": "a", "status": "CANCELLED"}, None, set()), "EXPIRADA")
        self.assertEqual(E.estado_ordem({"id": "a"}, {"status": "recusada", "motivo": "Erro inesperado"}, set()),
                         "FALHOU")
        self.assertEqual(E.estado_ordem({"id": "a"}, {"status": "fechada", "entrada": 1.0}, set()), "EXECUTADA")

    def test_ordem_com_entrada_nunca_e_cancelada(self):
        st = {"ledger": [rec("x", executed=False, recusada="parcial")], "signals": {}}
        ex = {"ops": {"x": {"status": "recusada", "entrada": 660.0}}}
        self.assertEqual(E.reconciliar_ordens(st, ex, 1), [])
        self.assertEqual(st["ledger"][0]["status"], "OPEN")


if __name__ == "__main__":
    unittest.main()
