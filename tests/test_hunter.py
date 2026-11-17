"""(17/11) Global Opportunity Hunter: sem olhar para a frente, estatistica corrigida, geometria, funding, universo,
registo do teste final e um ciclo completo do motor sobre dados sinteticos."""
import random
import unittest

try:                                     # numpy so e instalado nos workflows de investigacao (nao no scanner)
    import numpy as np
    from tools.hunter import dados as DD, estat as ES, familias as FA, geometria as GE, motor as MO
except ImportError:                      # pragma: no cover
    np = None

H = 1800


def velas(n=1200, seed=1, t0=1_780_000_000 // 14400 * 14400, deriva=0.0):
    rng = random.Random(seed)
    p, out = 100.0, []
    for i in range(n):
        o = p
        p = max(0.5, p * (1 + deriva + rng.gauss(0, 0.008)))
        out.append({"t": t0 + i * H, "o": o, "h": max(o, p) * (1 + abs(rng.gauss(0, 0.003))),
                    "l": min(o, p) * (1 - abs(rng.gauss(0, 0.003))), "c": p, "v": 100 * (1 + abs(rng.gauss(0, 1)))})
    return out


def S_de(v):
    S = {k: np.array([x[k] for x in v], dtype=float) for k in "ohlcv"}
    S["t"] = np.array([x["t"] for x in v])
    S["atr"] = np.array([np.nan if a is None else a for a in GE.atr_serie(v)])
    return S


SEM_NUMPY = unittest.skipIf(np is None, "numpy nao instalado (so nos workflows de investigacao)")


@SEM_NUMPY
class Familias(unittest.TestCase):
    def test_desloca_sem_dar_a_volta(self):
        x = np.arange(5.0)
        self.assertTrue(np.isnan(FA.sh(x, 1)[0]))
        self.assertEqual(FA.sh(x, 1)[1:].tolist(), [0, 1, 2, 3])
        self.assertTrue(np.isnan(FA.prev_max(x, 3)[2]))
        self.assertEqual(FA.prev_max(x, 3)[3], 2.0)

    def test_nenhuma_familia_olha_para_a_frente(self):
        v = velas(700, 3)
        corte = 500
        mex = [dict(b) for b in v]
        for b in mex[corte + 1:]:
            b.update(o=b["o"] * 1.7, h=b["h"] * 2, l=b["l"] * 1.5, c=b["c"] * 1.8, v=b["v"] * 30)
        S, Q = S_de(v), S_de(mex)
        n = len(v)
        M = {"btc_ret_1": np.linspace(-0.03, 0.03, n), "btc_ret_6": np.linspace(-0.1, 0.1, n),
             "btc_ret_24": np.linspace(-0.1, 0.1, n), "btc_acima": (np.arange(n) % 2).astype(float),
             "mercado_ret_6": np.linspace(-0.06, 0.06, n), "mercado_ret_24": np.linspace(-0.06, 0.06, n),
             "funding": np.sin(np.arange(n) / 7) * 1e-4}
        with np.errstate(all="ignore"):
            for fam, (fn, grelha) in FA.FAMILIAS.items():
                for p in grelha:
                    a, b = fn(S, M, p), fn(Q, M, p)
                    for x, y in zip(a, b):
                        self.assertEqual([i for i in x if i <= corte], [i for i in y if i <= corte], (fam, p))

    def test_familias_cobrem_os_seis_grupos(self):
        self.assertEqual(set(FA.GRUPO.values()), set("ABCDEF"))
        self.assertEqual(set(FA.GRUPO), set(FA.FAMILIAS))


@SEM_NUMPY
class Estatistica(unittest.TestCase):
    def test_bootstrap_por_blocos_trata_o_dia_como_unidade(self):
        # 200 operacoes no mesmo dia valem como 1 bloco: sem ic nem significancia
        ops = [{"t": 1_000_000, "d": 0.5} for _ in range(200)]
        m, ic, p = ES.bootstrap_blocos(ops)
        self.assertEqual((m, ic, p), (0.5, None, 1.0))
        ops = [{"t": 86400 * k, "d": 0.3 + random.Random(k).gauss(0, 0.1)} for k in range(60)]
        m, ic, p = ES.bootstrap_blocos(ops)
        self.assertLess(p, 0.01)
        self.assertLess(ic[0], m)

    def test_holm_cumulativo(self):
        ps = {"a": 0.001, "b": 0.02}
        self.assertEqual(ES.holm(ps)["a"], 0.002)
        self.assertEqual(ES.holm(ps, m_total=50)["a"], 0.05)     # rondas anteriores contam

    def test_teste_final_so_uma_vez(self):
        r = ES.Registo()
        r.nova_ronda(10)
        r.nova_ronda(5)
        self.assertEqual(r.d["hipoteses_avaliadas"], 15)
        rid = ES.regra_id({"x": 1})
        self.assertTrue(r.pode_testar(rid))
        r.marcar_teste(rid, {"n": 3})
        self.assertFalse(r.pode_testar(rid))
        with self.assertRaises(ValueError):
            r.marcar_teste(rid, {})

    def test_cortes(self):
        a, b = ES.cortes(0, 100)
        self.assertEqual((a, b), (50, 75))
        self.assertEqual([ES.periodo(t, (a, b)) for t in (10, 60, 90)], ["treino", "validacao", "teste"])


@SEM_NUMPY
class Geometria(unittest.TestCase):
    def v(self, barras):
        return [{"t": k * H, "o": o, "h": h, "l": l, "c": c, "v": 1} for k, (o, h, l, c) in enumerate(barras)]

    def test_stop_antes_do_alvo_e_gap(self):
        v = self.v([(100, 100, 100, 100), (100, 100, 100, 100), (100, 103, 97, 100)])
        r = GE.simular(v, 0, "LONG", 1.0, {"tipo": "fixa", "k": 2, "tp": 1, "hold": 2}, comissao=0, deslize=0)
        self.assertEqual(r["saida"], "stop")
        self.assertAlmostEqual(r["r"], -1.0)
        v = self.v([(100, 100, 100, 100), (100, 100, 100, 100), (90, 91, 89, 90)])
        r = GE.simular(v, 0, "LONG", 1.0, {"tipo": "fixa", "k": 2, "tp": 3, "hold": 2}, comissao=0, deslize=0)
        self.assertAlmostEqual(r["r"], -5.0)                     # gap atravessa o stop: sai na abertura

    def test_short_parcial_e_trailing(self):
        v = self.v([(100, 100, 100, 100), (100, 100, 100, 100), (100, 100, 97.5, 98), (98, 98.5, 95.5, 96)])
        r = GE.simular(v, 0, "SHORT", 1.0, {"tipo": "parcial", "k": 2, "tp": 2, "hold": 3}, comissao=0, deslize=0)
        self.assertEqual(r["saida"], "alvo")
        self.assertAlmostEqual(r["r"], 0.5 + 0.5 * 2)
        r = GE.simular(v, 0, "SHORT", 1.0, {"tipo": "trailing", "k": 1, "tp": None, "hold": 3}, comissao=0, deslize=0)
        self.assertIn(r["saida"], ("stop", "tempo"))

    def test_funding_real_e_cenario(self):
        f, fonte = GE.funding_entre([(1000, 0.001), (29800, 0.002)], 900, 30000, "LONG")
        self.assertEqual(fonte, "real")
        self.assertAlmostEqual(f, 0.003)
        f, fonte = GE.funding_entre([(1000, 0.001)], 900, 30000, "SHORT")
        self.assertAlmostEqual(f, -0.001)
        f, fonte = GE.funding_entre([(10 ** 9, 0.001)], 0, 57600, "LONG", cenario_taxa=0.0002)
        self.assertEqual(fonte, "cenario")
        self.assertAlmostEqual(f, 0.0004)

    def test_custos_e_funding_entram_no_r(self):
        v = self.v([(100, 100, 100, 100), (100, 100, 100, 100), (100, 100.5, 99.5, 100), (100, 100, 100, 100)])
        a = GE.simular(v, 0, "LONG", 1.0, {"tipo": "fixa", "k": 1, "tp": 3, "hold": 2}, comissao=0.05, deslize=0)
        self.assertAlmostEqual(a["custos_r"], 100 * 0.1 / 100 / 1.0)
        self.assertAlmostEqual(a["r"], -a["custos_r"])


@SEM_NUMPY
class Dados(unittest.TestCase):
    def test_universo_todos_os_xperps_e_classes(self):
        inst = [{"instId": "BTC-USD_UM_XPERP-310404", "state": "live", "ruleType": "xperp", "instCategory": "1",
                 "ctVal": "0.0001", "ctValCcy": "BTC", "minSz": "1", "lotSz": "1", "tickSz": "0.1", "listTime": "1"},
                {"instId": "AAPL-USD_UM_XPERP-310404", "state": "live", "ruleType": "xperp", "instCategory": "3",
                 "ctVal": "0.01", "ctValCcy": "AAPL", "minSz": "1", "lotSz": "1", "tickSz": "0.01", "listTime": "1"},
                {"instId": "NEW-USD_UM_XPERP-310404", "state": "live", "ruleType": "pre_market", "instCategory": "1"},
                {"instId": "BTC-USD-SWAP", "state": "live"}]
        tick = [{"instId": "BTC-USD_UM_XPERP-310404", "last": "90000", "vol24h": "1000"}]
        req = lambda path, params=None: inst if "instruments" in path else tick
        u = DD.universo(req)
        self.assertEqual(sorted(u), ["AAPL", "BTC"])
        self.assertEqual(u["AAPL"]["classe"], "equity")
        self.assertAlmostEqual(u["BTC"]["vol24h_usd"], 1000 * 0.0001 * 90000)
        self.assertIn("por confirmar", u["BTC"]["negociavel"])

    def test_historico_marca_desaparecidos(self):
        hist = {}
        DD.atualizar_historico(hist, {"A": {"inst": "A-1", "classe": "crypto"}, "B": {"inst": "B-1", "classe": "crypto"}}, 1)
        m = DD.atualizar_historico(hist, {"A": {"inst": "A-1", "classe": "crypto"}}, 2)
        self.assertEqual(m["desaparecidos"], ["B"])
        self.assertEqual(hist["B"]["desaparecido_em"], 2)

    def test_avisos_nao_fatais_nao_excluem(self):
        v = velas(300)
        for b in v[-40:-30]:
            b["v"] = 0.0                                       # velas sem volume: aviso, nao exclusao
        v[-5]["v"] = 1e9
        ok, motivos = DD.validar(v, H, v[-1]["t"] + H)
        self.assertTrue(ok, motivos)
        del v[-20]
        ok, motivos = DD.validar(v, H, v[-1]["t"] + H)
        self.assertFalse(ok)

    def test_reamostrar(self):
        v = velas(17, t0=1_780_000_000 // 14400 * 14400)
        h1 = DD.reamostrar(v, "1H")
        self.assertEqual(len(h1), 8)
        self.assertEqual(h1[0]["o"], v[0]["o"])
        self.assertEqual(h1[0]["c"], v[1]["c"])
        self.assertEqual(len(DD.reamostrar(v, "4H")), 2)


@SEM_NUMPY
class Motor(unittest.TestCase):
    def test_ciclo_completo_sintetico(self):
        dados = {}
        for k, b in enumerate(["BTC", "AAA", "BBB", "CCC"]):
            v = velas(2600, seed=k + 10)
            dados[b] = {"info": {"classe": "crypto", "tier": "A"}, "30m": v,
                        "funding": [(v[0]["t"] + 28800 * j, 0.0001) for j in range(1, 150)]}
        reg = ES.Registo()
        out = MO.correr(dados, reg, log=lambda *a: None, orcamento_evolucao=10, max_validacao=3)
        self.assertIn("diagnostico", out)
        self.assertGreater(len(out["diagnostico"]), 100)
        for v in out["hipoteses"].values():
            self.assertIn(v["veredicto"], ("CANDIDATA", "PROMISSORA", "EXPLORATORIA", "REJEITADA"))
            self.assertIn("p_holm_validacao", v)
        self.assertGreaterEqual(reg.d["hipoteses_avaliadas"], len(out["hipoteses"]))


if __name__ == "__main__":
    unittest.main()


@SEM_NUMPY
class Papel(unittest.TestCase):
    def test_volta_abre_acompanha_fecha_e_mede_o_funil(self):
        import json, os, tempfile
        from tools.hunter import papel as PA
        d = tempfile.mkdtemp()
        os.makedirs(os.path.join(d, "hunter"))
        estr = [{"id": "x1", "familia": "momentum_regime", "parametros": {"k": 3, "x": 0.0}, "tf": "30m", "lado": "LONG",
                 "filtro": None, "stop_ref": "30m", "saida": {"tipo": "fixa", "k": 1.5, "tp": 2.0, "hold": 8},
                 "veredicto": "EXPLORATORIA"}]
        with open(os.path.join(d, "hunter", "papel_estrategias.json"), "w") as f:
            json.dump({"estrategias": estr}, f)
        v = velas(400, seed=4, deriva=0.002)
        uni = {"AAA": {"inst": "AAA-USD_UM_XPERP-1", "classe": "crypto"}}
        now = v[-1]["t"] + H
        corte = len(v) - 12
        st = PA.volta(d, now=v[corte]["t"] + H, uni=uni, velas={"30m": {"AAA": v[:corte + 1]}}, funding_fn=lambda i: [],
                      spread_fn=lambda: {})
        self.assertEqual(st["funil_ultima"]["instrumentos_descobertos"], 1)
        self.assertGreaterEqual(st["funil_ultima"]["sinais_brutos"], st["funil_ultima"]["abertas_novas"])
        abertas = len(st["abertas"])
        st = PA.volta(d, now=now, uni=uni, velas={"30m": {"AAA": v}}, funding_fn=lambda i: [], spread_fn=lambda: {})
        self.assertEqual(st["voltas"], 2)
        if abertas:
            fech = [o for o in st["fechadas"] if o.get("r") is not None]
            self.assertTrue(fech or st["abertas"])
            for o in fech:
                for campo in ("id_op", "b", "mercado", "lado", "tf", "estrategia", "versao_estrategia", "versao_codigo",
                              "t_sinal", "t_entrada", "entrada", "stop_inicial", "saida", "tamanho", "custos", "funding_pct",
                              "r", "resultado_pct_preco", "permanencia_min", "motivo", "regime", "acontecimento",
                              "decisao", "historico", "preco_saida_equivalente"):
                    self.assertIn(campo, o)
        self.assertIn("PAPEL", st["aviso"])

    def test_papel_nao_toca_em_executores(self):
        import os
        raiz = os.path.join(os.path.dirname(__file__), "..", "tools", "hunter")
        for n in os.listdir(raiz):
            if n.endswith(".py"):
                with open(os.path.join(raiz, n), encoding="utf-8") as f:
                    src = f.read()
                for proibido in ("okx_exec", "engine.executor", "import executor", "privado(", "BYBIT_TRADE",
                                 "OKX_API_KEY", "trade/order", "SECRET", "PASSPHRASE", "TELEGRAM", "engine import alerts",
                                 "/api/v5/account", "/api/v5/trade", "x-access-token"):
                    self.assertNotIn(proibido, src, f"{n}: {proibido}")


@SEM_NUMPY
class Revisao(unittest.TestCase):
    """(17/11, revisao depois da primeira corrida real)"""

    def test_stop_minusculo_nao_entra(self):
        v = [{"t": k * H, "o": 100, "h": 100.01, "l": 99.99, "c": 100, "v": 1} for k in range(5)]
        self.assertIsNone(GE.simular(v, 0, "LONG", 0.01, {"tipo": "fixa", "k": 1, "tp": 2, "hold": 3}))

    def test_risco_agrupado_por_dia(self):
        from tools.hunter import correr as CO
        ops = [(86400 * 5 + k, 1.0) for k in range(400)] + [(86400 * d, -0.5) for d in range(10, 40)]
        r = CO.comparar_risco(ops, max_simultaneas=3)
        self.assertEqual(r["dias_com_operacoes"], 31)               # 400 operacoes num dia = 1 dia, 3 posicoes
        for k, v in r.items():
            if isinstance(v, dict) and "capital_12m_mediana" in v:
                self.assertLess(v["capital_12m_mediana"], 1e6)       # sem o crescimento absurdo de 17/11

    def test_veredicto_exige_dias_distintos(self):
        self.assertGreaterEqual(MO.DIAS_MIN_VALIDACAO, 20)
        self.assertGreaterEqual(MO.DIAS_MIN_TESTE, 10)


@SEM_NUMPY
class PapelIndependencia(unittest.TestCase):
    def setUp(self):
        import json, os, tempfile
        self.d = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.d, "hunter"))
        estr = [{"id": f"s{k}", "familia": "momentum_regime", "parametros": {"k": 1, "x": -1.0}, "tf": "30m",
                 "lado": "LONG", "filtro": None, "stop_ref": "30m",
                 "saida": {"tipo": "fixa", "k": 1.5, "tp": 2.0, "hold": 8}, "veredicto": "EXPLORATORIA"} for k in (1, 2)]
        with open(os.path.join(self.d, "hunter", "papel_estrategias.json"), "w") as f:
            json.dump({"estrategias": estr}, f)
        self.v = {b: velas(300, seed=k) for k, b in enumerate(["A1", "A2", "A3", "A4", "A5", "A6"])}
        self.uni = {b: {"inst": f"{b}-USD_UM_XPERP-1", "classe": "crypto", "vol24h_usd": 1e7} for b in self.v}
        self.now = self.v["A1"][-1]["t"] + H

    def corre(self, falhas=None, now=None):
        from tools.hunter import papel as PA
        return PA.volta(self.d, now=now or self.now, uni=self.uni, velas={"30m": self.v}, funding_fn=lambda i: [],
                        spread_fn=lambda: {}, falhas=falhas)

    def test_uma_posicao_por_moeda_e_acontecimento_e_carteiras_sombra(self):
        st = self.corre()
        f = st["funil_ultima"]
        self.assertEqual(f["sinais_brutos"], 12)                 # 2 estrategias x 6 moedas, todas na mesma vela
        self.assertEqual(f["abertas_novas"], 6)                  # 1 por moeda neste acontecimento
        self.assertEqual(f["acontecimentos_novos"], 1)
        self.assertEqual(f["elegiveis_apos_concentracao"], 3)   # carteira principal: max. 3 por acontecimento
        self.assertEqual(f["rejeitados"]["ja ha exposicao a esta moeda neste acontecimento (outra estrategia)"], 6)
        conta = {}
        for o in st["abertas"]:
            for k in o["carteiras"]:
                conta[k] = conta.get(k, 0) + 1
        self.assertEqual(conta, {"max1": 1, "max3": 3, "max5": 5, "sem_limite": 6})

    def test_sem_duplicados_apos_reinicio(self):
        self.corre()
        st = self.corre()                                        # mesma vela outra vez (reinicio)
        self.assertEqual(st["funil_ultima"]["abertas_novas"], 0)
        self.assertGreater(st["funil_ultima"]["rejeitados"].get(
            "sinal ja tratado (protecao contra duplicados apos reinicio)", 0), 0)

    def test_dados_pouco_fiaveis_bloqueiam_entradas_e_ciclo_fica_registado(self):
        import os
        st = self.corre(falhas=[f"x{k}" for k in 50 * [0]])
        self.assertFalse(st["funil_ultima"]["dados_fiaveis"])
        self.assertEqual(st["funil_ultima"]["abertas_novas"], 0)
        with open(os.path.join(self.d, "hunter", "papel_ciclos.jsonl")) as f:
            self.assertIn("falha tecnica", f.read())
        from tools.hunter import papel as PA
        self.assertIn("PAPEL", PA.resumo_diario(self.d, now=self.now + 86400))


