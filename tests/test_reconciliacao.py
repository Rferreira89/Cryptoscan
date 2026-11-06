"""(06/11) Conferencia incremental das operacoes reais, sem limite de dias (o caso da SEI de 23/10): operacoes antigas,
dados parciais, fechos parciais e totais, protecao, custos, sem duplicados, falhas da API e reinicios."""
import unittest
from engine import account as A
from engine import ledger as L
from engine import publico

DIA = 86400
AGORA = 1794000000
T_SEI = AGORA - 25 * DIA                                # emitida ha 25 dias (muito para la dos 6,5)


def sei(**kw):
    r = {"id": "SEI-SHORT_TURTLE-1", "kind": "4H", "asset": "SEI", "pair": "SEI/USDC", "side": "SHORT", "mode": "REAL",
         "status": "CLOSED", "executed": True, "issued_at": T_SEI, "closed_at": T_SEI + 6 * DIA, "stop": 0.065596,
         "entry": 0.05727, "result_r": 1.307, "real_r": None, "real": {"fechada": False, "n": 1}}
    r.update(kw)
    return r


def ex(i, t, lado, q, px, fee=0.0, moeda="USDC", tipo=None):
    return {"execId": f"e{i}", "execTime": str(int(t * 1000)), "side": lado, "execQty": str(q), "execPrice": str(px),
            "execFee": str(fee), "feeCurrency": moeda, "stopOrderType": tipo or ""}


class Bybit:
    """Leitura falsa: execucoes por par; pode falhar em janelas escolhidas; conta as chamadas."""
    def __init__(self, execs, falhar_antes_de=None):
        self.execs, self.falhar_antes_de, self.chamadas = execs, falhar_antes_de, []

    def ler(self, sym, a, b):
        self.chamadas.append((sym, a, b))
        if self.falhar_antes_de and b > self.falhar_antes_de:
            raise A.LeituraFalhou("timeout")
        return [e for e in self.execs.get(sym, []) if a <= int(e["execTime"]) / 1000 < b]


def correr(led, by, juros=0.0, protecao=None, agora=AGORA):
    res = A.reconciliar_pendentes(led, agora, ler=by.ler, juros=lambda m, a, b: juros,
                                  protecao=lambda s, a, b: protecao if protecao is not None else [])
    L.apply_real(led, res)
    return res


class Antigas(unittest.TestCase):
    def test_operacao_antiga_com_dados_parciais_volta_a_ser_conferida_e_fecha(self):
        led = [sei()]
        by = Bybit({"SEIUSDC": [ex(1, T_SEI + 120, "Sell", 100, 0.05715, fee=0.0143),
                                ex(2, T_SEI + 9 * DIA, "Buy", 100, 0.0470, fee=0.0118, tipo="TakeProfit")]})
        correr(led, by, juros=0.4, protecao=[{"tipo": "TakeProfit", "estado": "Filled"}, {"tipo": "StopLoss", "estado": "Cancelled"}])
        r = led[0]["real"]
        self.assertTrue(r["fechada"]); self.assertEqual(r["estado"], "fechada"); self.assertEqual(r["saida_por"], ["TakeProfit"])
        self.assertEqual(len(r["execs_valores"]), 2)
        pnl = 100 * 0.05715 - 100 * 0.0470 - 0.0143 - 0.0118 - 0.4 * 0.05715
        self.assertAlmostEqual(r["pnl_usdc"], pnl, places=6)
        risco = 100 * (0.065596 - 0.05715)
        self.assertAlmostEqual(r["risco_usdc"], risco, places=6)
        self.assertAlmostEqual(led[0]["real_r"], round(pnl / risco, 2))
        self.assertEqual(led[0]["real_r_fonte"], "risco inicial real")
        self.assertNotEqual(led[0]["real_r"], 1.307)                       # nunca o R do sinal
        self.assertEqual(r["protecao"][1], {"tipo": "StopLoss", "estado": "Cancelled"})

    def test_sem_juros_conhecidos_num_short_fica_incompleta(self):
        led = [sei()]
        by = Bybit({"SEIUSDC": [ex(1, T_SEI + 120, "Sell", 100, 0.05715), ex(2, T_SEI + 9 * DIA, "Buy", 100, 0.047)]})
        res = A.reconciliar_pendentes(led, AGORA, ler=by.ler, juros=lambda *a: None, protecao=lambda *a: None)
        L.apply_real(led, res)
        r = led[0]["real"]
        self.assertTrue(r["fechada"]); self.assertTrue(r["custos_incompletos"]); self.assertIsNone(r["pnl_usdc"])
        self.assertIsNotNone(r["pnl_usdc_sem_juros"]); self.assertIsNone(led[0]["real_r"])
        self.assertIn(led[0], A.pendentes(led))                             # continua na lista para completar os custos

    def test_long_sem_emprestimo_nao_precisa_de_juros(self):
        led = [sei(id="ENA-PULLBACK-1", asset="ENA", pair="ENA/USDC", side="LONG", stop=0.40, real=None)]
        by = Bybit({"ENAUSDC": [ex(1, T_SEI + 60, "Buy", 10, 0.50, fee=0.01, moeda="ENA"), ex(2, T_SEI + DIA, "Sell", 9.99, 0.55, fee=0.0137)]})
        correr(led, by, juros=None)
        self.assertTrue(led[0]["real"]["fechada"]); self.assertFalse(led[0]["real"]["custos_incompletos"])
        self.assertIsNotNone(led[0]["real_r"])


