"""(31/10) Papel por fase do mercado: short no minimo de 55 velas em lateral; trio comprado na subida."""
import unittest

from engine import papel_fases as F

DAY, H4 = 86400, 14400
NOW = 1793500000


def diario(serie):
    t0 = (NOW // DAY - len(serie) - 1) * DAY
    return [{"t": t0 + i * DAY, "o": c, "h": c, "l": c, "c": c} for i, c in enumerate(serie)]


def c4(n=80, base=1.0, ult=None):
    t0 = (NOW // H4 - n - 1) * H4
    out = [{"t": t0 + i * H4, "o": base, "h": base * 1.01, "l": base * 0.99, "c": base} for i in range(n)]
    if ult is not None:
        out[-1] = dict(out[-1], c=ult, l=min(ult, out[-1]["l"]))
    return out


class Fase(unittest.TestCase):
    def test_subida_lateral_queda(self):
        self.assertEqual(F.fase(diario([100 + i for i in range(260)]), NOW), 1)
        self.assertEqual(F.fase(diario([400 - i for i in range(260)]), NOW), -1)
        self.assertEqual(F.fase(diario([100 + i for i in range(200)] + [300 - 0.5 * i for i in range(60)]), NOW), 0)
        self.assertIsNone(F.fase(diario([1] * 100), NOW))


class Lateral(unittest.TestCase):
    def test_short_no_minimo_so_em_lateral(self):
        st = {}
        F.lateral(F._st(st), {"ALGO": c4(ult=0.95)}, 1, NOW)               # subida: nada
        self.assertFalse(st["papel_fases"]["lateral"]["abertas"])
        st = {}
        F.lateral(F._st(st), {"ALGO": c4(ult=0.95)}, 0, NOW)
        op = st["papel_fases"]["lateral"]["abertas"]["ALGO"]
        self.assertGreater(op["stop"], op["entrada"])
        self.assertLess(op["alvo"], op["entrada"])
        self.assertIn("short em mercado lateral", F.pop_avisos(st)[0])

    def test_fecha_no_objetivo_com_r_positivo(self):
        st = {}
        velas = c4(ult=0.95)
        F.lateral(F._st(st), {"ALGO": velas}, 0, NOW)
        op = st["papel_fases"]["lateral"]["abertas"]["ALGO"]
        velas = velas + [{"t": velas[-1]["t"] + H4, "o": 0.95, "h": 0.951, "l": op["alvo"] - 0.001, "c": op["alvo"]}]
        F.lateral(F._st(st), {"ALGO": velas}, 0, NOW + H4)
        f = st["papel_fases"]["lateral"]["fechadas"][0]
        self.assertEqual(f["motivo"], "objetivo")
        self.assertGreater(f["r"], 1.8)

    def test_stop_da_r_negativo(self):
        st = {}
        velas = c4(ult=0.95)
        F.lateral(F._st(st), {"ALGO": velas}, 0, NOW)
        op = st["papel_fases"]["lateral"]["abertas"]["ALGO"]
        velas = velas + [{"t": velas[-1]["t"] + H4, "o": 0.95, "h": op["stop"] + 0.01, "l": 0.94, "c": 0.96}]
        F.lateral(F._st(st), {"ALGO": velas}, 0, NOW + H4)
        self.assertLess(st["papel_fases"]["lateral"]["fechadas"][0]["r"], -1.0)


class Subida(unittest.TestCase):
    def test_entra_e_sai_com_a_fase(self):
        st = {}
        s = F._st(st)
        F.subida(s, 1, {"BTC": 100, "ETH": 10, "SOL": 1}, NOW)
        self.assertTrue(s["subida"]["pos"])
        F.subida(s, 1, {"BTC": 110, "ETH": 11, "SOL": 1.1}, NOW + DAY)          # continua
        self.assertTrue(s["subida"]["pos"])
        F.subida(s, 0, {"BTC": 110, "ETH": 11, "SOL": 1.1}, NOW + 2 * DAY)
        self.assertIsNone(s["subida"]["pos"])
        self.assertAlmostEqual(s["subida"]["fechadas"][0]["ret_pct"], 9.5, places=1)
        m = F.pop_avisos(st)
        self.assertIn("entra comprado", m[0])
        self.assertIn("+9.5%", m[-1])

    def test_sem_dados_de_fase_nao_sai(self):
        st = {}
        s = F._st(st)
        F.subida(s, 1, {"BTC": 100, "ETH": 10, "SOL": 1}, NOW)
        F.subida(s, None, {"BTC": 90, "ETH": 9, "SOL": 0.9}, NOW + DAY)
        self.assertTrue(s["subida"]["pos"])


class Resumo(unittest.TestCase):
    def test_update_e_resumo(self):
        st = {}
        r = F.update(st, {"ALGO": c4(ult=0.95)}, diario([100 + i for i in range(200)] + [300 - 0.5 * i for i in range(60)]),
                     {"BTC": 1, "ETH": 1, "SOL": 1}, NOW)
        self.assertEqual(r["fase"], "lateral")
        self.assertEqual(r["lateral"]["abertas"], ["ALGO"])
        self.assertFalse(r["subida"]["comprado"])


if __name__ == "__main__":
    unittest.main()
