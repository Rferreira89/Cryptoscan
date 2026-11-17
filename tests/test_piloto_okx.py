"""(17/11) Piloto real OKX: limites, dimensionamento, portas, ordens, stops, reinicios e isolamento - com uma OKX
falsa (nenhum pedido sai daqui)."""
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import piloto_okx as P  # noqa: E402

H4 = 14400
CFG = {"ativo": True, "estrategia": "e495d11739f6", "lado": "LONG", "capital_max": 10.0, "perda_max": 5.0,
       "suspender_em": 3.0, "perda_diaria_max": 1.0, "risco_max_op": 0.25, "nocional_max": 10.0, "alav_max": 5,
       "posicoes_max": 1, "margem": "isolated", "reserva_deslize_pct": 0.3}
INST = {"inst": "ABC-USD_UM_XPERP-310404", "ctVal": "1", "ctMult": "1", "ctValCcy": "ABC", "lotSz": "1", "minSz": "1",
        "tickSz": "0.0001", "lever": "20"}
OOS_OK = {"n": 100, "r_medio": 0.1}


def velas_sinal(t_fim):
    """Velas de 4H em que a ultima e um rompimento com reteste do maximo de 24 velas."""
    v = []
    for k in range(60):
        v.append({"t": t_fim - (60 - k) * H4, "o": 1.0, "h": 1.02, "l": 0.98, "c": 1.0})
    for k in (57, 58, 59):
        v[k].update(c=1.05, h=1.06, o=1.0)               # rompem 1.02 nas 3 anteriores a ultima
    v[-1] = {"t": t_fim - H4, "o": 1.04, "h": 1.05, "l": 1.021, "c": 1.03}
    return v


