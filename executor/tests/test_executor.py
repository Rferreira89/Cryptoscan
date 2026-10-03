import copy
import unittest

from engine import trade
from executor import plan, simulate

NOW = 2_000_000_000


def signal(direction="LONG", **over):
    long = direction == "LONG"
    p = {"entry_zone": [99.0, 100.0], "stop": 96.0 if long else 103.0,
         "tp": [104.0, 108.0, 112.0] if long else [95.0, 91.0, 87.0],
         "partials": [50, 30, 20], "position_usdc": 25.0, "risk_usdc": 0.9,
         "leverage": {"use": 2.0}}
    s = {"id": "X-PULLBACK-1", "asset": "X", "pair": "X/USDC",
         "direction": direction, "status": "ACTIVE", "mode": "REAL",
         "plan": p, "issued_at": NOW - 60, "expires_at": NOW + 3600}
    s.update(over)
    return s


def state(*sigs, age=30):
    return {"signals": {s["id"]: s for s in sigs}, "scan_times": [NOW - age]}


def trigger(s, px):
    s["status"] = "TRIGGERED"
    s["position"] = trade.open_position(s["plan"], px, NOW, 0.1,
                                        side=s["direction"])


class Plan(unittest.TestCase):
    def test_long_entry_at_top_of_zone(self):
        o = plan.entry_order(signal())
        self.assertEqual((o["side"], o["price"], o["qty"]), ("BUY", 100.0, 0.25))

    def test_short_entry_at_bottom_of_zone(self):
        o = plan.entry_order(signal("SHORT"))
        self.assertEqual((o["side"], o["price"]), ("SELL", 99.0))

    def test_protection_covers_whole_position(self):
        s = signal()
        orders = plan.protection_orders(s)
        stop, tps = orders[0], orders[1:]
        self.assertEqual((stop["side"], stop["trigger"], stop["qty"]),
                         ("SELL", 96.0, 0.25))
        self.assertAlmostEqual(sum(t["qty"] for t in tps), 0.25)
        self.assertEqual([t["price"] for t in tps], [104.0, 108.0, 112.0])

    def test_zero_partials_skipped_and_last_takes_rest(self):
        s = signal()
        s["plan"]["partials"] = [0, 100, 0]
        tps = plan.protection_orders(s)[1:]
        self.assertEqual([(t["n"], t["qty"]) for t in tps], [(2, 0.25)])

    def test_small_partial_flagged(self):
        self.assertFalse(any("warning" in t
                             for t in plan.protection_orders(signal())[1:]))
        s = signal()
        s["plan"]["position_usdc"] = 10.0
        tps = plan.protection_orders(s)[1:]         # 5.2, 3.24, 2.24 USDC
        self.assertEqual(["warning" in t for t in tps], [False, True, True])

    def test_refusals(self):
        self.assertIsNone(plan.refuse(signal(), 0))
        self.assertIn("PAPEL", plan.refuse(signal(mode="PAPER"), 0))
        self.assertIn("simultâneo", plan.refuse(signal(), 2))
        s = signal()
        s["plan"]["risk_usdc"] = 1.5
        self.assertIn("risco", plan.refuse(s, 0))
        s = signal()
        s["plan"]["position_usdc"] = 50.0
        self.assertIn("posição", plan.refuse(s, 0))


class Simulate(unittest.TestCase):
    def acts(self, st, book, now=NOW):
        return [a["action"] for a in simulate.step(st, book, now)]

    def test_full_lifecycle_is_idempotent(self):
        s, book = signal(), {}
        self.assertEqual(self.acts(state(s), book), ["PLACE_ENTRY"])
        self.assertEqual(self.acts(state(s), book), [])
        trigger(s, 100.0)
        self.assertEqual(self.acts(state(s), book),
                         ["PLACE_STOP", "PLACE_TP", "PLACE_TP", "PLACE_TP"])
        self.assertEqual(self.acts(state(s), book), [])
        trade.step(s["position"], 104.5, 104.5, 104.5, 104.5, NOW + 60)
        a = simulate.step(state(s), book, NOW)
        self.assertEqual([x["action"] for x in a], ["MOVE_STOP"])
        self.assertEqual(a[0]["trigger"], 100.0)
        self.assertAlmostEqual(a[0]["qty"], 0.125)
        s.update(status="CLOSED", close_reason="BREAKEVEN", result_r=0.6)
        self.assertEqual(self.acts(state(s), book), ["CANCEL_REST"])
        self.assertEqual(self.acts(state(s), book), [])

    def test_expired_cancels_entry(self):
        s, book = signal(), {}
        self.acts(state(s), book)
        s.update(status="EXPIRED", close_reason="validade")
        self.assertEqual(self.acts(state(s), book), ["CANCEL_ENTRY"])

    def test_stale_state_places_nothing_then_recovers(self):
        s, book = signal(), {}
        self.assertEqual(self.acts(state(s, age=3600), book), ["WAIT"])
        self.assertEqual(book, {})
        self.assertEqual(self.acts(state(s), book), ["PLACE_ENTRY"])

    def test_missing_scan_times_is_stale(self):
        st = state(signal())
        del st["scan_times"]
        self.assertEqual(self.acts(st, {}), ["WAIT"])

    def test_already_triggered_is_not_chased(self):
        s = signal()
        trigger(s, 100.0)
        book = {}
        self.assertEqual(self.acts(state(s), book), ["SKIP"])
        self.assertEqual(self.acts(state(s), book), [])

    def test_third_signal_refused(self):
        sigs = [signal(id=f"A{i}-P-1", issued_at=NOW - 60 + i) for i in range(3)]
        a = simulate.step(state(*sigs), {}, NOW)
        self.assertEqual([x["action"] for x in a],
                         ["PLACE_ENTRY", "PLACE_ENTRY", "SKIP"])

    def test_state_is_never_modified(self):
        s = signal()
        st = state(s)
        before = copy.deepcopy(st)
        simulate.step(st, {}, NOW)
        self.assertEqual(st, before)

    def test_everything_marked_simulated(self):
        self.assertTrue(all(a["simulated"]
                            for a in simulate.step(state(signal()), {}, NOW)))


if __name__ == "__main__":
    unittest.main()
