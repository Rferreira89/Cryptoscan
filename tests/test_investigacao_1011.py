"""(10/11) Componentes da investigacao: rejeicoes, vigia de decaimento, guarda antes da ordem (e a sua ligacao ao
executor da OKX). Inclui regressao: com a guarda desligada o executor faz exatamente o mesmo que antes."""
import ast
import json
import os
import tempfile
import unittest
from unittest import mock

from engine import decaimento as D
from engine import guarda as G
from tools import rejeicoes as RJ

H = 3600
H4 = 4 * H


class Guarda(unittest.TestCase):
    base = dict(lado="LONG", entrada=1.0, stop=0.95, ativo="X", t_sinal=1000, agora=1000)

    def test_stop_obrigatorio_e_do_lado_certo(self):
        self.assertEqual(G.verificar({}, **dict(self.base, stop=None)), (False, ["sem stop"]))
        self.assertEqual(G.verificar({}, **dict(self.base, stop=1.05))[1], ["stop do lado errado"])
        self.assertEqual(G.verificar({}, **dict(self.base, lado="SHORT", stop=0.95))[1], ["stop do lado errado"])
        self.assertTrue(G.verificar({}, **dict(self.base, lado="SHORT", stop=1.05))[0])
        self.assertTrue(G.verificar({}, **dict(self.base, stop=0.4))[0])                       # limite opcional desligado
        self.assertEqual(G.verificar({"guarda": {"stop_max_pct": 50}}, **dict(self.base, stop=0.4))[1],
                         ["stop a mais de 50% da entrada"])

    def test_duplicado_no_mesmo_ativo(self):
        self.assertIn("ja ha posicao ou ordem neste ativo", G.verificar({}, **self.base, abertas={"X"})[1])

    def test_limites_desligados_por_omissao(self):
        fech = [{"resultado": -5, "t": 990}] * 10
        self.assertTrue(G.verificar({}, **self.base, entradas_24h=500, fechadas=fech)[0])

    def test_limite_diario(self):
        c = {"guarda": {"max_ordens_dia": 3}}
        self.assertTrue(G.verificar(c, **self.base, entradas_24h=2)[0])
        self.assertFalse(G.verificar(c, **self.base, entradas_24h=3)[0])

    def test_pausa_depois_de_perdas_seguidas(self):
        c = {"guarda": {"perdas_seguidas_max": 3, "pausa_h": 24}}
        perdas = [{"resultado": 1, "t": 1}, {"resultado": -1, "t": 2}, {"resultado": -2, "t": 3}, {"resultado": -1, "t": 900}]
        self.assertFalse(G.verificar(c, **self.base, fechadas=perdas)[0])
        self.assertTrue(G.verificar(c, **dict(self.base, agora=900 + 25 * H), fechadas=perdas)[0])   # pausa acabou
        desconhecido = perdas[:-1] + [{"resultado": None, "t": 900}]                                 # nao inventa perdas
        self.assertTrue(G.verificar(c, **self.base, fechadas=desconhecido)[0])

    def test_grupo_correlacionado(self):
        c = {"guarda": {"max_por_grupo": 2}, "grupos": {"X": "alts", "A": "alts", "B": "alts", "BTC": "btc"}}
        self.assertTrue(G.verificar(c, **self.base, abertas={"A", "BTC"})[0])
        self.assertFalse(G.verificar(c, **self.base, abertas={"A", "B"})[0])

    def test_sinal_velho(self):
        c = {"guarda": {"idade_max_s": 60}}
        self.assertFalse(G.verificar(c, **dict(self.base, agora=1100))[0])

    def test_grupos_por_correlacao(self):
        import random
        rs = random.Random(1)
        base = [rs.gauss(0, 1) for _ in range(200)]
        r = {"A": base, "B": [x + rs.gauss(0, 0.2) for x in base], "C": [rs.gauss(0, 1) for _ in range(200)], "D": [0.1] * 10}
        g = G.grupos_por_correlacao(r)
        self.assertEqual(g["A"], g["B"]); self.assertNotEqual(g["A"], g["C"]); self.assertNotIn("D", g)


