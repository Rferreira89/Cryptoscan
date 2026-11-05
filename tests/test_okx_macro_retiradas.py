import unittest
from unittest import mock
from tools import okx_macro as M


class Retiradas(unittest.TestCase):
    def test_sai_quem_deixou_de_ser_macro(self):
        m = {"abertas": {"AAPL": {"t": 1, "entrada": 200.0}, "INIT": {"t": 1, "entrada": 0.5}, "SQQQ": {"t": 1, "entrada": 9.0}},
             "fechadas": [], "ultimo": {}}
        fora = M.retirar_fora(m, {"AAPL": "AAPL-USDT-SWAP"})
        self.assertEqual(fora, ["INIT", "SQQQ"])
        self.assertEqual(sorted(m["abertas"]), ["AAPL"])
        self.assertEqual([x["asset"] for x in m["retiradas"]], ["INIT", "SQQQ"])
        self.assertEqual(m["fechadas"], [])                    # sem resultado inventado

    def test_api_em_baixo_nao_apaga(self):
        m = {"abertas": {"AAPL": {"t": 1, "entrada": 200.0}}, "fechadas": [], "ultimo": {}}
        self.assertEqual(M.retirar_fora(m, {}), [])
        self.assertIn("AAPL", m["abertas"])

    def test_correr_usa_a_lista(self):
        st = {"macro": {"abertas": {"TRUTH": {"t": 1, "entrada": 0.1}}, "fechadas": [], "ultimo": {}}}
        with mock.patch.object(M, "contratos", return_value={"KO": "KO-USDT-SWAP"}), \
                mock.patch.object(M, "diario", return_value=[]), mock.patch.object(M.time, "sleep"):
            M.correr(st)
        self.assertEqual(st["macro"]["resumo"]["abertas"], [])
        self.assertEqual(st["macro"]["retiradas"][0]["asset"], "TRUTH")


if __name__ == "__main__":
    unittest.main()
