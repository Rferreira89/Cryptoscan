"""(10/11) Estrategia suspensa: cancela so ordens de entrada pendentes; posicoes abertas continuam geridas."""
import unittest

from engine import suspensao as S

ATIVA = {"real": True, "panico_real": True, "recuo_real": True}
H40_OFF = {"real": True, "panico_real": False, "recuo_real": True}


class Suspensao(unittest.TestCase):
    def test_pendente_de_estrategia_suspensa_e_cancelada(self):
        self.assertEqual(S.decidir(H40_OFF, {"estado": "pendente", "estrategia": "panico"}), "cancelar_pendente")

    def test_posicao_aberta_continua_gerida(self):
        self.assertEqual(S.decidir(H40_OFF, {"estado": "aberta", "estrategia": "panico"}), "gerir")

    def test_estrategia_ativa_nao_muda(self):
        self.assertEqual(S.decidir(ATIVA, {"estado": "pendente", "estrategia": "panico"}), "manter")
        self.assertEqual(S.decidir(H40_OFF, {"estado": "pendente", "estrategia": "recuo"}), "manter")   # H46 ativa

    def test_idempotente(self):
        self.assertEqual(S.decidir(H40_OFF, {"estado": "pendente", "estrategia": "panico", "cancelar_pedido": 1}), "ja_pedido")

    def test_registos_antigos_sem_estrategia_sao_h40(self):
        self.assertEqual(S.decidir(H40_OFF, {"estado": "pendente"}), "cancelar_pendente")

    def test_tudo_desligado(self):
        self.assertEqual(S.decidir({"real": False, "recuo_real": True}, {"estado": "pendente", "estrategia": "recuo"}),
                         "cancelar_pendente")

    def test_fechadas_ignoradas_e_plano(self):
        ops = {"PARTI": {"estado": "aberta", "estrategia": "panico"}, "X": {"estado": "pendente", "estrategia": "panico"},
               "Y": {"estado": "pendente", "estrategia": "recuo"}, "Z": {"estado": "fechada", "estrategia": "panico"}}
        self.assertEqual(S.plano(H40_OFF, ops), {"PARTI": "gerir", "X": "cancelar_pendente"})

    def test_nao_envia_nada(self):
        src = open(S.__file__).read()
        for p in ("privado", "POST", "urllib", "requests", "/order"):
            self.assertNotIn(p, src)


if __name__ == "__main__":
    unittest.main()


class Protecao(unittest.TestCase):
    def test_stop_completo(self):
        from engine import protecao as P
        ok = [{"slTriggerPx": "0.037", "side": "sell", "sz": "10"}]
        self.assertEqual(P.stop_cobre(ok, "10", "LONG", 0.04128), (True, []))
        self.assertFalse(P.stop_cobre([{"slTriggerPx": "0.037", "side": "sell", "sz": "6"}], "10", "LONG", 0.041)[0])
        self.assertFalse(P.stop_cobre([{"slTriggerPx": "0.037", "side": "buy", "sz": "10"}], "10", "LONG", 0.041)[0])
        self.assertFalse(P.stop_cobre([{"slTriggerPx": "0.045", "side": "sell", "sz": "10"}], "10", "LONG", 0.041)[0])
        self.assertTrue(P.stop_cobre([{"slTriggerPx": "0.037", "side": "sell", "closeFraction": "1"}], "10", "LONG", 0.041)[0])
        self.assertEqual(P.stop_cobre([], "10")[1], ["sem stop ativo"])
