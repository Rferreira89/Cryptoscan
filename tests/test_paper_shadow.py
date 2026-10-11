import unittest

from engine import arena, paper_shadow as P

TF = 14400


def bars(n=60, t0=1_800_000_000 // TF * TF, p=10.0):
    return [{"t": t0 + i * TF, "o": p, "h": p * 1.01, "l": p * 0.99, "c": p, "v": 1}
            for i in range(n)]


def row(asset="AAA", price=10.0, reason="confluência 58/100 abaixo do mínimo 65",
        state="READY", strategy="PULLBACK"):
    return {"asset": asset, "price": price, "decision": {
        "decision": "WATCHLIST", "state": state, "strategy": strategy, "reason": reason,
        "plan": {"entry_zone": [9.9, 10.05], "stop": 9.5, "tp": [10.6, 11.0, 11.5],
                 "partials": [50, 50, 0]}}}


class Shadow(unittest.TestCase):
    def test_so_setups_prontos_recusados_pelos_filtros(self):
        self.assertIsNotNone(P.candidate(row()))
        self.assertIsNone(P.candidate(row(state="WAITING")))
        self.assertIsNone(P.candidate(row(reason="volume baixo na Bybit UE")))
        self.assertIsNone(P.candidate(row(price=10.5)))          # fora da zona
        self.assertIsNone(P.candidate(row(strategy="PULLBACK_SHORT")))
        self.assertIsNotNone(P.candidate(row(reason="limite de operações em simultâneo atingido")))

    def test_abre_segue_e_entra_na_arena(self):
        st, c4 = {}, bars()
        now = c4[-1]["t"] + TF + 60
        res = P.update(st, [row()], {"AAA": c4}, now)
        self.assertEqual(res["open"], ["AAA"])
        up = [{"t": c4[-1]["t"] + TF * k, "o": 10.0, "h": 11.6, "l": 9.9, "c": 11.4, "v": 1}
              for k in (1, 2)]
        res = P.update(st, [], {"AAA": c4 + up}, now + 3 * TF)
        self.assertEqual(res["n"], 1)
        self.assertGreater(res["total_r"], 0)
        ks = [k for k, _, _ in arena.trades(st)]
        self.assertIn("REJEITADOS", ks)


if __name__ == "__main__":
    unittest.main()