@SEM_NUMPY
class Derivados(unittest.TestCase):
    def test_fotografia_arquivo_e_lacunas(self):
        import gzip, json, os, tempfile
        from tools.hunter import derivados as DV
        uni = {"BTC": {"inst": "BTC-USD_UM_XPERP-1", "ctVal": 0.0001, "ctValCcy": "BTC", "tier": "A"},
               "ZZZ": {"inst": "ZZZ-USD_UM_XPERP-1", "ctVal": 1, "ctValCcy": "ZZZ", "tier": "C"}}

        def req(path, params=None):
            if "tickers" in path:
                return [{"instId": "BTC-USD_UM_XPERP-1", "last": "90000", "vol24h": "10", "bidPx": "89990", "askPx": "90010"}]
            if "open-interest" in path:
                return [{"instId": "BTC-USD_UM_XPERP-1", "oi": "500", "oiUsd": "4500000"}]
            if "funding-rate" in path:
                return [{"fundingRate": "0.0001", "fundingTime": "1800000000000"}] if "BTC" in params["instId"] else None
            if "taker" in path:
                return None                                  # indisponivel: fica registado, nao inventado
            if "books" in path:
                return [{"bids": [["89990", "10"], ["80000", "99"]], "asks": [["90010", "5"]]}]
        linhas, disp = DV.fotografia(uni, 1_800_000_000, request=req)
        self.assertEqual(disp["funding_rate"], 1)
        self.assertEqual(disp["taker_volume"], 0)
        b = linhas["BTC-USD_UM_XPERP-1"]
        self.assertAlmostEqual(b["prof_bid_05pct_usd"], 10 * 0.0001 * 90000, places=2)    # o nivel de 80000 fica fora
        self.assertIsNone(linhas["ZZZ-USD_UM_XPERP-1"]["oi_contratos"])                   # sem leitura = vazio
        d = tempfile.mkdtemp()
        DV.arquivar(d, linhas, disp, 1_800_000_000)
        DV.arquivar(d, linhas, disp, 1_800_000_000 + 3 * 3600)                            # buraco de 3 h
        with gzip.open(os.path.join(d, "hunter", "derivados", "2027-01-15.csv.gz"), "rt") as f:
            rows = f.read().strip().split("\n")
        self.assertEqual(len(rows), 1 + 4)
        with open(os.path.join(d, "hunter", "derivados", "lacunas.json")) as f:
            lac = json.load(f)
        self.assertEqual(lac["lacunas"][0]["minutos"], 180)


