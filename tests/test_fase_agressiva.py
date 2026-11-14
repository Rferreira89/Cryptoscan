"""(14/11, ordem do Rui) CAP_MERCADO_V2 e BOUNCE_LARGO ligados ao papel: so papel, nunca dinheiro real."""
import unittest

from engine import paper_ring, promo
from tools import arena_ringue as AR

H4 = 14400


def barras(n=80, t0=1_700_000_000, queda_final=False):
    out, p = [], 100.0
    for i in range(n):
        out.append({"t": t0 + i * H4, "o": p, "h": p * 1.01, "l": p * 0.99, "c": p, "v": 100.0})
    if queda_final:
        prev = out[-2]["c"]
        out[-1] = {"t": out[-1]["t"], "o": prev, "h": prev, "l": prev * 0.90, "c": prev * 0.985, "v": 500.0}
    return out


class FaseAgressiva(unittest.TestCase):
    def test_so_papel(self):
        for k in AR.FASE_AGRESSIVA_SIGS:
            self.assertIn(k, AR.NEW_SIGS)
            self.assertIn(k, AR.PAPEL_ESTUDO)
            self.assertNotIn(k, promo.REAL_OK)
            self.assertIn(k, AR.SINAIS)
            self.assertEqual(AR.PAPEL_N_MIN[k], 25)
        self.assertNotIn("CAPITULACAO_R2", AR.FASE_AGRESSIVA_SIGS)

    def test_cap_mercado_precisa_de_outras_moedas_a_cair(self):
        fn = AR.sig_cap_mercado_v2(3, 1.5)
        alvo = barras(queda_final=True)
        AR.CTX.update(asset="AAA", bars={"AAA": alvo, "B1": barras(queda_final=True), "B2": barras(queda_final=True)})
        self.assertIsNone(fn(alvo))                             # so 2 outras
        AR.CTX["bars"] = dict(AR.CTX["bars"], B3=barras(queda_final=True))
        s = fn(alvo)
        self.assertIsNotNone(s)
        self.assertFalse(s["breakeven"])
        self.assertEqual(s["hold_s"], 3 * 86400)
        e = alvo[-1]["c"]
        self.assertAlmostEqual(s["tp"][0] - e, 1.5 * (e - s["stop"]))
        self.assertAlmostEqual(s["stop"], alvo[-1]["l"] - 0.1 * AR.PB.atr(alvo[-100:])[-1])

    def test_prova_so_com_25_e_todas_as_fases(self):
        closed = [{"r": 0.5, "fase": f} for f in ("queda", "subida", "lateral")] * 8
        self.assertEqual(paper_ring.prova_estudo(closed, None, n_min=25)["estado"], "a medir")
        closed += [{"r": 0.5, "fase": "queda"}]
        self.assertNotEqual(paper_ring.prova_estudo(closed, None, n_min=25)["estado"], "a medir")


if __name__ == "__main__":
    unittest.main()
