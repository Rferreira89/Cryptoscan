"""Diversificacao por familia, prova real, oportunidades e meta."""
import unittest
from unittest import mock

from engine import consultas, meta, promo

H4 = 14400
NOW = 1_800_000_000
CFG = {"fee_pct": 0.25, "risk_pct": 1.0, "max_position_pct": 25.0, "swing_leverage": 10.0,
       "capital_usdc": 85.0, "fixed_position_usdc": 18.82, "max_risk_usdc": 2.57, "min_order_usdc": 5.0}


def bars(n=60):
    return [{"t": NOW - (n - i) * H4, "o": 100, "h": 101, "l": 99, "c": 100, "v": 10} for i in range(n)]


class Familias(unittest.TestCase):
    def test_familias(self):
        self.assertEqual(promo.family("BOUNCE_X30"), "sobrevenda")
        self.assertEqual(promo.family("TURTLE_R2"), "tendencia")
        self.assertEqual(promo.family("SHORT_X30"), "short")
        self.assertEqual(promo.family("SQUEEZE_BB"), "volatilidade")

    def test_maximo_por_familia(self):
        led = [{"mode": "REAL", "status": "OPEN", "executed": True, "strategy": "BOUNCE_X30"},
               {"mode": "REAL", "status": "OPEN", "executed": True, "strategy": "BOUNCE_G0"}]
        st = {"ledger": led}
        rows = [{"asset": "AAA", "price": 100.0, "decision": {"venue": {"name": "Bybit EU"}}},
                {"asset": "BBB", "price": 100.0, "decision": {"venue": {"name": "Bybit EU"}}}]
        sig = {"stop": 95, "tp": [110], "t_sig": NOW, "gatilho": "g"}
        reg = {"BOUNCE_FLUXO": lambda c, p, cfg=None: dict(sig) if False else None,
               "TURTLE": lambda c, p, cfg=None: dict(sig)}
        reg["BOUNCE_FLUXO"] = lambda c, p, cfg=None: dict(sig)
        with mock.patch.object(promo, "registry", lambda: reg), \
                mock.patch.object(promo, "set_context", lambda r, b: None):
            out = promo.decisions(st, rows, {"AAA": bars(), "BBB": bars()}, CFG, NOW + 60,
                                  ["BOUNCE_FLUXO"], True, lambda a: None)
        self.assertEqual(out, {})                          # sobrevenda ja tem 2 abertas
        self.assertIn("diversificação", st["promo_lost"][-1]["reason"])
        st2 = {"ledger": led}
        with mock.patch.object(promo, "registry", lambda: reg), \
                mock.patch.object(promo, "set_context", lambda r, b: None):
            out = promo.decisions(st2, rows[:1], {"AAA": bars()}, CFG, NOW + 60,
                                  ["TURTLE"], True, lambda a: None)
        self.assertIn("AAA", out)                          # outra familia entra


class ProvaReal(unittest.TestCase):
    def test_suspende_quem_falha_no_real(self):
        led = [{"strategy": "BOUNCE_X30", "status": "CLOSED", "result_r": -0.8} for _ in range(8)]
        st = {"ledger": led, "arena": {"forma": {"lutadores": {
            "BOUNCE_X30": {"n": 90, "avg_r": 0.49, "acaso_p95": -0.05}}}, "mortos": {}, "status": {}}}
        self.assertIn("BOUNCE_X30", promo.suspended(st))
        with mock.patch.object(promo, "registry", lambda: {"BOUNCE_X30": 1}):
            self.assertNotIn("BOUNCE_X30", promo.champions(st))
        st["ledger"] = led[:5]
        self.assertEqual(promo.suspended(st), {})


class OportunidadesMeta(unittest.TestCase):
    def test_oportunidades(self):
        res = {"universe": [{"asset": a, "eligible": True, "analysis": {"4h": {"rsi": r}}}
                            for a, r in (("A", 28), ("B", 45), ("C", 75))]}
        t = consultas.answer("/oportunidades", res, {})
        self.assertIn("A: RSI 28", t)
        self.assertIn("C: RSI 75", t)

    def test_meta(self):
        m = meta.progress(None, 83.59)
        self.assertEqual(m["marco"], 100)
        self.assertAlmostEqual(m["cenarios"][1][1] / 12, 16.1, delta=0.2)   # 5% ao mes
        self.assertIn("primeiro milhão", consultas.answer("/meta", {"conta": {"equity": 83.59}}, {}))
        self.assertIsNone(meta.progress(None, 0))


if __name__ == "__main__":
    unittest.main()
