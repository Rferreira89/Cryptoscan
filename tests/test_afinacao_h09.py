"""Afinacao H9: o sinal do racio moeda/BTC so usa velas fechadas, dispara
quando o racio esteve muito abaixo da media e vira, e devolve um plano
valido (stop abaixo da entrada, objetivo na media do racio)."""
import unittest

from tools import arena_ringue as AR
from tools.afinacao_h09_racio import GRID, racio_var, racio_z

H4, DAY = AR.H4, AR.DAY
T0 = 1_600_000_000 - 1_600_000_000 % DAY


def series(n=300, drop_at=290, drop=0.85, up=1.02):
    """BTC parado; a moeda oscila e cai `drop` na vela drop_at, depois vira."""
    btc, coin = [], []
    for k in range(n):
        t = T0 + k * H4
        btc.append({"t": t, "o": 100, "h": 101, "l": 99, "c": 100, "v": 1.0})
        p = 10 * (1.01 if k % 2 else 0.99)
        if k == drop_at:
            p = 10 * drop
        if k == drop_at + 1:
            p = 10 * drop * up
        coin.append({"t": t, "o": p, "h": p * 1.005, "l": p * 0.995, "c": p, "v": 1.0})
    return btc, coin


class H09(unittest.TestCase):
    def setUp(self):
        self.btc, self.coin = series()
        AR.CTX.update(btc=self.btc)

    def test_fires_on_turn_after_deviation(self):
        f = racio_var(*GRID["R1"])
        hits = [k for k in range(200, len(self.coin)) if f(self.coin[:k + 1])]
        self.assertEqual(hits, [291])
        s = f(self.coin[:292])
        e = self.coin[291]["c"]
        self.assertLess(s["stop"], e)
        self.assertGreater(s["tp"][0], e * 1.01)
        z0, r0, r1, m = racio_z(self.coin[:292], 120)
        self.assertLessEqual(z0, -2)
        self.assertAlmostEqual(s["tp"][0], e * m / r1)

    def test_no_lookahead(self):
        f = racio_var(*GRID["R1"])
        a = f(self.coin[:292])
        btc2, coin2 = series(n=320)          # o futuro muda e o sinal nao
        coin2[300]["c"] = 1.0
        AR.CTX.update(btc=btc2)
        self.assertEqual(f(coin2[:292]), a)

    def test_rsi_filter_blocks_oversold(self):
        # a queda de 15% numa vela deixa o RSI muito baixo: o filtro "fora da
        # sobrevenda" (RSI >= 35) nao deixa entrar
        self.assertIsNone(racio_var(*GRID["R2"])(self.coin[:292]))

    def test_missing_btc_bar(self):
        AR.CTX.update(btc=[b for b in self.btc if b["t"] != self.coin[250]["t"]])
        self.assertIsNone(racio_var(*GRID["R1"])(self.coin[:292]))


if __name__ == "__main__":
    unittest.main()
