"""(27/10) Maquina do tempo: deterministica, conta alvo/stop/nenhum e so informa."""
import math
import unittest

from engine import maquina_tempo as M

H4 = 14400


def velas(n=1200, amp=0.02):
    out, px = [], 100.0
    for i in range(n):
        c = px * (1 + amp * math.sin(i / 7.0))
        out.append({"t": i * H4, "o": px, "h": max(px, c) * 1.01, "l": min(px, c) * 0.99, "c": c})
        px = c
    return out


class Maquina(unittest.TestCase):
    def test_soma_100_e_repetivel(self):
        c4 = velas()
        a = M.simular(c4, "LONG", 100, 95, 110, 20 * 86400, n=500)
        b = M.simular(c4, "LONG", 100, 95, 110, 20 * 86400, n=500)
        self.assertEqual(a, b)
        self.assertAlmostEqual(a["alvo_pct"] + a["stop_pct"] + a["nenhum_pct"], 100, delta=0.2)
        self.assertEqual(a["dias"], 20)

    def test_alvo_perto_acerta_mais(self):
        c4 = velas()
        perto = M.simular(c4, "SHORT", 100, 120, 99, 86400 * 5, n=500)
        longe = M.simular(c4, "SHORT", 100, 120, 50, 86400 * 5, n=500)
        self.assertGreater(perto["alvo_pct"], longe["alvo_pct"])

    def test_sem_historico_nao_inventa(self):
        self.assertIsNone(M.simular(velas(100), "LONG", 100, 95, 110, 86400))

    def test_registar_no_sinal_e_no_registo(self):
        c4 = velas()
        sig = {"id": "X-SHORT_TURTLE-1", "asset": "X", "direction": "SHORT",
               "plan": {"side": "SHORT", "entry_ref": 100.0, "entry_zone": [100.0, 100.2], "stop": 110.0,
                        "tp": [80.0, 60.0], "max_hold_s": 20 * 86400}}
        st = {}
        M.registar(st, [{"event": "ISSUED", "asset": "X", "signal": sig}], {"X": c4}, 1)
        self.assertIn("alvo_pct", sig["maquina_tempo"])
        self.assertEqual(st["maquina_tempo"][0]["id"], "X-SHORT_TURTLE-1")
        self.assertIn("Máquina do tempo", M.linha(sig["maquina_tempo"]))
        M.registar(st, [{"event": "ISSUED", "asset": "X", "signal": sig}], {"X": c4}, 2)
        self.assertEqual(len(st["maquina_tempo"]), 1)          # nao repete


if __name__ == "__main__":
    unittest.main()
