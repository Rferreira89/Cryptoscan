"""Afinacao H10: o short do racio moeda/BTC (no espelho) so usa velas fechadas,
dispara quando o racio real esteve muito ACIMA da media e vira para baixo com o
BTC em queda, nao dispara fora da queda e devolve um plano valido no espelho."""
import unittest
from unittest import mock

from engine import short as SH
from tools import arena_ringue as AR
from tools.afinacao_h10_racio_short import GRID, racio_m_z, racio_short

H4, DAY = AR.H4, AR.DAY
T0 = 1_600_000_000 - 1_600_000_000 % DAY


def series(n=300, jump_at=290, jump=1.06, down=0.99):
    """BTC parado; a moeda oscila, sobe `jump` na vela jump_at e depois cai."""
    btc, coin = [], []
    for k in range(n):
        t = T0 + k * H4
        btc.append({"t": t, "o": 100, "h": 101, "l": 99, "c": 100, "v": 1.0})
        p = 10 * (1.01 if k % 2 else 0.99)
        if k == jump_at:
            p = 10 * jump
        if k == jump_at + 1:
            p = 10 * jump * down
        coin.append({"t": t, "o": p, "h": p * 1.005, "l": p * 0.995, "c": p, "v": 1.0})
    return btc, coin


class H10(unittest.TestCase):
    def setUp(self):
        self.btc, coin = series()
        self.m4 = SH.mirror(coin)
        AR.CTX.update(btc=self.btc)
        p = mock.patch.object(AR, "_fase_btc", return_value="queda")
        self.fase = p.start()
        self.addCleanup(p.stop)

    def test_fires_on_turn_down_after_stretch(self):
        f = racio_short(*GRID["Q1"])
        hits = [k for k in range(200, len(self.m4)) if f(self.m4[:k + 1])]
        self.assertEqual(hits, [291])
        s = f(self.m4[:292])
        e = self.m4[291]["c"]
        self.assertLess(s["stop"], e)                       # no espelho: stop abaixo
        self.assertGreater(s["tp"][0], e * 1.01)
        z0, r0, r1, m = racio_m_z(self.m4[:292], 120)
        self.assertLessEqual(z0, -2.5)
        self.assertAlmostEqual(s["tp"][0], e * m / r1)
        # em precos reais: vende abaixo do stop e o objetivo e mais abaixo
        self.assertGreater(1 / s["stop"], 1 / e)
        self.assertLess(1 / s["tp"][0], 1 / e)

    def test_only_in_queda(self):
        self.fase.return_value = "lateral"
        self.assertIsNone(racio_short(*GRID["Q1"])(self.m4[:292]))
        self.assertIsNotNone(racio_short(*GRID["Q6"])(self.m4[:292]))
        self.fase.return_value = "subida"
        self.assertIsNone(racio_short(*GRID["Q6"])(self.m4[:292]))

    def test_no_lookahead(self):
        f = racio_short(*GRID["Q1"])
        a = f(self.m4[:292])
        btc2, coin2 = series(n=320)              # o futuro muda e o sinal nao
        coin2[300]["c"] = 1.0
        AR.CTX.update(btc=btc2)
        self.assertEqual(f(SH.mirror(coin2)[:292]), a)

    def test_rsi_filter_blocks_overbought(self):
        # uma subida de 20% numa vela deixa o RSI real muito alto: fora
        btc, coin = series(jump=1.20)
        AR.CTX.update(btc=btc)
        m4 = SH.mirror(coin)
        self.assertIsNone(racio_short(*GRID["Q1"])(m4[:292]))
        self.assertIsNotNone(racio_short(*GRID["Q4"])(m4[:292]))

    def test_missing_btc_bar(self):
        AR.CTX.update(btc=[b for b in self.btc if b["t"] != self.m4[250]["t"]])
        self.assertIsNone(racio_short(*GRID["Q1"])(self.m4[:292]))


if __name__ == "__main__":
    unittest.main()
