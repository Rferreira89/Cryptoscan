import unittest

from engine import arena, run

TF = 14400


def flat_bars(n=400, t0=1_800_000_000 // TF * TF, p=100.0, amp=0.03):
    out = []
    for i in range(n):
        q = p * (1 + amp * ((i % 20) - 10) / 10)
        out.append({"t": t0 + i * TF, "o": q, "h": q * 1.02, "l": q * 0.98,
                    "c": q, "v": 10})
    return out


def led(n, r, strategy="PULLBACK", t0=1_800_000_000 + 200 * TF):
    return [{"id": f"X{i}", "kind": "4H", "status": "CLOSED", "asset": "AAA",
             "strategy": strategy, "entry": 100.0, "stop": 95.0,
             "tp": [105.0, 110.0], "partials": [50, 50],
             "opened_at": t0 + i * 3600, "closed_at": t0 + i * 3600 + TF,
             "result_r": r, "side": "LONG"} for i in range(n)]


class Arena(unittest.TestCase):
    def test_regras(self):
        self.assertEqual(arena.verdict(10, -1.0, 0.0, 0.5, True), "A COMPETIR")
        self.assertEqual(arena.verdict(20, -0.3, 0.0, 0.5, True), "MORTA")
        self.assertEqual(arena.verdict(20, 0.1, 0.2, 0.5, True), "MORTA")
        self.assertEqual(arena.verdict(25, 0.6, 0.0, 0.5, True), "A COMPETIR")
        self.assertEqual(arena.verdict(30, 0.6, 0.0, 0.5, True), "SOBE")
        self.assertEqual(arena.verdict(30, 0.6, None, None, False), "A COMPETIR")

    def test_estrategia_que_perde_morre_e_avisa(self):
        st = {"ledger": led(22, -1.0)}
        bars = {"AAA": flat_bars()}
        for k in range(5):                    # controlos aos poucos por scan
            res = arena.update(st, bars, 1_900_000_000 + k, seed=1)
        row = next(b for b in res["classificacao"] if b["id"] == "PULLBACK")
        self.assertEqual(row["n"], 22)
        self.assertEqual(row["estado"], "MORTA")
        self.assertTrue(row["live"])
        # estrategia ao vivo morta nao entra na lista de papel a desligar
        self.assertNotIn("PULLBACK", arena.dead_paper(st))

    def test_aviso_so_na_mudanca(self):
        st = {"ledger": led(22, -1.0)}
        bars = {"AAA": flat_bars()}
        evs = []
        for k in range(6):
            res = arena.update(st, bars, 1_900_000_000 + k, seed=1)
            evs += arena.events(res, 1)
        self.assertEqual(len([e for e in evs if e["estado"] == "MORTA"]), 1)
        txt = run.alert_text(evs[0], {}, "")
        self.assertIn("morreu", txt)
        self.assertIn("opção B", txt)

    def test_papel_morto_deixa_de_abrir(self):
        st = {"arena": {"status": {"BOUNCE_V2": "MORTA", "BREAKOUT": "MORTA"}}}
        self.assertEqual(arena.dead_paper(st), {"BOUNCE_V2"})

    def test_controlos_sem_look_ahead_fora_do_historico(self):
        c4 = flat_bars(50)
        geo = {"stop": -0.05, "tp": [0.05], "partials": [100], "breakeven": False}
        import random
        rs = arena.control_rs(c4, c4[-1]["t"] + 10 * TF, geo, "LONG",
                              random.Random(1), reps=50)
        self.assertTrue(all(-1.2 < r < 1.2 for r in rs))


if __name__ == "__main__":
    unittest.main()
