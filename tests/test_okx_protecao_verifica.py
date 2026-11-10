"""(10/11) Verificacao privada da protecao: so GET; classifica VERIFICADA / INSUFICIENTE / NAO VERIFICADA."""
import unittest

from tools import okx_protecao_verifica as V

OP = {"PARTI": {"inst": "PARTI-X", "estado": "aberta", "entrada": 0.04128, "stop": 0.037}}


def okx(pos=None, algos=None, falha=()):
    pedidos = []

    def get(path):
        pedidos.append(path)
        if "positions" in path:
            return {"code": "1"} if "pos" in falha else {"code": "0", "data": pos or []}
        if "algo" in path:
            if "algo" in falha:
                return {"code": "50001"}
            tipo = "oco" if "oco" in path else "conditional"
            return {"code": "0", "data": [a for a in (algos or []) if a.get("_t", "oco") == tipo]}
        raise AssertionError("pedido inesperado " + path)
    return get, pedidos


POS = [{"instId": "PARTI-X", "pos": "10", "posSide": "net", "avgPx": "0.04128"}]


class Verifica(unittest.TestCase):
    def test_verificada(self):
        get, _ = okx(POS, [{"slTriggerPx": "0.037", "side": "sell", "sz": "10"}])
        r = V.verificar(OP, get)["PARTI"]
        self.assertEqual(r["classe"], "VERIFICADA", r); self.assertEqual(r["lado"], "LONG")

    def test_sem_stop(self):
        get, _ = okx(POS, [])
        self.assertEqual(V.verificar(OP, get)["PARTI"]["classe"], "INSUFICIENTE")

    def test_quantidade_insuficiente_e_aumento_da_posicao(self):
        get, _ = okx([dict(POS[0], pos="15")], [{"slTriggerPx": "0.037", "side": "sell", "sz": "10"}])
        r = V.verificar(OP, get)["PARTI"]
        self.assertEqual(r["classe"], "INSUFICIENTE"); self.assertTrue(any("10 de 15" in m for m in r["motivos"]))

    def test_reducao_da_posicao_continua_coberta(self):
        get, _ = okx([dict(POS[0], pos="6")], [{"slTriggerPx": "0.037", "side": "sell", "sz": "10"}])
        self.assertEqual(V.verificar(OP, get)["PARTI"]["classe"], "VERIFICADA")

    def test_lado_errado(self):
        get, _ = okx(POS, [{"slTriggerPx": "0.037", "side": "buy", "sz": "10"}])
        self.assertEqual(V.verificar(OP, get)["PARTI"]["classe"], "INSUFICIENTE")
        get, _ = okx(POS, [{"slTriggerPx": "0.045", "side": "sell", "sz": "10"}])
        self.assertEqual(V.verificar(OP, get)["PARTI"]["classe"], "INSUFICIENTE")

    def test_parcial_fecha_tudo_e_stop_condicional(self):
        get, _ = okx([dict(POS[0], pos="4")], [{"slTriggerPx": "0.037", "side": "sell", "closeFraction": "1", "_t": "conditional"}])
        self.assertEqual(V.verificar(OP, get)["PARTI"]["classe"], "VERIFICADA")

    def test_falhas_de_comunicacao_nao_assumem_nada(self):
        get, _ = okx(falha=("pos",))
        self.assertEqual(V.verificar(OP, get)["_geral"]["classe"], "NAO VERIFICADA")
        get, _ = okx(POS, falha=("algo",))
        self.assertEqual(V.verificar(OP, get)["PARTI"]["classe"], "NAO VERIFICADA")

    def test_discrepancias_com_o_estado_local(self):
        get, _ = okx([], [])
        self.assertEqual(V.verificar(OP, get)["PARTI"]["classe"], "INSUFICIENTE")       # local aberta, OKX sem posicao
        get, _ = okx(POS + [{"instId": "NOVA-X", "pos": "3", "avgPx": "1"}], [{"slTriggerPx": "0.037", "side": "sell", "sz": "10"}])
        r = V.verificar(OP, get)
        self.assertIn("NOVA", r); self.assertIn("NAO segue", "; ".join(r["NOVA"]["motivos"]))
        get, _ = okx(POS, [{"slTriggerPx": "0.030", "side": "sell", "sz": "10"}])
        self.assertTrue(any("preco do plano" in m for m in V.verificar(OP, get)["PARTI"]["motivos"]))

    def test_so_get_e_texto_publico_sem_quantidades(self):
        get, pedidos = okx(POS, [{"slTriggerPx": "0.037", "side": "sell", "sz": "10"}])
        pub, priv = V.textos(V.verificar(OP, get))
        self.assertNotIn("qtd", " ".join(pub)); self.assertIn("qtd 10", " ".join(priv))
        src = open(V.__file__).read()
        self.assertNotIn('"POST"', src); self.assertIn('E.privado("GET", path)', src)


if __name__ == "__main__":
    unittest.main()
