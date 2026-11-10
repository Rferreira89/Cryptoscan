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
