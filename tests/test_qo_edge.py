"""(17/11) Edge Detection do Quick Opportunities: sem olhar para a frente, divisao desenho/teste, acaso e Holm."""
import random
import unittest

from tools import qo_edge as E

BAR = 1800


def serie(n=900, seed=1, tendencia=0.0):
    rng = random.Random(seed)
    p, out = 100.0, []
    for i in range(n):
        o = p
        p = max(1.0, p * (1 + tendencia + rng.gauss(0, 0.01)))
        h, l = max(o, p) * (1 + abs(rng.gauss(0, 0.004))), min(o, p) * (1 - abs(rng.gauss(0, 0.004)))
        out.append({"t": 1_790_000_000 // BAR * BAR + i * BAR, "o": o, "h": h, "l": l, "c": p,
                    "v": 1000 * (1 + abs(rng.gauss(0, 1)))})
    return out


class QOEdge(unittest.TestCase):
    def setUp(self):
        self._n = E.N_ACASO

    def tearDown(self):
        E.N_ACASO = self._n

    def test_sinal_nao_olha_para_a_frente(self):
        cs = serie()
        base = [(i, c["family"], c["side"]) for i, c in E.sinais(cs) if i < 500]
        mexido = [dict(b) for b in cs]
        for b in mexido[501:]:
            b.update(c=b["c"] * 3, h=b["h"] * 3, v=b["v"] * 50)
        depois = [(i, c["family"], c["side"]) for i, c in E.sinais(mexido) if i < 500]
        self.assertEqual(base, depois)

    def test_sem_sobreposicao_por_familia_e_lado(self):
        cs = serie(seed=3)
        vistos = {}
        for i, c in E.sinais(cs):
            k = (c["family"], c["side"])
            if k in vistos:
                self.assertGreater(i, vistos[k] + E.QO.MAX_HOLD_BARS)
            vistos[k] = i

    def test_avaliar_separa_desenho_e_teste_e_da_veredicto(self):
        series = {f"A{k}": serie(seed=k) for k in range(4)}
        ts = sorted(b["t"] for cs in series.values() for b in cs)
        corte = ts[0] + int(0.6 * (ts[-1] - ts[0]))
        E.N_ACASO = 20
        res = E.avaliar(series, corte)
        self.assertTrue(res)
        for k, v in res.items():
            self.assertIn(v["veredicto"], ("CANDIDATA A PAPEL", "AMOSTRA INSUFICIENTE", "SEM VANTAGEM DEMONSTRADA"))
            self.assertGreaterEqual(v["p_holm"], 0)
            for mes in v["meses_teste"]:
                self.assertGreaterEqual(mes, __import__("time").strftime("%Y-%m", __import__("time").gmtime(corte)))

    def test_holm_e_criterios(self):
        res = {"a|LONG": {"percentil_acaso": 99.5, "n_teste": 150, "r_desenho": 0.1, "r_teste": 0.1},
               "b|LONG": {"percentil_acaso": 99.5, "n_teste": 50, "r_desenho": 0.1, "r_teste": 0.1},
               "c|SHORT": {"percentil_acaso": 60, "n_teste": 500, "r_desenho": 0.1, "r_teste": 0.01},
               "d|SHORT": {"percentil_acaso": 99.9, "n_teste": 500, "r_desenho": -0.1, "r_teste": 0.2}}
        E.N_ACASO = 200
        E.holm(res)
        self.assertEqual(res["a|LONG"]["veredicto"], "CANDIDATA A PAPEL")
        self.assertEqual(res["b|LONG"]["veredicto"], "AMOSTRA INSUFICIENTE")
        self.assertEqual(res["c|SHORT"]["veredicto"], "SEM VANTAGEM DEMONSTRADA")
        self.assertEqual(res["d|SHORT"]["veredicto"], "SEM VANTAGEM DEMONSTRADA")    # desenho negativo
        self.assertGreaterEqual(res["c|SHORT"]["p_holm"], res["a|LONG"]["p_holm"])

    def test_nao_importa_executores(self):
        import sys
        self.assertNotIn("okx_exec", sys.modules.get("tools.qo_edge").__dict__)
        with open(E.__file__, encoding="utf-8") as f:
            src = f.read()
        for proibido in ("okx_exec", "executor", "privado(", "BYBIT_TRADE"):
            self.assertNotIn(proibido, src.replace("sem executor", ""))


if __name__ == "__main__":
    unittest.main()
