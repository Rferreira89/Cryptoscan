import unittest

from engine import quick_opportunities_derivatives as D
from engine import quick_opportunities as Q


def okx_instrument(inst="BTC-USDT-SWAP", state="live", settle="USDT",
                  ct_type="linear"):
    return {"instId": inst, "state": state, "settleCcy": settle,
            "ctType": ct_type, "ctVal": "0.01", "ctValCcy": "BTC",
            "ctMult": "1", "minSz": "1", "lotSz": "1", "tickSz": "0.1"}


def bybit_instrument(symbol="BTCUSDT"):
    return {"symbol": symbol, "status": "Trading", "quoteCoin": "USDT",
            "settleCoin": "USDT", "contractType": "LinearPerpetual",
            "lotSizeFilter": {"minOrderQty": "0.001", "qtyStep": "0.001"},
            "priceFilter": {"tickSize": "0.1"}}


def okx_candle(ts, confirm="1"):
    return [str(ts), "100", "102", "99", "101", "10", "10", "1000", confirm]


class DerivativesAdapterTests(unittest.TestCase):
    def test_okx_discovers_only_live_linear_usdt_swaps(self):
        def request(url, params):
            return {"code": "0", "data": [
                okx_instrument(),
                okx_instrument("ETH-USDT-SWAP", state="suspend"),
                okx_instrument("BTC-USD-SWAP", settle="BTC"),
                okx_instrument("BTC-USDT-SWAP", ct_type="inverse"),
            ]}
        result = D.okx_linear_usdt_swaps(request)
        self.assertEqual(list(result), ["BTC"])
        self.assertEqual(result["BTC"]["inst_id"], "BTC-USDT-SWAP")
        self.assertEqual(result["BTC"]["market_type"], "linear_perpetual")
        self.assertEqual(result["BTC"]["contract_value"], 0.01)

    def test_bybit_discovers_linear_usdt_perpetuals(self):
        def request(url, params):
            self.assertEqual(params["category"], "linear")
            return {"retCode": 0, "result": {"list": [bybit_instrument()]}}
        result = D.bybit_linear_usdt_perpetuals(request)
        self.assertEqual(result["BTC"]["inst_id"], "BTCUSDT")
        self.assertEqual(result["BTC"]["min_size"], 0.001)

    def test_okx_swap_candles_paginates_and_keeps_confirmed_only(self):
        step = D.BAR_MS
        calls = []
        original = D.PAGE["okx"]
        D.PAGE["okx"] = 2
        def request(url, params):
            calls.append(params)
            batch = ([okx_candle(2 * step), okx_candle(step)]
                     if len(calls) == 1 else
                     [okx_candle(step), okx_candle(0, "0")])
            return {"code": "0", "data": batch}
        try:
            rows = D.fetch_okx_swap_candles("BTC-USDT-SWAP", 0, 3 * step,
                                             request, pause_seconds=0)
        finally:
            D.PAGE["okx"] = original
        self.assertEqual([x["t"] for x in rows], [1800, 3600])
        self.assertEqual(calls[0]["instId"], "BTC-USDT-SWAP")
        self.assertEqual(calls[0]["bar"], "30m")
        self.assertEqual(int(calls[1]["after"]), step)

    def test_bybit_linear_candles_use_linear_category(self):
        step = D.BAR_MS
        calls = []
        def request(url, params):
            calls.append(params)
            return {"retCode": 0, "result": {"list": [
                [str(0), "100", "102", "99", "101", "10", "1000"],
                [str(step), "101", "103", "100", "102", "11", "1100"],
            ]}}
        rows = D.fetch_bybit_linear_candles("BTCUSDT", 0, 2 * step,
                                             request, pause_seconds=0)
        self.assertEqual(calls[0]["category"], "linear")
        self.assertEqual(calls[0]["interval"], "30")
        self.assertEqual([x["t"] for x in rows], [0, 1800])

    def test_okx_funding_history_returns_timestamped_rates(self):
        def request(url, params):
            return {"code": "0", "data": [
                {"fundingTime": "3600000", "realizedRate": "0.0001"},
                {"fundingTime": "7200000", "realizedRate": "-0.0002"},
            ]}
        rows = D.fetch_okx_funding_history("BTC-USDT-SWAP", 0, 10_000_000,
                                            request, pause_seconds=0)
        self.assertEqual(rows, [(3600, 0.0001), (7200, -0.0002)])

    def test_bybit_funding_history_returns_timestamped_rates(self):
        def request(url, params):
            self.assertEqual(params["category"], "linear")
            return {"retCode": 0, "result": {"list": [
                {"fundingRateTimestamp": "3600000", "fundingRate": "0.0001"},
            ]}}
        rows = D.fetch_bybit_funding_history("BTCUSDT", 0, 10_000_000,
                                              request, pause_seconds=0)
        self.assertEqual(rows, [(3600, 0.0001)])


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
            D.fetch_okx_swap_candles("BTC-USDT-SWAP", 1, D.BAR_MS,
                                     lambda *_: {})


if __name__ == "__main__":
    unittest.main()
