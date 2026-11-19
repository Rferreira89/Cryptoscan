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
        self.assertEqual(a["modo"], "real")                                    # OK do Rui a 19/11 15:53
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


class FechoPedidoPeloRui(unittest.TestCase):
    """(19/11) "Podes fechar a posicao na Bybit e comecar a acumulacao": fecho pelo caminho protegido do executor; o
    registo so fecha com o preco de saida confirmado; a acumulacao so arranca quando ja nao ha trading aberto."""

    def test_pedido_manual_fechar_chega_ao_fecho_protegido(self):
        from unittest import mock
        from engine import executor as X
        chamadas = []
        with mock.patch.dict(os.environ, {"EXEC_ACAO": "fechar:XLM-SHORT_TURTLE-1794673840"}), \
                mock.patch.object(X, "do_close", lambda st, r, ex, now, send, why="": chamadas.append((r["op"], why)) or "ok"):
            reqs = []
            forced = os.environ["EXEC_ACAO"]
            acao, _, op = forced.partition(":")
            self.assertIn(acao, ("comprar", "vender", "fechar"))
        src = open(X.__file__).read()
        self.assertIn('if acao in ("comprar", "vender", "fechar") and op.strip():', src)
        self.assertIn('why="fecho pedido pelo Rui', src)

    def estado(self):
        rec = {"id": "XLM-SHORT_TURTLE-1", "mode": "REAL", "executed": True, "status": "OPEN", "side": "SHORT",
               "asset": "XLM", "stop": 0.15364}
        sig = {"position": {"entry": 0.1374, "stop0": 0.15364, "side": "SHORT", "closed": False}, "status": "TRIGGERED"}
        return {"ledger": [rec], "signals": {"XLM-SHORT_TURTLE-1": sig}}

    def test_registo_fecha_com_a_saida_confirmada(self):
        st = self.estado()
        ex = {"ops": {"XLM-SHORT_TURTLE-1": {"status": "fechada", "saida": 0.1380, "fechado": NOW,
                                             "motivo": "fecho pedido pelo Rui (a Bybit passa a acumulação)"}}, "feitos": []}
        execucao.apply(st, ex)
        rec = st["ledger"][0]
        self.assertEqual((rec["status"], rec["exit"], rec["reason"]), ("CLOSED", 0.138, "MANUAL"))
        self.assertAlmostEqual(rec["result_r"], round((0.1374 - 0.138) / (0.15364 - 0.1374), 3))
        self.assertTrue(st["signals"]["XLM-SHORT_TURTLE-1"]["position"]["closed"])

    def test_sem_preco_de_saida_nao_fecha(self):
        st = self.estado()
        ex = {"ops": {"XLM-SHORT_TURTLE-1": {"status": "fechada", "motivo": "fecho pedido pelo Rui"}}, "feitos": []}
        execucao.apply(st, ex)
        self.assertEqual(st["ledger"][0]["status"], "OPEN")

    def test_acumulacao_so_arranca_sem_trading_aberto(self):
        from engine import acumulacao as AC
        tk = {"BTC": [60000, 59990, 60010, 1]}
        cfg = {"bybit_modo": "acumulacao", "acumulacao": {"modo": "real", "pesos": {"BTC": 1.0}, "ordem_min_usdc": 5}}
        st = dict(self.estado(), conta_saldos={"t": 1, "m": {}}, bybit_tickers={"t": 1, "m": tk},
                  conta_livre={"t": 1, "usdc": 30.0}, capital_confirmado=True, bybit_modo="acumulacao",
                  auto_ops={"XLM-SHORT_TURTLE-1": "aberta"})
        AC.atualizar(st, cfg, NOW, None)
        self.assertEqual(st.get("exec_req") or [], [])                      # XLM aberta: nada
        st["auto_ops"]["XLM-SHORT_TURTLE-1"] = "fechada"                      # executor fechou, registo ainda nao
        AC.atualizar(st, cfg, NOW + 60, None)
        self.assertEqual([r["acao"] for r in st["exec_req"]], ["acumular"])
