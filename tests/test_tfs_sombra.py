"""(06/11) TF-SHORT em sombra: so leitura publica, minimos reais, livro de ordens, stops, regra de saida, custos,
oportunidades nao executaveis com 20 USD e estado fail-closed."""
import ast
import json
import os
import tempfile
import unittest

from tools import tfs_sombra as T

AGORA = 1794000000
H = 3600
INFO = {"inst": "DOGE-USD_UM_XPERP-1", "ctVal": 10.0, "minSz": 1.0, "lotSz": 1.0, "tickSz": 0.0001, "maxLever": 20}


class Pub:
    def __init__(self, infos=None, livro=None, velas=None, fund=None):
        self.infos = {"DOGE": INFO} if infos is None else infos
        self._livro = livro if livro is not None else {"bids": [(0.2000, 5), (0.1995, 100)], "asks": [(0.2002, 5), (0.2006, 100)]}
        self._velas = velas or []
        self._fund = fund if fund is not None else []
        self.pedidos = []

    def instrumentos(self):
        self.pedidos.append("instrumentos"); return self.infos

    def livro(self, inst):
        self.pedidos.append("livro"); return self._livro

    def velas_1h(self, inst, desde):
        self.pedidos.append("velas"); return None if self._velas is None else [v for v in self._velas if v["t"] >= desde]

    def financiamento(self, inst):
        self.pedidos.append("fund"); return self._fund


def tfs(moedas=("DOGE",), w=0.2, validado=True, stop=0.22):
    return {"sinais": {"abertas": {m: {"t": AGORA - 600, "entrada": 0.2, "stop": stop, "w": w, "validado": validado}
                                   for m in moedas}, "fechadas": []}}


