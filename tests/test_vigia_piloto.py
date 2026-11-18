"""(18/11) O vigia passa a ver o piloto real da OKX, que tem estado proprio (piloto_publico.json)."""
import json
import os
import tempfile
import unittest
from unittest import mock

from tools import vigia as V

NOW = 2_000_000


def op(**kw):
    return {"id": "e|RENDER|1", "base": "RENDER", "estado": "aberta", "stop_confirmado": True, "stop_estado": "confirmado",
            "t_ordem": NOW - 3600, "t_execucao": NOW - 3600, **kw}


def st(*ops, t=NOW - 600, eventos=(), operacional=True):
    return {"t": t, "operacional": operacional, "ops": list(ops), "eventos": list(eventos)}


def chaves(d):
    return [k for k, _ in V.problemas_piloto(d, NOW)]


class Piloto(unittest.TestCase):
    def test_tudo_bem_nao_avisa(self):
        self.assertEqual(chaves(st(op())), [])
        self.assertEqual(chaves(st(op(estado="fechada", stop_confirmado=False))), [])
        self.assertEqual(chaves({}), [])

    def test_batimento(self):
        self.assertEqual(chaves(st(t=NOW - 3 * 3600)), ["piloto-batimento"])
        self.assertEqual(chaves(st(t=NOW - 3 * 3600, operacional=False)), [])      # desligado e sem posicao
        out = V.problemas_piloto(st(op(), t=NOW - 3 * 3600, operacional=False), NOW)
        self.assertEqual([k for k, _ in out], ["piloto-batimento"])                # desligado mas com posicao
        self.assertIn("RENDER", out[0][1])

    def test_stop_em_falta_avisa_logo(self):
        for est in ("inexistente", "lado_errado", "quantidade_insuficiente"):
            out = V.problemas_piloto(st(op(stop_confirmado=False, stop_estado=est)), NOW)
            self.assertEqual([k for k, _ in out], ["piloto-stop-RENDER"])
            self.assertIn(est, out[0][1])

    def test_sem_resposta_so_com_duas_voltas(self):
        o = op(stop_confirmado=False, stop_estado="sem_resposta")
        e = {"t": NOW - 600, "txt": "STOP POR CONFIRMAR: a OKX nao respondeu"}
        velho = {"t": NOW - 6 * 3600, "txt": e["txt"]}
        self.assertEqual(chaves(st(o, eventos=[velho, e])), [])
        self.assertEqual(chaves(st(o, eventos=[{**e, "t": NOW - 2400}, e])), ["piloto-stop-RENDER"])

    def test_fecho_preso(self):
        o = op(estado="a fechar", t_execucao=NOW - 9 * 3600)
        pedido = {"t": NOW - 1200, "txt": "fecho pedido (tempo); confirmo na volta seguinte", "op": o["id"]}
        self.assertEqual(chaves(st(o, eventos=[pedido])), [])
        self.assertEqual(chaves(st(o, eventos=[{**pedido, "t": NOW - 4 * 3600}])), ["piloto-fecho-RENDER"])
        self.assertEqual(chaves(st(o, eventos=[{**pedido, "t": NOW - 4 * 3600, "op": "outra"}])), ["piloto-fecho-RENDER"])
        self.assertEqual(chaves(st(o, eventos=[{"t": NOW - 600, "txt": "LIMITE ATINGIDO"}])), [])

    def test_ordem_presa(self):
        self.assertEqual(chaves(st(op(estado="pendente", t_ordem=NOW - 600))), [])
        self.assertEqual(chaves(st(op(estado="pendente", t_ordem=NOW - 3 * 3600))), ["piloto-presa-RENDER"])

    def test_parado_nao_conclui_do_estado_velho(self):
        o = op(stop_confirmado=False, stop_estado="inexistente")
        self.assertEqual(chaves(st(o, t=NOW - 3 * 3600)), ["piloto-batimento"])

    def test_mensagens_sem_valores_da_conta(self):
        o = op(stop_confirmado=False, stop_estado="inexistente", estado="a fechar", t_execucao=NOW - 9 * 3600)
        for _, m in V.problemas_piloto(st(o), NOW):
            self.assertNotRegex(m, r"USD")


class Main(unittest.TestCase):
    def _corre(self, piloto):
        okx = {"resumo": {"t": NOW - 600}}
        def abrir(url, timeout=0):
            if "piloto-okx" in url:
                if piloto is None:
                    raise OSError("sem rede")
                d = piloto
            else:
                d = okx if "/okx/" in url else {}
            return mock.Mock(read=lambda: json.dumps(d).encode())
        enviados = []
        with tempfile.TemporaryDirectory() as td, mock.patch.object(V, "MEM", os.path.join(td, "m.json")), \
                mock.patch.object(V.time, "time", return_value=NOW), mock.patch.object(V, "telegram", enviados.append), \
                mock.patch.object(V.urllib.request, "urlopen", abrir):
            self.assertEqual(V.main(), 0)
            V.main()                                             # segunda volta: nao repete o aviso
        return enviados

    def test_avisa_uma_vez(self):
        self.assertEqual(len(self._corre(st(op(stop_confirmado=False, stop_estado="inexistente")))), 1)

    def test_sem_ficheiro_do_piloto_nao_falha(self):
        self.assertEqual(self._corre(None), [])


if __name__ == "__main__":
    unittest.main()
