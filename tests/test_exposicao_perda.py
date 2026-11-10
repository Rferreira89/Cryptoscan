"""(10/11) Mapa de exposicao/correlacao e perda diaria em % (ponto 5 da ordem do Rui). So calculo, sem ordens."""
import random
import unittest

from engine import exposicao as X
from engine import perda_diaria as P


def serie(rs, base, ruido):
    c, out = 100.0, []
    for b in base:
        c *= 1 + b + rs.gauss(0, ruido); out.append(c)
    return out


class Exposicao(unittest.TestCase):
    def setUp(self):
        rs = random.Random(3)
        mercado = [rs.gauss(0, 0.01) for _ in range(300)]
        self.f = {"BTC": serie(rs, mercado, 0.002), "XRP": serie(rs, mercado, 0.003), "OP": serie(rs, mercado, 0.003),
                  "GOLD": serie(rs, [0] * 300, 0.01)}

    def test_mesma_aposta_detetada(self):
        m = X.mapa(self.f, [{"ativo": "XRP", "lado": "LONG", "origem": "H40"}, {"ativo": "OP", "lado": "LONG", "origem": "Kronos"},
                            {"ativo": "GOLD", "lado": "LONG", "origem": "macro"}])
        self.assertEqual(m["concentracoes"][0]["ativos"], ["OP", "XRP"])
        self.assertLess(m["apostas_efetivas"], 3)

    def test_long_e_short_correlacionados_compensam(self):
        a = X.apostas_efetivas([("XRP", "LONG"), ("OP", "LONG")], X.retornos(self.f))
        b = X.apostas_efetivas([("XRP", "LONG"), ("OP", "SHORT")], X.retornos(self.f))
        self.assertLess(a, 1.2); self.assertGreater(b, 2)

    def test_sem_dados_nao_inventa_grupo(self):
        m = X.mapa(self.f, [{"ativo": "NOVA", "lado": "LONG"}, {"ativo": "NOVA2", "lado": "LONG"}])
        self.assertEqual(m["concentracoes"], [])


class PerdaDiaria(unittest.TestCase):
    def test_okx_r_vezes_risco_e_desconhecido_sem_risco(self):
        okx = {"real": {"hist": [
            {"estado": "fechada", "asset": "A", "entrada": 1.0, "stop": 0.9, "ret_pct": -10.0, "risco_pct": 0.8, "fechado": 86400 * 10},
            {"estado": "fechada", "asset": "B", "entrada": 1.0, "stop": 0.8, "ret_pct": 10.0, "risco_pct": 1.0, "fechado": 86400 * 10 + 5},
            {"estado": "fechada", "asset": "C", "entrada": 1.0, "stop": 0.9, "ret_pct": -10.0, "fechado": 86400 * 11},
            {"estado": "cancelada", "asset": "D"}]}}
        d = P.por_dia(P.da_okx(okx))
        dia = d["1970-01-11"]
        self.assertAlmostEqual(dia["pct"], -0.8 + 0.5); self.assertTrue(dia["completo"])
        self.assertFalse(d["1970-01-12"]["completo"])
        self.assertEqual(P.pior_dia(d), ("1970-01-11", -0.3))

    def test_bybit_nunca_usa_o_r_do_sinal(self):
        st = {"ledger": [{"executed": True, "status": "CLOSED", "id": "S", "result_r": 1.31, "risk_pct": 1.0, "closed_at": 86400},
                         {"executed": True, "status": "CLOSED", "id": "N", "user_result_r": -0.64, "risk_pct": 3.0, "closed_at": 86400}]}
        x = P.por_dia(P.da_bybit(st))["1970-01-02"]
        self.assertAlmostEqual(x["pct"], -1.92); self.assertEqual(x["desconhecidas"], 1); self.assertFalse(x["completo"])

    def test_sem_valores_em_dinheiro(self):
        src = open(P.__file__).read() + open(X.__file__).read()
        for proibido in ("usd", "USDC", "saldo", "equity", "POST", "/order"):
            self.assertNotIn(proibido + "\"", src)
        self.assertNotIn("urllib", src)


if __name__ == "__main__":
    unittest.main()


class ExposicaoDiaria(unittest.TestCase):
    def test_blocos_separados_e_posicao_real(self):
        import json, os, tempfile
        from tools import exposicao_diaria as E
        d = tempfile.mkdtemp()
        okx = {"real": {"ops": {"PARTI": {"estado": "aberta", "estrategia": "panico", "entrada": 0.04128, "stop": 0.037,
                                          "alvo": 0.04982, "risco_pct": 0.8, "stop_ok": 1}}},
               "abertas": {"XRP": {"tipo": "isolado"}}}
        st = {"ledger": [{"executed": True, "status": "OPEN", "asset": "SOL", "side": "LONG", "strategy": "X"}],
              "papel_fases": {"lateral": {"abertas": {"XRP": {}, "OP": {}}}}}
        json.dump(okx, open(os.path.join(d, "okx.json"), "w")); json.dump(st, open(os.path.join(d, "state.json"), "w"))
        rs = random.Random(1); base = [rs.gauss(0, 0.01) for _ in range(100)]
        series = {"PARTI": serie(rs, [0] * 100, 0.01), "SOL": serie(rs, base, 0.002), "XRP": serie(rs, base, 0.002),
                  "OP": serie(rs, base, 0.002)}
        series["PARTI"][-1] = 0.042
        out = E.correr(d, obter=lambda m: series.get(m, []))
        self.assertEqual(set(out["blocos"]), {"okx_real", "bybit_real", "papel_sombra"})
        self.assertEqual(out["blocos"]["bybit_real"]["n"], 1)
        p = out["blocos"]["papel_sombra"]
        self.assertIn("XRP", p["mesmo_ativo_varias_estrategias"])          # H40 LONG e fases SHORT no mesmo ativo
        r = out["okx_posicoes_reais"]["PARTI"]
        self.assertAlmostEqual(r["R_atual"], round((0.042 - 0.04128) / (0.04128 - 0.037), 2))
        self.assertGreater(r["risco_com_custos_pct_conta"], 0.8)


class Conflitos(unittest.TestCase):
    def test_tres_tipos(self):
        from tools import exposicao_diaria as E
        ex = [{"ativo": "PUMP", "lado": "LONG", "origem": "H40 papel (isolado)"}, {"ativo": "PUMP", "lado": "LONG", "origem": "H45 papel"},
              {"ativo": "BCH", "lado": "LONG", "origem": "H40 papel (isolado)"}, {"ativo": "BCH", "lado": "SHORT", "origem": "fases lateral papel"},
              {"ativo": "ADA", "lado": "SHORT", "origem": "fases lateral papel"}]
        c = E.conflitos(ex, {"PUMP": "g", "BCH": "g", "ADA": "g"})
        self.assertIn("BCH", c["mesmo_ativo_oposto"]); self.assertEqual(c["mesma_exposicao"], {"PUMP": ["H40 papel (isolado)", "H45 papel"]})
        self.assertEqual(c["grupo_oposto"][0]["long"], ["BCH", "PUMP"])
