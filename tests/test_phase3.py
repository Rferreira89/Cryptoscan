import unittest

from engine import derivatives as D
from engine import liquidity as L
from engine import volume as VOL
from tests.test_analysis import walk, zigzag

mk = lambda t, o, h, l, c, v=10.0, tb=None: {"t": t, "o": o, "h": h, "l": l,
                                             "c": c, "v": v, "tb": tb}


def flat(n, px=100.0, v=10.0, tb=5.0):
    return [mk(i, px, px + 1, px - 1, px, v, tb) for i in range(n)]


class Volume(unittest.TestCase):
    def test_rvol_and_labels(self):
        c = flat(60) + [mk(60, 100, 103, 99, 102, 30.0, 20.0)]
        v = VOL.analyse(c)
        self.assertEqual(v["rvol"], 3.0)
        self.assertIn("VOLUME_EXPANSION", v["labels"])
        self.assertNotIn("POSSIBLE_ABSORPTION", v["labels"])
        quiet = flat(60) + [mk(60, 100, 100.5, 99.5, 100, 30.0, 15.0)]
        self.assertIn("POSSIBLE_ABSORPTION", VOL.analyse(quiet)["labels"])
        low = flat(60) + [mk(60, 100, 101, 99, 100, 4.0, 2.0)]
        self.assertIn("VOLUME_CONTRACTION", VOL.analyse(low)["labels"])

    def test_cvd_sign_and_divergence(self):
        up = flat(40) + [mk(40 + i, 100 + 2 * i, 103 + 2 * i, 99 + 2 * i,
                            102 + 2 * i, 10.0, 8.0) for i in range(25)]
        v = VOL.analyse(up)
        self.assertEqual(v["flow_source"], "CVD")
        self.assertAlmostEqual(v["flow_20"], 0.6)
        self.assertIsNone(v["divergence"])
        sold = flat(40) + [mk(40 + i, 100 + 2 * i, 103 + 2 * i, 99 + 2 * i,
                              102 + 2 * i, 10.0, 3.0) for i in range(25)]
        v = VOL.analyse(sold)
        self.assertAlmostEqual(v["flow_20"], -0.4)
        self.assertEqual(v["divergence"], "BEARISH")

    def test_obv_fallback_and_bad_taker_data(self):
        c = walk(120)                       # sem campo tb
        self.assertEqual(VOL.analyse(c)["flow_source"], "OBV")
        bad = flat(60, tb=50.0)             # comprador > total: nao confiar
        self.assertEqual(VOL.analyse(bad)["flow_source"], "OBV")
        self.assertIsNone(VOL.analyse(flat(10)))


def zz(points):
    """zigzag precedido de 40 velas planas (o modulo exige 60 velas)."""
    p0 = points[0]
    return [mk(i, p0, p0 + 0.01, p0 - 0.01, p0) for i in range(40)] + zigzag(points)