@SEM_NUMPY
class Pesquisa(unittest.TestCase):
    def test_corrida_completa_sem_rede_painel_estados_e_risco(self):
        import json, os, tempfile
        from unittest import mock
        from tools.hunter import correr as CO
        dados = {}
        for k, b in enumerate(["BTC", "AAA", "BBB", "CCC", "DDD"]):
            v = velas(2600, seed=k + 20)
            dados[b] = {"info": {"classe": "crypto", "tier": "ABC"[k % 3]}, "30m": v, "funding": []}
        uni = {b: {"inst": f"{b}-USD_UM_XPERP-1", "classe": "crypto"} for b in dados}
        d = tempfile.mkdtemp()
        os.makedirs(os.path.join(d, "hunter"))
        antiga = {"id": "velha1", "familia": "momentum_regime", "parametros": {"k": 1, "x": -1.0}, "tf": "1H",
                  "lado": "LONG", "filtro": None, "stop_ref": "1H", "saida": {"tipo": "trailing", "k": 1.0, "tp": None, "hold": 4}}
        with open(os.path.join(d, "hunter", "papel_estrategias.json"), "w") as f:
            json.dump({"estrategias": [antiga]}, f)
        with mock.patch.object(CO.DD, "recolher", return_value=(dados, uni, {"instrumentos_descobertos": 5})):
            res = CO.main(d, 60, None, 10)
        with open(os.path.join(d, "hunter", "papel_estrategias.json")) as f:
            ids = [e["id"] for e in json.load(f)["estrategias"]]
        with open(os.path.join(d, "hunter", "estados.json")) as f:
            est = json.load(f)
        self.assertIn("velha1", est["estrategias"])                  # as estrategias ja em papel continuam avaliadas
        self.assertIn(est["estrategias"]["velha1"]["estado"],
                      ("EXPLORATORIA", "EM_VALIDACAO", "PAPEL", "REJEITADA"))     # nunca elegivel sem papel/teste
        p = res["painel"]["velha1"]
        self.assertIn("papel prospetivo: >= 30 fechadas em >= 14 dias com media > 0", p["criterios_por_cumprir"])
        self.assertEqual(p["teste_final"], "nao usado")
        for campo in ("n", "dias", "acontecimentos", "r_mediana", "ic95_blocos_acontecimento", "profit_factor",
                      "por_regime", "por_tier", "peso_custos", "operacoes_por_semana", "fracao_meses_positivos",
                      "quota_top3", "stops_com_gap_pct", "horizonte"):
            self.assertIn(campo, p["backtest_treino_validacao"])
        self.assertTrue(os.path.exists(os.path.join(d, "hunter", "familias_registo.json")))
        rc = res["risco_simulado"]["carteira"]
        if rc:
            self.assertLessEqual(rc.get("max1_por_acontecimento", {}).get("operacoes", 0),
                                 rc.get("sem_limite", {}).get("operacoes", 0))
        self.assertLessEqual(len(ids), CO.MAX_PAPEL)

    def test_carteira_uma_por_moeda_e_acontecimento(self):
        from tools.hunter import correr as CO
        ops = {"a": [{"t": 100, "b": "X", "r": 1.0}, {"t": 100, "b": "Y", "r": 1.0}, {"t": 100, "b": "Z", "r": 1.0}],
               "b": [{"t": 100, "b": "X", "r": -1.0}, {"t": 200, "b": "X", "r": 0.5}]}
        self.assertEqual(len(CO.carteira(ops, None)), 4)
        self.assertEqual(len(CO.carteira(ops, 1)), 2)
        self.assertEqual(CO.pior_sequencia([1, -1, -1, 2, -1]), 2)
