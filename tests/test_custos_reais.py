import unittest

from tools import custos_reais as C


class TestCustosReais(unittest.TestCase):
    def test_ida_volta(self):
        self.assertAlmostEqual(C.ida_volta(0.25, 0.14), 0.64)
        self.assertAlmostEqual(C.ida_volta(0.25, 0.0, 0.1), 0.7)        # o valor da investigacao

    def test_comissao_oficial_bybit(self):
        self.assertEqual(C.COMISSOES["bybit_ue_spot"]["taker"], 0.25)
        self.assertAlmostEqual(C.resumo.__globals__["DESLIZE_INVESTIGACAO"], 0.1)

    def test_operacoes_bybit(self):
        st = {"ledger": [
            {"status": "CLOSED", "entry": 100.0, "stop": 95.0, "asset": "AAA", "side": "LONG", "executed": True,
             "exec_price": 100.1, "result_r": -1.0, "strategy": "X"},
            {"status": "CLOSED", "entry": 100.0, "stop": 110.0, "asset": "BBB", "side": "SHORT", "executed": True,
             "exec_price": 99.9, "result_r": 0.5, "strategy": "Y"},
            {"status": "CANCELLED", "entry": 1.0, "stop": 0.9, "asset": "C"}]}
        ops = C.bybit_operacoes(st, {"AAA": 0.2, "BBB": 0.0})
        self.assertEqual(len(ops), 2)
        self.assertAlmostEqual(ops[0]["deslize_entrada_pct"], 0.1)
        self.assertAlmostEqual(ops[1]["deslize_entrada_pct"], 0.1)      # short vendido abaixo = contra
        self.assertAlmostEqual(ops[0]["custo_r"], 0.7 / 5.0, places=3)


if __name__ == "__main__":
    unittest.main()
