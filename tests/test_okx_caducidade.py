"""(11/11, auditoria P2) Caducidade de 8 h das ordens limite da OKX: o estado final e sempre confirmado na OKX.
Nenhum teste fala com a corretora: `privado` e sempre substituido por respostas gravadas."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import okx_exec as E  # noqa: E402

NOW = 2_000_000_000
VIVA = {"code": "0", "data": [{"state": "live", "accFillSz": "0"}]}
PEDIDO_OK = {"code": "0", "data": [{"sCode": "0"}]}


def op_caducada(**extra):
    return {"inst": "X-USD_UM_XPERP-1", "ordId": "7", "estado": "pendente", "valido_ate": NOW - 1, "lim": 1.0,
            "stop": 0.9, "alvo": 1.2, **extra}


class Gravador:
    """Responde por ordem de chamada e regista (metodo, caminho)."""

    def __init__(self, *respostas):
        self.respostas = list(respostas)
        self.chamadas = []

    def __call__(self, metodo, path, corpo=None):
        self.chamadas.append((metodo, path))
        return self.respostas.pop(0) if self.respostas else {"code": "0", "data": []}

    def posts(self):
        return [p for m, p in self.chamadas if m == "POST"]


def correr(op, g, now=NOW):
    msgs = []
    with mock.patch.object(E, "privado", g):
        fim = E.acompanhar("X", op, now, msgs)
    return fim, msgs


class Caducidade(unittest.TestCase):
    def test_cancelamento_normal_confirmado_com_zero_executado(self):
        op = op_caducada()
        g = Gravador(VIVA, PEDIDO_OK, {"code": "0", "data": [{"state": "canceled", "accFillSz": "0"}]})
        fim, msgs = correr(op, g)
        self.assertTrue(fim)
        self.assertEqual(op["estado"], "cancelada")
        self.assertIn("caducou", op["motivo"])
        self.assertTrue(any("Nada comprado" in m for m in msgs))
        self.assertEqual(g.posts(), ["/api/v5/trade/cancel-order"])

    def test_execucao_parcial_antes_do_cancelamento_fica_aberta_e_gerida(self):
        op = op_caducada()
        g = Gravador(VIVA, PEDIDO_OK, {"code": "0", "data": [{"state": "canceled", "accFillSz": "3", "avgPx": "0.99",
                                                             "fillTime": str((NOW - 60) * 1000)}]})
        fim, msgs = correr(op, g)
        self.assertFalse(fim)
        self.assertEqual(op["estado"], "aberta")
        self.assertTrue(op["parcial"])
        self.assertAlmostEqual(op["entrada"], 0.99)
        self.assertIn("sair_em", op)
        self.assertFalse(any("Nada comprado" in m for m in msgs))

    def test_execucao_total_durante_a_corrida(self):
        op = op_caducada()
        g = Gravador(VIVA, {"code": "1", "data": [{"sCode": "51400", "sMsg": "already filled"}]},
                     {"code": "0", "data": [{"state": "filled", "accFillSz": "5", "avgPx": "1.0", "fillTime": str(NOW * 1000)}]})
        fim, msgs = correr(op, g)
        self.assertFalse(fim)
        self.assertEqual(op["estado"], "aberta")
        self.assertNotIn("parcial", op)
        self.assertFalse(any("Nada comprado" in m for m in msgs))

    def test_codigos_51401_e_51402_tambem_levam_a_confirmacao(self):
        for codigo in ("51401", "51402"):
            op = op_caducada()
            g = Gravador(VIVA, {"code": "1", "data": [{"sCode": codigo}]},
                         {"code": "0", "data": [{"state": "canceled", "accFillSz": "0"}]})
            fim, _ = correr(op, g)
            self.assertTrue(fim, codigo)
            self.assertEqual(op["estado"], "cancelada")

    def test_falha_de_rede_no_cancelamento_fica_pendente(self):
        op = op_caducada()
        g = Gravador(VIVA, {})                                               # sem resposta
        fim, msgs = correr(op, g)
        self.assertFalse(fim)
        self.assertEqual(op["estado"], "pendente")
        self.assertNotIn("cancelar_pedido", op)
        self.assertEqual(op["ambiguo"], 1)
        self.assertEqual(msgs, [])                                           # ainda sem alerta (1 volta)

    def test_falha_de_rede_na_consulta_nao_envia_nada(self):
        op = op_caducada()
        g = Gravador({})
        fim, _ = correr(op, g)
        self.assertFalse(fim)
        self.assertEqual(op["estado"], "pendente")
        self.assertEqual(g.posts(), [])

    def test_resposta_ambigua_depois_do_pedido_fica_pendente(self):
        op = op_caducada()
        g = Gravador(VIVA, PEDIDO_OK, VIVA)                                  # a OKX ainda nao processou o cancelamento
        fim, _ = correr(op, g)
        self.assertFalse(fim)
        self.assertEqual(op["estado"], "pendente")
        self.assertIn("cancelar_pedido", op)

    def test_cancelada_sem_indicar_o_executado_nao_e_tratada_como_zero(self):
        op = op_caducada()
        g = Gravador(VIVA, PEDIDO_OK, {"code": "0", "data": [{"state": "canceled"}]})
        fim, msgs = correr(op, g)
        self.assertFalse(fim)
        self.assertEqual(op["estado"], "pendente")
        self.assertFalse(any("Nada comprado" in m for m in msgs))

    def test_alerta_unico_apos_tres_voltas_ambiguas(self):
        op = op_caducada()
        todas = []
        for i in range(5):
            _, msgs = correr(op, Gravador(VIVA, {}), NOW + i * 3600)
            todas += msgs
        alertas = [m for m in todas if "🚨" in m]
        self.assertEqual(len(alertas), 1)
        self.assertIn("PENDENTE", alertas[0])
        self.assertEqual(op["estado"], "pendente")

    def test_repeticao_idempotente_e_resolucao_na_volta_seguinte(self):
        op = op_caducada()
        correr(op, Gravador(VIVA, PEDIDO_OK, VIVA))                          # 1.a volta: pedido feito, estado por confirmar
        t0 = op["cancelar_pedido"]
        fim, msgs = correr(op, Gravador(VIVA, PEDIDO_OK, {"code": "0", "data": [{"state": "canceled", "accFillSz": "0"}]}),
                           NOW + 3600)
        self.assertTrue(fim)
        self.assertEqual(op["cancelar_pedido"], t0)                          # a hora do primeiro pedido nao muda
        self.assertEqual(op["estado"], "cancelada")
        self.assertNotIn("ambiguo", op)

    def test_motivo_da_suspensao_e_preservado(self):
        op = op_caducada(cancelar_pedido=NOW - 100, motivo_cancelar="H40 isolado")
        fim, _ = correr(op, Gravador(VIVA, PEDIDO_OK, {"code": "0", "data": [{"state": "canceled", "accFillSz": "0"}]}))
        self.assertTrue(fim)
        self.assertEqual(op["motivo"], "H40 isolado")

    def test_nunca_toca_em_stops_ou_posicoes(self):
        op = op_caducada()
        g = Gravador(VIVA, PEDIDO_OK, {"code": "0", "data": [{"state": "canceled", "accFillSz": "2", "avgPx": "1"}]})
        correr(op, g)
        for p in g.posts():
            self.assertEqual(p, "/api/v5/trade/cancel-order")

    def test_reconciliacao_posterior_adota_posicao_de_uma_ordem_registada_como_cancelada(self):
        # rede de seguranca que continua ativa: uma posicao na OKX sem operacao seguida e adotada e o stop confirmado
        R = {"ops": {}, "hist": [{"asset": "X", "inst": "X-USD_UM_XPERP-1", "ordId": "7", "estado": "cancelada",
                                   "stop": 0.9, "alvo": 1.2, "t_sig": NOW - 50000}]}

        def privado(metodo, path, corpo=None):
            if "positions?instType" in path:
                return {"code": "0", "data": [{"instId": "X-USD_UM_XPERP-1", "pos": "2", "avgPx": "1", "cTime": str(NOW * 1000), "lever": "3"}]}
            if "orders-algo-pending" in path:
                return {"code": "0", "data": [{"slTriggerPx": "0.9"}]}
            return {"code": "0", "data": []}
        msgs = []
        with mock.patch.object(E, "privado", privado):
            E.reconciliar(R, NOW, msgs)
        self.assertEqual(R["ops"]["X"]["estado"], "aberta")
        self.assertEqual(R["ops"]["X"]["stop"], 0.9)
        self.assertIn("stop_ok", R["ops"]["X"])


if __name__ == "__main__":
    unittest.main()
