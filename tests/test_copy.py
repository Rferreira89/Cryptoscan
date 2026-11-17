"""(17/11) CopyTrading: ranking (comportamentos perigosos, validacao temporal), SMART_COPY e volta completa com fontes
falsas (nenhum pedido sai daqui; nada aqui envia ordens)."""
import json
import os
import random
import shutil
import tempfile
import unittest

from tools.copy import correr as CR
from tools.copy import ranking as RK
from tools.copy import smart as SM

NOW = 1_800_000_000


def hist(n=60, media=0.004, alav=5, seed=1, dias=40, ativos=8, margem=10.0):
    rng = random.Random(seed)
    out = []
    for k in range(n):
        t = NOW - dias * 86400 + k * dias * 86400 // n
        out.append({"inst": f"A{k % ativos}-USDT-SWAP", "base": f"A{k % ativos}", "lado": "LONG" if k % 2 else "SHORT",
                    "t_abre": t, "t_fecha": t + 7200, "px_abre": 1.0, "px_fecha": 1.0, "alav": alav, "margem": margem,
                    "pnl_ratio": rng.gauss(media, 0.01) * alav, "id": str(k)})
    return out


def velas(n=40, sobe=True):
    return [{"t": NOW - (n - k) * 3600, "o": 1, "h": 1.01, "l": 0.99, "c": 1 + (0.001 * k if sobe else -0.001 * k)} for k in range(n)]


class Ranking(unittest.TestCase):
    def test_bom_aprovado_e_nao_so_por_roi(self):
        a = RK.avaliar({"fonte": "okx", "id": "x"}, hist())
        self.assertEqual(a["estado"], "APROVADO", a["motivos"] + a["perigos"])
        self.assertIn("validacao", a)

    def test_perigosos(self):
        self.assertEqual(RK.avaliar({}, hist(alav=50))["estado"], "REJEITADO")              # alavancagem
        h = hist()
        for i in range(1, len(h)):                                                       # dobra depois de perder
            if RK._ret(h[i - 1]) < 0:
                h[i]["margem"] = h[i - 1]["margem"] * 2
        self.assertEqual(RK.avaliar({}, h)["estado"], "REJEITADO")
        h = hist(media=-0.001)
        for o in h[:3]:
            o["pnl_ratio"] = 2.0                                                         # 3 operacoes extraordinarias
        self.assertIn("REJEITADO", RK.avaliar({}, h)["estado"])
        self.assertEqual(RK.avaliar({}, hist(ativos=1))["estado"], "REJEITADO")           # concentracao

    def test_drawdown_escondido_em_posicoes_abertas(self):
        pos = [{"base": "A1", "lado": "LONG", "upl_nocional": -0.08}]
        a = RK.avaliar({}, hist(), pos)
        self.assertEqual(a["estado"], "REJEITADO")
        self.assertIn("escondido", " ".join(a["perigos"]))

    def test_historico_insuficiente_e_validacao_negativa(self):
        self.assertNotEqual(RK.avaliar({}, hist(n=10))["estado"], "APROVADO")
        h = hist(n=60) [:40] + hist(n=20, media=-0.01, seed=3)
        for k, o in enumerate(h):
            o["t_fecha"] = NOW - 1000000 + k * 1000
        self.assertNotEqual(RK.avaliar({}, h)["estado"], "APROVADO")


class Fontes(unittest.TestCase):
    def test_campos_vazios_nao_partem(self):
        from unittest import mock
        from tools.copy import fontes as F
        lixo = [{"instId": "BTC-USDT-SWAP", "openTime": "", "openAvgPx": "1", "subPosId": "1", "posSide": "long", "lever": ""},
                {"instId": "BTC-USDT-SWAP", "openTime": "1", "openAvgPx": "", "subPosId": "2"}]
        with mock.patch.object(F, "okx", return_value=lixo):
            p = F.okx_posicoes("x")
            self.assertEqual(len(p), 1)
            self.assertIsNone(p[0]["t_abre"])
            self.assertEqual(F.okx_historico("x"), [])