class GuardaIsolada(unittest.TestCase):
    """(10/11, ordem do Rui, grupo B) A guarda entra como componente isolado: nenhum executor a importa."""
    def test_nenhum_executor_usa_a_guarda(self):
        import glob
        execs = [f for f in glob.glob(os.path.join(os.path.dirname(__file__), "..", "tools", "*.py")) +
                 glob.glob(os.path.join(os.path.dirname(__file__), "..", "engine", "*.py"))
                 if os.path.basename(f) in ("okx_exec.py", "okx_short.py", "executor.py", "execucao.py", "auto.py", "nucleo.py")]
        self.assertTrue(execs)
        for f in execs:
            src = open(f).read()
            self.assertNotIn("from engine import guarda", src, f); self.assertNotIn("import guarda", src, f)
            for m in ("exposicao", "perda_diaria", "rejeicoes", "decaimento"):     # componentes de leitura
                self.assertNotIn(f"import {m}", src, f)


class GuardaDesligadaNaoMudaNada(unittest.TestCase):
    """Ponto 4: com os limites desligados, a guarda aceita TODAS as ordens que o plano do executor da OKX produz
    (o stop do plano fica sempre abaixo da entrada e um ativo com posicao ja e saltado antes)."""
    def test_qualquer_plano_do_executor_passa(self):
        import random, sys
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
        import okx_exec
        rs = random.Random(5)
        n = 0
        for _ in range(3000):
            lim = 10 ** rs.uniform(-6, 5); atr = lim * rs.uniform(0.001, 0.45)
            info = {"inst": "X", "ctVal": 10 ** rs.uniform(-3, 2), "minSz": 1.0, "lotSz": rs.choice([0.01, 1.0]),
                    "tick": lim / 10 ** rs.randint(2, 6), "ctType": "linear", "lever": 20}
            p = okx_exec.plano({"lim": lim, "atr": atr}, info, 20.0, dict(okx_exec.CFG_PADRAO))
            if not p:
                continue
            n += 1
            pode, porque = G.verificar(dict(okx_exec.CFG_PADRAO), lado="LONG", entrada=p["lim"], stop=p["stop"],
                                       ativo="X", t_sinal=0, agora=0, entradas_24h=99, fechadas=[{"resultado": -1, "t": 0}] * 9)
            self.assertTrue(pode, (p, porque))
        self.assertGreater(n, 100)


