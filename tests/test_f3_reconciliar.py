"""(28/10, auditoria F3) Programa e conta Bybit batem certo, ou o Rui e avisado."""
import unittest
from unittest import mock

from engine import run, inbox


def conta(t, held=False, stop=False):
    return {"t": t, "trades": [{"id": "SEI-SHORT_TURTLE-1", "asset": "SEI", "held": held,
                                "stop_found": stop, "tp_n": 0, "fill_px": 0.057}]}


class Reconciliar(unittest.TestCase):
    def test_operacao_que_desapareceu_avisa_a_segunda_leitura(self):
        st = {}
        self.assertEqual(run.reconciliar(st, conta(100), {}, 100), [])          # uma leitura: espera
        self.assertEqual(run.reconciliar(st, conta(100), {}, 400), [])          # a mesma leitura: nao conta
        out = run.reconciliar(st, conta(1000), {}, 1000)
        self.assertEqual(len(out), 1)
        self.assertIn("SEI", out[0])
        self.assertIn("/limpar", out[0])
        self.assertEqual(run.reconciliar(st, conta(2000), {}, 2000), [])        # so uma vez

    def test_posicao_com_stop_nao_avisa(self):
        st = {}
        run.reconciliar(st, conta(100, held=True, stop=True), {}, 100)
        self.assertEqual(run.reconciliar(st, conta(1000, held=True, stop=True), {}, 1000), [])

    def test_nucleo_com_mais_do_que_a_conta(self):
        st = {"conta_saldos": {"t": 100, "m": {"BTC": 0.0, "ETH": 0.032, "SOL": 0.0}}}
        ex = {"nucleo": {"BTC": {"qty": 0.00094, "entrada": 81841}, "ETH": {"qty": 0.032, "entrada": 2402}}}
        c = {"t": 100, "trades": []}
        run.reconciliar(st, c, ex, 100)
        st["conta_saldos"]["t"] = 1000
        out = run.reconciliar(st, dict(c, t=1000), ex, 1000)
        self.assertEqual(len(out), 1)
        self.assertIn("núcleo BTC", out[0])

    def test_limpar_pede_ao_executor_para_acertar_o_nucleo(self):
        st = {"ledger": []}
        inbox.apply(st, [{"message": {"chat": {"id": "admin"}, "date": 5, "text": "/limpar"}}], "admin")
        self.assertTrue(any(r["acao"] == "nucleo_acertar" for r in st["exec_req"]))

    def test_executor_acerta_sem_negociar(self):
        from engine import executor as X
        ex = {"nucleo": {"BTC": {"qty": 0.00094, "entrada": 81841.0}, "ETH": {"qty": 0.032, "entrada": 2402.0},
                         "SOL": {"qty": 0.74, "entrada": 104.0}}}
        saldos = {"BTC": 0.0, "ETH": 0.032, "SOL": 0.5}
        sent = []
        with mock.patch.object(X, "wallet", return_value={}), \
                mock.patch.object(X, "held", side_effect=lambda w, a: saldos[a]), \
                mock.patch.object(X, "post") as post:
            X.do_nucleo_acertar({}, {"op": ""}, ex, 0, lambda t, html=False: sent.append(t))
        post.assert_not_called()
        self.assertNotIn("BTC", ex["nucleo"])
        self.assertEqual(ex["nucleo"]["ETH"]["qty"], 0.032)
        self.assertEqual(ex["nucleo"]["SOL"]["qty"], 0.5)
        self.assertIn("Nada foi comprado", sent[0])


if __name__ == "__main__":
    unittest.main()
