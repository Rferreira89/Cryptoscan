"""(19/11) Estudo das rapidas (1 h): eventos so com o passado, entrada na vela seguinte, custo de ida e volta."""
import unittest

from tools import estudo_rapidas_1h as ER

H = 3600


def velas(n=40, p=1.0):
    return [{"t": k * H, "o": p, "h": p * 1.001, "l": p * 0.999, "c": p, "v": 100.0} for k in range(n)]


class Eventos(unittest.TestCase):
    def test_rutura_com_volume(self):
        c = velas()
        c[30].update(h=1.02, c=1.015, v=500.0)
        self.assertIn(("R1", 30, 1), ER.eventos_em("X", c, 30))

    def test_nao_ve_o_futuro(self):
        c = velas()
        c[31].update(h=1.05, c=1.05, v=900.0)            # evento so na vela 31
        self.assertEqual([e for e in ER.eventos_em("X", c, 30) if e[0] == "R1"], [])
        c2 = [dict(x) for x in c]
        for k in range(31, 40):
            c2[k].update(o=9.0, h=9.0, l=9.0, c=9.0)    # mudar o futuro nao muda o evento da vela 30
        self.assertEqual(ER.eventos_em("X", c, 30), ER.eventos_em("X", c2, 30))

    def test_atraso_face_ao_btc(self):
        c = velas()
        evs = ER.eventos_em("ALT", c, 30, btc_ret={30 * H: 0.025})
        self.assertIn(("R3", 30, 1), evs)
        self.assertNotIn("R3", [e[0] for e in ER.eventos_em("BTC", c, 30, btc_ret={30 * H: 0.025})])


class Simulacao(unittest.TestCase):
    def test_entrada_na_abertura_seguinte_e_stop_com_salto(self):
        c = velas()
        c[31].update(o=0.98, l=0.97)                     # abre abaixo do stop de um LONG
        ret, r, mot = ER.simular(c, 30, 1, 4)
        self.assertEqual(mot, "stop")
        self.assertLess(r, -1.0 + 1e-9)

    def test_custo_e_de_ida_e_volta(self):
        self.assertAlmostEqual(ER.CUSTOS["okx_perp"], 0.002)
        self.assertAlmostEqual(ER.CUSTOS["bybit_spot_modelo"], 0.007)


if __name__ == "__main__":
    unittest.main()
