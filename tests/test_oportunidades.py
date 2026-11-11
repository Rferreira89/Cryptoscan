"""(11/11) Global Opportunity Hunter: detetores, classificacao explicavel, evidencia so medida, IC sem futuro,
sem autoridade de execucao."""
import gzip
import json
import os
import random
import sys
import tempfile
import unittest

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.join(RAIZ, "tools"))
from engine import oportunidades as OP  # noqa: E402
import cacador_global as CG  # noqa: E402


class Detetores(unittest.TestCase):
    def test_funding_empatado_no_valor_por_omissao_nao_e_extremo(self):
        a = {"funding": 0.0001, "funding_hist": [0.0001] * 30 + [0.00005] * 5}
        self.assertIsNone(OP.funding_extremo(a))

    def test_funding_muito_negativo_propoe_long(self):
        a = {"funding": -0.002, "funding_hist": [0.0001 * i for i in range(30)]}
        f, d, m = OP.funding_extremo(a)
        self.assertEqual(d, "LONG")

    def test_oi_com_queda(self):
        self.assertEqual(OP.oi_variacao({"oi_chg_24h": 0.2, "ret_24h": -0.06})[1], "SHORT")
        self.assertEqual(OP.oi_variacao({"oi_chg_24h": -0.2, "ret_24h": -0.06})[1], "LONG")
        self.assertIsNone(OP.oi_variacao({"oi_chg_24h": 0.02, "ret_24h": -0.06}))

    def test_detetor_com_dados_em_falta_nao_dispara(self):
        for fn in OP.DETETORES.values():
            self.assertIsNone(fn({}))


class Classificacao(unittest.TestCase):
    A = {"ativo": "X", "t": 1, "preco": 1.0, "ret_24h": -0.12, "ret_3d": -0.2, "atr_pct": 0.04, "regime": "BEAR",
         "oi_chg_24h": -0.15, "spread_bps": 10}

    def test_registo_completo_e_sem_autoridade(self):
        o = OP.classificar(self.A)
        for campo in ("ativo", "direcao_potencial", "regime", "sinais", "qualidade_dados", "risco", "custos_estimados_pct",
                      "invalidacao", "expectativa_estimada", "confianca_estatistica", "motivo"):
            self.assertIn(campo, o)
        self.assertEqual(o["autoridade"], "nenhuma (sombra)")
        self.assertEqual(o["direcao_potencial"], "LONG")
        self.assertAlmostEqual(o["invalidacao"], 0.92)

    def test_sem_evidencia_a_expectativa_e_desconhecida(self):
        o = OP.classificar(self.A)
        self.assertEqual(o["expectativa_estimada"], "desconhecida")

    def test_evidencia_a_favor_mas_liquido_negativo_nao_e_positiva(self):
        ev = {"reversao_continuacao": {"ic_na_direcao": 0.03, "t": 3.0, "dias": 600, "liquido_pct": -0.8, "fonte": "t"}}
        o = OP.classificar(self.A, ev)
        self.assertEqual(o["expectativa_estimada"], "IC a favor mas sem resultado liquido positivo")

    def test_evidencia_positiva_completa(self):
        ev = {"reversao_continuacao": {"ic_na_direcao": 0.03, "t": 3.0, "dias": 600, "liquido_pct": 0.2},
              "oi": {"ic_na_direcao": 0.02, "t": 2.5, "dias": 400, "liquido_pct": 0.1}}
        self.assertEqual(OP.classificar(self.A, ev)["expectativa_estimada"], "positiva com evidencia")

    def test_poucos_dias_de_evidencia(self):
        ev = {"reversao_continuacao": {"ic_na_direcao": 0.5, "t": 9, "dias": 5, "liquido_pct": 3}}
        self.assertIn("menos de 30", OP.classificar(self.A, ev)["confianca_estatistica"])

    def test_nenhum_sinal_nenhuma_oportunidade(self):
        self.assertIsNone(OP.classificar({"ativo": "Y", "ret_24h": 0.001, "atr_pct": 0.04}))

    def test_qualidade(self):
        self.assertEqual(OP.qualidade({})["nivel"], "baixa")
        q = OP.qualidade({c: 1 for c in OP.CAMPOS_ESPERADOS})
        self.assertEqual(q["nivel"], "alta")


