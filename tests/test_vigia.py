import unittest
from tools import vigia as V


class Vigia(unittest.TestCase):
    def test_batimento_e_stops(self):
        now = 1_000_000
        ok = {"resumo": {"t": now - 600}, "real": {"ops": {"HUMA": {"estado": "aberta", "stop": 0.0155, "sair_em": now + 3600}}}}
        self.assertEqual(V.problemas(ok, now), [])
        mau = {"resumo": {"t": now - 4 * 3600}, "real": {"ops": {"X": {"estado": "aberta", "stop": None, "sair_em": now - 3 * 3600},
                                                                 "Y": {"estado": "pendente"}}}}
        chaves = [k for k, _ in V.problemas(mau, now)]
        self.assertEqual(chaves, ["batimento", "stop-X", "tempo-X"])


class OrdemPresa(unittest.TestCase):
    def test_pendente_depois_de_caducar(self):
        now = 1_000_000
        base = {"resumo": {"t": now - 600}}
        dentro = {**base, "real": {"ops": {"A": {"estado": "pendente", "valido_ate": now + 3600}}}}
        self.assertEqual(V.problemas(dentro, now), [])
        folga = {**base, "real": {"ops": {"A": {"estado": "pendente", "valido_ate": now - 3600}}}}
        self.assertEqual(V.problemas(folga, now), [])          # o agente corre de hora a hora: 1 h ainda e normal
        presa = {**base, "real": {"ops": {"A": {"estado": "pendente", "valido_ate": now - 3 * 3600}}}}
        out = V.problemas(presa, now)
        self.assertEqual([k for k, _ in out], ["presa-A"])
        self.assertIn("3 h", out[0][1])
        self.assertNotRegex(out[0][1], r"USD")                  # nunca valores da conta
