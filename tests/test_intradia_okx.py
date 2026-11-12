"""(12/11) Intradiario OKX: sem retrospetiva (o sinal so ve velas fechadas), stop primeiro quando a vela toca os dois,
custos e financiamento, saida no prazo, criterio fixo. Dados sinteticos."""
import inspect
import random
import unittest

from tools import intradia_okx as I

H = 3600


def serie(n=900, deriva=0.0, semente=1, vol=0.01):
    rnd, c, out = random.Random(semente), 100.0, []
    for k in range(n):
        o = c
        c = o * (1 + deriva + rnd.gauss(0, vol))
        out.append({"t": 1_700_000_000 // H * H + k * H, "o": o, "h": max(o, c) * 1.003, "l": min(o, c) * 0.997, "c": c, "v": 100 + rnd.random()})
    return out


class SemRetrospetiva(unittest.TestCase):
    def test_sinal_nao_muda_com_o_futuro(self):
        c = serie()
        ind = I.indicadores(c)
        a = I.sinais(c, ind, 700)
        c2 = c[:701] + [dict(x, c=x["c"] * 5, h=x["h"] * 5) for x in c[701:]]
        self.assertEqual(a, I.sinais(c2, I.indicadores(c2), 700))

    def test_stop_primeiro_quando_a_vela_toca_os_dois(self):
        c = [{"t": k * H, "o": 100, "h": 100, "l": 100, "c": 100, "v": 1} for k in range(3)]
        c[2] = {"t": 2 * H, "o": 100, "h": 110, "l": 90, "c": 100, "v": 1}
        r, _, _ = I.simular(c, 0, "LONG", 1.0)
        self.assertLess(r, -1.0)                                 # stop (-1R) mais custos

    def test_custos_e_prazo(self):
        c = [{"t": k * H, "o": 100, "h": 100.1, "l": 99.9, "c": 100, "v": 1} for k in range(40)]
        r, te, ts = I.simular(c, 0, "SHORT", 1.0)
        self.assertEqual((ts - te) // H, I.HOLD)                 # sai ao fim de 24 h
        self.assertAlmostEqual(r, -(2 * I.CUSTO_LADO + I.FUNDING_8H * I.HOLD / 8) / 0.02, places=6)


class Criterio(unittest.TestCase):
    def test_ruido_nao_passa(self):
        ops = []
        for s in range(6):
            ops += I.operacoes(serie(n=3000, semente=s), f"M{s}")
        linhas, _ = I.avaliar(ops, min(o["t"] for o in ops), max(o["t"] for o in ops), reps=200)
        self.assertFalse(any(l["candidata"] for l in linhas))
        self.assertTrue(all(l["lado"] in ("LONG", "SHORT") for l in linhas))

    def test_so_investigacao(self):
        src = inspect.getsource(I)
        for proibido in ("urlopen", "API_KEY", "/trade/", "privado("):
            self.assertNotIn(proibido, src)


if __name__ == "__main__":
    unittest.main()
