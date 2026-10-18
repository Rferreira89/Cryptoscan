import unittest

from engine import risco

T = risco.DESDE + 100


def op(i, r, strat="BOUNCE_X30", t=None):
    return {"id": f"o{i}", "kind": "4H", "strategy": strat, "executed": True, "status": "CLOSED",
            "closed_at": (t or T) + i, "result_r": r, "stop": 1, "entry": 2}


class NivelDeRisco(unittest.TestCase):
    def test_reduzido_ate_a_prova(self):
        st = {"ledger": [op(i, 1.0) for i in range(4)]}
        n = risco.nivel(st, 222)
        self.assertTrue(n["reduzido"])
        self.assertIn("4/5", n["motivo"])
        st["ledger"].append(op(9, -1.0))
        n = risco.nivel(st, 222)
        self.assertFalse(n["reduzido"])
        self.assertTrue(n["mudou"])
        self.assertIn("NORMAL", risco.aviso(n))
        self.assertFalse(risco.nivel(st, 222)["mudou"])

    def test_nao_contam_classicas_nem_antigas_nem_nao_executadas(self):
        led = [op(1, 1.0, "PULLBACK"), op(2, 1.0, t=risco.DESDE - 10**5),
               dict(op(3, 1.0), executed=False)] + [op(i, 0.5) for i in range(10, 14)]
        self.assertEqual(risco.prova(led), (4, 2.0))

    def test_prova_falhada_fica_reduzido(self):
        st = {"ledger": [op(i, -0.5) for i in range(5)] + [op(9, 3.0)]}
        n = risco.nivel(st, 222)
        self.assertTrue(n["reduzido"])
        self.assertIn("falhou", n["motivo"])

    def test_travao_aos_10_por_cento(self):
        st = {"ledger": [op(i, 1.0) for i in range(5)]}
        self.assertFalse(risco.nivel(st, 300)["reduzido"])
        self.assertFalse(risco.nivel(st, 275)["reduzido"])
        n = risco.nivel(st, 269)
        self.assertTrue(n["reduzido"])
        self.assertIn("travão", n["motivo"])
        self.assertIn("REDUZIDO", risco.aviso(n))
        self.assertFalse(risco.nivel(st, 301)["reduzido"])      # recuperou o maximo


if __name__ == "__main__":
    unittest.main()
