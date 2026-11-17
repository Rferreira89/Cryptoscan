"""(17/11) BOUNCE_ALVO, sucessor de BOUNCE_LARGO: filtro do 1.o objetivo, sem look-ahead, so papel."""
import random
import unittest

from engine import promo
from tools import arena_ringue as AR
from tools import research_bounce_alvo as BA

H4 = 14400


class _Sim(dict):
    def get(self, *_):
        return True


def serie(seed, n=900):
    rng, p, out = random.Random(seed), 100.0, []
    for i in range(n):
        o = p
        p = p * (1 + rng.gauss(0, 0.03))
        h = max(o, p) * (1 + abs(rng.gauss(0, 0.01)))
        lo = min(o, p) * (1 - abs(rng.gauss(0, 0.01)))
        out.append({"t": 1_700_000_000 + i * H4, "o": o, "h": h, "l": lo, "c": p,
                    "v": 100.0 * (3 if rng.random() < 0.15 else 1)})
    return out


class BounceAlvo(unittest.TestCase):
    def test_alvo_ok(self):
        s = {"stop": 90.0, "tp": [110.0]}
        self.assertTrue(BA.alvo_ok(s, 100.0, 1.0))
        self.assertFalse(BA.alvo_ok(s, 100.0, 1.25))
        self.assertFalse(BA.alvo_ok({"stop": 100.0, "tp": [110.0]}, 100.0, 1.0))

    def test_filtro_so_tira_sinais(self):
        from tools import research_fase_agressiva as FA
        tot = 0
        for sd in range(20):
            c = serie(sd)
            base, alvo = FA.bl_signals(c, _Sim(), 30, 2.0), BA.signals(c, _Sim(), 30, 1.0)
            self.assertTrue(set(alvo) <= set(base))
            tot += len(alvo)
        self.assertGreater(tot, 0)

    def test_sem_look_ahead(self):
        """O sinal decidido no fecho da vela i e o mesmo com a serie cortada em i e com o futuro alterado."""
        vistos = 0
        for sd in range(20):
            c = serie(sd)
            full = BA.signals(c, _Sim(), 30, 1.0)
            for te, s in full.items():
                i = next(k for k, b in enumerate(c) if b["t"] + H4 == te)
                cut = BA.signals(c[:i + 1], _Sim(), 30, 1.0)
                self.assertEqual(cut.get(te), s)
                fut = c[:i + 1] + [dict(b, h=b["h"] * 3, l=b["l"] * 0.3, c=b["c"] * 2, v=b["v"] * 9) for b in c[i + 1:]]
                self.assertEqual(BA.signals(fut, _Sim(), 30, 1.0).get(te), s)
                vistos += 1
        self.assertGreater(vistos, 0)

    def test_sinal_da_arena_igual_ao_da_investigacao(self):
        """A funcao da arena (ultimas 120 velas) da o mesmo filtro de alvo que a investigacao."""
        fn = AR.SUCESSORES_SIGS["BOUNCE_ALVO"]
        for sd in range(20):
            c = serie(sd)
            for i in range(250, len(c)):
                s = fn(c[:i + 1])
                if s:
                    risk = c[i]["c"] - s["stop"]
                    self.assertGreaterEqual(s["tp"][0] - c[i]["c"], 1.0 * risk)
                    self.assertTrue(s["breakeven"])
                    self.assertEqual(s["hold_s"], 5 * 86400)
                    base = AR.sig_bounce_largo(30, 2.0)(c[:i + 1])
                    self.assertEqual(base["stop"], s["stop"])

    def test_so_papel(self):
        k = "BOUNCE_ALVO"
        self.assertIn(k, AR.NEW_SIGS)
        self.assertIn(k, AR.SINAIS)
        self.assertIn(k, AR.PAPEL_ESTUDO)
        self.assertNotIn(k, promo.REAL_OK)
        self.assertNotIn(k, AR.PAPEL_SEM_FILTRO_BTC)
        self.assertEqual(AR.PAPEL_N_MIN[k], 25)
        self.assertIsNone(AR.PAPEL_FASE[k])


if __name__ == "__main__":
    unittest.main()
