"""Mesa redonda (votos reais dos lutadores) e liga semanal."""
import unittest
from unittest import mock

from engine import consultas, debate, liga, reports
from tools import arena_ringue as AR

H4 = 14400
NOW = 1_800_000_000


def bars(n=320, t0=NOW - 320 * H4):
    return [{"t": t0 + i * H4, "o": 100, "h": 101, "l": 99, "c": 100, "v": 10, "tb": 5}
            for i in range(n)]


class Mesa(unittest.TestCase):
    def test_votos_seguem_a_funcao_de_sinal(self):
        c4 = bars()
        plan = {"stop": 90, "tp": [110], "partials": [100], "gatilho": "sinal X"}
        fake = {"BOUNCE_X30": lambda c, p: dict(plan), "BOUNCE_FLUXO": lambda c, p: None,
                "MORTO": lambda c, p: dict(plan)}
        with mock.patch.object(AR, "SINAIS", fake):
            v = debate.votes("AAA", c4, 100, {"BOUNCE_X30", "BOUNCE_FLUXO"})
        self.assertEqual([x["id"] for x in v], ["BOUNCE_X30", "BOUNCE_FLUXO"])
        self.assertEqual(v[0]["voto"], "entra")
        self.assertEqual(v[0]["razao"], "sinal X")
        self.assertEqual(v[1]["voto"], "não")
        self.assertIn("RSI 4H", v[1]["razao"])

    def test_tabela_ordena_por_votos(self):
        rows = [{"asset": "A", "price": 1, "analysis": {"4h": {"rsi": 50}}},
                {"asset": "B", "price": 1, "analysis": {"4h": {"rsi": 28}}}]
        st = {"arena": {"forma": {"lutadores": {"BOUNCE_X30": {}}}, "mortos": {}, "status": {}}}
        with mock.patch.object(debate, "votes", lambda a, c, p, al: [
                {"id": "BOUNCE_X30", "persona": "Xavier", "voto": "entra" if a == "B" else "não", "razao": "r"}]):
            t = debate.table(rows, {"A": bars(), "B": bars()}, st)
        self.assertEqual(t[0]["asset"], "B")
        self.assertEqual(t[0]["a_favor"], 1)
        self.assertIn("debate", rows[0])

    def test_absorcao_e_lsr(self):
        c4 = bars(20)
        for x in c4[-9:-3]:
            x["l"] = 99
        for x in c4[-4:-1]:
            x["tb"] = 4
        c4[-1].update(l=97, tb=7)
        self.assertTrue(AR.absorcao(c4)[0])
        c4[-1]["tb"] = 4
        self.assertFalse(AR.absorcao(c4)[0])
        AR.CTX["ls"] = {"AAA": [(NOW - (40 - i) * H4, 2.0 - i * 0.01) for i in range(40)]}
        try:
            ok, txt = AR.lsr_ok("AAA", NOW)
            self.assertTrue(ok, txt)
            AR.CTX["ls"]["AAA"][-1] = (AR.CTX["ls"]["AAA"][-1][0], 3.0)
            AR.CTX["ls"]["AAA"][-2] = (AR.CTX["ls"]["AAA"][-2][0], 3.0)
            self.assertFalse(AR.lsr_ok("AAA", NOW)[0])
        finally:
            AR.CTX["ls"] = {}
        self.assertIn("BOUNCE_ABSORCAO", AR.SINAIS)
        self.assertIn("BOUNCE_LSR", AR.SINAIS)


ROWS = [{"id": "A", "persona": "Ana", "name": "a", "estado": "SOBE", "forma": {"n": 40, "avg_r": 0.5}},
        {"id": "B", "persona": "Bia", "name": "b", "estado": "A COMPETIR", "forma": {"n": 18, "avg_r": -0.15}},
        {"id": "C", "persona": "Caio", "name": "c", "estado": "MORTA", "morte": {}, "forma": {"n": 30, "avg_r": -0.4}}]


class Liga(unittest.TestCase):
    def test_tabela_movimento_e_perigo(self):
        st = {}
        lg = liga.update(st, ROWS, ["A"], NOW)
        self.assertEqual([t["id"] for t in lg["tabela"]], ["A", "B"])     # mortos fora
        self.assertTrue(lg["tabela"][1]["perigo"])
        self.assertEqual(lg["tabela"][0]["mov"], 0)
        rows2 = [dict(ROWS[1], forma={"n": 25, "avg_r": 0.9}), ROWS[0]]
        lg2 = liga.update(st, rows2, ["A"], NOW + 3600)
        self.assertEqual(lg2["tabela"][0]["id"], "B")
        self.assertEqual(lg2["tabela"][0]["mov"], 1)
        self.assertEqual(lg2["destaque"]["persona"], "Bia")
        lg3 = liga.update(st, rows2, ["A"], NOW + 8 * 86400)               # semana nova
        self.assertEqual(lg3["anterior"]["semana"], lg["semana"])
        self.assertEqual(lg3["tabela"][0]["mov"], 0)
        self.assertIn("Lutador da semana", liga.text(lg2))

    def test_comandos_e_domingo(self):
        lg = liga.update({}, ROWS, ["A"], NOW)
        res = {"liga": lg, "status_global": "OK", "sources": {}, "universe": [
            {"asset": "SOL", "price": 100, "debate": [{"persona": "Xavier", "voto": "entra", "razao": "r"}]}],
               "mesa": [{"asset": "SOL", "a_favor": 1, "votantes": 1, "rsi": 28}]}
        self.assertIn("Mesa redonda: SOL", consultas.answer("/debate sol", res, {}))
        self.assertIn("mais discutidas", consultas.answer("/debate", res, {}))
        self.assertIn("Liga dos lutadores", consultas.answer("/liga", res, {}))
        import datetime
        from zoneinfo import ZoneInfo
        sun = int(datetime.datetime(2027, 1, 3, 21, 0, tzinfo=ZoneInfo("Europe/Lisbon")).timestamp())
        st = {"reports": {"daily": "2027-01-03", "health": "OK"}}
        out = reports.due(res, st, sun)
        self.assertIn("liga", [k for k, _ in out])
        self.assertNotIn("liga", [k for k, _ in reports.due(res, st, sun + 60)])