class Liquidity(unittest.TestCase):
    def test_sweep_low_unconfirmed_then_confirmed(self):
        base = zz([100, 110, 104, 112, 106, 111])       # fundo em ~104/106
        n = len(base)
        sw = mk(n, 111, 111.2, 105.5, 110.5)                # fura 106 e recupera
        r = L.analyse(base + [sw])["sweep"]
        self.assertEqual((r["side"], r["confirmed"], r["bars_ago"]),
                         ("LOW", False, 0))
        self.assertAlmostEqual(r["level"], 105.99, places=2)
        after = mk(n + 1, 110.5, 112.5, 110.2, 112.4)       # fecha acima do maximo
        r = L.analyse(base + [sw, after])["sweep"]
        self.assertEqual((r["confirmed"], r["bars_ago"]), (True, 1))

    def test_breakdown_is_not_sweep(self):
        base = zz([100, 110, 104, 112, 106, 111])
        brk = mk(len(base), 111, 111.2, 104.5, 105.0)       # fecha abaixo
        self.assertIsNone(L.analyse(base + [brk])["sweep"])

    def test_pools_and_equal_highs(self):
        c = zz([100, 110, 104, 110.02, 103, 108, 105])
        r = L.analyse(c)
        self.assertEqual(len(r["pools_above"]), 2)
        self.assertAlmostEqual(r["equal_highs"], 110.02, places=1)
        self.assertTrue(all(p > c[-1]["c"] for p in r["pools_above"]))
        self.assertTrue(all(p < c[-1]["c"] for p in r["pools_below"]))

    def test_fvg_unfilled_and_filled(self):
        c = flat(70)
        n = len(c)
        gap = [mk(n, 100, 101, 99.5, 100.8), mk(n + 1, 101, 108, 100.9, 107.5),
               mk(n + 2, 107.5, 109, 104, 108.5), mk(n + 3, 108.5, 110, 107, 109)]
        r = L.analyse(c + gap)
        self.assertEqual(r["fvg_below"], [101, 104])
        fill = mk(n + 4, 109, 109.5, 100.5, 109)            # preenche o gap
        self.assertIsNone(L.analyse(c + gap + [fill])["fvg_below"])

    def test_order_block_after_bos(self):
        c = zz([100, 110, 105, 118, 112, 126, 120, 135])
        ob = L.analyse(c)["order_block"]
        self.assertEqual(ob["side"], "DEMAND")
        self.assertLess(ob["zone"][1], c[-1]["c"])

    def test_book_metrics(self):
        bids = [(99.9, 50), (99.5, 100), (98.0, 1000)]
        asks = [(100.1, 50), (100.5, 100), (102.0, 1000)]
        m = L.book_metrics(bids, asks)
        self.assertTrue(m["depth_complete"])
        self.assertAlmostEqual(m["imbalance"], (14945 - 15055) / 30000, places=3)
        # 10k: 50@100.1 (5005) + 49.70@100.5 -> media ~100.30 vs mid 100
        self.assertAlmostEqual(m["slippage_bps_10k"], 29.96, delta=0.1)
        thin = L.book_metrics([(99.9, 1)], [(100.1, 1)])
        self.assertIsNone(thin["slippage_bps_10k"])
        self.assertFalse(thin["depth_complete"])
        self.assertIsNone(L.book_metrics([], asks))


