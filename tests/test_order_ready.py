import unittest

from engine import run


def sig(direction="LONG"):
    return {"id": "ENA-PULLBACK-1", "asset": "ENA", "pair": "ENA/USDC",
            "venue": "Bybit EU", "mode": "REAL", "direction": direction,
            "plan": {"position_usdc": 24.15, "entry_ref": 0.247,
                     "entry_zone": [0.244, 0.247], "stop": 0.2301,
                     "tp": [0.2812, 0.3, 0.32], "partials": [50, 50, 0]}}


class OrderReady(unittest.TestCase):
    def test_bybit_url(self):
        self.assertEqual(run.bybit_url("ENA/USDC"),
                         "https://www.bybit.eu/en-EU/trade/spot/ENA/USDC")

    def test_block_has_copyable_values(self):
        b = run.order_block(sig())
        self.assertIn("<code>24.15</code> USDC", b)
        self.assertIn("compra: <code>0.247</code>", b)
        self.assertIn("Stop-loss: <code>0.2301</code>", b)
        self.assertIn("TP1: <code>0.2812</code>", b)
        self.assertIn("TP2", b)
        self.assertNotIn("TP3", b)          # parcial 0: sem terceira venda
        self.assertIn("venda", run.order_block(sig("SHORT")))

    def test_markup(self):
        s = sig()
        m = run.markup_for({"event": "ISSUED", "id": s["id"]}, s, True)
        self.assertEqual(len(m["inline_keyboard"]), 1)
        self.assertNotIn("url", m["inline_keyboard"][0][0])
        self.assertIsNone(run.markup_for({"event": "STOP", "id": s["id"]}, s, True))
        self.assertIsNone(run.markup_for({"event": "ISSUED", "id": "x"}, s, False))

    def test_deliver_uses_html_and_escapes(self):
        from engine import alerts
        sent = []
        orig = (alerts.send, alerts.configured)
        alerts.send = lambda t, markup=None, html=False: sent.append((t, html))
        alerts.configured = lambda: True
        try:
            s = sig()
            s.update(strategy="PULLBACK", timeframe="4h", score=70)
            s["plan"].update(position_pct=29, risk_pct=3, stop_pct=6.8, rr=2,
                             leverage={"use": 1, "reason": "a<b & c"})
            run.deliver({"alerts": True}, {"signals": {s["id"]: s}},
                        [{"event": "ISSUED", "id": s["id"]}])
        finally:
            alerts.send, alerts.configured = orig
        t, h = sent[0]
        self.assertTrue(h)
        self.assertIn("a&lt;b &amp; c", t)
        self.assertIn("ORDEM PRONTA", t)


if __name__ == "__main__":
    unittest.main()
