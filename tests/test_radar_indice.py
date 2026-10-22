"""Radar de quebras e indice do mercado (22/10)."""
import unittest

from engine import radar, indice
from tools import arena_ringue as AR

H4, DAY = 14400, 86400
T0 = 1_700_006_400 - 1_700_006_400 % DAY


def velas(precos):
    out = []
    for i, p in enumerate(precos):
        out.append({"t": T0 + i * H4, "o": p, "h": p * 1.01, "l": p * 0.99, "c": p, "v": 1.0, "tb": 0.5})
    return out


def diarias(precos):
    return [{"t": T0 + i * DAY, "o": p, "h": p, "l": p, "c": p, "v": 1} for i, p in enumerate(precos)]


class Radar(unittest.TestCase):
    def test_nivel_igual_ao_do_sinal(self):
        c4 = velas([100 + (i % 12) for i in range(180)])
        lo, hi = radar.niveis(c4)
        m = [{"t": x["t"], "o": 1 / x["o"], "h": 1 / x["l"], "l": 1 / x["h"], "c": 1 / x["c"], "v": 1, "tb": 0} for x in c4]
        d = [x for x in AR.B.daily(m) if x["t"] + DAY <= m[-1]["t"] + H4]
        self.assertAlmostEqual(1 / max(x["h"] for x in d[-21:-1]), lo)

    def test_velas_ao_vivo_sem_volume_comprador(self):
        c4 = [dict(x, tb=None) for x in velas([100.0] * 180)]
        self.assertIsNotNone(radar.niveis(c4))

    def test_estados(self):
        c4 = velas([100.0] * 180)
        lo, _ = radar.niveis(c4)
        r = radar.calcular([{"asset": "AAA", "price": lo * 0.99}], {"AAA": c4}, 0)
        self.assertEqual(r["quebras"][0]["estado"], "abaixo do mínimo: sinal se fechar assim")
        r = radar.calcular([{"asset": "AAA", "price": lo * 1.03}], {"AAA": c4}, 0)
        self.assertEqual(r["quebras"][0]["estado"], "a aproximar-se")
        self.assertEqual(radar.calcular([{"asset": "AAA", "price": lo * 1.5}], {"AAA": c4}, 0)["quebras"], [])


class Indice(unittest.TestCase):
    def test_alta_baixa_lateral(self):
        sobe = diarias([100 * 1.004 ** i for i in range(260)])
        desce = diarias([100 * 0.996 ** i for i in range(260)])
        alts_up = {f"A{i}": sobe for i in range(12)}
        a = indice.calcular(sobe, alts_up)
        b = indice.calcular(desce, {f"A{i}": desce for i in range(12)})
        self.assertGreater(a["valor"], 80)
        self.assertEqual(a["fase_regra"], "subida")
        self.assertLess(b["valor"], 20)
        self.assertEqual(b["fase_regra"], "queda")
        self.assertTrue(all(x["ok"] for x in a["falta"]["subida"]))
        self.assertIsNone(indice.calcular(sobe[:100]))

    def test_historico_por_hora(self):
        st = {}
        indice.historico(st, {"valor": 50}, 0)
        indice.historico(st, {"valor": 51}, 100)
        indice.historico(st, {"valor": 52}, 3600)
        self.assertEqual(st["indice_hist"], [[0, 50], [3600, 52]])


if __name__ == "__main__":
    unittest.main()