class Decaimento(unittest.TestCase):
    """Ponto 6 da ordem de 10/11: dependencia do mesmo dia, tamanho da amostra, variabilidade vs degradacao,
    referencia certa, nada de conclusoes prematuras."""
    dias = staticmethod(lambda n: list(range(n)))

    def test_evidencia_insuficiente_e_explicita(self):
        e = D.estado([1, -1, 1])
        self.assertEqual(e["estado"], "evidencia_insuficiente"); self.assertFalse(e["definitivo"])

    def test_mesmo_dia_nao_e_independente(self):
        e = D.estado([-1.1] * 19, 0.1, grupos=[0] * 19)
        self.assertEqual(e["estado"], "evidencia_insuficiente"); self.assertEqual(e["dias_independentes"], 1)

    def test_morta_preliminar_com_pouca_amostra(self):
        e = D.estado([-1.0] * 9 + [0.5] * 3, 0.1, grupos=self.dias(12))
        self.assertEqual(e["estado"], "morta"); self.assertFalse(e["definitivo"])
        self.assertTrue(any("preliminar" in p for p in e["porques"]))

    def test_morta_definitiva_com_amostra_grande(self):
        e = D.estado([-1.0, -1.0, 0.5] * 12, 0.1, grupos=self.dias(36))
        self.assertEqual(e["estado"], "morta"); self.assertTrue(e["definitivo"])

    def test_variabilidade_normal_e_inconclusiva(self):
        e = D.estado([2.0, -1.0, -1.0, 1.0] * 5, 0.1, grupos=self.dias(20))
        self.assertEqual(e["estado"], "inconclusiva")

    def test_abaixo_da_referencia_sem_estar_morta(self):
        R = [2.0, -1.0, -1.0] * 10 + [0.1] * 10
        self.assertEqual(D.estado(R, 0.6, grupos=self.dias(40))["estado"], "abaixo_da_referencia")

    def test_positiva_so_com_intervalo_acima_de_zero(self):
        self.assertEqual(D.estado([2.0, -1.0, 1.0] * 12, 0.1, grupos=self.dias(36))["estado"], "positiva")

    def test_aviso_de_recencia_nao_muda_o_estado(self):
        R = [2.0, -1.0] * 15 + [-0.5] * 10
        e = D.estado(R, 0.5, grupos=self.dias(40))
        self.assertTrue(e["avisos"]); self.assertIn(e["estado"], ("inconclusiva", "abaixo_da_referencia"))

    def test_h40_usa_a_referencia_da_variante(self):
        from engine import registo as RG
        ops = [RG.op("H40", "papel", "okx", "A", "f", str(i), {"tipo": "isolado"}, R=-1.0, t_entrada=i * 86400)
               for i in range(12)]
        ops += [RG.op("H40", "papel", "okx", "B", "f", f"m{i}", {"tipo": "mercado"}, R=1.0, t_entrada=i * 86400)
                for i in range(3)]
        out = {(x["estrategia"], x["classe"]): x for x in D.vigiar(ops)}
        self.assertEqual(out[("H40 isolado", "papel")]["referencia_R"], -0.126)
        self.assertEqual(out[("H40 mercado", "papel")]["estado"], "evidencia_insuficiente")

    def test_real_e_papel_separados(self):
        from engine import registo as RG
        ops = [RG.op("H46", "papel", "okx", "A", "f", str(i), {}, R=-1.0, t_entrada=i * 86400) for i in range(12)]
        ops += [RG.op("H46", "real", "okx", "A", "g", str(i), {}, R=1.0, t_entrada=i * 86400) for i in range(3)]
        out = {(x["estrategia"], x["classe"]): x for x in D.vigiar(ops)}
        self.assertEqual(out[("H46", "papel")]["estado"], "morta")
        self.assertEqual(out[("H46", "executada")]["estado"], "evidencia_insuficiente")
        self.assertEqual(out[("H46", "papel")]["referencia_R"], out[("H46", "executada")]["referencia_R"])


class Rejeicoes(unittest.TestCase):
    def pasta(self):
        d = tempfile.mkdtemp()
        okx = {"fechadas": [{"asset": "A", "t_sig": 100, "r": -1.0}, {"asset": "B", "t_sig": 200, "r": 2.0}],
               "real": {"avisados": ["p:A:100", "x:B:200", "i:C:300", "HUMA:5", "p:A:100"]}}
        json.dump(okx, open(os.path.join(d, "okx.json"), "w"))
        st = {"papel_panico": {"fechadas": [{"asset": "Z", "t_sig": 86400 * i, "r": -1.0} for i in range(12)],
                               "real": {"k": {"asset": "Q", "t_sig": 5, "estado": "recusada"}}}}
        json.dump(st, open(os.path.join(d, "state.json"), "w"))
        tfs = {"conta": {"ignoradas": [{"moeda": "E", "t": 7, "motivo": "abaixo_minimo"}]}, "sinais": {"fechadas": []}}
        json.dump(tfs, open(os.path.join(d, "okx_tfshort.json"), "w"))
        json.dump({"versao": 1, "soma": "x", "estado": {"nao_executaveis": [{"moeda": "F", "dia": 9, "motivo": "abaixo_minimo_do_contrato"}]}},
                  open(os.path.join(d, "kronos_sombra.json"), "w"))
        return d

    def test_junta_e_classifica_sem_duplicar(self):
        rejs, res = RJ.tudo(self.pasta())
        okx = [r for r in rejs if r["fonte"] == "okx" and r["estrategia"] == "H40"]
        self.assertEqual(len(okx), 3)                                    # duplicado e formato antigo ignorados
        porm = {r["motivo"]: r for r in okx}
        self.assertEqual(porm["H40 suspensa do dinheiro real (decisao)"]["R"], -1.0)
        self.assertEqual(porm["sem X-Perp negociavel na conta"]["classe"], "operacional")
        self.assertIsNone(porm["H40 panico isolado (so_mercado)"]["R"])    # sem par em papel: desconhecido
        h45 = [r for r in res if r["estrategia"] == "H45" and r["com_resultado"]][0]
        self.assertEqual(h45["veredito"], "bloqueio justificado")
        self.assertTrue(any(r["estrategia"] == "Kronos sombra" for r in rejs))


