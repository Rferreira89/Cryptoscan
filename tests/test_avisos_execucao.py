"""(13/11, A2) Uma falha de execucao nunca fica silenciosa: o executor regista cada aviso (id da mensagem do
Telegram, falha, duplicado), volta a enviar os falhados e o scanner reconcilia ordens recusadas sem aviso confirmado.
Corretora simulada que recusa a ordem (170140)."""
import json
import os
import tempfile
import unittest
from unittest import mock

from engine import alerts, execucao as E, executor as X

NOW = 1794600000


class Executor(unittest.TestCase):
    def correr(self, envio, ex0=None):
        d = tempfile.mkdtemp()
        st = os.path.join(d, "st.json")
        json.dump({"exec_req": [{"id": "vender-op1", "acao": "vender", "op": "op1", "t": NOW}]}, open(st, "w"))
        ein = os.path.join(d, "in.json")
        json.dump(ex0 or {}, open(ein, "w"))
        out = os.path.join(d, "out.json")

        def recusa(state, req, ex, now, send):           # a corretora simulada recusa a ordem
            ex["ops"]["op1"] = {"asset": "BNB", "status": "recusada", "erro": "170140", "t": now}
            send("⚠️ A venda a descoberto de BNB falhou na Bybit: 170140. Nada foi vendido.")
            return "170140"
        with mock.patch.object(X, "configured", return_value=True), \
                mock.patch.object(X, "get", return_value={"permissions": {}, "ips": ["1.2.3.4"], "readOnly": 0}), \
                mock.patch.object(X, "key_ok", return_value=(True, "ok")), \
                mock.patch.dict(X.ACTIONS, {"vender": recusa}), \
                mock.patch.object(alerts, "send", side_effect=envio), \
                mock.patch("time.time", return_value=NOW):
            X.main(st, ein, out)
        return json.load(open(out))

    def test_regista_id_da_mensagem(self):
        ex = self.correr(lambda t, html=False: 4321)
        a = ex["avisos"][-1]
        self.assertEqual((a["estado"], a["message_id"], a["op"]), ("enviado", 4321, "op1"))

    def test_falha_registada_e_reenviada(self):
        def falha(t, html=False):
            raise alerts.AlertError("Telegram HTTP 502")
        ex = self.correr(falha)
        self.assertEqual((ex["avisos"][-1]["estado"], ex["avisos"][-1]["tentativas"]), ("falhou", 1))
        enviados = []
        ex2 = self.correr(lambda t, html=False: enviados.append(t) or 99, ex0={"avisos": ex["avisos"], "feitos": ["vender-op1"]})
        rec = [a for a in ex2["avisos"] if a["hash"] == ex["avisos"][-1]["hash"]][0]
        self.assertEqual((rec["estado"], rec["message_id"], rec["tentativas"]), ("enviado", 99, 2))
        self.assertTrue(enviados[0].startswith("(reenvio)"))


class Reconciliacao(unittest.TestCase):
    def ex(self, avisos):
        return {"t": NOW, "ops": {"op1": {"asset": "BNB", "status": "recusada", "erro": "170140", "t": NOW - 1200}},
                "avisos": avisos}

    def test_sem_aviso_confirmado_o_scanner_avisa_uma_vez(self):
        st = {"ledger": [{"id": "op1", "asset": "BNB", "strategy": "SHORT_TURTLE"}]}
        enviados = []
        with mock.patch.object(alerts, "configured", return_value=True), \
                mock.patch.object(alerts, "send", side_effect=lambda t, *a, **k: enviados.append(t) or 7):
            self.assertEqual(E.reconciliar_avisos(st, self.ex([{"op": "op1", "estado": "falhou"}]), NOW), ["op1"])
            self.assertEqual(E.reconciliar_avisos(st, self.ex([{"op": "op1", "estado": "falhou"}]), NOW), [])
        self.assertEqual(len(enviados), 1)
        self.assertIn("BNB", enviados[0])
        self.assertEqual(st["avisos_reconciliados"]["op1"]["message_id"], 7)

    def test_com_aviso_confirmado_nao_repete(self):
        self.assertEqual(E.avisos_em_falta({}, self.ex([{"op": "op1", "estado": "enviado", "message_id": 1}]), NOW), [])

    def test_antigas_e_recentes_nao(self):
        ex = self.ex([])
        ex["ops"]["op1"]["t"] = NOW - 60                       # o executor ainda pode estar a enviar
        self.assertEqual(E.avisos_em_falta({}, ex, NOW), [])
        ex["ops"]["op1"]["t"] = E.A2_DESDE - 10                # BNB de 12/11: ja tratada
        self.assertEqual(E.avisos_em_falta({}, ex, E.A2_DESDE + 3600), [])


if __name__ == "__main__":
    unittest.main()
