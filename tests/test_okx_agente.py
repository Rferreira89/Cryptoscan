"""(04/11) Agente OKX: segue uma operacao com custos de futuros e calcula o tamanho para 20 USD."""
import unittest
from tools import okx_agente as A


class Agente(unittest.TestCase):
    def test_objetivo_com_custos_de_futuros(self):
        op = {"entrada": 1.0, "stop": 0.9, "alvo": 1.2, "risco": 0.1, "t_fill": 0, "visto": -1}
        fim = A.seguir(op, [{"t": 0, "o": 1.0, "h": 1.05, "l": 0.95, "c": 1.0}, {"t": A.H4, "o": 1.0, "h": 1.21, "l": 0.99, "c": 1.2}])
        self.assertEqual(fim[1], "objetivo")
        self.assertAlmostEqual(fim[0], 2.0 - (0.0002 + 0.0002 * 1.2) / 0.1, places=3)

    def test_stop_na_primeira_vela_so_se_abrir_acima(self):
        op = {"entrada": 1.0, "stop": 0.9, "alvo": 1.2, "risco": 0.1, "t_fill": 0, "visto": -1}
        self.assertEqual(A.seguir(op, [{"t": 0, "o": 0.95, "h": 1.0, "l": 0.85, "c": 0.9}])[1], "stop")

    def test_tamanho_para_20_usd(self):
        nom, mn, cabe = A.tamanho(20.0, 1.0, 0.92, {"ctVal": 1, "minSz": 1})
        self.assertAlmostEqual(nom, 2.5)
        self.assertTrue(cabe)
        self.assertFalse(A.tamanho(20.0, 1.0, 0.92, {"ctVal": 10, "minSz": 1})[2])


if __name__ == "__main__":
    unittest.main()


class Calibracao(unittest.TestCase):
    def test_metricas_e_alerta(self):
        from tools import okx_agente as A
        m = A.metricas([2.0, -1.0, 2.0, -1.0])
        self.assertEqual((m["n"], m["r_medio"], m["acerto_pct"], m["profit_factor"]), (4, 0.5, 50, 2.0))
        self.assertEqual(A.metricas([]), {"n": 0})
        st = {"desempenho": {"mercado": A.metricas([-1.0] * 15 + [0.5] * 5)}}
        self.assertIn("🚨", A.alerta_vantagem(st))
        self.assertIsNone(A.alerta_vantagem(st))                  # uma vez por patamar
        st = {"desempenho": {"mercado": A.metricas([1.0, -0.2] * 6)}}
        self.assertIsNone(A.alerta_vantagem(st))                  # menos de 20


class Classe(unittest.TestCase):
    def test_cripto_pela_categoria_da_okx(self):
        from tools import okx_agente as A
        self.assertTrue(A.e_cripto({"instId": "0G-USDT-SWAP", "instCategory": "1"}, set()))     # cripto sem spot
        self.assertFalse(A.e_cripto({"instId": "NVDA-USDT-SWAP", "instCategory": "3"}, {"NVDA"}))
        self.assertTrue(A.e_cripto({"instId": "BTC-USDT-SWAP"}, {"BTC"}))                      # sem o campo: regra antiga
        self.assertFalse(A.e_cripto({"instId": "XAU-USDT-SWAP"}, {"BTC"}))


class Radar(unittest.TestCase):
    def test_radar_diz_o_que_falta_e_relata_uma_vez_por_dia(self):
        import time as _t
        from unittest import mock
        from tools import okx_agente as A
        c = lambda px: [{"t": 1000 + i * 14400, "o": p, "h": p, "l": p, "c": p} for i, p in enumerate(px)]
        caiu = c([1.0] * 31 + [0.92] * 18)                # -8% em 3 dias
        parado = c([1.0] * 49)
        btc = c([100.0] * 40 + [101.0] * 9)
        fund = [(i, -0.0001) for i in range(300)]
        with mock.patch.object(A, "funding", return_value=fund), mock.patch.object(A.time, "sleep"):
            R = A.radar_quase([("XYZ", {"inst": "XYZ-USDT-SWAP"}, caiu), ("ABC", {"inst": "ABC-USDT-SWAP"}, parado)], btc, {})
        self.assertEqual([x["a"] for x in R["lista"]], ["XYZ"])
        self.assertTrue(any("queda de 3 dias -8.0%" in f for f in R["lista"][0]["falta"]))
        self.assertTrue(any("BTC" in f for f in R["lista"][0]["falta"]))
        st = {"radar": R}
        hora19 = 86400 * 20000 + 19 * 3600 + 120
        self.assertIn("XYZ", A.relatorio_radar(st, hora19))
        self.assertIsNone(A.relatorio_radar(st, hora19 + 600))     # so uma vez por dia
        self.assertIsNone(A.relatorio_radar({"radar": R}, hora19 - 3600))


