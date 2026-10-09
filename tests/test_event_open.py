import unittest

from engine import events, run

EV = [{"name": "Desbloqueio de PUMP", "t": 1_800_000_000, "assets": ["PUMP"],
       "before_h": 48}]


def led(executed=True, status="OPEN", asset="PUMP"):
    return {"ledger": [{"id": "X1", "asset": asset, "status": status,
                        "executed": executed, "stop": 0.005, "kind": "4H"}]}


class EventOpen(unittest.TestCase):
    def test_avisa_uma_vez_dentro_da_janela(self):
        st = led()
        now = EV[0]["t"] - 47 * 3600
        out = events.open_warnings(st, now, EV)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["event"], "EVENT_OPEN")
        self.assertEqual(events.open_warnings(st, now + 600, EV), [])

    def test_fora_da_janela_nao_avisa(self):
        self.assertEqual(events.open_warnings(led(), EV[0]["t"] - 50 * 3600, EV), [])
        self.assertEqual(events.open_warnings(led(), EV[0]["t"] + 60, EV), [])

    def test_so_operacoes_abertas_executadas_do_ativo(self):
        now = EV[0]["t"] - 3600
        for st in (led(executed=False), led(executed=None),
                   led(status="CLOSED"), led(asset="ICP")):
            self.assertEqual(events.open_warnings(st, now, EV), [])

    def test_eventos_de_mercado_ficam_de_fora(self):
        ev = [dict(EV[0], assets=["ALL"])]
        self.assertEqual(events.open_warnings(led(), EV[0]["t"] - 3600, ev), [])

    def test_texto_do_telegram(self):
        e = events.open_warnings(led(), EV[0]["t"] - 3600, EV)[0]
        txt = run.alert_text(e, {}, "")
        self.assertIn("PUMP", txt)
        self.assertIn("hora de Lisboa", txt)
        self.assertIn("não mexe no plano", txt)


if __name__ == "__main__":
    unittest.main()
