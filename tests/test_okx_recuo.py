import sys, os, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import okx_recuo as RC  # noqa: E402


class Recuo(unittest.TestCase):
    def test_sinal_so_com_tendencia_e_rsi_baixo_e_fecha_no_objetivo(self):
        H4 = 14400
        sobe = [100 + i for i in range(80)]                        # diario em subida
        desce = [200 - i for i in range(80)]
        c4 = [{"t": 1000 + i * H4, "o": 10.0, "h": 10.2, "l": 9.8, "c": 10.0} for i in range(40)]
        c4 += [{"t": 1000 + (40 + i) * H4, "o": 10 - 0.2 * i, "h": 10 - 0.2 * i + 0.05, "l": 10 - 0.2 * i - 0.25,
                "c": 10 - 0.2 * (i + 1)} for i in range(10)]        # recuo: RSI baixo
        lista = {"BTC": {"inst": "BTC"}, "XYZ": {"inst": "XYZ"}}
        st = {}
        RC.correr(st, [("XYZ", lista["XYZ"], c4)], lista, 0, diario_f=lambda i: desce if i == "BTC" else sobe)
        self.assertEqual(st["recuo"]["pend"], {})                  # BTC a descer: nada
        st = {}
        m = RC.correr(st, [("XYZ", lista["XYZ"], c4)], lista, 0, diario_f=lambda i: sobe)
        self.assertIn("XYZ", st["recuo"]["pend"])
        self.assertTrue(any("recuo" in x for x in m))
        p = st["recuo"]["pend"]["XYZ"]
        seg = [{"t": p["t_sig"] + H4, "o": p["lim"] * 1.005, "h": p["lim"] * 1.006, "l": p["lim"] * 0.999, "c": p["lim"]},
               {"t": p["t_sig"] + 2 * H4, "o": p["lim"], "h": p["lim"] * 2, "l": p["lim"], "c": p["lim"] * 1.5}]
        RC.correr(st, [("XYZ", lista["XYZ"], c4 + seg)], lista, 0, diario_f=lambda i: sobe)
        self.assertEqual(st["recuo"]["fechadas"][0]["motivo"], "objetivo")
        self.assertEqual(st["recuo"]["resumo"]["metricas"]["n"], 1)
