"""Operacoes marcadas "nao executei" nao ocupam vaga no limite."""
import unittest

from engine import ledger, signals
from tests.test_phase4 import C4, CFG, V, row

NOW = 1_800_000_000
CFG2 = dict(CFG, max_open_positions=2)


def rows(names):
    out = []
    for a in names:
        r = row(asset=a)
        r["decision"] = signals.decide(r, C4, CFG2, V, "BULL", False)
        out.append(r)
    return out


def scan(state, names, t):
    rs = rows(names)
    ev = signals.update_state(state, rs, CFG2, t)
    ledger.apply(state, ev)
    return rs, [e["id"] for e in ev if e["event"] == "ISSUED"]


class DeclinedSlots(unittest.TestCase):
    def test_limit_holds_without_reply(self):
        state = {}
        _, issued = scan(state, ["A0", "A1"], NOW)
        self.assertEqual(len(issued), 2)
        rs, issued = scan(state, ["A0", "A1", "A2"], NOW + 300)
        self.assertEqual(issued, [])
        self.assertIn("limite", rs[2]["decision"]["reason"])

    def test_declined_frees_one_slot_only(self):
        state = {}
        _, first = scan(state, ["A0", "A1"], NOW)
        rec = next(r for r in state["ledger"] if r["id"] == first[0])
        rec["executed"] = False                      # botao "Nao executei"
        rs, issued = scan(state, ["A0", "A1", "A2", "A3"], NOW + 300)
        self.assertEqual(len(issued), 1)             # so uma vaga libertada
        self.assertIn("limite", rs[3]["decision"]["reason"])
        # o sinal recusado continua vivo e a ser acompanhado em papel
        self.assertIn(state["signals"][first[0]]["status"],
                      ("ACTIVE", "TRIGGERED"))

    def test_executed_or_unanswered_keeps_slot(self):
        state = {}
        _, first = scan(state, ["A0", "A1"], NOW)
        next(r for r in state["ledger"]
             if r["id"] == first[0])["executed"] = True
        _, issued = scan(state, ["A0", "A1", "A2"], NOW + 300)
        self.assertEqual(issued, [])

    def test_declined_asset_gets_no_second_signal(self):
        state = {}
        _, first = scan(state, ["A0"], NOW)
        state["ledger"][0]["executed"] = False
        _, issued = scan(state, ["A0"], NOW + 300)
        self.assertEqual(issued, [])                 # uma operacao por ativo

    def test_declined_helper(self):
        st = {"ledger": [
            {"id": "a", "kind": "4H", "asset": "A", "executed": False},
            {"id": "b", "kind": "4H", "asset": "B", "executed": True},
            {"id": "c", "kind": "4H", "asset": "C"},
            {"id": "d", "kind": "1D", "asset": "D", "status": "OPEN",
             "executed": False},
            {"id": "e", "kind": "1D", "asset": "E", "status": "CLOSED",
             "executed": False}]}
        ids, trend = ledger.declined(st)
        self.assertEqual((ids, trend), ({"a", "d", "e"}, {"D"}))
        self.assertEqual(ledger.declined({}), (set(), set()))


if __name__ == "__main__":
    unittest.main()


class DailyReportDeclined(unittest.TestCase):
    def test_nao_executada_nao_aparece_como_em_curso(self):
        from engine import reports
        st = {"signals": {
                "ENA-X-1": {"id": "ENA-X-1", "asset": "ENA", "strategy": "LIQUIDITY_SWEEP",
                            "status": "TRIGGERED",
                            "position": {"stop": 0.19, "tp_hit": 0}},
                "ICP-X-2": {"id": "ICP-X-2", "asset": "ICP", "strategy": "LIQUIDITY_SWEEP",
                            "status": "TRIGGERED",
                            "position": {"stop": 2.83, "tp_hit": 0}}},
              "ledger": [{"id": "ENA-X-1", "asset": "ENA", "kind": "4H",
                          "status": "OPEN", "executed": False},
                         {"id": "ICP-X-2", "asset": "ICP", "kind": "4H",
                          "status": "OPEN", "executed": True}]}
        op, skip = reports._open_lines(st)
        self.assertEqual(len(op), 1)
        self.assertIn("ICP", op[0])
        self.assertEqual(skip, ["ENA"])
