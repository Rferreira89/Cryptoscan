"""(07/11) Agente Kronos em sombra (hipotese K1): regra registada, tamanho pelo risco, minimos, stops, saida a 24 h,
controlo ingenuo, estado fail-closed e so leitura publica. Sem torch: o previsor e falso."""
import ast
import json
import os
import tempfile
import unittest

from tools import kronos_sombra as K

DIA = 1794009600                    # 00:00 UTC
AGORA = DIA + 31 * 60
H = 3600
INFO = {"inst": "SOL-USD_UM_XPERP-1", "ctVal": 0.1, "minSz": 1.0, "lotSz": 1.0, "tickSz": 0.01, "maxLever": 20}


def velas(px=100.0, n=K.CONTEXTO, fim=DIA, amp=0.04, tend=0.0):
    out = []
    for i in range(n):
        t = fim - (n - i) * H
        c = px * (1 + tend * (i - n) / n)
        out.append({"t": t, "o": c, "h": c * (1 + amp / 4), "l": c * (1 - amp / 4), "c": c, "v": 10.0})
    return out


class Prev:
    def __init__(self, fator):
        self.fator = fator

    def trajetorias(self, series, **kw):
        return {m: [v[-1]["c"] * f for f in (self.fator(m) if callable(self.fator) else self.fator)] for m, v in series.items()}


class Pub:
    def __init__(self, infos=None, livro=None, v1h=None, fund=None, perp=None):
        self.infos = {"SOL": INFO} if infos is None else infos
        self._livro = livro if livro is not None else {"bids": [(99.9, 50)], "asks": [(100.1, 50)]}
        self._v1h = v1h or []
        self._fund = fund or []
        self._perp = perp

    def instrumentos(self):
        return self.infos

    def livro(self, inst):
        return self._livro

    def velas_1h(self, inst, desde):
        return [v for v in self._v1h if v["t"] >= desde]

    def financiamento(self, inst):
        return self._fund

    def velas_perp(self, m, n=K.CONTEXTO):
        if self._perp is not None:
            return self._perp.get(m)
        return velas() if m == "SOL" else None


SOBE = [1.03] * 14 + [0.99] * 2        # mediana +3%, acordo 14/16
INDECISO = [1.03] * 10 + [0.98] * 6    # acordo 10/16 < 0,75


class Regra(unittest.TestCase):
    def test_limiares_registados(self):
        self.assertEqual(K.sinal(100, [103] * 16)[0], "LONG")
        self.assertEqual(K.sinal(100, [97] * 16)[0], "SHORT")
        self.assertIsNone(K.sinal(100, [100.5] * 16)[0])                    # abaixo de 1%
        self.assertIsNone(K.sinal(100, [100 * f for f in INDECISO])[0])    # sem acordo
        self.assertEqual(K.sinal(100, [100 * f for f in SOBE])[0], "LONG")

    def test_registo_fixo(self):
        self.assertEqual(K.REGISTO, "2026-11-07"); self.assertEqual(len(K.UNIVERSO), 20)
        self.assertEqual((K.LIMIAR, K.ACORDO, K.STOP_X, K.RISCO, K.HORIZONTE, K.TRAJ), (0.01, 0.75, 1.5, 0.01, 24, 16))

    def test_amplitude_diaria(self):
        self.assertAlmostEqual(K.amplitude_diaria(velas(amp=0.04)), 0.02, places=6)

    def test_tamanho_pelo_risco_e_tetos(self):
        n, m = K.contratos(20, 0.03, 100, INFO, 0)          # 0,2 de risco / 3% = 6,67 USD -> 0,667 contratos < 1
        self.assertEqual((n, m), (0, "abaixo_minimo_do_contrato"))
        n, m = K.contratos(20, 0.01, 100, dict(INFO, ctVal=0.01), 0)   # 20 USD (1x) -> 20 contratos de 1 USD
        self.assertEqual((n, m), (20, None))
        n, m = K.contratos(20, 0.001, 100, dict(INFO, ctVal=0.01), 0)  # pedia 200 USD -> teto 3x = 60
        self.assertEqual(n, 60)
        self.assertEqual(K.contratos(20, 0.01, 100, INFO, 60)[1], "alavancagem_total")
        self.assertAlmostEqual(K.capital_minimo(0.03, 100, INFO), 30.0)


