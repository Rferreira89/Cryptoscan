"""(12/11, montagem final) Ponta a ponta do motor comum de execucao da Bybit UE, LONG e SHORT, com a corretora
simulada: dimensionamento pelo risco real, entrada, stop na corretora, saida, reinicio, rejeicoes, falhas de API,
sentidos incompativeis e limites do piloto. Nada vem da rede."""
import unittest
from unittest import mock

from engine import promo, risk
from tests.test_diretor import NOW, VendaADescoberto


def cfg_piloto_teste(**k):
    from engine import config
    c = dict(config.load())
    c.update(capital_usdc=20.0, fixed_position_usdc=4.4, max_risk_usdc=0.1, max_risk_usdc_normal=0.1,
             swing_leverage=10.0, max_position_pct=25.0, risk_pct=1.0, min_order_usdc=5.0, **k)
    return c


class Base(VendaADescoberto):
    def snd(self):
        self.sent = []
        return lambda t, html=False: self.sent.append(t)

    def short_state(self, usdc=5.0, tp=(78.0,), partials=(100,), maxv=None):
        # (12/11) como o dimensionamento real: o plano leva o valor maximo que o teto do piloto permite (4% de 20 com
        # stop de 11% -> 7,27), para o executor poder subir um lote quando o arredondamento fica abaixo do minimo
        sig = {"status": "ACTIVE", "mode": "REAL", "plan": {"side": "SHORT", "entry_zone": [99.5, 100.5], "stop": 111.0,
               "tp": list(tp), "partials": list(partials), "position_usdc": usdc,
               "max_position_usdc": maxv if maxv is not None else round(20 * 0.04 / 0.11, 2)}}
        return {"signals": {"op1": sig}, "ledger": [{"id": "op1", "asset": "SEI", "pair": "SEI/USDC", "side": "SHORT",
                                                     "strategy": "SHORT_TURTLE", "issued_at": NOW}]}

    def long_state(self, usdc=6.0):
        sig = {"status": "ACTIVE", "mode": "REAL", "plan": {"entry_zone": [99.5, 100.5], "stop": 94.0, "tp": [112.0],
               "partials": [100], "position_usdc": usdc, "leverage": {"use": 1}}}
        return {"signals": {"op2": sig}, "ledger": [{"id": "op2", "asset": "SOL", "pair": "SOL/USDC", "side": "LONG",
                                                     "strategy": "TESTE_LONG", "issued_at": NOW}]}

    def vendas(self):
        return [b for p, b in self.calls if p == "/v5/order/create" and b.get("side") == "Sell"]

    def compras(self):
        return [b for p, b in self.calls if p == "/v5/order/create" and b.get("side") == "Buy"]


