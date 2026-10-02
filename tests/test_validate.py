import unittest

from engine import validate as V
from engine import scanner as S

TF = 14400
NOW = 1_800_000_000 - (1_800_000_000 % TF) + 100


def series(n=300, end=None):
    end = end or (NOW - NOW % TF) - TF
    return [{"t": end - TF * (n - 1 - i), "o": 100.0, "h": 101.0, "l": 99.0,
             "c": 100.0, "v": 10.0} for i in range(n)]


def status(raw):
    return V.validate_candles(raw, TF, NOW)[1]


class T(unittest.TestCase):
    def test_clean(self):
        self.assertEqual(status(series())["status"], V.VALID)

    def test_forming_candle_dropped(self):
        raw = series() + [{"t": NOW - NOW % TF, "o": 1e9, "h": 1e9, "l": 1e9,
                           "c": 1e9, "v": 1.0}]
        c, rep = V.validate_candles(raw, TF, NOW)
        self.assertEqual(rep["status"], V.VALID)
        self.assertEqual(len(c), 300)

    def test_exact_duplicate_is_degraded(self):
        raw = series(); raw.append(dict(raw[5]))
        self.assertEqual(status(raw)["status"], V.DEGRADED)

    def test_conflicting_duplicate_invalid(self):
        raw = series(); d = dict(raw[5]); d["c"] = 100.5; raw.append(d)
        self.assertEqual(status(raw)["status"], V.INVALID)

    def test_recent_gap_invalid(self):
        raw = series(); del raw[-10]
        self.assertEqual(status(raw)["status"], V.INVALID)

    def test_old_single_gap_degraded(self):
        raw = series(); del raw[20]
        self.assertEqual(status(raw)["status"], V.DEGRADED)

    def test_impossible_price(self):
        raw = series(); raw[50]["h"] = 98.0
        self.assertEqual(status(raw)["status"], V.INVALID)
        raw = series(); raw[50]["l"] = -1.0
        self.assertEqual(status(raw)["status"], V.INVALID)

    def test_misaligned(self):
        raw = series(); raw[50]["t"] += 7
        self.assertEqual(status(raw)["status"], V.INVALID)

    def test_stale(self):
        self.assertEqual(status(series(end=NOW - NOW % TF - 5 * TF))["status"],
                         V.INVALID)

    def test_unparseable(self):
        raw = series(); raw[3]["c"] = None
        self.assertEqual(status(raw)["status"], V.INVALID)

    def test_short_history_and_empty(self):
        self.assertEqual(status(series(50))["status"], V.DEGRADED)
        self.assertEqual(status([])["status"], V.INVALID)

    def test_divergence(self):
        self.assertEqual(V.price_divergence({"a": 100, "b": 100.1})[1], V.VALID)
        self.assertEqual(V.price_divergence({"a": 100, "b": 101.5})[1], V.DEGRADED)
        self.assertEqual(V.price_divergence({"a": 100, "b": 110})[1], V.INVALID)
        self.assertIsNone(V.price_divergence({"a": 100})[1])

    def test_universe_filters(self):
        tk = lambda last, bid, ask, vol: {"base": "", "last": last, "bid": bid,
                                          "ask": ask, "vol_quote": vol,
                                          "chg_pct": 1.0}
        data = {"bybit": {"BTC": tk(100, 99.99, 100.01, 5e8),
                          "USDC": tk(1, 1, 1, 9e9),
                          "BTC3L": tk(1, 1, 1.0001, 9e9),
                          "THIN": tk(1, 0.9, 1.1, 9e7),
                          "TINY": tk(1, 1, 1.0001, 1e5),
                          "DEAD": tk(1, 0, 0, 1e9)},
                "okx": {"BTC": tk(100.02, 100.0, 100.03, 2e8)}}
        uni = {r["asset"]: r for r in S.build_universe(data)}
        self.assertEqual(set(uni), {"BTC", "THIN", "TINY"})
        self.assertTrue(uni["BTC"]["eligible"])
        self.assertEqual(uni["BTC"]["volume_24h"], 7e8)
        self.assertEqual(uni["THIN"]["excluded_for"], ["spread excessivo"])
        self.assertEqual(uni["TINY"]["excluded_for"], ["volume baixo"])
        self.assertGreater(S.liquidity_score(1e9, 1, 3), S.liquidity_score(1e7, 15, 1))


if __name__ == "__main__":
    unittest.main()