class Smart(unittest.TestCase):
    TR = {"estado": "APROVADO", "validacao": {"r_medio": 0.002, "profit_factor": 1.2}}
    TOPO = {"estado": "APROVADO", "validacao": {"r_medio": 0.005, "profit_factor": 2.0}}

    def ctx(self, **kw):
        c = {"now": NOW, "xperps": {"BTC": "BTC-USD_UM_XPERP-1"}, "preco": 1.0, "velas": velas(), "consenso": 0, "ja_ha_copia": False}
        c.update(kw)
        return c

    def op(self, **kw):
        o = {"base": "BTC", "lado": "LONG", "px_abre": 1.0, "t_abre": NOW - 60}
        o.update(kw)
        return o

    def test_decisoes(self):
        self.assertEqual(SM.decidir(self.op(), self.TOPO, self.ctx())[0], "COPY_DIRECT")
        self.assertEqual(SM.decidir(self.op(), self.TR, self.ctx())[0], "CONFIRM_AND_COPY")          # tendencia a favor
        self.assertEqual(SM.decidir(self.op(lado="SHORT"), self.TR, self.ctx())[0], "SIGNAL_ONLY")  # contra a tendencia
        self.assertEqual(SM.decidir(self.op(lado="SHORT"), self.TR, self.ctx(consenso=1))[0], "CONFIRM_AND_COPY")
        self.assertEqual(SM.decidir(self.op(), {"estado": "REJEITADO", "perigos": ["x"]}, self.ctx())[0], "IGNORE")
        self.assertEqual(SM.decidir(self.op(), {"estado": "OBSERVAR", "motivos": []}, self.ctx())[0], "SIGNAL_ONLY")

    def test_copia_tardia_preco_duplicado_e_mercado(self):
        self.assertEqual(SM.decidir(self.op(t_abre=NOW - 700), self.TOPO, self.ctx())[0], "IGNORE")
        self.assertEqual(SM.decidir(self.op(), self.TOPO, self.ctx(preco=1.01))[0], "IGNORE")            # ja andou 1%
        self.assertEqual(SM.decidir(self.op(), self.TOPO, self.ctx(ja_ha_copia=True))[0], "IGNORE")
        self.assertEqual(SM.decidir(self.op(base="XYZ"), self.TOPO, self.ctx())[0], "SIGNAL_ONLY")
        d, _, pl = SM.decidir(self.op(lado="SHORT"), self.TOPO, self.ctx())
        self.assertEqual(d, "COPY_DIRECT")
        self.assertGreater(pl["stop"], 1.0)

    def test_custos_e_mapeamento_kpepe(self):
        fraco = {"estado": "APROVADO", "validacao": {"r_medio": 0.001, "profit_factor": 1.3}}
        d, m, _ = SM.decidir(self.op(), fraco, self.ctx())
        self.assertEqual(d, "SIGNAL_ONLY")
        self.assertIn("custos", m)
        from tools.copy import fontes as F
        self.assertEqual(F._base_hl("kPEPE"), ("PEPE", 0.001))
        self.assertEqual(F._base_hl("BTC"), ("BTC", 1.0))
        d, _, pl = SM.decidir(self.op(px_abre=1000.0, fator_px=0.001), self.TOPO, self.ctx())
        self.assertEqual(d, "COPY_DIRECT")                     # 1000 por lote de 1000 = 1,0 por unidade: preco viavel

    def test_bybit_eu_nunca_copia(self):
        self.assertEqual(SM.decidir_bybit({"lado": "SHORT", "base": "BTC"}, {"BTC"})[0], "IGNORE")
        self.assertEqual(SM.decidir_bybit({"lado": "LONG", "base": "BTC"}, {"BTC"})[0], "SIGNAL_ONLY")