class IC(unittest.TestCase):
    def test_spearman(self):
        self.assertAlmostEqual(OP.spearman([1, 2, 3, 4, 5], [5, 6, 7, 8, 9]), 1.0)
        self.assertAlmostEqual(OP.spearman([1, 2, 3, 4, 5], [9, 8, 7, 6, 5]), -1.0)

    def test_ic_diario_e_resumo(self):
        rnd = random.Random(1)
        linhas = []
        for d in range(60):
            for a in range(20):
                x = rnd.gauss(0, 1)
                linhas.append({"dia": d, "ativo": a, "f": x, "ret_seguinte": -0.3 * x + rnd.gauss(0, 1)})
        r = OP.resumo_ic(OP.ic_diario(linhas, "f"))
        self.assertLess(r["ic_medio"], 0)
        self.assertLess(r["t"], -3)


def _velas(caminho, n, p0=100.0, seed=0, salto_em=None):
    rnd = random.Random(seed)
    p = p0
    with gzip.open(caminho, "wt") as f:
        for i in range(n):
            t = 1_600_000_000 - 1_600_000_000 % 86400 + i * 14400
            o = p
            p = p * (1 + rnd.gauss(0, 0.01)) * (3.0 if salto_em is not None and i == salto_em else 1.0)
            f.write(f"{t},{o},{max(o, p) * 1.005},{min(o, p) * 0.995},{p},1000,{1000 * p}\n")


class SemFuturo(unittest.TestCase):
    def test_caracteristicas_nao_mudam_com_velas_futuras(self):
        with tempfile.TemporaryDirectory() as d:
            _velas(os.path.join(d, "BTC.csv.gz"), 500, seed=1)
            _velas(os.path.join(d, "A.csv.gz"), 500, seed=2)
            _velas(os.path.join(d, "B.csv.gz"), 500, seed=2, salto_em=450)   # igual a A ate a vela 449
            btc = {x[0]: x[4] for x in CG.ler_velas(os.path.join(d, "BTC.csv.gz"))}
            va, vb = CG.ler_velas(os.path.join(d, "A.csv.gz")), CG.ler_velas(os.path.join(d, "B.csv.gz"))
            self.assertEqual(CG.caracteristicas_velas(va, 440, btc), CG.caracteristicas_velas(vb, 440, btc))

    def test_painel_so_usa_velas_fechadas(self):
        with tempfile.TemporaryDirectory() as d:
            _velas(os.path.join(d, "BTC.csv.gz"), 500, seed=1)
            _velas(os.path.join(d, "A.csv.gz"), 500, seed=2)
            v = CG.ler_velas(os.path.join(d, "A.csv.gz"))
            now = v[450][0] + 100                                          # a vela 450 ainda esta aberta
            p = CG.painel(d, d, "-", now)
            self.assertEqual(p["A"]["t"], v[449][0])


class SemExecucao(unittest.TestCase):
    def test_modulos_do_cacador_nao_chamam_corretoras_privadas(self):
        for f in ("engine/oportunidades.py", "tools/cacador_global.py", "backtest/estudos/novos/cacador_ic_historico.py"):
            src = open(os.path.join(RAIZ, f)).read()
            for proibido in ("okx_exec", "privado(", "/trade/", "/v5/order", "engine.executor", "account.get", "urlopen"):
                self.assertNotIn(proibido, src, f"{f}: {proibido}")


class Evidencia(unittest.TestCase):
    def test_fica_a_mais_conservadora(self):
        with tempfile.TemporaryDirectory() as d:
            def estudo(nome, ic, t, spread):
                p = os.path.join(d, nome)
                json.dump({"caracteristicas": {"ret_3d": {"ic_medio": ic, "t": t, "dias": 600, "fonte": nome,
                                                          "quintis_baixo_menos_alto": {"spread_medio_pct": spread, "custo_ida_volta_dois_lados_pct": 0.4,
                                                                                       "liquido_estimado_pct": spread - 0.4}}}}, open(p, "w"))
                return p
            ev = CG.evidencia_de_ic([estudo("a", -0.05, -8, 0.6), estudo("b", -0.02, -3, -0.4)])
            e = ev["reversao_continuacao"]
            self.assertAlmostEqual(e["ic_na_direcao"], 0.02)
            self.assertAlmostEqual(e["liquido_pct"], -0.8)


if __name__ == "__main__":
    unittest.main()
