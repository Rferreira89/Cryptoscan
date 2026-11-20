"""(20/11) Prazo encurtado pelo Rui no short BTC da OKX (executor antigo): so encurta, avisa uma vez, nao mexe no
stop nem no objetivo, nao toca noutras operacoes (XLM)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import okx_exec as E  # noqa: E402

FILL = 1795162200


def btc():
    return {"estado": "aberta", "lado": "SHORT", "id_bybit": "BTC-SHORT_TURTLE-1795161609", "t_fill": FILL,
            "hold_s": 1728000, "sair_em": FILL + 1728000, "stop": 66182.9, "alvo": 54577.9}


class PrazoPedido(unittest.TestCase):
    def test_btc_passa_a_7_dias_e_avisa_uma_vez(self):
        op, msgs = btc(), []
        self.assertTrue(E.aplicar_prazo_pedido("BTC", op, msgs))
        self.assertEqual((op["hold_s"], op["sair_em"]), (7 * 86400, FILL + 7 * 86400))
        self.assertEqual((op["stop"], op["alvo"]), (66182.9, 54577.9))
        self.assertFalse(E.aplicar_prazo_pedido("BTC", op, msgs))
        self.assertEqual(len(msgs), 1)
        self.assertIn("27/11", msgs[0])

    def test_nunca_alonga_e_nao_toca_noutras(self):
        op = dict(btc(), hold_s=3 * 86400, sair_em=FILL + 3 * 86400)
        E.aplicar_prazo_pedido("BTC", op, [])
        self.assertEqual(op["hold_s"], 3 * 86400)
        xlm = dict(btc(), id_bybit="XLM-SHORT_TURTLE-1794673840")
        self.assertFalse(E.aplicar_prazo_pedido("XLM", xlm, []))
        self.assertEqual(xlm["hold_s"], 1728000)

    def test_saida_por_tempo_usa_o_prazo_novo(self):
        src = open(E.__file__, encoding="utf-8").read()
        self.assertIn('if aberta and op.get("sair_em") is not None and now >= op["sair_em"]:', src)


if __name__ == "__main__":
    unittest.main()
