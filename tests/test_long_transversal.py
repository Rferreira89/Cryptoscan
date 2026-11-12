"""(12/11) Motor LONG transversal: sem olhar para o futuro, stop/tempo corretos, custos no R, formato da avaliacao."""
import unittest

from tools import long_transversal as L

D = 86400


def serie(n, f):
    out = []
    for i in range(n):
        c = f(i)
        out.append({"t": i * D, "o": c, "h": c * 1.01, "l": c * 0.99, "c": c, "v": 1e7, "n": 6})
    return out


class Transversal(unittest.TestCase):
    def test_sair_por_stop_e_tempo(self):
        dd = serie(30, lambda i: 100.0)
        px, t = L.sair(dd, 5, 99.5, 10)
        self.assertEqual(px, 99.5)                       # o minimo do dia toca o stop
        px, t = L.sair(dd, 5, 90.0, 10)
        self.assertEqual((px, t), (100.0, 14 * D + D - 1))

    def test_sem_futuro(self):
        """Mudar o futuro nao muda os indicadores de hoje."""
        a = serie(300, lambda i: 100 + i)
        b = [dict(x) for x in a]
        for x in b[250:]:
            x.update(c=1.0, o=1.0, h=1.0, l=1.0)
        ia, ib = L.indicadores(a), L.indicadores(b)
        self.assertEqual(ia[249], ib[249])

    def test_custos_e_formato(self):
        btc = serie(400, lambda i: 100 * 1.001 ** i)
        forte = serie(400, lambda i: 100 * 1.004 ** i)
        ops = L.operacoes({"BTC": btc, "AAA": forte}, {})
        self.assertTrue(ops)
        o = ops[0]
        for k in ("k", "fam", "a", "t", "t_fim", "r", "stop", "fase"):
            self.assertIn(k, o)
        self.assertNotEqual(o["a"], "BTC")
        self.assertGreater(o["t_fim"], o["t"])


if __name__ == "__main__":
    unittest.main()
