"""(17/11, alteracao cirurgica autorizada pelo Rui) o executor OKX antigo nunca adota, gere, fecha nem abre por cima de
posicoes/ordens do piloto ("pil"); e continua a adotar as suas (comportamento anterior intacto)."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import okx_exec as E  # noqa: E402
import piloto_id as PID  # noqa: E402

NOW = 2_000_000_000
INST = "AAA-USD_UM_XPERP-1"


class Conta:
    """OKX falsa so com o que reconciliar/abrir usam. algos/fills/pend: listas por instrumento."""
    def __init__(self, pos=None, algos=(), fills=(), pend=(), falha=()):
        self.p, self.algos, self.fills, self.pend, self.falha = pos, list(algos), list(fills), list(pend), set(falha)
        self.posts = []

    def __call__(self, metodo, path, corpo=None):
        base = path.split("?")[0].rsplit("/", 1)[-1]
        if metodo == "POST":
            self.posts.append((path, corpo))
            return {"code": "0", "data": [{"sCode": "0", "ordId": "1"}]}
        if base in self.falha:
            return {"code": "50001", "data": []}
        if base == "positions":
            return {"code": "0", "data": [self.p] if self.p else []}
        if base == "orders-algo-pending":
            return {"code": "0", "data": self.algos if "oco" in path else []}
        if base == "orders-pending":
            return {"code": "0", "data": self.pend}
        if base in ("fills", "fills-history"):
            return {"code": "0", "data": self.fills}
        raise AssertionError(path)


def pos(**k):
    return {"instId": INST, "pos": "5", "avgPx": "1.0", "cTime": str(NOW * 1000 - 3600_000), "lever": "5", **k}


class Reconciliar(unittest.TestCase):
    def correr(self, conta):
        R, msgs = {"ops": {}, "hist": []}, []
        with mock.patch.object(E, "privado", conta):
            E.reconciliar(R, NOW, msgs)
        return R, msgs

    def test_posicao_do_piloto_pelo_stop_nao_e_adotada(self):
        c = Conta(pos(), algos=[{"instId": INST, "algoClOrdId": "pilabcslt", "slTriggerPx": "0.9", "side": "sell", "sz": "5"}])
        R, msgs = self.correr(c)
        self.assertEqual(R["ops"], {})
        self.assertEqual(c.posts, [])

    def test_posicao_do_piloto_pela_execucao_nao_e_adotada(self):
        c = Conta(pos(), fills=[{"instId": INST, "clOrdId": "pilabc", "ts": str(NOW * 1000 - 3000_000)}])
        R, _ = self.correr(c)
        self.assertEqual(R["ops"], {})
        self.assertEqual(c.posts, [])

    def test_sem_resposta_da_okx_nao_adota(self):
        for f in ("orders-algo-pending", "fills", "orders-pending"):
            c = Conta(pos(), falha=(f,))
            R, msgs = self.correr(c)
            self.assertEqual(R["ops"], {}, f)
            self.assertEqual(c.posts, [], f)
            self.assertTrue(any("não confirmou a origem" in m for m in msgs), f)

    def test_posicao_propria_continua_a_ser_adotada(self):
        c = Conta(pos(), fills=[{"instId": INST, "clOrdId": "csAAA1", "ts": str(NOW * 1000 - 3000_000)}])
        R, msgs = self.correr(c)
        self.assertIn("AAA", R["ops"])
        self.assertTrue(R["ops"]["AAA"]["adotada"])

    def test_execucao_antiga_do_piloto_antes_da_posicao_nao_conta(self):
        c = Conta(pos(), fills=[{"instId": INST, "clOrdId": "pilantigo", "ts": str(NOW * 1000 - 90000_000)},
                                {"instId": INST, "clOrdId": "csAAA1", "ts": str(NOW * 1000 - 3000_000)}])
        R, _ = self.correr(c)
        self.assertIn("AAA", R["ops"])


class Abrir(unittest.TestCase):
    PLANO = {"alav": 5, "px_s": "1", "sz_s": "1", "alvo_s": "1.2", "stop_s": "0.9", "nominal": 1, "risco_usd": 0.1,
             "lim": 1.0, "stop": 0.9, "alvo": 1.2}

    def abrir(self, conta):
        msgs = []
        with mock.patch.object(E, "privado", conta), mock.patch.object(E, "plano", return_value=dict(self.PLANO)):
            op = E.abrir("AAA", {"t_sig": NOW}, {"inst": INST}, 100.0, {}, NOW, msgs)
        return op, msgs

    def test_nao_abre_por_cima_do_piloto(self):
        for c in (Conta(pos(), algos=[{"instId": INST, "algoClOrdId": "pilxslt", "slTriggerPx": "0.9"}]),
                  Conta(None, pend=[{"instId": INST, "clOrdId": "pilx"}]),
                  Conta(None, falha=("positions",))):
            op, msgs = self.abrir(c)
            self.assertIsNone(op)
            self.assertEqual(c.posts, [])
            self.assertIn("piloto", msgs[-1])

    def test_abre_normalmente_sem_piloto(self):
        c = Conta(None, fills=[{"instId": INST, "clOrdId": "pilfechada", "ts": "1"}])   # posicao do piloto ja fechada
        op, _ = self.abrir(c)
        self.assertIsNotNone(op)
        self.assertEqual([p for p, _ in c.posts], ["/api/v5/account/set-leverage", "/api/v5/trade/order"])
        self.assertTrue(op["clOrdId"].startswith("cs"))


class Identificacao(unittest.TestCase):
    def test_declaracao_e_prefixos_distintos(self):
        self.assertTrue(E.PILOTO_ISOLADO)
        self.assertEqual(PID.PREFIXO, "pil")
        src = open(E.__file__, encoding="utf-8").read()
        self.assertIn('cl = f"cs{base[:8]}', src)                    # o executor antigo nunca usa o prefixo do piloto


if __name__ == "__main__":
    unittest.main()