class FakeOKX:
    def __init__(self, settle="USDC", perm="read_only,trade", saldo=20.0, fill="filled", algo_ok=True, now=0,
                 spread=(1.0299, 1.0301), contas=None, ctval="1"):
        self.ctval = ctval
        self.chamadas, self.settle, self.perm, self.saldo = [], settle, perm, saldo
        self.fill, self.algo_ok, self.now, self.spread = fill, algo_ok, now, spread
        self.pos = None
        self.ordem = None
        self.algos = []
        self.contas = contas if contas is not None else [INST["inst"]]

    def pub(self, path, params=None):
        self.chamadas.append(("GET", path, params))
        if "instruments" in path:
            return [{"instId": INST["inst"], "state": "live", "ctType": "linear", "instCategory": "1", "ruleType": "xperp",
                     "ctVal": self.ctval, "ctMult": "1", "ctValCcy": "ABC", "lotSz": "1", "minSz": "1",
                     "tickSz": "0.0001", "lever": "20"}]
        if "tickers" in path:
            return [{"instId": INST["inst"], "bidPx": str(self.spread[0]), "askPx": str(self.spread[1]), "volCcy24h": "1000000"}]
        if "candles" in path:
            v = velas_sinal(self.now // H4 * H4)
            return [[str(b["t"] * 1000), b["o"], b["h"], b["l"], b["c"], 1, 1, 1, "1"] for b in reversed(v)]
        return []

    def priv(self, metodo, path, corpo=None):
        self.chamadas.append((metodo, path, corpo))
        if path.startswith("/api/v5/account/config"):
            return {"code": "0", "data": [{"settleCcy": self.settle, "perm": self.perm, "posMode": "net_mode", "acctLv": "2"}]}
        if path.startswith("/api/v5/account/balance"):
            return {"code": "0", "data": [{"details": [{"ccy": "USDC", "availBal": str(self.saldo)}]}]}
        if path.startswith("/api/v5/account/instruments"):
            return {"code": "0", "data": [{"instId": i} for i in self.contas]}
        if path == "/api/v5/account/set-leverage":
            return {"code": "0", "data": [{}]}
        if path == "/api/v5/trade/order" and metodo == "POST":
            self.ordem = dict(corpo, ordId="777")
            return {"code": "0", "data": [{"ordId": "777", "sCode": "0"}]}
        if path.startswith("/api/v5/trade/order?"):
            if self.fill == "nenhum":
                return {"code": "0", "data": [{"state": "live", "accFillSz": "0"}]}
            sz = float(self.ordem["sz"])
            acc = sz if self.fill == "filled" else max(1.0, float(int(sz // 2)))
            self.pos = {"pos": str(acc), "upl": "-0.05", "instId": INST["inst"]}
            if self.algo_ok:
                self.algos = [{"slTriggerPx": self.ordem["attachAlgoOrds"][0]["slTriggerPx"], "sz": str(acc), "side": "sell",
                               "reduceOnly": "true", "ordType": "oco"}]
            return {"code": "0", "data": [{"state": "filled" if self.fill == "filled" else "partially_filled",
                                           "accFillSz": str(acc), "avgPx": "1.0302", "fillTime": str(self.now * 1000)}]}
        if path.startswith("/api/v5/account/positions"):
            return {"code": "0", "data": [self.pos] if self.pos else []}
        if path.startswith("/api/v5/trade/orders-algo-pending"):
            return {"code": "0", "data": self.algos if "oco" in path else []}
        if path == "/api/v5/trade/order-algo":
            return {"code": "0" if self.algo_ok else "51000", "data": [{}]}
        if path in ("/api/v5/trade/cancel-order", "/api/v5/trade/close-position"):
            if path.endswith("close-position"):
                self.pos = None
            return {"code": "0", "data": [{}]}
        if path.startswith("/api/v5/trade/fills-history"):
            return {"code": "0", "data": []}
        return {"code": "1", "data": []}

    def posts(self):
        return [c for c in self.chamadas if c[0] == "POST"]


class Piloto(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.now = 1_800_000_000 // H4 * H4 + 120          # 2 min depois de um fecho de 4H
        self.p = mock.patch.object(P, "cfg", return_value=dict(CFG))
        self.p.start()

    def tearDown(self):
        self.p.stop()
        shutil.rmtree(self.d, ignore_errors=True)

    def corre(self, api, **kw):
        kw.setdefault("teste_oos", OOS_OK)
        kw.setdefault("isolado", True)
        return P.ciclo(api, self.d, now=kw.pop("now", self.now), **kw)

    # ---------------- dimensionamento ----------------
    def test_dimensionamento_risco_nocional_e_alavancagem(self):
        pl = {"entrada": 1.0, "stop": 0.9, "alvo": 1.15}
        d, porque = P.dimensionar(pl, INST, CFG, 0.05, saldo=10)
        self.assertIsNone(porque)
        self.assertLessEqual(d["risco_total"], 0.25)
        self.assertLessEqual(d["nocional"], 10)
        self.assertEqual(d["alav"], 1)
        # stop muito perto: o nocional e que trava (10 USDC), nunca o risco
        d, _ = P.dimensionar({"entrada": 1.0, "stop": 0.999, "alvo": 1.0015}, INST, CFG, 0.05, saldo=10)
        self.assertLessEqual(d["nocional"], 10.0)
        self.assertLessEqual(d["risco_total"], 0.25)
        # pouca margem livre -> alavancagem sobe, mas nunca acima de 5x
        for saldo, esperado in ((10, 2), (3, 4)):
            d, _ = P.dimensionar({"entrada": 1.0, "stop": 0.999, "alvo": 1.0015}, INST, CFG, 0.05, saldo=saldo)
            self.assertEqual(d["alav"], esperado)
        d, porque = P.dimensionar({"entrada": 1.0, "stop": 0.999, "alvo": 1.0015}, INST, CFG, 0.05, saldo=1.0)
        self.assertIsNone(d)
        self.assertIn("alavancagem", porque)

    def test_minimo_do_contrato_rejeita_em_vez_de_aumentar(self):
        grande = dict(INST, ctVal="100")                     # 1 contrato = 100 ABC
        d, porque = P.dimensionar({"entrada": 1.0, "stop": 0.9, "alvo": 1.15}, grande, CFG, 0.05, saldo=10)
        self.assertIsNone(d)
        self.assertIn("tamanho minimo", porque)

    def test_custos_entram_no_risco(self):
        pl = {"entrada": 1.0, "stop": 0.9, "alvo": 1.15}
        sem, _ = P.dimensionar(pl, INST, dict(CFG, reserva_deslize_pct=0), 0.0, saldo=10)
        com, _ = P.dimensionar(pl, INST, dict(CFG, reserva_deslize_pct=1.0), 0.3, saldo=10, funding_8h=0.001)
        self.assertLessEqual(com["contratos"], sem["contratos"])
        self.assertGreater(com["custos_estimados"], 0)

    # ---------------- sinal ----------------
    def test_sinal_v2_reproduzivel(self):
        v = velas_sinal(self.now // H4 * H4)
        s = P.sinal_v2(v)
        self.assertIsNotNone(s)
        self.assertAlmostEqual(s["nivel"], 1.02)
        self.assertIsNone(P.sinal_v2(v[:-1]))              # na vela anterior nao havia sinal
        pl = P.plano(s)
        self.assertAlmostEqual(pl["alvo"] - pl["entrada"], 1.5 * (pl["entrada"] - pl["stop"]))

    # ---------------- portas ----------------
    def test_portas_bloqueiam(self):
        casos = [({"settle": "USD"}, {}, "conta_usdc"), ({"perm": "read_only,trade,withdraw"}, {}, "sem_levantamentos"),
                 ({"saldo": 5.0}, {}, "saldo_usdc"), ({}, {"isolado": False}, "isolamento"),
                 ({}, {"teste_oos": {"n": 382, "r_medio": -0.3}}, "teste_fora_da_amostra")]
        for kw_api, kw, porta in casos:
            shutil.rmtree(self.d)
            os.makedirs(self.d)
            api = FakeOKX(now=self.now, **kw_api)
            st, msgs = self.corre(api, **kw)
            self.assertFalse(st["portas"][porta]["ok"], porta)
            self.assertEqual(api.posts(), [], porta)                     # nenhuma ordem
            self.assertTrue(any("portas fechadas" in m for m in msgs), porta)

    def test_config_inativa_bloqueia(self):
        with mock.patch.object(P, "cfg", return_value=dict(CFG, ativo=False)):
            api = FakeOKX(now=self.now)
            st, _ = self.corre(api)
        self.assertFalse(st["portas"]["config_ativa"]["ok"])
        self.assertEqual(api.posts(), [])

    def test_contrato_nao_negociavel_pela_conta(self):
        api = FakeOKX(now=self.now, contas=[])
        st, _ = self.corre(api)
        self.assertEqual(api.posts(), [])
        self.assertIsNone(st["aberta"])

    def test_liquidez_insuficiente(self):
        api = FakeOKX(now=self.now, spread=(1.00, 1.03))
        st, _ = self.corre(api)
        self.assertEqual(api.posts(), [])
        self.assertIn("spread", json.dumps(st["ultimo_sinal"]))

    # ---------------- ordens, execucao, stop ----------------
    def test_entrada_isolada_com_stop_e_confirmacao(self):
        api = FakeOKX(now=self.now)
        st, msgs = self.corre(api)
        posts = api.posts()
        self.assertEqual([c[1] for c in posts], ["/api/v5/account/set-leverage", "/api/v5/trade/order"])
        o = posts[1][2]
        self.assertEqual((o["tdMode"], o["side"], o["ordType"]), ("isolated", "buy", "limit"))
        self.assertTrue(o["clOrdId"].startswith("pil"))
        self.assertIn("slTriggerPx", o["attachAlgoOrds"][0])
        self.assertLessEqual(int(posts[0][2]["lever"]), 5)
        self.assertEqual(st["aberta"]["estado"], "pendente")              # enviada nao e executada
        self.assertTrue(any("Enviada não é executada" in m for m in msgs))
        st, msgs = self.corre(api, now=self.now + 3600)
        self.assertEqual(st["aberta"]["estado"], "aberta")
        self.assertTrue(st["aberta"]["stop_confirmado"])
        self.assertEqual(len([c for c in api.posts() if c[1] == "/api/v5/trade/order"]), 1)   # sem segunda entrada

    def test_execucao_parcial_recalcula_risco_e_cancela_o_resto(self):
        api = FakeOKX(now=self.now, fill="parcial", ctval="0.1")
        self.corre(api)
        risco0 = json.load(open(os.path.join(self.d, "piloto_estado.json")))["aberta"]["risco_planeado"]
        st, _ = self.corre(api, now=self.now + 3600)
        self.assertLess(st["aberta"]["risco_planeado"], risco0)
        self.assertIn("/api/v5/trade/cancel-order", [c[1] for c in api.posts()])

    def test_entrada_nao_executada_e_cancelada_no_prazo(self):
        api = FakeOKX(now=self.now, fill="nenhum")
        self.corre(api)
        st, msgs = self.corre(api, now=self.now + P.PRAZO_ENTRADA_S + 10)
        self.assertIsNone(st["aberta"])
        self.assertIn("/api/v5/trade/cancel-order", [c[1] for c in api.posts()])

    def test_falha_do_stop_fecha_e_bloqueia(self):
        api = FakeOKX(now=self.now, algo_ok=False)
        self.corre(api)
        st, msgs = self.corre(api, now=self.now + 3600)
        self.assertIn("/api/v5/trade/close-position", [c[1] for c in api.posts()])
        self.assertTrue(st["bloqueio"])
        self.assertTrue(any("bloqueei o piloto" in m for m in msgs))

    def test_falha_da_api_nao_envia_ordens(self):
        api = FakeOKX(now=self.now)
        api.priv = lambda *a, **k: {"code": "50001", "data": []}
        st, _ = self.corre(api)
        self.assertFalse(st["portas"]["conta_usdc"]["ok"])

    # ---------------- limites e reinicios ----------------
    def test_perda_diaria_suspensao_e_encerramento(self):
        st = P.estado_inicial()
        now = self.now
        st["dias"][__import__("time").strftime("%Y-%m-%d", __import__("time").gmtime(now))] = -1.0
        st["perda_realizada"] = -1.0
        _, acoes = P.aplicar_limites(st, CFG, 0.0, now)
        self.assertIn("cancelar_entradas", acoes)
        self.assertFalse(st["suspenso"])
        st["perda_realizada"] = -2.5
        _, acoes = P.aplicar_limites(st, CFG, -0.6, now)             # realizada + nao realizada = 3,1
        self.assertTrue(st["suspenso"])
        st["perda_realizada"] = -4.0
        _, acoes = P.aplicar_limites(st, CFG, -1.2, now)
        self.assertTrue(st["bloqueio"])
        self.assertIn("fechar_posicao", acoes)

    def test_bloqueio_sobrevive_a_reinicio(self):
        api = FakeOKX(now=self.now)
        st = P.estado_inicial()
        st["bloqueio"] = {"t": 1, "motivo": "perda acumulada 5 USDC: piloto encerrado"}
        json.dump(st, open(os.path.join(self.d, "piloto_estado.json"), "w"))
        st2, _ = self.corre(api)
        self.assertTrue(st2["bloqueio"])
        self.assertFalse(st2["portas"]["bloqueio"]["ok"])
        self.assertEqual(api.posts(), [])

    def test_mesmo_sinal_nao_entra_duas_vezes_apos_reinicio(self):
        api = FakeOKX(now=self.now, fill="nenhum")
        self.corre(api)
        self.corre(api, now=self.now + P.PRAZO_ENTRADA_S + 10)        # cancelada no prazo
        st, _ = self.corre(api, now=self.now + P.PRAZO_ENTRADA_S + 20)  # mesmo fecho de 4H
        self.assertEqual(len([c for c in api.posts() if c[1] == "/api/v5/trade/order"]), 1)

    def test_simulacao_integral_sem_ordens(self):
        api = FakeOKX(now=self.now)
        st, msgs = self.corre(api, simular=True)
        self.assertEqual(api.posts(), [])
        self.assertTrue(any("simulação" in m for m in msgs))
        self.assertEqual(st["ops"][0]["estado"], "simulada (sem ordem)")

    # ---------------- isolamento ----------------
    def test_so_endpoints_e_instrumentos_do_piloto(self):
        api = FakeOKX(now=self.now)
        self.corre(api)
        self.corre(api, now=self.now + 3600)
        for metodo, path, corpo in api.posts():
            self.assertIn(path, ("/api/v5/account/set-leverage", "/api/v5/trade/order", "/api/v5/trade/order-algo",
                                 "/api/v5/trade/cancel-order", "/api/v5/trade/close-position"))
            self.assertEqual(corpo.get("instId"), INST["inst"])
            if "mgnMode" in corpo or "tdMode" in corpo:
                self.assertEqual(corpo.get("mgnMode") or corpo.get("tdMode"), "isolated")
        src = open(P.__file__, encoding="utf-8").read()
        for proibido in ("set-position-mode", "set-account-level", "asset/transfer", "withdrawal", "\"okx_config.json",
                         "config.json\", \"w", "set-leverage\", {\"instId\": None"):
            self.assertNotIn(proibido, src)

    def test_executor_existente_nao_esta_isolado_hoje(self):
        """O executor OKX existente adota posicoes que nao segue: enquanto nao declarar PILOTO_ISOLADO, a porta
        de isolamento fica fechada (e este piloto NAO o altera)."""
        import okx_exec
        self.assertFalse(getattr(okx_exec, "PILOTO_ISOLADO", False))
        self.assertFalse(P._okx_exec_isolado())

    def test_config_de_producao_do_piloto(self):
        c = json.load(open(P.CFG_FICHEIRO))
        self.assertEqual((c["capital_max"], c["perda_max"], c["risco_max_op"], c["nocional_max"], c["alav_max"],
                          c["posicoes_max"], c["perda_diaria_max"], c["suspender_em"], c["margem"], c["lado"],
                          c["estrategia"]), (10.0, 5.0, 0.25, 10.0, 5, 1, 1.0, 3.0, "isolated", "LONG", "e495d11739f6"))


if __name__ == "__main__":
    unittest.main()
