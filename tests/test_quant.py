"""(10/11) Modulo quant: DSR, PBO (CSCV) e vantagem residual face ao BTC.
Os dados destes testes sao SINTETICOS (gerados com semente fixa) e servem so para validar as formulas; nunca sao
resultados do CryptoScan. Referencias numericas: artigo do DSR (Bailey e Lopez de Prado 2014) e statsmodels 0.15
(OLS com HAC, maxlags=4, use_correction=True), calculados fora e fixados aqui."""
import json
import math
import os
import random
import tempfile
import unittest

from backtest.quant import dados as Q
from backtest.quant import dsr as D
from backtest.quant import estatistica as E
from backtest.quant import pbo as P
from backtest.quant import residual as RS


def ar1(n, phi, rng, sd=1.0):
    e = [0.0] * n
    for i in range(1, n):
        e[i] = phi * e[i - 1] + rng.gauss(0, sd)
    return e


class Estatistica(unittest.TestCase):
    def test_t_de_student_contra_valores_tabelados(self):
        self.assertAlmostEqual(E.t_cdf(2.0, 7), 0.957190335718512, places=10)        # scipy.stats.t.cdf(2, 7)
        self.assertAlmostEqual(E.t_ppf(0.975, 12), 2.178812829667228, places=6)       # tabela t(12)
        self.assertAlmostEqual(E.t_ppf(0.975, 10 ** 7), 1.959963984540054, places=5)  # tende para a normal

    def test_momentos(self):
        x = [1, 2, 3, 4, 100]
        self.assertGreater(E.assimetria(x), 1); self.assertGreater(E.curtose(x), 3)
        self.assertAlmostEqual(E.curtose([1, -1] * 50), 1.0)                          # dois pontos: curtose minima

    def test_inversa_e_singular(self):
        A = [[4, 7], [2, 6]]
        I = E.matmul(A, E.inversa(A))
        self.assertAlmostEqual(I[0][0], 1); self.assertAlmostEqual(I[0][1], 0)
        with self.assertRaises(ValueError):
            E.inversa([[1, 2], [2, 4]])


class DSR(unittest.TestCase):
    def test_exemplo_numerico_do_artigo(self):
        # Bailey e Lopez de Prado (2014): SR anual 2,5, T=1250 dias, assimetria -3, curtose 10, N=100, V[SR] anual 1/2 -> DSR ~ 0,9004
        sr = 2.5 / math.sqrt(250)
        sr0 = D.sr_max_esperado(100, 0.5 / 250)
        self.assertAlmostEqual(sr0, 0.1132, places=4)
        self.assertAlmostEqual(D.psr(sr, sr0, 1250, -3, 10), 0.9004, places=3)

    def test_mais_tentativas_exigem_mais(self):
        rng = random.Random(3); r = [rng.gauss(0.15, 1) for _ in range(200)]
        a, b, c = (D.dsr(r, n)["dsr"] for n in (1, 10, 1000))
        self.assertGreater(a, b); self.assertGreater(b, c)
        self.assertAlmostEqual(a, D.dsr(r, 1)["psr_zero"])                            # com 1 tentativa, DSR = PSR(0)

    def test_assimetria_negativa_e_caudas_baixam_a_confianca(self):
        self.assertLess(D.psr(0.1, 0, 300, -2, 9), D.psr(0.1, 0, 300, 0, 3))

    def test_sem_alfa_nao_passa(self):
        rng = random.Random(11); r = [rng.gauss(0, 1) for _ in range(500)]
        self.assertLess(D.dsr(r, 100)["dsr"], 0.5)

    def test_amostra_insuficiente_e_sem_variacao(self):
        self.assertEqual(D.dsr([0.5] * 10, 5)["estado"], "insuficiente")
        self.assertEqual(D.dsr([0.5] * 40, 5)["estado"], "insuficiente")
        self.assertEqual(D.dsr([1, None, float("nan")] * 5, 5)["t"], 5)              # dados incompletos ficam de fora

    def test_contagem_de_tentativas_vem_dos_registos(self):
        c = D.contar_tentativas({"lutadores": {"A": {}, "B": {}}})
        self.assertGreaterEqual(c["minimo"], 1)
        self.assertEqual(c["conservador"], c["minimo"] + c["partes"]["novas_registadas"] + 2)