class Parciais(unittest.TestCase):
    def test_fecho_parcial_e_depois_total(self):
        led = [sei()]
        execs = [ex(1, T_SEI + 120, "Sell", 100, 0.05715), ex(2, T_SEI + 3 * DIA, "Buy", 40, 0.050, tipo="TakeProfit")]
        by = Bybit({"SEIUSDC": execs})
        correr(led, by, agora=T_SEI + 5 * DIA)
        r = led[0]["real"]
        self.assertEqual((r["estado"], r["pct_fechado"], r["fechada"]), ("parcial", 40.0, False)); self.assertIsNone(led[0]["real_r"])
        execs.append(ex(3, T_SEI + 12 * DIA, "Buy", 60, 0.046, tipo="StopLoss"))
        correr(led, by)
        r = led[0]["real"]
        self.assertEqual((r["estado"], r["pct_fechado"]), ("fechada", 100.0)); self.assertEqual(r["saida_por"], ["StopLoss", "TakeProfit"])
        self.assertAlmostEqual(r["preco_saida"], (40 * 0.050 + 60 * 0.046) / 100)

    def test_aberta_sem_saidas(self):
        led = [sei(status="OPEN")]
        correr(led, Bybit({"SEIUSDC": [ex(1, T_SEI + 120, "Sell", 100, 0.05715)]}))
        self.assertEqual(led[0]["real"]["estado"], "aberta")


class SemDuplicados(unittest.TestCase):
    def test_reinicio_e_janelas_repetidas_nao_duplicam(self):
        led = [sei()]
        execs = [ex(1, T_SEI + 120, "Sell", 100, 0.05715)]
        by = Bybit({"SEIUSDC": execs})
        correr(led, by, agora=T_SEI + 2 * DIA)
        cursor = led[0]["real"]["lido_ate"]
        led2 = __import__("json").loads(__import__("json").dumps(led))       # "reinicio": estado gravado e lido
        by.chamadas.clear()
        execs.append(ex(2, T_SEI + 9 * DIA, "Buy", 100, 0.047))
        correr(led2, by)
        self.assertGreaterEqual(by.chamadas[0][1], cursor)                   # so le o que falta
        self.assertEqual(len(led2[0]["real"]["execs_valores"]), 2)
        res = A.reconciliar_pendentes(led2, AGORA + DIA, ler=Bybit({"SEIUSDC": execs + execs}).ler,
                                      juros=lambda *a: 0.0, protecao=lambda *a: [])
        self.assertEqual(res, {})                                           # ja fechada e completa: nao volta a ler

    def test_execucao_repetida_na_api_conta_uma_vez(self):
        led = [sei()]
        e = ex(1, T_SEI + 120, "Sell", 100, 0.05715)
        correr(led, Bybit({"SEIUSDC": [e, dict(e)]}))
        self.assertEqual(led[0]["real"]["n"], 1)

    def test_nao_mistura_com_a_operacao_seguinte_no_mesmo_par(self):
        nova = sei(id="SEI-SHORT_TURTLE-2", issued_at=T_SEI + 15 * DIA)
        led = [sei(), nova]
        by = Bybit({"SEIUSDC": [ex(1, T_SEI + 120, "Sell", 100, 0.05715), ex(2, T_SEI + 15 * DIA + 60, "Sell", 50, 0.04)]})
        correr(led, by)
        self.assertEqual(led[0]["real"]["n"], 1); self.assertEqual(led[1]["real"]["n"], 1)


class FalhasDaApi(unittest.TestCase):
    def test_falha_marca_incompleta_e_o_cursor_nao_avanca(self):
        led = [sei()]
        execs = {"SEIUSDC": [ex(1, T_SEI + 120, "Sell", 100, 0.05715), ex(2, T_SEI + 9 * DIA, "Buy", 100, 0.047)]}
        correr(led, Bybit(execs, falhar_antes_de=T_SEI + 8 * DIA))
        r = led[0]["real"]
        self.assertEqual(r["estado"], "incompleta"); self.assertTrue(r["falhas"]); self.assertLess(r["lido_ate"], T_SEI + 8 * DIA)
        self.assertIsNone(led[0]["real_r"])
        correr(led, Bybit(execs))                                           # a API volta: completa sem duplicar
        self.assertEqual((led[0]["real"]["estado"], led[0]["real"]["n"]), ("fechada", 2))

    def test_sem_execucoes_fica_sem_dados(self):
        led = [sei(real=None)]
        correr(led, Bybit({}))
        self.assertEqual(led[0]["real"]["estado"], "sem_dados"); self.assertIsNone(led[0]["real_r"])
        self.assertIn(led[0], A.pendentes(led))

    def test_leitura_real_nao_engole_erros(self):
        orig = A.get
        A.get = lambda *a, **k: (_ for _ in ()).throw(A.AccountError("HTTP 403"))
        try:
            with self.assertRaises(A.LeituraFalhou):
                A.execs_janela("SEIUSDC", T_SEI, T_SEI + DIA)
            self.assertIsNone(A.juros_margem("SEI", T_SEI, T_SEI + DIA)); self.assertIsNone(A.ordens_protecao("SEIUSDC", T_SEI, T_SEI + DIA))
        finally:
            A.get = orig


