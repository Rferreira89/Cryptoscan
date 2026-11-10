"""(10/11, preparado para aprovacao; ramo de investigacao) Executor da OKX: estrategia suspensa e protecao integral.
Prova que posicoes abertas continuam geridas com a estrategia suspensa."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import okx_exec as E  # noqa: E402
from tests.test_okx_confirmar_stop import Falso, op_aberta, NOW  # noqa: E402

H40_OFF = dict(E.CFG_PADRAO, real=True, panico_real=False, recuo_real=True)


class Okx:
    """OKX falsa para o ciclo completo do executor (so os pedidos usados aqui)."""
    def __init__(self, estado_ordem="live", acc="0", cancel="0", pos="0"):
        self.estado_ordem, self.acc, self.cancel, self.pos, self.pedidos = estado_ordem, acc, cancel, pos, []

    def __call__(self, metodo, path, corpo=None):
        self.pedidos.append((metodo, path))
        if path.endswith("cancel-order"):
            if self.cancel == "rede":
                return {"code": "rede", "msg": "URLError"}
            if self.cancel == "0":
                self.estado_ordem = "canceled"
            return {"code": "0" if self.cancel == "0" else "1", "data": [{"sCode": self.cancel}]}
        if "/trade/order?" in path:
            return {"code": "0", "data": [{"state": self.estado_ordem, "accFillSz": self.acc, "avgPx": "1.0", "fillTime": str(NOW * 1000)}]}
        if "account/positions" in path:
            return {"code": "0", "data": [{"pos": self.pos}] if float(self.pos) else []}
        if "orders-algo-pending" in path:
            return {"code": "0", "data": [{"slTriggerPx": "0.9", "side": "sell", "sz": self.pos}] if "oco" in path and float(self.pos) else []}
        if "positions-history" in path:
            return {"code": "0", "data": []}
        if "balance" in path:
            return {"code": "0", "data": [{"totalEq": "20"}]}
        return {"code": "0", "data": []}

    def posts(self, fim):
        return [p for m, p in self.pedidos if m == "POST" and p.endswith(fim)]


def pendente(**k):
    return {"inst": "P-X", "ordId": "7", "estado": "pendente", "estrategia": "panico", "lim": 1.0, "stop": 0.9, "alvo": 1.2,
            "valido_ate": NOW + 7200, "t_sig": NOW - 3600, **k}


class Suspensa(unittest.TestCase):
    def correr(self, okx, ops, cfg=H40_OFF):
        st, msgs = {"real": {"ops": dict(ops), "hist": []}}, []
        with mock.patch.object(E, "_chaves", return_value=("k", "s", "p")), mock.patch.object(E, "privado", okx), \
                mock.patch.object(E, "cfg", return_value=cfg), mock.patch.object(E, "reconciliar", lambda *a: None):
            E.correr(st, [], NOW, msgs)
        return st["real"], msgs

    def test_pendente_e_cancelada_e_fica_registada(self):
        okx = Okx()
        R, msgs = self.correr(okx, {"P": pendente()})
        self.assertEqual(len(okx.posts("cancel-order")), 1)
        self.assertNotIn("P", R["ops"]); self.assertEqual(R["hist"][-1]["estado"], "cancelada")

    def test_idempotente_nao_repete_o_pedido(self):
        okx = Okx(cancel="51000")                        # recusa generica: nada e marcado
        R, _ = self.correr(okx, {"P": pendente(cancelar_pedido=NOW - 60)})
        self.assertEqual(okx.posts("cancel-order"), [])

    def test_falha_de_comunicacao_nao_assume_cancelada(self):
        okx = Okx(cancel="rede")
        R, msgs = self.correr(okx, {"P": pendente()})
        self.assertEqual(R["ops"]["P"]["estado"], "pendente"); self.assertNotIn("cancelar_pedido", R["ops"]["P"])
        self.assertTrue(any("não consegui cancelar" in m for m in msgs))

    def test_parcialmente_executada_fica_aberta_e_gerida(self):
        okx = Okx(acc="3", pos="3")
        R, msgs = self.correr(okx, {"P": pendente()})
        op = R["ops"]["P"]
        self.assertEqual(op["estado"], "aberta"); self.assertTrue(op["parcial"])
        self.assertTrue(any("execução parcial" in m for m in msgs))

    def test_posicao_aberta_continua_gerida_com_a_estrategia_suspensa(self):
        okx = Okx(pos="5")
        R, _ = self.correr(okx, {"A": op_aberta(estrategia="panico")})
        self.assertEqual(okx.posts("cancel-order"), []); self.assertEqual(okx.posts("close-position"), [])
        self.assertEqual(R["ops"]["A"]["stop_ok"], NOW)            # o stop continua a ser confirmado
        # e sai por tempo como antes, mesmo suspensa
        okx2 = Okx(pos="5")
        R2, _ = self.correr(okx2, {"A": op_aberta(estrategia="panico", sair_em=NOW - 1)})
        self.assertEqual(len(okx2.posts("close-position")), 1)

    def test_estrategia_ativa_comportamento_inalterado(self):
        okx = Okx()
        R, _ = self.correr(okx, {"P": pendente()}, cfg=dict(H40_OFF, panico_real=True))
        self.assertEqual(okx.posts("cancel-order"), []); self.assertEqual(R["ops"]["P"]["estado"], "pendente")


class ProtecaoIntegral(unittest.TestCase):
    def confirmar(self, f, op):
        R, msgs = {"ops": {"AAA": op}, "hist": []}, []
        with mock.patch.object(E, "privado", f):
            E.confirmar_stops(R, NOW, msgs)
        return R["ops"]["AAA"], msgs

    def test_quantidade_insuficiente_so_alerta(self):
        f = Falso(algos_sl=True, pos="5", algos_sz="3")
        op, msgs = self.confirmar(f, op_aberta())
        self.assertNotIn("stop_ok", op); self.assertEqual(f.posts, [])
        self.assertIn("NÃO protege a posição toda", msgs[0])

    def test_lado_errado_so_alerta(self):
        f = Falso(algos_sl=True, algos_lado="buy")
        op, msgs = self.confirmar(f, op_aberta())
        self.assertEqual(f.posts, []); self.assertTrue(msgs)

    def test_alerta_nao_se_repete_antes_de_6h(self):
        f = Falso(algos_sl=True, algos_sz="1")
        op, msgs = self.confirmar(f, op_aberta(stop_insuficiente=NOW - 3600))
        self.assertEqual(msgs, [])



class OkxCorrida(Okx):
    """(10/11, autorizacao final) a OKX responde ao cancelamento mas a ordem ja tinha executado (corrida), ou responde
    de forma ambigua, ou a consulta do estado falha."""
    def __init__(self, depois="filled", resposta="0", consulta="ok", **k):
        super().__init__(**k)
        self.depois, self.resposta, self.consulta = depois, resposta, consulta

    def __call__(self, metodo, path, corpo=None):
        if path.endswith("cancel-order"):
            self.pedidos.append((metodo, path))
            if self.resposta == "rede":
                return {"code": "rede", "msg": "URLError"}
            self.estado_ordem = self.depois
            return {"code": "0" if self.resposta == "0" else "1", "data": [{"sCode": self.resposta}]}
        if "/trade/order?" in path and self.consulta == "falha":
            self.pedidos.append((metodo, path))
            return {"code": "rede", "msg": "URLError"}
        return super().__call__(metodo, path, corpo)


class PanicoIsoladoCancelamento(unittest.TestCase):
    """(10/11, autorizacao final, ponto 3) cancelamento do panico isolado: o pedido nunca prova que nada executou."""
    ATIVA = dict(E.CFG_PADRAO, real=True, panico_real=True, recuo_real=True, so_mercado=True)

    def correr(self, okx, op, cfg=None, vezes=1):
        st, msgs = {"real": {"ops": {"P": op}, "hist": []}, "pend": {"P": {"tipo": "isolado"}}}, []
        with mock.patch.object(E, "_chaves", return_value=("k", "s", "p")), mock.patch.object(E, "privado", okx), \
                mock.patch.object(E, "cfg", return_value=cfg or self.ATIVA), mock.patch.object(E, "reconciliar", lambda *a: None):
            for i in range(vezes):
                E.correr(st, [], NOW + i * 60, msgs)
        return st["real"], msgs

    def test_cancelada_sem_execucao(self):
        okx = OkxCorrida(depois="canceled", acc="0")
        R, _ = self.correr(okx, pendente())
        self.assertNotIn("P", R["ops"])
        self.assertEqual(R["hist"][-1]["estado"], "cancelada"); self.assertEqual(R["hist"][-1]["motivo"], "H40 isolado")

    def test_parcialmente_executada_fica_aberta_com_gestao(self):
        okx = OkxCorrida(depois="canceled", acc="2", pos="2")
        R, msgs = self.correr(okx, pendente())
        op = R["ops"]["P"]
        self.assertEqual(op["estado"], "aberta"); self.assertTrue(op["parcial"]); self.assertIn("sair_em", op)
        self.assertEqual(op["stop_ok"], NOW)                       # stop confirmado sobre a parte executada
        self.assertEqual(okx.posts("close-position"), [])

    def test_corrida_totalmente_executada_antes_do_cancelamento(self):
        okx = OkxCorrida(depois="filled", resposta="51401", acc="5", pos="5")   # a OKX diz: ja executada
        R, msgs = self.correr(okx, pendente())
        self.assertEqual(R["ops"]["P"]["estado"], "aberta"); self.assertNotIn("parcial", R["ops"]["P"])
        self.assertTrue(any("compra executada" in m for m in msgs))

    def test_corrida_cancelamento_aceite_mas_ordem_executou(self):
        okx = OkxCorrida(depois="filled", resposta="0", acc="5", pos="5")       # aceitou o pedido, mas ja tinha executado
        R, _ = self.correr(okx, pendente())
        self.assertEqual(R["ops"]["P"]["estado"], "aberta")

    def test_estado_desconhecido_por_falha_de_comunicacao_no_cancelamento(self):
        okx = OkxCorrida(resposta="rede")
        R, _ = self.correr(okx, pendente())
        self.assertEqual(R["ops"]["P"]["estado"], "pendente"); self.assertNotIn("cancelar_pedido", R["ops"]["P"])

    def test_estado_desconhecido_por_falha_na_consulta_depois_do_pedido(self):
        okx = OkxCorrida(depois="canceled", consulta="falha")
        R, _ = self.correr(okx, pendente())
        self.assertEqual(R["ops"]["P"]["estado"], "pendente")     # nao se assume cancelada
        self.assertIn("cancelar_pedido", R["ops"]["P"])

    def test_resposta_ambigua_nao_assume_nada(self):
        okx = OkxCorrida(depois="live", resposta="51410")          # codigo nao reconhecido
        R, _ = self.correr(okx, pendente())
        self.assertEqual(R["ops"]["P"]["estado"], "pendente"); self.assertNotIn("cancelar_pedido", R["ops"]["P"])

    def test_cancelamento_idempotente_em_varias_voltas(self):
        okx = OkxCorrida(depois="live", resposta="0")              # pedido aceite, a OKX ainda mostra a ordem viva
        R, _ = self.correr(okx, pendente(), vezes=3)
        self.assertEqual(len(okx.posts("cancel-order")), 1); self.assertEqual(R["ops"]["P"]["estado"], "pendente")

    def test_com_h40_suspensa_um_so_pedido(self):
        okx = OkxCorrida(depois="canceled")
        R, _ = self.correr(okx, pendente(), cfg=H40_OFF)
        self.assertEqual(len(okx.posts("cancel-order")), 1); self.assertNotIn("P", R["ops"])


class SuspensaCorrida(unittest.TestCase):
    def test_suspensa_cancelamento_aceite_mas_executou_fica_gerida(self):
        okx = OkxCorrida(depois="filled", acc="5", pos="5")
        R, _ = Suspensa.correr(Suspensa(), okx, {"P": pendente()})
        self.assertEqual(R["ops"]["P"]["estado"], "aberta"); self.assertEqual(R["ops"]["P"]["stop_ok"], NOW)

    def test_suspensa_nao_abre_novas_posicoes(self):
        st, msgs, posts = {"real": {"ops": {}, "hist": []}}, [], []

        def privado(m, p, c=None):
            if m == "POST":
                posts.append(p)
            return {"code": "0", "data": [{"totalEq": "20"}] if "balance" in p else []}
        with mock.patch.object(E, "_chaves", return_value=("k", "s", "p")), mock.patch.object(E, "privado", privado), \
                mock.patch.object(E, "cfg", return_value=H40_OFF), mock.patch.object(E, "reconciliar", lambda *a: None):
            E.correr(st, [("NOVA", {"t_sig": NOW - 3600, "lim": 1.0, "atr": 0.01, "tipo": "mercado"})], NOW, msgs)
        self.assertNotIn("/api/v5/trade/order", posts); self.assertEqual(st["real"]["ops"], {})

    def test_suspensao_nunca_mexe_em_stops_ou_objetivos(self):
        okx = Okx(pos="5")
        Suspensa.correr(Suspensa(), okx, {"A": op_aberta(estrategia="panico")})
        mexe = [p for m, p in okx.pedidos if m == "POST" and any(k in p for k in ("cancel-algos", "amend-algos", "amend-order", "order-algo"))]
        self.assertEqual(mexe, [])


if __name__ == "__main__":
    unittest.main()
