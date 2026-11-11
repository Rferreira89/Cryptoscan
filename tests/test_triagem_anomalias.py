import math
import random
import unittest

from tools import triagem_anomalias as T

DAY, H4 = 86400, 4 * 3600


def _bars(n_moedas=16, dias=260, seed=4, t0=None):
    rng = random.Random(seed)
    t0 = t0 if t0 is not None else T.CORTE - 200 * DAY
    out = {}
    for k in range(n_moedas):
        px, rows = 100.0, []
        for i in range(dias * 6):
            o = px
            px *= math.exp(rng.gauss(0, 0.01))
            rows.append({"t": t0 + i * H4, "o": o, "h": max(o, px), "l": min(o, px), "c": px,
                         "v": 100 + rng.random(), "tb": 50 + rng.random()})
        out[f"M{k}"] = rows
    return out


class TestCorte(unittest.TestCase):
    def test_recortar(self):
        b = T.recortar(_bars(n_moedas=2))
        for c in b.values():
            self.assertTrue(c)
            self.assertLessEqual(c[-1]["t"] + H4, T.CORTE)

    def test_retorno_futuro_nao_atravessa_o_corte(self):
        b = _bars(n_moedas=2)
        p = T.painel(b)
        d_ult = T.CORTE // DAY - 1
        self.assertIsNone(T._fwd(p, "M0", d_ult - 2, 3))
        self.assertIsNotNone(T._fwd(p, "M0", d_ult - 30, 3))

    def test_sem_look_ahead_e_sem_reserva(self):
        """Mudar tudo o que vem depois do corte nao muda a triagem."""
        b1 = _bars()
        b2 = {a: [dict(x) for x in c] for a, c in b1.items()}
        for c in b2.values():
            for x in c:
                if x["t"] + H4 > T.CORTE:
                    x["c"] *= 3.0
                    x["o"] *= 0.5
        fn = dict((n, f) for _, n, f in T._sinais())["momento 7 dias"]
        r1 = T.seccional(T.painel(T.recortar(b1)), fn, 3)
        r2 = T.seccional(T.painel(T.recortar(b2)), fn, 3)
        self.assertEqual(r1, r2)
        self.assertTrue(r1[0])

    def test_sinal_do_dia_so_usa_o_passado(self):
        b = _bars(n_moedas=3)
        p = T.painel(b)
        d = sorted(p["M0"])[120]
        antes = {n: f(p, "M0", d) for _, n, f in T._sinais()}
        for k in list(p["M0"]):
            if k > d:
                p["M0"][k] = dict(p["M0"][k], c=p["M0"][k]["c"] * 5, o=1.0, v=1e9, tbf=0.99, fund=-1)
        depois = {n: f(p, "M0", d) for _, n, f in T._sinais()}
        self.assertEqual(antes, depois)

    def test_custos_sao_os_da_bybit(self):
        self.assertAlmostEqual(T.CUSTO_IDA_VOLTA, 2 * (0.0025 + 0.001))


if __name__ == "__main__":
    unittest.main()
