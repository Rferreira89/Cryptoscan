import unittest

from engine import backtest as B
from tools import autopsia_racio_disp as A

H4 = B.H4


def _serie(n, t0=1_700_000_000 - 1_700_000_000 % H4):
    return [{"t": t0 + i * H4, "o": 100 + i, "h": 101 + i, "l": 99 + i, "c": 100.5 + i, "v": 1} for i in range(n)]


class TestAutopsiaRacioDisp(unittest.TestCase):
    def test_px_so_velas_fechadas(self):
        s = _serie(10)
        ts = [x["t"] for x in s]
        # no fecho da vela 3 (= abertura da 4) o preco e o fecho da vela 3, nunca o da 4
        self.assertEqual(A._px(s, ts, s[4]["t"]), s[3]["c"])
        # a meio da vela 4 ainda so se conhece a vela 3
        self.assertEqual(A._px(s, ts, s[4]["t"] + H4 // 2), s[3]["c"])
        self.assertIsNone(A._px(s, ts, s[0]["t"]))

    def test_resumo_decompoe_racio_e_btc(self):
        trs = [{"asset": "X", "t": 0, "r": -1.0, "saida": "STOP", "tp_tocado": False, "mfe_r": 0, "horas": 8,
                "stop_pct": 3, "tp_r": 1.5, "moeda_pct": -5, "btc_pct": -3, "racio_pct": -2.1, "btc7d_pct": 1},
               {"asset": "Y", "t": H4, "r": 1.0, "saida": "TP1", "tp_tocado": True, "mfe_r": 1.5, "horas": 30,
                "stop_pct": 3, "tp_r": 1.5, "moeda_pct": 5, "btc_pct": 1, "racio_pct": 3.9, "btc7d_pct": -1}]
        r = A.resumo(trs, {})
        self.assertEqual(r["racio_x_btc"]["racio_desce/btc_desce"], {"n": 1, "r": -1.0})
        self.assertEqual(r["racio_x_btc"]["racio_sobe/btc_sobe"], {"n": 1, "r": 1.0})
        self.assertEqual(r["perdedoras_com_racio_a_subir_pct"], 0.0)


if __name__ == "__main__":
    unittest.main()
