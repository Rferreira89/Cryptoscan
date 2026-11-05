"""(05/11) Base multi-estrategia (preparacao isolada): registo, etiquetas, bloqueio, tamanho pelo risco com alavancagem
efetiva minima e teto de 10x, tetos globais, stops obrigatorios, monitorizacao e degradacao."""
import unittest
from engine import multiestrategia as M

INFO = {"ctVal": 1.0, "minSz": 0.01, "lotSz": 0.01}
REG = {"corretora": "okx", "tetos": {"bruta_max": 3.0, "risco_aberto_max": 6.0},
       "estrategias": {"h46": {"estado": "real", "real": True, "fracao": 0.5, "risco_pct": 1.0, "max_pos": 3, "bruta_max": 3.0, "alav_max": 10},
                       "tfs": {"estado": "papel", "fracao": 0.5, "risco_pct": 0.5, "max_pos": 5, "bruta_max": 0.5, "alav_max": 2}}}


class Registo(unittest.TestCase):
    def test_valido(self):
        self.assertEqual(M.valida_registo(REG), [])
        self.assertTrue(M.e_real(REG, "h46")); self.assertFalse(M.e_real(REG, "tfs")); self.assertFalse(M.e_real(REG, "xyz"))

    def test_erros(self):
        r = {"tetos": {"bruta_max": 0}, "estrategias": {"A!": {"estado": "real", "risco_pct": 5, "alav_max": 20, "fracao": 1.2}}}
        e = " | ".join(M.valida_registo(r))
        for t in ("tetos.bruta_max", "tetos.risco_aberto_max", "codigo invalido", "interruptor real", "risco_pct", "alav_max", "somam"):
            self.assertIn(t, e)


class Etiquetas(unittest.TestCase):
    def test_ida_e_volta(self):
        c = M.etiqueta("tfs", 7, 1793000000)
        self.assertTrue(c.isalnum()); self.assertLessEqual(len(c), 32)
        self.assertEqual(M.dono(c), "tfs")
        self.assertIsNone(M.dono("ordem-manual-123")); self.assertIsNone(M.dono(None))
        with self.assertRaises(ValueError):
            M.etiqueta("TFS", 1, 1)


class Bloqueio(unittest.TestCase):
    def test_uma_estrategia_por_instrumento(self):
        pos = {"WLD-USD_UM_XPERP": "h46"}
        self.assertEqual(M.pode_abrir(pos, "AAA", "tfs"), (True, ""))
        ok, m = M.pode_abrir(pos, "WLD-USD_UM_XPERP", "tfs"); self.assertFalse(ok); self.assertIn("h46", m)
        self.assertFalse(M.pode_abrir(pos, "WLD-USD_UM_XPERP", "h46")[0])


class Tamanho(unittest.TestCase):
    def test_alavancagem_efetiva_e_a_minima(self):
        t = M.tamanho(20.0, 1.0, 100.0, 92.0, INFO)                # stop 8%: nocional 2,5 -> 1x
        self.assertTrue(t["cabe"]); self.assertEqual(t["alav"], 1); self.assertAlmostEqual(t["nocional"], 2.0)
        t = M.tamanho(20.0, 1.0, 100.0, 99.5, INFO)                # stop 0,5%: nocional 40 -> 2x
        self.assertEqual(t["alav"], 2); self.assertLessEqual(t["risco_pct_efetivo"], 1.0)

    def test_teto_de_10x_e_da_estrategia(self):
        t = M.tamanho(20.0, 2.0, 100.0, 99.9, INFO)                # pediria 400 USD (20x): limitado a 10x
        self.assertLessEqual(t["nocional"], 200.0 + 1e-9); self.assertLessEqual(t["alav"], 10)
        self.assertLess(t["risco_pct_efetivo"], 2.0)                 # o risco fica abaixo do pedido, nunca acima
        t = M.tamanho(20.0, 2.0, 100.0, 99.9, INFO, alav_max_estr=2)
        self.assertLessEqual(t["alav"], 2)

    def test_minimo(self):
        t = M.tamanho(20.0, 1.0, 100.0, 92.0, {"ctVal": 1, "minSz": 1, "lotSz": 1})
        self.assertFalse(t["cabe"]); self.assertIn("minimo", t["motivo"])


class Tetos(unittest.TestCase):
    def test_estrategia_e_corretora(self):
        e = REG["estrategias"]["tfs"]
        ab = [{"cod": "tfs", "nocional": 4.0, "risco_usd": 0.1}]
        self.assertFalse(M.cabe_nos_tetos(ab, {"cod": "tfs", "nocional": 2.0, "risco_usd": 0.1}, 20.0, REG["tetos"], e)[0])  # 0,5x de 10
        self.assertTrue(M.cabe_nos_tetos(ab, {"cod": "tfs", "nocional": 1.0, "risco_usd": 0.1}, 20.0, REG["tetos"], e)[0])
        ab = [{"cod": "h46", "nocional": 10.0, "risco_usd": 1.15}]
        ok, m = M.cabe_nos_tetos(ab, {"cod": "tfs", "nocional": 1.0, "risco_usd": 0.1}, 20.0, REG["tetos"], e)
        self.assertFalse(ok); self.assertIn("risco aberto", m)


class Stops(unittest.TestCase):
    def test_ordem_sem_stop_ou_sem_etiqueta(self):
        cl = M.etiqueta("tfs", 1, 1)
        self.assertTrue(M.ordem_valida({"cl_id": cl, "px": 10, "stop": 11, "lado": "short"})[0])
        self.assertEqual(M.ordem_valida({"cl_id": cl, "px": 10, "stop": 9, "lado": "short"})[1], "stop do lado errado")
        self.assertEqual(M.ordem_valida({"cl_id": cl, "px": 10, "lado": "long"})[1], "sem stop")
        self.assertEqual(M.ordem_valida({"cl_id": "manual", "px": 10, "stop": 9, "lado": "long"})[1], "sem etiqueta de estrategia")
        self.assertEqual(M.stops_em_falta({"A": 1, "B": 1}, {"A": ["x"]}), ["B"])


class Monitor(unittest.TestCase):
    def test_saude(self):
        al = M.saude(10_000, 0, {"A", "B"}, {"A": "tfs", "C": "h46"})
        t = " | ".join(al)
        self.assertIn("volta atrasada", t); self.assertIn("sem dono", t); self.assertIn("C", t)
        self.assertEqual(M.saude(100, 90, {"A"}, {"A": "tfs"}), [])

    def test_degradacao(self):
        self.assertIsNone(M.degradacao([0.1] * 10, -0.2, 8))
        self.assertIn("abaixo", M.degradacao([-0.5] * 20, -0.2, 50))
        self.assertIn("queda", M.degradacao([1.0] * 20 + [-1.0] * 13 + [1.0] * 7, -2.0, 8))
        self.assertIsNone(M.degradacao([0.2, -0.1] * 15, -0.2, 8))


if __name__ == "__main__":
    unittest.main()
