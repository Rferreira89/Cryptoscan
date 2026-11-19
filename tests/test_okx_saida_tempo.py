"""(19/11, ordem do Rui, ponto 2B) Executor OKX antigo: saida por tempo e falhas da API numa posicao ABERTA.
Uma leitura falhada nunca e "posicao fechada"; um fecho por tempo recusado nunca marca a operacao como fechada; o
resultado so vem do historico da OKX dessa posicao (nunca de uma posicao anterior do mesmo instrumento).
Nenhum teste fala com a corretora."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import okx_exec as E  # noqa: E402
from tests.test_okx_caducidade import Gravador  # noqa: E402

NOW = 2_000_000_000
INST = "XLM-USD_UM_XPERP-310704"
POS = {"code": "0", "data": [{"instId": INST, "pos": "-0.3", "avgPx": "0.13745"}]}
SEM_POS = {"code": "0", "data": []}
OK = {"code": "0", "data": [{"sCode": "0"}]}


def op_aberta(**k):
    return {"inst": INST, "ordId": "1", "clOrdId": "csXLM1", "estado": "aberta", "lado": "SHORT", "entrada": 0.13745,
            "t_fill": NOW - 20 * 86400 - 60, "sair_em": NOW - 60, "hold_s": 1728000, "stop": 0.15363, "alvo": 0.11802, **k}


def hist(utime, px="0.138", pnl="-0.01"):
    return {"code": "0", "data": [{"instId": INST, "uTime": str(utime * 1000), "cTime": str((NOW - 20 * 86400) * 1000),
                                   "closeAvgPx": px, "realizedPnl": pnl}]}


def correr(op, g, now=NOW):
    msgs = []
    with mock.patch.object(E, "privado", g):
        fim = E.acompanhar("XLM", op, now, msgs)
    return fim, msgs


class SaidaPorTempo(unittest.TestCase):
    def test_prazo_vem_do_registo_e_fecha_ao_fim_de_20_dias(self):
        op = op_aberta()
        g = Gravador(POS, OK, hist(NOW))
        fim, msgs = correr(op, g)
        self.assertTrue(fim)
        self.assertEqual(op["estado"], "fechada")
        self.assertIn("tempo (480 h)", op["motivo"])
        self.assertIn("/api/v5/trade/close-position", g.posts())

    def test_antes_do_prazo_nao_fecha(self):
        op = op_aberta(sair_em=NOW + 3600)
        fim, _ = correr(op, Gravador(POS))
        self.assertFalse(fim)
        self.assertEqual(op["estado"], "aberta")

    def test_fecho_por_tempo_recusado_nao_marca_fechada(self):
        op = op_aberta()
        g = Gravador(POS, {"code": "51000", "msg": "erro", "data": []})
        fim, msgs = correr(op, g)
        self.assertFalse(fim)
        self.assertEqual(op["estado"], "aberta")                     # tenta na volta seguinte
        self.assertTrue(any("não confirmou o fecho" in m for m in msgs), msgs)

    def test_fecho_sem_resposta_nao_marca_fechada(self):
        op = op_aberta()
        g = Gravador(POS, {"code": "rede", "msg": "URLError"})
        fim, _ = correr(op, g)
        self.assertFalse(fim)
        self.assertEqual(op["estado"], "aberta")


class LeituraFalhada(unittest.TestCase):
    def test_leitura_das_posicoes_falhada_nao_e_posicao_fechada(self):
        for falha in ({"code": "rede", "msg": "URLError"}, {"code": "50001", "msg": "servico", "data": []}, {}):
            op = op_aberta(sair_em=NOW + 3600)
            g = Gravador(falha)
            fim, msgs = correr(op, g)
            self.assertFalse(fim, falha)
            self.assertEqual(op["estado"], "aberta", falha)
            self.assertEqual(g.posts(), [])

    def test_stop_ou_objetivo_so_com_leitura_valida(self):
        op = op_aberta(sair_em=NOW + 3600)
        fim, _ = correr(op, Gravador(SEM_POS, hist(NOW - 600, px="0.1536")))
        self.assertTrue(fim)
        self.assertEqual((op["estado"], op["motivo"], op["saida"]), ("fechada", "stop ou objetivo", 0.1536))


class HistoricoDaPosicaoCerta(unittest.TestCase):
    def test_historico_de_uma_posicao_anterior_nao_conta(self):
        op = op_aberta(sair_em=NOW + 3600)
        antigo = hist(NOW - 40 * 86400, px="0.20", pnl="5")         # fechou ANTES desta operacao abrir
        fim, _ = correr(op, Gravador(SEM_POS, antigo))
        self.assertTrue(fim)
        self.assertEqual(op["estado"], "fechada")
        self.assertIsNone(op["saida"])                                # resultado por confirmar, nunca o da antiga
        self.assertTrue(op.get("resultado_por_confirmar"))

    def test_historico_ilegivel_fica_por_confirmar(self):
        op = op_aberta(sair_em=NOW + 3600)
        fim, _ = correr(op, Gravador(SEM_POS, {"code": "rede"}))
        self.assertTrue(fim)
        self.assertIsNone(op["saida"])
        self.assertTrue(op.get("resultado_por_confirmar"))


class PrazoAposPerdaDeEstado(unittest.TestCase):
    """Reinicio sem o registo da operacao (estado perdido): a posicao e adotada, mas o prazo nao e inventado."""

    def adotar(self, hist_ant):
        R = {"ops": {}, "hist": list(hist_ant)}
        pos = {"code": "0", "data": [{"instId": INST, "pos": "-0.3", "avgPx": "0.13745", "lever": "5",
                                      "cTime": str((NOW - 5 * 86400) * 1000)}]}
        oco = {"code": "0", "data": [{"slTriggerPx": "0.15363"}]}
        g = Gravador(pos, oco, oco)
        msgs = []
        with mock.patch.object(E, "privado", g), mock.patch.object(E.PID, "do_piloto", return_value=False):
            E.reconciliar(R, NOW, msgs)
        return R["ops"]["XLM"], msgs

    def test_com_registo_anterior_usa_o_prazo_original(self):
        op, msgs = self.adotar([{"inst": INST, "hold_s": 1728000, "stop": 0.15363, "alvo": 0.11802, "estado": "fechada"}])
        self.assertEqual(op["sair_em"], NOW - 5 * 86400 + 1728000)
        self.assertFalse(op["prazo_desconhecido"])
        self.assertTrue(any("ao fim de 480 h" in m for m in msgs))

    def test_sem_registo_nao_inventa_72_h(self):
        op, msgs = self.adotar([])
        self.assertIsNone(op["sair_em"])
        self.assertTrue(op["prazo_desconhecido"])
        self.assertTrue(any("prazo original desconhecido" in m for m in msgs))
        fim, _ = correr(op, Gravador(POS), now=NOW + 30 * 86400)     # nunca fecha por tempo, o stop continua
        self.assertFalse(fim)
        self.assertEqual(op["estado"], "aberta")

    def test_execucao_recuperada_pelos_fills_usa_o_prazo_da_operacao(self):
        op = {"inst": INST, "ordId": "9", "estado": "pendente", "valido_ate": NOW + 3600, "lim": 0.1374, "hold_s": 1728000,
              "stop": 0.15363, "alvo": 0.11802, "lado": "SHORT"}
        fills = {"code": "0", "data": [{"ordId": "9", "fillSz": "0.3", "fillPx": "0.1374", "ts": str((NOW - 60) * 1000)}]}
        nao = {"code": "51603", "data": [{"sCode": "51603"}]}
        msgs = []
        with mock.patch.object(E, "privado", Gravador(nao, fills)):
            E.acompanhar("XLM", op, NOW, msgs)
        self.assertEqual(op["estado"], "aberta")
        self.assertEqual(op["sair_em"], NOW - 60 + 1728000)


if __name__ == "__main__":
    unittest.main()