if __name__ == "__main__":
    unittest.main()


class FamiliasNovas(unittest.TestCase):
    def test_tartarugas_rompimento(self):
        c4 = bars(200)
        for x in c4:
            x.update(h=101, l=99, c=100)
        c4[-1].update(c=103, h=103.5)
        p = AR.sig_turtle(c4)
        self.assertIsNotNone(p)
        self.assertLess(p["stop"], 103)
        self.assertEqual(len(p["tp"]), 2)
        self.assertEqual(p["trail_r"], 1.0)
        c4[-2]["c"] = 102                      # ja estava acima: nao e rompimento novo
        c4[-3].update(h=102.5)
        self.assertIsNone(AR.sig_turtle(c4))

    def test_momentum_so_a_segunda_e_no_top(self):
        import time as _t
        t0 = 1_799_020_800                    # segunda-feira 00h UTC
        self.assertEqual(_t.gmtime(t0).tm_wday, 0)
        mk = lambda g: [{"t": t0 - (300 - i) * H4, "o": 1, "h": 1, "l": 1, "c": 100 * (1 + g) ** i, "v": 1}
                        for i in range(300)]
        bars_ = {f"A{i}": mk(0.001 * i) for i in range(8)}
        bars_["BTC"] = mk(0.0)
        AR.CTX.update(bars=bars_, rank={}, btc=bars_["BTC"], asset="A7")
        try:
            self.assertEqual(AR.momentum_rank(bars_, t0)[0], "A7")
            self.assertIsNotNone(AR.sig_momentum(bars_["A7"]))
            AR.CTX["asset"] = "A1"
            self.assertIsNone(AR.sig_momentum(bars_["A1"]))           # fora do top 5
            AR.CTX["asset"] = "A7"
            self.assertIsNone(AR.sig_momentum(bars_["A7"][:-1]))      # nao e segunda 00h
        finally:
            AR.CTX.update(bars={}, rank={}, btc=None, asset=None)

    def test_nomes_e_mesa(self):
        from engine import arena
        for k, n in (("TURTLE", "Rodrigo"), ("SQUEEZE_BB", "Beatriz"), ("MOMENTUM", "Mónica")):
            self.assertEqual(arena.persona(k), n)
            self.assertIn(k, AR.SINAIS)
        v = debate.votes("AAA", bars(200), 100, {"TURTLE"})
        self.assertIn("máximo de 20 dias", v[0]["razao"])


class Regresso(unittest.TestCase):
    def test_regime_e_regresso_com_nome_novo(self):
        from engine import arena
        st = {"arena": {"mortos": {"TURTLE": {"t": NOW, "motivo": "x"}}}}
        self.assertEqual(arena.rebirth(st, NOW, "lateral"), [])
        self.assertEqual(st["arena"]["mortos"]["TURTLE"]["regime"], "lateral")
        self.assertEqual(arena.rebirth(st, NOW + 3600, "subida"), [])        # ainda nao firme
        ev = arena.rebirth(st, NOW + 3600 + 8 * 86400, "subida")
        self.assertEqual(ev[0]["novo"], "TURTLE_R2")
        self.assertNotEqual(ev[0]["nome"], arena.persona("TURTLE"))
        self.assertIn("(regresso)", arena._name("TURTLE_R2"))
        self.assertEqual(st["arena"]["renascidos"]["TURTLE_R2"]["base"], "TURTLE")
        self.assertEqual(arena.rebirth(st, NOW + 20 * 86400, "subida"), [])  # so uma vez
        st["arena"]["mortos"]["TURTLE_R2"] = {"t": NOW, "regime": "subida"}
        ev = arena.rebirth(st, NOW + 40 * 86400, "queda")
        self.assertEqual(arena.rebirth(st, NOW + 48 * 86400, "queda")[0]["novo"], "TURTLE_R3")

    def test_registo_e_dinheiro_real_herdam(self):
        from engine import promo
        self.assertIn("TURTLE_R2", AR.SINAIS)
        self.assertIs(AR.SINAIS.get("TURTLE_R2"), AR.SINAIS["TURTLE"])
        self.assertIsNone(AR.SINAIS.get("XPTO_R2"))
        self.assertIn("TURTLE_R3", promo.REAL_OK)
        self.assertNotIn("PULLBACK_R2", promo.REAL_OK)

    def test_ringue_so_conta_depois_do_regresso(self):
        out = AR.run({"BTC": bars(10)}, {}, NOW, days=1,
                     renascidos={"TURTLE_R2": {"base": "TURTLE", "desde": NOW + 1}})
        self.assertIn("TURTLE_R2", out["lutadores"])
        self.assertEqual(out["lutadores"]["TURTLE_R2"]["n"], 0)

    def test_regime_btc(self):
        from engine import arena
        up = [{"t": NOW - (1500 - i) * H4, "o": 1, "h": 1, "l": 1, "c": 100 * 1.001 ** i, "v": 1, "tb": 0.5}
              for i in range(1500)]
        self.assertEqual(arena.market_regime(up), "subida")
        flat = [dict(x, c=100) for x in up]
        self.assertEqual(arena.market_regime(flat), "lateral")
        self.assertIsNone(arena.market_regime(up[:100]))


