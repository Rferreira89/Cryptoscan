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
