"""(28/10, auditoria, OK do Rui) Dinheiro real so para estrategias autorizadas depois do criterio."""
import unittest
from unittest import mock

from engine import promo, risco
from tests.test_so_papel import st


class Autorizados(unittest.TestCase):
    def setUp(self):
        self.old = promo.SO_PAPEL_FAM, promo.CONFIG_ESTUDO, promo.AUTORIZADOS
        promo.SO_PAPEL_FAM, promo.CONFIG_ESTUDO = set(), {"lateral": ["SHORT_TURTLE"]}

    def tearDown(self):
        promo.SO_PAPEL_FAM, promo.CONFIG_ESTUDO, promo.AUTORIZADOS = self.old

    def reg(self):
        return mock.patch.object(promo, "registry", return_value={"BOUNCE_SQUEEZE": 1, "SHORT_TURTLE": 1})

    def test_sem_autorizacao_fica_em_papel(self):
        promo.AUTORIZADOS = set()
        s = st()
        with self.reg():
            self.assertEqual(promo.champions(s, (), "lateral", True), [])
        self.assertIn("autorização do Rui", s["so_papel"]["SHORT_TURTLE"])

    def test_autorizado_passa(self):
        promo.AUTORIZADOS = {"SHORT_TURTLE"}
        s = st()
        with self.reg():
            self.assertEqual(promo.champions(s, (), "lateral", True), ["SHORT_TURTLE"])

    def test_prova_so_conta_autorizadas(self):
        led = [{"id": "x", "strategy": "BOUNCE_SQUEEZE", "executed": True, "status": "CLOSED", "kind": "4H",
                "issued_at": risco.DESDE + 1, "closed_at": risco.DESDE + 9, "result_r": 1.0}]
        promo.AUTORIZADOS = set()
        self.assertEqual(risco.prova(led), (0, 0))
        promo.AUTORIZADOS = None
        self.assertEqual(risco.prova(led)[0], 1)


if __name__ == "__main__":
    unittest.main()