class Publico(unittest.TestCase):
    def test_copia_publica_sem_valores(self):
        led = [sei()]
        correr(led, Bybit({"SEIUSDC": [ex(1, T_SEI + 120, "Sell", 100, 0.05715), ex(2, T_SEI + 9 * DIA, "Buy", 100, 0.047)]}), juros=0.4)
        pub = publico.state({"ledger": led})["ledger"][0]["real"]
        for k in ("execs_valores", "compra_usdc", "venda_usdc", "pnl_usdc", "risco_usdc", "comissoes_usdc", "preco_entrada",
                  "preco_saida", "juros_valor_moeda"):
            self.assertNotIn(k, pub)
        self.assertEqual(pub["estado"], "fechada")


class ParaNoFecho(unittest.TestCase):
    def test_execucoes_depois_do_fecho_total_nao_contam(self):
        led = [sei(id="paper-NEAR-1", asset="NEAR", pair="NEAR/USDC", side="LONG", kind="1D", stop=4.689, real=None)]
        by = Bybit({"NEARUSDC": [ex(1, T_SEI + 60, "Buy", 1, 5.92), ex(2, T_SEI + 2 * DIA, "Sell", 1, 5.143),
                                 ex(3, T_SEI + 10 * DIA, "Buy", 3, 2.5), ex(4, T_SEI + 11 * DIA, "Sell", 3, 2.6)]})   # manuais depois
        correr(led, by)
        r = led[0]["real"]
        self.assertTrue(r["fechada"]); self.assertEqual(r["n"], 2); self.assertAlmostEqual(r["preco_saida"], 5.143)
        self.assertLess(max(c[2] for c in by.chamadas), T_SEI + 10 * DIA)   # parou de ler depois do fecho


def exl(i, t, lado, q, px, link, **kw):
    e = ex(i, t, lado, q, px, **kw)
    e["orderLinkId"] = link
    return e


class RiscoNear(unittest.TestCase):
    """(06/11) Compras manuais na app no mesmo par, antes do fecho, nao entram no resultado da operacao do programa."""
    def near(self):
        return [sei(id="paper-NEAR-1", asset="NEAR", pair="NEAR/USDC", side="LONG", kind="1D", stop=4.689, real=None)]

    def test_compra_manual_antes_do_fecho_ignorada(self):
        led = self.near()
        by = Bybit({"NEARUSDC": [exl(1, T_SEI + 60, "Buy", 1, 5.92, "cs-near1"),
                                 exl(2, T_SEI + DIA, "Buy", 4, 5.5, ""),            # manual (app)
                                 exl(3, T_SEI + 2 * DIA, "Sell", 1, 5.143, "cs-near1s")]})
        correr(led, by)
        r = led[0]["real"]
        self.assertTrue(r["fechada"]); self.assertAlmostEqual(r["preco_entrada"], 5.92)
        self.assertEqual(r["entradas_manuais_ignoradas"], 1); self.assertTrue(r["origem_entrada_verificada"])
        self.assertAlmostEqual(r["pnl_usdc"], 5.143 - 5.92, places=6)

    def test_fecho_manual_da_posicao_do_programa_conta(self):
        led = self.near()
        by = Bybit({"NEARUSDC": [exl(1, T_SEI + 60, "Buy", 1, 5.92, "cs-near1"),
                                 exl(2, T_SEI + DIA, "Sell", 1, 6.1, "")]})        # fecho manual na app
        correr(led, by)
        self.assertTrue(led[0]["real"]["fechada"]); self.assertAlmostEqual(led[0]["real"]["preco_saida"], 6.1)

    def test_dados_sem_orderlinkid_aceites_e_assinalados(self):
        led = self.near()
        by = Bybit({"NEARUSDC": [ex(1, T_SEI + 60, "Buy", 1, 5.92), ex(2, T_SEI + DIA, "Sell", 1, 6.1)]})
        correr(led, by)
        self.assertFalse(led[0]["real"]["origem_entrada_verificada"]); self.assertTrue(led[0]["real"]["fechada"])


class Historico(unittest.TestCase):
    def test_resultado_real_ja_fechado_nao_e_reescrito(self):
        led = [sei(real_r=-1.0, real={"fechada": True, "pnl_usdc": -0.2, "custos_incompletos": False})]
        self.assertEqual(A.pendentes(led), [])
        L.apply_real(led, {led[0]["id"]: {"fechada": False, "n": 1}})
        self.assertEqual(led[0]["real_r"], -1.0); self.assertTrue(led[0]["real"]["fechada"])


if __name__ == "__main__":
    unittest.main()
