"""(11/11, P4) Contabilidade real: metricas, privacidade do relatorio publico, so leitura.
Os numeros das fixtures sao inventados para o teste (nao sao dados reais)."""
import ast
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.join(RAIZ, "tools"))
from engine import contabilidade as C  # noqa: E402
import okx_contabilidade as K  # noqa: E402


def op(r_px, **kw):
    # long, entrada 1.0, stop 0.9: risco por unidade 0.1; saida = 1 + 0.1 * r_px
    base = dict(corretora="okx", estrategia="panico", ativo="AAA", lado="LONG", entrada=1.0, saida=1.0 + 0.1 * r_px, stop=0.9)
    base.update(kw)
    return C.operacao(**base)


class Operacao(unittest.TestCase):
    def test_r_bruto_e_liquido_pela_proporcao_do_pnl(self):
        o = op(-1.2, pnl_preco=-12.0, pnl_liquido=-12.6, comissoes=-0.5, funding=-0.1, motivo="stop")
        self.assertAlmostEqual(o["r_bruto"], -1.2)
        self.assertAlmostEqual(o["r_liquido"], -1.26)
        self.assertAlmostEqual(o["custo_r"], 0.06)
        self.assertAlmostEqual(o["deslize_stop_r"], -0.2)
        self.assertEqual(o["metodo_r"], "proporcao_pnl")

    def test_r_liquido_pelo_risco_em_dinheiro_tem_prioridade(self):
        o = op(2.0, pnl_preco=20, pnl_liquido=19, risco_dinheiro=10)
        self.assertAlmostEqual(o["r_liquido"], 1.9)
        self.assertEqual(o["metodo_r"], "risco_dinheiro")

    def test_short(self):
        o = C.operacao("bybit", "S", "BBB", "SHORT", entrada=10, saida=9, stop=11, pnl_preco=1, pnl_liquido=0.9)
        self.assertAlmostEqual(o["r_bruto"], 1.0)
        self.assertAlmostEqual(o["r_liquido"], 0.9)

    def test_sem_custos_fica_incompleta_e_nao_inventa(self):
        o = op(-1.0)
        self.assertIsNone(o["r_liquido"])
        self.assertFalse(o["completa"])

    def test_deslize_na_entrada(self):
        o = op(1.0, limite=0.99)                                  # comprou 0.01 acima do limite = 0.1R pior
        self.assertAlmostEqual(o["deslize_entrada_r"], 0.1)

    def test_casos_parti_e_cashcat_reproduzem_a_auditoria(self):
        parti = C.operacao("okx", "panico", "PARTI", "LONG", 0.04128, 0.03605, 0.037, motivo="stop")
        cash = C.operacao("okx", "panico", "CASHCAT", "LONG", 0.07391, 0.06251, 0.06266, motivo="stop")
        self.assertAlmostEqual(parti["r_bruto"], -1.222, places=3)
        self.assertAlmostEqual(parti["deslize_stop_r"], -0.222, places=3)
        self.assertAlmostEqual(cash["r_bruto"], -1.013, places=3)


class Resumo(unittest.TestCase):
    def test_metricas(self):
        ops = [op(2, pnl_preco=2, pnl_liquido=1.9, t_fecho=1), op(-1, pnl_preco=-1, pnl_liquido=-1.05, t_fecho=2),
               op(-1, pnl_preco=-1, pnl_liquido=-1.05, t_fecho=3), op(2, pnl_preco=2, pnl_liquido=1.9, t_fecho=4)]
        r = C.resumo(ops)
        self.assertEqual(r["n_com_dados"], 4)
        self.assertAlmostEqual(r["soma_r"], 1.7)
        self.assertEqual(r["acerto_pct"], 50.0)
        self.assertAlmostEqual(r["profit_factor"], 3.8 / 2.1, places=3)
        self.assertAlmostEqual(r["drawdown_r"], -2.1)
        self.assertEqual(r["pior_sequencia_perdas"], 2)
        self.assertAlmostEqual(r["custo_medio_r"], 0.075)

    def test_grupos(self):
        ops = [op(1, pnl_preco=1, pnl_liquido=1, ativo="A"), op(-1, pnl_preco=-1, pnl_liquido=-1, ativo="B", corretora="bybit")]
        rel = C.relatorio(ops)
        self.assertEqual(set(rel["por_ativo"]), {"A", "B"})
        self.assertEqual(set(rel["por_corretora"]), {"okx", "bybit"})