class Macro(unittest.TestCase):
    def test_entra_so_acima_da_media_a_subir(self):
        from tools import okx_macro as M
        sobe = [{"t": i, "c": 100 + i} for i in range(80)]
        entra, sai, forca, px, m = M.sinal(sobe)
        self.assertTrue(entra)
        self.assertFalse(sai)
        desce = [{"t": i, "c": 200 - i} for i in range(80)]
        entra, sai, *_ = M.sinal(desce)
        self.assertFalse(entra)
        self.assertTrue(sai)
        self.assertIsNone(M.sinal(sobe[:30]))


class Execucao(unittest.TestCase):
    def setUp(self):
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
        import okx_exec
        self.E = okx_exec
        # (05/11) o travao e fail-closed sem DATA_KEY: estes testes simulam o agente com a chave presente
        from unittest import mock
        p = mock.patch.dict(os.environ, {"DATA_KEY": "teste-agente"})
        p.start(); self.addCleanup(p.stop)
        # estes testes verificam H40/H46 numa conta com o maximo ja inicializado (o travao tem testes proprios em
        # tests/test_okx_seguranca.py)
        q = mock.patch.object(okx_exec, "estado_pico", lambda R, c, eq: ("ok", eq))
        q.start(); self.addCleanup(q.stop)
        # Testes de execução simulam uma conta cujo USD-M settlement já foi confirmado em USDC.
        u = mock.patch.object(okx_exec.DERIV, "validate_okx_account_config",
                              return_value=(True, "USDC confirmado"))
        u.start(); self.addCleanup(u.stop)

    def info(self, **kw):
        i = {"inst": "HUMA-USD_UM_XPERP-310101", "ctVal": 10.0, "minSz": 1.0, "lotSz": 1.0, "tick": 0.00001, "ctType": "linear", "lever": 20}
        i.update(kw)
        return i

    def test_plano_arrisca_1pct_e_respeita_minimos(self):
        p = self.E.plano({"lim": 0.0236, "atr": 0.001}, self.info(), 20.0, dict(self.E.CFG_PADRAO))
        self.assertIsNotNone(p)
        self.assertLessEqual(p["risco_usd"], 0.2 + 1e-9)          # 1% de 20 USD
        self.assertAlmostEqual(p["stop"], p["lim"] - 0.002, places=5)
        self.assertAlmostEqual(p["alvo"], p["lim"] + 0.004, places=5)
        self.assertEqual(p["alav"], int(1 / (1.5 * 0.002 / p["lim"])) if int(1 / (1.5 * 0.002 / p["lim"])) < 10 else 10)
        largo = self.E.plano({"lim": 1.0, "atr": 0.075}, self.info(ctVal=1.0), 20.0, dict(self.E.CFG_PADRAO))   # stop a 15%
        self.assertEqual(largo["alav"], 4)
        self.assertIsNone(self.E.plano({"lim": 100.0, "atr": 0.01}, self.info(ctVal=1000.0), 20.0, dict(self.E.CFG_PADRAO)))
        # minimo obriga a 1,5%: aceita (teto 2%)
        p2 = self.E.plano({"lim": 1.0, "atr": 0.0375}, self.info(ctVal=4.0, tick=0.0001), 20.0, dict(self.E.CFG_PADRAO))
        self.assertEqual(p2["sz"], 1.0)
        self.assertLessEqual(p2["risco_usd"], 0.4)

    def test_desligado_nao_envia_ordens(self):
        from unittest import mock
        chamadas = []
        st = {}
        with mock.patch.object(self.E, "_chaves", return_value=("k", "s", "p")), \
                mock.patch.object(self.E, "privado", side_effect=lambda *a, **k: chamadas.append(a) or {"code": "0", "data": []}), \
                mock.patch.object(self.E, "cfg", return_value=dict(self.E.CFG_PADRAO, real=False)):
            self.E.correr(st, [("HUMA", {"t_sig": 1e10, "lim": 0.02, "atr": 0.001})], 1e10, [])
        self.assertFalse(any(a[0] == "POST" for a in chamadas))

    def test_ligado_poe_ordem_com_stop_e_objetivo_e_caduca(self):
        from unittest import mock
        posts, msgs = [], []
        now = 2_000_000_000

        def privado(metodo, path, corpo=None):
            if metodo == "POST":
                posts.append((path, corpo))
                return {"code": "0", "data": [{"ordId": "1", "sCode": "0"}]}
            if "balance" in path:
                return {"code": "0", "data": [{"totalEq": "20"}]}
            if "trade/order" in path:
                # (11/11, P2) depois do pedido de cancelamento a OKX passa a dizer cancelada com 0 executado
                if any(p == "/api/v5/trade/cancel-order" for p, _ in posts):
                    return {"code": "0", "data": [{"state": "canceled", "accFillSz": "0"}]}
                return {"code": "0", "data": [{"state": "live"}]}
            return {"code": "0", "data": []}
        st = {}
        sig = {"t_sig": now - H4, "lim": 0.0236, "atr": 0.001, "tipo": "mercado"}
        with mock.patch.object(self.E, "_chaves", return_value=("k", "s", "p")), mock.patch.object(self.E, "privado", privado), \
                mock.patch.object(self.E, "cfg", return_value=dict(self.E.CFG_PADRAO, real=True, panico_real=True)), \
                mock.patch.object(self.E, "xperps", return_value={"HUMA": self.info()}):
            self.E.correr(st, [("HUMA", sig)], now, msgs)
            ordem = [c for p, c in posts if p == "/api/v5/trade/order"][0]
            self.assertEqual(ordem["side"], "buy")
            self.assertEqual(ordem["tdMode"], "isolated")
            self.assertIn("slTriggerPx", ordem["attachAlgoOrds"][0])
            self.assertIn("HUMA", st["real"]["ops"])
            self.E.correr(st, [("HUMA", sig)], now + 60, msgs)                 # o mesmo sinal nao repete
            self.assertEqual(sum(1 for p, _ in posts if p == "/api/v5/trade/order"), 1)
            self.E.correr(st, [("ISO", {"t_sig": now - H4, "lim": 1.0, "atr": 0.01, "tipo": "isolado"})], now + 120, msgs)
            self.assertNotIn("ISO", st["real"]["ops"])                          # H40: panico isolado fica em papel
            self.E.correr(st, [], now + 3 * H4, msgs)                          # caducou: cancela
        self.assertIn("/api/v5/trade/cancel-order", [p for p, _ in posts])
        self.assertNotIn("HUMA", st["real"]["ops"])

    def test_recuo_real_so_ligado_e_com_metade_do_risco(self):
        from unittest import mock
        posts, msgs = [], []
        now = 2_000_000_000

        def privado(metodo, path, corpo=None):
            if metodo == "POST":
                posts.append((path, corpo))
                return {"code": "0", "data": [{"ordId": "1", "sCode": "0"}]}
            if "balance" in path:
                return {"code": "0", "data": [{"totalEq": "20"}]}
            return {"code": "0", "data": []}
        sig = {"t_sig": now - H4, "lim": 0.0236, "atr": 0.001, "tipo": "recuo"}
        for ligado, espera in ((False, 0), (True, 1)):
            posts.clear(); st = {}
            with mock.patch.object(self.E, "_chaves", return_value=("k", "s", "p")), mock.patch.object(self.E, "privado", privado), \
                    mock.patch.object(self.E, "cfg", return_value=dict(self.E.CFG_PADRAO, real=True, risco_pct=2.0, recuo_real=ligado)), \
                    mock.patch.object(self.E, "xperps", return_value={"HUMA": self.info()}):
                self.E.correr(st, [("HUMA", sig)], now, msgs)
            self.assertEqual(sum(1 for p, _ in posts if p == "/api/v5/trade/order"), espera)
        self.assertEqual(st["real"]["ops"]["HUMA"]["estrategia"], "recuo")
        ordem = [c for p, c in posts if p == "/api/v5/trade/order"][0]
        self.assertLessEqual(float(ordem["sz"]) * 10.0 * 0.002, 0.2 + 1e-9)       # 1% de 20 USD, nao 2%
        self.assertIn("recuo na subida", msgs[-1])

    def test_h40_suspensa_nao_abre_mas_h46_continua(self):
        from unittest import mock
        posts, msgs = [], []
        now = 2_000_000_000

        def privado(metodo, path, corpo=None):
            if metodo == "POST":
                posts.append((path, corpo))
                return {"code": "0", "data": [{"ordId": "1", "sCode": "0"}]}
            if "balance" in path:
                return {"code": "0", "data": [{"totalEq": "20"}]}
            return {"code": "0", "data": []}
        st = {}
        panico = {"t_sig": now - H4, "lim": 0.0236, "atr": 0.001, "tipo": "mercado"}
        recuo = {"t_sig": now - H4, "lim": 1.0, "atr": 0.01, "tipo": "recuo"}
        with mock.patch.object(self.E, "_chaves", return_value=("k", "s", "p")), mock.patch.object(self.E, "privado", privado), \
                mock.patch.object(self.E, "cfg", return_value=dict(self.E.CFG_PADRAO, real=True, recuo_real=True, panico_real=False)), \
                mock.patch.object(self.E, "xperps", return_value={"HUMA": self.info(), "XYZ": self.info(inst="XYZ-USD_UM_XPERP-1", ctVal=1.0)}):
            self.E.correr(st, [("HUMA", panico), ("XYZ", recuo)], now, msgs)
        self.assertNotIn("HUMA", st["real"]["ops"])                         # H40 so em papel
        self.assertIn("XYZ", st["real"]["ops"])                             # H46 continua real
        self.assertEqual(st["real"]["ops"]["XYZ"]["estrategia"], "recuo")
        self.assertTrue(any("só em papel" in m for m in msgs))

    def test_h40_sem_interruptor_na_configuracao_fica_em_papel(self):
        from unittest import mock
        posts = []
        now = 2_000_000_000

        def privado(metodo, path, corpo=None):
            if metodo == "POST":
                posts.append(path)
                return {"code": "0", "data": [{"ordId": "1", "sCode": "0"}]}
            if "balance" in path:
                return {"code": "0", "data": [{"totalEq": "20"}]}
            return {"code": "0", "data": []}
        cfg_sem = {k: v for k, v in dict(self.E.CFG_PADRAO, real=True).items() if k != "panico_real"}
        st = {}
        sinais = [("HUMA", {"t_sig": now - H4, "lim": 0.0236, "atr": 0.001, "tipo": "mercado"}),
                  ("ABC", {"t_sig": now - H4, "lim": 0.0236, "atr": 0.001, "tipo": "outra"})]       # desconhecida
        with mock.patch.object(self.E, "_chaves", return_value=("k", "s", "p")), mock.patch.object(self.E, "privado", privado), \
                mock.patch.object(self.E, "cfg", return_value=cfg_sem), \
                mock.patch.object(self.E, "xperps", return_value={"HUMA": self.info(), "ABC": self.info(inst="ABC-USD_UM_XPERP-1")}):
            self.E.correr(st, sinais, now, [])
        self.assertNotIn("/api/v5/trade/order", posts)                    # nada aberto
        self.assertFalse(self.E.CFG_PADRAO["panico_real"])

    def test_ordens_existentes_continuam_geridas_com_h40_suspensa(self):
        from unittest import mock
        posts = []
        now = 2_000_000_000

        def privado(metodo, path, corpo=None):
            if metodo == "POST":
                posts.append(path)
                return {"code": "0", "data": [{"sCode": "0"}]}
            if "trade/order?" in path:
                if "/api/v5/trade/cancel-order" in posts:                # (11/11, P2) estado final confirmado
                    return {"code": "0", "data": [{"state": "canceled", "accFillSz": "0"}]}
                return {"code": "0", "data": [{"state": "live"}]}
            return {"code": "0", "data": []}
        st = {"real": {"ops": {"HUMA": {"inst": "HUMA-USD_UM_XPERP-1", "ordId": "9", "estado": "pendente", "t_sig": now - 4 * H4,
                                        "valido_ate": now - 10, "criado": now - 4 * H4, "lim": 1, "stop": 0.9, "alvo": 1.2, "alav": 3}},
                       "hist": [], "pico": None}}
        with mock.patch.object(self.E, "_chaves", return_value=("k", "s", "p")), mock.patch.object(self.E, "privado", privado), \
                mock.patch.object(self.E, "cfg", return_value=dict(self.E.CFG_PADRAO, real=True, panico_real=False)), \
                mock.patch.object(self.E, "reconciliar", lambda *a: None):
            self.E.correr(st, [], now, [])
        self.assertIn("/api/v5/trade/cancel-order", posts)              # ordem caducada continua a ser tratada
        self.assertNotIn("HUMA", st["real"]["ops"])
        self.assertNotIn("/api/v5/trade/close-position", posts)           # nada fechado a forca

    def test_config_real_da_okx(self):
        import json, os
        c = json.load(open(os.path.join(os.path.dirname(__file__), "..", "okx_config.json")))
        self.assertEqual((c["real"], c["recuo_real"], c["panico_real"]), (True, True, False))   # (10/11, ordem do Rui) H40 suspensa do real
        self.assertEqual((c["panico_risco_pct"], c["panico_risco_max_pct"], c["panico_max_posicoes"], c["risco_total_max_pct"],
                          c["so_mercado"]), (1.0, 1.0, 3, 5.0, True))   # (10/11, OK do Rui) so o panico do mercado todo; (14/11) teto 5% como na Bybit
        self.assertEqual((c["espelho_real"], c["espelho_risco_short_pct"], c["espelho_teto_short_pct"], c["espelho_risco_long_pct"],
                          c["espelho_teto_long_pct"], c["espelho_max_posicoes"]), (True, 2.5, 5.0, 1.0, 1.0, 2))   # (14/11, Rui)
        self.assertEqual((c["risco_pct"], c["alavancagem"], c["max_posicoes"], c["recuo_risco_pct"]), (2.0, 10, 30, 1.0))


    def _corre(self, sinais, cfg_extra, ops=None, now=2_000_000_000):
        from unittest import mock
        posts, msgs = [], []

        def privado(metodo, path, corpo=None):
            if metodo == "POST":
                posts.append((path, corpo))
                return {"code": "0", "data": [{"ordId": str(len(posts)), "sCode": "0"}]}
            if "balance" in path:
                return {"code": "0", "data": [{"totalEq": "20"}]}
            if "trade/order" in path:
                return {"code": "0", "data": [{"state": "live"}]}
            return {"code": "0", "data": []}
        st = {"real": {"ops": dict(ops or {}), "hist": []}}
        xp = {b: self.info(inst=f"{b}-USD_UM_XPERP-1") for b, _ in sinais}
        xp.update({b: self.info(inst=o["inst"]) for b, o in (ops or {}).items()})
        with mock.patch.object(self.E, "_chaves", return_value=("k", "s", "p")), mock.patch.object(self.E, "privado", privado), \
                mock.patch.object(self.E, "cfg", return_value=dict(self.E.CFG_PADRAO, real=True, **cfg_extra)), \
                mock.patch.object(self.E, "xperps", return_value=xp), \
                mock.patch.object(self.E, "acompanhar", return_value=False):
            self.E.correr(st, sinais, now, msgs)
        ordens = [c for p_, c in posts if p_ == "/api/v5/trade/order"]
        return st, ordens, msgs

    # ---------- (14/11, Rui) campeoes da arena da Bybit tambem na OKX ----------
    def _esp(self, sinais, last, cfg_extra=None, ops=None, now=2_000_000_000):
        from unittest import mock
        with mock.patch.object(self.E.A, "get", return_value=[{"last": str(last)}]):
            return self._corre(sinais, dict(dict(espelho_real=True, risco_total_max_pct=5.0), **(cfg_extra or {})), ops=ops, now=now)

    def test_espelho_short_vende_com_o_stop_e_objetivo_do_campeao(self):
        now = 2_000_000_000
        sig = {"tipo": "espelho", "lado": "SHORT", "stop": 0.0260, "alvo": 0.0200, "t_sig": now - 600, "hold_s": 20 * 86400,
               "estrategia": "SHORT_TURTLE", "id": "X-SHORT_TURTLE-1"}
        st, ordens, msgs = self._esp([("XLM", sig)], 0.0236)
        self.assertEqual(len(ordens), 1)
        o = ordens[0]
        self.assertEqual(o["side"], "sell")
        self.assertEqual(float(o["attachAlgoOrds"][0]["slTriggerPx"]), 0.026)
        self.assertEqual(float(o["attachAlgoOrds"][0]["tpTriggerPx"]), 0.02)
        self.assertLess(float(o["px"]), 0.0236)                                  # limite 0,2% abaixo: entra ja
        op = st["real"]["ops"]["XLM"]
        self.assertEqual((op["estrategia"], op["lado"], op["hold_s"], op["estrategia_bybit"]),
                         ("espelho", "SHORT", 7 * 86400, "SHORT_TURTLE"))  # (20/11) 7 dias, pedido do Rui (antes 20)
        self.assertLessEqual(op["risco_pct"], 5.0)
        self.assertEqual(op["valido_ate"], now - 600 + H4)
        self.assertTrue(any("campeão da arena SHORT_TURTLE" in m and "venda a descoberto" in m for m in msgs))

    def test_espelho_desligado_nao_entra(self):
        now = 2_000_000_000
        sig = {"tipo": "espelho", "lado": "SHORT", "stop": 0.0260, "alvo": 0.0200, "t_sig": now - 600}
        _, ordens, _ = self._esp([("XLM", sig)], 0.0236, dict(espelho_real=False))
        self.assertEqual(ordens, [])

    def test_espelho_preco_fora_do_plano_nao_entra(self):
        now = 2_000_000_000
        sig = {"tipo": "espelho", "lado": "SHORT", "stop": 0.0260, "alvo": 0.0200, "t_sig": now - 600}
        _, ordens, msgs = self._esp([("XLM", sig)], 0.0262)                     # ja acima do stop
        self.assertEqual(ordens, []); self.assertTrue(any("fora do plano" in m for m in msgs))

    def test_funil_regista_decisoes_sem_repetir(self):
        # (18/11) cada sinal fica com a ultima decisao do executor (publico, sem valores)
        now = 2_000_000_000
        ok = {"tipo": "espelho", "lado": "SHORT", "stop": 0.0260, "alvo": 0.0200, "t_sig": now - 600,
              "estrategia": "SHORT_TURTLE", "origem": "okx"}
        fora = dict(ok, stop=0.0230)                                        # preco ja acima do stop
        st, ordens, _ = self._esp([("XLM", ok), ("ABC", fora)], 0.0236)
        f = st["real"]["funil"]
        self.assertEqual(f[f"XLM:{now - 600}"]["decisao"], "ordem enviada")
        self.assertEqual(f[f"XLM:{now - 600}"]["origem"], "espelho_okx")
        self.assertEqual(f[f"ABC:{now - 600}"]["decisao"], "preco fora do plano")
        r = self.E.resumo_funil(st["real"], now)
        dia = list(r)[0]
        self.assertEqual(r[dia]["espelho_okx"], {"ordem enviada": 1, "preco fora do plano": 1})
        self.assertNotIn("usd", str(f).lower())

    def test_funil_h40_suspensa(self):
        now = 2_000_000_000
        sig = {"t_sig": now - H4, "lim": 0.0236, "atr": 0.001, "tipo": "mercado"}
        st, ordens, _ = self._corre([("HUMA", sig)], dict(panico_real=False), now=now)
        self.assertEqual(ordens, [])
        self.assertEqual(st["real"]["funil"][f"HUMA:{now - H4}"]["decisao"], "H40 suspensa do real")

    def test_espelho_long_arrisca_1pct(self):
        now = 2_000_000_000
        sig = {"tipo": "espelho", "lado": "LONG", "stop": 0.0226, "alvo": 0.0280, "t_sig": now - 600}
        st, ordens, _ = self._esp([("ABC", sig)], 0.0236)
        self.assertEqual(len(ordens), 1); self.assertEqual(ordens[0]["side"], "buy")
        self.assertLessEqual(st["real"]["ops"]["ABC"]["risco_pct"], 1.0)

    def test_espelho_maximo_2_posicoes(self):
        now = 2_000_000_000
        ops = {b: {"inst": f"{b}-USD_UM_XPERP-1", "ordId": "9", "estado": "aberta", "estrategia": "espelho", "risco_pct": 1.0,
                   "t_sig": now - H4, "lado": "SHORT"} for b in ("A", "B")}
        sig = {"tipo": "espelho", "lado": "SHORT", "stop": 0.0260, "alvo": 0.0200, "t_sig": now - 600}
        _, ordens, msgs = self._esp([("XLM", sig)], 0.0236, ops=ops)
        self.assertEqual(ordens, []); self.assertTrue(any("máximo 2" in m for m in msgs))

    def test_espelho_sinais_so_da_vela_atual_e_reais(self):
        now = 2_000_000_000
        t0 = now // H4 * H4
        st_b = {"ledger": [
            {"id": "XLM-1", "asset": "XLM", "mode": "REAL", "status": "OPEN", "side": "SHORT", "issued_at": t0 + 100,
             "stop": 0.15, "tp": [0.12, 0.1], "strategy": "SHORT_TURTLE"},
            {"id": "BTC-1", "asset": "BTC", "mode": "REAL", "status": "OPEN", "side": "SHORT", "issued_at": t0 - H4 + 100,
             "stop": 75000, "tp": [65000], "strategy": "SHORT_TURTLE"},                      # vela anterior
            {"id": "ETH-1", "asset": "ETH", "mode": "PAPER", "status": "OPEN", "issued_at": t0 + 100, "stop": 1, "tp": [2]},
            {"id": "SOL-1", "asset": "SOL", "mode": "REAL", "status": "CLOSED", "issued_at": t0 + 100, "stop": 1, "tp": [2]}],
            "signals": {"XLM-1": {"plan": {"max_hold_s": 1728000, "side": "SHORT"}}}}
        out = self.E.espelho_sinais(st_b, now)
        self.assertEqual([a for a, _ in out], ["XLM"])
        s = out[0][1]
        self.assertEqual((s["tipo"], s["lado"], s["stop"], s["alvo"], s["hold_s"], s["t_sig"]),
                         ("espelho", "SHORT", 0.15, 0.12, 1728000, t0))
        self.assertEqual(self.E.espelho_sinais(None, now), [])

    def test_campeoes_procuram_sinal_em_todos_os_xperps(self):
        from unittest import mock
        from tools import arena_ringue as AR
        now = 2_000_000_000
        t_ult = now // H4 * H4 - H4                       # vela que acabou de fechar
        velas = lambda inst: [{"t": t_ult - (299 - i) * H4, "o": 1, "h": 1, "l": 1, "c": 1, "v": 1} for i in range(300)]
        sinal = lambda c4, px, cfg=None: ({"side": "SHORT", "stop": 1.1, "tp": [0.9, 0.8], "hold_s": 86400,
                                           "t_sig": c4[-1]["t"] + H4} if AR.CTX["asset"] == "ADA" else None)
        xp = {b: self.info(inst=f"{b}-USD_UM_XPERP-1") for b in ("ADA", "DOT", "BTC")}
        # (18/11) SHORT_TURTLE esta em arena.mortos (morreu noutra fase) mas e campeao da Bybit: conta. Uma morte
        # decidida pelo Rui ("decisao") e o que esta so em papel nunca contam.
        sb = {"campeoes_ant": ["SHORT_TURTLE", "MORTO", "PAPEL"], "so_papel": {"PAPEL": {}},
              "arena": {"mortos": {"MORTO": {"decisao": True}, "SHORT_TURTLE": {"motivo": "forma recente (90 dias)"}}}}
        reg = AR._Sinais({"SHORT_TURTLE": sinal, "MORTO": lambda *a: 1 / 0, "PAPEL": lambda *a: 1 / 0})
        with mock.patch.object(AR, "SINAIS", reg):
            out = self.E.campeoes_sinais(sb, xp, now, velas=velas)
        self.assertEqual([a for a, _ in out], ["ADA"])
        s = out[0][1]
        self.assertEqual((s["tipo"], s["lado"], s["stop"], s["alvo"], s["estrategia"], s["origem"]),
                         ("espelho", "SHORT", 1.1, 0.9, "SHORT_TURTLE", "okx"))
        with mock.patch.object(AR, "SINAIS", reg):     # vela velha: nada
            self.assertEqual(self.E.campeoes_sinais(sb, xp, now + 2 * H4, velas=velas), [])
        self.assertEqual(self.E.campeoes_sinais({}, xp, now, velas=velas), [])

    def test_velas_4h_so_fechadas_e_por_ordem(self):
        from unittest import mock
        d = [["3000000", "1", "2", "0.5", "1.5", "10", "", "", "0"], ["2000000", "1", "2", "0.5", "1.4", "9", "", "", "1"],
             ["1000000", "1", "2", "0.5", "1.3", "8", "", "", "1"]]
        with mock.patch.object(self.E.A, "get", return_value=d):
            v = self.E.velas_4h("X")
        self.assertEqual([b["t"] for b in v], [1000, 2000])

    def test_espelho_nao_e_cancelado_pela_suspensao(self):
        from engine import suspensao
        op = {"estado": "pendente", "estrategia": "espelho"}
        self.assertEqual(suspensao.decidir({"real": True, "espelho_real": True}, op), "manter")
        self.assertEqual(suspensao.decidir({"real": True, "espelho_real": False}, op), "cancelar_pendente")

    def test_stop_reposto_num_short_compra_para_fechar(self):
        from unittest import mock
        posts = []

        def privado(metodo, path, corpo=None):
            if metodo == "POST":
                posts.append(corpo)
                return {"code": "0", "data": [{"sCode": "0"}]}
            if "positions" in path:
                return {"code": "0", "data": [{"pos": "-3"}]}
            return {"code": "0", "data": []}
        R = {"ops": {"XLM": {"inst": "XLM-USD_UM_XPERP-1", "estado": "aberta", "lado": "SHORT", "stop": 0.15, "alvo": 0.12,
                             "entrada": 0.137}}}
        with mock.patch.object(self.E, "privado", privado):
            self.E.confirmar_stops(R, 2_000_000_000, [])
        self.assertEqual((posts[0]["side"], posts[0]["sz"], posts[0]["reduceOnly"]), ("buy", "3", True))

    def test_h40_isolado_reprovado_nunca_entra(self):
        """(13/11, ordem do Rui) panico isolado reprovado para dinheiro real: nem com a H40 e o isolado ligados."""
        now = 2_000_000_000
        st, ordens, _ = self._corre([("ISO", {"t_sig": now - H4, "lim": 0.0236, "atr": 0.001, "tipo": "isolado"})],
                                    dict(panico_real=True, so_mercado=False))
        self.assertEqual(ordens, [])
        self.assertNotIn("ISO", st["real"]["ops"])

    def test_h40_limitada_mercado_entra_com_1pct(self):
        now = 2_000_000_000
        st, ordens, _ = self._corre([("MKT", {"t_sig": now - H4, "lim": 0.0236, "atr": 0.001, "tipo": "mercado"})],
                                    dict(panico_real=True, so_mercado=False))
        self.assertEqual(len(ordens), 1)
        self.assertLessEqual(float(ordens[0]["sz"]) * 10.0 * 0.002, 0.2 + 1e-9)          # 1% de 20 USD
        op = st["real"]["ops"]["MKT"]
        self.assertEqual(op["estrategia"], "panico"); self.assertLessEqual(op["risco_pct"], 1.0)

    def test_h40_minimo_acima_de_1pct_nao_entra(self):
        now = 2_000_000_000
        st, ordens, msgs = self._corre([("X", {"t_sig": now - H4, "lim": 1.0, "atr": 0.0375, "tipo": "mercado"})],
                                       dict(panico_real=True, so_mercado=False))
        # um contrato (10 x 0,075) arriscaria 3,75% da conta: o teto da H40 e 1% -> nao entra
        self.assertEqual(ordens, []); self.assertNotIn("X", st["real"]["ops"])

    def test_h40_maximo_3_posicoes(self):
        now = 2_000_000_000
        ops = {b: {"inst": f"{b}-USD_UM_XPERP-1", "ordId": "9", "estado": "aberta", "estrategia": "panico", "risco_pct": 0.5,
                   "t_sig": now - H4} for b in ("A", "B", "C")}
        st, ordens, msgs = self._corre([("D", {"t_sig": now - H4, "lim": 0.0236, "atr": 0.001, "tipo": "mercado"})],
                                       dict(panico_real=True, so_mercado=False), ops=ops)
        self.assertEqual(ordens, []); self.assertTrue(any("máximo 3" in m for m in msgs))

    def test_teto_de_risco_total_3pct_inclui_h46(self):
        now = 2_000_000_000
        ops = {"R1": {"inst": "R1-USD_UM_XPERP-1", "ordId": "9", "estado": "aberta", "estrategia": "recuo", "risco_pct": 1.0, "t_sig": now - H4},
               "P1": {"inst": "P1-USD_UM_XPERP-1", "ordId": "8", "estado": "aberta", "estrategia": "panico", "risco_pct": 1.0, "t_sig": now - H4},
               "R2": {"inst": "R2-USD_UM_XPERP-1", "ordId": "7", "estado": "aberta", "estrategia": "recuo", "risco_pct": 0.9, "t_sig": now - H4}}
        st, ordens, msgs = self._corre([("D", {"t_sig": now - H4, "lim": 0.0236, "atr": 0.001, "tipo": "mercado"})],
                                       dict(panico_real=True, so_mercado=False), ops=ops)
        self.assertEqual(ordens, []); self.assertTrue(any("risco aberto passaria 3.0%" in m for m in msgs))

    def test_h40_desligada_continua_em_papel(self):
        now = 2_000_000_000
        st, ordens, _ = self._corre([("M", {"t_sig": now - H4, "lim": 0.0236, "atr": 0.001, "tipo": "mercado"})],
                                    dict(panico_real=False))
        self.assertEqual(ordens, [])


H4 = 14400
