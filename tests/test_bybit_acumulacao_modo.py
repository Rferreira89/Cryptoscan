"""(19/11, decisao do Rui) Bybit UE em modo acumulacao: nenhuma entrada de trading nova, as posicoes abertas seguem as
suas regras (fechos e saidas passam), e as decisoes dos campeoes continuam a chegar a OKX."""
import json
import os
import sys
import unittest

from engine import config, execucao, ledger

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import okx_exec as E  # noqa: E402

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOW = 1_800_000_000


class Entradas(unittest.TestCase):
    def st(self):
        return {"bybit_modo": "acumulacao", "capital_confirmado": True}

    def test_entradas_de_trading_bloqueadas(self):
        st = self.st()
        for acao in sorted(execucao.ENTRADAS):
            self.assertIsNone(execucao.request(st, acao, f"X-{acao}", NOW))
        self.assertEqual(st.get("exec_req") or [], [])
        self.assertTrue(all("acumulação" in b["motivo"] for b in st["entradas_bloqueadas"]))

    def test_fechos_e_protecoes_das_abertas_passam(self):
        st = self.st()
        for acao in ("fechar", "breakeven"):
            self.assertIsNotNone(execucao.request(st, acao, "XLM-SHORT_TURTLE-1794673840", NOW))
        self.assertEqual([r["acao"] for r in st["exec_req"]], ["fechar", "breakeven"])

    def test_em_trading_continua_como_antes(self):
        st = {"bybit_modo": "trading", "capital_confirmado": True}
        self.assertIsNotNone(execucao.request(st, "comprar", "A-1", NOW))

    def test_config_de_producao(self):
        c = config.load(os.path.join(RAIZ, "config.json"))
        self.assertEqual(c["bybit_modo"], "acumulacao")
        a = c["acumulacao"]
        self.assertEqual(a["modo"], "sombra")                                  # real so com o OK do Rui
        self.assertAlmostEqual(sum(a["pesos"].values()), 1.0)
        self.assertEqual(a["pesos"]["BTC"], 0.70)
        self.assertTrue(all(w <= a["max_alt_pct"] / 100 + 1e-9 for k, w in a["pesos"].items() if k not in ("BTC", "ETH")))
        # limites do trading nao mudaram
        self.assertEqual((c["piloto"]["teto_pct"], c["piloto"]["teto_agregado_pct"], c["piloto"]["max_posicoes"]), (5, 5, 2))


class Decisoes(unittest.TestCase):
    def test_decisao_real_passa_a_papel_marcada(self):
        from engine import scanner
        d = scanner.para_acumulacao({"mode": "REAL", "decision": "SHORT", "notes": []}, "acumulacao")
        self.assertEqual((d["mode"], d["espelho_okx"]), ("PAPER", True))
        self.assertIn("segue para a OKX", d["notes"][-1])
        self.assertEqual(scanner.para_acumulacao({"mode": "REAL"}, "trading"), {"mode": "REAL"})
        self.assertEqual(scanner.para_acumulacao({"mode": "PAPER"}, "acumulacao"), {"mode": "PAPER"})


class EspelhoOKX(unittest.TestCase):
    def registo(self, espelho, mode="PAPER"):
        st = {"ledger": [], "signals": {}}
        sig = {"asset": "SEI", "pair": "SEIUSDC", "strategy": "SHORT_TURTLE", "mode": mode, "score": 70,
               "direction": "SHORT", "plan": {"entry_zone": [0.2, 0.2], "stop": 0.22, "tp": [0.17], "rr": 1.5,
                                              "risk_pct": 2.5, "position_pct": 20, "max_hold_s": 1728000}}
        if espelho:
            sig["espelho_okx"] = True
        ledger.apply(st, [{"event": "ISSUED", "id": "SEI-SHORT_TURTLE-1", "t": NOW, "signal": sig}])
        st["signals"]["SEI-SHORT_TURTLE-1"] = {"plan": sig["plan"]}
        return st

    def test_decisao_do_campeao_em_papel_chega_a_okx(self):
        st = self.registo(True)
        self.assertTrue(st["ledger"][0]["espelho_okx"])
        out = E.espelho_sinais(st, NOW + 60)
        self.assertEqual([(a, s["lado"], s["estrategia"]) for a, s in out], [("SEI", "SHORT", "SHORT_TURTLE")])
        self.assertEqual(out[0][1]["hold_s"], 1728000)

    def test_papel_normal_nao_chega(self):
        self.assertEqual(E.espelho_sinais(self.registo(False), NOW + 60), [])

    def test_real_continua_a_chegar(self):
        self.assertEqual(len(E.espelho_sinais(self.registo(False, mode="REAL"), NOW + 60)), 1)


if __name__ == "__main__":
    unittest.main()
