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


class StopConfirmado(unittest.TestCase):
    """(11/11) operacao real aberta sem confirmacao do stop na OKX ha mais de 3 h, com o agente a correr."""
    def setUp(self):
        self.now = 1_000_000
        self.base = {"resumo": {"t": self.now - 600}}

    def _ops(self, op, t_agente=None):
        st = {**self.base, "real": {"ops": {"A": {"estado": "aberta", "stop": 1.0, "sair_em": self.now + 9 * 3600, **op}}}}
        if t_agente is not None:
            st["resumo"] = {"t": t_agente}
        return [k for k, _ in V.problemas(st, self.now)], V.problemas(st, self.now)

    def test_confirmado_recente_nao_avisa(self):
        self.assertEqual(self._ops({"stop_ok": self.now - 3600})[0], [])

    def test_acabada_de_executar_nao_avisa(self):
        self.assertEqual(self._ops({"t_fill": self.now - 2 * 3600})[0], [])

    def test_confirmacao_parada_avisa(self):
        chaves, out = self._ops({"stop_ok": self.now - 4 * 3600, "t_fill": self.now - 20 * 3600})
        self.assertEqual(chaves, ["stopok-A"])
        self.assertIn("4 h", out[0][1])
        self.assertNotRegex(out[0][1], r"USD")

    def test_nunca_confirmada_avisa(self):
        self.assertEqual(self._ops({"t_fill": self.now - 5 * 3600})[0], ["stopok-A"])

    def test_agente_parado_so_avisa_batimento(self):
        chaves, _ = self._ops({"stop_ok": self.now - 5 * 3600}, t_agente=self.now - 4 * 3600)
        self.assertEqual(chaves, ["batimento"])

    def test_sem_stop_registado_so_o_aviso_de_stop(self):
        chaves, _ = self._ops({"stop": None, "t_fill": self.now - 5 * 3600})
        self.assertEqual(chaves, ["stop-A"])
