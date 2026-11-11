"""(11/11) Guarda do piloto (preparacao, nao ligada): so conta operacoes reais executadas; suspende por perda
acumulada, perda diaria e juro; decide ao fim de 30. Sem ligacao ao executor."""
import inspect
import unittest

from engine import piloto as P

DAY = 86400


def op(r, dia, executed=True, est="SHORT_TURTLE", mode="REAL"):
    return {"strategy": est, "mode": mode, "status": "CLOSED", "executed": executed, "result_r": r,
            "closed_at": 1000 * DAY + dia * DAY, "opened_at": 1000 * DAY + dia * DAY - 3600}


class Guarda(unittest.TestCase):
    def test_nao_conta_o_que_nao_executou_nem_papel_nem_antes_do_inicio(self):
        rows = [op(0.5, 1, executed=False), op(0.47, 2, mode="PAPER"), op(-1.0, -5), op(1.3, 3), op(0.2, 4, est="X")]
        a = P.avaliar(rows, "SHORT_TURTLE", 1000 * DAY)
        self.assertEqual(a["n"], 1)
        self.assertAlmostEqual(a["soma_r"], 1.3)
        self.assertTrue(a["pode_abrir"])

    def test_perda_acumulada_suspende(self):
        rows = [op(-1.0, d) for d in range(10)]
        a = P.avaliar(rows, "SHORT_TURTLE", 0)
        self.assertFalse(a["pode_abrir"])
        self.assertEqual(a["estado"], "suspenso")

    def test_perda_num_dia_suspende(self):
        a = P.avaliar([op(-1.0, 1), op(-1.0, 1), op(-1.05, 1)], "SHORT_TURTLE", 0)
        self.assertFalse(a["pode_abrir"])

    def test_juro_real_acima_suspende(self):
        a = P.avaliar([op(0.5, 1)], "SHORT_TURTLE", 0, juros_r=[0.1, 0.08])
        self.assertFalse(a["pode_abrir"])

    def test_decisao_aos_30(self):
        bom = [op(0.6 if d % 2 else -0.4, d) for d in range(30)]
        self.assertEqual(P.avaliar(bom, "SHORT_TURTLE", 0)["estado"], "decidir (continuar ou alterar com o Rui)")
        mau = [op(-0.3 if d % 3 else 0.5, d) for d in range(30)]
        r = P.avaliar(mau, "SHORT_TURTLE", 0)
        self.assertEqual(r["estado"], "terminar")
        self.assertFalse(r["pode_abrir"])

    def test_so_o_promo_a_chama_e_so_com_config(self):
        from engine import executor, promo, scanner
        for m in (executor, scanner):
            self.assertNotIn("piloto", inspect.getsource(m))
        self.assertIn('cfg.get("piloto")', inspect.getsource(promo.cfg_piloto))
        src = inspect.getsource(P)
        for proibido in ("urlopen", "/v5/order", "privado(", "place"):
            self.assertNotIn(proibido, src)


if __name__ == "__main__":
    unittest.main()


class LigacaoPiloto(unittest.TestCase):
    """Sem a chave "piloto" na configuracao, o dimensionamento e o plano sao exatamente os de antes."""

    def cfg(self, **k):
        from engine import config
        c = dict(config.load())
        c.update(capital_usdc=20.0, fixed_position_usdc=4.4, max_risk_usdc=0.1, max_risk_usdc_normal=0.1,
                 swing_leverage=10.0, max_position_pct=25.0, risk_pct=1.0, min_order_usdc=5.0, **k)
        return c

    def test_sem_piloto_a_ordem_minima_continua_recusada(self):
        from engine import risk
        sz, why = risk.sizing(11.0, 0.11, 1.0, self.cfg(), short=True)
        self.assertIsNone(sz)
        self.assertIn("abaixo da ordem", why)

    def test_com_teto_entra_a_ordem_minima_e_o_risco_cabe(self):
        from engine import risk
        sz, why = risk.sizing(11.0, 0.11, 1.0, self.cfg(piloto_teto_pct=3.9), short=True)
        self.assertIsNotNone(sz, why)
        self.assertAlmostEqual(sz["usdc"]["position_usdc"], 5.0)
        self.assertLessEqual(5.0 * 0.11, 20.0 * 3.9 / 100)

    def test_teto_nao_deixa_passar_stop_largo(self):
        from engine import risk
        sz, why = risk.sizing(20.0, 0.20, 1.0, self.cfg(piloto_teto_pct=3.9), short=True)
        self.assertIsNone(sz)

    def test_cfg_piloto_so_para_a_estrategia_e_com_guarda(self):
        from engine import promo
        base = {"x": 1}
        self.assertIs(promo.cfg_piloto("SHORT_TURTLE", {}, base, 0), base)              # sem config: igual
        c = {"piloto": {"estrategia": "SHORT_TURTLE", "teto_pct": 3.9, "inicio": 0, "perda_max_r": -8}}
        self.assertNotIn("piloto_teto_pct", promo.cfg_piloto("BOUNCE_X30", {}, c, 0))
        self.assertEqual(promo.cfg_piloto("SHORT_TURTLE", {"ledger": []}, c, 0)["piloto_teto_pct"], 3.9)
        perdas = [op(-1.0, d) for d in range(9)]
        st = {"ledger": perdas}
        self.assertNotIn("piloto_teto_pct", promo.cfg_piloto("SHORT_TURTLE", st, c, 0))   # -9R <= -8R: suspenso
        self.assertIn("suspenso", st["piloto"])

    def test_config_de_producao_nao_tem_piloto(self):
        import json, os
        raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(raiz, "config.json"), encoding="utf-8") as f:
            self.assertNotIn("piloto", json.load(f))
