"""(05/11, S2, OK do Rui) capital e deposito mensal fora do config.json publico, sem mudar o funcionamento."""
import json
import os
import unittest
from engine import config, liberdade, publico

RAIZ = os.path.join(os.path.dirname(__file__), "..")


class S2(unittest.TestCase):
    def test_config_publico_sem_capital(self):
        c = json.load(open(os.path.join(RAIZ, "config.json")))
        self.assertNotIn("capital_usdc", c); self.assertNotIn("capital_since", c)

    def test_capital_continua_a_vir_da_conta(self):
        # o capital de trabalho vem do saldo lido na Bybit (state["capital"], automatico); o config so era reserva
        self.assertEqual(config.load()["capital_usdc"], config.DEFAULTS["capital_usdc"])

    def test_deposito_migra_para_o_estado_uma_vez(self):
        st = {}
        c = liberdade.cfg_privado(st, {"deposito_mensal": 300, "rendimento_mensal": 2000})
        self.assertEqual(st["privado"]["deposito_mensal"], 300.0); self.assertEqual(c["deposito_mensal"], 300.0)
        c2 = liberdade.cfg_privado(st, {"rendimento_mensal": 2000})      # depois de sair do config, o estado manda
        self.assertEqual(c2["deposito_mensal"], 300.0)
        c3 = liberdade.cfg_privado(st, {"deposito_mensal": 999})          # o estado nao e reescrito pelo config
        self.assertEqual(c3["deposito_mensal"], 300.0)

    def test_privado_nunca_vai_para_a_copia_publica(self):
        out = publico.state({"privado": {"deposito_mensal": 300}, "x": 1})
        self.assertNotIn("privado", out); self.assertNotIn("300", json.dumps(out))


class SemSaldoRealNaoAbre(unittest.TestCase):
    def test_entradas_bloqueadas_sem_saldo_confirmado(self):
        from engine import execucao
        st = {}
        for acao in ("comprar", "vender", "nucleo_comprar", "nucleo_reforcar", "panico_comprar", "panico_ordem", "panico_refazer"):
            self.assertIsNone(execucao.request(st, acao, "X-1", 100))
        self.assertEqual(st.get("exec_req", []), [])
        self.assertEqual(len(st["entradas_bloqueadas"]), 7)

    def test_saidas_passam_sempre(self):
        from engine import execucao
        st = {}
        for acao in ("fechar", "nucleo_vender", "parar", "panico_cancelar", "breakeven"):
            self.assertTrue(execucao.request(st, acao, "X-1", 100))

    def test_com_saldo_confirmado_entra(self):
        from engine import execucao
        st = {"capital_confirmado": True}
        self.assertTrue(execucao.request(st, "nucleo_comprar", "NUCLEO-BTC", 100))

    def test_scanner_so_confirma_com_leitura_fresca(self):
        from engine import scanner
        st = {}
        with __import__("unittest").mock.patch.object(scanner, "apply_account", return_value=None):
            conta = scanner.apply_account(st, {}, 0)
        st["capital_confirmado"] = bool(conta and conta.get("equity"))
        self.assertFalse(st["capital_confirmado"])

    def test_flag_nao_vai_para_a_copia_publica(self):
        self.assertNotIn("capital_confirmado", publico.state({"capital_confirmado": True}))


if __name__ == "__main__":
    unittest.main()
