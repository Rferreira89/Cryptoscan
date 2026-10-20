import unittest
from engine import posmortem as P


def op(i, r, reason="STOP", tp=0, real=None, fase=None, strat="BREAKOUT", t=0, risk=1.0, rs=None):
    x = {"id": f"X{i}", "asset": "AAA", "strategy": strat, "mode": "REAL", "executed": True, "status": "CLOSED",
         "result_r": r if rs is None else rs, "reason": reason, "tp_hit": tp, "closed_at": t or 1000 + i, "risk_usdc": risk}
    if real is not None:
        x["real_r"] = real
    if fase:
        x["fase"] = fase
    return x


class PosMorte(unittest.TestCase):
    def test_execucao_fase_e_padroes(self):
        longo = {"BREAKOUT": {"por_regime": {"lateral": {"n": 30, "avg_r": -.2, "acaso_p95": .1, "metades": [-.1, -.3]}}}}
        led = [op(1, -1.0, fase="lateral"), op(2, -1.0, t=1001), op(3, -1.0, t=1002),
               op(4, None, "BREAKEVEN", 1, real=-.06, rs=.15, strat="BOUNCE_SQUEEZE"),
               {"mode": "PAPER", "executed": True, "status": "CLOSED", "result_r": 5}]
        r = P.relatorio(led, longo, ["BOUNCE_SQUEEZE"])
        self.assertEqual(r["n"], 4)
        o = {x["id"]: x for x in r["ops"]}
        self.assertEqual(o["X1"]["causa"], "fase")
        self.assertEqual(o["X4"]["causa"], "execucao")
        self.assertTrue(any("execução custou" in l for l in o["X4"]["licoes"]))
        self.assertTrue(any("BREAKOUT" in p and "fora do dinheiro real" in p for p in r["padroes"]))
        self.assertTrue(any("perdas em cadeia" in p for p in r["padroes"]))

    def test_mensagens_so_para_operacoes_novas(self):
        st, led = {}, [op(1, -1.0)]
        self.assertEqual(P.novos(st, P.relatorio(led)), [])          # primeira vez: so marca
        led.append(op(2, 1.5, "TP2", 2, strat="TURTLE"))
        m = P.novos(st, P.relatorio(led))
        self.assertEqual(len(m), 1)
        self.assertIn("Pós-morte", m[0])
        self.assertEqual(P.novos(st, P.relatorio(led)), [])

    def test_sem_operacoes(self):
        self.assertEqual(P.relatorio([]), {"n": 0})


if __name__ == "__main__":
    unittest.main()
