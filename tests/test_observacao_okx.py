"""(19/11) Observacao de 7 dias da OKX: so leitura, sem dinheiro no publico, base exclui operacoes anteriores,
uma fotografia no Telegram por dia e o relatorio final uma unica vez."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import observacao_okx as O  # noqa: E402

INI = 1795114800
CFG = {"inicio": INI, "dias": 7}


def op_contab(ativo, r, dia, executor="piloto", est="piloto:29933c49ce9e", lado="LONG"):
    return {"corretora": "okx", "executor": executor, "estrategia": est, "ativo": ativo, "lado": lado, "motivo": "stop",
            "dia_fecho": dia, "r_bruto": r + 0.02, "r_liquido": r, "custo_r": 0.02, "deslize_stop_r": None,
            "deslize_entrada_r": None, "ret_preco_pct": 1.0, "completa": True}


PILOTO = {"t": INI + 600, "operacional": True, "bloqueado": False, "suspenso": False, "motivo": None,
          "portas": {"api_fiavel": {"ok": True}, "dados_frescos": {"ok": True}},
          "ativas": ["a", "b"], "orcamento": {"abertas": 1, "maximo": 2, "risco_usado_pct": 50.0},
          "ops": [{"base": "ETHFI", "estrategia": "29933c49ce9e", "lado": "LONG", "tf": "4H", "estado": "aberta",
                   "stop_confirmado": True, "r_aberto": -0.7, "stop": 1.23, "preco_efetivo": 1.5, "inst": "X",
                   "t_execucao": INI - 3600}],
          "oportunidades": [{"t": INI + 100, "categoria": "liquidez", "decisao": "REJEITADA"},
                            {"t": INI - 100, "categoria": "executada", "decisao": "EXECUTADA_REAL"}]}
OKX = {"real": {"ops": {"XLM": {"estado": "aberta", "lado": "SHORT", "estrategia_bybit": "SHORT_TURTLE",
                                "stop": 0.15, "entrada": 0.137, "inst": "XLM-..", "stop_ok": INI}}}}


class TestObservacao(unittest.TestCase):
    def test_antes_do_inicio_nao_faz_nada(self):
        e, m, f = O.volta({}, CFG, PILOTO, OKX, {"operacoes": []}, now=INI - 10)
        self.assertEqual((e, m, f), ({}, [], None))

    def test_publico_sem_precos_nem_dinheiro(self):
        e, m, _ = O.volta({}, CFG, PILOTO, OKX, {"operacoes": []}, now=INI + 700)
        self.assertEqual(O.C.sem_dinheiro(e), [])
        txt = json.dumps(e)
        for proibido in ("1.23", "0.137", "XLM-..", "preco_efetivo"):
            self.assertNotIn(proibido, txt)
        pos = e["fotografias"][-1]["posicoes"]
        self.assertEqual({p["ativo"] for p in pos}, {"ETHFI", "XLM"})
        self.assertTrue(all(p["stop_confirmado"] for p in pos))
        self.assertEqual(e["fotografias"][-1]["funil_desde_inicio"]["sinais"], 1)   # so os sinais desde o inicio
        self.assertEqual(len(m), 1)

    def test_base_exclui_operacoes_anteriores(self):
        antigo = op_contab("SPCX", 0.66, INI // 86400 * 86400)
        e, _, _ = O.volta({}, CFG, PILOTO, OKX, {"operacoes": [antigo]}, now=INI + 700)
        self.assertEqual(e["resultados"]["total"]["n"], 0)
        novo = op_contab("BASED", -1.0, INI // 86400 * 86400)
        e, _, _ = O.volta(e, CFG, PILOTO, OKX, {"operacoes": [antigo, novo]}, now=INI + 7200)
        self.assertEqual(e["resultados"]["total"]["n"], 1)
        self.assertAlmostEqual(e["resultados"]["total"]["soma_r"], -1.0)

    def test_um_aviso_por_dia_e_final_uma_vez(self):
        e, m1, _ = O.volta({}, CFG, PILOTO, OKX, {"operacoes": []}, now=INI + 700)
        e, m2, _ = O.volta(e, CFG, PILOTO, OKX, {"operacoes": []}, now=INI + 3 * 3600)
        self.assertEqual((len(m1), len(m2)), (1, 0))
        reg = {"estrategias": {"x": {"id": "29933c49ce9e", "backtest": {"r_medio": 0.07}}}}
        ops = [op_contab("A", 1.2, INI // 86400 * 86400 + 86400)]
        e, m3, final = O.volta(e, CFG, PILOTO, OKX, {"operacoes": ops}, registo=reg,
                               privado={"operacoes": [{"t_fecho": INI + 90000, "pnl_liquido": 0.12, "comissoes": -0.01}]},
                               now=INI + 7 * 86400 + 60)
        self.assertEqual(len(m3), 1)
        self.assertIn("FINAL", final)
        self.assertIn("backtest +0.070R", final)
        self.assertNotIn("pnl_liquido", final)                 # o dinheiro so vai no Telegram
        self.assertIn("pnl_liquido +0.1200", m3[0])
        e, m4, f4 = O.volta(e, CFG, PILOTO, OKX, {"operacoes": ops}, now=INI + 8 * 86400)
        self.assertEqual((m4, f4), ([], None))

    def test_disponibilidade(self):
        runs = {"piloto-okx.yml": [{"t": INI + 1800, "ok": True}, {"t": INI + 3600, "ok": False}]}
        d = O.disponibilidade(runs, INI, INI + 7200)
        self.assertEqual(d["piloto-okx.yml"]["voltas"], 2)
        self.assertEqual(d["piloto-okx.yml"]["falhadas"], 1)

    def test_main_escreve_estado(self):
        with tempfile.TemporaryDirectory() as d:
            for nome, obj in (("piloto_publico.json", PILOTO), ("okx.json", OKX), ("contabilidade_okx.json", {"operacoes": []})):
                json.dump(obj, open(os.path.join(d, nome), "w"))
            self.assertEqual(O.main([d, "--sem-telegram"]), 0)
            cfg = json.load(open(O.CFG_FICHEIRO))
            e = json.load(open(os.path.join(d, "observacao_okx.json")))
            self.assertEqual(e.get("inicio"), cfg["inicio"] if O.time.time() >= cfg["inicio"] else None)

    def test_ferramenta_nao_envia_ordens(self):
        src = open(O.__file__, encoding="utf-8").read()
        for proibido in ("okx_exec", "privado(", "POST", "/trade/"):
            self.assertNotIn(proibido, src.split('"""', 2)[2])


if __name__ == "__main__":
    unittest.main()
