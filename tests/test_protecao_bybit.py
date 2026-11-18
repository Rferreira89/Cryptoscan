"""(18/11) Representacao da protecao da Bybit UE: estado lido na corretora, nunca pelo plano interno."""
import unittest
from unittest import mock

from engine import account as A, protecao as P

NOW = 1_800_000_000
SYM = "XLMUSDC"


def tpsl(status="Untriggered", side="Buy", sl="0.1536", tp="0.118", qty="10", sym=SYM, oid="2348290033494419713"):
    return {"orderId": oid, "symbol": sym, "side": side, "orderStatus": status, "stopOrderType": "BidirectionalTpslOrder",
            "triggerPrice": "0.0000", "stopLoss": sl, "takeProfit": tp, "qty": qty,
            "createdTime": str((NOW - 3600) * 1000), "updatedTime": str((NOW - 60) * 1000)}


def est(abertas, ok=True, lida=NOW, historico=None, interno="aberta", lado="SHORT", plano=0.15364):
    return P.estado_protecao_bybit(SYM, lado, abertas, ok, lida, NOW, plano_stop=plano, historico=historico,
                                   estado_interno=interno)


class EstadoProtecao(unittest.TestCase):
    def test_tpsl_ativo(self):
        r = est([tpsl()])
        self.assertEqual(r["estado"], "ATIVA")
        self.assertEqual((r["stop"], r["objetivo"], r["quantidade"]), (0.1536, 0.118, 10.0))
        o = r["ordens"][0]
        self.assertEqual((o["orderId"], o["tipo"], o["estado"], o["lado"]),
                         ("2348290033494419713", "BidirectionalTpslOrder", "Untriggered", "Buy"))
        self.assertEqual((o["criada"], o["atualizada"]), (NOW - 3600, NOW - 60))
        self.assertEqual(r["lida_em"], NOW)
        self.assertEqual(r["divergencias"], [])

    def test_tpsl_disparado(self):
        r = est([], historico=[{"tipo": "BidirectionalTpslOrder", "estado": "Triggered"}])
        self.assertEqual(r["estado"], "DISPARADA")
        self.assertTrue(any("aberta" in d for d in r["divergencias"]))   # o registo ainda diz aberta

    def test_ordem_cancelada(self):
        r = est([tpsl(status="Cancelled")], historico=[{"tipo": "BidirectionalTpslOrder", "estado": "Cancelled"}])
        self.assertEqual(r["estado"], "CANCELADA")

    def test_ordem_inexistente(self):
        r = est([], historico=[])
        self.assertEqual(r["estado"], "INEXISTENTE")
        r = est([tpsl(side="Sell")], historico=[])      # do lado errado nao protege um short
        self.assertEqual(r["estado"], "INEXISTENTE")
        r = est([tpsl(sym="XLMUSDT")], historico=[])     # outro par
        self.assertEqual(r["estado"], "INEXISTENTE")

    def test_api_indisponivel(self):
        r = est([], ok=False)
        self.assertEqual(r["estado"], "NAO_VERIFICADA")
        r = est([tpsl()], ok=False)                       # nem com ordens de outra leitura parcial
        self.assertEqual(r["estado"], "NAO_VERIFICADA")

    def test_estado_interno_diferente_da_corretora(self):
        r = est([tpsl()], interno="fechada")
        self.assertEqual(r["estado"], "ATIVA")
        self.assertTrue(any("fechada" in d for d in r["divergencias"]))
        r = est([tpsl(sl="0.17")])
        self.assertTrue(any("difere do plano" in d for d in r["divergencias"]))

    def test_dados_antigos_ou_sem_hora(self):
        self.assertEqual(est([tpsl()], lida=None)["estado"], "NAO_VERIFICADA")
        r = est([tpsl()], lida=NOW - P.BYBIT_LEITURA_MAX_S - 1)
        self.assertEqual(r["estado"], "NAO_VERIFICADA")
        self.assertIn("min", r["motivo"])

    def test_nunca_ativa_pelo_plano(self):
        r = est([], historico=None, plano=0.15364)
        self.assertNotEqual(r["estado"], "ATIVA")
        self.assertIn("historico nao lido", r["motivo"])

    def test_historico_vazio_nao_e_desprotegida(self):
        # o caso da XLM a 18/11: 'protecao' do registo vazio (historico) e a ordem ativa na corretora
        self.assertEqual(est([tpsl()], historico=[])["estado"], "ATIVA")

    def test_long(self):
        r = P.estado_protecao_bybit("SOLUSDC", "LONG", [tpsl(sym="SOLUSDC", side="Sell", sl="90", tp="120")], True, NOW,
                                    NOW, plano_stop=90)
        self.assertEqual((r["estado"], r["stop"], r["objetivo"]), ("ATIVA", 90.0, 120.0))


class Integracao(unittest.TestCase):
    def test_open_orders_lidas_assinala_falha_sem_filtro(self):
        def get(path, prm):
            if "orderFilter" not in prm:
                raise A.AccountError("timeout")
            return {"list": []}
        with mock.patch.object(A, "get", get):
            ordens, ok, t = A.open_orders_lidas()
        self.assertEqual(ordens, [])
        self.assertFalse(ok)

    def test_open_orders_lidas_ok(self):
        with mock.patch.object(A, "get", lambda path, prm: {"list": [tpsl()] if "orderFilter" not in prm else []}):
            ordens, ok, t = A.open_orders_lidas()
            self.assertEqual(A.open_orders(), ordens)
        self.assertTrue(ok)
        self.assertEqual(len(ordens), 1)

    def test_check_trades_leva_a_protecao_e_mantem_stop_found(self):
        led = [{"id": "x", "kind": "4H", "status": "OPEN", "asset": "XLM", "pair": "XLM/USDC", "side": "SHORT",
                "stop": 0.15364, "issued_at": NOW - 7200, "real": {"estado": "aberta", "protecao": []}}]
        r = A.check_trades(led, {"XLM": -10.0}, [tpsl()], [], NOW, leitura=(True, NOW))[0]
        self.assertTrue(r["stop_found"])
        self.assertEqual(r["protecao"]["estado"], "ATIVA")
        r = A.check_trades(led, {"XLM": -10.0}, [], [], NOW, leitura=(False, NOW))[0]
        self.assertEqual(r["protecao"]["estado"], "NAO_VERIFICADA")
        self.assertFalse(r["stop_found"])                 # comportamento dos alarmes inalterado
        self.assertNotIn("protecao", A.check_trades(led, {}, [], [], NOW)[0])   # chamada antiga: igual

    def test_copia_publica_sem_quantidades(self):
        from engine import publico
        r = publico.limpar({"trades": [{"protecao": est([tpsl()])}]})
        txt = str(r)
        self.assertNotIn("quantidade", txt)
        self.assertIn("ATIVA", txt)


if __name__ == "__main__":
    unittest.main()
