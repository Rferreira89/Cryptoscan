"""Diretor de Trading: relatorios estruturados e autorizacao das entradas."""
import unittest
from unittest import mock

from engine import consultas, diretor, run

H4 = 14400
NOW = 1_800_000_000 - (1_800_000_000 % H4) + 600     # 10 min depois do fecho de uma vela


def c4(n=200, px=100.0):
    t0 = NOW - 600 - n * H4
    return [{"t": t0 + i * H4, "o": px, "h": px * 1.01, "l": px * 0.99, "c": px, "v": 1}
            for i in range(n)]


def deps(**cores):
    nomes = ["Tendência e estrutura", "Liquidez e smart money", "Volume e fluxo", "Derivados",
             "Suportes e resistências", "Força relativa", "Sobrevenda", "Macroeconomia"]
    return [{"dep": n, "cor": cores.get(n, "amarelo"), "texto": f"leitura de {n}"} for n in nomes]


def row(dep=None, **kw):
    r = {"asset": "SOL", "price": 100.0, "divergence_pct": 0.1, "venue": {"stale": False},
         "timeframes": {"4h": {"status": "VALID"}, "1d": {"status": "VALID"}},
         "departamentos": dep if dep is not None else deps()}
    r.update(kw)
    return r


def dec(side="LONG", strategy="BOUNCE_X30", **plan):
    p = {"entry_zone": [99.0, 100.0], "entry_ref": 100.0, "stop": 95.0,
         "tp": [104.0, 108.0, 112.0], "rr": 2.0}
    if side == "SHORT":
        p.update(entry_zone=[100.0, 101.0], stop=106.0, tp=[96.0, 92.0, 88.0])
    p.update(plan)
    return {"decision": side, "strategy": strategy, "mode": "REAL", "plan": p,
            "trigger": "RSI 4H abaixo de 30"}


class Relatorios(unittest.TestCase):
    def test_campos_obrigatorios(self):
        v = diretor.review(row(), dec(), c4(), None, c4(), NOW)
        self.assertEqual(v["decisao"], "AUTORIZADO")
        self.assertEqual(len(v["relatorios"]), 9)            # lutador + 8 departamentos
        for r in v["relatorios"]:
            for k in ("agente", "ativo", "timeframe", "dados", "direcao", "condicoes",
                      "contra", "estado_dados", "invalidacao"):
                self.assertIn(k, r)
            self.assertTrue(all(z["t"] for z in r["dados"]))  # cada dado com hora
        p = v["relatorios"][0]
        self.assertEqual((p["stop"], p["alvos"][0]), (95.0, 104.0))
        self.assertIn("abaixo de 95", p["invalidacao"][0])


class Regras(unittest.TestCase):
    def test_r1_dados_atrasados_ou_indisponiveis(self):
        v = diretor.review(row(), dec(), c4(), None, None, NOW + 2 * H4)
        self.assertEqual((v["decisao"], v["estado_dados"]), ("REJEITADO", "atrasado"))
        v = diretor.review(row(timeframes={"4h": {"status": "DATA INVALID"}, "1d": {"status": "VALID"}}),
                           dec(), c4(), None, None, NOW)
        self.assertEqual(v["estado_dados"], "indisponivel")
        v = diretor.review(row(divergence_pct=1.5), dec(), c4(), None, None, NOW)
        self.assertEqual(v["decisao"], "REJEITADO")
        # aviso (DEGRADED) continua utilizavel
        v = diretor.review(row(timeframes={"4h": {"status": "DEGRADED"}, "1d": {"status": "VALID"}}),
                           dec(), c4(), None, None, NOW)
        self.assertEqual(v["decisao"], "AUTORIZADO")

    def test_r2_plano(self):
        for bad in (dict(stop=101.0), dict(tp=[99.5]), dict(rr=0.9), dict(stop=None)):
            v = diretor.review(row(), dec(**bad), c4(), None, None, NOW)
            self.assertEqual(v["decisao"], "REJEITADO", bad)
        self.assertEqual(diretor.review(row(), dec("SHORT", "SHORT_X30"), c4(), None, None, NOW)["decisao"],
                         "AUTORIZADO")
        self.assertEqual(diretor.review(row(), dec("SHORT", "SHORT_X30", stop=99.0), c4(), None, None,
                                        NOW)["decisao"], "REJEITADO")

    def test_r3_conflitos_e_premissa_da_familia(self):
        R = "vermelho"
        # sobrevenda: tendencia, volume e forca relativa contra sao a premissa
        d = deps(**{"Tendência e estrutura": R, "Volume e fluxo": R, "Força relativa": R})
        v = diretor.review(row(d), dec(), c4(), None, None, NOW)
        self.assertEqual(v["decisao"], "AUTORIZADO")
        self.assertEqual(len(v["esperado"]), 3)
        # numa estrategia de tendencia, as mesmas leituras rejeitam
        v = diretor.review(row(d), dec(strategy="TURTLE"), c4(), None, None, NOW)
        self.assertEqual(v["decisao"], "REJEITADO")
        d = deps(**{"Liquidez e smart money": R, "Suportes e resistências": R, "Sobrevenda": R})
        self.assertEqual(diretor.review(row(d), dec(), c4(), None, None, NOW)["decisao"], "REJEITADO")

    def test_r4_macro_medo(self):
        v = diretor.review(row(), dec(), c4(), {"estado": "medo"}, None, NOW)
        self.assertEqual(v["decisao"], "REJEITADO")
        v = diretor.review(row(), dec(strategy="BOUNCE_MEDO"), c4(), {"estado": "medo"}, None, NOW)
        self.assertNotIn("macroeconomia em medo: compras suspensas", v["motivos"])

    def test_r5_derivados(self):
        d = deps(**{"Derivados": "vermelho", "Suportes e resistências": "vermelho"})
        v = diretor.review(row(d), dec(), c4(), None, None, NOW)
        self.assertEqual(v["decisao"], "REJEITADO")
        self.assertIn("derivados", v["motivos"][0])


