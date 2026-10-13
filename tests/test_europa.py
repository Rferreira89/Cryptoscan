"""Servidor europeu: derivados da Binance, conta automatica, Desalavancagem."""
import json
import os
import tempfile
import unittest
from unittest import mock

from engine import account, arena, europa, promo, scanner
from tools import arena_ringue as AR

H4 = 4 * 3600
NOW = 1_800_000_000


def coin(n_oi=10, drop=0.0, funding=-0.0002):
    oi = [(NOW - (n_oi - 1 - i) * H4, 1000.0) for i in range(n_oi)]
    if drop:
        oi[-1] = (oi[-1][0], 1000.0 * (1 + drop))
    return {"funding_now": funding, "funding_h": 8.0,
            "funding": [(NOW - (99 - i) * 28800, 0.0001) for i in range(100)],
            "oi": oi, "oi_usd": 5e7, "chg_24h_pct": -3.0,
            "ls": [(NOW - (99 - i) * H4, 1.0 + i / 100) for i in range(100)]}


class Simbolos(unittest.TestCase):
    def test_base(self):
        self.assertEqual(europa.base_of("BTCUSDT"), "BTC")
        self.assertEqual(europa.base_of("1000PEPEUSDT"), "PEPE")
        self.assertEqual(europa.base_of("1000000MOGUSDT"), "MOG")
        self.assertEqual(europa.base_of("1INCHUSDT"), "1INCH")


class Overlay(unittest.TestCase):
    def test_binance_substitui_okx(self):
        okx = {"venue": "okx", "missing": ["funding"], "funding_rate": 0.0001,
               "liquidations": {"long_usd": 1}, "oi_usd": 1, "basis_pct": 0.1,
               "price_chg_24h_pct": -3.0}
        d = europa.overlay(okx, coin(drop=-0.2), NOW)
        self.assertEqual(d["venue"], "binance")
        self.assertEqual(d["liq_venue"], "okx")
        self.assertEqual(d["funding_rate"], -0.0002)
        self.assertEqual(d["missing"], [])
        self.assertEqual(d["oi_chg_24h_pct"], -20.0)
        self.assertEqual(d["positioning"], "LONG_LIQUIDATION")
        self.assertEqual(d["liquidations"], {"long_usd": 1})
        self.assertEqual(d["ls_ratio"], 1.99)
        self.assertIn("flags", d)

    def test_sem_okx_e_sem_binance(self):
        self.assertIsNone(europa.overlay(None, None, NOW))
        d = europa.overlay(None, coin(), NOW)
        self.assertEqual(d["venue"], "binance")
        self.assertIn("liquidations", d["missing"])

    def test_oi_velho_nao_conta(self):
        c = coin()
        c["oi"] = [(t - 5 * H4, v) for t, v in c["oi"]]
        d = europa.overlay({"venue": "okx", "missing": [], "oi_chg_24h_pct": 3.0}, c, NOW)
        self.assertEqual(d["oi_chg_24h_pct"], 3.0)


class Carregar(unittest.TestCase):
    def test_idade(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "dados.json")
            json.dump({"t": NOW - 60, "moedas": {}}, open(p, "w"))
            self.assertIsNotNone(europa.load(now=NOW, path=p))
            self.assertIsNone(europa.load(now=NOW + 3600, path=p))
            self.assertIsNotNone(europa.load(europa.MAX_AGE_RING, now=NOW + 3600, path=p))
            self.assertIsNone(europa.load(now=NOW, path=os.path.join(d, "x.json")))


class Conta(unittest.TestCase):
    def test_equity(self):
        self.assertEqual(account.equity({"list": [{"totalEquity": "83.664"}]}), 83.66)
        self.assertEqual(account.equity({"list": [{"coin": [{"usdValue": "3"},
                                                            {"usdValue": "80.5"}]}]}), 83.5)
        self.assertIsNone(account.equity({"list": []}))

    def test_capital_automatico(self):
        st = {"capital": 50, "capital_t": 1}
        eu = {"t": NOW, "conta": {"ok": True, "t": NOW - 120, "equity": 83.66,
                                  "usdc_free": 3.98, "trades": {}}}
        out = scanner.apply_account(st, eu, NOW)
        self.assertEqual(st["capital"], 83.66)
        self.assertEqual(st["capital_t"], NOW - 120)
        self.assertEqual(out["usdc_free"], 3.98)

    def test_conta_falhada_ou_velha_nao_mexe(self):
        for c in ({"ok": False}, {"ok": True, "t": NOW - 7200, "equity": 90},
                  {"ok": True, "t": NOW, "equity": 1}):
            st = {"capital": 50, "capital_t": 1}
            scanner.apply_account(st, {"t": NOW, "conta": c}, NOW)
            self.assertEqual(st["capital"], 50)
        self.assertIsNone(scanner.apply_account({}, None, NOW))


class Desalavancagem(unittest.TestCase):
    def setUp(self):
        self.c4 = [{"t": NOW - (300 - i) * H4, "o": 1, "h": 1, "l": 1, "c": 1, "v": 1}
                   for i in range(300)]
        self.base = {"stop": 0.9, "tp": [1.1], "partials": [100], "breakeven": True,
                     "hold_s": 1, "gatilho": "x"}
        AR.CTX["asset"] = "AAA"

    def tearDown(self):
        AR.CTX.update(oi={}, asset=None)

    def oi(self, drop):
        t = self.c4[-1]["t"] + H4
        v = [(t - (9 - i) * H4, 1000.0) for i in range(10)]
        v[-1] = (t, 1000.0 * (1 + drop))
        AR.CTX["oi"] = {"AAA": v}

    def test_sinal(self):
        self.assertIn("BOUNCE_DESALAV", AR.SINAIS)
        self.assertNotIn("BOUNCE_DESALAV", promo.REAL_OK)    # so papel ate provar
        self.assertEqual(arena.persona("BOUNCE_DESALAV"), "Dália")
        with mock.patch.object(AR, "sig_x30", return_value=dict(self.base)):
            self.oi(-0.08)
            s = AR.sig_desalav(self.c4)
            self.assertIn("-8%", s["gatilho"])
            self.oi(-0.02)
            self.assertIsNone(AR.sig_desalav(self.c4))
            AR.CTX["oi"] = {}
            self.assertIsNone(AR.sig_desalav(self.c4))
        with mock.patch.object(AR, "sig_x30", return_value=None):
            self.oi(-0.3)
            self.assertIsNone(AR.sig_desalav(self.c4))

    def test_contexto_ao_vivo(self):
        promo.EU = {"moedas": {"AAA": {"oi": [[1, 2.0]]}}}
        try:
            promo.set_context([], {})
            self.assertEqual(AR.CTX["oi"], {"AAA": [(1, 2.0)]})
        finally:
            promo.EU = None


if __name__ == "__main__":
    unittest.main()
