import math
import random
import unittest
from unittest import mock

from tools import arena_ringue as R
from tools import filtro_operacoes as FO

H4, DAY = 4 * 3600, 86400


def _c4(n=600, seed=3):
    rng = random.Random(seed)
    px, out = 100.0, []
    for i in range(n):
        o = px
        px *= math.exp(rng.gauss(0, 0.02))
        out.append({"t": 1_700_000_000 + i * H4, "o": o, "h": max(o, px) * 1.005, "l": min(o, px) * 0.995,
                    "c": px, "v": 1.0, "tb": 0.5})
    return out


def _sig(c4):
    """Sinal de teste: so olha para as velas que recebe."""
    if len(c4) % 17:
        return None
    c = c4[-1]["c"]
    return {"stop": c * 0.95, "tp": [c * 1.05], "partials": [100], "breakeven": True, "hold_s": 3 * DAY}


class TestFiltroOperacoes(unittest.TestCase):
    def test_campos_e_fecho_depois_da_entrada(self):
        c4 = _c4()
        above = {(x["t"]) // DAY: True for x in c4}
        with mock.patch.object(R, "_known", return_value=True):
            ops = FO.trades("X", c4, above, 0, _sig)
        self.assertTrue(ops)
        for o in ops:
            self.assertGreater(o["t_fim"], o["t"])
            self.assertAlmostEqual(o["stop_pct"], 5.0, delta=2.5)
        self.assertEqual(R.CTX["asset"], "X")

    def test_sem_look_ahead(self):
        """Cortar o futuro nao muda as operacoes ja fechadas antes do corte."""
        c4 = _c4()
        with mock.patch.object(R, "_known", return_value=True):
            todas = FO.trades("X", c4, {}, 0, _sig)
            parte = FO.trades("X", c4[:400], {}, 0, _sig)
        corte = c4[399]["t"] + H4
        self.assertEqual([o for o in todas if o["t_fim"] <= corte][:len(parte)],
                         [o for o in parte if o["t_fim"] <= corte])


class TestShortEmPrecoReal(unittest.TestCase):
    def test_short_real_e_niveis_convertidos(self):
        from engine import short as SH
        c4 = []
        px = 100.0
        for i in range(600):                       # sobe devagar e depois cai a pique
            o = px
            px *= 1.001 if i < 400 else 0.99
            c4.append({"t": 1_700_000_000 + i * H4, "o": o, "h": max(o, px) * 1.002, "l": min(o, px) * 0.998,
                       "c": px, "v": 1.0, "tb": 0.5})
        m4 = SH.mirror(c4)

        def sig(m):
            if len(m) != 405:
                return None
            c = m[-1]["c"]
            return {"stop": c * 0.9, "tp": [c * 1.3], "partials": [100], "breakeven": True, "hold_s": 30 * DAY}
        ops = FO.trades_short("X", c4, m4, 0, sig)
        self.assertEqual(len(ops), 1)
        o = ops[0]
        self.assertEqual(o["lado"], "SHORT")
        self.assertGreater(o["r"], 0)              # o preco real caiu: o short ganha
        self.assertAlmostEqual(o["stop_pct"], (1 / 0.9 - 1) * 100, delta=1.0)   # stop acima: 1/0,9


if __name__ == "__main__":
    unittest.main()
