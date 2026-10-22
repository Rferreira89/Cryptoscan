"""Auditoria S/R (22/10): alarme de custos, falso rompimento so em papel e so na queda, shorts em papel."""
import unittest
from unittest import mock

from engine import posmortem, paper_ring, promo
from tools import arena_ringue as AR

H4, DAY = 14400, 86400
NOW = 1_800_000_000


def op(i, rr, rs, est="SHORT_TURTLE"):
    return {"id": f"X-{est}-{i}", "mode": "REAL", "executed": True, "status": "CLOSED", "asset": "X",
            "strategy": est, "closed_at": NOW + i, "real_r": rr, "result_r": rs, "reason": "TP"}


class AlarmeDeCustos(unittest.TestCase):
    def test_avisa_com_20_operacoes_e_custo_acima_do_limite(self):
        led = [op(i, 0.30, 0.45) for i in range(20)]                      # -0,15R por operacao
        rel = posmortem.relatorio(led)
        self.assertEqual(rel["gap_por_estrategia"]["SHORT_TURTLE"], {"n": 20, "gap": -0.15})
        st = {}
        self.assertEqual(len(posmortem.custo_aviso(st, rel, NOW)), 1)
        self.assertEqual(posmortem.custo_aviso(st, rel, NOW + 3600), [])        # uma vez
        self.assertEqual(len(posmortem.custo_aviso(st, rel, NOW + 8 * DAY)), 1)  # de novo ao fim de 7 dias

    def test_nao_avisa_com_poucas_ou_custo_baixo(self):
        self.assertEqual(posmortem.custo_aviso({}, posmortem.relatorio([op(i, 0.3, 0.45) for i in range(19)]), NOW), [])
        self.assertEqual(posmortem.custo_aviso({}, posmortem.relatorio([op(i, 0.40, 0.45) for i in range(25)]), NOW), [])


class FalsoRompimentoEmPapel(unittest.TestCase):
    def test_nunca_dinheiro_real_e_so_na_queda(self):
        self.assertIn("SHORT_FALSO_ROMP", AR.SINAIS)
        self.assertNotIn("SHORT_FALSO_ROMP", promo.REAL_OK)
        self.assertIn("SHORT_FALSO_ROMP", AR.PAPEL_ESTUDO)
        self.assertEqual(AR.PAPEL_FASE["SHORT_FALSO_ROMP"], "queda")
        sig = {"stop": 1.0, "tp": [2.0], "partials": [100], "hold_s": DAY, "atr": .1, "gatilho": "x"}
        with mock.patch.object(AR, "sig_falso_rompimento", return_value=dict(sig)):
            with mock.patch.object(AR, "_fase_btc", return_value="lateral"):
                self.assertIsNone(AR.sig_short_falso_rompimento([{"t": 0}]))
            with mock.patch.object(AR, "_fase_btc", return_value="queda"):
                self.assertIsNotNone(AR.sig_short_falso_rompimento([{"t": 0}]))

    def test_falso_rompimento_regra(self):
        c4 = []
        for i in range(200):
            c4.append({"t": i * H4, "o": 100, "h": 101, "l": 99, "c": 100, "v": 1, "tb": .5})
        c4[-1] = dict(c4[-1], l=97, c=100.5)                              # fura o minimo (99) e fecha acima
        self.assertIsNotNone(AR.sig_falso_rompimento(c4))
        c4[-1] = dict(c4[-1], l=99.5)
        self.assertIsNone(AR.sig_falso_rompimento(c4))

    def test_papel_abre_shorts_do_lado_certo(self):
        c4 = [{"t": i * H4, "o": 10, "h": 10.1, "l": 9.9, "c": 10, "v": 1} for i in range(200)]
        now = c4[-1]["t"] + H4 + 60
        fake = {"SHORT_FALSO_ROMP": lambda c, p, cfg=None: {"side": "SHORT", "stop": 11.0, "tp": [8.0], "partials": [100],
                                                           "hold_s": DAY, "t_sig": c[-1]["t"] + H4}}
        st = {"mercado": {"regime": "queda"}}
        with mock.patch.object(promo, "registry", return_value=fake), mock.patch.object(promo, "qualified", return_value=[]), \
                mock.patch.object(promo, "set_context"):
            r = paper_ring.update(st, [{"asset": "AAA", "price": 10.0}], {"AAA": c4}, now, market_ok=False)
        pos = st["paper_ring"]["SHORT_FALSO_ROMP"]["open"]["AAA"]
        self.assertEqual(pos["side"], "SHORT")
        self.assertEqual(pos["fase"], "queda")
        self.assertEqual(r["SHORT_FALSO_ROMP"]["prova"]["fase"], "queda")


if __name__ == "__main__":
    unittest.main()
