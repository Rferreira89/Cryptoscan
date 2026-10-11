"""A investigacao do oversold bounce (4H) nao pode ver o futuro."""
import unittest

from tools import research_rlib as R
from tools.research_bounce import TF, signals

DAY = 86400


def synth(seed, n=1500, crashes=(), scale_after=None):
    bars, p, x = [], 100.0, seed
    for i in range(n):
        x = (x * 1103515245 + 12345) % 2 ** 31
        r = (x / 2 ** 31 - 0.47) * 0.02
        for a in crashes:
            if a <= i < a + 6:
                r = -0.03
            if i == a + 6:
                r = 0.035
        o, p = p, p * (1 + r)
        k = 3.0 if scale_after is not None and i > scale_after else 1.0
        bars.append({"t": i * TF, "o": o * k, "h": max(o, p) * 1.003 * k,
                     "l": min(o, p) * 0.997 * k, "c": p * k, "v": 1000.0})
    return bars


CR = (700, 900, 1100, 1300)
UP = {d: True for d in range(0, 400)}
CFG = (30, False)


class NoLookAhead(unittest.TestCase):
    def test_signals_exist(self):
        self.assertTrue(signals(synth(2, crashes=CR), UP, *CFG))

    def test_truncating_future_changes_no_signal(self):
        full = synth(2, crashes=CR)
        sig = signals(full, UP, *CFG)
        for cut in (705, 708, 950, 1200):
            part = signals(full[:cut], UP, *CFG)
            self.assertEqual(part, {t: s for t, s in sig.items()
                                    if t <= full[cut - 1]["t"] + TF})

    def test_changing_future_prices_changes_nothing_before(self):
        a, b = synth(2, crashes=CR), synth(2, crashes=CR, scale_after=1000)
        sa, sb = signals(a, UP, *CFG), signals(b, UP, *CFG)
        lim = a[1000]["t"] + TF
        self.assertEqual({t: s for t, s in sa.items() if t <= lim},
                         {t: s for t, s in sb.items() if t <= lim})
        data_a = {"BTC": synth(1), "AAA": a}
        data_b = {"BTC": synth(1), "AAA": b}
        ca, ta = R.simulate(data_a, {"AAA": sa}, TF, 3 * DAY)
        cb, tb = R.simulate(data_b, {"AAA": sb}, TF, 3 * DAY)
        d = (a[1000]["t"] + TF) // DAY
        self.assertTrue([t for t in ta if t["exit_t"] <= lim])
        self.assertEqual([x for x in ca if x[0] < d], [x for x in cb if x[0] < d])
        self.assertEqual([t for t in ta if t["exit_t"] <= lim],
                         [t for t in tb if t["exit_t"] <= lim])

    def test_entry_is_open_of_bar_after_signal(self):
        a = synth(2, crashes=CR)
        sig = signals(a, UP, *CFG)
        _, tr = R.simulate({"AAA": a}, {"AAA": sig}, TF, 3 * DAY)
        self.assertTrue(tr)
        for t in tr:
            i = t["i"]
            self.assertIn(a[i]["t"], sig)                 # decidido em i-1
            self.assertGreater(a[i - 1]["c"], a[i - 2]["h"])
            s = sig[a[i]["t"]]
            self.assertAlmostEqual(t["geo"]["stop"], s["stop"] / a[i]["o"] - 1)
            self.assertLess(s["stop"], min(x["l"] for x in a[i - 6:i]))

    def test_btc_filter_uses_last_closed_day(self):
        a = synth(2, crashes=CR)
        sig = signals(a, UP, *CFG)
        t = min(sig)
        day = t // DAY - 1
        self.assertFalse(t in signals(a, {d: d != day for d in UP}, *CFG))
        # o proprio dia da decisao (ainda aberto ou acabado de fechar) e o
        # seguinte nao contam
        self.assertTrue(t in signals(a, {d: d <= day for d in UP}, *CFG))

    def test_time_exit_and_costs(self):
        bars = [{"t": i * TF, "o": 100.0, "h": 100.5, "l": 99.5, "c": 100.0,
                 "v": 1.0} for i in range(40)]
        plan = {"stop": 90.0, "tp": [120.0], "partials": [100]}
        pos, k = R.run_trade(bars, 5, plan, TF, 3 * DAY)
        self.assertEqual(k, 5 + 17)                       # 18 velas = 3 dias
        self.assertEqual(pos["exit_reason"], "TIME")
        e, x = 100 * 1.001, 100 * 0.999
        exp = ((x - e) - 0.0025 * (x + e)) / ((e - 90) + 0.0025 * (e + 90))
        self.assertAlmostEqual(pos["r"], round(exp, 3), places=3)

    def test_control_trades_only_read_forward(self):
        a = synth(2, crashes=CR)
        geo = {"stop": -0.05, "tp": [0.03, 0.06], "partials": [50, 50]}
        full = R.control_rs(a, 800, geo, TF, 3 * DAY, 20)
        b = [dict(x) for x in a]
        for x in b[:780]:
            for f in "ohlc":
                x[f] *= 2
        self.assertEqual(full, R.control_rs(b, 800, geo, TF, 3 * DAY, 20))


if __name__ == "__main__":
    unittest.main()