class RegressoComProva(unittest.TestCase):
    def test_so_regressa_quem_ganhou_no_regime(self):
        from engine import arena
        st = {"arena": {"mortos": {"TURTLE": {"t": NOW, "regime": "lateral"},
                                   "SQUEEZE_BB": {"t": NOW, "regime": "lateral"}},
                        "longo": {"lutadores": {
                            "TURTLE": {"por_regime": {"subida": {"n": 40, "avg_r": 0.6, "acaso_p95": 0.3}}},
                            "SQUEEZE_BB": {"por_regime": {"subida": {"n": 40, "avg_r": -0.2, "acaso_p95": 0.1}}}}}},
              "mercado": {"regime": "subida", "desde": NOW - 8 * 86400}}
        ev = arena.rebirth(st, NOW, "subida")
        self.assertEqual([e["novo"] for e in ev], ["TURTLE_R2"])


class RegressoMesmoRegime(unittest.TestCase):
    def test_volta_no_mesmo_regime_se_o_ano_provar(self):
        from engine import arena
        st = {"arena": {"mortos": {"PULLBACK": {"t": NOW - 10 * 86400, "regime": "subida"},
                                   "BREAKOUT": {"t": NOW - 10 * 86400, "regime": "subida"}},
                        "longo": {"lutadores": {
                            "PULLBACK": {"por_regime": {"subida": {"n": 16, "avg_r": 0.72, "acaso_p95": 0.3}}},
                            "BREAKOUT": {"por_regime": {"subida": {"n": 12, "avg_r": -0.5, "acaso_p95": 0.4}}}}}},
              "mercado": {"regime": "subida", "desde": NOW - 30 * 86400}}
        ev = arena.rebirth(st, NOW, "subida")
        self.assertEqual([e["novo"] for e in ev], ["PULLBACK_R2"])
        st["arena"]["mortos"]["PULLBACK"]["t"] = NOW            # morreu agora: espera 7 dias
        st["arena"]["mortos"]["PULLBACK"].pop("renasceu")
        self.assertEqual(arena.rebirth(st, NOW, "subida"), [])


class RompimentoReteste(unittest.TestCase):
    def mk(self, n=220):
        return [{"t": NOW - (n - i) * H4, "o": 100, "h": 101, "l": 99, "c": 100, "v": 10, "tb": 5}
                for i in range(n)]

    def test_rompimento_com_espaco(self):
        c4 = self.mk()
        for x in c4[-181:-40]:
            x["h"] = 120                         # resistencia longe (espaco)
        c4[-1].update(c=101.5, h=101.8, v=30)    # rompe 101 com volume, pouco esticado
        p = AR.sig_breakout_espaco(c4)
        self.assertIsNotNone(p)
        self.assertLess(p["stop"], 101)
        c4[-1].update(c=106, h=106.5)            # entrada tardia: recusa
        self.assertIsNone(AR.sig_breakout_espaco(c4))
        c4[-1].update(c=101.5, h=101.8)
        for x in c4[-181:-40]:
            x["h"] = 102                         # resistencia colada: sem espaco
        self.assertIsNone(AR.sig_breakout_espaco(c4))

    def test_reteste(self):
        c4 = self.mk(150)
        for x in c4[-12:-3]:
            x.update(c=104, h=105, l=103)        # rompeu 101 e ficou acima
        c4[-3].update(l=101.2, c=102, h=103)     # volta ao nivel
        c4[-2].update(o=102, c=101.8, h=102.5, l=100.9)
        c4[-1].update(o=101.9, c=103, h=103.2, l=101.5)   # vela de retoma acima do maximo anterior
        p = AR.sig_reteste(c4)
        self.assertIsNotNone(p)
        self.assertLess(p["stop"], 101)
        self.assertIn("RETESTE", AR.SINAIS)
        self.assertIn("BRK_ESPACO", AR.SINAIS)
