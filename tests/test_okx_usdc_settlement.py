import unittest

from tools.okx_exec import validar_liquidacao_usdc


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
