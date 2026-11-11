"""(11/11) Executor TF-SHORT (preparado, NAO ativo): OKX falsa em memoria. Short com stop anexado, sem duplicados
num reinicio, adocao de posicoes sem registo, fecho so reduz, falhas transitorias e recusas, alerta sem stop."""
import unittest

from tools import okx_tfshort_exec as X

INFO = {"DOGE": {"inst": "DOGE-USD_UM_XPERP-1", "ctVal": 10.0, "minSz": 1.0, "lotSz": 1.0, "tick": 0.00001, "lever": 20},
        "SUI": {"inst": "SUI-USD_UM_XPERP-1", "ctVal": 1.0, "minSz": 1.0, "lotSz": 1.0, "tick": 0.0001, "lever": 20}}
SIN = {"DOGE": {"t": 1793923200, "entrada": 0.0716, "atr_pct": 0.05, "w": 0.09}}
CFG = {"tfshort_real": True}


class OKXFalsa:
    def __init__(self):
        self.pos, self.algo, self.ordens, self.pedidos, self.falhar = {}, set(), {}, [], set()

    def __call__(self, metodo, caminho, corpo):
        self.pedidos.append((metodo, caminho, corpo))
        if caminho in self.falhar:
            return {"code": "rede", "msg": "TimeoutError"}
        if caminho.startswith("/api/v5/account/positions"):
            return {"code": "0", "data": [{"instId": i, "pos": str(q), "avgPx": "0.0716"} for i, q in self.pos.items()]}
        if caminho.startswith("/api/v5/trade/orders-algo-pending"):
            return {"code": "0", "data": [{"instId": i} for i in self.algo]}
        if caminho == "/api/v5/account/set-leverage":
            return {"code": "0", "data": [{}]}
        if caminho == "/api/v5/trade/order" and metodo == "POST":
            cl = corpo["clOrdId"]
            if cl in self.ordens:
                return {"code": "1", "data": [{"sCode": "51016", "sMsg": "Duplicated clOrdId"}]}
            self.ordens[cl] = corpo
            n = float(corpo["sz"])
            if corpo["side"] == "sell":
                self.pos[corpo["instId"]] = self.pos.get(corpo["instId"], 0) - n
                if corpo.get("attachAlgoOrds"):
                    self.algo.add(corpo["instId"])
            else:
                self.pos[corpo["instId"]] = self.pos.get(corpo["instId"], 0) + n
                if not self.pos[corpo["instId"]]:
                    self.pos.pop(corpo["instId"]); self.algo.discard(corpo["instId"])
            return {"code": "0", "data": [{"sCode": "0", "ordId": f"o{len(self.ordens)}"}]}
        if caminho.startswith("/api/v5/trade/order?"):
            cl = caminho.split("clOrdId=")[-1] if "clOrdId=" in caminho else None
            return {"code": "0", "data": [{"ordId": "oX", "state": "filled"}]} if cl in self.ordens else {"code": "0", "data": [{"state": "canceled"}]}
        if caminho.startswith("/api/v5/trade/fills-history"):
            return {"code": "0", "data": [{"side": "buy", "fillPx": "0.08", "fillSz": "2", "ts": str(10 ** 13)}]}
        return {"code": "0", "data": []}