class FontesFalsas:
    def __init__(self):
        self.pos = {"T1": []}

    def xperps_eea(self):
        return {"BTC": "BTC-USD_UM_XPERP-1"}

    def okx_posicoes(self, uc):
        return list(self.pos.get(uc, []))

    def hl_posicoes(self, a):
        return []

    def velas_1h(self, inst):
        return velas()

    def preco(self, inst):
        return 1.0


class Volta(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.d, "copy"))
        tr = {"t": NOW, "versao": CR.RANKING_VERSAO, "traders": {"okx:T1": {"estado": "APROVADO", "score": 1.0, "validacao": {"r_medio": 0.005, "profit_factor": 2.0},
                                               "motivos": [], "perigos": []}}}
        json.dump(tr, open(os.path.join(self.d, "copy", "traders.json"), "w"))
        self.f = FontesFalsas()

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def test_entrada_fecho_e_sem_copia_na_primeira_volta(self):
        self.f.pos["T1"] = [{"base": "BTC", "lado": "LONG", "px_abre": 1.0, "t_abre": NOW - 30, "id": "p0", "tamanho": 1}]
        r = CR.volta(self.d, NOW, fontes=self.f, log=lambda m: None)
        self.assertEqual(r["copias_para_okx"], 0)                      # ja estava aberta quando comecamos a seguir
        self.f.pos["T1"].append({"base": "BTC", "lado": "LONG", "px_abre": 1.0, "t_abre": NOW + 100, "id": "p1", "tamanho": 1})
        r = CR.volta(self.d, NOW + 120, fontes=self.f, log=lambda m: None)
        self.assertEqual(r["copias_para_okx"], 1)                      # nova entrada fresca de um aprovado: copia
        self.f.pos["T1"] = [{"base": "BTC", "lado": "LONG", "px_abre": 1.0, "t_abre": NOW + 230, "id": "p2", "tamanho": 1}]
        r = CR.volta(self.d, NOW + 240, fontes=self.f, log=lambda m: None)
        s = json.load(open(os.path.join(self.d, "copy", "sinais.json")))
        ids = [a["id_op"] for a in s["abertas"]]
        self.assertTrue(any("p2" in i for i in ids))                    # p1 fechou nesta volta: p2 pode ser copiada
        self.assertTrue(any(f["id_op"].endswith("p1") and f["motivo"] == "trader fechou" for f in s["fechadas"]))
        self.assertIn("copy:okx:T1", s["estrategias"])
        self.f.pos["T1"] = []
        CR.volta(self.d, NOW + 360, fontes=self.f, log=lambda m: None)
        s = json.load(open(os.path.join(self.d, "copy", "sinais.json")))
        self.assertEqual(s["abertas"], [])
        self.assertTrue(all(f["motivo"] == "trader fechou" for f in s["fechadas"]))


