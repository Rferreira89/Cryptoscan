import unittest
from unittest import mock

from engine import sources


class USDCSourceTests(unittest.TestCase):
    def test_scanner_quote_is_usdc(self):
        self.assertEqual(sources.QUOTE, "USDC")

    def test_binance_tickers_keep_only_usdc_pairs(self):
        rows = [
            {"symbol": "BTCUSDC", "lastPrice": "60000", "bidPrice": "59999",
             "askPrice": "60001", "quoteVolume": "1000000",
             "priceChangePercent": "1.5"},
            {"symbol": "BTCUSDT", "lastPrice": "60010", "bidPrice": "60009",
             "askPrice": "60011", "quoteVolume": "2000000",
             "priceChangePercent": "1.6"},
        ]
        with mock.patch.object(sources, "_get", return_value=rows):
            data = sources.Binance().tickers()
        self.assertEqual(set(data), {"BTC"})
        self.assertEqual(data["BTC"]["vol_quote"], 1000000.0)

    def test_okx_tickers_keep_only_usdc_pairs(self):
        payload = {"code": "0", "data": [
            {"instId": "ETH-USDC", "last": "3000", "open24h": "2950",
             "bidPx": "2999", "askPx": "3001", "volCcy24h": "100000"},
            {"instId": "ETH-USDT", "last": "3001", "open24h": "2950",
             "bidPx": "3000", "askPx": "3002", "volCcy24h": "200000"},
        ]}
        with mock.patch.object(sources, "_get", return_value=payload):
            data = sources.OKX().tickers()
        self.assertEqual(set(data), {"ETH"})
        self.assertEqual(data["ETH"]["vol_quote"], 100000.0)

    def test_kucoin_tickers_keep_only_usdc_pairs(self):
        payload = {"code": "200000", "data": {"ticker": [
            {"symbol": "SOL-USDC", "last": "150", "buy": "149.9",
             "sell": "150.1", "volValue": "50000", "changeRate": "0.02"},
            {"symbol": "SOL-USDT", "last": "151", "buy": "150.9",
             "sell": "151.1", "volValue": "90000", "changeRate": "0.03"},
        ]}}
        with mock.patch.object(sources, "_get", return_value=payload):
            data = sources.KuCoin().tickers()
        self.assertEqual(set(data), {"SOL"})
        self.assertEqual(data["SOL"]["vol_quote"], 50000.0)

    def test_candle_requests_use_usdc_symbols(self):
        binance = sources.Binance()
        okx = sources.OKX()
        kucoin = sources.KuCoin()
        with mock.patch.object(sources, "_get", return_value=[]) as get:
            binance.candles("BTC", "30m")
            self.assertEqual(get.call_args.args[1]["symbol"], "BTCUSDC")
        with mock.patch.object(sources, "_get", return_value={"code": "0", "data": []}) as get:
            okx.candles("BTC", "30m")
            self.assertEqual(get.call_args.args[1]["instId"], "BTC-USDC")
        with mock.patch.object(sources, "_get", return_value={"code": "200000", "data": []}) as get:
            kucoin.candles("BTC", "30m")
            self.assertEqual(get.call_args.args[1]["symbol"], "BTC-USDC")


if __name__ == "__main__":
    unittest.main()
