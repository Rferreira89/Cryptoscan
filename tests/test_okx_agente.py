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
                return {"code": "0", "data": [{"state": "live"}]}
            return {"code": "0", "data": []}
        st = {}
        sig = {"t_sig": now - H4, "lim": 0.0236, "atr": 0.001, "tipo": "mercado"}
        with mock.patch.object(self.E, "_chaves", return_value=("k", "s", "p")), mock.patch.object(self.E, "privado", privado), \
                mock.patch.object(self.E, "cfg", return_value=dict(self.E.CFG_PADRAO, real=True)), \
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


H4 = 14400
