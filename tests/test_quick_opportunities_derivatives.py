import unittest

from engine import quick_opportunities_derivatives as D
from engine import quick_opportunities as Q


def xperp(inst="BTC-USD_UM_XPERP", state="live", family="BTC-USD_UM",
          ct_type="linear", expiry="1930000000000", rule_type="xperp"):
    return {"instId": inst, "instFamily": family, "state": state, "ruleType": rule_type,
            "ctType": ct_type, "ctVal": "0.0001", "ctValCcy": "BTC",
            "ctMult": "1", "minSz": "1", "lotSz": "1", "tickSz": "0.1",
            "expTime": expiry, "settleCcy": "USDⓈ"}


def xperp_candle(ts, confirm="1"):
    return [str(ts), "100", "102", "99", "101", "10", "10", "1000", confirm]


class USDCAccountAdapterTests(unittest.TestCase):
    def test_discovers_only_live_linear_usd_um_xperps(self):
        def request(url, params):
            self.assertEqual(params["instType"], "FUTURES")
            return {"code": "0", "data": [
                xperp(),
                xperp("ETH-USD_UM_XPERP", family="ETH-USD_UM"),
                xperp("BTC-USDT-250808", family="BTC-USDT", expiry=""),
                xperp("SOL-USD_UM_XPERP", state="suspend", family="SOL-USD_UM"),
                xperp("DOGE-USD_UM_XPERP", family="DOGE-USD_UM", ct_type="inverse"),
                xperp("PRE-USD_UM_XPERP", family="PRE-USD_UM", rule_type="pre_market"),
            ]}
        result = D.okx_usdc_xperps(request)
        self.assertEqual(set(result), {"BTC", "ETH"})
        self.assertEqual(result["BTC"]["inst_id"], "BTC-USD_UM_XPERP")
        self.assertEqual(result["BTC"]["market_type"], "usd_margined_xperp")
        self.assertEqual(result["BTC"]["settlement_currency_required"], "USDC")
        self.assertAlmostEqual(result["BTC"]["contract_value"], 0.0001)

    def test_prefers_furthest_expiry_generation(self):
        def request(url, params):
            return {"code": "0", "data": [
                xperp(expiry="1900000000000"),
                xperp(expiry="1930000000000"),
            ]}
        result = D.okx_usdc_xperps(request)
        self.assertEqual(result["BTC"]["expiry"], "1930000000000")

    def test_account_config_must_confirm_usdc(self):
        self.assertEqual(D.validate_okx_account_config(
            {"code": "0", "data": [{"settleCcy": "USDC"}]}), (True, "USDC confirmado"))
        ok, reason = D.validate_okx_account_config(
            {"code": "0", "data": [{"settleCcy": "USD"}]})
        self.assertFalse(ok)
        self.assertIn("não USDC", reason)
        self.assertFalse(D.validate_okx_account_config({"code": "1", "data": []})[0])
        self.assertFalse(D.validate_okx_account_config({})[0])

    def test_xperp_candles_paginate_and_keep_confirmed_only(self):
        step = D.BAR_MS
        calls = []
        original = D.PAGE["okx"]
        D.PAGE["okx"] = 2
        def request(url, params):
            calls.append(params)
            batch = ([xperp_candle(2 * step), xperp_candle(step)]
                     if len(calls) == 1 else
                     [xperp_candle(step), xperp_candle(0, "0")])
            return {"code": "0", "data": batch}
        try:
            rows = D.fetch_okx_xperp_candles("BTC-USD_UM_XPERP", 0,
                                              3 * step, request, pause_seconds=0)
        finally:
            D.PAGE["okx"] = original
        self.assertEqual([x["t"] for x in rows], [1800, 3600])
        self.assertEqual(calls[0]["instId"], "BTC-USD_UM_XPERP")
        self.assertEqual(calls[0]["bar"], "30m")
        self.assertEqual(int(calls[1]["after"]), step)

    def test_xperp_funding_history_returns_timestamped_rates(self):
        def request(url, params):
            return {"code": "0", "data": [
                {"fundingTime": "3600000", "realizedRate": "0.0001"},
                {"fundingTime": "7200000", "realizedRate": "-0.0002"},
            ]}
        rows = D.fetch_okx_xperp_funding_history(
            "BTC-USD_UM_XPERP", 0, 10_000_000, request, pause_seconds=0)
        self.assertEqual(rows, [(3600, 0.0001), (7200, -0.0002)])

    def test_funding_history_limit_is_enforced(self):
        with self.assertRaises(ValueError):
            D.fetch_okx_xperp_funding_history(
                "BTC-USD_UM_XPERP", 0, 91 * 24 * 60 * 60 * 1000,
                lambda *_: {})

    def test_historical_funding_is_charged_to_long_and_credited_to_short(self):
        candles = [{"t": i * Q.BAR_SECONDS, "o": 100, "h": 101,
                    "l": 99, "c": 100, "v": 10} for i in range(10)]
        long_trade = Q.simulate_candidate(
            candles, 0, {"side": "LONG", "stop": 90, "target": 120},
            fee_pct=0, slippage_pct=0, funding_events=[(3600, 0.001)])
        short_trade = Q.simulate_candidate(
            candles, 0, {"side": "SHORT", "stop": 110, "target": 80},
            fee_pct=0, slippage_pct=0, funding_events=[(3600, 0.001)])
        self.assertEqual(long_trade["status"], "CLOSED")
        self.assertEqual(short_trade["status"], "CLOSED")
        self.assertGreater(long_trade["costs_r"], short_trade["costs_r"])
        self.assertAlmostEqual(long_trade["funding_cost_pct"], 0.1)
        self.assertAlmostEqual(short_trade["funding_cost_pct"], -0.1)

    def test_rejects_unaligned_candle_range(self):
        with self.assertRaises(ValueError):
            D.fetch_okx_xperp_candles("BTC-USD_UM_XPERP", 1,
                                       D.BAR_MS, lambda *_: {})


if __name__ == "__main__":
    unittest.main()
