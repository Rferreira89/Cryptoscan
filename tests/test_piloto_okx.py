"""(17/11) Piloto real OKX: promocao so com criterios conferidos, LONG e SHORT, limites (20 USDC, 0,25 por operacao,
5x-10x, 1/3/5 USDC), ordens, stops, execucoes parciais, reinicios, orfas e isolamento - com uma OKX falsa (nenhum
pedido sai daqui)."""
import copy
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import piloto_okx as P  # noqa: E402

INST = "ABC-USD_UM_XPERP-310404"
CFG = json.load(open(P.CFG_FICHEIRO))
NOW0 = 1_800_000_000 // 1800 * 1800 + 660          # 11 min depois de um fecho de 30 min


def estrategia(eid="aaa111", lado="LONG", **kw):
    e = {"id": eid, "versao": eid, "estado": "APPROVED_REAL", "lado": lado, "tf": "1H", "regimes": None,
         "oos": {"n": 150, "acontecimentos": 60, "dias": 40, "r_medio": 0.2, "profit_factor": 1.5, "p_holm": 0.01,
                 "ic95_acontecimento": [0.05, 0.35], "custo_medio_r": 0.05,
                 "robustez": {k: 0.1 for k in P.ROBUSTEZ}, "concentracao": {"moeda": 0.2, "acontecimento": 0.1, "dia": 0.1}},
         "papel": {"fechadas": 40, "acontecimentos": 35, "dias": 20, "r_medio": 0.15, "falhas_criticas": 0}}
    for k, v in kw.items():
        if isinstance(v, dict) and isinstance(e.get(k), dict):
            e[k].update(v)
        else:
            e[k] = v
    return e


def registo(*es, t=NOW0):
    return {"t": t, "estrategias": {e["id"]: e for e in es}}


def sinal(eid="aaa111", lado="LONG", base="ABC", t_fecho=NOW0 - 660, tf="1H", **kw):
    o = {"id_op": f"{eid}|{base}|{t_fecho - 3600}", "estrategia": eid, "b": base, "inst": INST, "lado": lado, "tf": tf,
         "t_sinal": t_fecho - P.TF_S[tf], "atr_ref": 0.01, "saida": {"tipo": "fixa", "k": 2.0, "tp": 2.0, "hold": 4},
         "regime": "lateral", "decisao": {"fecho": 1.0}, "aberta_em": t_fecho + 75}
    o.update(kw)
    return o


def papel(*abertas, fechadas=(), t=NOW0):
    return {"t": t, "abertas": list(abertas), "fechadas": list(fechadas)}


