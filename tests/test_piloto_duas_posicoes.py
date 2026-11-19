"""(18/11, ordem do Rui) Piloto OKX com ate 2 posicoes simultaneas SEM aumentar o risco: o orcamento (risco no stop com
custos, nocional, margem) e o de uma posicao e e partilhado. OKX falsa com varios instrumentos (nenhum pedido sai daqui)."""
import copy
import json
import os
import random
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import piloto_okx as P  # noqa: E402

CFG = json.load(open(P.CFG_FICHEIRO))
NOW0 = 1_800_000_000 // 1800 * 1800 + 660
RT, NT = CFG["risco_total_max"], CFG["nocional_total_max"]


def inst_id(b):
    return f"{b}-USD_UM_XPERP-310404"


class MultiOKX:
    """OKX falsa com varios instrumentos: ordens por clOrdId/ordId, posicoes, stops e historico por instrumento."""

    def __init__(self, bases=("AAA", "BBB", "CCC"), saldo=30.0, lot="1", minsz="1", ctval="1"):
        self.bases, self.saldo = list(bases), saldo
        self.spec = {inst_id(b): {"lotSz": lot, "minSz": minsz, "ctVal": ctval} for b in bases}
        self.chamadas, self.ordens, self.pos, self.algos, self.hist, self.fills = [], {}, {}, {}, [], []
        self.fill = {}            # inst -> "filled" | "nenhum" | "parcial"
        self.falha, self.outros = set(), {}   # endpoints que falham; inst -> posicao de outro executor
        self.post_sem_resposta = False
        self.n = 0

    def pub(self, path, params=None):
        self.chamadas.append(("PUB", path, params))
        if "instruments" in path:
            return [{"instId": i, "state": "live", "ctType": "linear", "instCategory": "1", "ruleType": "xperp",
                     "ctVal": s["ctVal"], "ctMult": "1", "ctValCcy": i.split("-")[0], "lotSz": s["lotSz"], "minSz": s["minSz"],
                     "tickSz": "0.0001", "lever": "20"} for i, s in self.spec.items()]
        if "tickers" in path:
            return [{"instId": i, "bidPx": "0.9995", "askPx": "1.0005", "last": "1.0", "volCcy24h": "1000000"} for i in self.spec]
        if "funding-rate" in path:
            return [{"fundingRate": "0.0001"}]
        return []

    def _ok(self, d):
        return {"code": "0", "data": d}

    def _inst(self, path):
        return next((i for i in self.spec if i in path), None)

    def priv(self, metodo, path, corpo=None):
        self.chamadas.append((metodo, path, corpo))
        base = path.split("?")[0].rsplit("/", 1)[-1]
        if base in self.falha:
            return {"code": "50001", "data": []}
        inst = self._inst(path) or (corpo or {}).get("instId")
        if base == "config":
            return self._ok([{"settleCcy": "USDC", "perm": "read_only,trade", "posMode": "net_mode", "acctLv": "2"}])
        if base == "balance":
            return self._ok([{"details": [{"ccy": "USDC", "availBal": str(self.saldo)}]}])
        if base == "instruments":
            return self._ok([{"instId": i} for i in self.spec])
        if base == "set-leverage":
            return self._ok([{}])
        if base == "order" and metodo == "POST":
            if self.post_sem_resposta:                # timeout: a OKX pode ter recebido a ordem
                self.n += 1
                self.ordens[corpo["clOrdId"]] = dict(corpo, ordId=f"o{self.n}")
                return None
            self.n += 1
            self.ordens[corpo["clOrdId"]] = dict(corpo, ordId=f"o{self.n}")
            return self._ok([{"ordId": f"o{self.n}", "sCode": "0"}])
        if base == "order":
            if "clOrdId=" in path:
                cl = path.split("clOrdId=")[1]
                o = self.ordens.get(cl)
                return self._ok([{"ordId": o["ordId"]}] if o else [])
            oid = path.split("ordId=")[1] if "ordId=" in path else None
            o = next((x for x in self.ordens.values() if x["ordId"] == oid), None)
            if not o:
                return self._ok([{"state": "live", "accFillSz": "0"}])
            modo = self.fill.get(o["instId"], "filled")
            if modo == "nenhum":
                return self._ok([{"state": "live", "accFillSz": "0"}])
            sz = float(o["sz"])
            acc = sz if modo == "filled" else float(max(1, int(sz // 2)))
            if o["instId"] not in self.pos and not o.get("_feito"):
                o["_feito"] = True
                self.pos[o["instId"]] = {"pos": str(acc if o["side"] == "buy" else -acc), "upl": "-0.01", "instId": o["instId"],
                                         "posId": "p" + o["ordId"], "cTime": "1", "markPx": "1.0"}
                self.fills.append({"instId": o["instId"], "clOrdId": o["clOrdId"], "ts": "2"})
                a = o["attachAlgoOrds"][0]
                self.algos[o["instId"]] = [{"slTriggerPx": a["slTriggerPx"], "sz": str(acc), "algoClOrdId": a["attachAlgoClOrdId"],
                                            "algoId": "a" + o["ordId"], "side": "sell" if o["side"] == "buy" else "buy",
                                            "ordType": "oco"}]
            return self._ok([{"state": "filled" if modo == "filled" else "partially_filled", "accFillSz": str(acc),
                              "avgPx": o["px"], "fillTime": "1000"}])
        if base == "positions":
            todas = list(self.pos.values()) + list(self.outros.values())
            return self._ok(todas if inst is None else [x for x in todas if x["instId"] == inst])
        if base == "orders-pending":
            return self._ok([])
        if base == "orders-algo-pending":
            if "oco" not in path:
                return self._ok([])
            return self._ok([a for i, xs in self.algos.items() for a in xs if inst is None or i == inst])
        if base in ("fills", "fills-history"):
            return self._ok([x for x in self.fills if "instId=" not in path or x["instId"] in path])
        if base == "positions-history":
            return self._ok([h for h in self.hist if inst is None or h["instId"] == inst])
        if base == "order-algo":
            return self._ok([{}])
        if base in ("cancel-order", "cancel-algos"):
            if base == "cancel-algos":
                ids = {x["algoId"] for x in corpo}
                for i in self.algos:
                    self.algos[i] = [a for a in self.algos[i] if a["algoId"] not in ids]
            return self._ok([{}])
        if base == "close-position":
            if inst in self.outros:
                raise AssertionError("o piloto tentou fechar a posicao de outro executor")
            p = self.pos.pop(inst, None)
            if p:
                self.hist.append({"posId": p["posId"], "instId": inst, "realizedPnl": "0.05", "closeAvgPx": "1.0",
                                  "cTime": "1", "uTime": str(10 ** 13)})
            return self._ok([{}])
        raise AssertionError(path)

    def posts(self, nome):
        return [c for c in self.chamadas if c[0] == "POST" and c[1].endswith(nome)]

    def fechar(self, b):                       # stop/objetivo na corretora
        p = self.pos.pop(inst_id(b))
        self.algos.pop(inst_id(b), None)
        self.hist.append({"posId": p["posId"], "instId": p["instId"], "realizedPnl": "-0.02", "closeAvgPx": "0.99",
                          "cTime": "1", "uTime": str(10 ** 13)})


def estrategia(eid, lado="LONG"):
    return {"id": eid, "versao": eid, "estado": "APPROVED_REAL", "lado": lado, "tf": "1H", "regimes": None,
            "oos": {"n": 150, "acontecimentos": 60, "dias": 40, "r_medio": 0.2, "profit_factor": 1.5, "p_holm": 0.01,
                    "ic95_acontecimento": [0.05, 0.35], "custo_medio_r": 0.05,
                    "robustez": {k: 0.1 for k in P.ROBUSTEZ}, "concentracao": {"moeda": 0.2, "acontecimento": 0.1, "dia": 0.1}},
            "papel": {"fechadas": 40, "acontecimentos": 35, "dias": 20, "r_medio": 0.15, "falhas_criticas": 0}}


def sinal(eid, base, t_fecho=NOW0 - 660, atr=0.05, lado="LONG"):
    return {"id_op": f"{eid}|{base}|{t_fecho - 3600}", "estrategia": eid, "b": base, "inst": inst_id(base), "lado": lado,
            "tf": "1H", "t_sinal": t_fecho - 3600, "atr_ref": atr, "saida": {"tipo": "fixa", "k": 2.0, "tp": 2.0, "hold": 4},
            "regime": "lateral", "decisao": {"fecho": 1.0}, "aberta_em": t_fecho + 75}


class Base(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        # estrategia "boa" com melhor expectativa e "fraca" para a escolha
        self.reg = {"estrategias": {"boa": dict(estrategia("boa"), oos=dict(estrategia("boa")["oos"], r_medio=0.4)),
                                    "fraca": estrategia("fraca"), "curta": dict(estrategia("curta"), lado="SHORT")}}

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def corre(self, api, *sinais, now=NOW0):
        reg = copy.deepcopy(self.reg)
        reg["t"] = now
        pap = {"t": now, "abertas": [copy.deepcopy(s) for s in sinais], "fechadas": []}
        return P.ciclo(api, self.d, now=now, registo=reg, papel=pap, isolado=True, cifra_ok=True)

    def vivas(self, st):
        return P.ativas(st)

    def limites_respeitados(self, st):
        o = P.orcamento(st, CFG)
        self.assertLessEqual(o["risco_aberto"], RT + 1e-9)
        self.assertLessEqual(o["nocional_aberto"], NT + 1e-9)
        self.assertLessEqual(o["margem_usada"], CFG["capital_max"] + 1e-9)
        self.assertLessEqual(o["abertas"], CFG["posicoes_max"])
        return o


class DuasPosicoes(Base):
    def test_config_so_muda_o_numero_de_posicoes(self):
        self.assertEqual(CFG["posicoes_max"], 2)
        self.assertEqual((CFG["risco_total_max"], CFG["nocional_total_max"]), (CFG["risco_max_op"], CFG["nocional_max"]))
        self.assertEqual((CFG["capital_max"], CFG["alav_min"], CFG["alav_max"], CFG["perda_max"], CFG["suspender_em"],
                          CFG["perda_diaria_max"]), (20.0, 5, 10, 5.0, 3.0, 1.0))

    def test_1_segunda_entra_com_o_risco_que_sobra(self):
        api = MultiOKX()
        st, _ = self.corre(api, sinal("boa", "AAA", atr=0.05))                 # risco por contrato ~0,1: 2 contratos
        st, _ = self.corre(api, now=NOW0 + 900)
        a = self.vivas(st)[0]
        self.assertEqual((a["base"], a["estado"]), ("AAA", "aberta"))
        livre = RT - a["risco_planeado"]
        self.assertGreater(livre, 0)
        st, _ = self.corre(api, sinal("fraca", "BBB", t_fecho=NOW0 + 1800 - 660, atr=0.0025), now=NOW0 + 1800)
        vs = self.vivas(st)
        self.assertEqual([o["base"] for o in vs], ["AAA", "BBB"])
        self.assertLessEqual(vs[1]["risco_planeado"], livre + 1e-9)               # so o residual
        self.limites_respeitados(st)
        self.assertNotEqual(vs[0]["clOrdId"], vs[1]["clOrdId"])

    def test_2_terceira_nunca_entra(self):
        api = MultiOKX(bases=("AAA", "BBB", "CCC"))
        st, _ = self.corre(api, sinal("boa", "AAA", atr=0.05))
        st, _ = self.corre(api, sinal("fraca", "BBB", t_fecho=NOW0 + 900 - 660, atr=0.0025), now=NOW0 + 900)
        st, _ = self.corre(api, now=NOW0 + 1800)
        self.assertEqual(len(self.vivas(st)), 2)
        n_ord = len(api.posts("/trade/order"))
        st, _ = self.corre(api, sinal("curta", "CCC", t_fecho=NOW0 + 2700 - 660, atr=0.0001, lado="SHORT"), now=NOW0 + 2700)
        self.assertEqual(len(api.posts("/trade/order")), n_ord)
        r = st["oportunidades"]["curta|CCC|" + str(NOW0 + 2700 - 660 - 3600)]
        self.assertIn("sem vaga", r["aguarda"])                                    # (19/11) fresco: aguarda vaga
        self.assertIsNone(r["decisao"])
        self.limites_respeitados(st)

    def test_3_primeira_gasta_quase_todo_o_orcamento(self):
        api = MultiOKX()
        st, _ = self.corre(api, sinal("boa", "AAA", atr=0.005))                # ~0,0145/contrato: ~17 contratos
        st, _ = self.corre(api, now=NOW0 + 900)
        a = self.vivas(st)[0]
        self.assertGreater(a["risco_planeado"], 0.9 * RT)
        st, _ = self.corre(api, sinal("fraca", "BBB", t_fecho=NOW0 + 1800 - 660, atr=0.05), now=NOW0 + 1800)
        self.assertEqual(len(self.vivas(st)), 1)
        mot = [x["motivo"] for x in st["sinais_perdidos"] if x["sinal"].startswith("fraca|BBB")][-1]
        self.assertTrue("tamanho minimo" in mot or "esgotado" in mot, mot)
        self.limites_respeitados(st)

    def test_4_duas_competem_pela_ultima_vaga_ganha_a_melhor(self):
        api = MultiOKX()
        st, _ = self.corre(api, sinal("fraca", "AAA", atr=0.05))
        st, _ = self.corre(api, now=NOW0 + 900)
        t = NOW0 + 1800 - 660
        # recebidas pela ordem "fraca" primeiro; a "boa" tem melhor expectativa e entra ela
        st, _ = self.corre(api, sinal("fraca", "CCC", t_fecho=t, atr=0.0025), sinal("boa", "BBB", t_fecho=t, atr=0.0025),
                           now=NOW0 + 1800)
        self.assertEqual([o["base"] for o in self.vivas(st)], ["AAA", "BBB"])
        # (19/11) sem vaga e capacidade, nao defeito do sinal: fica a aguardar (volta a ser visto enquanto fresco)
        sid = sinal("fraca", "CCC", t_fecho=t)["id_op"]
        self.assertFalse([x for x in st["sinais_perdidos"] if x["sinal"] == sid])
        self.assertNotIn(sid, st["vistos"])
        self.assertIn("sem vaga", st["oportunidades"][sid]["aguarda"])
        self.assertNotEqual(st["oportunidades"][sid].get("decisao"), "REJEITADA")
        self.limites_respeitados(st)

    def test_4c_rejeitada_por_vaga_entra_quando_a_vaga_abre_ainda_fresca(self):
        api = MultiOKX()
        t = NOW0 + 1800 - 660
        st, _ = self.corre(api, sinal("fraca", "AAA", atr=0.05))
        st, _ = self.corre(api, now=NOW0 + 900)
        cc = sinal("fraca", "CCC", t_fecho=t, atr=0.0025)
        st, _ = self.corre(api, cc, sinal("boa", "BBB", t_fecho=t, atr=0.0025), now=NOW0 + 1800)   # sem vaga: aguarda
        self.assertEqual([o["base"] for o in self.vivas(st)], ["AAA", "BBB"])
        api.fechar("AAA")                                                          # stop na corretora liberta a vaga
        st, _ = self.corre(api, cc, now=NOW0 + 1800 + 600)                         # ainda fresco (1H: 25 min)
        self.assertIn("CCC", [o["base"] for o in self.vivas(st)])
        self.assertIn(st["oportunidades"][cc["id_op"]].get("decisao"), ("ORDEM_ENVIADA", "EXECUTADA_REAL"))
        self.assertEqual(st["vistos"].count(cc["id_op"]), 1)
        self.limites_respeitados(st)

    def test_4d_sem_vaga_ate_ficar_velho_fica_perdido_uma_vez(self):
        api = MultiOKX()
        t = NOW0 + 1800 - 660
        st, _ = self.corre(api, sinal("fraca", "AAA", atr=0.05))
        st, _ = self.corre(api, now=NOW0 + 900)
        cc = sinal("fraca", "CCC", t_fecho=t, atr=0.0025)
        st, _ = self.corre(api, cc, sinal("boa", "BBB", t_fecho=t, atr=0.0025), now=NOW0 + 1800)
        self.assertEqual(len(self.vivas(st)), 2)
        for k in range(1, 4):                                                         # 0, 10, 20, 30 min depois
            st, _ = self.corre(api, cc, now=NOW0 + 1800 + 600 * k)
        st, _ = self.corre(api, cc, now=NOW0 + 1800 + 2400)
        r = st["oportunidades"][cc["id_op"]]
        self.assertEqual(r["decisao"], "REJEITADA")                                # velho: decisao final, uma so vez
        self.assertIn("sem vaga", r["motivo"])
        dia = st["resumo_oportunidades"]
        self.assertEqual(sum(v.get("por_categoria", {}).get(r["categoria"], 0) for v in dia.values()), 1)
        self.assertEqual(len(self.vivas(st)), 2)
        self.limites_respeitados(st)

    def test_4e_a_aguardar_e_sai_do_papel_fica_decidida(self):
        api = MultiOKX()
        t = NOW0 + 1800 - 660
        st, _ = self.corre(api, sinal("fraca", "AAA", atr=0.05))
        st, _ = self.corre(api, now=NOW0 + 900)
        cc = sinal("fraca", "CCC", t_fecho=t, atr=0.0025)
        st, _ = self.corre(api, cc, sinal("boa", "BBB", t_fecho=t, atr=0.0025), now=NOW0 + 1800)
        api.fechar("AAA")
        st, _ = self.corre(api, now=NOW0 + 2100)                                   # vaga livre, sinal ja nao esta no papel
        r = st["oportunidades"][cc["id_op"]]
        self.assertEqual(r["decisao"], "REJEITADA")
        self.assertIn("sem vaga", r["motivo"])
        self.limites_respeitados(st)

    def test_4b_duas_ao_mesmo_tempo_sem_posicoes_entram_as_duas_se_couberem(self):
        api = MultiOKX()
        st, _ = self.corre(api, sinal("boa", "AAA", atr=0.05), sinal("fraca", "BBB", atr=0.0025))
        vs = self.vivas(st)
        self.assertEqual([o["base"] for o in vs], ["AAA", "BBB"])                 # a melhor primeiro
        self.assertEqual([o["estado"] for o in vs], ["pendente", "pendente"])
        self.limites_respeitados(st)                                              # pendentes contam inteiras

    def test_5_correlacionadas(self):
        api = MultiOKX()
        # mesmo ativo por duas estrategias: nunca duas
        st, _ = self.corre(api, sinal("boa", "AAA", atr=0.05), sinal("fraca", "AAA", atr=0.0025))
        self.assertEqual(len(self.vivas(st)), 1)
        # mesma direcao em ativos diferentes: entram, mas o risco SOMADO (correlacao 1) cabe no orcamento de uma posicao
        st, _ = self.corre(api, sinal("fraca", "BBB", t_fecho=NOW0 + 900 - 660, atr=0.0025), now=NOW0 + 900)
        o = self.limites_respeitados(st)
        self.assertEqual(o["por_direcao"]["SHORT"], 0)
        self.assertLessEqual(o["por_direcao"]["LONG"], RT + 1e-9)
        pub = P.orcamento_publico(st, CFG)
        self.assertLessEqual(pub["risco_usado_pct"], 100.0)

    def test_6_minimo_acima_do_risco_disponivel(self):
        api = MultiOKX()
        api.spec[inst_id("BBB")]["minSz"] = "5"
        st, _ = self.corre(api, sinal("boa", "AAA", atr=0.05))
        st, _ = self.corre(api, sinal("fraca", "BBB", t_fecho=NOW0 + 900 - 660, atr=0.05), now=NOW0 + 900)
        self.assertEqual(len(self.vivas(st)), 1)
        mot = [x["motivo"] for x in st["sinais_perdidos"] if x["sinal"].startswith("fraca|BBB")][-1]
        self.assertIn("tamanho minimo", mot)
        self.assertEqual(len(api.posts("/trade/order")), 1)

    def test_7_sem_margem(self):
        api = MultiOKX(saldo=0.5)                                                 # margem minima nao chega
        st, _ = self.corre(api, sinal("boa", "AAA"))
        self.assertEqual(self.vivas(st), [])
        self.assertFalse(st["portas"]["saldo_usdc"]["ok"])
        self.assertEqual(api.posts("/trade/order"), [])

    def test_8_stop_ausente_bloqueia_novas_entradas(self):
        api = MultiOKX()
        st, _ = self.corre(api, sinal("boa", "AAA", atr=0.05))
        api.falha.add("order-algo")                                               # nao consegue repor
        st, _ = self.corre(api, now=NOW0 + 900)
        api.algos[inst_id("AAA")] = []                                            # o stop desapareceu
        api.falha.discard("order-algo")
        n = len(api.posts("/trade/order"))
        st, _ = self.corre(api, sinal("fraca", "BBB", t_fecho=NOW0 + 1800 - 660, atr=0.0025), now=NOW0 + 1800)
        self.assertFalse(st["portas"]["posicoes_protegidas"]["ok"])
        self.assertEqual(len(api.posts("/trade/order")), n)                       # nenhuma entrada nova
        self.assertEqual(len(api.posts("/trade/order-algo")), 1)                  # so a reposicao do stop da AAA

    def test_9_okx_indisponivel(self):
        api = MultiOKX()
        st, _ = self.corre(api, sinal("boa", "AAA", atr=0.05))
        st, _ = self.corre(api, now=NOW0 + 900)
        api.falha.add("positions")
        st, _ = self.corre(api, sinal("fraca", "BBB", t_fecho=NOW0 + 1800 - 660, atr=0.0025), now=NOW0 + 1800)
        self.assertEqual(len(api.posts("/trade/order")), 1)
        self.assertEqual([o["base"] for o in self.vivas(st)], ["AAA"])           # a falha nao apaga a posicao

    def test_10_posicao_do_piloto_na_okx_fora_do_registo(self):
        api = MultiOKX()
        st, _ = self.corre(api)
        # posicao "pil" na OKX que o estado nao tem (estado perdido): orfa -> fecho dela e suspensao; nada novo
        cl = P._cl("perdida|CCC|1")
        api.ordens[cl] = {"clOrdId": cl, "ordId": "x9", "instId": inst_id("CCC"), "side": "buy", "sz": "3", "px": "1",
                          "attachAlgoOrds": [{"attachAlgoClOrdId": cl[:28] + "slt", "slTriggerPx": "0.9"}]}
        api.pos[inst_id("CCC")] = {"pos": "3", "upl": "0", "instId": inst_id("CCC"), "posId": "px", "cTime": "1000"}
        api.fills.append({"instId": inst_id("CCC"), "clOrdId": cl, "ts": "1500"})
        st, _ = self.corre(api, sinal("boa", "AAA", t_fecho=NOW0 + 900 - 660), now=NOW0 + 900)
        self.assertTrue(st["suspenso"])
        self.assertEqual(api.posts("/trade/order"), [])

    def test_11_parcial_conta_so_o_executado(self):
        api = MultiOKX()
        api.fill[inst_id("AAA")] = "parcial"
        st, _ = self.corre(api, sinal("boa", "AAA", atr=0.005))
        risco_inteiro = self.vivas(st)[0]["risco_planeado"]
        st, _ = self.corre(api, now=NOW0 + 900)
        a = self.vivas(st)[0]
        self.assertLess(a["risco_planeado"], risco_inteiro)
        o = self.limites_respeitados(st)
        self.assertAlmostEqual(o["risco_aberto"], a["risco_planeado"])

    def test_12_timeout_no_envio_nao_duplica(self):
        api = MultiOKX()
        api.post_sem_resposta = True
        s = sinal("boa", "AAA", atr=0.05)
        st, _ = self.corre(api, s)
        self.assertEqual(self.vivas(st), [])                                      # sem resposta: nao assume
        api.post_sem_resposta = False
        # o mesmo sinal nunca volta a ser tratado (vistos) e a ordem que a OKX recebeu aparece como orfa do piloto
        st, _ = self.corre(api, s, now=NOW0 + 300)
        self.assertEqual(len(api.posts("/trade/order")), 1)

    def test_13_reinicio_com_duas_posicoes(self):
        api = MultiOKX()
        st, _ = self.corre(api, sinal("boa", "AAA", atr=0.05), sinal("fraca", "BBB", atr=0.0025))
        st, _ = self.corre(api, now=NOW0 + 900)
        self.assertEqual([o["estado"] for o in self.vivas(st)], ["aberta", "aberta"])
        with open(os.path.join(self.d, "piloto_estado.json")) as f:
            guardado = json.load(f)
        self.assertEqual(len(P.ativas(guardado)), 2)
        st, _ = self.corre(api, now=NOW0 + 1800)                                  # novo processo: le o ficheiro
        self.assertEqual([o["base"] for o in self.vivas(st)], ["AAA", "BBB"])
        self.assertTrue(all(o["stop_estado"] == "confirmado" for o in self.vivas(st)))
        self.assertEqual(len(api.posts("/trade/order")), 2)
        self.assertFalse(st["suspenso"])

    def test_14_nao_duplica_o_mesmo_ativo(self):
        api = MultiOKX()
        st, _ = self.corre(api, sinal("boa", "AAA", atr=0.05))
        st, _ = self.corre(api, sinal("fraca", "AAA", t_fecho=NOW0 + 900 - 660, atr=0.0025), now=NOW0 + 900)
        self.assertEqual(len(api.posts("/trade/order")), 1)
        mot = [x["motivo"] for x in st["sinais_perdidos"] if x["sinal"].startswith("fraca|AAA")][-1]
        self.assertIn("sem duplicar", mot)

    def test_15_posicao_de_outro_executor(self):
        api = MultiOKX()
        api.outros[inst_id("BBB")] = {"pos": "-7", "upl": "0", "instId": inst_id("BBB"), "posId": "outro", "cTime": "1"}
        st, _ = self.corre(api, sinal("boa", "AAA", atr=0.05), sinal("fraca", "BBB", atr=0.0025))
        self.assertEqual([o["base"] for o in self.vivas(st)], ["AAA"])
        st, _ = self.corre(api, now=NOW0 + 900)
        st, _ = self.corre(api, now=NOW0 + 7 * 3600)                              # tempo: fecha a AAA
        self.assertFalse(any(c[2] and c[2].get("instId") == inst_id("BBB") for c in api.chamadas if c[0] == "POST"))
        self.assertIn(inst_id("BBB"), api.outros)                                 # intacta

    def test_16_fecho_liberta_o_orcamento(self):
        api = MultiOKX()
        st, _ = self.corre(api, sinal("boa", "AAA", atr=0.005))                   # gasta quase tudo
        st, _ = self.corre(api, now=NOW0 + 900)
        self.assertGreater(P.orcamento(st, CFG)["risco_aberto"], 0.9 * RT)
        api.fechar("AAA")                                                         # stop na OKX
        st, _ = self.corre(api, now=NOW0 + 1800)
        self.assertEqual(P.orcamento(st, CFG)["risco_aberto"], 0)
        st, _ = self.corre(api, sinal("fraca", "BBB", t_fecho=NOW0 + 2700 - 660, atr=0.005), now=NOW0 + 2700)
        self.assertEqual([o["base"] for o in self.vivas(st)], ["BBB"])
        self.assertGreater(self.vivas(st)[0]["risco_planeado"], 0.9 * RT)

    def test_17_falha_de_uma_protecao_com_a_outra_aberta(self):
        api = MultiOKX()
        st, _ = self.corre(api, sinal("boa", "AAA", atr=0.05), sinal("fraca", "BBB", atr=0.0025))
        st, _ = self.corre(api, now=NOW0 + 900)
        api.algos[inst_id("BBB")] = []                                            # o stop da BBB desapareceu
        api.falha.add("order-algo")                                               # e nao da para repor
        st, msgs = self.corre(api, now=NOW0 + 1800)
        b = next(o for o in st["ops"] if o["base"] == "BBB")
        a = next(o for o in st["ops"] if o["base"] == "AAA")
        self.assertEqual(b["estado"], "a fechar")                                 # fecho de seguranca so da BBB
        self.assertEqual(a["estado"], "aberta")
        self.assertEqual(a["stop_estado"], "confirmado")
        self.assertTrue(st["bloqueio"])
        fechos = [c[2]["instId"] for c in api.chamadas if c[0] == "POST" and c[1].endswith("close-position")]
        self.assertEqual(fechos, [inst_id("BBB")])

    def test_18_limites_globais_nunca_passam(self):
        rng = random.Random(18)
        for rodada in range(25):
            api = MultiOKX(bases=("AAA", "BBB", "CCC", "DDD"))
            api.spec[inst_id("CCC")]["lotSz"] = str(rng.choice([1, 2, 3]))
            d = tempfile.mkdtemp()
            self.d, antigo = d, self.d
            try:
                t = NOW0
                for k in range(8):
                    sinais = [sinal(rng.choice(["boa", "fraca"]), b, t_fecho=t - 660, atr=rng.choice([0.0025, 0.005, 0.02, 0.05]))
                              for b in rng.sample(["AAA", "BBB", "CCC", "DDD"], rng.randint(0, 3))]
                    if rng.random() < 0.3 and api.pos:
                        api.fechar(rng.choice(list(api.pos)).split("-")[0])
                    st, _ = self.corre(api, *sinais, now=t)
                    self.limites_respeitados(st)
                    t += 1800
            finally:
                shutil.rmtree(d, ignore_errors=True)
                self.d = antigo


if __name__ == "__main__":
    unittest.main()


class ResumoContaOportunidades(Base):
    """(19/11) o resumo diario do funil conta cada oportunidade uma vez (a 18/11 dizia 4 executadas para 2)."""

    def test_executada_conta_uma_vez(self):
        api = MultiOKX()
        st, _ = self.corre(api, sinal("boa", "AAA", atr=0.05))                   # ORDEM_ENVIADA
        st, _ = self.corre(api, now=NOW0 + 900)                                   # EXECUTADA_REAL
        tot = sum((v.get("por_categoria") or {}).get("executada", 0) for v in st["resumo_oportunidades"].values())
        self.assertEqual(tot, 1)
        self.assertEqual(sum(v.get("X", 0) for v in st["resumo_oportunidades"].values()), 1)

    def test_decisoes_somam_o_numero_de_oportunidades(self):
        api = MultiOKX()
        st, _ = self.corre(api, sinal("fraca", "AAA", atr=0.05))
        st, _ = self.corre(api, now=NOW0 + 900)
        t = NOW0 + 1800 - 660
        st, _ = self.corre(api, sinal("fraca", "CCC", t_fecho=t, atr=0.0025), sinal("boa", "BBB", t_fecho=t, atr=0.0025),
                           now=NOW0 + 1800)
        for k in range(1, 5):
            st, _ = self.corre(api, sinal("fraca", "CCC", t_fecho=t, atr=0.0025), now=NOW0 + 1800 + 600 * k)
        decididas = sum(1 for r in st["oportunidades"].values() if r.get("decisao"))
        contadas = sum(v.get("X", 0) + v.get("B", 0) + v.get("A", 0) + v.get("C", 0) for v in st["resumo_oportunidades"].values())
        self.assertEqual(contadas, decididas)
