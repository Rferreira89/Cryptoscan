"""(06/11, P1) Ponta a ponta em MODO SOMBRA:
sinal TF-SHORT -> validacao (A1) -> tamanho -> ordem SHORT simulada -> stop -> acompanhamento -> fecho -> registo unico.
Prova: nenhuma ordem real; estado preservado depois de reinicio; sem duplicados; registo correto; real, papel e sombra
separados; falhas de estado, comunicacao e dados bloqueiam entradas novas."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import okx_short as S  # noqa: E402
import okx_sombra as W  # noqa: E402
import okx_tfshort as T  # noqa: E402
from engine import registo as G  # noqa: E402

DAY = 86400
CFG_OKX = {"real": True, "risco_pct": 2.0, "alavancagem": 10, "max_posicoes": 30, "recuo_real": True, "recuo_risco_pct": 1.0,
           "panico_real": False}
INFO_T = {"ctVal": 1.0, "minSz": 0.01, "lotSz": 0.01}
INFOS = {"AAA": {"inst": "AAA-USD_UM_XPERP-1", "ctVal": 1.0, "minSz": 0.01, "lotSz": 0.01, "alav_max": 20}}


def desce(n=240, p0=100.0):
    out, p = [], p0
    for k in range(n):
        p *= 0.997 * (1.02 if k % 2 else 0.98)
        out.append(p)
    return out


def tfs_com_posicao():
    """Estado real do paper TF-SHORT (o mesmo modulo da producao) com uma posicao aberta em AAA."""
    f = desce(); st = {}
    v = [{"t": k * DAY, "o": c, "h": c * 1.01, "l": c * 0.99, "c": c, "usd": 30e6} for k, c in enumerate(f)]
    T.correr(st, {"AAA": {"velas": v, "px": f[-1], "px_global": f[-1], "fund": [], "validado": True}}, 240 * DAY, {"AAA": INFO_T})
    assert "AAA" in st["conta"]["abertas"]
    return st, f[-1]


class Espiao:
    """Transporte 'real' de teste: regista tudo o que lhe chegar. Nunca deve receber escritas."""
    def __init__(self):
        self.pedidos = []

    def __call__(self, metodo, path, corpo=None):
        self.pedidos.append((metodo, path)); return {"code": "0", "data": []}


class PontaAPonta(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(); self.cam = os.path.join(self.tmp, "sombra.json")
        self.tfs, self.px = tfs_com_posicao()
        self.agora = 240 * DAY + 600

    def vela(self, c, h=None, l=None, t=None):
        return {"AAA": {"c": c, "h": h or c, "l": l or c, "t": t or self.agora - 5}}

    def test_fluxo_completo_com_reinicio_sem_duplicados_e_registo(self):
        self.assertIs(S.SHORT_REAL_PERMITIDO, False)
        # 1.a volta (inicializacao autorizada): entra em short na corretora sombra, com protecao
        est, ok, m = W.carregar(self.cam, iniciar=True)
        cli = W.CorretoraSombra({"precos": {"AAA-USD_UM_XPERP-1": self.px}})
        al = W.volta(self.tfs, est, ok, m, cli, self.vela(self.px), INFOS, CFG_OKX, 20.0, self.agora)
        self.assertTrue(any("short em AAA" in a for a in al), al)
        op = list(est["ops"].values())[0]
        self.assertEqual(op["estado"], "aberta"); self.assertGreater(op["stop"], op["px"])
        self.assertGreater(cli.pos["AAA-USD_UM_XPERP-1"], 0)                      # short aberto (simulado)
        self.assertEqual(len(cli.algos), 1); a = list(cli.algos.values())[0]
        self.assertEqual((a["side"], a["reduceOnly"]), ("buy", "true"))
        est["corretora_sombra"] = cli.foto(); W.guardar(self.cam, est)
        # reinicio: estado e corretora recuperados do ficheiro; a mesma posicao do TF-SHORT nao duplica
        est2, ok2, m2 = W.carregar(self.cam)
        self.assertTrue(ok2, m2); self.assertEqual(est2["ops"], est["ops"])
        cli2 = W.CorretoraSombra(est2["corretora_sombra"])
        W.volta(self.tfs, est2, ok2, m2, cli2, self.vela(self.px * 0.99, t=self.agora + 3600), INFOS, CFG_OKX, 20.0, self.agora + 3600)
        self.assertEqual(len(est2["ops"]), 1)
        self.assertEqual(sum(1 for k in cli2.ordens if not k.startswith("algo") and not k.endswith("f")), 1)
        # o preco sobe acima do stop: a protecao fecha na corretora sombra e a op vai para o registo unico
        stop = op["stop"]
        al3 = W.volta(self.tfs, est2, True, "ok", cli2, self.vela(stop * 1.01, h=stop * 1.02, t=self.agora + 7200),
                      INFOS, CFG_OKX, 20.0, self.agora + 7200)
        self.assertTrue(any("stop atingido" in a for a in al3), al3)
        self.assertEqual(list(est2["ops"].values())[0]["estado"], "fechada")
        self.assertAlmostEqual(cli2.pos["AAA-USD_UM_XPERP-1"], 0.0)
        reg = est2["registo"]; self.assertEqual(len(reg), 1)
        r = reg[0]
        self.assertEqual((r["origem"], r["classe"], r["estrategia"]), ("sombra", "sombra", "TF-SHORT sombra (P1)"))
        self.assertLess(r["R"], -0.9); self.assertGreater(r["R"], -1.2)            # perdeu ~1R mais custos
        self.assertIsNotNone(r["custos"]["comissao"])
        # real, papel e sombra nunca se somam
        real = G.op("H40", "real", "okx", "HUMA", "okx.real.hist", "9", {}, R=-1.0)
        with self.assertRaises(ValueError):
            G.metricas([r, real])
        self.assertEqual(G.metricas([r])["classe"], "sombra")

    def test_nenhuma_ordem_real_mesmo_ligado_ao_fluxo(self):
        espiao = Espiao()
        for cfg in ({}, {"short_real": True}):
            est, ok, m = W.carregar(self.cam, iniciar=True)
            al = W.volta(self.tfs, est, ok, m, espiao, self.vela(self.px), INFOS, CFG_OKX, 20.0, self.agora, cfg_exec=cfg)
            self.assertTrue(any("short real desligado" in a for a in al), al)
        self.assertEqual([p for p in espiao.pedidos if p[0] != "GET"], [])
        self.assertTrue(all(o["estado"] == "bloqueada" for o in est["ops"].values()))

    def test_estado_em_falta_ilegivel_ou_adulterado_bloqueia_entradas(self):
        est, ok, m = W.carregar(self.cam)                                             # sem inicializacao
        self.assertFalse(ok); self.assertIn("inicializacao", m)
        open(self.cam, "w").write("{lixo")
        self.assertFalse(W.carregar(self.cam)[1])
        W.guardar(self.cam, {"ops": {}, "fechadas": [], "registo": [], "alertas": []})
        c = json.load(open(self.cam)); c["estado"]["ops"]["X"] = {"estado": "aberta"}; json.dump(c, open(self.cam, "w"))
        est, ok, m = W.carregar(self.cam)
        self.assertFalse(ok); self.assertIn("adulterado", m)
        cli = W.CorretoraSombra({"precos": {"AAA-USD_UM_XPERP-1": self.px}})
        est = {"ops": {}, "fechadas": [], "registo": [], "alertas": []}
        al = W.volta(self.tfs, est, ok, m, cli, self.vela(self.px), INFOS, CFG_OKX, 20.0, self.agora)
        self.assertEqual(est["ops"], {}); self.assertTrue(any("sem entradas novas" in a for a in al))

    def test_falha_de_comunicacao_bloqueia_entradas_mas_continua_a_gerir(self):
        est, ok, m = W.carregar(self.cam, iniciar=True)
        cli = W.CorretoraSombra({"precos": {"AAA-USD_UM_XPERP-1": self.px}})
        W.volta(self.tfs, est, ok, m, cli, self.vela(self.px), INFOS, CFG_OKX, 20.0, self.agora)
        # segunda moeda no paper, mas a comunicacao falha nesta volta: nao entra; a AAA continua acompanhada
        tfs2 = json.loads(json.dumps(self.tfs)); b = dict(tfs2["conta"]["abertas"]["AAA"], t=self.agora)
        tfs2["conta"]["abertas"]["BBB"] = b
        infos = dict(INFOS, BBB={"inst": "BBB-USD_UM_XPERP-1", "ctVal": 1.0, "minSz": 0.01, "lotSz": 0.01})
        cli.precos["BBB-USD_UM_XPERP-1"] = self.px; cli.falhar.add("/api/v5/trade/order")
        velas = dict(self.vela(self.px), BBB={"c": self.px, "h": self.px, "l": self.px, "t": self.agora - 5})
        al = W.volta(tfs2, est, True, "ok", cli, velas, infos, CFG_OKX, 20.0, self.agora + 60)
        self.assertEqual(len(est["ops"]), 1); self.assertTrue(any("falha de comunicacao" in a for a in al), al)

    def test_dados_desatualizados_nao_entram(self):
        est, ok, m = W.carregar(self.cam, iniciar=True)
        cli = W.CorretoraSombra({"precos": {"AAA-USD_UM_XPERP-1": self.px}})
        W.volta(self.tfs, est, ok, m, cli, self.vela(self.px, t=self.agora - 3600), INFOS, CFG_OKX, 20.0, self.agora)
        self.assertEqual(est["ops"], {}); self.assertIn("desatualizados", est["ignoradas"][0]["motivo"])

    def test_saida_pela_regra_do_tfshort(self):
        est, ok, m = W.carregar(self.cam, iniciar=True)
        cli = W.CorretoraSombra({"precos": {"AAA-USD_UM_XPERP-1": self.px}})
        W.volta(self.tfs, est, ok, m, cli, self.vela(self.px), INFOS, CFG_OKX, 20.0, self.agora)
        tfs2 = json.loads(json.dumps(self.tfs)); tfs2["conta"]["abertas"] = {}            # o paper saiu da AAA
        al = W.volta(tfs2, est, True, "ok", cli, self.vela(self.px * 0.95, t=self.agora + 60), INFOS, CFG_OKX, 20.0, self.agora + 60)
        self.assertTrue(any("saída pela regra" in a for a in al), al)
        r = est["registo"][0]; self.assertEqual(r["motivo"], "regra"); self.assertGreater(r["R"], 0)
        self.assertFalse(cli.algos); self.assertAlmostEqual(cli.pos["AAA-USD_UM_XPERP-1"], 0.0)

    def test_parametros_por_validar_documentados(self):
        for k in ("ctVal / ctValCcy", "order-algo oco/conditional", "posSide", "financiamento"):
            self.assertIn(k, W.VALIDAR)

    def test_isolamento(self):
        raiz = os.path.join(os.path.dirname(__file__), "..")
        for f in os.listdir(os.path.join(raiz, ".github", "workflows")):
            self.assertNotIn("okx_sombra", open(os.path.join(raiz, ".github", "workflows", f), encoding="utf-8").read(), f)
            self.assertNotIn("okx_short", open(os.path.join(raiz, ".github", "workflows", f), encoding="utf-8").read(), f)


if __name__ == "__main__":
    unittest.main()
