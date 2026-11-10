"""(10/11) cada operacao real aberta tem de ter o stop vivo na OKX (nao so registado no estado)."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import okx_exec as E  # noqa: E402

NOW = 2_000_000_000


def op_aberta(**k):
    return {"inst": "AAA-USD_UM_XPERP-1", "ordId": "9", "estado": "aberta", "entrada": 1.0, "stop": 0.9, "alvo": 1.2,
            "t_fill": NOW - 3600, "sair_em": NOW + 3600, **k}


class Falso:
    def __init__(self, algos_sl=False, falha_algos=False, pos="5", recusa=False):
        self.algos_sl, self.falha_algos, self.pos, self.recusa, self.posts = algos_sl, falha_algos, pos, recusa, []

    def __call__(self, metodo, path, corpo=None):
        if "orders-algo-pending" in path:
            if self.falha_algos:
                return {"code": "50001", "data": []}
            return {"code": "0", "data": [{"slTriggerPx": "0.9"}] if self.algos_sl and "oco" in path else []}
        if "account/positions" in path:
            return {"code": "0", "data": [{"pos": self.pos}] if self.pos else []}
        if path.endswith("order-algo"):
            self.posts.append(corpo)
            return {"code": "1", "data": [{"sCode": "51000"}]} if self.recusa else {"code": "0", "data": [{"sCode": "0"}]}
        raise AssertionError(path)


class ConfirmarStop(unittest.TestCase):
    def correr(self, f, op):
        R, msgs = {"ops": {"AAA": op}, "hist": []}, []
        with mock.patch.object(E, "privado", f):
            E.confirmar_stops(R, NOW, msgs)
        return R["ops"]["AAA"], msgs

    def test_stop_vivo_confirma_sem_mexer(self):
        f = Falso(algos_sl=True)
        op, msgs = self.correr(f, op_aberta())
        self.assertEqual(op["stop_ok"], NOW)
        self.assertEqual(f.posts, []); self.assertEqual(msgs, [])

    def test_sem_stop_repoe_oco_so_para_fechar(self):
        f = Falso()
        op, msgs = self.correr(f, op_aberta())
        self.assertEqual(len(f.posts), 1)
        c = f.posts[0]
        self.assertEqual((c["side"], c["ordType"], c["reduceOnly"], c["sz"]), ("sell", "oco", True, "5"))
        self.assertEqual((c["slTriggerPx"], c["tpTriggerPx"]), ("0.9", "1.2"))
        self.assertEqual(op["stop_reposto"], NOW)
        self.assertIn("repus o stop", msgs[0])

    def test_consulta_falhada_nao_faz_nada(self):
        f = Falso(falha_algos=True)
        op, msgs = self.correr(f, op_aberta())
        self.assertEqual(f.posts, []); self.assertEqual(msgs, []); self.assertNotIn("stop_ok", op)

    def test_posicao_ja_fechada_nao_poe_ordem(self):
        f = Falso(pos=None)
        op, msgs = self.correr(f, op_aberta())
        self.assertEqual(f.posts, []); self.assertEqual(msgs, [])

    def test_recusa_avisa_e_volta_a_tentar(self):
        f = Falso(recusa=True)
        op, msgs = self.correr(f, op_aberta())
        self.assertIn("SEM stop", msgs[0]); self.assertNotIn("stop_ok", op)

    def test_sem_preco_de_stop_avisa_sem_ordem(self):
        f = Falso()
        op, msgs = self.correr(f, op_aberta(stop=None))
        self.assertEqual(f.posts, []); self.assertIn("SEM stop", msgs[0])

    def test_nunca_empilha_segunda_reposicao(self):
        f = Falso()
        op, msgs = self.correr(f, op_aberta(stop_reposto=NOW - 7200))
        self.assertEqual(f.posts, []); self.assertIn("já o repus", msgs[0])
        op, msgs = self.correr(f, op)                        # o aviso nao repete na hora seguinte
        self.assertEqual(f.posts, []); self.assertEqual(msgs, [])

    def test_confirmado_ha_pouco_nao_consulta(self):
        def privado(*a, **k):
            raise AssertionError("nao devia consultar")
        R = {"ops": {"AAA": op_aberta(stop_ok=NOW - 600), "BBB": {"estado": "pendente", "inst": "x"}}, "hist": []}
        with mock.patch.object(E, "privado", privado):
            E.confirmar_stops(R, NOW, [])


if __name__ == "__main__":
    unittest.main()
