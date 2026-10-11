import unittest

from engine import rewards, run


def led(rs, executed=True, t=1_900_000_000):
    return [{"id": f"X{i}", "kind": "4H", "status": "CLOSED", "executed": executed,
             "result_r": r, "entry": 1.0, "stop": 0.9, "closed_at": t - i * 3600}
            for i, r in enumerate(rs)]


class Rewards(unittest.TestCase):
    def test_nada_sem_conquistas(self):
        out, ev = rewards.update({"ledger": led([-1, -1])}, {}, 1_900_000_000)
        self.assertEqual(ev, [])
        self.assertFalse(any(x["unlocked"] for x in out))

    def test_primeira_vitoria_desbloqueia_e_fica(self):
        st = {"ledger": led([0.8, -1])}
        out, ev = rewards.update(st, {}, 1_900_000_000)
        self.assertEqual([e["name"] for e in ev], ["Mesa de bilhar"])
        st["ledger"] = []                      # mesmo que o registo mude
        out, ev = rewards.update(st, {}, 1_900_000_100)
        self.assertEqual(ev, [])
        self.assertTrue(next(x for x in out if x["id"] == "WIN1")["unlocked"])

    def test_nao_executadas_nao_contam(self):
        out, ev = rewards.update({"ledger": led([2, 2, 2], executed=False)}, {},
                                 1_900_000_000)
        self.assertEqual(ev, [])

    def test_capital_arena_e_semana(self):
        res = {"config": {"capital_usdc": 90, "capital_base": 84},
               "arena": {"classificacao": [{"estado": "SOBE"}]}}
        out, ev = rewards.update({"ledger": led([0.5, 0.4])}, res, 1_900_000_000)
        names = {e["name"] for e in ev}
        self.assertEqual(names, {"Mesa de bilhar", "Troféu dourado",
                                 "Máquina de arcade", "Hall da Fama"})

    def test_mensagem(self):
        txt = run.alert_text({"event": "REWARD", "name": "Mesa de bilhar",
                              "cond": "x"}, {}, "")
        self.assertIn("desbloqueaste", txt)


if __name__ == "__main__":
    unittest.main()


class FecheiManual(unittest.TestCase):
    def test_fechei_registra_resultado_e_silencia(self):
        from engine import inbox, ledger
        st = {"ledger": [{"id": "ICP-1", "kind": "4H", "asset": "ICP", "status": "OPEN",
                          "executed": True, "exec_price": 3.01, "entry": 3.004,
                          "stop": 2.8316, "tp": [3.245, 3.609, 3.8005], "tp_hit": 1,
                          "risk_usdc": 1.53, "side": "LONG", "strategy": "LIQUIDITY_SWEEP"}],
              "signals": {"ICP-1": {"plan": {"partials": [50, 50, 0]}}}}
        upd = [{"message": {"chat": {"id": 7}, "date": 1_900_000_000,
                            "text": "/fechei ICP 3.20"}}]
        out = inbox.apply(st, upd, "7")
        rec = st["ledger"][0]
        self.assertAlmostEqual(rec["user_exit"], 3.20)
        # 50% a 3.245 e 50% a 3.20 com entrada a 3.01 e stop a 2.8316
        self.assertTrue(0.9 < rec["user_result_r"] < 1.3)
        self.assertIn("Registado", out[0][0])
        self.assertTrue(inbox.muted(st, {"event": "BREAKEVEN", "id": "ICP-1"}))
        self.assertEqual(rec["status"], "OPEN")          # o sinal continua
        m = ledger.summary(st["ledger"], executed_only=True)
        self.assertEqual(m["closed"], 1)
        self.assertGreater(ledger.realized_usdc(st["ledger"], 0), 0)
        out2, ev = rewards.update(st, {}, 1_900_000_100)
        self.assertIn("Mesa de bilhar", [e["name"] for e in ev])
