"""Perguntas pelo Telegram e leitura por departamentos."""
import unittest

from engine import consultas as C, inbox, run

ROW = {"asset": "SOL", "price": 107.6, "chg_24h": -0.1,
       "analysis": {"1d": {"ema_trend": "UP", "structure": "BULLISH"},
                    "4h": {"structure": "BULLISH", "adx": 30, "rsi": 31,
                           "swing_low": 105.0, "swing_high": 120.0,
                           "volume": {"rvol": 1.6, "buy_share": 0.6, "divergence": None},
                           "liquidity": {"sweep": {"side": "LOW", "level": 105.7, "bars_ago": 2,
                                                   "confirmed": True},
                                         "order_block": {"side": "DEMAND", "zone": [100, 102]},
                                         "fvg_below": None, "fvg_above": [109, 110],
                                         "pools_below": [101], "pools_above": [121]}}},
       "derivatives": {"venue": "binance", "funding_rate": -0.0001, "funding_pctile": 10,
                       "oi_chg_24h_pct": -6, "positioning": "LONG_LIQUIDATION",
                       "ls_ratio": 1.2, "flags": []},
       "decision": {"decision": "NO TRADE", "reason": "sem setup"}}
MACRO = {"estado": "favoravel", "vix": 15, "sp_24h_pct": 0.2, "dxy_5d_pct": -0.1, "us10y": 4.2}
RES = {"universe": [ROW], "macro": MACRO, "conta": {"t": 0, "equity": 83.3, "usdc_free": 4},
       "config": {"capital_usdc": 83.3},
       "promo": {"campeao": "BOUNCE_G0", "campeoes": ["BOUNCE_G0"], "perdidas_7d": []},
       "arena": {"classificacao": [
           {"id": "BOUNCE_G0", "persona": "Gaspar", "name": "Bounce", "estado": "A COMPETIR",
            "forma": {"n": 26, "avg_r": 0.77}},
           {"id": "BREAKOUT", "persona": "Bruno", "name": "Quebra", "estado": "MORTA",
            "morte": {"motivo": "x"}, "forma": {"n": 40, "avg_r": -0.3}}]}}


class Departamentos(unittest.TestCase):
    def test_cores(self):
        d = {x["dep"]: x for x in C.departments(ROW, MACRO)}
        self.assertEqual(len(d), 8)
        self.assertEqual(d["Tendência e estrutura"]["cor"], C.G)
        self.assertEqual(d["Liquidez e smart money"]["cor"], C.G)
        self.assertIn("order block de compra", d["Liquidez e smart money"]["texto"])
        self.assertEqual(d["Volume e fluxo"]["cor"], C.G)
        self.assertEqual(d["Derivados"]["cor"], C.G)          # funding negativo
        self.assertEqual(d["Sobrevenda"]["cor"], C.G)
        self.assertEqual(d["Macroeconomia"]["cor"], C.G)
        self.assertEqual(d["Força relativa"]["cor"], C.Y)     # sem velas
        self.assertEqual(C.departments({"analysis": {}}), [])

    def test_resistencia_perto_e_vermelho(self):
        a4 = dict(ROW["analysis"]["4h"], swing_high=108.5)
        self.assertEqual(C.dep_sr(a4, 107.6)[0], C.R)


class Comandos(unittest.TestCase):
    def test_respostas(self):
        t = C.answer("/porque sol", RES, {})
        self.assertIn("<b>SOL</b>", t)
        self.assertIn("moeda=SOL", t)
        self.assertIn("Sem sinal agora", t)
        self.assertIn("não está entre", C.answer("/porque XYZ", RES, {}))
        self.assertIn("Diz-me a moeda", C.answer("/porque", RES, {}))
        r = C.answer("/ringue", RES, {})
        self.assertIn("🏆 Gaspar", r)
        self.assertIn("Memorial: Bruno", r)
        self.assertIn("favorável", C.answer("/macro", RES, {}))
        self.assertIn("83.30", C.answer("/conta", RES, {}))
        led = [{"asset": "SOL", "status": "OPEN", "executed": True, "entry": 100,
                "stop": 95, "risk_usdc": 1.0, "strategy": "BOUNCE_X30"}]
        h = C.answer("/hoje", RES, {"ledger": led})
        self.assertIn("SOL", h)
        self.assertIn("+1.52R", h)
        self.assertIn("/porque", C.answer("/ajuda", RES, {}))
        self.assertIsNone(C.answer("/fechei SOL 100", RES, {}))
        self.assertIsNone(C.answer("olá", RES, {}))

    def test_inbox_responde_e_botao(self):
        ups = [{"update_id": 1, "message": {"chat": {"id": 7}, "text": "/macro", "date": 1}},
               {"update_id": 2, "callback_query": {"id": "c", "data": "q|p|SOL",
                                                   "message": {"chat": {"id": 7}}}}]
        out = inbox.apply({"ledger": []}, ups, "7", RES)
        self.assertEqual(len(out), 2)
        self.assertTrue(out[0][2] and out[1][2])               # HTML
        self.assertEqual(out[1][1], "c")
        sent = []
        inbox.reply([("a", None), ("<b>b</b>", None, True)],
                    lambda t, html=False: sent.append((t, html)))
        self.assertEqual(sent, [("a", False), ("<b>b</b>", True)])

    def test_botoes_no_alerta(self):
        e = {"event": "ISSUED", "id": "SOL-X-1", "asset": "SOL", "t": 1}
        m = run.markup_for(e, {}, True)
        rows = m["inline_keyboard"]
        self.assertEqual(rows[1][0]["callback_data"], "q|p|SOL")
        self.assertIn("#moeda=SOL", rows[1][1]["url"])


if __name__ == "__main__":
    unittest.main()