class FakeOKX:
    def __init__(self, settle="USDC", perm="read_only,trade", saldo=30.0, fill="filled", algo_ok=True, bid=0.9995,
                 ask=1.0005, contas=(INST,), lever="20", ctval="1", minsz="1", outro=None, falha=(), pnl=-0.1):
        self.settle, self.perm, self.saldo, self.fill, self.algo_ok = settle, perm, saldo, fill, algo_ok
        self.bid, self.ask, self.contas, self.lever, self.ctval, self.minsz = bid, ask, list(contas), lever, ctval, minsz
        self.outro, self.falha, self.pnl = outro, set(falha), pnl
        self.chamadas, self.pos, self.ordem, self.algos, self.historico, self.fills = [], None, None, [], [], []

    def pub(self, path, params=None):
        self.chamadas.append(("PUB", path, params))
        if "instruments" in path:
            return [{"instId": INST, "state": "live", "ctType": "linear", "instCategory": "1", "ruleType": "xperp",
                     "ctVal": self.ctval, "ctMult": "1", "ctValCcy": "ABC", "lotSz": "1", "minSz": self.minsz,
                     "tickSz": "0.0001", "lever": self.lever}]
        if "tickers" in path:
            return [{"instId": INST, "bidPx": str(self.bid), "askPx": str(self.ask), "last": "1.0", "volCcy24h": "1000000"}]
        if "funding-rate" in path:
            return [{"fundingRate": "0.0001"}]
        return []

    def _ok(self, data):
        return {"code": "0", "data": data}

    def priv(self, metodo, path, corpo=None):
        self.chamadas.append((metodo, path, corpo))
        base = path.split("?")[0].rsplit("/", 1)[-1]
        if base in self.falha:
            return {"code": "50001", "data": []}
        if base == "config":
            return self._ok([{"settleCcy": self.settle, "perm": self.perm, "posMode": "net_mode", "acctLv": "2"}])
        if base == "balance":
            return self._ok([{"details": [{"ccy": "USDC", "availBal": str(self.saldo)}]}])
        if base == "instruments":
            return self._ok([{"instId": i} for i in self.contas])
        if base == "set-leverage":
            return self._ok([{}])
        if base == "order" and metodo == "POST":
            self.ordem = dict(corpo, ordId="777")
            return self._ok([{"ordId": "777", "sCode": "0"}])
        if base == "order":
            if "clOrdId=" in path:
                return self._ok([]) if not self.ordem else self._ok([{"ordId": "777"}])
            if self.fill == "nenhum" or not self.ordem:
                return self._ok([{"state": "live", "accFillSz": "0"}])
            sz = float(self.ordem["sz"])
            acc = sz if self.fill == "filled" else float(max(1, int(sz // 2)))
            if self.pos is None and not self.historico:
                self.pos = {"pos": str(acc if self.ordem["side"] == "buy" else -acc), "upl": "-0.05", "instId": INST,
                            "posId": "p1", "cTime": "1"}
                self.fills.append({"instId": INST, "clOrdId": self.ordem["clOrdId"], "ts": "2"})
                if self.algo_ok:
                    a = self.ordem["attachAlgoOrds"][0]
                    self.algos = [{"slTriggerPx": a["slTriggerPx"], "sz": str(acc), "algoClOrdId": a["attachAlgoClOrdId"],
                                   "side": "sell" if self.ordem["side"] == "buy" else "buy", "ordType": "oco"}]
            return self._ok([{"state": "filled" if self.fill == "filled" else "partially_filled", "accFillSz": str(acc),
                              "avgPx": self.ordem["px"], "fillTime": "1000"}])
        if base == "positions":
            if "instType" in path:
                return self._ok(([self.pos] if self.pos else []) + ([self.outro] if self.outro else []))
            if self.outro and self.outro["instId"] in path:
                return self._ok([self.outro])
            return self._ok([self.pos] if self.pos else [])
        if base == "orders-pending":
            return self._ok([])
        if base == "orders-algo-pending":
            return self._ok([a for a in self.algos if INST in path] if "oco" in path else [])
        if base in ("fills", "fills-history"):
            return self._ok([x for x in self.fills if "instId=" not in path or x["instId"] in path])
        if base == "positions-history":
            return self._ok(self.historico)
        if base == "order-algo":
            return self._ok([{}]) if self.algo_ok else {"code": "51000", "data": [{}]}
        if base == "cancel-order":
            return self._ok([{}])
        if base == "close-position":
            if self.pos:
                self.historico.append({"posId": self.pos["posId"], "instId": INST, "realizedPnl": str(self.pnl),
                                       "closeAvgPx": "1.0", "cTime": "1", "uTime": str(10 ** 13)})
            self.pos, self.algos = None, []
            return self._ok([{}])
        raise AssertionError(path)

    def posts(self, nome=None):
        return [c for c in self.chamadas if c[0] == "POST" and (nome is None or c[1].endswith(nome))]


class Base(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def corre(self, api, reg=None, pap=None, now=NOW0, **kw):
        kw.setdefault("isolado", True)
        kw.setdefault("cifra_ok", True)
        reg = reg if reg is not None else registo(estrategia())
        pap = pap if pap is not None else papel(sinal())
        reg, pap = copy.deepcopy(reg), copy.deepcopy(pap)
        reg["t"], pap["t"] = now, now
        return P.ciclo(api, self.d, now=now, registo=reg, papel=pap, **kw)


class Criterios(Base):
    def test_estrategia_qualificada_passa_a_conferencia(self):
        ok, f = P.criterios_reais(estrategia())
        self.assertTrue(ok, f)

    def test_qualquer_criterio_falhado_ou_em_falta_bloqueia(self):
        casos = [{"oos": {"n": 99}}, {"oos": {"acontecimentos": 29}}, {"oos": {"dias": 29}}, {"oos": {"r_medio": -0.01}},
                 {"oos": {"profit_factor": 1.19}}, {"oos": {"p_holm": 0.06}}, {"oos": {"ic95_acontecimento": [-0.01, 0.3]}},
                 {"oos": {"robustez": {"custos_mais_25pct": -0.01}}}, {"oos": {"concentracao": {"moeda": 0.6}}},
                 {"papel": {"fechadas": 29}}, {"papel": {"dias": 13}}, {"papel": {"r_medio": 0}},
                 {"papel": {"falhas_criticas": 1}}, {"estado": "PAPER_TRADING"}, {"estado": "SUSPENDED"}]
        for kw in casos:
            ok, f = P.criterios_reais(estrategia(**copy.deepcopy(kw)))
            self.assertFalse(ok, kw)
        e = estrategia()
        del e["oos"]["robustez"]
        self.assertFalse(P.criterios_reais(e)[0])

    def test_v2_rejeitada_nunca_passa(self):
        self.assertFalse(P.criterios_reais(estrategia(eid=P.V2_REJEITADA, id=P.V2_REJEITADA))[0])

    def test_estrategia_negativa_nunca_chega_a_ordem(self):
        api = FakeOKX()
        st, msgs = self.corre(api, reg=registo(estrategia(oos={"r_medio": -0.2})))
        self.assertEqual(api.posts(), [])
        self.assertFalse(st["portas"]["estrategias_elegiveis"]["ok"])


class Dimensionamento(Base):
    def pl(self, e=1.0, st=0.98, lado="LONG"):
        return {"entrada": e, "stop": st, "alvo": None, "lado": lado}

    def spec(self, **kw):
        return {"ctVal": "1", "ctMult": "1", "ctValCcy": "ABC", "lotSz": "1", "minSz": "1", "lever": "20", **kw}

    def test_risco_025_incluindo_custos_e_nocional_20(self):
        for st in (0.98, 0.999, 0.9):
            d, _ = P.dimensionar(self.pl(st=st), self.spec(), CFG, 0.05, saldo=20)
            self.assertLessEqual(d["risco_total"], 0.25 + 1e-9)
            self.assertLessEqual(d["nocional"], 20 + 1e-9)

    def test_alavancagem_entre_5_e_10(self):
        d, _ = P.dimensionar(self.pl(st=0.999), self.spec(), CFG, 0.05, saldo=20)
        self.assertEqual(d["alav"], 5)                                # referencia 5x
        d, _ = P.dimensionar(self.pl(st=0.999), self.spec(), CFG, 0.05, saldo=3)
        self.assertGreater(d["alav"], 5)
        self.assertLessEqual(d["alav"], 10)                           # sobe so pela margem
        d, porque = P.dimensionar(self.pl(st=0.999), self.spec(), CFG, 0.05, saldo=1.5)
        self.assertIsNone(d)
        self.assertIn("10x", porque)
        d, porque = P.dimensionar(self.pl(), self.spec(lever="3"), CFG, 0.05, saldo=20)
        self.assertIsNone(d)                                          # instrumento abaixo de 5x
        self.assertIn("instrumento", porque)

    def test_minimo_do_contrato_rejeita(self):
        d, porque = P.dimensionar(self.pl(), self.spec(ctVal="100"), CFG, 0.05, saldo=20)
        self.assertIsNone(d)
        self.assertIn("tamanho minimo", porque)

    def test_short_e_custos(self):
        d, _ = P.dimensionar(self.pl(st=1.02, lado="SHORT"), self.spec(), CFG, 0.05, saldo=20, funding_8h=-0.001)
        d0, _ = P.dimensionar(self.pl(st=1.02, lado="SHORT"), self.spec(), CFG, 0.05, saldo=20, funding_8h=0.001)
        self.assertLessEqual(d["contratos"], d0["contratos"])          # funding negativo custa ao SHORT
        self.assertIsNone(P.dimensionar(self.pl(st=0.98, lado="SHORT"), self.spec(), CFG, 0.05)[0])

    def test_config_de_producao(self):
        self.assertEqual((CFG["capital_max"], CFG["nocional_max"], CFG["perda_max"], CFG["suspender_em"],
                          CFG["perda_diaria_max"], CFG["risco_max_op"], CFG["alav_min"], CFG["alav_max"],
                          CFG["posicoes_max"], CFG["margem"], sorted(CFG["lados"])),
                         (20.0, 20.0, 5.0, 3.0, 1.0, 0.25, 5, 10, 1, "isolated", ["LONG", "SHORT"]))


class Ordens(Base):
    def test_long_isolado_com_stop_e_confirmacao(self):
        api = FakeOKX()
        st, msgs = self.corre(api)
        posts = api.posts()
        self.assertEqual([c[1].rsplit("/", 1)[-1] for c in posts], ["set-leverage", "order"])
        o = posts[1][2]
        self.assertEqual((o["tdMode"], o["side"], o["ordType"]), ("isolated", "buy", "limit"))
        self.assertTrue(o["clOrdId"].startswith("pil") and o["attachAlgoOrds"][0]["attachAlgoClOrdId"].startswith("pil"))
        self.assertTrue(5 <= int(posts[0][2]["lever"]) <= 10)
        self.assertEqual(posts[0][2]["mgnMode"], "isolated")
        self.assertEqual(st["aberta"]["estado"], "pendente")
        st, _ = self.corre(api, now=NOW0 + 900)
        self.assertEqual(st["aberta"]["estado"], "aberta")
        self.assertTrue(st["aberta"]["stop_confirmado"])
        self.assertEqual(len(api.posts("/trade/order")), 1)            # sem segunda entrada

    def test_short(self):
        api = FakeOKX()
        st, _ = self.corre(api, reg=registo(estrategia(lado="SHORT")), pap=papel(sinal(lado="SHORT")))
        o = api.posts("/trade/order")[0][2]
        self.assertEqual(o["side"], "sell")
        self.assertGreater(float(o["attachAlgoOrds"][0]["slTriggerPx"]), float(o["px"]))
        st, _ = self.corre(api, reg=registo(estrategia(lado="SHORT")), pap=papel(sinal(lado="SHORT")), now=NOW0 + 900)
        self.assertTrue(st["aberta"]["stop_confirmado"])

    def test_execucao_parcial(self):
        api = FakeOKX(ctval="0.1", fill="parcial")
        self.corre(api)
        r0 = json.load(open(os.path.join(self.d, "piloto_estado.json")))["aberta"]["risco_planeado"]
        st, _ = self.corre(api, now=NOW0 + 900)
        self.assertLess(st["aberta"]["risco_planeado"], r0)
        self.assertTrue(api.posts("cancel-order"))

    def test_nao_executada_cancela_no_prazo(self):
        api = FakeOKX(fill="nenhum")
        self.corre(api)
        st, _ = self.corre(api, now=NOW0 + P.PRAZO_ENTRADA_S + 1)
        self.assertIsNone(st["aberta"])
        self.assertTrue(api.posts("cancel-order"))

    def test_falha_do_stop_fecha_e_bloqueia(self):
        api = FakeOKX(algo_ok=False)
        self.corre(api)
        st, msgs = self.corre(api, now=NOW0 + 900)
        self.assertTrue(api.posts("close-position"))
        self.assertTrue(st["bloqueio"])

    def test_saida_por_tempo_e_contas_pela_okx(self):
        api = FakeOKX(pnl=-0.2)
        self.corre(api)
        self.corre(api, now=NOW0 + 900)
        st, _ = self.corre(api, now=NOW0 + 900 + 4 * 3600 + 60)
        self.assertTrue(api.posts("close-position"))
        st, _ = self.corre(api, now=NOW0 + 900 + 4 * 3600 + 960)
        op = st["ops"][-1]
        self.assertEqual(op["estado"], "fechada")
        self.assertAlmostEqual(op["pnl_liquido"], -0.2)
        self.assertLess(op["r"], 0)

    def test_espelho_do_fecho_do_papel(self):
        api = FakeOKX()
        s = sinal()
        self.corre(api, pap=papel(s))
        self.corre(api, pap=papel(s), now=NOW0 + 900)
        st, _ = self.corre(api, pap=papel(fechadas=[dict(s, r=-1.0, motivo="stop")]), now=NOW0 + 1800)
        self.assertTrue(api.posts("close-position"))
        self.assertIn("espelho", st["ops"][-1]["motivo_saida"])


class Portas(Base):
    def test_portas_bloqueiam(self):
        casos = [({"settle": "USD"}, {}, "conta_usdc"), ({"perm": "read_only,trade,withdraw"}, {}, "sem_levantamentos"),
                 ({"saldo": 1.0}, {}, "saldo_usdc"), ({}, {"isolado": False}, "isolamento"),
                 ({}, {"cifra_ok": False}, "estado_cifrado"), ({"falha": ("balance",)}, {}, "api_fiavel")]
        for kw_api, kw, porta in casos:
            shutil.rmtree(self.d)
            os.makedirs(self.d)
            api = FakeOKX(**kw_api)
            st, msgs = self.corre(api, **kw)
            self.assertFalse(st["portas"][porta]["ok"], porta)
            self.assertEqual(api.posts(), [], porta)
            if porta not in ("saldo_usdc", "api_fiavel"):                              # sem margem o dimensionamento ja recusa antes
                self.assertTrue(any("portas fechadas" in m for m in msgs), porta)

    def test_dados_velhos_bloqueiam(self):
        api = FakeOKX()
        reg, pap = registo(estrategia()), papel(sinal())
        st, _ = P.ciclo(api, self.d, now=NOW0, registo=dict(reg, t=NOW0 - 7 * 3600), papel=pap, isolado=True, cifra_ok=True)
        self.assertFalse(st["portas"]["dados_frescos"]["ok"])
        self.assertEqual(api.posts(), [])

    def test_config_inativa(self):
        with mock.patch.object(P, "cfg", return_value=dict(CFG, ativo=False)):
            api = FakeOKX()
            st, _ = self.corre(api)
        self.assertEqual(api.posts(), [])

    def test_sinais_perdidos_com_causa(self):
        casos = [(dict(t_fecho=NOW0 - 3000), "min depois"), (dict(regime="queda"), "regime"),
                 (dict(decisao={"fecho": 1.05}), "fugiu")]
        for kw, txt in casos:
            shutil.rmtree(self.d)
            os.makedirs(self.d)
            api = FakeOKX()
            st, _ = self.corre(api, reg=registo(estrategia(regimes=["lateral", "subida"])), pap=papel(sinal(**kw)))
            self.assertEqual(api.posts(), [], txt)
            self.assertIn(txt, json.dumps(st["sinais_perdidos"], ensure_ascii=False), txt)

    def test_liquidez_e_contrato(self):
        for kw, txt in (({"bid": 0.98, "ask": 1.02}, "spread"), ({"contas": ()}, "negociavel"), ({"lever": "3"}, "instrumento")):
            shutil.rmtree(self.d)
            os.makedirs(self.d)
            api = FakeOKX(**kw)
            st, _ = self.corre(api)
            self.assertEqual(api.posts(), [], txt)
            self.assertIn(txt, json.dumps(st["sinais_perdidos"], ensure_ascii=False), txt)

    def test_melhor_oportunidade_e_uma_so_posicao(self):
        api = FakeOKX()
        a, b = estrategia("aaa111"), estrategia("bbb222", oos={"r_medio": 0.4})
        st, _ = self.corre(api, reg=registo(a, b), pap=papel(sinal("aaa111"), sinal("bbb222", base="ABC")))
        self.assertEqual(len(api.posts("/trade/order")), 1)
        self.assertEqual(st["aberta"]["estrategia"], "bbb222")


class Limites(Base):
    def test_diaria_suspensao_encerramento(self):
        st = P.estado_inicial()
        d = P._dia(NOW0)
        st["dias"][d], st["perda_realizada"] = -1.0, -1.0
        _, ac = P.aplicar_limites(st, CFG, 0.0, NOW0)
        self.assertIn("cancelar_entradas", ac)
        self.assertTrue(st["bloqueio_dia"][d])
        self.assertFalse(st["suspenso"])
        st["perda_realizada"] = -2.5
        P.aplicar_limites(st, CFG, -0.6, NOW0)
        self.assertTrue(st["suspenso"])
        st["perda_realizada"] = -4.0
        _, ac = P.aplicar_limites(st, CFG, -1.1, NOW0)
        self.assertTrue(st["bloqueio"])
        self.assertIn("fechar_posicao", ac)

    def test_perdas_da_okx_contam_mesmo_sem_estado(self):
        st = P.estado_inicial()
        p, _ = P.aplicar_limites(st, CFG, 0.0, NOW0, {"total": -5.2, "dias": {}})
        self.assertTrue(st["bloqueio"])

    def test_bloqueio_sobrevive_a_reinicio(self):
        api = FakeOKX()
        st = P.estado_inicial()
        st["bloqueio"] = {"t": 1, "motivo": "perda acumulada maxima atingida: piloto encerrado"}
        json.dump(st, open(os.path.join(self.d, "piloto_estado.json"), "w"))
        st2, _ = self.corre(api)
        self.assertTrue(st2["bloqueio"])
        self.assertEqual(api.posts(), [])

    def test_mesmo_sinal_nao_entra_duas_vezes(self):
        api = FakeOKX(fill="nenhum")
        self.corre(api)
        self.corre(api, now=NOW0 + P.PRAZO_ENTRADA_S + 1)
        self.corre(api, now=NOW0 + P.PRAZO_ENTRADA_S + 2)
        self.assertEqual(len(api.posts("/trade/order")), 1)

    def test_estado_perdido_nao_repete_ordem(self):
        api = FakeOKX(fill="nenhum")
        self.corre(api)
        os.remove(os.path.join(self.d, "piloto_estado.json"))
        self.corre(api, now=NOW0 + 60)
        self.assertEqual(len(api.posts("/trade/order")), 1)          # clOrdId ja existe na OKX

    def test_simulacao_integral_sem_ordens(self):
        api = FakeOKX()
        st, msgs = self.corre(api, simular=True)
        self.assertEqual(api.posts(), [])
        self.assertEqual(st["ops"][0]["estado"], "simulada (sem ordem)")
        self.assertTrue(any("simulação" in m for m in msgs))


class Isolamento(Base):
    def test_nao_abre_em_instrumento_de_outro_executor(self):
        api = FakeOKX(outro={"instId": INST, "pos": "3", "posId": "x", "cTime": "1"})
        st, _ = self.corre(api)
        self.assertEqual(api.posts(), [])
        self.assertIn("outro executor", json.dumps(st["sinais_perdidos"]))

    def test_posicao_do_executor_antigo_noutro_instrumento_nao_e_tocada(self):
        outro = {"instId": "ZZZ-USD_UM_XPERP-1", "pos": "3", "posId": "x", "cTime": "1"}
        api = FakeOKX(outro=outro)
        api.fills = [{"instId": "ZZZ-USD_UM_XPERP-1", "clOrdId": "csZZZ1", "ts": "5"}]
        self.corre(api)
        self.corre(api, now=NOW0 + 900)
        for metodo, path, corpo in api.posts():
            self.assertEqual(corpo.get("instId"), INST)

    def test_orfa_do_piloto_fecha_e_suspende(self):
        api = FakeOKX()
        api.pos = {"pos": "2", "instId": INST, "posId": "p9", "cTime": "1"}
        api.fills = [{"instId": INST, "clOrdId": "pilabc", "ts": "5"}]
        st, _ = self.corre(api, pap=papel())
        self.assertTrue(api.posts("close-position"))
        self.assertTrue(st["suspenso"])

    def test_so_endpoints_do_piloto_e_nada_global(self):
        src = open(P.__file__, encoding="utf-8").read()
        for proibido in ("set-position-mode", "set-account-level", "asset/transfer", "withdrawal", "\"okx_config.json",
                         "cancel-all", "mass-cancel"):
            self.assertNotIn(proibido, src)

    def test_publico_sem_valores_monetarios(self):
        api = FakeOKX()
        self.corre(api)
        self.corre(api, now=NOW0 + 900)
        txt = open(os.path.join(self.d, "piloto_publico.json"), encoding="utf-8").read()
        for k in ("risco_planeado", "nocional", "pnl_liquido", "_saldo_usdc", "contratos", "custos_estimados", "perda_realizada"):
            self.assertNotIn(f'"{k}"', txt, k)


def experimental(eid="exp111", lado="LONG", **kw):
    e = {"id": eid, "estado": "EXPERIMENTAL_REAL", "estado_estatistico": "PAPER_TRADING", "lado": lado, "tf": "1H",
         "definicao": {"tf": "1H", "lado": lado, "saida": {"tipo": "fixa", "k": 2.0, "tp": 2.0, "hold": 4}},
         "auditoria_tecnica": {"ok": True, "falhas": []}, "backtest": {"r_medio": 0.05}}
    e.update(kw)
    return e


def copy_doc(abertas=(), fechadas=(), t=NOW0):
    e = {"id": "copy:okx:T1", "versao": "copy:okx:T1", "estado": "EXPERIMENTAL_REAL", "lado": "AMBOS", "tf": "1H", "origem": "copy",
         "definicao": {"tf": "1H", "saida": {"tipo": "fixa", "k": 1.5, "tp": 2.0, "hold": 4}},
         "auditoria_tecnica": {"ok": True, "falhas": []}, "backtest": {"r_medio": 0.002}}
    return {"t": t, "estrategias": {e["id"]: e}, "abertas": list(abertas), "fechadas": list(fechadas)}


def copia(lado="LONG", t_ref=NOW0 - 120, pid="p1"):
    return {"id_op": f"copy|okx:T1|{pid}", "origem": "copy", "estrategia": "copy:okx:T1", "b": "ABC", "inst": INST, "lado": lado,
            "tf": "1H", "t_sinal": NOW0 - 60, "t_ref": t_ref, "atr_ref": 0.01, "saida": {"tipo": "fixa", "k": 1.5, "tp": 2.0, "hold": 4},
            "regime": None, "decisao": {"fecho": 1.0}, "aberta_em": NOW0 - 60}


class CopyTrading(Base):
    def corre_copy(self, api, cp, now=NOW0, pap=None, **kw):
        return self.corre(api, reg=registo(), pap=pap if pap is not None else papel(), now=now, copy=cp, **kw)

    def test_copia_long_e_short_com_limites_do_piloto(self):
        for lado, lado_ordem in (("LONG", "buy"), ("SHORT", "sell")):
            shutil.rmtree(self.d)
            os.makedirs(self.d)
            api = FakeOKX()
            st, _ = self.corre_copy(api, copy_doc([copia(lado)]))
            o = api.posts("/trade/order")
            self.assertEqual(len(o), 1, lado)
            self.assertEqual(o[0][2]["side"], lado_ordem)
            self.assertEqual(st["aberta"]["estrategia"], "copy:okx:T1")
            self.assertLessEqual(st["aberta"]["risco_planeado"], 0.25)
            self.assertLessEqual(st["aberta"]["nocional"], 20)

    def test_copia_tardia_nao_entra(self):
        api = FakeOKX()
        st, _ = self.corre_copy(api, copy_doc([copia(t_ref=NOW0 - 700)]))
        self.assertEqual(api.posts(), [])
        self.assertIn("copia tardia", json.dumps(st["sinais_perdidos"], ensure_ascii=False))

    def test_trader_fecha_e_a_copia_fecha(self):
        api = FakeOKX()
        c = copia()
        self.corre_copy(api, copy_doc([c]))
        self.corre_copy(api, copy_doc([c]), now=NOW0 + 300)
        st, _ = self.corre_copy(api, copy_doc([], [{"id_op": c["id_op"], "motivo": "trader fechou"}]), now=NOW0 + 600)
        self.assertTrue(api.posts("close-position"))
        self.assertIn("espelho", st["ops"][-1]["motivo_saida"])

    def test_copy_funciona_com_papel_velho_e_partilha_a_unica_posicao(self):
        api = FakeOKX()
        st, _ = self.corre_copy(api, copy_doc([copia()]), pap=dict(papel(sinal()), t=NOW0 - 7200))
        self.assertTrue(st["portas"]["dados_frescos"]["ok"])
        self.assertEqual(len(api.posts("/trade/order")), 1)
        self.assertEqual(st["aberta"]["estrategia"], "copy:okx:T1")

    def test_copy_velho_nao_traz_sinais_e_trader_degradado_suspenso_sozinho(self):
        api = FakeOKX()
        st, _ = self.corre_copy(api, copy_doc([copia()], t=NOW0 - 400))              # posicao do trader vista ha > 5 min
        self.assertEqual(api.posts(), [])
        st0 = P.estado_inicial()
        st0["ops"] = [{"estrategia": "copy:okx:T1", "r": -1.0, "estado": "fechada"}] * 4
        json.dump(st0, open(os.path.join(self.d, "piloto_estado.json"), "w"))
        api = FakeOKX()
        st, _ = self.corre(api, reg=registo(experimental()), pap=papel(sinal("exp111")), copy=copy_doc([copia()]))
        self.assertIn("copy:okx:T1", st["recusadas_pelo_executor"])
        self.assertEqual(st["aberta"]["estrategia"], "exp111")


class RegistoOportunidades(Base):
    def test_todas_as_oportunidades_ficam_registadas_e_classificadas(self):
        api = FakeOKX()
        reg = registo(experimental("bom"), {"id": "mau", "estado": "PAPER_TRADING", "motivo": "bloqueada pelo papel", "lado": "LONG"})
        pap = papel(sinal("bom"), sinal("mau", base="XYZ"), sinal("bom", base="OLD", t_fecho=NOW0 - 5000, aberta_em=NOW0 - 60))
        st, _ = self.corre(api, reg=reg, pap=pap)
        R = st["oportunidades"]
        self.assertEqual(len(R), 3)
        por = {r["origem"] + ":" + r["base"]: r for r in R.values()}
        self.assertEqual(por["bom:ABC"]["decisao"], "ORDEM_ENVIADA")
        self.assertEqual((por["mau:XYZ"]["categoria"], por["mau:XYZ"]["classe"]), ("sem_vantagem", "B"))
        self.assertEqual(por["bom:OLD"]["categoria"], "expirado")          # o papel ja o deu tarde: rejeicao correta (B)
        tarde = P.estado_inicial()
        self.assertEqual(P.classificar("chegou 40 min depois do fecho da vela", visto_tarde=True)[1], "C")
        st, _ = self.corre(api, reg=reg, pap=pap, now=NOW0 + 900)
        self.assertEqual(st["oportunidades"][sinal("bom")["id_op"]]["decisao"], "EXECUTADA_REAL")
        pub = json.load(open(os.path.join(self.d, "piloto_publico.json")))
        self.assertTrue(all("margem_livre" not in r for r in pub["oportunidades"]))
        dia = P._dia(NOW0)
        self.assertEqual(pub["resumo_oportunidades"][dia]["B"], 2)

    def test_voltas_sem_sinais_contam_como_a_e_hipotetico_do_papel(self):
        api = FakeOKX()
        reg = registo({"id": "mau", "estado": "PAPER_TRADING", "motivo": "x", "lado": "LONG"})
        s = sinal("mau")
        self.corre(api, reg=reg, pap=papel(s))
        st, _ = self.corre(api, reg=reg, pap=papel(fechadas=[dict(s, r=-1.2)]), now=NOW0 + 60)
        r = st["oportunidades"][s["id_op"]]
        self.assertEqual(r["resultado_hipotetico_r"], -1.2)
        self.assertIn("NAO e resultado real", r["resultado_hipotetico_fonte"])
        self.assertEqual(st["resumo_oportunidades"][P._dia(NOW0)]["voltas_sem_sinais"], 1)

    def test_sinal_tratado_antes_do_registo_fica_decidido(self):
        st0 = P.estado_inicial()
        s = sinal("exp111")
        st0["vistos"] = [s["id_op"]]
        st0["sinais_perdidos"] = [{"t": 1, "sinal": s["id_op"], "motivo": "spread 0.5% acima de 0.3% (liquidez)"}]
        json.dump(st0, open(os.path.join(self.d, "piloto_estado.json"), "w"))
        st, _ = self.corre(FakeOKX(), reg=registo(experimental()), pap=papel(s))
        self.assertEqual(st["oportunidades"][s["id_op"]]["categoria"], "liquidez")

    def test_falha_tecnica_e_classe_c(self):
        self.assertEqual(P.classificar("ordem recusada pela OKX (x)"), ("ordem_rejeitada", "C"))
        self.assertEqual(P.classificar("OKX sem resposta sobre o instrumento"), ("erro_api", "C"))
        self.assertEqual(P.classificar("portas fechadas: api_fiavel")[1], "C")
        self.assertEqual(P.classificar("portas fechadas: perda_do_dia"), ("bloqueio_risco", "B"))
        self.assertEqual(P.classificar("copia tardia: 12 min", visto_tarde=True), ("falha_sincronizacao", "C"))
        self.assertEqual(P.classificar("spread 0.5% acima de 0.3% (liquidez)"), ("liquidez", "B"))


class Protecao(Base):
    """(18/11, incidente RENDER) estado do stop sempre lido na OKX."""
    def abrir(self, **kw):
        api = FakeOKX(**kw)
        self.corre(api)
        st, _ = self.corre(api, now=NOW0 + 900)
        return api, st

    def test_confirmado_e_duplicado_nao_repoe(self):
        api, st = self.abrir()
        self.assertEqual((st["aberta"]["stop_estado"], st["aberta"]["stop_cobertura"]), ("confirmado", 1.0))
        api.algos.append(dict(api.algos[0]))                                   # dois stops: protegido, nada a fazer
        st, _ = self.corre(api, now=NOW0 + 1800)
        self.assertEqual(st["aberta"]["stop_estado"], "confirmado")
        self.assertEqual(api.posts("order-algo"), [])

    def test_cancelado_na_okx_apesar_do_estado_local_repoe(self):
        api, st = self.abrir()
        api.algos = []                                                         # divergencia: local diz confirmado
        st, _ = self.corre(api, now=NOW0 + 1800)
        self.assertEqual(len(api.posts("order-algo")), 1)
        o = api.posts("order-algo")[0][2]
        self.assertEqual((o["side"], o["reduceOnly"], o["tdMode"]), ("sell", True, "isolated"))
        self.assertFalse(st["portas"]["posicoes_protegidas"]["ok"])           # sem entradas ate confirmar

    def test_parcial_repoe_so_o_que_falta(self):
        api, st = self.abrir(ctval="0.1")
        q = float(api.pos["pos"])
        api.algos[0]["sz"] = str(q / 2)
        self.corre(api, now=NOW0 + 1800)
        self.assertAlmostEqual(float(api.posts("order-algo")[0][2]["sz"]), q / 2)

    def test_falha_da_api_nao_repoe_nem_conclui(self):
        api, st = self.abrir()
        api.falha.add("orders-algo-pending")
        st, _ = self.corre(api, now=NOW0 + 1800)
        self.assertEqual(st["aberta"]["stop_estado"], "sem_resposta")
        self.assertEqual(api.posts("order-algo"), [])
        self.assertFalse(st["portas"]["posicoes_protegidas"]["ok"])

    def test_rejeitado_fecha_e_bloqueia(self):
        api, st = self.abrir()
        api.algos, api.algo_ok = [], False
        st, _ = self.corre(api, now=NOW0 + 1800)
        self.assertTrue(api.posts("close-position"))
        self.assertTrue(st["bloqueio"])

    def test_reinicio_le_a_okx_de_novo(self):
        api, st = self.abrir()
        e = json.load(open(os.path.join(self.d, "piloto_estado.json")))
        e["aberta"]["stop_confirmado"] = False
        json.dump(e, open(os.path.join(self.d, "piloto_estado.json"), "w"))
        st, _ = self.corre(api, now=NOW0 + 1800)
        self.assertEqual(st["aberta"]["stop_estado"], "confirmado")
        self.assertEqual(api.posts("order-algo"), [])

    def test_estrategia_suspensa_nao_entra(self):
        with mock.patch.object(P, "cfg", return_value=dict(CFG, estrategias_suspensas={"exp111": "revisao"})):
            api = FakeOKX()
            st, _ = self.corre(api, reg=registo(experimental()), pap=papel(sinal("exp111")))
        self.assertEqual(api.posts(), [])
        self.assertIn("suspensa", " ".join(st["recusadas_pelo_executor"]["exp111"]))

    def test_config_suspende_bbc2557ab78e(self):
        self.assertIn("bbc2557ab78e", CFG["estrategias_suspensas"])


class Experimental(Base):
    def test_experimental_sem_estatistica_opera_dentro_dos_limites(self):
        api = FakeOKX()
        st, _ = self.corre(api, reg=registo(experimental()), pap=papel(sinal("exp111")))
        o = api.posts("/trade/order")
        self.assertEqual(len(o), 1)
        self.assertTrue(st["portas"]["estrategias_elegiveis"]["ok"])
        self.assertLessEqual(st["aberta"]["risco_planeado"], 0.25)
        self.assertLessEqual(st["aberta"]["nocional"], 20)
        self.assertTrue(5 <= st["aberta"]["alav"] <= 10)

    def test_short_experimental(self):
        api = FakeOKX()
        self.corre(api, reg=registo(experimental(lado="SHORT")), pap=papel(sinal("exp111", lado="SHORT")))
        self.assertEqual(api.posts("/trade/order")[0][2]["side"], "sell")

    def test_rejeitadas_nunca_operam(self):
        for rid in ("e495d11739f6", "f8f018b82179"):
            shutil.rmtree(self.d)
            os.makedirs(self.d)
            api = FakeOKX()
            self.corre(api, reg=registo(experimental(rid), estrategia(rid, id=rid)), pap=papel(sinal(rid)))
            self.assertEqual(api.posts(), [], rid)

    def test_auditoria_tecnica_falhada_ou_estado_errado(self):
        for kw in ({"auditoria_tecnica": {"ok": False, "falhas": ["x"]}}, {"estado": "PAPER_TRADING"},
                   {"estado": "SUSPENDED"}, {"definicao": {"saida": {"k": 0}}}):
            shutil.rmtree(self.d)
            os.makedirs(self.d)
            api = FakeOKX()
            self.corre(api, reg=registo(experimental(**kw)), pap=papel(sinal("exp111")))
            self.assertEqual(api.posts(), [], kw)

    def test_uma_estrategia_degradada_nao_bloqueia_as_outras(self):
        st = P.estado_inicial()
        st["ops"] = [{"estrategia": "mau", "r": -1.0, "estado": "fechada"}] * 5
        json.dump(st, open(os.path.join(self.d, "piloto_estado.json"), "w"))
        api = FakeOKX()
        s2, _ = self.corre(api, reg=registo(experimental("mau"), experimental("bom")),
                           pap=papel(sinal("mau"), sinal("bom", base="ABC")))
        self.assertEqual(s2["aberta"]["estrategia"], "bom")
        self.assertIn("mau", s2["recusadas_pelo_executor"])

    def test_aprovada_tem_prioridade_sobre_experimental(self):
        api = FakeOKX()
        st, _ = self.corre(api, reg=registo(experimental("exp111", backtest={"r_medio": 0.3}), estrategia("apr222")),
                           pap=papel(sinal("exp111"), sinal("apr222")))
        self.assertEqual(st["aberta"]["estrategia"], "apr222")

    def test_contrato_de_acoes_e_aceite(self):
        api = FakeOKX()
        orig = api.pub
        api.pub = lambda path, params=None: [dict(x, instCategory="3") for x in orig(path, params)] if "instruments" in path else orig(path, params)
        self.corre(api, reg=registo(experimental()), pap=papel(sinal("exp111")))
        self.assertEqual(len(api.posts("/trade/order")), 1)


if __name__ == "__main__":
    unittest.main()


class FakeFecho(FakeOKX):
    """OKX falsa com o fecho controlavel: fecha | aceita (mas a posicao fica) | recusa | parcial."""
    def __init__(self, modo="aceita", **kw):
        super().__init__(**kw)
        self.modo, self.cancelados = modo, []

    def priv(self, metodo, path, corpo=None):
        base = path.split("?")[0].rsplit("/", 1)[-1]
        if base == "close-position":
            self.chamadas.append((metodo, path, corpo))
            if self.modo == "recusa":
                return {"code": "51000", "data": []}
            if self.modo == "aceita":
                return {"code": "0", "data": [{}]}
            if self.modo == "parcial" and self.pos:
                self.pos = dict(self.pos, pos=str(float(self.pos["pos"]) / 2))
                return {"code": "0", "data": [{}]}
        if base == "cancel-algos":
            self.chamadas.append((metodo, path, corpo))
            self.cancelados += [c["algoId"] for c in corpo]
            self.algos = [a for a in self.algos if a.get("algoId") not in self.cancelados]
            return {"code": "0", "data": [{}]}
        return super().priv(metodo, path, corpo)


class PrecoAtual(Base):
    """(18/11) Preco atual com hora e R da posicao aberta no estado publico e no desempenho."""

    def test_preco_e_r_aberto(self):
        api = FakeOKX()
        self.corre(api)
        st, _ = self.corre(api, now=NOW0 + 900)
        op = st["aberta"]
        ent, stp = op["preco_efetivo"], op.get("stop_inicial") or op["stop"]
        mk = ent + (ent - stp) * 0.5 * (1 if op["lado"] == "LONG" else -1)     # meio R a favor
        api.pos = dict(api.pos, markPx=str(mk))
        st, _ = self.corre(api, now=NOW0 + 1800)
        op = st["aberta"]
        self.assertEqual((op["preco_atual"], op["t_preco"]), (mk, NOW0 + 1800))
        self.assertAlmostEqual(op["r_aberto"], 0.5, places=2)
        d = P.desempenho(st)[op["estrategia"]]
        self.assertEqual(d["abertas"], 1)
        self.assertAlmostEqual(d["r_aberto"], 0.5, places=2)
        self.assertAlmostEqual(d["r_total_com_abertas"], 0.5, places=2)
        pub = P.publico(st, P.cfg(), {}, NOW0 + 1800)
        o = [x for x in pub["ops"] if x["estado"] == "aberta"][0]
        self.assertEqual((o["preco_atual"], o["t_preco"]), (mk, NOW0 + 1800))
        self.assertAlmostEqual(o["r_aberto"], 0.5, places=2)
        # sem resposta da OKX: fica o ultimo preco com a hora antiga (nao se inventa um novo)
        api.pos = dict(api.pos)
        api.pos.pop("markPx")
        st, _ = self.corre(api, now=NOW0 + 2700)
        self.assertEqual(st["aberta"]["t_preco"], NOW0 + 1800)


class FechoRecuperacao(Base):
    """(18/11) pedido de fecho aceite mas posicao aberta: repete, limita, bloqueia sem abandonar o stop."""
    def a_fechar(self, modo="aceita", **kw):
        api = FakeFecho(modo=modo, **kw)
        self.corre(api)                                            # entrada
        self.corre(api, now=NOW0 + 900)                            # executada
        for a in api.algos:
            a["algoId"] = "a1"
        st, _ = self.corre(api, now=NOW0 + 900 + 4 * 3600 + 60)    # saida por tempo: 1.o pedido
        return api, st, NOW0 + 900 + 4 * 3600 + 60

    def fechos(self, api):
        return [c for c in api.chamadas if c[1].endswith("close-position")]

    def test_aceite_mas_aberta_repete_depois_do_intervalo(self):
        api, st, t = self.a_fechar()
        self.assertEqual(st["aberta"]["estado"], "a fechar")
        self.corre(api, now=t + 300)                               # antes de 10 min: nada
        self.assertEqual(len(self.fechos(api)), 1)
        st, _ = self.corre(api, now=t + P.FECHO_REPETIR_S + 1)
        self.assertEqual(len(self.fechos(api)), 2)
        self.assertTrue(all(c[2] == {"instId": INST, "mgnMode": "isolated"} for c in self.fechos(api)))
        self.assertTrue(st["aberta"]["stop_confirmado"])           # continua protegida entre tentativas

    def test_limite_de_pedidos_bloqueia_e_mantem_stop(self):
        api, st, t = self.a_fechar()
        for k in range(1, 6):
            st, msgs = self.corre(api, now=t + k * (P.FECHO_REPETIR_S + 1))
        self.assertEqual(len(self.fechos(api)), P.FECHO_MAX_PEDIDOS)
        self.assertTrue(st["bloqueio"])
        self.assertFalse(st["portas"]["bloqueio"]["ok"])
        self.assertEqual(st["aberta"]["stop_estado"], "confirmado")
        self.assertEqual(api.posts("/trade/order"), api.posts("/trade/order")[:1])   # nenhuma entrada nova

    def test_recusado_repete_com_intervalo_e_limite(self):
        # (revisao 18/11) antes, um fecho recusado deixava a operacao "aberta" e o pedido repetia-se em TODAS as voltas,
        # sem limite. Agora fica "a fechar": repete de 10 em 10 min, no maximo 3 pedidos, e depois bloqueia.
        api, st, t = self.a_fechar(modo="recusa")
        self.assertEqual(st["aberta"]["estado"], "a fechar")
        self.corre(api, now=t + 60)
        self.assertEqual(len(self.fechos(api)), 1)                 # antes do intervalo: nada
        for k in range(1, 6):
            st, _ = self.corre(api, now=t + k * (P.FECHO_REPETIR_S + 1))
        self.assertEqual(len(self.fechos(api)), P.FECHO_MAX_PEDIDOS)
        self.assertTrue(st["bloqueio"])
        self.assertEqual(st["aberta"]["stop_estado"], "confirmado")

    def test_lado_contrario_sem_stop_nenhuma_ordem(self):
        # (revisao 18/11) com a posicao do lado contrario e sem stop do lado da operacao, o caminho do stop tentava repor
        # o stop e, se falhasse, pedia close-position: fecharia uma posicao que nao e do piloto. Agora: nenhuma ordem.
        api, st, t = self.a_fechar()
        api.pos = dict(api.pos, pos="-3")
        api.algos = []
        n_algo = len(api.posts("/trade/order-algo"))
        st, msgs = self.corre(api, now=t + P.FECHO_REPETIR_S + 1)
        self.assertEqual(len(self.fechos(api)), 1)
        self.assertEqual(len(api.posts("/trade/order-algo")), n_algo)
        self.assertTrue(st["bloqueio"])
        self.assertEqual(st["aberta"]["divergencia"], "lado contrario")
        st, msgs2 = self.corre(api, now=t + 2 * (P.FECHO_REPETIR_S + 1))
        self.assertFalse([m for m in msgs2 if "não corresponde" in m])   # alerta uma vez, nao em todas as voltas

    def test_aberta_com_contratos_a_mais_nenhuma_ordem(self):
        api = FakeFecho(modo="aceita")
        self.corre(api)
        st, _ = self.corre(api, now=NOW0 + 900)
        self.assertEqual(st["aberta"]["estado"], "aberta")
        api.pos = dict(api.pos, pos=str(float(api.pos["pos"]) * 3))  # outro executor/manual no mesmo instrumento
        api.algos = []
        n_algo = len(api.posts("/trade/order-algo"))
        st, msgs = self.corre(api, now=NOW0 + 1800)
        self.assertEqual(len(self.fechos(api)), 0)
        self.assertEqual(len(api.posts("/trade/order-algo")), n_algo)
        self.assertEqual(st["aberta"]["divergencia"], "contratos a mais")
        self.assertTrue(st["bloqueio"])
        self.assertTrue(any("não corresponde" in m for m in msgs))

    def test_parcial_nao_e_divergencia(self):
        api, st, t = self.a_fechar(modo="parcial", ctval="0.1")
        st, _ = self.corre(api, now=t + P.FECHO_REPETIR_S + 1)
        self.assertNotIn("divergencia", st["aberta"])

    def test_fechada_entre_tentativas_reconcilia_e_limpa_so_as_condicionais_da_operacao(self):
        api, st, t = self.a_fechar()
        api.algos.append({"algoId": "outro", "algoClOrdId": "csXLM1", "slTriggerPx": "2", "side": "buy", "instId": INST})
        api.algos.append({"algoId": "semid", "slTriggerPx": "2", "side": "buy", "instId": INST})
        api.historico.append({"posId": "p1", "instId": INST, "realizedPnl": "0.1", "closeAvgPx": "1.0", "cTime": "1", "uTime": str(10 ** 13)})
        api.pos = None                                             # fechou sozinha (ex.: a OKX executou o pedido tarde)
        st, _ = self.corre(api, now=t + 120)
        self.assertEqual(st["ops"][-1]["estado"], "fechada")
        self.assertEqual(len(self.fechos(api)), 1)                 # nao repetiu
        self.assertEqual(api.cancelados, ["a1"])                   # so a do piloto desta operacao
        self.assertFalse(st["ops"][-1]["limpeza_pendente"])

    def test_reinicio_no_estado_a_fechar(self):
        api, st, t = self.a_fechar()
        e = json.load(open(os.path.join(self.d, "piloto_estado.json")))
        e["aberta"].pop("fecho_pedidos", None)                     # estado antigo, sem o registo de pedidos
        json.dump(e, open(os.path.join(self.d, "piloto_estado.json"), "w"))
        self.corre(api, now=t + 60)
        self.assertEqual(len(self.fechos(api)), 2)

    def test_api_indisponivel_nada_e_pedido(self):
        api, st, t = self.a_fechar()
        api.falha.add("positions")
        st, _ = self.corre(api, now=t + P.FECHO_REPETIR_S + 1)
        self.assertEqual(len(self.fechos(api)), 1)
        self.assertEqual(st["aberta"]["estado"], "a fechar")

    def test_parcial_repete_ate_fechar(self):
        api, st, t = self.a_fechar(modo="parcial", ctval="0.1")
        st, _ = self.corre(api, now=t + P.FECHO_REPETIR_S + 1)
        self.assertLess(st["aberta"]["fecho_restante_pct"], 100)
        self.assertEqual(len(self.fechos(api)), 2)

    def test_lado_contrario_nao_fecha_e_bloqueia(self):
        api, st, t = self.a_fechar()
        api.pos = dict(api.pos, pos="-3")                          # a OKX mostra SHORT numa operacao LONG
        st, msgs = self.corre(api, now=t + P.FECHO_REPETIR_S + 1)
        self.assertEqual(len(self.fechos(api)), 1)
        self.assertTrue(st["bloqueio"])

    def test_limpeza_falhada_repete_na_volta_seguinte(self):
        api, st, t = self.a_fechar()
        api.historico.append({"posId": "p1", "instId": INST, "realizedPnl": "0.1", "closeAvgPx": "1.0", "cTime": "1", "uTime": str(10 ** 13)})
        api.pos = None
        api.falha.add("orders-algo-pending")
        st, _ = self.corre(api, now=t + 120)
        self.assertTrue(st["ops"][-1]["limpeza_pendente"])
        api.falha.discard("orders-algo-pending")
        st, _ = self.corre(api, now=t + 240)
        self.assertEqual(api.cancelados, ["a1"])
