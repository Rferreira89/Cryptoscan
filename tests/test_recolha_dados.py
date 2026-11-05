"""(05/11, L1) recolha de dados novos: so a vela fechada de ontem, sem repeticoes, e avaliacao so com dados
posteriores ao registo da hipotese."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import recolha_dados as R  # noqa: E402

DAY = 86400
AGORA = 1793923200 + 3600          # 2026-11-06 01:00 UTC


def dados():
    ontem = (AGORA // DAY - 1) * DAY
    v = [{"t": ontem - DAY, "o": 1, "h": 1, "l": 1, "c": 1, "usd": 1e6}, {"t": ontem, "o": 2, "h": 3, "l": 1.5, "c": 2.5, "usd": 3e7}]
    return {"AAA": {"velas": v, "px": 2.4, "px_global": 2.41, "fund": [(ontem + 3600, 0.0001), (ontem - 10, 0.5)], "validado": True},
            "BBB": {"velas": v[:1], "px": 1, "px_global": 1, "fund": [], "validado": None}}


class Recolha(unittest.TestCase):
    def test_so_a_vela_fechada_de_ontem(self):
        rs = R.linhas(dados(), {"AAA": 5e6}, {"AAA-USD_UM_XPERP-1": 1e5}, {"AAA": {"inst": "AAA-USD_UM_XPERP-1"}}, AGORA)
        self.assertEqual([r["moeda"] for r in rs], ["AAA"])                 # BBB sem a vela de ontem: fica de fora
        r = rs[0]
        self.assertEqual((r["data"], r["c"], r["validado"], r["oi_usd_global"], r["oi_xperp"]), ("2026-11-05", 2.5, 1, 5e6, 1e5))
        self.assertAlmostEqual(r["fund_xperp_24h"], 0.0001)                  # so o financiamento do dia

    def test_idempotente(self):
        with tempfile.TemporaryDirectory() as d:
            rs = R.linhas(dados(), {}, {}, {}, AGORA)
            self.assertEqual(R.gravar(d, rs), 1)
            self.assertEqual(R.gravar(d, rs), 0)
            self.assertEqual(len(R.dados_para_avaliar(d, "2026-11-01")), 1)

    def test_avaliacao_so_depois_do_registo(self):
        with tempfile.TemporaryDirectory() as d:
            R.gravar(d, R.linhas(dados(), {}, {}, {}, AGORA))
            self.assertEqual(R.dados_para_avaliar(d, "2026-11-05"), [])        # registada no proprio dia: ainda nada
            self.assertEqual(len(R.dados_para_avaliar(d, "2026-11-04")), 1)

    def test_sem_chaves_nem_ordens(self):
        src = open(R.__file__, encoding="utf-8").read()
        for p in ("/api/v5/trade", "/api/v5/account", "OKX_API", "privado("):
            self.assertNotIn(p, src)
        wf = open(".github/workflows/okx-recolha.yml", encoding="utf-8").read()
        for p in ("OKX_API", "OKX_PASSPHRASE", "DATA_KEY", "push -f", "push -q -f"):
            self.assertNotIn(p, wf)                                           # acumula: nunca reescreve o historico


if __name__ == "__main__":
    unittest.main()
