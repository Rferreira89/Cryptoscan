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
