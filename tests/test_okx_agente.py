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
                          c["so_mercado"]), (1.0, 1.0, 3, 3.0, True))   # (10/11, OK do Rui) so o panico do mercado todo
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