class PBO(unittest.TestCase):
    def test_ruido_puro_da_cerca_de_metade(self):
        rng = random.Random(1)
        M = [[rng.gauss(0, 1) for _ in range(20)] for _ in range(400)]
        r = P.cscv(M, s=10)
        self.assertEqual(r["combinacoes"], 252)                                       # C(10, 5)
        self.assertTrue(0.3 <= r["pbo"] <= 0.7, r["pbo"])

    def test_alfa_conhecido_da_pbo_baixa(self):
        rng = random.Random(2)
        M = [[rng.gauss(0, 1) + (0.5 if j == 3 else 0) for j in range(20)] for _ in range(400)]
        r = P.cscv(M, s=10, nomes=[f"c{j}" for j in range(20)])
        self.assertLess(r["pbo"], 0.05); self.assertEqual(next(iter(r["escolhidas"])), "c3")

    def test_sobreajuste_da_pbo_alta(self):
        # cada configuracao e boa em alguns blocos e ma noutros, com media total zero: o melhor no treino perde fora
        rng = random.Random(4); N, B = 30, 10
        sg = [[rng.choice([1, -1]) for _ in range(N)] for _ in range(B)]
        M = [[rng.gauss(0, 1) + 0.8 * (sg[i // 40][j] - sum(sg[b][j] for b in range(B)) / B) for j in range(N)] for i in range(400)]
        self.assertGreater(P.cscv(M, s=10)["pbo"], 0.8)

    def test_estrategias_correlacionadas_duplicadas_nao_mudam_a_conclusao(self):
        rng = random.Random(5)
        base = [[rng.gauss(0, 1) + (0.4 if j == 0 else 0) for j in range(6)] for _ in range(240)]
        dup = [r + [r[0] + rng.gauss(0, .01), r[0] + rng.gauss(0, .01)] for r in base]   # duas copias quase iguais da melhor
        self.assertLess(P.cscv(dup, s=8)["pbo"], 0.1)

    def test_sem_fugas_treino_e_teste_disjuntos_e_embargo(self):
        lims = P.blocos(100, 4)
        self.assertEqual(lims, [(0, 25), (25, 50), (50, 75), (75, 100)])
        tr, te = P.indices(lims, {0, 2})
        self.assertFalse(set(tr) & set(te)); self.assertEqual(sorted(tr + te), list(range(100)))
        tr, te = P.indices(lims, {0, 2}, embargo=3)
        self.assertFalse(set(tr) & set(te))
        for x in (25, 26, 27, 47, 48, 49, 75, 76, 77):                                 # junto as fronteiras com treino
            self.assertNotIn(x, te)
        self.assertIn(30, te)

    def test_ordem_temporal_mantida_e_reprodutivel(self):
        rng = random.Random(6); M = [[rng.gauss(0, 1) for _ in range(8)] for _ in range(160)]
        a, b = P.cscv(M, s=8), P.cscv(M, s=8)
        self.assertEqual(a["pbo"], b["pbo"]); self.assertEqual(a["lambdas"], b["lambdas"])

    def test_insuficiente(self):
        self.assertEqual(P.cscv([[1, 2]] * 20, s=8)["estado"], "insuficiente")
        self.assertEqual(P.cscv([[1]] * 100, s=8)["estado"], "insuficiente")
        self.assertEqual(P.cscv([[1, 2]] * 100, s=7)["estado"], "insuficiente")

    def test_posicoes_com_empates(self):
        self.assertEqual(P._posicoes([3, 1, 3, 2]), [3.5, 1, 3.5, 2])

    def test_matriz_diaria_corta_ao_periodo_comum_ou_usa_a_uniao(self):
        dias, nomes, M = P.matriz_diaria({"a": {"d1": 1, "d3": 2, "d5": 1}, "b": {"d2": 1, "d4": -1}})
        self.assertEqual(dias, ["d2", "d3", "d4"]); self.assertEqual(M, [[0.0, 1], [2, 0.0], [0.0, -1]])
        dias, _, M = P.matriz_diaria({"a": {"d1": 1}, "b": {"d3": -1}}, periodo="uniao")
        self.assertEqual(dias, ["d1", "d3"]); self.assertEqual(M, [[1, 0.0], [0.0, -1]])
        self.assertEqual(P.cscv([], s=8)["razao"], "sem periodos com dados")


class Residual(unittest.TestCase):
    def test_ols_hac_igual_ao_statsmodels(self):
        rng = random.Random(5); x = [rng.gauss(0, 1) for _ in range(120)]; e = ar1(120, 0.6, rng)
        y = [0.3 + 0.8 * a + b for a, b in zip(x, e)]
        r = RS.ols_hac(y, [[1, a] for a in x], lags=4)
        # statsmodels 0.15: OLS(...).fit(cov_type="HAC", cov_kwds={"maxlags": 4, "use_correction": True})
        for got, ref in zip(r["coef"] + r["se"], [0.11519934529047338, 0.6669328974344424, 0.20266348318476834, 0.10901588531188836]):
            self.assertAlmostEqual(got, ref, places=9)
        self.assertAlmostEqual(r["r2"], 0.2396894342485396, places=10)
        self.assertEqual(RS.lags_nw(120), 4)

    def test_autocorrelacao_alarga_o_erro_face_ao_ols_simples(self):
        rng = random.Random(8); x = ar1(300, 0.8, rng); e = ar1(300, 0.8, rng)
        y = [0.1 + 0.5 * a + b for a, b in zip(x, e)]
        X = [[1, a] for a in x]
        self.assertGreater(RS.ols_hac(y, X, lags=8)["se"][0], 1.5 * RS.ols_hac(y, X, lags=0)["se"][0])

    def _btc(self, rng, dias=200):
        p, t0, pts = 30000.0, 1_700_000_000, []
        for h in range(dias * 24):
            p *= math.exp(rng.gauss(0, 0.006)); pts.append((t0 + h * 3600, p))
        return RS.SerieBTC(pts), t0

    def _ops(self, btc, t0, rng, alfa, beta, n=150, ms=False):
        ops = []
        for i in range(n):
            te = t0 + 3600 * (5 + i * 30); ts = te + 3600 * 20
            x = btc.preco_em(ts) / btc.preco_em(te) - 1
            k = 1000 if ms else 1
            ops.append({"t_entrada": te * k, "t_saida": ts * k, "R": alfa + beta * x + rng.gauss(0, 0.3)})
        return ops

    def test_sem_alfa_so_beta(self):
        rng = random.Random(9); btc, t0 = self._btc(rng)
        r = RS.analisar(self._ops(btc, t0, rng, 0.0, 40.0), btc)
        self.assertEqual(r["estado"], "calculado"); self.assertGreater(r["p_alfa"], 0.05)
        self.assertTrue(r["ic_beta"][0] < 40 < r["ic_beta"][1]); self.assertIn("sem evidencia", r["veredito"])

    def test_alfa_conhecido_detetado(self):
        rng = random.Random(10); btc, t0 = self._btc(rng)
        r = RS.analisar(self._ops(btc, t0, rng, 0.25, 20.0), btc)
        self.assertLess(r["p_alfa"], 0.01); self.assertTrue(r["ic_alfa"][0] < 0.25 < r["ic_alfa"][1])
        self.assertIn("positiva", r["veredito"])
        self.assertEqual(len(r["metades"]), 2); self.assertTrue(r["movel"])
        self.assertIn("subida", r["regimes"]); self.assertIn("descida", r["regimes"])

    def test_timestamps_em_milissegundos_e_desalinhados(self):
        rng = random.Random(12); btc, t0 = self._btc(rng)
        a = RS.analisar(self._ops(btc, t0, random.Random(1), 0.1, 10.0), btc)
        b = RS.analisar(self._ops(btc, t0, random.Random(1), 0.1, 10.0, ms=True), btc)
        self.assertAlmostEqual(a["alfa"], b["alfa"]); self.assertAlmostEqual(a["beta"], b["beta"])
        mau = [{"t_entrada": t0 + 7200, "t_saida": t0 + 3600, "R": 1}]
        linhas, excl = RS.alinhar_por_operacao(mau, btc)
        self.assertEqual(linhas, []); self.assertIn("desalinhados", excl[0][1])

    def test_dados_incompletos_nunca_sao_preenchidos(self):
        rng = random.Random(13); btc, t0 = self._btc(rng, dias=10)
        ops = [{"t_entrada": t0 + 3600 * 24 * 20, "t_saida": t0 + 3600 * 24 * 21, "R": 1},      # depois do fim do BTC
               {"t_entrada": t0 + 3600, "t_saida": None, "R": 1}, {"t_entrada": t0, "t_saida": t0 + 7200, "R": None}]
        r = RS.analisar(ops, btc)
        self.assertEqual(r["estado"], "insuficiente"); self.assertEqual(r["excluidas"], 3)
        self.assertIn("sem preco do BTC na entrada ou na saida", r["motivos_exclusao"])

    def test_modo_diario_alinha_por_dia_utc(self):
        rng = random.Random(14); btc, t0 = self._btc(rng, dias=60)
        ops = [{"t_entrada": t0 + 86400 * d, "t_saida": t0 + 86400 * d + 3600 * 23, "R": 0.5} for d in range(2, 50, 2)]
        linhas, _ = RS.alinhar_diario(ops, btc)
        dias = [l["dia"] for l in linhas]
        self.assertEqual(dias, sorted(dias)); self.assertEqual(len(dias), len(set(dias)))
        self.assertIn(0.0, [l["y"] for l in linhas])                                   # dias ativos sem fecho = 0

    def test_reprodutivel(self):
        rng = random.Random(15); btc, t0 = self._btc(rng)
        ops = self._ops(btc, t0, random.Random(2), 0.05, 5.0)
        a, b = RS.analisar(ops, btc), RS.analisar(ops, btc)
        self.assertEqual((a["alfa"], a["se_alfa"], a["p_alfa"]), (b["alfa"], b["se_alfa"], b["p_alfa"]))


class Integracao(unittest.TestCase):
    def test_ambientes_separados_e_avaliacao_completa(self):
        from tools import quant_avaliar as QA
        t0 = 1_793_000_000
        O = {"real": {"hist": [{"asset": "X", "estado": "fechada", "entrada": 1.0, "stop": 0.9, "saida": 1.1, "t_fill": t0, "fechado": t0 + 7200},
                               {"asset": "Y", "estado": "cancelada"}]},
             "fechadas": [{"asset": "Z", "t_sig": t0, "t_fim": t0 + 3600, "r": -1}], "recuo": {"fechadas": []}}
        St = {"papel_panico": {"fechadas": [{"asset": "W", "t_fill": t0, "t_fim": t0 + 3600, "r": 0.5}]}}
        S = {"journal": {"rows": [{"asset": "V", "strategy": "PULLBACK", "mode": "REAL", "status": "CLOSED", "executed": True, "result_r": 1.2, "opened_at": t0, "closed_at": t0 + 3600},
                                  {"asset": "U", "strategy": "PULLBACK", "mode": "REAL", "status": "CLOSED", "executed": False, "result_r": 2}]}}
        Sb = {"estado": {"fechadas": [{"asset": "T", "t_fill": t0, "t_fim": t0 + 3600, "r": 0.3}]}}
        Dv = {"campos": ["t", "preco"], "moedas": {"BTC": [[t0 + h * 3600, 70000 + h] for h in range(48)]}}
        with tempfile.TemporaryDirectory() as d:
            for n, v in {"okx.json": O, "state.json": St, "scan.json": S, "okx_tfshort_sombra.json": Sb, "derivados.json": Dv}.items():
                json.dump(v, open(os.path.join(d, n), "w"))
            base = Q.carregar(d)
            amb = {(o["ambiente"], o["estrategia"]) for o in base["operacoes"]}
            self.assertEqual(amb, {("OKX_REAL", "H40"), ("PAPEL", "H40"), ("PAPEL", "H45"), ("BYBIT_REAL", "PULLBACK"), ("SOMBRA", "TF-SHORT")})
            self.assertAlmostEqual([o for o in base["operacoes"] if o["ambiente"] == "OKX_REAL"][0]["R"], 1.0)
            r = QA.avaliar(base)
            self.assertEqual(len([l for l in r["estrategias"] if l["estrategia"] == "H40"]), 2)     # real e papel nunca somados
            self.assertTrue(all(l["dsr_minimo"]["estado"] == "insuficiente" for l in r["estrategias"] if l.get("n")))
            self.assertIn("H57", {l["estrategia"] for l in r["estrategias"]})
            self.assertTrue(all(p["estado"] == "insuficiente" for p in r["pbo"].values()))
            self.assertIn("Avaliacao quantitativa retrospetiva", QA.markdown(r))

    def test_operacoes_sem_hora_contam_no_dsr_mas_nao_no_residual(self):
        from tools import quant_avaliar as QA
        base = {"operacoes": [{"ambiente": "PAPEL", "estrategia": "ARENA:TREND_DAILY", "ativo": "A", "t_entrada": None, "t_saida": None, "R": 0.5}] * 3,
                "btc": [], "notas": [], "forma": None}
        l = [x for x in QA.avaliar(base)["estrategias"] if x["estrategia"] == "ARENA:TREND_DAILY"][0]
        self.assertEqual((l["n"], l["sem_hora"], l["desde"]), (3, 3, None)); self.assertEqual(l["residual"]["estado"], "insuficiente")

    def test_arena_exclui_operacoes_executadas_em_real(self):
        t0 = 1_793_000_000
        st = {"ledger": [{"id": "a1", "kind": "4H", "status": "CLOSED", "result_r": 1, "entry": 1, "stop": .9, "tp": [1.2], "strategy": "PULLBACK", "asset": "A", "opened_at": t0, "closed_at": t0 + 9, "executed": True},
                         {"id": "a2", "kind": "4H", "status": "CLOSED", "result_r": -1, "entry": 1, "stop": .9, "tp": [1.2], "strategy": "PULLBACK", "asset": "B", "opened_at": t0, "closed_at": t0 + 9}]}
        ops, excl = Q.arena_papel(st)
        self.assertEqual(excl, 1); self.assertEqual([o["ativo"] for o in ops], ["B"]); self.assertEqual(ops[0]["ambiente"], "PAPEL")

    def test_modulo_nao_toca_em_execucao_nem_estrategias(self):
        raiz = os.path.join(os.path.dirname(__file__), "..")
        src = ""
        for p in ["backtest/quant/dsr.py", "backtest/quant/pbo.py", "backtest/quant/residual.py", "backtest/quant/dados.py", "tools/quant_avaliar.py"]:
            with open(os.path.join(raiz, p), encoding="utf-8") as f:
                src += f.read()
        for proibido in ("okx_exec", "executor", "privado(", "cancel-order", "/trade/order", "okx_config", "alerts.send", "urllib", "requests"):
            self.assertNotIn(proibido, src)


if __name__ == "__main__":
    unittest.main()
