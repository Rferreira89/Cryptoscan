"""(20/11) O vigia avisa quando um ficheiro publico (okx.json, state.json, scan.json, piloto_publico.json) parece ter
valores em dinheiro da conta. O repositorio e publico; a 19/11 o piloto publicou "risco X, nocional Y" (USDC
livres) num motivo sem ninguem ver. O aviso diz o caminho do campo, nunca o valor."""
import unittest
from tools import vigia as V


class Fugas(unittest.TestCase):
    def test_estado_limpo_nao_avisa(self):
        st = {"resumo": {"t": 1, "conta_sim_pct": 3.64, "r_medio": 0.02},
              "ultimo": {"USDC": 1795132800, "BTC": 1795132800},          # ticker como chave, valor = hora da vela
              "universe": [{"book": {"imbalance": -0.03}}],               # "imbalance" nao e "balance"
              "orcamento": {"nocional_usado_pct": 8.9, "margem_usada_pct": 1.8},
              "troca_filtro": {"regra": {"margem_r": 0.05}},
              "oportunidades": [{"margem_disponivel": True, "motivo": "risco 3% do orcamento, nocional 29% do orcamento"},
                                {"motivo": "spread 0.768% acima de 0.3% (liquidez)"},
                                {"txt": "risco 1.5R, saida em 72 h; conta simulada de 20 USD: +3.6%"}],
              "pico_cifrado": "gAAAA+5USDC/abc", "real": {"ops": {"XLM": {"risco_pct": 2.34, "lim": 0.137}}}}
        self.assertEqual(V.fugas(st), [])
        self.assertEqual(V.problemas_fugas("okx.json", st), [])

    def test_motivo_do_piloto_de_19_11(self):
        st = {"sinais_perdidos": [{"motivo": "tamanho minimo (0.01 contratos) passaria o risco ou o nocional autorizados "
                                             "(livre depois das 1 posicoes abertas: risco 0.0111, nocional 9.99)"}]}
        self.assertEqual(V.fugas(st), ["sinais_perdidos[].motivo"])

    def test_campos_numericos_de_dinheiro(self):
        st = {"conta": {"saldo": 123.45, "equity_usdt": 99.0, "pnl": -1.2},
              "saldos": {"saldo": {"USDT": 50.1}},                         # ticker debaixo de um campo de dinheiro
              "evento": "fechou com lucro de 3.21 USDT"}
        f = V.fugas(st)
        for c in ("conta.saldo", "conta.equity_usdt", "conta.pnl", "saldos.saldo.USDT", "evento"):
            self.assertIn(c, f)

    def test_aviso_sem_valores(self):
        st = {"conta": {"saldo": 123.45, "nocional": 67.89, "margem": 11.1, "pnl": 2.5}}
        out = V.problemas_fugas("piloto_publico.json", st)
        self.assertEqual([k for k, _ in out], ["fuga-piloto_publico.json"])
        msg = out[0][1]
        self.assertIn("conta.saldo", msg)
        self.assertIn("e mais 1", msg)
        for v in ("123", "67.89", "11.1", "2.5"):
            self.assertNotIn(v, msg)

    def test_zero_e_booleanos_nao_contam(self):
        self.assertEqual(V.fugas({"saldo": 0, "margem": True, "pnl": None}), [])


if __name__ == "__main__":
    unittest.main()
