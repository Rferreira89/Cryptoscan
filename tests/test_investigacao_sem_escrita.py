"""(11/11) Garantia: nenhum modulo de investigacao deste ramo consegue chamar endpoints de escrita das corretoras,
nem importa os executores reais. Verificacao estatica do codigo-fonte e execucao dos agentes com a rede cortada."""
import ast
import os
import sys
import tempfile
import unittest
from unittest import mock

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.join(RAIZ, "tools"))

INVESTIGACAO = ["engine/oportunidades.py", "engine/risco_intel.py", "engine/qualidade_execucao.py", "engine/contabilidade.py",
                "backtest/quant/robustez.py", "tools/cacador_global.py", "tools/quant_robustez.py", "tools/funil_frequencia.py",
                "tools/agentes_investigacao.py", "tools/recolha_liquidez_okx.py", "tools/okx_contabilidade.py",
                "tools/exposicao_historico.py", "backtest/estudos/novos/cacador_ic_historico.py",
                "backtest/estudos/externos/optuna_h40_wf.py", "backtest/estudos/externos/rl_baseline_h40.py",
                "backtest/estudos/externos/vectorbt_bench.py"]
ESCRITA = ("/trade/order", "cancel-order", "cancel-batch", "close-position", "set-leverage", "order-algo", "amend-order",
           "/v5/order/create", "/v5/order/cancel", "/v5/order/amend", "/v5/position/", "/asset/transfer", "withdraw")
EXECUTORES = ("okx_exec", "engine.executor", "engine import executor")


class SemEscrita(unittest.TestCase):
    def test_nenhum_endpoint_de_escrita_nem_executor(self):
        for f in INVESTIGACAO:
            src = open(os.path.join(RAIZ, f), encoding="utf-8").read()
            arvore = ast.parse(src)
            textos = [n.value for n in ast.walk(arvore) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
            for t in textos:
                for e in ESCRITA:
                    if e in t and not t.lstrip().startswith(("(", '"""')) and "\n" not in t:
                        self.fail(f"{f}: texto com endpoint de escrita: {t[:80]}")
            imports = [n for n in ast.walk(arvore) if isinstance(n, (ast.Import, ast.ImportFrom))]
            if f == "tools/okx_contabilidade.py":
                continue                                   # excecao documentada no teste seguinte (so GET)
            for n in imports:
                nomes = [a.name for a in n.names] + ([n.module] if isinstance(n, ast.ImportFrom) and n.module else [])
                for x in nomes:
                    self.assertNotIn(x, ("okx_exec", "engine.executor", "executor"), f"{f} importa {x}")

    def test_contabilidade_okx_so_importa_o_cliente_para_get(self):
        # unica excecao documentada: tools/okx_contabilidade.py importa okx_exec SO para o GET assinado (leitura)
        src = open(os.path.join(RAIZ, "tools", "okx_contabilidade.py")).read()
        self.assertIn('okx_exec.privado("GET", path)', src)
        self.assertEqual(src.count("okx_exec.privado("), 1)

    def test_agentes_correm_com_a_rede_cortada(self):
        import agentes_investigacao as A

        def sem_rede(*a, **k):
            raise AssertionError("tentativa de acesso a rede")
        with tempfile.TemporaryDirectory() as d, mock.patch("urllib.request.urlopen", sem_rede), \
                mock.patch("socket.create_connection", sem_rede):
            r = A.correr(d, os.path.join(d, "agentes.json"))
        self.assertEqual(len(r["agentes"]), 7)
        for g in r["agentes"]:
            self.assertEqual(g["autoridade"], "nenhuma (so leitura)")
            for k in ("factos", "hipoteses", "previsoes", "fontes", "reproducao"):
                self.assertIn(k, g)


if __name__ == "__main__":
    unittest.main()
