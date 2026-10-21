"""Afinacao H7: o short do rompimento falhado so usa velas fechadas, dispara
no primeiro fecho de volta abaixo do maximo de 20 dias e devolve um plano
valido no espelho (stop real acima da entrada)."""
import unittest

from engine import short as SH
from tools import arena_ringue as AR
from tools.afinacao_h07_falhado import GRID, falha_core, falhado_var

H4, DAY = AR.H4, AR.DAY


def bars(n=400, brk=380, back=2):
    """Lateral com ruido, rompimento na vela `brk` e regresso abaixo do nivel
    `back` velas depois."""
    out, t = [], 1_600_000_000 - 1_600_000_000 % DAY
    for k in range(n):
        p = 100 + (3 if k % 7 < 3 else -3)
        if brk <= k < brk + back:
            p = 105
        out.append({"t": t + k * H4, "o": p, "h": p * 1.01, "l": p * 0.99, "c": p,
                    "v": 1.0, "tb": 0.5})
    return out


class H07(unittest.TestCase):
    def test_fires_on_first_close_back_below(self):
        c = bars(back=2)
        i = 382
        hits = [k for k in range(300, len(c)) if falha_core(c[:k + 1], 2)]
        self.assertEqual(hits, [i])
        hi20, b, stop = falha_core(c[:i + 1], 2)
        self.assertEqual(b, 380)
        self.assertLess(c[i]["c"], hi20)
        self.assertGreater(stop, max(x["h"] for x in c[380:i + 1]))
        # K=1 nao ve uma falha 2 velas depois
        self.assertIsNone(falha_core(c[:i + 1], 1))

    def test_no_lookahead(self):
        c = bars()
        for i in range(300, len(c) - 1):
            fut = [dict(x, c=x["c"] * 3, h=x["h"] * 3, l=x["l"] * 3, o=x["o"] * 3)
                   for x in c[i + 1:]]
            self.assertEqual(falha_core(c[:i + 1], 6), falha_core((c[:i + 1] + fut)[:i + 1], 6))

    def test_mirror_plan(self):
        c = bars()
        m = SH.mirror(c)
        i = 382
        for k, cfg in GRID.items():
            p = falhado_var(*cfg)(m[:i + 1])
            if cfg[0] < 2:
                self.assertIsNone(p, k)
                continue
            self.assertIsNotNone(p, k)
            # no espelho: stop abaixo da entrada; em precos reais, acima
            self.assertLess(p["stop"], m[i]["c"])
            self.assertGreater(1 / p["stop"], c[i]["c"])
            self.assertLess(m[i]["c"], p["tp"][0])
            self.assertEqual(len(p["tp"]), len(p["partials"]))
            self.assertLessEqual(p["hold_s"], 5 * DAY)


if __name__ == "__main__":
    unittest.main()
