"""(19/11) O estudo por duracao usa o MESMO sinal da SHORT_TURTLE ao vivo e simula sem olhar para o futuro."""
import math
import unittest

from tools import arena_ringue as AR
from tools import estudo_duracao_short_turtle as ED

H4, DAY = 14400, 86400


def serie(n=700, seed=3):
    import random
    rng = random.Random(seed)
    p, out = 1.0, []
    t0 = 1_700_000_000 // DAY * DAY
    for k in range(n):
        p *= math.exp(rng.gauss(-0.0008, 0.02))
        h, l = p * (1 + abs(rng.gauss(0, 0.01))), p * (1 - abs(rng.gauss(0, 0.01)))
        out.append({"t": t0 + k * H4, "o": p, "h": h, "l": l, "c": p * (1 + rng.gauss(0, 0.003)), "v": 1.0, "tb": 0.5})
    for x in out:
        x["h"], x["l"] = max(x["h"], x["o"], x["c"]), min(x["l"], x["o"], x["c"])
    return out


class Equivalencia(unittest.TestCase):
    def test_sinais_iguais_aos_do_ringue(self):
        live = AR.short_live(AR.SHORT_SIGS["SHORT_TURTLE"])
        for seed in (3, 5, 8):
            c4 = serie(seed=seed)
            meus = {i: (s, t) for i, s, t in ED.sinais(c4)}
            ringue = {}
            for i in range(200, len(c4)):
                sig = live(c4[:i + 1], c4[i]["c"])
                if sig:
                    ringue[i] = (sig["stop"], sig["tp"][0])
            meus = {i: v for i, v in meus.items() if i >= 200}
            self.assertEqual(sorted(meus), sorted(ringue), seed)
            self.assertTrue(ringue, "a serie de teste tem de dar sinais")
            for i in ringue:
                self.assertAlmostEqual(meus[i][0], ringue[i][0], places=9)
                self.assertAlmostEqual(meus[i][1], ringue[i][1], places=9)


class SemFuturo(unittest.TestCase):
    def test_entrada_na_vela_seguinte_e_stop_pessimista(self):
        c4 = [{"t": k * H4, "o": 1.0, "h": 1.0, "l": 1.0, "c": 1.0} for k in range(10)]
        c4[2].update(h=1.2, l=0.7)                     # stop e objetivo na mesma vela: conta o stop
        traj, fim = ED.simular(c4, 0, 1.1, 0.8, juro_dia=0)
        self.assertEqual(fim["motivo"], "stop")
        self.assertLess(fim["r"], -1)                  # custos e deslize por cima do risco
        self.assertEqual(len(traj), 1)

    def test_fechar_ao_fim_de_k_usa_so_o_que_ja_aconteceu(self):
        c4 = [{"t": k * H4, "o": 1.0, "h": 1.0, "l": 1.0, "c": 1.0 - 0.001 * k} for k in range(200)]
        traj, fim = ED.simular(c4, 0, 1.5, 0.1, juro_dia=0)
        self.assertEqual(fim["motivo"], "tempo")
        r1 = ED.r_ao_fim_de(traj, fim, 1)
        r5 = ED.r_ao_fim_de(traj, fim, 5)
        self.assertLess(r1, r5)                        # o preco foi descendo: mais tempo, mais ganho
        self.assertEqual(ED.r_ao_fim_de(traj, fim, 20), fim["r"])

    def test_aberta_no_fim_dos_dados_fica_de_fora(self):
        c4 = [{"t": k * H4, "o": 1.0, "h": 1.0, "l": 1.0, "c": 1.0} for k in range(20)]
        self.assertIsNone(ED.simular(c4, 0, 1.5, 0.5)[1])

    def test_juro_conta_o_tempo(self):
        c4 = [{"t": k * H4, "o": 1.0, "h": 1.0, "l": 1.0, "c": 1.0} for k in range(200)]
        _, sem = ED.simular(c4, 0, 1.5, 0.1, juro_dia=0)
        _, com = ED.simular(c4, 0, 1.5, 0.1, juro_dia=0.0003)
        self.assertLess(com["r"], sem["r"])


if __name__ == "__main__":
    unittest.main()
