"""Afinacao H15: o PULLBACK so na fase de subida. A fase e a do dia fechado
anterior ao sinal (sem look-ahead), o score minimo filtra, o slippage e o de
0,1% por lado e o lutador (P2) entra a mercado na abertura seguinte com o
stop, os objetivos e as parciais do plano do motor."""
import unittest
from unittest import mock

from tools import arena_ringue as AR
from tools import afinacao_h15_recuo_subida as M

H4, DAY = AR.H4, AR.DAY
T0 = 1_700_006_400 - 1_700_006_400 % DAY


def velas(n=600, px=100.0):
    return [{"t": T0 + k * H4, "o": px, "h": px * 1.01, "l": px * 0.99, "c": px,
             "v": 1.0, "tb": 0.5} for k in range(n)]


def cand(i, score=70):
    t = T0 + i * H4 + H4
    return {"asset": "X", "i": i, "t": t, "strategy": "PULLBACK", "score": score,
            "plan": {"entry_zone": [99.0, 100.0], "stop": 95.0, "tp": [105.0, 110.0],
                     "partials": [50, 50], "risk_pct": 1.0}}


class FaseEScore(unittest.TestCase):
    def setUp(self):
        self.c4 = velas()
        dia = (cand(300)["t"] - DAY) // DAY
        M._G["rmap"] = {dia: "subida"}
        self.above = {k: True for k in range(T0 // DAY - 2, T0 // DAY + 200)}

    def test_fase_do_dia_anterior(self):
        cs = {"X": [cand(300)]}
        with mock.patch.object(M.B, "simulate", return_value={"status": "CLOSED", "r": 1.0,
                                                              "entry_t": 1}) as sim:
            self.assertEqual(len(M.ring_trades(cs, {"X": self.c4}, {}, self.above, ("subida",), 65)), 1)
            self.assertEqual(M.ring_trades(cs, {"X": self.c4}, {}, self.above, ("lateral",), 65), [])
            self.assertEqual(sim.call_args.kwargs["slip_pct"], 0.1)

    def test_score_minimo(self):
        cs = {"X": [cand(300, score=50)]}
        with mock.patch.object(M.B, "simulate", return_value={"status": "CLOSED", "r": 1.0,
                                                              "entry_t": 1}):
            self.assertEqual(M.ring_trades(cs, {"X": self.c4}, {}, self.above, ("subida",), 65), [])
            self.assertEqual(len(M.ring_trades(cs, {"X": self.c4}, {}, self.above, ("subida",), 0)), 1)

    def test_lutador_entra_na_abertura_seguinte(self):
        self.c4[301]["o"] = 100.5
        with mock.patch.object(AR, "_known", return_value=True), \
                mock.patch.object(M, "B_START", 0):
            trs = M.fighter_trades({"X": [cand(300)]}, {"X": self.c4}, self.above, 65)
        self.assertEqual(len(trs), 1)
        self.assertEqual(trs[0]["t"], self.c4[301]["t"])
        self.assertAlmostEqual(trs[0]["geo"]["stop"], 95.0 / 100.5 - 1)
        self.assertEqual(trs[0]["geo"]["partials"], [50, 50])

    def test_plano(self):
        p = M.recuo_plano(cand(1)["plan"], 70)
        self.assertEqual((p["stop"], p["tp"], p["hold_s"]), (95.0, [105.0, 110.0], 30 * DAY))


if __name__ == "__main__":
    unittest.main()
