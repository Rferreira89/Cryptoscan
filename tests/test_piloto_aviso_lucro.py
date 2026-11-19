"""(19/11, desenho da acumulacao) Aviso de lucro realizado do piloto OKX para o Rui o passar (se quiser) para a Bybit:
so avisa, nunca transfere; conta so lucro confirmado na OKX; no maximo uma vez por semana; nunca no ficheiro publico."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import piloto_okx as P  # noqa: E402

C = {"capital_max": 20}
NOW = 1_800_000_000


def op(pnl, conf=True):
    o = {"estado": "fechada", "pnl_liquido": pnl}
    if not conf:
        o["pnl_por_confirmar"] = True
    return o


class AvisoLucro(unittest.TestCase):
    def test_comeca_do_zero_sem_contar_o_passado(self):
        st = {"ops": [op(50.0)], "_saldo_usdc": 100.0}
        msgs = []
        self.assertIsNone(P.aviso_lucro(st, C, NOW, msgs))
        self.assertEqual((st["lucro_aviso"]["base"], msgs), (50.0, []))

    def test_avisa_com_lucro_novo_e_nao_repete(self):
        st = {"ops": [op(1.0)], "_saldo_usdc": 100.0, "lucro_aviso": {"base": 1.0, "t": 0}}
        st["ops"].append(op(6.0))
        msgs = []
        self.assertEqual(P.aviso_lucro(st, C, NOW, msgs), 6.0)
        self.assertEqual(len(msgs), 1)
        self.assertIn("6.00 USDC", msgs[0])
        self.assertIn("nunca transfere", msgs[0])
        st["ops"].append(op(9.0))
        self.assertIsNone(P.aviso_lucro(st, C, NOW + 3600, msgs))                     # menos de uma semana
        self.assertEqual(P.aviso_lucro(st, C, NOW + P.LUCRO_AVISO_S, msgs), 9.0)       # so o lucro novo

    def test_abaixo_do_minimo_perdas_e_por_confirmar_nao_avisam(self):
        msgs = []
        st = {"ops": [op(3.0)], "lucro_aviso": {"base": 0.0, "t": 0}}
        self.assertIsNone(P.aviso_lucro(st, C, NOW, msgs))                             # abaixo de 5
        st = {"ops": [op(10.0), op(-8.0)], "lucro_aviso": {"base": 0.0, "t": 0}}
        self.assertIsNone(P.aviso_lucro(st, C, NOW, msgs))                             # a perda abate
        st = {"ops": [op(10.0), op(1.0, conf=False)], "lucro_aviso": {"base": 0.0, "t": 0}}
        self.assertIsNone(P.aviso_lucro(st, C, NOW, msgs))                             # resultado por confirmar
        self.assertEqual(msgs, [])

    def test_sem_folga_no_saldo_avisa_para_esperar(self):
        st = {"ops": [op(8.0)], "_saldo_usdc": 22.0, "lucro_aviso": {"base": 0.0, "t": 0}}
        msgs = []
        P.aviso_lucro(st, C, NOW, msgs)
        self.assertIn("não chega", msgs[0])

    def test_nao_vai_para_o_publico(self):
        src = open(P.__file__, encoding="utf-8").read()
        campos = src.split("def publico(st, c, aprovadas, now):")[1].split("oper =")[0]
        self.assertNotIn("lucro_aviso", campos)


if __name__ == "__main__":
    unittest.main()
