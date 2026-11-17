import unittest
from unittest import mock

from engine import quick_opportunities_okx as Q
from engine import quick_opportunities_telegram as T
from engine import quick_opportunities_derivatives as D


class OkxQuickOpportunityTests(unittest.TestCase):
    def instruments(self):
        return {
            "BTC": {
                "inst_id": "BTC-USD_UM_XPERP",
                "inst_family": "BTC-USD_UM",
                "contract_type": "linear",
                "asset_class": "crypto",
                "contract_value": 0.01,
                "contract_multiplier": 1,
            },
            "ETH": {
                "inst_id": "ETH-USD_UM_XPERP",
                "inst_family": "ETH-USD_UM",
                "contract_type": "linear",
                "asset_class": "crypto",
                "contract_value": 0.1,
                "contract_multiplier": 1,
            },
            "AAPL": {
                "inst_id": "AAPL-USD_UM_XPERP",
                "inst_family": "AAPL-USD_UM",
                "contract_type": "linear",
                "asset_class": "equity",
                "contract_value": 1,
                "contract_value_currency": "AAPL",
                "contract_multiplier": 1,
            },
            "XAU": {
                "inst_id": "XAU-USD_UM_XPERP",
                "inst_family": "XAU-USD_UM",
                "contract_type": "linear",
                "asset_class": "precious_metal",
                "contract_value": 1,
                "contract_value_currency": "XAU",
                "contract_multiplier": 1,
            },
            "BAD": {
                "inst_id": "BAD-USDT-SWAP",
                "inst_family": "BAD-USDT",
                "contract_type": "linear",
            },
        }

    def test_public_discovery_accepts_canonical_okx_xperp_id(self):
        response = {
            "code": "0",
            "data": [{
                "instId": "BTC-USD_UM_XPERP",
                "instFamily": "BTC-USD_UM",
                "state": "live",
                "instCategory": "1",
                "ctType": "linear",
                "ctVal": "0.01",
                "ctValCcy": "BTC",
                "minSz": "1",
                "lotSz": "1",
                "tickSz": "0.1",
                "expTime": "",
            }],
        }
        instruments = D.okx_usdc_xperps(
            request=lambda url, params: response)
        self.assertIn("BTC", instruments)
        self.assertEqual(instruments["BTC"]["inst_id"], "BTC-USD_UM_XPERP")
        self.assertEqual(instruments["BTC"]["contract_value_currency"], "BTC")

    def test_selects_only_live_xperp_metadata_and_ranks_by_volume(self):
        tickers = [
            {"instId": "BTC-USD_UM_XPERP", "volCcy24h": "1000", "last": "3000"},
            {"instId": "ETH-USD_UM_XPERP", "volCcy24h": "5000", "last": "2000"},
            {"instId": "BAD-USDT-SWAP", "volCcy24h": "9000"},
        ]
        rows = Q.select_liquid_xperps(self.instruments(), tickers, limit=1)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["base"], "ETH")
        self.assertEqual(rows[0]["inst_id"], "ETH-USD_UM_XPERP")

    def test_equity_and_precious_metal_xperps_are_included_and_classified(self):
        tickers = [
            {"instId": "AAPL-USD_UM_XPERP", "vol24h": "100", "last": "200"},
            {"instId": "XAU-USD_UM_XPERP", "vol24h": "10", "last": "2500"},
        ]
        rows = Q.select_liquid_xperps(self.instruments(), tickers)
        by_base = {row["base"]: row for row in rows}
        self.assertEqual(by_base["AAPL"]["asset_class"], "equity")
        self.assertEqual(by_base["XAU"]["asset_class"], "precious_metal")
        self.assertEqual(by_base["AAPL"]["volume_24h_contract_quote"], 20000)
        self.assertEqual(by_base["XAU"]["volume_24h_contract_quote"], 25000)

    def test_contract_multiplier_is_included_in_notional_volume(self):
        info = {**self.instruments()["BTC"], "contract_multiplier": 10}
        rows = Q.select_liquid_xperps(
            {"BTC": info},
            [{"instId": info["inst_id"], "vol24h": "2", "last": "30000"}],
        )
        self.assertEqual(rows[0]["volume_24h_contract_quote"], 6000)

    def test_one_contract_feed_failure_does_not_escape_worker(self):
        info = self.instruments()["BTC"]
        info = {**info, "base": "BTC"}
        with mock.patch.object(D, "fetch_okx_xperp_candles",
                               side_effect=RuntimeError("temporary API failure")):
            returned, candidates, report = Q._fetch_one(
                info, 0, Q.BAR_MS, 1800, request=lambda *_: {})
        self.assertEqual(returned["base"], "BTC")
        self.assertEqual(candidates, [])
        self.assertEqual(report["status"], "DATA SOURCE ERROR")
        self.assertIn("temporary API failure", report["error"])

    def test_ignores_missing_or_zero_volume_contracts(self):
        tickers = [{"instId": "BTC-USD_UM_XPERP", "volCcy24h": "0"}]
        self.assertEqual(Q.select_liquid_xperps(self.instruments(), tickers), [])

    def test_okx_alert_identifies_contract_and_does_not_claim_account_confirmed(self):
        candidate = {
            "asset": "ETH", "family": "momentum", "side": "SHORT",
            "signal_t": 1790000000, "signal_close": 3000.0,
            "stop": 3050.0, "target": 2900.0, "max_hold_bars": 8,
            "regime": "bearish", "score": 2, "reason": "momentum negativo",
            "venue": "OKX", "market_type": "USD_UM_XPERP",
            "instrument_id": "ETH-USD_UM_XPERP",
            "asset_class": "equity",
        }
        message = T.format_candidate(candidate)
        self.assertIn("OKX USD_UM X-Perp", message)
        self.assertIn("ETH-USD_UM_XPERP", message)
        self.assertIn("Ações/ETF", message)
        self.assertIn("USD/USDC/USDG", message)
        self.assertIn("execução desativada", message)
        self.assertNotIn("SHORT não é executável em spot", message)

    def test_persisted_ids_prevent_duplicate_telegram_alerts(self):
        now = 1800000000
        info = self.instruments()["ETH"]
        info = {**info, "base": "ETH", "volume_24h_contract_quote": 5000}
        candidate = {
            "asset": "ETH", "family": "momentum", "side": "SHORT",
            "signal_t": 1799998200, "signal_close": 3000.0,
            "stop": 3050.0, "target": 2900.0, "max_hold_bars": 8,
            "regime": "bearish", "score": 2, "reason": "momentum negativo",
            "venue": "OKX", "market_type": "USD_UM_XPERP",
            "instrument_id": info["inst_id"],
            "asset_class": "crypto",
        }
        seen = {}
        with mock.patch.object(Q, "_public_universe", return_value=([info], 1)), \
                mock.patch.object(Q, "_fetch_one",
                                  return_value=(info, [candidate], {"status": "VALID"})), \
                mock.patch.object(T, "notify_digest",
                                  side_effect=lambda rows, sender=None: [
                                      {"id": T._signal_id(row), "message_id": 1}
                                      for row in rows]):
            first = Q.scan_okx_xperps(now, seen_ids=seen)
            second = Q.scan_okx_xperps(now + 60, seen_ids=seen)
        self.assertEqual(len(first["telegram_sent"]), 1)
        self.assertEqual(second["telegram_sent"], [])
        self.assertEqual(len(seen), 1)
        self.assertFalse(first["account_settlement_confirmed"])