class SoLeitura(unittest.TestCase):
    def test_modulo_sem_escrita_nem_chaves_nem_executor_real(self):
        src = open(T.__file__).read()
        tree = ast.parse(src)
        imports = {a.name for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))
                   for a in n.names} | {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
        self.assertFalse(imports & {"okx_short", "okx_exec", "okx_sombra", "requests", "hmac"})
        for proibido in ("POST", "API_KEY", "OKX_KEY", "SECRET", "PASSPHRASE", "/trade/", "set-leverage", "data="):
            self.assertNotIn(proibido, src)
        self.assertIn('method="GET"', src)


class Entradas(unittest.TestCase):
    def test_entrada_ao_preco_do_livro_com_custos_medidos(self):
        est = T.novo(); pub = Pub()
        r = T.volta(tfs(), est, True, "ok", pub, AGORA)
        self.assertEqual(r["entradas"], 1)
        op = est["abertas"]["DOGE"]
        # 20 x 0.2 = 4 USD -> 2 contratos de 10 DOGE a 0.2000 (livro chega)
        self.assertEqual(op["contratos"], 2); self.assertAlmostEqual(op["px_fill"], 0.2)
        self.assertGreater(op["spread_pct"], 0); self.assertEqual(op["deslize_pct"], 0)
        self.assertIsNone(op["objetivo"]); self.assertGreaterEqual(op["stop"], 0.22)

    def test_deslize_quando_o_livro_e_fino(self):
        est = T.novo()
        pub = Pub(livro={"bids": [(0.2000, 1), (0.1990, 100)], "asks": [(0.2002, 5)]})
        T.volta(tfs(), est, True, "ok", pub, AGORA)
        self.assertGreater(est["abertas"]["DOGE"]["deslize_pct"], 0)

    def test_abaixo_do_minimo_regista_capital_necessario(self):
        info = dict(INFO, ctVal=1000.0)                   # 1 contrato = 200 USD
        est = T.novo()
        T.volta(tfs(), est, True, "ok", Pub(infos={"DOGE": info}), AGORA)
        self.assertEqual(est["abertas"], {})
        x = est["nao_executaveis"][0]
        self.assertEqual(x["motivo"], "abaixo_minimo_do_contrato"); self.assertAlmostEqual(x["capital_minimo_usd"], 1000.0)

    def test_fora_do_universo_e_sem_instrumento(self):
        est = T.novo()
        t = tfs(("DOGE", "XYZ")); t["sinais"]["abertas"]["DOGE"]["validado"] = False
        T.volta(t, est, True, "ok", Pub(), AGORA)
        self.assertEqual(sorted(x["motivo"] for x in est["nao_executaveis"]),
                         ["fora_do_universo_validado", "sem_instrumento_okx_eea"])

    def test_tetos_de_posicoes_e_exposicao(self):
        est = T.novo()
        T.volta(tfs(("A", "B", "C"), w=0.2), est, True, "ok", Pub(infos={m: INFO for m in "ABC"}), AGORA)
        self.assertEqual(len(est["abertas"]), 2)           # 0.2 + 0.2 = 0.4; a terceira passaria 0.5
        self.assertEqual(est["nao_executaveis"][0]["motivo"], "exposicao_bruta")

    def test_sinal_visto_uma_so_vez(self):
        est = T.novo(); pub = Pub(infos={"DOGE": dict(INFO, ctVal=1000.0)})
        T.volta(tfs(), est, True, "ok", pub, AGORA); T.volta(tfs(), est, True, "ok", pub, AGORA + 86400)
        self.assertEqual(len(est["nao_executaveis"]), 1)

    def test_sinal_de_outro_dia_nao_entra_agora(self):
        est = T.novo(); t = tfs(); t["sinais"]["abertas"]["DOGE"]["t"] = AGORA - 3 * 86400
        T.volta(t, est, True, "ok", Pub(), AGORA)
        self.assertEqual(est["abertas"], {}); self.assertEqual(est["nao_executaveis"], []); self.assertEqual(est["antigos"], 1)

    def test_sem_livro_nao_entra(self):
        est = T.novo()
        T.volta(tfs(), est, True, "ok", Pub(livro={"bids": [], "asks": []}), AGORA)
        self.assertEqual(est["abertas"], {}); self.assertEqual(est["nao_executaveis"][0]["motivo"], "sem_livro_de_ordens")


class FalhasDeLeitura(unittest.TestCase):
    def test_instrumentos_indisponiveis_nao_consomem_sinais(self):
        est = T.novo()
        p = Pub(); p.infos = None
        r = T.volta(tfs(), est, True, "ok", p, AGORA)
        self.assertEqual(est["nao_executaveis"], []); self.assertEqual(est["vistos"], [])
        self.assertTrue(r["entradas_bloqueadas"])
        T.volta(tfs(), est, True, "ok", Pub(), AGORA + 60)
        self.assertIn("DOGE", est["abertas"])

    def test_livro_indisponivel_tenta_na_proxima_volta(self):
        est = T.novo(); p = Pub(); p._livro = None
        p.livro = lambda inst: None
        T.volta(tfs(), est, True, "ok", p, AGORA)
        self.assertEqual(est["nao_executaveis"], [])
        T.volta(tfs(), est, True, "ok", Pub(), AGORA + 60)
        self.assertIn("DOGE", est["abertas"])


class Saidas(unittest.TestCase):
    def abrir(self):
        est = T.novo(); T.volta(tfs(), est, True, "ok", Pub(), AGORA); return est

    def test_stop_tocado_nas_velas_do_xperp(self):
        est = self.abrir()
        velas = [{"t": AGORA + H, "o": 0.205, "h": 0.21, "l": 0.2, "c": 0.208},
                 {"t": AGORA + 2 * H, "o": 0.215, "h": 0.23, "l": 0.21, "c": 0.225}]
        T.volta(tfs(), est, True, "ok", Pub(velas=velas, fund=[(AGORA + H, 0.0001)]), AGORA + 86400)
        f = est["fechadas"][0]
        self.assertEqual(f["motivo"], "stop"); self.assertAlmostEqual(f["saida"], 0.22 * 1.001, places=8)
        self.assertLess(f["R"], -1.0)                       # perde um pouco mais do que 1R (custos e deslize)
        self.assertGreater(f["custos_usd"], 0); self.assertGreater(f["fund_usd"], 0)

    def test_stop_com_abertura_acima_sai_a_abertura(self):
        est = self.abrir()
        velas = [{"t": AGORA + H, "o": 0.24, "h": 0.25, "l": 0.235, "c": 0.24}]
        T.volta(tfs(), est, True, "ok", Pub(velas=velas), AGORA + 86400)
        self.assertAlmostEqual(est["fechadas"][0]["saida"], 0.24 * 1.001, places=8)

    def test_regra_de_saida_ao_preco_de_compra_do_livro(self):
        est = self.abrir()
        velas = [{"t": AGORA + H, "o": 0.19, "h": 0.195, "l": 0.18, "c": 0.185}]
        sem = {"sinais": {"abertas": {}, "fechadas": []}}
        T.volta(sem, est, True, "ok", Pub(velas=velas), AGORA + 86400)
        f = est["fechadas"][0]
        self.assertEqual(f["motivo"], "regra"); self.assertAlmostEqual(f["saida"], 0.2002)
        self.assertNotEqual(est["capital"], 20.0)

    def test_falha_de_velas_mantem_aberta(self):
        est = self.abrir()
        p = Pub(); p._velas = None
        r = T.volta(tfs(), est, True, "ok", p, AGORA + 86400)
        self.assertIn("DOGE", est["abertas"]); self.assertTrue(r["falhas"])


class Estado(unittest.TestCase):
    def test_adulterado_bloqueia_entradas_mas_acompanha(self):
        d = tempfile.mkdtemp(); p = os.path.join(d, "s.json")
        est = T.novo(); T.guardar(p, est)
        corpo = json.load(open(p)); corpo["estado"]["capital"] = 999; json.dump(corpo, open(p, "w"))
        est2, ok, motivo = T.carregar(p)
        self.assertFalse(ok); self.assertIn("adulterado", motivo)
        r = T.volta(tfs(), est2, ok, motivo, Pub(), AGORA)
        self.assertEqual(r["entradas"], 0); self.assertEqual(r["entradas_bloqueadas"], motivo)

    def test_inexistente_so_com_inicializacao_autorizada(self):
        p = os.path.join(tempfile.mkdtemp(), "nao.json")
        self.assertFalse(T.carregar(p)[1]); self.assertTrue(T.carregar(p, iniciar=True)[1])

    def test_ida_e_volta(self):
        p = os.path.join(tempfile.mkdtemp(), "s.json")
        est = T.novo(); T.volta(tfs(), est, True, "ok", Pub(), AGORA); T.guardar(p, est)
        est2, ok, _ = T.carregar(p)
        self.assertTrue(ok); self.assertEqual(est2, json.loads(json.dumps(est)))


class NoRegisto(unittest.TestCase):
    def test_entra_no_registo_como_sombra(self):
        from engine import registo as G
        est = T.novo(); T.volta(tfs(), est, True, "ok", Pub(), AGORA)
        velas = [{"t": AGORA + H, "o": 0.215, "h": 0.23, "l": 0.21, "c": 0.225}]
        T.volta(tfs(), est, True, "ok", Pub(velas=velas), AGORA + 86400)
        ops = G.do_tfs_sombra(est)
        self.assertEqual(len(ops), 1); self.assertEqual(ops[0]["classe"], "sombra"); self.assertEqual(ops[0]["origem"], "sombra")


if __name__ == "__main__":
    unittest.main()


class NaoLava(unittest.TestCase):
    def test_estado_adulterado_nao_e_regravado(self):
        import contextlib, io
        d = tempfile.mkdtemp(); p = os.path.join(d, "s.json"); t = os.path.join(d, "t.json")
        json.dump(tfs(), open(t, "w"))
        T.guardar(p, T.novo()); c = json.load(open(p)); c["estado"]["capital"] = 99; json.dump(c, open(p, "w"))
        orig = T.Publico; T.Publico = Pub
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                T.main([t, p, "--gravar"])
        finally:
            T.Publico = orig
        self.assertFalse(T.carregar(p)[1])


class FinanciamentoEmFalta(unittest.TestCase):
    def test_stop_sem_financiamento_fica_assinalado(self):
        est = T.novo(); T.volta(tfs(), est, True, "ok", Pub(), AGORA)
        p = Pub(velas=[{"t": AGORA + 3600, "o": 0.215, "h": 0.23, "l": 0.21, "c": 0.225}])
        p.financiamento = lambda inst: None
        T.volta(tfs(), est, True, "ok", p, AGORA + 86400)
        self.assertEqual(est["fechadas"][0]["custos_incompletos"], "financiamento indisponivel")
