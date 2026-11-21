import unittest
from tools import vigia as V


class EspelhoDivergente(unittest.TestCase):
    """(21/11) espelho real aberto na OKX com a original da Bybit ja fechada (caso XLM de 19/11)."""
    def setUp(self):
        self.now = 1_000_000
        self.okx = {"resumo": {"t": self.now - 600}, "real": {"ops": {
            "XLM": {"estado": "aberta", "estrategia": "espelho", "id_bybit": "XLM-ST-1", "stop": 0.15}}}}

    def _bybit(self, **sig):
        return {"signals": {"XLM-ST-1": {"status": "TRIGGERED", **sig}}}

    def test_original_viva_nao_avisa(self):
        self.assertEqual(V.problemas_espelho(self.okx, self._bybit(), self.now), [])

    def test_original_fechada_avisa(self):
        sb = self._bybit(status="CLOSED", closed_at=self.now - 5 * 3600, result_r=0.197,
                         position={"exit_reason": "MANUAL"})
        out = V.problemas_espelho(self.okx, sb, self.now)
        self.assertEqual([k for k, _ in out], ["diverge-XLM"])
        self.assertIn("5 h", out[0][1]); self.assertIn("manual", out[0][1]); self.assertIn("+0.20R", out[0][1])
        self.assertNotRegex(out[0][1], r"USD")

    def test_fechada_ha_pouco_espera(self):
        sb = self._bybit(status="CLOSED", closed_at=self.now - 600)
        self.assertEqual(V.problemas_espelho(self.okx, sb, self.now), [])

    def test_sem_original_ou_nao_espelho_nao_avisa(self):
        self.assertEqual(V.problemas_espelho(self.okx, {"signals": {}}, self.now), [])
        self.assertEqual(V.problemas_espelho(self.okx, None, self.now), [])
        okx = {"real": {"ops": {"XLM": {**self.okx["real"]["ops"]["XLM"], "estrategia": "panico"}}}}
        sb = self._bybit(status="CLOSED", closed_at=self.now - 5 * 3600)
        self.assertEqual(V.problemas_espelho(okx, sb, self.now), [])
        fechada = {"real": {"ops": {"XLM": {**self.okx["real"]["ops"]["XLM"], "estado": "fechada"}}}}
        self.assertEqual(V.problemas_espelho(fechada, sb, self.now), [])

    def test_estado_ao_vivo_de_hoje(self):
        # forma real de 21/11: XLM espelho aberto, original fechada a mao a 19/11 16:17
        okx = {"real": {"ops": {"XLM": {"estado": "aberta", "estrategia": "espelho",
                                        "id_bybit": "XLM-SHORT_TURTLE-1794673840", "stop": 0.15363}}}}
        sb = {"signals": {"XLM-SHORT_TURTLE-1794673840": {"status": "CLOSED", "closed_at": 1795105036,
                                                           "result_r": 0.197, "position": {"exit_reason": "MANUAL"}}}}
        self.assertEqual(len(V.problemas_espelho(okx, sb, 1795234035)), 1)


if __name__ == "__main__":
    unittest.main()