if __name__ == "__main__":
    unittest.main()


class InstIdReais(unittest.TestCase):
    """(17/11) regressao: os X-Perps reais tem sufixo no instId (resposta publica da OKX vista a 17/11)."""
    REAL = {"instCategory": "1", "category": "1", "ctMult": "1", "ctType": "linear", "ctVal": "0.0001",
            "ctValCcy": "BTC", "expTime": "1933056000000", "instFamily": "BTC-USD_UM_XPERP",
            "instId": "BTC-USD_UM_XPERP-310404", "instType": "FUTURES", "lever": "50", "lotSz": "1", "minSz": "1",
            "ruleType": "xperp", "settleCcy": "USD", "state": "live", "tickSz": "0.1"}

    def test_descobre_ids_com_sufixo(self):
        from engine import quick_opportunities_derivatives as D
        pre = dict(self.REAL, instId="NEW-USD_UM_XPERP-310404", instFamily="NEW-USD_UM_XPERP", ruleType="pre_market")
        out = D.okx_usdc_xperps(request=lambda url, params=None: {"code": "0", "data": [self.REAL, pre]})
        self.assertEqual(list(out), ["BTC"])
        self.assertEqual(out["BTC"]["inst_id"], "BTC-USD_UM_XPERP-310404")
        self.assertTrue(D.is_um_xperp("BTC-USD_UM_XPERP"))
        self.assertFalse(D.is_um_xperp("BTC-USD-SWAP"))
        self.assertFalse(D.is_um_xperp("BTC-USD_UM_XPERP-ABC"))

    def test_seleciona_por_volume_com_ids_reais(self):
        from engine import quick_opportunities_derivatives as D, quick_opportunities_okx as Q
        inst = D.okx_usdc_xperps(request=lambda url, params=None: {"code": "0", "data": [self.REAL]})
        rows = Q.select_liquid_xperps(inst, [{"instId": "BTC-USD_UM_XPERP-310404", "vol24h": "1000", "last": "90000"}])
        self.assertEqual([r["base"] for r in rows], ["BTC"])
        self.assertAlmostEqual(rows[0]["volume_24h_contract_quote"], 1000 * 0.0001 * 90000)
