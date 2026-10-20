import unittest
from engine import evolucao as E

H = 3600


def nuc(q, px, res=0.0):
    return {"pos": {"BTC": {"qty": q}}, "plano": {"BTC": {"preco": px, "resultado_usdc": res}}}


class Evolucao(unittest.TestCase):
    def led(self):
        return [{"mode": "REAL", "executed": True, "status": "CLOSED", "closed_at": 100, "real_r": -1.0, "risk_usdc": 2.0, "id": "a"},
                {"mode": "REAL", "executed": True, "status": "CLOSED", "closed_at": 200, "result_r": 2.0, "risk_usdc": 1.0, "id": "b"},
                {"mode": "REAL", "executed": False, "status": "CLOSED", "closed_at": 300, "result_r": 5.0, "risk_usdc": 1.0},
                {"mode": "REAL", "executed": True, "status": "OPEN", "risk_usdc": 1.0}]

    def test_comeca_com_o_resultado_das_operacoes_fechadas(self):
        st = {}
        ev = E.atualizar(st, 200, 1000, self.led(), nuc(1, 100, 0.5))
        self.assertEqual(ev["hist"], [[100, -2.0], [200, 0.0]])
        self.assertAlmostEqual(ev["g"], 0.5)
        E.atualizar(st, 210, 1000 + 60, self.led(), nuc(1, 110))     # menos de uma hora: nada
        self.assertEqual(len(st["evolucao"]["pts"]), 1)

    def test_mercado_conta_como_ganho_deposito_nao(self):
        st = {}
        E.atualizar(st, 200, 0, [], nuc(1, 100))
        E.atualizar(st, 210, H, [], nuc(1, 110))            # BTC +10: ganho
        self.assertAlmostEqual(st["evolucao"]["g"], 10)
        E.atualizar(st, 310, 2 * H, [], nuc(1, 110))        # +100 sem mercado: deposito
        self.assertAlmostEqual(st["evolucao"]["g"], 10)
        self.assertEqual(st["evolucao"]["fluxos"], [[2 * H, 100.0]])
        E.atualizar(st, 311.5, 3 * H, [], nuc(1, 110))      # pequena variacao das operacoes: ganho
        self.assertAlmostEqual(st["evolucao"]["g"], 11.5)
        r = E.resumo(st["evolucao"], 311.5, 3 * H)
        self.assertEqual(r["investido"], 300.0)
        self.assertAlmostEqual(r["pct"], 11.5 / 300 * 100, 2)
        self.assertEqual(r["periodos"], {})                  # ainda sem um dia de registo
        self.assertEqual(r["serie"][-1], [3 * H, 11.5])

    def test_vender_o_nucleo_nao_e_deposito(self):
        st = {}
        E.atualizar(st, 200, 0, [], nuc(1, 100, 20))
        E.atualizar(st, 200, H, [], {"pos": {}, "plano": {"BTC": {"preco": 100}}})
        self.assertEqual(st["evolucao"]["fluxos"], [])

    def test_sem_capital_nao_faz_nada(self):
        self.assertEqual(E.atualizar({}, None, 0), {})
        self.assertIsNone(E.resumo({}))


if __name__ == "__main__":
    unittest.main()


class Periodos(unittest.TestCase):
    def test_percentagem_do_dia(self):
        st = {}
        E.atualizar(st, 200, 0, [], nuc(1, 100))
        for i in range(1, 26):
            E.atualizar(st, 200 + i, i * H, [], nuc(1, 100))
        r = E.resumo(st["evolucao"], 225, 25 * H)
        self.assertAlmostEqual(r["periodos"]["dia"], 24 / 200 * 100, 2)
