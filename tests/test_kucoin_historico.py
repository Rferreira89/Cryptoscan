"""(12/11) A KuCoin tem de receber o intervalo de datas para devolver historico suficiente (MNT, POPCAT)."""
import unittest
from unittest import mock

from engine import sources


class KuCoinHistorico(unittest.TestCase):
    def test_pede_o_intervalo_e_aceita_500_velas(self):
        cap = {}
        linhas = [[str(1_800_000_000 - k * 14400), "1", "1.1", "1.2", "0.9", "10", "11"] for k in range(500)]

        def falso(url, params=None, **k):
            cap.update(params or {})
            return {"code": "200000", "data": linhas}
        with mock.patch.object(sources, "_get", side_effect=falso):
            cs = sources.KuCoin().candles("MNT", "4h", limit=500)
        self.assertEqual(len(cs), 500)
        self.assertIn("startAt", cap)
        self.assertEqual(cap["endAt"] - cap["startAt"], 500 * 14400)

    def test_nunca_pede_mais_do_que_a_kucoin_da(self):
        cap = {}
        with mock.patch.object(sources, "_get", side_effect=lambda u, p=None, **k: (cap.update(p), {"code": "200000", "data": []})[1]):
            sources.KuCoin().candles("X", "1d", limit=5000)
        self.assertEqual(cap["endAt"] - cap["startAt"], 1500 * 86400)


if __name__ == "__main__":
    unittest.main()