class Executor(unittest.TestCase):
    def test_desligado_nao_escreve(self):
        okx, R = OKXFalsa(), {}
        X.volta(R, SIN, INFO, 20.0, okx, {"tfshort_real": False}, now=1)
        self.assertFalse([p for p in okx.pedidos if p[0] == "POST"])

    def test_short_com_stop_e_sem_duplicado_no_reinicio(self):
        okx, R = OKXFalsa(), {}
        X.volta(R, SIN, INFO, 20.0, okx, CFG, now=1)
        envio = [p for p in okx.pedidos if p[1] == "/api/v5/trade/order"]
        self.assertEqual(len(envio), 1)
        self.assertEqual(envio[0][2]["side"], "sell")
        self.assertTrue(envio[0][2]["attachAlgoOrds"][0]["slTriggerPx"])
        X.volta(R, SIN, INFO, 20.0, okx, CFG, now=2)            # segunda volta: ja ha op
        self.assertEqual(len([p for p in okx.pedidos if p[1] == "/api/v5/trade/order"]), 1)
        self.assertEqual(R["ops"]["DOGE"]["estado"], "aberta")
        R2 = {}                                                  # reinicio com estado perdido: a OKX ja tem a ordem
        X.volta(R2, SIN, INFO, 20.0, okx, CFG, now=3)
        self.assertEqual(okx.pos["DOGE-USD_UM_XPERP-1"], -2.0)   # nunca dobra a posicao
        self.assertEqual(R2["ops"]["DOGE"]["ordId"], "oX")       # adotou pelo clOrdId (51016)

    def test_posicao_sem_registo_e_adotada(self):
        okx, R = OKXFalsa(), {"universo": ["SUI"]}
        okx.pos["SUI-USD_UM_XPERP-1"] = -3.0
        okx.algo.add("SUI-USD_UM_XPERP-1")
        X.volta(R, {}, INFO, 20.0, okx, CFG, now=5)
        self.assertTrue(R["ops"]["SUI"]["adotada"])

    def test_fecho_pela_regra_so_reduz_e_regista(self):
        okx, R = OKXFalsa(), {}
        X.volta(R, SIN, INFO, 20.0, okx, CFG, now=1)
        X.volta(R, SIN, INFO, 20.0, okx, CFG, now=2)
        X.volta(R, {}, INFO, 20.0, okx, CFG, now=3)             # saiu do livro do papel: fecha
        fecho = [p for p in okx.pedidos if p[1] == "/api/v5/trade/order" and p[2]["side"] == "buy"]
        self.assertEqual(len(fecho), 1)
        self.assertTrue(fecho[0][2]["reduceOnly"])
        X.volta(R, {}, INFO, 20.0, okx, CFG, now=4)
        self.assertNotIn("DOGE", R["ops"])
        self.assertEqual(R["hist"][-1]["motivo"], "regra")
        self.assertAlmostEqual(R["hist"][-1]["saida"], 0.08)

    def test_stop_na_okx_fecha_o_registo(self):
        okx, R = OKXFalsa(), {}
        X.volta(R, SIN, INFO, 20.0, okx, CFG, now=1)
        X.volta(R, SIN, INFO, 20.0, okx, CFG, now=2)
        okx.pos.pop("DOGE-USD_UM_XPERP-1"); okx.algo.discard("DOGE-USD_UM_XPERP-1")    # o stop executou
        X.volta(R, SIN, INFO, 20.0, okx, CFG, now=3)
        self.assertIn("stop", R["hist"][-1]["motivo"])
        X.volta(R, SIN, INFO, 20.0, okx, CFG, now=4)            # o mesmo sinal nao volta a entrar
        self.assertEqual(len([p for p in okx.pedidos if p[1] == "/api/v5/trade/order" and p[2]["side"] == "sell"]), 1)

    def test_sem_stop_alerta(self):
        okx, R = OKXFalsa(), {}
        X.volta(R, SIN, INFO, 20.0, okx, CFG, now=1)
        okx.algo.clear()
        msgs = X.volta(R, SIN, INFO, 20.0, okx, CFG, now=2)
        self.assertTrue(any("SEM stop" in m for m in msgs))

    def test_falha_de_leitura_nao_mexe(self):
        okx, R = OKXFalsa(), {}
        okx.falhar.add("/api/v5/account/positions?instType=FUTURES")
        msgs = X.volta(R, SIN, INFO, 20.0, okx, CFG, now=1)
        self.assertFalse([p for p in okx.pedidos if p[0] == "POST"])
        self.assertTrue(any("não consegui ler" in m for m in msgs))

    def test_falha_transitoria_no_envio_tenta_depois(self):
        okx, R = OKXFalsa(), {}
        okx.falhar.add("/api/v5/trade/order")
        X.volta(R, SIN, INFO, 20.0, okx, CFG, now=1)
        self.assertNotIn("DOGE", R.get("ops", {}))
        self.assertNotIn("tfDOGE93923200", R.get("tentados", []))
        okx.falhar.clear()
        X.volta(R, SIN, INFO, 20.0, okx, CFG, now=2)
        self.assertIn("DOGE", R["ops"])

    def test_recusa_definitiva_nao_repete(self):
        okx, R = OKXFalsa(), {}
        orig = okx.__call__
        def recusa(m, c, b):
            if c == "/api/v5/trade/order" and m == "POST":
                okx.pedidos.append((m, c, b))
                return {"code": "1", "data": [{"sCode": "51008", "sMsg": "Insufficient margin"}]}
            return orig(m, c, b)
        X.volta(R, SIN, INFO, 20.0, recusa, CFG, now=1)
        X.volta(R, SIN, INFO, 20.0, recusa, CFG, now=2)
        self.assertEqual(len([p for p in okx.pedidos if p[1] == "/api/v5/trade/order"]), 1)
        self.assertEqual(R["recusas"][0]["codigo"], "51008")

    def test_nao_ligado_a_producao(self):
        import os
        raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for f in ("tools/okx_exec.py", "tools/okx_agente.py", ".github/workflows/okx-agente.yml", "okx_config.json"):
            with open(os.path.join(raiz, f), encoding="utf-8") as fh:
                self.assertNotIn("tfshort_exec", fh.read())
        with open(os.path.join(raiz, "okx_config.json"), encoding="utf-8") as fh:
            self.assertNotIn("tfshort_real", fh.read())


if __name__ == "__main__":
    unittest.main()
