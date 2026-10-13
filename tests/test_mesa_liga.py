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