class Volta(unittest.TestCase):
    def test_entrada_long_com_controlo(self):
        est = K.novo()
        r = K.volta(est, True, "ok", Pub(infos={"SOL": dict(INFO, ctVal=0.01)}), Prev(SOBE), AGORA)
        self.assertEqual(r["entradas"], 1); op = est["abertas"]["SOL"]
        self.assertEqual(op["lado"], "LONG"); self.assertAlmostEqual(op["px_fill"], 100.1)
        self.assertLess(op["stop"], op["px_fill"]); self.assertIsNone(op["objetivo"])
        self.assertEqual(op["controlo"]["lado"], "SHORT")    # momento das ultimas 24 h = 0 -> controlo ingenuo SHORT

    def test_previsoes_de_todas_as_moedas_registadas(self):
        perp = {m: velas() for m in K.UNIVERSO}
        est = K.novo()
        K.volta(est, True, "ok", Pub(perp=perp), Prev([1.0] * 16), AGORA)
        self.assertEqual(len(est["previsoes"]), 20); self.assertEqual(est["abertas"], {})

    def test_uma_volta_por_dia(self):
        est = K.novo(); pub = Pub(infos={"SOL": dict(INFO, ctVal=0.01)})
        K.volta(est, True, "ok", pub, Prev(SOBE), AGORA)
        r = K.volta(est, True, "ok", pub, Prev(SOBE), AGORA + 600)
        self.assertEqual(r["entradas_bloqueadas"], "previsoes de hoje ja feitas"); self.assertEqual(len(est["previsoes"]), 1)

    def test_abaixo_do_minimo_registado(self):
        est = K.novo()
        K.volta(est, True, "ok", Pub(), Prev(SOBE), AGORA)
        self.assertEqual(est["abertas"], {})
        x = est["nao_executaveis"][0]
        self.assertEqual(x["motivo"], "abaixo_minimo_do_contrato"); self.assertGreater(x["capital_minimo_usd"], 20)

    def test_maximo_cinco_por_dia(self):
        perp = {m: velas() for m in K.UNIVERSO}
        infos = {m: dict(INFO, ctVal=0.001) for m in K.UNIVERSO}
        est = K.novo()
        r = K.volta(est, True, "ok", Pub(infos=infos, perp=perp), Prev(SOBE), AGORA)
        self.assertEqual(r["sinais"], 20); self.assertLessEqual(r["entradas"] + r["nao_executaveis"], 5)

    def abrir(self, fator=SOBE):
        est = K.novo()
        K.volta(est, True, "ok", Pub(infos={"SOL": dict(INFO, ctVal=0.01)}), Prev(fator), AGORA)
        return est

    def test_stop_do_agente_e_controlo_independentes(self):
        est = self.abrir()
        op = est["abertas"]["SOL"]; op["controlo"] = {"lado": "SHORT", "stop": 105.0, "saida": None, "motivo": None}
        queda = [{"t": AGORA + H, "o": 99, "h": 99.5, "l": 90, "c": 91}]
        pub = Pub(infos={"SOL": dict(INFO, ctVal=0.01)}, v1h=queda, livro={"bids": [(92.0, 99)], "asks": [(92.2, 99)]})
        K.volta(est, True, "ok", pub, Prev([1.0] * 16), AGORA + 2 * H)
        self.assertIn("SOL", est["abertas"])                     # agente parado no stop; controlo continua ate 24 h
        self.assertEqual(est["abertas"]["SOL"]["motivo"], "stop")
        K.volta(est, True, "ok", pub, Prev([1.0] * 16), AGORA + 86400)
        f = est["fechadas"][0]
        self.assertLess(f["R"], -1.0); self.assertGreater(f["R_controlo"], 0)
        self.assertEqual(f["controlo"]["motivo"], "24h")

    def test_saida_24h_ao_preco_do_livro(self):
        est = self.abrir()
        pub = Pub(infos={"SOL": dict(INFO, ctVal=0.01)}, livro={"bids": [(103.0, 99)], "asks": [(103.2, 99)]})
        K.volta(est, True, "ok", pub, Prev([1.0] * 16), AGORA + 86400)
        f = est["fechadas"][0]
        self.assertEqual(f["motivo"], "24h"); self.assertAlmostEqual(f["saida"], 103.0); self.assertGreater(f["R"], 0)
        self.assertNotEqual(est["capital"], 20.0)

    def test_short_paga_e_recebe_financiamento(self):
        R_rec, _ = K.r_de("SHORT", 100, 100, 102, 10, 0.001)
        R_pag, _ = K.r_de("LONG", 100, 100, 98, 10, 0.001)
        self.assertGreater(R_rec, R_pag)

    def test_falhas_de_leitura(self):
        est = K.novo(); p = Pub(); p.infos = None
        r = K.volta(est, True, "ok", p, Prev(SOBE), AGORA)
        self.assertTrue(r["entradas_bloqueadas"]); self.assertEqual(est["previsoes"], [])
        est = K.novo()
        r = K.volta(est, True, "ok", Pub(perp={}), Prev(SOBE), AGORA)
        self.assertEqual(r["entradas_bloqueadas"], "sem dados")

    def test_velas_atrasadas_nao_contam(self):
        est = K.novo()
        K.volta(est, True, "ok", Pub(perp={"SOL": velas(fim=DIA - 6 * H)}), Prev(SOBE), AGORA)
        self.assertEqual(est["previsoes"], [])