class ShortPontaAPonta(Base):
    def test_sem_teto_no_plano_recusa_sem_enviar(self):
        """Plano sem valor maximo e arredondamento abaixo do minimo: recusa com motivo claro, nada enviado."""
        ex = {"ops": {}}
        st = self.short_state(5.0)
        st["signals"]["op1"]["plan"].pop("max_position_usdc")
        res = self.run_with(self.X.do_short, st, {"op": "op1"}, ex, NOW, self.snd(), last_price=100.0, best_bid=99.9)
        self.assertIn("abaixo do mínimo", res)
        self.assertEqual(self.vendas(), [])
        self.assertEqual(ex["ops"]["op1"]["status"], "recusada")

    def test_dimensionamento_do_piloto_entrada_stop_e_fecho(self):
        # 1) risco real: ordem minima de 5 com stop de 11% = 2,75% de 20 -> cabe no teto de 4%
        sz, why = risk.sizing(11.0, 0.11, 100.0, cfg_piloto_teste(piloto_teto_pct=4.0), short=True)
        self.assertIsNotNone(sz, why)
        usdc = sz["usdc"]["position_usdc"]
        self.assertEqual(usdc, 5.0)
        self.assertLessEqual(usdc * 0.11, 20.0 * 0.04)
        # 2) entrada: venda com margem, stop e objetivo ANEXADOS a ordem; 5 USDC a 99,8 com lote 0,001 arredondava
        # para 4,99 (< minimo, recusado pela Bybit como a BNB de 12/11): sobe um lote, dentro do teto
        ex, st = {"ops": {}}, self.short_state(usdc, maxv=sz["usdc"]["max_position_usdc"])
        res = self.run_with(self.X.do_short, st, {"op": "op1"}, ex, NOW, self.snd(), last_price=100.0, best_bid=99.9)
        self.assertEqual(res, "ok")
        v = self.vendas()
        self.assertEqual(len(v), 1)
        self.assertEqual((v[0]["isLeverage"], v[0]["stopLoss"], v[0]["takeProfit"]), (1, "111.00", "78.00"))
        val = float(v[0]["qty"]) * float(v[0]["price"])
        self.assertGreaterEqual(val, 5.0)
        self.assertLessEqual(val * 0.11, 20.0 * 0.04)
        self.assertTrue(ex["ops"]["op1"]["partes"][0]["anexo"])
        # 3) reinicio / pedido repetido: nunca uma segunda venda
        self.assertEqual(self.run_with(self.X.do_short, st, {"op": "op1"}, ex, NOW + 5, self.snd(), last_price=100.0),
                         "já executada antes")
        self.assertEqual(len(self.vendas()), 1)
        # 4) fecho: recompra so para devolver o emprestimo
        self.calls.clear()
        self.run_with(self.X.do_close, st, {"op": "op1"}, ex, NOW + 60, self.snd())
        self.assertTrue(self.compras())
        self.assertEqual(ex["ops"]["op1"]["status"], "fechada")

    def test_stop_anexado_recusado_fica_stop_condicional(self):
        X = self.X

        def post(path, body):
            if path == "/v5/order/create" and body.get("side") == "Sell" and body.get("stopLoss"):
                raise X.ExecError("TP/SL não suportado")
            return self.post(path, body)
        ex = {"ops": {}}
        ps = self.patches(last_price=100.0, best_bid=99.9)
        [p.start() for p in ps]
        try:
            with mock.patch.object(X, "post", side_effect=post):
                res = X.do_short(self.short_state(), {"op": "op1"}, ex, NOW, self.snd())
        finally:
            [p.stop() for p in ps]
        self.assertEqual(res, "ok")
        parte = ex["ops"]["op1"]["partes"][0]
        self.assertFalse(parte["anexo"])
        self.assertTrue(parte.get("stopId"))                       # stop de compra condicional colocado
        cond = [b for p, b in self.calls if b.get("triggerPrice")]
        self.assertEqual(cond[0]["side"], "Buy")

    def test_sem_execucao_nada_fica_aberto(self):
        ex = {"ops": {}}
        ps = self.patches(last_price=100.0, best_bid=99.9)
        [p.start() for p in ps]
        try:
            with mock.patch.object(self.X, "fills_or_state", return_value=(None, 0)):
                res = self.X.do_short(self.short_state(), {"op": "op1"}, ex, NOW, self.snd())
        finally:
            [p.stop() for p in ps]
        self.assertIn("sem execução", res)
        self.assertEqual(ex["ops"]["op1"]["status"], "recusada")
        self.assertFalse([b for p, b in self.calls if b.get("triggerPrice")])

    def test_pedido_duplicado_na_corretora_nao_repete(self):
        X = self.X

        def post(path, body):
            if path == "/v5/order/create" and body.get("side") == "Sell":
                self.calls.append((path, dict(body)))
                raise X.ExecError("Duplicate orderLinkId")
            return self.post(path, body)
        ex = {"ops": {}}
        ps = self.patches(last_price=100.0, best_bid=99.9)
        [p.start() for p in ps]
        try:
            with mock.patch.object(X, "post", side_effect=post):
                X.do_short(self.short_state(), {"op": "op1"}, ex, NOW, self.snd())
        finally:
            [p.stop() for p in ps]
        self.assertEqual(len(self.vendas()), 1)                    # nao tentou a segunda via sem anexo
        self.assertEqual(ex["ops"]["op1"]["status"], "recusada")

    def test_falha_de_api_antes_da_ordem_nao_envia_nada(self):
        X = self.X
        ps = self.patches(last_price=100.0, best_bid=99.9)
        [p.start() for p in ps]
        try:
            with mock.patch.object(X, "wallet", side_effect=X.ExecError("timeout")):
                with self.assertRaises(X.ExecError):
                    X.do_short(self.short_state(), {"op": "op1"}, {"ops": {}}, NOW, self.snd())
        finally:
            [p.stop() for p in ps]
        self.assertFalse(self.vendas())

    def test_moeda_em_carteira_recusa_o_short(self):
        ex = {"ops": {}}
        res = self.run_with(self.X.do_short, self.short_state(), {"op": "op1"}, ex, NOW, self.snd(),
                            last_price=100.0, best_bid=99.9, held=0.05)       # 5 USDC de SEI em carteira
        self.assertIn("em carteira", res)
        self.assertFalse(self.vendas())
        self.assertEqual(ex["ops"]["op1"]["status"], "recusada")

    def test_po_de_moeda_nao_bloqueia(self):
        ex = {"ops": {}}
        res = self.run_with(self.X.do_short, self.short_state(), {"op": "op1"}, ex, NOW, self.snd(),
                            last_price=100.0, best_bid=99.9, held=0.001)      # 0,10 USDC: resto sem significado
        self.assertEqual(res, "ok")


