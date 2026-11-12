"""(12/11, BNB SHORT_TURTLE recusada pela Bybit: 170140 Order value exceeded lower limit) A ordem minima de 5 USDC a
~660 com lote de 0,001 BNB arredondava para 0,007 BNB = 4,6 USDC < 5. Agora sobe um lote se o risco autorizado deixar."""
import unittest
from engine import executor as X

BNB = {"base_step": "0.001", "quote_step": "0.01", "min_amt": 5.0, "tick": "0.01"}


class Lote(unittest.TestCase):
    def test_caso_bnb_sobe_um_lote(self):
        self.assertAlmostEqual(X.floor_to(5.0 / 660.0, BNB["base_step"]) * 660, 4.62, places=2)   # o erro antigo
        q = X.qty_ordem(5.0, 660.0, BNB, max_quote=20.0)
        self.assertAlmostEqual(q, 0.008)
        self.assertGreaterEqual(q * 660, 5.0)

    def test_recusa_se_passa_o_risco(self):
        with self.assertRaises(X.ExecError) as e:
            X.qty_ordem(5.0, 660.0, BNB, max_quote=5.1)
        self.assertIn("risco autorizado", str(e.exception))
        with self.assertRaises(X.ExecError):
            X.qty_ordem(5.0, 660.0, BNB)                       # sem teto conhecido: nao sobe, recusa claro

    def test_sem_mudanca_quando_ja_chega(self):
        self.assertAlmostEqual(X.qty_ordem(10.0, 660.0, BNB, max_quote=20.0), 0.015)

    def test_teto_vem_do_plano(self):
        """O dimensionamento do piloto poe no plano o valor maximo que o teto permite; o executor so sobe o lote
        ate ai (o executor nao conhece o piloto)."""
        from engine import config, risk, scanner
        c = dict(config.load("config.json"))
        c["capital_usdc"] = 30.0
        c.update(scanner.compounding(c, [], 0))
        p, why = risk.sizing(7.0, 0.07, 1.0, dict(c, piloto_teto_pct=5.0), short=True)
        self.assertIsNotNone(p, why)
        u = p["usdc"]
        self.assertEqual(u["position_usdc"], 5.0)
        self.assertAlmostEqual(u["max_position_usdc"], round(30 * 0.05 / 0.07, 2))
        q = X.qty_ordem(5.0, 660.0, BNB, X.valor_max(u))
        self.assertLessEqual(q * 660 * 0.07, 30 * 0.05 + 1e-9)
        self.assertEqual(X.valor_max(u, cap=6.0), 6.0)
        self.assertIsNone(X.valor_max({}))


if __name__ == "__main__":
    unittest.main()
