import unittest

from engine import risco

T = risco.DESDE + 100


def op(i, r, strat="BOUNCE_X30", t=None):
    return {"id": f"o{i}", "kind": "4H", "strategy": strat, "executed": True, "status": "CLOSED",
            "issued_at": (t or T) + i, "closed_at": (t or T) + i, "result_r": r, "stop": 1, "entry": 2}


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


class Pedidos18Outubro(unittest.TestCase):
    def test_operacao_aberta_antes_da_decisao_nao_conta(self):
        pump = dict(op(1, -1.0), issued_at=risco.DESDE - 3 * 86400)   # aberta a 15/10, fechada depois
        self.assertEqual(risco.prova([pump]), (0, 0))

    def test_pausa_por_perdas_seguidas_desligada(self):
        from engine import signals
        mk = lambda i: {"id": f"s{i}", "status": "CLOSED", "mode": "REAL", "closed_at": 10**6 + i, "result_r": -1.0}
        sigs = {f"s{i}": mk(i) for i in range(3)}
        cfg = {"max_daily_loss_r": 9, "max_weekly_loss_r": 99, "cooldown_after_losses": 0}
        self.assertIsNone(signals.trading_halt(sigs, cfg, 10**6 + 100))
        self.assertIn("perdas seguidas", signals.trading_halt(sigs, dict(cfg, cooldown_after_losses=3), 10**6 + 100))
        self.assertIn("diária", signals.trading_halt(sigs, dict(cfg, max_daily_loss_r=3), 10**6 + 100))