class Funil(unittest.TestCase):
    def test_funil_conta_cada_sinal_uma_vez_e_conflitos(self):
        d = Rejeicoes().pasta()
        okx = json.load(open(os.path.join(d, "okx.json")))
        okx["real"]["avisados"] += ["i:A:100"]                     # segundo motivo para o mesmo sinal
        okx["real"]["hist"] = [{"asset": "R", "t_sig": 50, "estado": "fechada"}]
        okx["abertas"] = {"T": {"t_sig": 400}}
        json.dump(okx, open(os.path.join(d, "okx.json"), "w"))
        tfs = json.load(open(os.path.join(d, "okx_tfshort.json")))
        tfs["sinais"]["abertas"] = {"T": {"t": 300}}
        tfs["conta"]["ignoradas"] *= 2                             # o mesmo sinal ignorado em duas voltas
        json.dump(tfs, open(os.path.join(d, "okx_tfshort.json"), "w"))
        f = RJ.funil(d)
        self.assertEqual(f["H40"]["rejeitados"], 3)                # A (2 motivos), B, C
        self.assertEqual(f["H40"]["em_real"], 1)
        self.assertEqual(f["TF-SHORT"]["rejeitados"], 1)
        cf = RJ.conflitos(d)
        self.assertEqual([(c["ativo"], c["long"], c["short"]) for c in cf], [("T", "H40", "TF-SHORT")])
        txt = RJ.texto_completo(d)
        self.assertIn("Filtros que mais cortam", txt); self.assertIn("Conflitos", txt)


class TFShortSinaisIndependentes(unittest.TestCase):
    def test_mesmo_sinal_em_varias_voltas_e_na_sombra_conta_uma_vez(self):
        d = tempfile.mkdtemp()
        tfs = {"sinais": {"abertas": {"ADA": {"t": 1000, "entrada": 1.0, "stop": 1.2}}, "fechadas": []},
               "conta": {"ignoradas": [{"moeda": "ADA", "t": 1000 + 86400 * i, "motivo": "fora_do_universo_validado"}
                                       for i in range(5)]}}
        json.dump(tfs, open(os.path.join(d, "okx_tfshort.json"), "w"))
        json.dump({"versao": 1, "soma": "x", "estado": {"nao_executaveis": [
            {"moeda": "ADA", "sinal": "ADA-1000", "t": 5000, "motivo": "fora_do_universo_validado"}]}},
            open(os.path.join(d, "okx_tfshort_sombra.json"), "w"))
        json.dump({"universe": [{"asset": "ADA", "price": 0.9}]}, open(os.path.join(d, "scan.json"), "w"))
        rejs, res = RJ.tudo(d)
        ada = [r for r in rejs if r["ativo"] == "ADA"]
        self.assertEqual(len(ada), 1)
        self.assertAlmostEqual(ada[0]["R_prov"], 0.5 - RJ.CUSTO_TFS / 0.2, places=6)   # short a ganhar 0,5R menos custos
        self.assertIn("provisorio", res[0]["veredito"])


class SemOrdens(unittest.TestCase):
    def test_componentes_de_investigacao_nao_enviam_ordens(self):
        for mod in (D, G, RJ):
            src = open(mod.__file__).read()
            nomes = {a.name for n in ast.walk(ast.parse(src)) if isinstance(n, (ast.Import, ast.ImportFrom)) for a in n.names} | \
                    {n.module for n in ast.walk(ast.parse(src)) if isinstance(n, ast.ImportFrom) and n.module}
            self.assertFalse(nomes & {"urllib.request", "requests", "hmac", "okx_exec", "tools.okx_exec", "engine.executor",
                                      "executor", "socket", "http.client"}, mod.__name__)
            for proibido in ("POST", "/order", "API_KEY", "SECRET"):
                self.assertNotIn(proibido, src, mod.__name__)


if __name__ == "__main__":
    unittest.main()