class Privacidade(unittest.TestCase):
    def test_publico_sem_dinheiro_precos_nem_ids(self):
        ops = [op(-1.2, pnl_preco=-12, pnl_liquido=-12.6, comissoes=-0.5, funding=-0.1, risco_dinheiro=10,
                  t_abertura=1794268800, t_fecho=1794300000, limite=1.0)]
        pub = C.publico(ops)
        self.assertEqual(C.sem_dinheiro(pub), [])
        txt = json.dumps(pub)
        for v in ("-12.6", "-0.5", "1794300000"):
            self.assertNotIn(v, txt)

    def test_verificador_apanha_campos_proibidos(self):
        self.assertTrue(C.sem_dinheiro({"a": [{"pnl_liquido": 1}]}))

    def test_privado_nao_e_escrito_sem_data_key(self):
        pos = [{"instId": "AAA-USD_UM_XPERP-1", "openAvgPx": "1", "closeAvgPx": "0.88", "pnl": "-1.2", "fee": "-0.02",
                "fundingFee": "-0.01", "realizedPnl": "-1.23", "cTime": "1000", "uTime": "2000", "type": "2"}]
        with tempfile.TemporaryDirectory() as d:
            est = os.path.join(d, "okx.json")
            json.dump({"real": {"hist": [{"inst": "AAA-USD_UM_XPERP-1", "estado": "fechada", "stop": 0.9, "alvo": 1.2,
                                          "lim": 1.0, "estrategia": "panico", "t_fill": 1, "motivo": "stop ou objetivo"}]}}, open(est, "w"))

            def ler(path):
                return {"code": "0", "data": pos if "positions-history" in path else []}
            with mock.patch.dict(os.environ, {"DATA_KEY": ""}):
                pub, priv = K.correr(est, d, ler=ler)
            self.assertFalse(priv)
            self.assertFalse(os.path.exists(os.path.join(d, "contabilidade_okx_privado.json")))
            o = pub["operacoes"][0]
            self.assertEqual(o["motivo"], "stop")
            self.assertAlmostEqual(o["r_bruto"], -1.2)
            self.assertAlmostEqual(o["r_liquido"], -1.23)

    def test_privado_e_cifrado_com_data_key(self):
        with tempfile.TemporaryDirectory() as d:
            est = os.path.join(d, "okx.json")
            json.dump({}, open(est, "w"))
            cifrados = []
            with mock.patch.dict(os.environ, {"DATA_KEY": "k"}):
                K.correr(est, d, ler=lambda p: {"code": "0", "data": []}, cifrar=cifrados.append)
            self.assertEqual(len(cifrados), 1)


class SoLeitura(unittest.TestCase):
    def test_modulo_nao_contem_chamadas_de_escrita(self):
        """Verificacao estatica: nenhuma chamada a privado/leitura com metodo diferente de GET, nenhum endpoint de
        ordens, cancelamentos, alavancagem ou fecho de posicoes."""
        src = open(os.path.join(RAIZ, "tools", "okx_contabilidade.py")).read()
        for proibido in ("/trade/order", "cancel-order", "close-position", "set-leverage", "order-algo", "amend"):
            self.assertNotIn(proibido, src.replace("fills-history", ""))
        arvore = ast.parse(src)
        for n in ast.walk(arvore):
            if isinstance(n, ast.Call) and getattr(n.func, "attr", getattr(n.func, "id", "")) == "privado":
                self.assertEqual(n.args[0].value, "GET")

    def test_guarda_recusa_outros_metodos(self):
        with self.assertRaises(K.SoLeitura):
            K._guarda("POST")


class Bybit(unittest.TestCase):
    def test_de_bybit(self):
        reg = {"strategy": "BOUNCE_SQUEEZE", "asset": "ENA", "side": "LONG", "stop": 0.18, "opened_at": 1, "closed_at": 2,
               "reason": "STOP"}
        res = {"fechada": True, "pnl_usdc": -1.1, "comissoes_usdc": 0.1, "preco_entrada": 0.2, "preco_saida": 0.18,
               "risco_usdc": 1.0}
        o = C.de_bybit(reg, res)
        self.assertAlmostEqual(o["r_liquido"], -1.1)
        self.assertAlmostEqual(o["r_bruto"], -1.0)
        self.assertIsNone(C.de_bybit(reg, {"fechada": False}))


if __name__ == "__main__":
    unittest.main()
