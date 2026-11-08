"""(08/11) O macro so pede velas diarias a quem ainda nao tem a vela de ontem (as decisoes so mudam com vela nova)."""
import unittest
from unittest import mock
from tools import okx_macro as M

AGORA = 1794111855                       # 08/11/2026 04:24 UTC
ONTEM = AGORA // 86400 * 86400 - 86400   # abertura da vela diaria de 07/11


def velas(n, ultimo=ONTEM, sobe=True):
    return [{"t": ultimo - 86400 * (n - 1 - i), "c": (100 + i) if sobe else (200 - i)} for i in range(n)]


class VelaDiaria(unittest.TestCase):
    def correr(self, st, lista, dados):
        pedidos = []

        def diario(inst):
            pedidos.append(inst)
            return dados.get(inst, [])
        with mock.patch.object(M, "contratos", return_value=lista), mock.patch.object(M, "diario", side_effect=diario), \
                mock.patch.object(M.time, "sleep"), mock.patch.object(M.time, "time", return_value=AGORA):
            msgs = M.correr(st)
        return pedidos, msgs

    def test_segunda_volta_do_dia_nao_pede_nada(self):
        lista = {"KO": "KO-USDT-SWAP", "NOVA": "NOVA-USDT-SWAP"}
        dados = {"KO-USDT-SWAP": velas(80), "NOVA-USDT-SWAP": velas(10)}
        st = {}
        p1, m1 = self.correr(st, lista, dados)
        self.assertEqual(sorted(p1), ["KO-USDT-SWAP", "NOVA-USDT-SWAP"])
        self.assertIn("KO", st["macro"]["abertas"])
        r1 = dict(st["macro"]["resumo"])
        p2, m2 = self.correr(st, lista, dados)
        self.assertEqual(p2, [])                              # zero pedidos repetidos
        self.assertEqual(m2, [])                              # sem mensagens repetidas
        self.assertEqual(st["macro"]["resumo"], r1)           # mesmas contagens (analisados 1, sem historico 1)
        self.assertEqual((r1["analisados"], r1["sem_historico"]), (1, 1))

    def test_vela_antiga_ou_api_em_baixo_volta_a_pedir(self):
        lista = {"KO": "KO-USDT-SWAP", "X": "X-USDT-SWAP"}
        st = {"macro": {"abertas": {}, "fechadas": [], "ultimo": {"KO": ONTEM - 86400}}}
        p, _ = self.correr(st, lista, {"KO-USDT-SWAP": velas(80)})    # X: API devolve vazio
        self.assertEqual(sorted(p), ["KO-USDT-SWAP", "X-USDT-SWAP"])
        p, _ = self.correr(st, lista, {"KO-USDT-SWAP": velas(80)})
        self.assertEqual(p, ["X-USDT-SWAP"])                  # sem dados -> tenta outra vez na volta seguinte

    def test_saida_continua_a_acontecer_com_vela_nova(self):
        lista = {"KO": "KO-USDT-SWAP"}
        st = {"macro": {"abertas": {"KO": {"t": ONTEM - 86400 * 5, "entrada": 150.0}}, "fechadas": [],
                        "ultimo": {"KO": ONTEM - 86400}}}
        p, msgs = self.correr(st, lista, {"KO-USDT-SWAP": velas(80, sobe=False)})
        self.assertEqual(p, ["KO-USDT-SWAP"])
        self.assertNotIn("KO", st["macro"]["abertas"])
        self.assertEqual(len(st["macro"]["fechadas"]), 1)

    def test_curtos_de_contratos_que_sairam_sao_limpos(self):
        st = {"macro": {"abertas": {}, "fechadas": [], "ultimo": {}, "curtos": {"VELHA": ONTEM}}}
        self.correr(st, {"KO": "KO-USDT-SWAP"}, {"KO-USDT-SWAP": velas(10)})
        self.assertEqual(st["macro"]["curtos"], {"KO": ONTEM})
        self.correr(st, {}, {})                               # API em baixo: lista vazia nao apaga
        self.assertEqual(st["macro"]["curtos"], {"KO": ONTEM})


if __name__ == "__main__":
    unittest.main()
