import unittest

from engine import paper_bounce as P, run

TF = 14400


def bars_with_bounce(n=120, t0=1_800_000_000 // TF * TF):
    """Subida lenta, queda forte (RSI < 25) e uma vela de recuperacao."""
    out, p = [], 100.0
    for i in range(n - 12):
        o = p
        p *= 1.002
        out.append({"t": t0 + i * TF, "o": o, "h": p * 1.003, "l": o * 0.997,
                    "c": p, "v": 10})
    for _ in range(11):                       # queda forte
        o = p
        p *= 0.975
        out.append({"t": t0 + len(out) * TF, "o": o, "h": o * 1.001,
                    "l": p * 0.998, "c": p, "v": 10})
    o = p                                      # recuperacao acima do maximo anterior
    prev_h = out[-1]["h"]
    p = prev_h * 1.004
    out.append({"t": t0 + len(out) * TF, "o": o, "h": p * 1.001, "l": o * 0.999,
                "c": p, "v": 10})
    return out


class PaperBounce(unittest.TestCase):
    def test_sinal_na_ultima_vela(self):
        c4 = bars_with_bounce()
        s = P.signal(c4)
        self.assertIsNotNone(s)
        self.assertLess(s["rsi"], 25)
        self.assertLess(s["stop"], c4[-1]["c"])
        self.assertGreater(s["tp"][0], c4[-1]["c"] * 1.01)
        self.assertIsNone(P.signal(c4[:-1]))   # sem vela de recuperacao

    def test_ciclo_completo_so_papel(self):
        c4 = bars_with_bounce()
        now = c4[-1]["t"] + TF + 60
        st = {}
        row = {"asset": "AAA", "price": c4[-1]["c"], "analysis": None}
        res, ev = P.update(st, [row], {"AAA": c4}, True, now)
        self.assertEqual([e["event"] for e in ev], ["BOUNCE_PAPER_BUY"])
        self.assertFalse(ev[0]["real"])
        self.assertIn("AAA", res["G0"]["open"])
        self.assertIn("AAA", res["V3"]["open"])
        # a mesma vela nao abre segunda vez
        _, ev2 = P.update(st, [row], {"AAA": c4}, True, now + 300)
        self.assertEqual(ev2, [])
        # 3 dias de velas paradas: sai por tempo
        last, more = c4[-1]["c"], []
        for k in range(1, 20):
            more.append({"t": c4[-1]["t"] + k * TF, "o": last, "h": last * 1.001,
                         "l": last * 0.999, "c": last, "v": 10})
        res, ev3 = P.update(st, [row], {"AAA": c4 + more}, True,
                            more[-1]["t"] + TF + 60)
        sells = [e for e in ev3 if e["event"] == "BOUNCE_PAPER_SELL"]
        self.assertEqual(len(sells), 1)
        self.assertEqual(sells[0]["reason"], "TIME")
        self.assertEqual(res["G0"]["n"], 1)
        self.assertEqual(res["G0"]["open"], [])

    def test_sem_mercado_nao_entra(self):
        c4 = bars_with_bounce()
        st = {}
        _, ev = P.update(st, [{"asset": "AAA", "price": c4[-1]["c"]}],
                         {"AAA": c4}, False, c4[-1]["t"] + TF + 60)
        self.assertEqual(ev, [])

    def test_sinal_antigo_nao_entra(self):
        c4 = bars_with_bounce()
        st = {}
        _, ev = P.update(st, [{"asset": "AAA", "price": c4[-1]["c"]}],
                         {"AAA": c4}, True, c4[-1]["t"] + 3 * TF)
        self.assertEqual(ev, [])

    def test_mensagens_marcadas_papel_sem_botoes(self):
        e = {"t": 1, "event": "BOUNCE_PAPER_BUY", "id": "bounce-AAA-1",
             "asset": "AAA", "pair": "AAA/USDC", "price": 1.0, "stop": 0.9,
             "tp": [1.1, 1.2], "rsi": 22.0, "real": False}
        txt = run.alert_text(e, {}, "")
        self.assertIn("PAPEL", txt)
        self.assertIn("não é para executar", txt)
        self.assertIsNone(run.markup_for(e, {}, False))
        txt2 = run.alert_text({"event": "BOUNCE_PAPER_SELL", "asset": "AAA",
                               "reason": "TIME", "r": -0.3}, {}, "")
        self.assertIn("-0.30R", txt2)


if __name__ == "__main__":
    unittest.main()
