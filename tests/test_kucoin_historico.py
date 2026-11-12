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


class FonteComHistoricoParaAAnalise(unittest.TestCase):
    """Uma fonte com 202 velas (chega a validacao, nao chega a analise) nao impede de usar outra com 499."""
    def test_usa_a_fonte_com_historico_suficiente(self):
        from engine import analysis, scanner

        def velas(n):
            return [{"t": 1_800_000_000 // 14400 * 14400 - (k + 1) * 14400, "o": 1.0, "h": 1.01, "l": 0.99, "c": 1.0,
                     "v": 10.0, "tb": 5.0} for k in range(n)][::-1]

        class F:
            def __init__(self, name, n):
                self.name, self.n = name, n

            def candles(self, base, tf, limit=500):
                return velas(self.n) if tf == "4h" else [dict(x, t=x["t"] // 86400 * 86400) for x in velas(self.n)]
        row = {"asset": "GRASS", "sources": ["okx", "kucoin"], "divergence_pct": 0}
        with mock.patch.object(sources, "TF_SECONDS", {"4h": 14400, "1d": 14400}):
            out = scanner.deep_check(row, [F("okx", 202), F("kucoin", 499)], 1_800_000_000 // 14400 * 14400)
        self.assertEqual(out["timeframes"]["4h"]["source"], "kucoin")
        self.assertGreaterEqual(out["timeframes"]["4h"]["n"], analysis.MIN_BARS)
