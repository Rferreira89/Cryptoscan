"""Forma recente da arena (tools/arena_ringue.py) e comandos /desliga /liga."""
import unittest

from engine import arena, inbox, run
from tools import arena_ringue as AR

TF, DAY = 14400, 86400


def forma(k, n, r, med=0.05, p95=0.4):
    return {"atualizado": 1, "janela_dias": 90, "moedas": 70, "lutadores": {
        k: {"n": n, "wins": 0, "avg_r": r, "total_r": n * r, "ultimas": [r],
            "acaso_mediana": med, "acaso_p95": p95,
            "veredicto": arena.verdict(n, r, med, p95, True)}}}


class Forma(unittest.TestCase):
    def test_forma_mata_e_a_morte_e_definitiva(self):
        st = {}
        res = arena.update(st, {}, 1000, seed=1, forma=forma("BREAKOUT", 33, -0.5))
        b = next(x for x in res["classificacao"] if x["id"] == "BREAKOUT")
        self.assertEqual(b["estado"], "MORTA")
        self.assertTrue(b["motivo"].startswith("forma recente"))
        ev = arena.events(res, 1000)
        self.assertEqual(len([e for e in ev if e["strategy"] == "BREAKOUT"]), 1)
        txt = run.alert_text(ev[0], {}, "")
        self.assertIn("33 operações", txt)
        self.assertIn("/desliga quebra", txt)
        # mesmo que a forma recupere, quem morreu nao volta
        res = arena.update(st, {}, 2000, seed=1, forma=forma("BREAKOUT", 40, 0.9))
        b = next(x for x in res["classificacao"] if x["id"] == "BREAKOUT")
        self.assertEqual(b["estado"], "MORTA")
        self.assertFalse(b["mudou"])

    def test_forma_nunca_promove(self):
        st = {}
        res = arena.update(st, {}, 1000, seed=1, forma=forma("BOUNCE_G0", 60, 0.9))
        b = next(x for x in res["classificacao"] if x["id"] == "BOUNCE_G0")
        self.assertEqual(b["estado"], "A COMPETIR")
        self.assertEqual(b["forma"]["n"], 60)

    def test_sem_forma_nova_usa_a_guardada(self):
        st = {}
        arena.update(st, {}, 1000, seed=1, forma=forma("PULLBACK", 12, 0.1))
        res = arena.update(st, {}, 2000, seed=1, forma=None)
        b = next(x for x in res["classificacao"] if x["id"] == "PULLBACK")
        self.assertEqual(b["forma"]["n"], 12)
        self.assertEqual(res["forma"]["janela_dias"], 90)


class OnOff(unittest.TestCase):
    def test_desliga_e_liga(self):
        st = {}
        t = inbox.onoff(st, "/desliga quebra", 5)
        self.assertIn("Desligada", t)
        self.assertIn("BREAKOUT", st["disabled"])
        t = inbox.onoff(st, "/liga Quebra", 6)
        self.assertNotIn("BREAKOUT", st["disabled"])
        self.assertIn("configuração", inbox.onoff(st, "/liga range", 7, {"RANGE"}))
        self.assertNotIn("RANGE", st["disabled"])
        self.assertIn("desconhecida", inbox.onoff(st, "/desliga xyz", 8))
        self.assertIsNone(inbox.onoff(st, "/fechei NEAR 6", 8))

    def test_comando_pelo_telegram(self):
        st = {"ledger": []}
        ups = [{"message": {"chat": {"id": 7}, "date": 9, "text": "/desliga sweep"}}]
        out = inbox.apply(st, ups, 7)
        self.assertIn("LIQUIDITY_SWEEP", st["disabled"])
        self.assertIn("Sweep", out[0][0])


def daily_bars(prices, t0=1_700_000_000 // DAY * DAY):
    """Seis velas de 4H iguais por dia, para formar o diario."""
    out = []
    for d, p in enumerate(prices):
        for k in range(6):
            out.append({"t": t0 + d * DAY + k * TF, "o": p, "h": p * 1.01,
                        "l": p * 0.99, "c": p, "v": 1, "tb": 0.5})
    return out


class Ringue(unittest.TestCase):
    def test_tendencia_sem_look_ahead(self):
        ps = [100 + 0.2 * i for i in range(260)] + [160 - i for i in range(40)]
        c4 = daily_bars(ps)
        above = {x["t"] // DAY: True for x in c4}
        cfg = {"fee_pct": 0.25}
        t0 = c4[0]["t"]
        full = AR.trend_trades("BTC", c4, above, cfg, t0)
        self.assertTrue(full)
        # cortar o futuro nao muda as operacoes ja fechadas antes do corte
        cut = full[0][1]["t"] + 5 * DAY
        part = AR.trend_trades("BTC", [x for x in c4 if x["t"] < cut + 60 * DAY],
                               above, cfg, t0)
        self.assertEqual(round(part[0][1]["r"], 6), round(full[0][1]["r"], 6))

    def test_so_velas_fechadas(self):
        rows = [{"t": 0}, {"t": TF}, {"t": 2 * TF}]
        self.assertEqual(len(AR.closed(rows, 2 * TF + 10)), 2)

    def test_julgamento(self):
        c4 = daily_bars([100 + (i % 7) for i in range(120)])
        trs = [{"asset": "AAA", "t": c4[200 + i]["t"], "r": -1.0,
                "geo": {"stop": -0.03, "tp": [0.03], "partials": [100],
                        "breakeven": False}} for i in range(12)]
        import random
        j = AR.judge(trs, {"AAA": c4}, random.Random(1))
        self.assertEqual(j["n"], 12)
        self.assertEqual(j["veredicto"], "MORTA")


class MorteAutomatica(unittest.TestCase):
    def test_estrategia_ao_vivo_morta_e_desligada(self):
        st = {}
        res = arena.update(st, {}, 1000, seed=1, forma=forma("BREAKOUT", 33, -0.5))
        self.assertEqual(arena.auto_disable(st, res, 1000), ["BREAKOUT"])
        self.assertEqual(st["disabled"]["BREAKOUT"]["reason"], "arena")
        self.assertEqual(arena.auto_disable(st, res, 1001), [])     # so uma vez
        ev = dict(arena.events(res, 1000)[0], desligada=True)
        self.assertIn("Desligada automaticamente", run.alert_text(ev, {}, ""))
        # /liga nao ressuscita quem morreu na arena
        self.assertIn("definitiva", inbox.onoff(st, "/liga quebra", 5))
        self.assertIn("BREAKOUT", st["disabled"])

    def test_papel_nao_e_desligado_assim(self):
        st = {}
        res = arena.update(st, {}, 1000, seed=1, forma=forma("BOUNCE_G0", 30, -0.6))
        self.assertEqual(arena.auto_disable(st, res, 1000), [])

    def test_aviso_das_mortas_antigas(self):
        txt = run.alert_text({"event": "ARENA_OFF", "strategies": ["BREAKOUT", "TREND_DAILY"],
                              "id": "x"}, {}, "")
        self.assertIn("Quebra", txt)
        self.assertIn("Tendência", txt)

    def test_scanner_desliga_e_o_sinal_nao_sai(self):
        from engine import signals
        st = {"disabled": {}}
        res = arena.update(st, {}, 1000, seed=1, forma=forma("PULLBACK", 50, -0.3))
        arena.auto_disable(st, res, 1000)
        self.assertIn("PULLBACK", st["disabled"])
