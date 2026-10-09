import random
import unittest

from engine import confluence, inbox, run
from tools import random_baseline as RB


class StructureWarnings(unittest.TestCase):
    def test_ena_case(self):
        a1 = {"event": {"type": "CHOCH", "direction": "DOWN", "bars_ago": 1}}
        a4 = {"event": {"type": "BOS", "direction": "DOWN", "bars_ago": 4}}
        w = confluence.structure_warnings(a4, a1)
        self.assertEqual(len(w), 2)
        self.assertIn("mudança de estrutura contra a operação no diário", w[0])
        self.assertIn("há 1 vela)", w[0])
        self.assertIn("quebra de estrutura contra a operação no 4H", w[1])

    def test_old_or_favourable_events_ignored(self):
        up = {"event": {"type": "BOS", "direction": "UP", "bars_ago": 0}}
        old4 = {"event": {"type": "BOS", "direction": "DOWN", "bars_ago": 7}}
        old1 = {"event": {"type": "CHOCH", "direction": "DOWN", "bars_ago": 4}}
        self.assertEqual(confluence.structure_warnings(up, up), [])
        self.assertEqual(confluence.structure_warnings(old4, old1), [])
        self.assertEqual(confluence.structure_warnings({}, None), [])

    def test_shown_in_telegram(self):
        s = {"warnings": ["quebra de estrutura contra a operação no 4H "
                          "(na última vela)"]}
        self.assertIn("⚠️ Atenção: quebra", run.warn_line(s))
        self.assertEqual(run.warn_line({}), "")


class SlipNote(unittest.TestCase):
    def test_worse_long_entry(self):
        r = {"side": "LONG", "entry": 0.24565, "stop": 0.24313,
             "position_usdc": 25.0}
        t = inbox.slip_note(r, 0.247, fee_pct=0.25)
        self.assertIn("0.55% acima", t)
        self.assertIn("vender", t)
        self.assertEqual(inbox.slip_note(r, 0.2457, fee_pct=0.25), "")

    def test_short_and_wrong_side(self):
        r = {"side": "SHORT", "entry_zone": [100, 101], "stop": 104,
             "position_usdc": 30.0}
        self.assertIn("recomprar", inbox.slip_note(r, 99.5, fee_pct=0.25))
        self.assertIn("lado errado", inbox.slip_note(r, 105, fee_pct=0.25))

    def test_reply_includes_note(self):
        st = {"ledger": [{"id": "x", "asset": "ENA", "status": "OPEN",
                          "side": "LONG", "entry": 0.24565, "stop": 0.24313,
                          "position_usdc": 25.0}]}
        msg = {"message": {"chat": {"id": 7}, "text": "/preco ENA 0,247",
                           "date": 1}}
        out = inbox.apply(st, [msg], 7)
        self.assertIn("Atenção", out[0][0])


def bars(prices, t0=0):
    return [{"t": t0 + i * 14400, "o": p, "h": p * 1.001, "l": p * 0.999,
             "c": p, "v": 1} for i, p in enumerate(prices)]


class RandomBaseline(unittest.TestCase):
    GEO = {"stop": -0.05, "tp": [0.10, 0.15, 0.20], "partials": [50, 50, 0]}

    def test_control_hits_target_or_stop(self):
        up = bars([100 + i for i in range(60)])
        self.assertGreater(RB.control_trade(up, 0, self.GEO, "LONG", 0.25), 0)
        down = bars([100 - i for i in range(60)])
        self.assertLess(RB.control_trade(down, 0, self.GEO, "LONG", 0.25), 0)

    def test_no_look_ahead(self):
        # o resultado de uma entrada na vela j nao pode mudar com velas
        # anteriores a j
        a = bars([100] * 10 + [100 + i for i in range(60)])
        b = bars([50] * 10 + [100 + i for i in range(60)])
        self.assertEqual(RB.control_trade(a, 10, self.GEO, "LONG", 0.25),
                         RB.control_trade(b, 10, self.GEO, "LONG", 0.25))

    def test_geometry_both_sides(self):
        g = RB.geometry({"entry_zone": [99, 100], "stop": 95,
                         "tp": [110, 115, 120], "partials": [50, 50, 0]}, "LONG")
        self.assertAlmostEqual(g["stop"], -0.05)
        g = RB.geometry({"entry_zone": [100, 101], "stop": 105,
                         "tp": [90, 85, 80], "partials": [50, 50, 0]}, "SHORT")
        self.assertAlmostEqual(g["stop"], 0.05)
        self.assertAlmostEqual(g["tp"][0], -0.10)

    def test_run_reports_percentile(self):
        up = bars([100 + i * 0.5 for i in range(400)])
        prepared = [("X", "LONG", 50 + k, self.GEO, 1.0, "S") for k in range(5)]
        res = RB.run(prepared, {"X": up}, 0.25, reps=20, window=20)
        self.assertIn("TODAS", res)
        self.assertEqual(res["S"]["n"], 5)
        self.assertTrue(0 <= res["S"]["percentil"] <= 100)


if __name__ == "__main__":
    unittest.main()
