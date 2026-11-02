"""Estudo da conta de BOUNCE_AMPLITUDE: sem look-ahead (o sinal so ve velas
fechadas, entra na abertura seguinte, e cortar o futuro nao muda as operacoes
ja fechadas) e a conta nunca tem mais posicoes do que as vagas."""
import random
import unittest

from tools import arena_ringue as AR
from tools import conta_bounce_amplitude as CB

H4, DAY = AR.H4, AR.DAY
T0 = 1_600_000_000 - 1_600_000_000 % DAY


def serie(seed, n=700):
    r = random.Random(seed)
    p, out = 100.0, []
    for i in range(n):
        o = p
        p = max(1.0, p * (1 + r.gauss(0, 0.02)))
        out.append({"t": T0 + i * H4, "o": o, "h": max(o, p) * 1.005, "l": min(o, p) * 0.995,
                    "c": p, "v": 1.0, "tb": 0.5})
    return out


VISTO = []


def sinal_teste(c4):
    """Compra quando o fecho fica abaixo do minimo da vela anterior."""
    VISTO.append(c4[-1]["t"])
    b, a = c4[-1], c4[-2]
    if b["c"] >= a["l"]:
        return None
    return {"stop": b["c"] * 0.95, "tp": [b["c"] * 1.03], "partials": [100],
            "breakeven": True, "hold_s": 3 * DAY}


class ContaBounceAmplitude(unittest.TestCase):
    def setUp(self):
        self.bars = {f"M{k}": serie(k) for k in range(4)}
        self.above = {(T0 // DAY) + d: True for d in range(-5, 400)}

    def test_sem_look_ahead(self):
        VISTO.clear()
        ops = CB.operacoes(self.bars, self.above, fn=sinal_teste, amp=False)
        self.assertGreater(len(ops), 20)
        for o in ops:
            c4 = self.bars[o["a"]]
            i = next(k for k, x in enumerate(c4) if x["t"] == o["t"])
            self.assertIn(c4[i - 1]["t"], VISTO)       # sinal na vela fechada anterior
            self.assertGreater(o["fim"], o["t"])
        corte = T0 + 400 * H4
        curtas = {a: [x for x in c4 if x["t"] < corte] for a, c4 in self.bars.items()}
        ops2 = CB.operacoes(curtas, self.above, fn=sinal_teste, amp=False)
        # por moeda, ate a primeira operacao que atravessa o corte (essa nao fecha na serie
        # curta e deixa a moeda livre mais cedo: nao e look-ahead, e o fim dos dados)
        lim = {}
        for o in ops:
            if o["fim"] >= corte - H4:
                lim[o["a"]] = min(lim.get(o["a"], o["t"]), o["t"])
        antes = [(o["a"], o["t"], o["r"]) for o in ops if o["t"] < lim.get(o["a"], corte)]
        depois = [(o["a"], o["t"], o["r"]) for o in ops2 if o["t"] < lim.get(o["a"], corte)]
        self.assertTrue(antes)
        self.assertEqual(antes, depois)

    def test_conta_respeita_vagas(self):
        ops = [{"a": "X", "t": 0, "fim": 10, "ret": 0.1}, {"a": "Y", "t": 0, "fim": 10, "ret": 0.1},
               {"a": "Z", "t": 5, "fim": 20, "ret": -0.5}]
        m, q, n = CB.conta(ops, 0, 100, vagas=1, rng=random.Random(1))
        self.assertEqual(n, 1)
        self.assertAlmostEqual(m, 1.1)
        m2, _, n2 = CB.conta(ops, 0, 100, vagas=2, rng=random.Random(1))
        self.assertEqual(n2, 2)
        self.assertAlmostEqual(m2, 1.1)
        m3, q3, n3 = CB.conta(ops, 0, 100, vagas=3, alav=3.0, rng=random.Random(1))
        self.assertEqual(n3, 3)
        self.assertAlmostEqual(m3, 1 + 3 * (0.1 / 3 * 2 - 0.5 / 3))


if __name__ == "__main__":
    unittest.main()
