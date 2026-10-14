"""Vendas a descoberto pela margem spot: espelho, plano real, decisoes."""
import unittest
from unittest import mock

from engine import execucao, promo, run
from tools import arena_ringue as AR

H4 = 14400
NOW = 1_800_000_000
CFG = {"fee_pct": 0.25, "risk_pct": 1.0, "max_position_pct": 25.0, "swing_leverage": 10.0,
       "capital_usdc": 85.0, "fixed_position_usdc": 18.82, "max_risk_usdc": 2.57,
       "min_order_usdc": 5.0, "shorts": True}


def bars(n=320):
    return [{"t": NOW - (n - i) * H4, "o": 100, "h": 101, "l": 99, "c": 100, "v": 10, "tb": 5}
            for i in range(n)]


class Espelho(unittest.TestCase):
    def test_sinal_ao_vivo_em_precos_reais(self):
        # no espelho (1/preco) o plano tem stop abaixo e objetivo acima
        fake = lambda m4: {"stop": 1 / 110, "tp": [1 / 90], "partials": [100], "hold_s": 1,
                           "gatilho": "x"}
        f = AR.short_live(fake)
        s = f(bars(), 100.0)
        self.assertEqual(s["side"], "SHORT")
        self.assertAlmostEqual(s["stop"], 110)
        self.assertAlmostEqual(s["tp"][0], 90)
        self.assertIsNone(f(bars(), 120.0))            # preco ja acima do stop

    def test_plano_de_short(self):
        p, why = promo.short_plan_for({"stop": 110, "tp": [95, 90]}, 100, CFG)
        self.assertIsNone(why)
        self.assertEqual(p["side"], "SHORT")
        self.assertGreater(p["stop"], p["entry_zone"][1])
        self.assertLess(p["tp"][0], p["entry_ref"])
        self.assertGreater(p["risk_usdc"], 0)
        self.assertIsNone(promo.short_plan_for({"stop": 99, "tp": [95]}, 100, CFG)[0])

    def test_lutadores_no_registo(self):
        for k in AR.SHORT_SIGS:
            self.assertIn(k, AR.SINAIS)
            self.assertIn(k, promo.REAL_OK)
        out = AR.run({"BTC": bars(10)}, CFG, NOW, days=1)
        self.assertIn("SHORT_X30", out["lutadores"])


class Decisoes(unittest.TestCase):
    def test_campeao_short_vira_decisao_short(self):
        st = {}
        rows = [{"asset": "AAA", "price": 100.0, "decision": {"venue": {"name": "Bybit EU"}}}]
        sig = {"stop": 110, "tp": [95, 90], "side": "SHORT", "t_sig": NOW, "gatilho": "g"}
        with mock.patch.object(promo, "registry", lambda: {"SHORT_X30": lambda c, p, cfg=None: dict(sig)}), \
                mock.patch.object(promo, "set_context", lambda r, b: None):
            out = promo.decisions(st, rows, {"AAA": bars()}, CFG, NOW + 60, ["SHORT_X30"], True,
                                  lambda a: None)
        self.assertEqual(out["AAA"]["decision"], "SHORT")
        self.assertEqual(out["AAA"]["plan"]["side"], "SHORT")
        self.assertTrue(any("descoberto" in n for n in out["AAA"]["notes"]))

    def test_sem_botao_executar_nos_shorts(self):
        execucao.READY = True
        try:
            e = {"event": "ISSUED", "id": "AAA-SHORT_X30-1", "asset": "AAA", "t": 1}
            m = run.markup_for(e, {"direction": "SHORT"}, True)
            self.assertNotIn("e|", str(m))
            m = run.markup_for(e, {"direction": "LONG"}, True)
            self.assertIn("e|", str(m))
        finally:
            execucao.READY = False


if __name__ == "__main__":
    unittest.main()