class Gate(unittest.TestCase):
    def test_rejeita_vira_no_trade_e_fica_registado(self):
        st = {}
        r = row(deps(**{"Derivados": "vermelho", "Sobrevenda": "vermelho"}))
        r["decision"] = dec()
        r["_c4"] = c4()
        diretor.gate(st, [r], {"SOL": c4()}, None, NOW)
        self.assertEqual(r["decision"]["decision"], "NO TRADE")
        self.assertTrue(r["decision"]["reason"].startswith("Diretor de Trading"))
        self.assertEqual(len(st["diretor"]["rejeitados"]), 1)
        # revista de novo no scan seguinte: sem duplicar
        r["decision"] = dec()
        diretor.gate(st, [r], {"SOL": c4()}, None, NOW + 300)
        self.assertEqual(len(st["diretor"]["rejeitados"]), 1)
        self.assertEqual(len(st["diretor"]["decisoes"]), 1)

    def test_autoriza_e_paper_nao_passa(self):
        st = {}
        r = row()
        r["decision"] = dec()
        r["decision_short"] = dict(dec("SHORT", "SHORT_X30"), mode="PAPER")
        diretor.gate(st, [r], {"SOL": c4()}, None, NOW)
        self.assertEqual(r["decision"]["decision"], "LONG")
        self.assertEqual(r["decision"]["diretor"]["decisao"], "AUTORIZADO")
        self.assertNotIn("diretor", r["decision_short"])

    def test_falha_fechada(self):
        st = {}
        r = row()
        r["decision"] = dec()
        with mock.patch.object(diretor, "review", side_effect=ValueError):
            diretor.gate(st, [r], {"SOL": c4()}, None, NOW)
        self.assertEqual(r["decision"]["decision"], "NO TRADE")

    def test_seguimento_das_rejeicoes(self):
        st = {"diretor": {"rejeitados": [
            {"t": NOW - 3 * H4, "ativo": "SOL", "lado": "LONG", "entrada": 100, "stop": 99.5,
             "tp": [110], "estado": "aberto"},
            {"t": NOW - 3 * H4, "ativo": "SOL", "lado": "LONG", "entrada": 100, "stop": 90,
             "tp": [100.5], "estado": "aberto"}]}}
        out = diretor.follow(st, {"SOL": c4()}, NOW)
        self.assertEqual((out["evitou_perda"], out["custou_ganho"]), (1, 1))


class Saidas(unittest.TestCase):
    def test_telegram_e_comando(self):
        v = diretor.review(row(), dec(), c4(), None, None, NOW)
        txt = run.diretor_lines(v)
        self.assertIn("Diretor de Trading: AUTORIZADO", txt)
        st = {}
        r = row()
        r["decision"] = dec()
        diretor.gate(st, [r], {"SOL": c4()}, None, NOW)
        res = {"diretor": diretor.summary(st, NOW)}
        self.assertIn("1 autorizadas", consultas.answer("/diretor", res, st))
        rep = consultas.answer("/diretor SOL", res, st)
        self.assertIn("Estado dos dados", rep)
        self.assertIn("Invalida se", rep)
        self.assertIn("ainda não reviu", consultas.answer("/diretor", {}, {}))


if __name__ == "__main__":
    unittest.main()
