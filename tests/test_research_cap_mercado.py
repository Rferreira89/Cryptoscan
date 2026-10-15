"""O sucessor CAP_MERCADO (2026-10-15) nao pode ver o futuro."""
import unittest

from tests.test_research_bounce import synth as _synth
from tools import research_rlib as R
from tools.research_cap_mercado import TF, breadth, raw_signals, signals

DAY = 86400
CR = (700, 900, 1100, 1300)


def synth(seed, scale_after=None):
    """Quedas de 6 velas seguidas de uma vela de capitulacao (pavio longo,
    fecho no topo, volume 5x) na mesma vela em todas as moedas."""
    bars = _synth(seed, crashes=CR, scale_after=scale_after)
    for a in CR:
        b = bars[a + 6]
        o = b["o"]
        b.update(l=o * 0.85, c=o * 1.02, h=o * 1.02 * 1.003, v=5000.0)
        if a + 7 < len(bars):
            bars[a + 7]["o"] = b["c"]
    return bars


def run(data, b_min=0.35):
    br = breadth(data)
    return {a: signals(raw_signals(c), br, b_min) for a, c in data.items()}


class NoLookAhead(unittest.TestCase):
    def data(self, scale_after=None):
        return {"AAA": synth(3, scale_after), "BBB": synth(5), "CCC": synth(8)}

    def test_breadth_needs_min_coins(self):
        import tools.research_cap_mercado as M
        old = M.MIN_COINS
        M.MIN_COINS = 3
        try:
            br = breadth(self.data())
            self.assertGreaterEqual(br[CR[0] * TF + 6 * TF], 0.99)
        finally:
            M.MIN_COINS = old

    def test_signals_exist_and_truncation(self):
        import tools.research_cap_mercado as M
        old = M.MIN_COINS
        M.MIN_COINS = 3
        try:
            full = run(self.data())
            self.assertTrue(full["AAA"])
            for cut in (800, 1000, 1200):
                part = run({a: c[:cut] for a, c in self.data().items()})
                lim = cut * TF
                for a in full:
                    self.assertEqual(part[a], {t: s for t, s in full[a].items() if t <= lim})
        finally:
            M.MIN_COINS = old

    def test_changing_future_prices_changes_nothing_before(self):
        import tools.research_cap_mercado as M
        old = M.MIN_COINS
        M.MIN_COINS = 3
        try:
            a, b = self.data(), self.data(scale_after=1000)
            lim = a["AAA"][1000]["t"] + TF
            sa, sb = run(a), run(b)
            for k in sa:
                self.assertEqual({t: s for t, s in sa[k].items() if t <= lim},
                                 {t: s for t, s in sb[k].items() if t <= lim})
            _, ta = R.simulate(a, sa, TF, 3 * DAY)
            _, tb = R.simulate(b, sb, TF, 3 * DAY)
            self.assertTrue(ta)
            self.assertEqual([t for t in ta if t["exit_t"] <= lim],
                             [t for t in tb if t["exit_t"] <= lim])
        finally:
            M.MIN_COINS = old

    def test_no_signal_without_market_flush(self):
        import tools.research_cap_mercado as M
        old = M.MIN_COINS
        M.MIN_COINS = 3
        try:
            d = self.data()
            d["BBB"], d["CCC"] = _synth(5), _synth(8)     # so uma moeda cai
            self.assertFalse(run(d, 0.5)["AAA"])
        finally:
            M.MIN_COINS = old


if __name__ == "__main__":
    unittest.main()
