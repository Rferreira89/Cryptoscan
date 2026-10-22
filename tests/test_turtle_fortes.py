"""TURTLE_FORTES (22/10, OK do Rui): so em papel, so na subida, so moedas fortes."""
import unittest
from unittest import mock

from engine import paper_ring, promo, arena
from tools import arena_ringue as AR

H4 = 14400


def velas(n=200, p0=1.0, passo=0.003):
    out, p = [], p0
    for i in range(n):
        out.append({"t": 1_700_000_000 + i * H4, "o": p, "h": p * 1.01, "l": p * 0.99, "c": p * (1 + passo), "v": 1e6})
        p *= 1 + passo
    return out


SIG = {"stop": 0.5, "tp": [10.0, 20.0], "partials": [50, 50], "breakeven": True, "hold_s": 20 * 86400,
       "trail_r": 1.0, "atr": 0.01, "gatilho": "rompimento do máximo de 20 dias"}


class TurtleFortes(unittest.TestCase):
    def test_nunca_dinheiro_real(self):
        self.assertIn("TURTLE_FORTES", AR.SINAIS)
        self.assertNotIn("TURTLE_FORTES", promo.REAL_OK)
        self.assertIn("TURTLE_FORTES", AR.PAPEL_ESTUDO)
        self.assertEqual(arena.persona("TURTLE_FORTES"), "Teodoro")
        st = {"arena": {"longo": {"lutadores": {"TURTLE_FORTES": {"por_regime": {"subida": {
            "n": 40, "avg_r": .9, "acaso_p95": .1, "metades": [.5, .6]}}}}}}}
        self.assertNotIn("TURTLE_FORTES", promo.champions(st, fase="subida", por_fase=True))

    def test_so_na_subida_e_so_moedas_fortes(self):
        c4 = velas()
        with mock.patch.object(AR, "sig_turtle", return_value=dict(SIG)), \
                mock.patch.object(AR, "_btc_ret", return_value=0.05):
            with mock.patch.object(AR, "_fase_btc", return_value="lateral"):
                self.assertIsNone(AR.sig_turtle_fortes(c4))
            with mock.patch.object(AR, "_fase_btc", return_value="subida"):
                s = AR.sig_turtle_fortes(c4)
                self.assertIsNotNone(s)
                self.assertIn("mais forte que o BTC", s["gatilho"])
        with mock.patch.object(AR, "sig_turtle", return_value=dict(SIG)), \
                mock.patch.object(AR, "_btc_ret", return_value=5.0), \
                mock.patch.object(AR, "_fase_btc", return_value="subida"):
            self.assertIsNone(AR.sig_turtle_fortes(c4))       # mais fraca que o BTC

    def test_papel_ativo_e_regista_a_fase(self):
        c4 = velas()
        now = c4[-1]["t"] + H4 + 60
        px = c4[-1]["c"]
        fake = {"TURTLE_FORTES": lambda c, p, cfg=None: dict(SIG, t_sig=c[-1]["t"] + H4)}
        st = {"mercado": {"regime": "subida"}}
        with mock.patch.object(promo, "registry", return_value=fake), \
                mock.patch.object(promo, "qualified", return_value=[]), \
                mock.patch.object(promo, "set_context"):
            r = paper_ring.update(st, [{"asset": "AAA", "price": px}], {"AAA": c4}, now)
        self.assertEqual(r["TURTLE_FORTES"]["open"], ["AAA"])
        self.assertEqual(st["paper_ring"]["TURTLE_FORTES"]["open"]["AAA"]["fase"], "subida")

    def test_regra_de_promocao(self):
        mk = lambda rs, f="subida": [{"r": r, "fase": f} for r in rs]
        self.assertEqual(paper_ring.prova_estudo(mk([1] * 19))["estado"], "a medir")
        self.assertEqual(paper_ring.prova_estudo(mk([1] * 30, "lateral"))["n"], 0)
        self.assertEqual(paper_ring.prova_estudo(mk([0.5, -0.1] * 10))["estado"], "aprovado: pede o OK do Rui")
        self.assertEqual(paper_ring.prova_estudo(mk([1] * 10 + [-1] * 10))["estado"], "a medir")   # 2.a metade a perder
        self.assertEqual(paper_ring.prova_estudo(mk([-0.2] * 20))["estado"], "chumbado")

    def test_aviso_so_quando_muda(self):
        from engine import run
        st = {}
        pr = lambda e: {"TURTLE_FORTES": {"prova": {"fase": "subida", "n": 20, "r": .3, "metades": [.2, .4], "estado": e}}}
        self.assertEqual(run.estudo_aviso(st, pr("a medir")), [])
        self.assertEqual(len(run.estudo_aviso(st, pr("aprovado: pede o OK do Rui"))), 1)
        self.assertEqual(run.estudo_aviso(st, pr("aprovado: pede o OK do Rui")), [])


if __name__ == "__main__":
    unittest.main()