class Estado(unittest.TestCase):
    def test_adulterado_sem_entradas(self):
        p = os.path.join(tempfile.mkdtemp(), "k.json")
        K.guardar(p, K.novo())
        c = json.load(open(p)); c["estado"]["capital"] = 1e6; json.dump(c, open(p, "w"))
        est, ok, mot = K.carregar(p)
        self.assertFalse(ok)
        r = K.volta(est, ok, mot, Pub(), Prev(SOBE), AGORA)
        self.assertEqual(r["entradas"], 0); self.assertIn("adulterado", r["entradas_bloqueadas"])

    def test_inexistente_so_com_inicializacao(self):
        p = os.path.join(tempfile.mkdtemp(), "x.json")
        self.assertFalse(K.carregar(p)[1]); self.assertTrue(K.carregar(p, iniciar=True)[1])


class SoLeitura(unittest.TestCase):
    def test_sem_escrita_sem_chaves_sem_executor(self):
        src = open(K.__file__).read()
        tree = ast.parse(src)
        mods = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names} | \
               {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
        self.assertFalse(mods & {"tools.okx_short", "tools.okx_exec", "okx_short", "okx_exec", "requests", "hmac"})
        for proibido in ("POST", "API_KEY", "OKX_KEY", "SECRET", "PASSPHRASE", "/trade/", "set-leverage"):
            self.assertNotIn(proibido, src)


class NoRegisto(unittest.TestCase):
    def test_entra_como_sombra_com_controlo_a_parte(self):
        from engine import registo as G
        est = Volta().abrir()
        pub = Pub(infos={"SOL": dict(INFO, ctVal=0.01)}, livro={"bids": [(103.0, 99)], "asks": [(103.2, 99)]})
        K.volta(est, True, "ok", pub, Prev([1.0] * 16), AGORA + 86400)
        ops = G.do_kronos_sombra(est)
        self.assertEqual([o["classe"] for o in ops], ["sombra"]); self.assertEqual(ops[0]["estrategia"], "Kronos K1 sombra")


if __name__ == "__main__":
    unittest.main()
