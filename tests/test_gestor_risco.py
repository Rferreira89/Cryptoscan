"""(12/11 15:44) Gestor global de risco da conta e porta automatica do LONG real."""
import unittest

from engine import porta_long as PL
from engine import promo


def aberta(a, risk, strategy="X", side="SHORT"):
    return {"mode": "REAL", "status": "OPEN", "executed": True, "asset": a, "risk_pct": risk, "strategy": strategy,
            "side": side}


class Risco(unittest.TestCase):
    def test_risco_aberto_soma_todas_e_ignora_nao_executadas(self):
        st = {"ledger": [aberta("A", 1.5), aberta("B", 0.8, side="LONG"),
                         dict(aberta("C", 3.0), executed=False), dict(aberta("D", 2.0), mode="PAPER")]}
        r = promo.risco_aberto(st)
        self.assertEqual((r["pct"], r["moedas"]), (2.3, {"A", "B"}))

    def test_travao_da_conta(self):
        now = 100 * 86400 + 3600
        cfg = {"piloto": {"inicio": 0, "perda_max_r": -8}}
        led = [{"mode": "REAL", "status": "CLOSED", "executed": True, "result_r": -1.6, "closed_at": now - 60}] * 2
        self.assertIn("dia", promo.travao_conta({"ledger": led}, cfg, now))
        led = [{"mode": "REAL", "status": "CLOSED", "executed": True, "result_r": -1.0,
                "closed_at": now - (i + 2) * 86400} for i in range(8)]
        self.assertIn("acumulada", promo.travao_conta({"ledger": led}, cfg, now))
        led[0] = dict(led[0], executed=False)
        self.assertIsNone(promo.travao_conta({"ledger": led}, cfg, now))


class Porta(unittest.TestCase):
    def desc(self, **k):
        return {"resultados": [dict({"estrategia": "L1", "fase": "subida", "corretora": "bybit_ue",
                                     "classe": PL.CLASSE_OK, "robusta": True}, **k)]}

    def papel(self, n, r):
        return [{"strategy": "L1", "mode": "PAPER", "status": "CLOSED", "result_r": r if i % 3 else -0.5}
                for i in range(n)]

    def test_passa_so_com_tudo(self):
        p, rel = PL.avaliar(self.desc(), self.papel(40, 1.0), None, {"L1"})
        self.assertEqual([x["estrategia"] for x in p], ["L1"])
        self.assertEqual(p[0]["teto_pct"], 1.0)
        for d, led, mot, motivo in ((self.desc(robusta=None), self.papel(40, 1.0), {"L1"}, "robustez"),
                                    (self.desc(classe="INCONCLUSIVA"), self.papel(40, 1.0), {"L1"}, "classe"),
                                    (self.desc(), self.papel(10, 1.0), {"L1"}, "papel 10/30"),
                                    (self.desc(), self.papel(40, 0.1), {"L1"}, "papel sem vantagem"),
                                    (self.desc(), self.papel(40, 1.0), set(), "motor")):
            p, rel = PL.avaliar(d, led, None, mot)
            self.assertEqual(p, [])
            self.assertTrue(any(motivo in f for f in rel["L1|subida"]["falta"]), (motivo, rel))

    def test_teto_long_nunca_passa_1(self):
        cfg = {"piloto": {"estrategia": "SHORT_TURTLE", "teto_pct": 5},
               "pilotos_long": [{"estrategia": "L1", "teto_pct": 4}]}
        self.assertEqual(PL.piloto_de(cfg, "L1")["teto_pct"], 1.0)
        self.assertEqual(PL.piloto_de(cfg, "SHORT_TURTLE")["teto_pct"], 5)
        self.assertEqual(PL.piloto_de(cfg, "OUTRA"), {})

    def test_aplicar_acrescenta_autorizacao_e_fase(self):
        st = {"ledger": self.papel(40, 1.0), "porta_dados": {"descoberta": self.desc(), "papel": None}}
        cfg = {"real_autorizados": ["SHORT_TURTLE"], "campeoes_estudo": {"lateral": ["SHORT_TURTLE"]}}
        c = PL.aplicar(cfg, st, {"L1"}, 1000)
        self.assertEqual(c["real_autorizados"], ["L1", "SHORT_TURTLE"])
        self.assertEqual(c["campeoes_estudo"]["subida"], ["L1"])
        self.assertEqual(cfg["real_autorizados"], ["SHORT_TURTLE"])          # o cfg original fica igual
        self.assertEqual(st["porta_long"]["pilotos"], ["L1"])
        st2 = {"ledger": [], "porta_dados": {"descoberta": self.desc(), "papel": None}}
        self.assertIs(PL.aplicar(cfg, st2, {"L1"}, 1000), cfg)

    def test_producao_hoje_sem_long(self):
        """Com a descoberta atual (nenhuma VANTAGEM DEMONSTRADA), nenhum LONG entra."""
        st = {"ledger": [], "porta_dados": {"descoberta": {"resultados": [
            {"estrategia": "MAIORES_TENDENCIA", "fase": "lateral", "corretora": "bybit_ue", "classe": "INCONCLUSIVA"}]}}}
        cfg = {"real_autorizados": ["SHORT_TURTLE"]}
        self.assertIs(PL.aplicar(cfg, st, {"MAIORES_TENDENCIA"}, 1), cfg)


if __name__ == "__main__":
    unittest.main()


class NoCircuito(unittest.TestCase):
    """O gestor no circuito real de sinais (promo.decisions): risco ja aberto noutra estrategia + o novo > 5% e
    recusado como 'capacidade'; moeda com posicao aberta tambem."""

    def correr(self, ledger):
        from unittest import mock
        from tests.test_promo import CFG, TF, bars
        c4 = bars()
        now = c4[-1]["t"] + TF + 60
        sig = {"stop": 80.0, "tp": [90.0, 95.0], "partials": [50, 50], "breakeven": True,
               "hold_s": 3 * 86400, "t_sig": c4[-1]["t"] + TF, "atr": 1.5}
        rows = [{"asset": "AAA", "price": 84.1, "decision": {"decision": "NO TRADE", "venue": {"pair": "AAA/USDC"}}}]
        st = {"ledger": ledger}
        with mock.patch.object(promo, "registry", return_value={"BOUNCE_G0": lambda c, px, cfg: sig}):
            d = promo.decisions(st, rows, {"AAA": c4}, CFG, now, ["BOUNCE_G0"], True, lambda a: None)
        return d, st

    def test_capacidade(self):
        d, _ = self.correr([])
        self.assertEqual(len(d), 1)
        novo = d["AAA"]["plan"]["risk_pct"]
        d, st = self.correr([aberta("ZZZ", 5.0 - novo + 0.01, "SHORT_TURTLE")])
        self.assertEqual(d, {})
        self.assertIn("capacidade", st["promo_lost"][-1]["reason"])
        d, st = self.correr([aberta("ZZZ", 5.0 - novo - 0.01, "SHORT_TURTLE")])
        self.assertEqual(len(d), 1)
        d, st = self.correr([aberta("AAA", 0.1, "SHORT_TURTLE")])
        self.assertEqual(d, {})
        self.assertIn("já há uma posição real aberta em AAA", st["promo_lost"][-1]["reason"])
