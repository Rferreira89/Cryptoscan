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
        self.assertFalse(st["portas"]["estrategias_aprovadas"]["ok"])


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
        st, _ = P.ciclo(api, self.d, now=NOW0, registo=dict(reg, t=NOW0 - 4 * 3600), papel=pap, isolado=True, cifra_ok=True)
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


if __name__ == "__main__":
    unittest.main()
