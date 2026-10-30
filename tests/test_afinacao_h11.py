"""Afinacao H11: a reversao do intervalo no diario so usa velas fechadas, so se
avalia na vela de 4H que fecha o dia, dispara no terco inferior de um intervalo
com o dia a virar para cima e o BTC lateral, e devolve um plano valido."""
import unittest
from unittest import mock

from tools import arena_ringue as AR
from tools.afinacao_h11_intervalo_diario import GRID, intervalo_diario

H4, DAY = AR.H4, AR.DAY
T0 = 1_600_000_000 - 1_600_000_000 % DAY
DIAS = 120


def series(dias=DIAS, ultimo=(97.0, 104.0, 96.0, 103.0)):
    """Moeda a oscilar entre 95 e 125 (intervalo de 30%, sem tendencia); o
    penultimo dia fecha em baixo (96..99) e o ultimo dia e `ultimo` (o, h, l, c)."""
    out = []
    for d in range(dias):
        ph = d % 10
        mid = 100 + 4 * ph if ph < 5 else 120 - 4 * (ph - 5)
        o, h, l, c = mid, mid + 3, mid - 3, mid + 1
        if d == dias - 2:
            o, h, l, c = 99.0, 100.0, 96.0, 97.0
        if d == dias - 1:
            o, h, l, c = ultimo
        t = T0 + d * DAY
        px = [o, (o + c) / 2, l, h, (o + c) / 2, c]
        for k in range(6):
            p0 = px[k - 1] if k else o
            p1 = px[k]
            out.append({"t": t + k * H4, "o": p0, "h": max(p0, p1, h if k == 3 else p1),
                        "l": min(p0, p1, l if k == 2 else p1), "c": p1, "v": 1.0, "tb": 0.5})
    return out


class H11(unittest.TestCase):
    def setUp(self):
        AR.CTX.update(daily={}, asset="TESTE")
        p = mock.patch.object(AR, "_fase_btc", return_value="lateral")
        self.fase = p.start()
        self.addCleanup(p.stop)
        self.c4 = series()

    def test_fires_on_daily_turn_in_lower_third(self):
        s = intervalo_diario(*GRID["R1"])(self.c4)
        self.assertIsNotNone(s)
        e = self.c4[-1]["c"]
        self.assertLess(s["stop"], 95)                     # abaixo do minimo do intervalo
        self.assertLess(s["stop"], e)
        self.assertGreater(s["tp"][0], e * 1.015)
        self.assertEqual(s["partials"], [100])
        self.assertEqual(s["hold_s"], 10 * DAY)
        s5 = intervalo_diario(*GRID["R5"])(self.c4)
        self.assertEqual(len(s5["tp"]), 2)
        self.assertGreater(s5["tp"][1], s5["tp"][0])

    def test_only_on_daily_close(self):
        f = intervalo_diario(*GRID["R1"])
        for k in range(1, 6):                              # velas de 4H a meio do dia
            self.assertIsNone(f(self.c4[:-k]))

    def test_no_trigger_without_turn(self):
        c4 = series(ultimo=(97.0, 99.5, 96.0, 98.0))       # fecha abaixo do maximo de ontem
        self.assertIsNone(intervalo_diario(*GRID["R1"])(c4))
        self.assertIsNotNone(intervalo_diario(*GRID["R2"])(c4))   # fecho > fecho de ontem

    def test_not_in_upper_part(self):
        c4 = series(ultimo=(97.0, 116.0, 96.0, 115.0))     # acima do terco inferior
        self.assertIsNone(intervalo_diario(*GRID["R1"])(c4))

    def test_only_in_lateral(self):
        self.fase.return_value = "subida"
        self.assertIsNone(intervalo_diario(*GRID["R1"])(self.c4))
        self.assertIsNotNone(intervalo_diario(*GRID["R6"])(self.c4))
        self.fase.return_value = "queda"
        self.assertIsNone(intervalo_diario(*GRID["R6"])(self.c4))

    def test_trend_blocks(self):
        c4 = []
        for k, x in enumerate(series()):                   # tendencia forte: ADX alto
            m = 1.004 ** (k // 6)
            c4.append({**x, "o": x["o"] * m, "h": x["h"] * m, "l": x["l"] * m, "c": x["c"] * m})
        self.assertIsNone(intervalo_diario(*GRID["R1"])(c4))

    def test_no_lookahead(self):
        f = intervalo_diario(*GRID["R1"])
        a = f(self.c4)
        fut = self.c4 + [{**x, "t": x["t"] + 6 * H4, "c": 1.0, "l": 0.5} for x in self.c4[-6:]]
        self.assertEqual(f(fut[:len(self.c4)]), a)


if __name__ == "__main__":
    unittest.main()
