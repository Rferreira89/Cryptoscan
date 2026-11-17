import unittest

from engine.quick_opportunities_derivatives import validate_okx_account_config as validar_liquidacao_usdc


class OKXUSDCSettlementTests(unittest.TestCase):
    def test_allows_only_confirmed_usdc_settlement(self):
        self.assertEqual(
            validar_liquidacao_usdc({"code": "0", "data": [{"settleCcy": "USDC"}]}),
            (True, "USDC confirmado"))

    def test_rejects_usd_and_usdg(self):
        for currency in ("USD", "USDG", "USDT", ""):
            ok, reason = validar_liquidacao_usdc(
                {"code": "0", "data": [{"settleCcy": currency}]})
            self.assertFalse(ok)
            self.assertIn("não USDC", reason)

    def test_rejects_missing_or_failed_account_config(self):
        self.assertFalse(validar_liquidacao_usdc(None)[0])
        self.assertFalse(validar_liquidacao_usdc({"code": "500", "data": []})[0])
        self.assertFalse(validar_liquidacao_usdc({"code": "0", "data": []})[0])


if __name__ == "__main__":
    unittest.main()


class XperpsReais(unittest.TestCase):
    """(17/11) regressao: com os campos reais da OKX (instFamily "BTC-USD_UM_XPERP") o executor via 0 contratos."""

    def test_executor_reconhece_os_contratos_reais(self):
        from unittest import mock
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
        import okx_exec as E
        real = {"instId": "XLM-USD_UM_XPERP-310404", "instFamily": "XLM-USD_UM_XPERP", "state": "live",
                "ctType": "linear", "ctVal": "100", "minSz": "1", "lotSz": "1", "tickSz": "0.00001", "lever": "20"}
        pre = dict(real, instId="ABC-USD-SWAP", instFamily="ABC-USD")
        with mock.patch.object(E, "privado", return_value={"data": [{"instId": real["instId"]}, {"instId": pre["instId"]}]}), \
                mock.patch.object(E.A, "get", return_value=[real, pre]):
            xp = E.xperps()
        self.assertEqual(list(xp), ["XLM"])
        self.assertEqual(xp["XLM"]["inst"], "XLM-USD_UM_XPERP-310404")
