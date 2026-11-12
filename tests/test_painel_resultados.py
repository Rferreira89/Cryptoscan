"""(12/11) Painel: real so com execucao, papel separado, perdidas por motivo."""
import unittest

from tools import painel_resultados as P


class Painel(unittest.TestCase):
    def test_real_sem_execucao_fica_a_parte(self):
        St = {"ledger": [{"status": "CLOSED", "mode": "REAL", "executed": True, "result_r": 1.3, "strategy": "S", "closed_at": 1},
                         {"status": "CLOSED", "mode": "REAL", "executed": False, "result_r": 0.5, "strategy": "S", "closed_at": 2},
                         {"status": "CLOSED", "mode": "PAPER", "result_r": -1.0, "strategy": "S", "closed_at": 3}],
              "promo_lost": [{"strategy": "S", "reason": "plano: x", "t": 1, "asset": "A"},
                             {"strategy": "S", "reason": "plano: y", "t": 2, "asset": "B"}]}
        b = P.bybit(St)
        self.assertEqual(b["operacoes"]["REAL | S"]["n"], 1)
        self.assertEqual(b["operacoes"]["REAL_SEM_EXECUCAO (nao conta) | S"]["n"], 1)
        self.assertEqual(b["operacoes"]["PAPER | S"]["soma_r"], -1.0)
        self.assertEqual(b["oportunidades_perdidas"][0], {"estrategia": "S", "motivo": "plano", "n": 2})

    def test_okx_real_e_papel(self):
        O = {"real": {"hist": [{"estado": "fechada", "entrada": 10, "stop": 9, "saida": 8},
                               {"estado": "cancelada"}]}, "fechadas": [{"tipo": "mercado", "r": 0.3}]}
        o = P.okx(O)
        self.assertEqual(o["real_h40_h46_bruto"]["soma_r"], -2.0)
        self.assertEqual(o["ordens_sem_execucao"], {"cancelada": 1})
        self.assertEqual(o["papel_h40"]["mercado"]["n"], 1)

    def test_metricas(self):
        m = P.metricas([1, -1, -1, 2])
        self.assertEqual((m["pf"], m["max_dd_r"]), (1.5, -2.0))


if __name__ == "__main__":
    unittest.main()


class Decisoes(unittest.TestCase):
    def test_estrategia_real_negativa_sinalizada(self):
        led = [{"status": "CLOSED", "mode": "REAL", "executed": True, "result_r": -1.0, "strategy": "X", "closed_at": i,
                "side": "LONG"} for i in range(5)]
        r = P.correr.__wrapped__ if hasattr(P.correr, "__wrapped__") else None
        b = P.bybit({"ledger": led})
        self.assertEqual(b["real_por_lado"]["LONG"]["n"], 5)
        d = P.decisoes({"bybit_ue": b, "okx": P.okx({})})
        self.assertTrue(any("REAL | X" in x for x in d))
