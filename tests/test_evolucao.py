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
        self.assertEqual(G.verificar({}, **dict(self.base, stop=0.4))[1], ["stop a mais de 50% da entrada"])

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


class GuardaNoExecutor(unittest.TestCase):
    def setUp(self):
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
        import okx_exec
        self.E = okx_exec
        p = mock.patch.dict(os.environ, {"DATA_KEY": "teste"}); p.start(); self.addCleanup(p.stop)
        q = mock.patch.object(okx_exec, "estado_pico", lambda R, c, eq: ("ok", eq)); q.start(); self.addCleanup(q.stop)

    def corre(self, cfg_extra, hist=(), now=2_000_000_000):
        posts, msgs = [], []

        def privado(metodo, path, corpo=None):
            if metodo == "POST":
                posts.append((path, corpo)); return {"code": "0", "data": [{"ordId": "1", "sCode": "0"}]}
            if "balance" in path:
                return {"code": "0", "data": [{"totalEq": "20"}]}
            return {"code": "0", "data": []}
        st = {"real": {"ops": {}, "hist": list(hist)}}
        info = {"inst": "M-USD_UM_XPERP-1", "ctVal": 10.0, "minSz": 1.0, "lotSz": 1.0, "tick": 0.00001, "ctType": "linear", "lever": 20}
        with mock.patch.object(self.E, "_chaves", return_value=("k", "s", "p")), mock.patch.object(self.E, "privado", privado), \
                mock.patch.object(self.E, "cfg", return_value=dict(self.E.CFG_PADRAO, real=True, panico_real=True, **cfg_extra)), \
                mock.patch.object(self.E, "xperps", return_value={"M": info}):
            self.E.correr(st, [("M", {"t_sig": now - H4, "lim": 0.0236, "atr": 0.001, "tipo": "mercado"})], now, msgs)
        return [c for p_, c in posts if p_ == "/api/v5/trade/order"], msgs

    def test_regressao_guarda_desligada_entra_como_antes(self):
        ordens, _ = self.corre({})
        self.assertEqual(len(ordens), 1)

    def test_pausa_por_perdas_bloqueia_a_entrada(self):
        now = 2_000_000_000
        hist = [{"asset": a, "estado": "fechada", "ret_pct": -5.0, "fechado": now - 3600 * i} for i, a in enumerate("ABC", 1)]
        ordens, msgs = self.corre({"guarda": {"perdas_seguidas_max": 3}}, hist=hist, now=now)
        self.assertEqual(ordens, []); self.assertTrue(any("perdas seguidas" in m for m in msgs))

    def test_limite_diario_conta_ordens_das_ultimas_24h(self):
        now = 2_000_000_000
        hist = [{"asset": a, "estado": "cancelada", "ordId": "9", "criado": now - 3600} for a in "AB"]
        ordens, msgs = self.corre({"guarda": {"max_ordens_dia": 2}}, hist=hist, now=now)
        self.assertEqual(ordens, []); self.assertTrue(any("2 entradas em 24 h" in m for m in msgs))


class Decaimento(unittest.TestCase):
    def test_sem_dados_abaixo_de_10(self):
        self.assertEqual(D.estado([1, -1, 1])["estado"], "sem_dados")

    def test_morta_quando_perde_com_confianca(self):
        self.assertEqual(D.estado([-1.0] * 9 + [0.5] * 3, 0.1)["estado"], "morta")

    def test_em_decaimento_abaixo_da_referencia(self):
        R = [2.0, -1.0, -1.0] * 10 + [0.1] * 10
        e = D.estado(R, 0.6)
        self.assertEqual(e["estado"], "em_decaimento", e)

    def test_viva(self):
        R = [2.0, -1.0, 1.0, -1.0, 2.0] * 6
        self.assertEqual(D.estado(R, 0.1)["estado"], "viva")

    def test_a_vigiar_quando_as_ultimas_10_caem(self):
        R = [2.0, -1.0] * 15 + [-0.5] * 10
        e = D.estado(R, 0.5)
        self.assertIn(e["estado"], ("a_vigiar", "em_decaimento"))

    def test_operacoes_do_mesmo_dia_nao_sao_independentes(self):
        e = D.estado([-1.1] * 19, 0.1, grupos=[0] * 19)
        self.assertEqual(e["estado"], "sem_dados"); self.assertEqual(e["dias_independentes"], 1)
        e2 = D.estado([-1.0, 0.2] * 10, 0.1, grupos=list(range(20)))
        self.assertNotEqual(e2["estado"], "sem_dados")

    def test_vigiar_separa_classes(self):
        from engine import registo as RG
        ops = [RG.op("H40", "papel", "okx", "A", "f", str(i), {}, R=-1.0, t_entrada=i * 86400) for i in range(12)]
        ops += [RG.op("H40", "real", "okx", "A", "g", str(i), {}, R=1.0, t_entrada=i) for i in range(3)]
        out = {(x["estrategia"], x["classe"]): x for x in D.vigiar(ops)}
        self.assertEqual(out[("H40", "papel")]["estado"], "morta"); self.assertEqual(out[("H40", "executada")]["estado"], "sem_dados")


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
