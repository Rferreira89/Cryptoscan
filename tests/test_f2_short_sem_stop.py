"""(28/10, auditoria F2) Um short nunca fica sem stop em silencio."""
import unittest

from tests.test_diretor import VendaADescoberto, NOW


class ShortSemStop(VendaADescoberto):
    def post_sem_stop(self, path, body):
        X = self.X
        if path == "/v5/order/create" and body.get("side") == "Sell" and body.get("stopLoss"):
            raise X.ExecError("TP/SL não suportado")            # o anexo falha
        if path == "/v5/order/create" and body.get("triggerPrice"):
            raise X.ExecError("stop recusado")                    # o stop de reserva tambem
        return self.post(path, body)

    def test_recompra_logo_e_avisa(self):
        from unittest import mock
        X, sent = self.X, []
        ex = {"ops": {}}
        ps = self.patches(last_price=100.0, best_bid=99.9)
        for p in ps:
            p.start()
        try:
            with mock.patch.object(X, "post", side_effect=self.post_sem_stop):
                res = X.do_short(self._sei(), {"op": "op1"}, ex, NOW, lambda t, html=False: sent.append(t))
        finally:
            for p in ps:
                p.stop()
        self.assertEqual(res, "sem stop: recomprada")
        self.assertEqual(ex["ops"]["op1"]["status"], "fechada")
        buys = [b for p, b in self.calls if b.get("side") == "Buy" and "triggerPrice" not in b]
        self.assertTrue(buys)                                      # recomprou
        self.assertIn("recusou o stop", sent[-1])
        self.assertFalse(any("fica na Bybit até ao fim" in t for t in sent))

    def test_sem_stop_e_sem_recompra_da_alarme(self):
        from unittest import mock
        X, sent = self.X, []
        ex = {"ops": {}}

        def tudo_falha(path, body):
            if path == "/v5/order/create" and body.get("side") == "Buy":
                raise X.ExecError("recompra recusada")
            return self.post_sem_stop(path, body)
        ps = self.patches(last_price=100.0, best_bid=99.9)
        for p in ps:
            p.start()
        try:
            with mock.patch.object(X, "post", side_effect=tudo_falha):
                X.do_short(self._sei(), {"op": "op1"}, ex, NOW, lambda t, html=False: sent.append(t))
        finally:
            for p in ps:
                p.stop()
        self.assertTrue(any("SEM STOP" in t for t in sent))
        self.assertFalse(any("fica na Bybit até ao fim" in t for t in sent))
        self.assertEqual(ex["ops"]["op1"]["status"], "aberta")    # continua seguida para fechar


if __name__ == "__main__":
    unittest.main()