class LongPontaAPonta(Base):
    def patches_long(self, **kw):
        X = self.X
        ps = self.patches(**kw)
        ps += [mock.patch.object(X, "usdc_debt", return_value=0.0),
               mock.patch.object(X, "fills_or_state", return_value=(100.0, 0.06))]
        return ps

    def correr(self, st, ex, **kw):
        ps = self.patches_long(**kw)
        [p.start() for p in ps]
        try:
            return self.X.do_buy(st, {"op": "op2"}, ex, NOW, self.snd())
        finally:
            [p.stop() for p in ps]

    def test_compra_com_stop_anexado_e_sem_repeticao(self):
        ex, st = {"ops": {}}, self.long_state()
        res = self.correr(st, ex, last_price=100.0)
        self.assertEqual(res, "ok", self.sent)
        c = self.compras()
        self.assertEqual(len(c), 1)
        self.assertEqual(c[0]["stopLoss"], "94.00")
        self.assertEqual(self.correr(st, ex, last_price=100.0), "já executada antes")
        self.assertEqual(len(self.compras()), 1)

    def test_short_aberto_na_mesma_moeda_recusa_a_compra(self):
        self.debt["v"] = 0.5                                        # ha SOL emprestada: short aberto
        ex = {"ops": {}}
        res = self.correr(self.long_state(), ex, last_price=100.0)
        self.assertIn("venda a descoberto aberta", res)
        self.assertFalse(self.compras())

    def test_sem_leitura_do_emprestimo_nao_compra(self):
        ex = {"ops": {}}
        ps = self.patches_long(last_price=100.0)
        [p.start() for p in ps]
        try:
            with mock.patch.object(self.X, "coin_debt", side_effect=self.X.ExecError("x")):
                res = self.X.do_buy(self.long_state(), {"op": "op2"}, ex, NOW, self.snd())
        finally:
            [p.stop() for p in ps]
        self.assertIn("não consegui confirmar", res)
        self.assertFalse(self.compras())


class LimitesDoPiloto(unittest.TestCase):
    PL = {"piloto": {"estrategia": "SHORT_TURTLE", "teto_pct": 4, "perda_max_r": -8, "max_posicoes": 1,
                     "juro_max_r": 0.06, "dias_max": 20, "inicio": 0}}

    def op(self, r, dia, status="CLOSED"):
        return {"strategy": "SHORT_TURTLE", "mode": "REAL", "status": status, "executed": True, "result_r": r,
                "closed_at": NOW - 40 * 86400 + dia * 86400}

    def test_risco_acima_do_teto_nao_entra(self):
        sz, why = risk.sizing(17.5, 0.175, 100.0, cfg_piloto_teste(piloto_teto_pct=4.0), short=True)
        self.assertIsNone(sz)                                       # 5 x 17,5% = 4,4% de 20
        self.assertIn("abaixo da ordem", why)

    def test_perda_acumulada_fecha_a_porta_e_uma_posicao_de_cada_vez(self):
        st = {"ledger": [self.op(-1.0, d) for d in range(8)]}
        self.assertIn("suspenso", promo.cfg_piloto("SHORT_TURTLE", st, dict(self.PL), NOW)["piloto_bloqueio"])
        st2 = {"ledger": [self.op(None, 1, status="OPEN")]}
        self.assertIn("posição aberta", promo.cfg_piloto("SHORT_TURTLE", st2, dict(self.PL), NOW)["piloto_bloqueio"])

    def test_outra_estrategia_nunca_herda_o_teto_do_piloto(self):
        c = promo.cfg_piloto("BOUNCE_X30", {"ledger": []}, dict(self.PL), NOW)
        self.assertNotIn("piloto_teto_pct", c)
        sz, _ = risk.sizing(11.0, 0.11, 100.0, cfg_piloto_teste(), short=False)
        self.assertIsNone(sz)                                       # sem piloto, a ordem minima continua recusada


if __name__ == "__main__":
    unittest.main()
