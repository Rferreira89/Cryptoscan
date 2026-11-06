"""(06/11, P1) Executor de SHORT da OKX (preparacao isolada). Duas partes:
1) INTERRUPTOR: com SHORT_REAL_PERMITIDO = False nenhum pedido de escrita chega ao transporte, com qualquer config;
2) LOGICA (num laboratorio: interruptor ligado SO dentro do teste e uma corretora falsa em memoria): entrada SELL,
   stop acima, OCO reduce-only, parciais, cancelamentos, caducidade, recusas, falhas de comunicacao e duplicacao."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import okx_short as S  # noqa: E402
from engine import multiestrategia as M  # noqa: E402

AGORA = 1_800_000_000
INFO = {"ctVal": 1.0, "minSz": 0.1, "lotSz": 0.1, "alav_max": 20}
REG = {"corretora": "okx", "tetos": {"bruta_max": 3.0, "risco_aberto_max": 6.0},
       "estrategias": {"tfs": {"estado": "papel", "fracao": 1.0, "risco_pct": 0.5, "max_pos": 5, "bruta_max": 0.5, "alav_max": 2},
                       "h46": {"estado": "real", "real": True, "fracao": 1.0, "risco_pct": 1.0, "max_pos": 30, "bruta_max": 3, "alav_max": 10}}}
SINAL = {"id": "DOGE-tfs-20261106", "moeda": "DOGE", "inst": "DOGE-USD_UM_XPERP-1", "px": 0.0716, "t_px": AGORA - 5,
         "stop": 0.0824, "objetivo": 0.0600, "t_sinal": 1793923200}


class Corretora:
    """OKX falsa: guarda ordens por clOrdId; o teste controla estado, preenchimento, recusas e falhas de rede."""
    def __init__(self):
        self.pedidos, self.ordens, self.algos = [], {}, {}
        self.falhar_rede, self.recusar = set(), {}
        self.n = 0

    def __call__(self, metodo, path, corpo=None):
        self.pedidos.append((metodo, path, corpo))
        chave = path.split("?")[0]
        if chave in self.falhar_rede:
            raise TimeoutError("rede")
        if chave in self.recusar:
            return {"code": self.recusar[chave], "msg": "recusada", "data": []}
        if metodo == "POST" and chave == "/api/v5/trade/order":
            self.n += 1
            self.ordens[corpo["clOrdId"]] = {"ordId": str(self.n), "state": "live", "accFillSz": "0", "corpo": corpo}
            return {"code": "0", "data": [{"ordId": str(self.n)}]}
        if metodo == "POST" and chave == "/api/v5/trade/order-algo":
            self.n += 1
            self.algos[str(self.n)] = corpo
            return {"code": "0", "data": [{"algoId": str(self.n)}]}
        if metodo == "POST" and chave == "/api/v5/trade/cancel-algos":
            for a in corpo:
                self.algos.pop(a["algoId"], None)
            return {"code": "0", "data": []}
        if metodo == "POST" and chave == "/api/v5/trade/cancel-order":
            self.ordens[corpo["clOrdId"]]["state"] = "canceled"
            return {"code": "0", "data": []}
        if metodo == "GET" and chave == "/api/v5/trade/order":
            cl = path.split("clOrdId=")[1]
            o = self.ordens.get(cl)
            if not o:
                return {"code": "51603", "msg": "Order does not exist", "data": []}
            return {"code": "0", "data": [{"state": o["state"], "accFillSz": o["accFillSz"]}]}
        return {"code": "0", "data": []}

    def escritas(self):
        return [p for p in self.pedidos if p[0] != "GET"]


def plano(**kw):
    s = dict(SINAL, **kw)
    return S.planear(s, 20.0, 20.0, INFO, REG, [], {}, AGORA)


class Interruptor(unittest.TestCase):
    def test_constante_desligada_no_codigo(self):
        self.assertIs(S.SHORT_REAL_PERMITIDO, False)

    def test_nada_chega_a_corretora_mesmo_com_a_config_ligada(self):
        for cfg in ({}, {"short_real": True}, {"short_real": "sim"}):
            c = Corretora(); est = {}
            op = S.abrir(c, cfg, plano(), est, AGORA)
            self.assertEqual(op["estado"], "bloqueada")
            self.assertEqual(c.escritas(), [], cfg)                      # nem alavancagem, nem ordem
            with self.assertRaises(S.EnvioBloqueado):
                S.fechar(c, cfg, dict(op, algoId="9", preenchido=1.0))
            self.assertEqual(c.escritas(), [])

    def test_so_leituras_passam(self):
        c = Corretora()
        with self.assertRaises(S.Recusa):                                 # a leitura chegou (e a ordem nao existe)
            S._enviar(c, {"short_real": True}, "GET", "/api/v5/trade/order?instId=X&clOrdId=y")
        self.assertEqual(len(c.pedidos), 1)
        for metodo, path in (("POST", "/api/v5/trade/order"), ("POST", "/api/v5/account/set-leverage"), ("DELETE", "/qualquer")):
            with self.assertRaises(S.EnvioBloqueado):
                S._enviar(c, {"short_real": True}, metodo, path, {})
        self.assertEqual(len(c.pedidos), 1)

    def test_precisa_dos_dois_interruptores(self):
        with mock.patch.object(S, "SHORT_REAL_PERMITIDO", True):
            self.assertFalse(S.real_permitido({}))
            self.assertTrue(S.real_permitido({"short_real": True}))
        self.assertFalse(S.real_permitido({"short_real": True}))


class Planeamento(unittest.TestCase):
    def test_plano_valido(self):
        p = plano()
        self.assertTrue(p["ok"]); self.assertGreater(p["stop"], p["px"]); self.assertLess(p["objetivo"], p["px"])
        self.assertEqual(M.dono(p["cl_id"]), "tfs"); self.assertLessEqual(p["alav"], 2)
        self.assertLessEqual(p["risco_usd"], 0.5 / 100 * 20 + 1e-9)
        self.assertEqual(plano()["cl_id"], p["cl_id"])                   # o mesmo sinal -> o mesmo clOrdId

    def test_recusas_de_planeamento(self):
        self.assertIn("stop", plano(stop=0.07)["motivo"])
        self.assertIn("objetivo", plano(objetivo=0.08)["motivo"])
        self.assertIn("desatualizados", plano(t_px=AGORA - 3600)["motivo"])
        self.assertIn("minimo", S.planear(SINAL, 20.0, 20.0, dict(INFO, minSz=1000, lotSz=1000), REG, [], {}, AGORA)["motivo"])
        self.assertIn("h46", S.planear(SINAL, 20.0, 20.0, INFO, REG, [], {SINAL["inst"]: "h46"}, AGORA)["motivo"])
        cheio = [{"cod": "tfs", "nocional": 9.9, "risco_usd": 0.1}]
        self.assertIn("exposicao", S.planear(SINAL, 20.0, 20.0, INFO, REG, cheio, {}, AGORA)["motivo"])
        self.assertIn("registada", S.planear(dict(SINAL, cod="xyz"), 20.0, 20.0, INFO, REG, [], {}, AGORA)["motivo"])


class Laboratorio(unittest.TestCase):
    """Interruptor ligado SO aqui dentro, com a corretora falsa (nenhum transporte real existe no modulo)."""
    CFG = {"short_real": True}

    def setUp(self):
        p = mock.patch.object(S, "SHORT_REAL_PERMITIDO", True); p.start(); self.addCleanup(p.stop)
        self.c = Corretora(); self.est = {}; self.p = plano()

    def test_entrada_sell_isolada_com_alavancagem_minima(self):
        op = S.abrir(self.c, self.CFG, self.p, self.est, AGORA)
        self.assertEqual(op["estado"], "pendente")
        lev, ordem = self.c.escritas()
        self.assertEqual(lev[1], "/api/v5/account/set-leverage"); self.assertEqual(lev[2]["lever"], str(self.p["alav"]))
        self.assertEqual((ordem[2]["side"], ordem[2]["tdMode"], ordem[2]["ordType"]), ("sell", "isolated", "limit"))

    def test_nao_duplica(self):
        S.abrir(self.c, self.CFG, self.p, self.est, AGORA)
        S.abrir(self.c, self.CFG, self.p, self.est, AGORA + 60)
        self.assertEqual(sum(1 for x in self.c.escritas() if x[1] == "/api/v5/trade/order"), 1)

    def test_preenchida_fica_protegida_com_oco_de_compra_reduce_only(self):
        op = S.abrir(self.c, self.CFG, self.p, self.est, AGORA)
        self.c.ordens[op["cl_id"]].update(state="filled", accFillSz=str(op["sz"]))
        self.assertEqual(S.acompanhar(self.c, self.CFG, op, AGORA + 60), "aberta")
        a = list(self.c.algos.values())[0]
        self.assertEqual((a["side"], a["reduceOnly"], a["ordType"]), ("buy", "true", "oco"))
        self.assertGreater(float(a["slTriggerPx"]), op["px"]); self.assertLess(float(a["tpTriggerPx"]), op["px"])
        self.assertEqual(float(a["sz"]), op["sz"])

    def test_sem_objetivo_usa_stop_condicional(self):
        p = plano(objetivo=None)
        op = S.abrir(self.c, self.CFG, p, self.est, AGORA)
        self.c.ordens[op["cl_id"]].update(state="filled", accFillSz=str(op["sz"]))
        S.acompanhar(self.c, self.CFG, op, AGORA + 60)
        self.assertEqual(list(self.c.algos.values())[0]["ordType"], "conditional")

    def test_parcial_protege_o_preenchido_e_cresce(self):
        op = S.abrir(self.c, self.CFG, self.p, self.est, AGORA)
        self.c.ordens[op["cl_id"]].update(state="partially_filled", accFillSz="0.5")
        self.assertEqual(S.acompanhar(self.c, self.CFG, op, AGORA + 60), "parcial")
        self.assertEqual(float(list(self.c.algos.values())[0]["sz"]), 0.5)
        self.c.ordens[op["cl_id"]].update(accFillSz="0.8")
        S.acompanhar(self.c, self.CFG, op, AGORA + 120)
        self.assertEqual(len(self.c.algos), 1)                            # a protecao antiga foi trocada
        self.assertEqual(float(list(self.c.algos.values())[0]["sz"]), 0.8)

    def test_caducada_sem_preenchimento_cancela(self):
        op = S.abrir(self.c, self.CFG, self.p, self.est, AGORA)
        self.assertEqual(S.acompanhar(self.c, self.CFG, op, op["valido_ate"] + 1), "cancelada")
        self.assertEqual(self.c.ordens[op["cl_id"]]["state"], "canceled")

    def test_caducada_parcial_cancela_o_resto_e_fica_protegida(self):
        op = S.abrir(self.c, self.CFG, self.p, self.est, AGORA)
        self.c.ordens[op["cl_id"]].update(state="partially_filled", accFillSz="0.3")
        self.assertEqual(S.acompanhar(self.c, self.CFG, op, op["valido_ate"] + 1), "aberta")
        self.assertIn("restante cancelado", op["motivo"]); self.assertEqual(float(list(self.c.algos.values())[0]["sz"]), 0.3)

    def test_cancelada_na_corretora(self):
        op = S.abrir(self.c, self.CFG, self.p, self.est, AGORA)
        self.c.ordens[op["cl_id"]]["state"] = "canceled"
        self.assertEqual(S.acompanhar(self.c, self.CFG, op, AGORA + 60), "cancelada")

    def test_ordem_recusada(self):
        self.c.recusar["/api/v5/trade/order"] = "51008"                 # margem insuficiente
        op = S.abrir(self.c, self.CFG, self.p, self.est, AGORA)
        self.assertEqual(op["estado"], "recusada"); self.assertIn("51008", op["motivo"])
        self.assertEqual(S.acompanhar(self.c, self.CFG, op, AGORA + 60), "recusada")

    def test_falha_de_rede_no_envio_reconcilia_sem_reenviar(self):
        self.c.falhar_rede.add("/api/v5/trade/order")
        op = S.abrir(self.c, self.CFG, self.p, self.est, AGORA)
        self.assertEqual(op["estado"], "incerto")
        self.c.falhar_rede.clear()
        S.abrir(self.c, self.CFG, self.p, self.est, AGORA + 60)          # novo pedido do mesmo sinal: nao reenvia
        self.assertEqual(sum(1 for x in self.c.escritas() if x[1] == "/api/v5/trade/order"), 1)
        self.assertEqual(S.acompanhar(self.c, self.CFG, op, AGORA + 120), "cancelada")   # a corretora nao a tem
        self.assertIn("reconciliado", op["motivo"])

    def test_falha_de_rede_no_envio_mas_a_ordem_chegou(self):
        self.c.falhar_rede.add("/api/v5/trade/order")
        op = S.abrir(self.c, self.CFG, self.p, self.est, AGORA)
        self.c.ordens[op["cl_id"]] = {"ordId": "77", "state": "filled", "accFillSz": str(op["sz"])}   # chegou de facto
        self.c.falhar_rede.clear()
        self.assertEqual(S.acompanhar(self.c, self.CFG, op, AGORA + 60), "aberta")
        self.assertEqual(len(self.c.algos), 1)

    def test_falha_de_rede_ao_acompanhar_nao_muda_nada(self):
        op = S.abrir(self.c, self.CFG, self.p, self.est, AGORA)
        self.c.falhar_rede.add("/api/v5/trade/order")
        self.assertEqual(S.acompanhar(self.c, self.CFG, op, AGORA + 60), "pendente")
        self.assertIn("sem comunicacao", op["aviso"])

    def test_falha_ao_proteger_fica_aviso_e_repete(self):
        op = S.abrir(self.c, self.CFG, self.p, self.est, AGORA)
        self.c.ordens[op["cl_id"]].update(state="filled", accFillSz=str(op["sz"]))
        self.c.falhar_rede.add("/api/v5/trade/order-algo")
        S.acompanhar(self.c, self.CFG, op, AGORA + 60)
        self.assertIn("sem comunicacao", op["aviso"]); self.assertFalse(self.c.algos)
        self.c.falhar_rede.clear()
        S.acompanhar(self.c, self.CFG, op, AGORA + 120)
        self.assertEqual(len(self.c.algos), 1)

    def test_fechar_cancela_protecao_e_compra_reduce_only(self):
        op = S.abrir(self.c, self.CFG, self.p, self.est, AGORA)
        self.c.ordens[op["cl_id"]].update(state="filled", accFillSz=str(op["sz"]))
        S.acompanhar(self.c, self.CFG, op, AGORA + 60)
        S.fechar(self.c, self.CFG, op)
        self.assertFalse(self.c.algos)
        ult = self.c.escritas()[-1][2]
        self.assertEqual((ult["side"], ult["reduceOnly"], ult["ordType"]), ("buy", "true", "market"))
        self.assertEqual(op["estado"], "fechada")


class Isolamento(unittest.TestCase):
    def test_nao_ligado_ao_agente_nem_ao_okx_exec(self):
        raiz = os.path.join(os.path.dirname(__file__), "..")
        for f in ("tools/okx_agente.py", "tools/okx_exec.py"):
            self.assertNotIn("okx_short", open(os.path.join(raiz, f), encoding="utf-8").read())
        src = open(S.__file__, encoding="utf-8").read()
        self.assertNotIn("import okx_exec", src); self.assertNotIn("urllib", src); self.assertNotIn("OKX_API", src)


if __name__ == "__main__":
    unittest.main()