class Observador(Volta):
    def test_sem_duplicados_apos_reinicio_e_registo_de_consultas(self):
        self.f.pos["T1"] = []
        CR.volta(self.d, NOW, fontes=self.f, log=lambda m: None)
        self.f.pos["T1"] = [{"base": "BTC", "lado": "LONG", "px_abre": 1.0, "t_abre": NOW + 60, "id": "p1", "tamanho": 1}]
        r1 = CR.volta(self.d, NOW + 120, fontes=self.f, log=lambda m: None)
        st = json.load(open(os.path.join(self.d, "copy", "estado.json")))
        del st["posicoes"]["okx:T1"]["p1"]                        # reinicio a meio: o snapshot perdeu a posicao
        json.dump(st, open(os.path.join(self.d, "copy", "estado.json"), "w"))
        r2 = CR.volta(self.d, NOW + 240, fontes=self.f, log=lambda m: None)
        self.assertEqual((r1["oportunidades"], r2["oportunidades"]), (1, 0))   # o mesmo evento nao e tratado duas vezes
        st = json.load(open(os.path.join(self.d, "copy", "estado.json")))
        self.assertEqual([c["t"] for c in st["consultas"]], [NOW, NOW + 120, NOW + 240])
        self.assertEqual(st["consultas"][-1]["intervalo_s"], 120)

    def test_interrupcao_nao_copia_tarde_mas_fecha(self):
        self.f.pos["T1"] = [{"base": "BTC", "lado": "LONG", "px_abre": 1.0, "t_abre": NOW + 60, "id": "p1", "tamanho": 1}]
        CR.volta(self.d, NOW, fontes=self.f, log=lambda m: None)
        CR.volta(self.d, NOW + 120, fontes=self.f, log=lambda m: None)
        self.f.pos["T1"].append({"base": "BTC", "lado": "LONG", "px_abre": 1.0, "t_abre": NOW + 200, "id": "p2", "tamanho": 1})
        r = CR.volta(self.d, NOW + 3000, fontes=self.f, log=lambda m: None)     # 48 min sem consultas
        self.assertEqual(r["copias_para_okx"], 0)
        st = json.load(open(os.path.join(self.d, "copy", "estado.json")))
        self.assertTrue(st["recuperacao"])


class PercursoCompleto(unittest.TestCase):
    """Trader -> deteccao -> SMART_COPY -> sinais.json -> piloto -> ordem (OKX falsa) -> execucao -> trader fecha -> fecho."""
    def test_long_e_short(self):
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
        import piloto_okx as P
        from tests import test_piloto_okx as TP
        for lado, side in (("LONG", "buy"), ("SHORT", "sell")):
            d = tempfile.mkdtemp()
            os.makedirs(os.path.join(d, "copy"))
            json.dump({"t": NOW, "versao": CR.RANKING_VERSAO, "traders": {"okx:T1": {"estado": "APROVADO", "score": 1, "motivos": [],
                       "perigos": [], "validacao": {"r_medio": 0.005, "profit_factor": 2}}}}, open(os.path.join(d, "copy", "traders.json"), "w"))
            f = FontesFalsas()
            f.xperps_eea = lambda: {"ABC": TP.INST}
            f.pos["T1"] = []
            CR.volta(d, TP.NOW0 - 240, fontes=f, log=lambda m: None)
            f.pos["T1"] = [{"base": "ABC", "lado": lado, "px_abre": 1.0, "t_abre": TP.NOW0 - 100, "id": "p1", "tamanho": 1}]
            r = CR.volta(d, TP.NOW0 - 60, fontes=f, log=lambda m: None)
            self.assertEqual(r["copias_para_okx"], 1, lado)
            sin = json.load(open(os.path.join(d, "copy", "sinais.json")))
            api = TP.FakeOKX()
            kw = dict(registo={"t": TP.NOW0, "estrategias": {}}, papel={"t": TP.NOW0, "abertas": [], "fechadas": []}, isolado=True, cifra_ok=True)
            st, _ = P.ciclo(api, d, now=TP.NOW0, copy=sin, **kw)
            self.assertEqual(api.posts("/trade/order")[0][2]["side"], side)
            st, _ = P.ciclo(api, d, now=TP.NOW0 + 120, copy=sin, **kw)
            self.assertEqual(st["aberta"]["estado"], "aberta")
            self.assertTrue(st["aberta"]["stop_confirmado"])
            f.pos["T1"] = []
            CR.volta(d, TP.NOW0 + 200, fontes=f, log=lambda m: None)
            sin = json.load(open(os.path.join(d, "copy", "sinais.json")))
            st, _ = P.ciclo(api, d, now=TP.NOW0 + 240, copy=sin, **kw)
            self.assertTrue(api.posts("close-position"), lado)
            st, _ = P.ciclo(api, d, now=TP.NOW0 + 360, copy=sin, **kw)
            self.assertEqual(st["ops"][-1]["estado"], "fechada")
            shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
