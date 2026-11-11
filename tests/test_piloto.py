"""(11/11) Guarda do piloto (preparacao, nao ligada): so conta operacoes reais executadas; suspende por perda
acumulada, perda diaria e juro; decide ao fim de 30. Sem ligacao ao executor."""
import inspect
import unittest

from engine import piloto as P

DAY = 86400


def op(r, dia, executed=True, est="SHORT_TURTLE", mode="REAL"):
    return {"strategy": est, "mode": mode, "status": "CLOSED", "executed": executed, "result_r": r,
            "closed_at": 1000 * DAY + dia * DAY, "opened_at": 1000 * DAY + dia * DAY - 3600}


class Guarda(unittest.TestCase):
    def test_nao_conta_o_que_nao_executou_nem_papel_nem_antes_do_inicio(self):
        rows = [op(0.5, 1, executed=False), op(0.47, 2, mode="PAPER"), op(-1.0, -5), op(1.3, 3), op(0.2, 4, est="X")]
        a = P.avaliar(rows, "SHORT_TURTLE", 1000 * DAY)
        self.assertEqual(a["n"], 1)
        self.assertAlmostEqual(a["soma_r"], 1.3)
        self.assertTrue(a["pode_abrir"])

    def test_perda_acumulada_suspende(self):
        rows = [op(-1.0, d) for d in range(10)]
        a = P.avaliar(rows, "SHORT_TURTLE", 0)
        self.assertFalse(a["pode_abrir"])
        self.assertEqual(a["estado"], "suspenso")

    def test_perda_num_dia_suspende(self):
        a = P.avaliar([op(-1.0, 1), op(-1.0, 1), op(-1.05, 1)], "SHORT_TURTLE", 0)
        self.assertFalse(a["pode_abrir"])

    def test_juro_real_acima_suspende(self):
        a = P.avaliar([op(0.5, 1)], "SHORT_TURTLE", 0, juros_r=[0.1, 0.08])
        self.assertFalse(a["pode_abrir"])

    def test_decisao_aos_30(self):
        bom = [op(0.6 if d % 2 else -0.4, d) for d in range(30)]
        self.assertEqual(P.avaliar(bom, "SHORT_TURTLE", 0)["estado"], "decidir (continuar ou alterar com o Rui)")
        mau = [op(-0.3 if d % 3 else 0.5, d) for d in range(30)]
        r = P.avaliar(mau, "SHORT_TURTLE", 0)
        self.assertEqual(r["estado"], "terminar")
        self.assertFalse(r["pode_abrir"])

    def test_nao_esta_ligada(self):
        from engine import executor, promo, scanner
        for m in (executor, promo, scanner):
            self.assertNotIn("piloto", inspect.getsource(m))
        src = inspect.getsource(P)
        for proibido in ("urlopen", "/v5/order", "privado(", "place"):
            self.assertNotIn(proibido, src)


if __name__ == "__main__":
    unittest.main()