class Derivatives(unittest.TestCase):
    def test_quadrants(self):
        self.assertEqual(D.quadrant(3, 5), "LONG_BUILDUP")
        self.assertEqual(D.quadrant(3, -5), "SHORT_COVERING")
        self.assertEqual(D.quadrant(-3, 5), "SHORT_BUILDUP")
        self.assertEqual(D.quadrant(-3, -5), "LONG_LIQUIDATION")
        self.assertEqual(D.quadrant(3, 0.2), "FLAT")
        self.assertIsNone(D.quadrant(None, 5))

    def test_pctile(self):
        h = list(range(100))
        self.assertEqual(D.pctile(99, h), 100)
        self.assertEqual(D.pctile(49, h), 50)
        self.assertEqual(D.pctile(1e-4, [1e-4] * 30), 50)   # empates
        self.assertIsNone(D.pctile(5, [1, 2, 3]))        # amostra curta
        self.assertIsNone(D.pctile(None, h))

    def test_flags(self):
        f = D.flags
        self.assertIn("FUNDING_EXTREME_POSITIVE",
                      f({"funding_pctile": 97, "funding_apr": 40}))
        # percentil alto mas funding baixo em absoluto: nao e extremo
        self.assertEqual(f({"funding_pctile": 97, "funding_apr": 8}), [])
        self.assertIn("CROWDED_LONGS",
                      f({"funding_pctile": 80, "funding_apr": 12, "ls_pctile": 95}))
        self.assertIn("CROWDED_SHORTS",
                      f({"funding_pctile": 10, "funding_apr": -2, "ls_pctile": 5}))
        self.assertIn("LEVERAGE_EXPANSION", f({"oi_chg_24h_pct": 14}))
        self.assertEqual(f({}), [])

    def _patch(self, responses):
        orig = D._get

        def fake(kind, path, params):
            v = responses[path.rsplit("/", 1)[-1]]
            if isinstance(v, Exception):
                raise v
            return v
        D._get = fake
        self.addCleanup(lambda: setattr(D, "_get", orig))

    SNAP = {"tick": {"SUI-USDT-SWAP": {"last": "1.21", "open24h": "1.10"}},
            "oi": {"SUI-USDT-SWAP": 5e7}, "ctval": {"SUI-USDT-SWAP": 1.0}}
    NOW = 1_800_000_000

    def _ok(self):
        return {
            "funding-rate": [{"fundingRate": "0.0005", "fundingTime": "28800000",
                              "nextFundingTime": "57600000"}],
            "funding-rate-history": [{"fundingRate": str(i * 1e-5)}
                                     for i in range(40)],
            "open-interest-history": [[0, 0, str(110 - i), 0] for i in range(7)],
            "long-short-account-ratio-contract": [[0, str(2.5 - i * 0.01)]
                                                  for i in range(60)],
            "liquidation-orders": [{"details": [
                {"posSide": "long", "sz": "100", "bkPx": "1.2",
                 "ts": str((self.NOW - 3600) * 1000)},
                {"posSide": "short", "sz": "50", "bkPx": "1.2",
                 "ts": str((self.NOW - 7200) * 1000)},
                {"posSide": "long", "sz": "999", "bkPx": "1.2",
                 "ts": str((self.NOW - 90000) * 1000)}]}]}

    def test_analyse_full(self):
        self._patch(self._ok())
        d = D.analyse("SUI", 1.20, self.SNAP, self.NOW)
        self.assertEqual(d["missing"], [])
        self.assertEqual(d["funding_interval_h"], 8.0)
        self.assertAlmostEqual(d["funding_apr"], 54.8, places=1)
        self.assertEqual(d["funding_pctile"], 100)
        self.assertAlmostEqual(d["oi_chg_24h_pct"], 5.77, places=2)
        self.assertEqual(d["price_chg_24h_pct"], 10.0)
        self.assertEqual(d["positioning"], "LONG_BUILDUP")
        self.assertAlmostEqual(d["basis_pct"], 0.833, places=3)
        self.assertEqual(d["liquidations"]["long_usd"], 120)   # exclui >24h
        self.assertEqual(d["liquidations"]["short_usd"], 60)
        self.assertEqual(d["liquidations"]["hours_covered"], 24.0)
        self.assertTrue(d["liquidations"]["complete"])
        self.assertIn("CROWDED_LONGS", d["flags"])
        self.assertIn("FUNDING_EXTREME_POSITIVE", d["flags"])

    def test_partial_failure_is_reported_not_invented(self):
        from engine.sources import SourceError
        r = self._ok()
        r["funding-rate"] = SourceError("x")
        r["long-short-account-ratio-contract"] = []
        self._patch(r)
        d = D.analyse("SUI", 1.20, self.SNAP, self.NOW)
        self.assertEqual(sorted(d["missing"]), ["funding", "long_short_ratio"])
        self.assertIsNone(d["funding_rate"])
        self.assertIsNone(d["ls_ratio"])
        self.assertEqual(d["flags"], [])
        self.assertEqual(d["positioning"], "LONG_BUILDUP")

    def test_liquidations_pagination_incomplete(self):
        r = self._ok()
        calls = []

        def page(n):
            ts = (self.NOW - 600 * n) * 1000
            return [{"details": [{"posSide": "short", "sz": "10", "bkPx": "2",
                                  "ts": str(ts)}]}]
        orig = D._get

        def fake(kind, path, params):
            key = path.rsplit("/", 1)[-1]
            if key == "liquidation-orders":
                calls.append(params.get("after"))
                return page(len(calls))
            return r[key]
        D._get = fake
        self.addCleanup(lambda: setattr(D, "_get", orig))
        d = D.analyse("SUI", 1.20, self.SNAP, self.NOW)
        liq = d["liquidations"]
        self.assertEqual(len(calls), D.MAX_LIQ_PAGES)
        self.assertIsNone(calls[0])
        self.assertFalse(liq["complete"])
        self.assertEqual(liq["short_usd"], 20 * D.MAX_LIQ_PAGES)
        self.assertEqual(liq["hours_covered"], round(600 * D.MAX_LIQ_PAGES / 3600, 1))

    def test_no_perp(self):
        self.assertIsNone(D.analyse("NOPE", 1.0, self.SNAP, self.NOW))


if __name__ == "__main__":
    unittest.main()
