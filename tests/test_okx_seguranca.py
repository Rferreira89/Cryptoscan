"""(05/11, OK do Rui) okx.json e publico: o maximo da conta em USD so fica cifrado; ordens canceladas ficam como
"cancelada" no historico; o travao continua a funcionar com o valor cifrado."""
import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import okx_exec as E  # noqa: E402

H4 = 14400
NOW = 2_000_000_000


class Pico(unittest.TestCase):
    def test_pico_antigo_passa_a_cifrado_e_sai_do_estado_publico(self):
        R = {"ops": {}, "hist": [], "pico": 21.90279405}
        with mock.patch.dict(os.environ, {"DATA_KEY": "teste-segredo"}):
            E.migrar_publico(R, NOW)
            self.assertNotIn("pico", R)
            self.assertNotIn("21.9", json.dumps(R))
            self.assertAlmostEqual(E.ler_pico(R), 21.90279405, places=6)

    def test_sem_chave_o_valor_antigo_fica_e_o_travao_fecha(self):
        R = {"ops": {}, "hist": [], "pico": 21.9}
        with mock.patch.dict(os.environ, {"DATA_KEY": ""}):
            E.migrar_publico(R, NOW)
            self.assertEqual(R["pico"], 21.9)                           # nao se perde: espera pela chave
            self.assertEqual(E.estado_pico(R, {}, 30.0)[0], "fechado")

    def test_chave_errada_fecha_em_vez_de_recomecar(self):
        R = {"ops": {}, "hist": []}
        with mock.patch.dict(os.environ, {"DATA_KEY": "a"}):
            E.guardar_pico(R, 30.0)
        with mock.patch.dict(os.environ, {"DATA_KEY": "b"}):
            self.assertIsNone(E.ler_pico(R))
            est, motivo = E.estado_pico(R, {}, 50.0)
            self.assertEqual(est, "fechado"); self.assertIn("não abre", motivo)

    def test_estado_perdido_com_historico_fecha(self):
        with mock.patch.dict(os.environ, {"DATA_KEY": "k"}):
            self.assertEqual(E.estado_pico({"ops": {}, "hist": [{"estado": "fechada"}]}, {}, 20.0)[0], "fechado")
            self.assertEqual(E.estado_pico({"ops": {"X": {}}, "hist": []}, {}, 20.0)[0], "fechado")
            est, motivo = E.estado_pico({"ops": {}, "hist": []}, {}, 20.0)      # vazio: nova OU perdida -> nao adivinha
            self.assertEqual(est, "fechado"); self.assertIn("inicializ", motivo)

    def test_estado_vazio_so_abre_com_inicializacao_autorizada(self):
        with mock.patch.dict(os.environ, {"DATA_KEY": "k"}):
            R = {"ops": {}, "hist": []}
            self.assertEqual(E.estado_pico(R, {}, 20.0)[0], "fechado")
            self.assertEqual(E.estado_pico(R, {"travao_reiniciar_pico": "2026-11-06"}, 20.0), ("ok", 20.0))
            self.assertEqual(R["pico_reiniciado"], "2026-11-06")
            self.assertAlmostEqual(E.estado_pico(R, {"travao_reiniciar_pico": "2026-11-06"}, 15.0)[1], 20.0)   # nao repete
            self.assertAlmostEqual(E.estado_pico(R, {}, 15.0)[1], 20.0)                                      # segue cifrado

    def test_estado_vazio_sem_chave_nao_inicializa(self):
        with mock.patch.dict(os.environ, {"DATA_KEY": ""}):
            self.assertEqual(E.estado_pico({"ops": {}, "hist": []}, {"travao_reiniciar_pico": "2026-11-06"}, 20.0)[0], "fechado")

    def test_recomeco_manual_uma_vez_por_pedido(self):
        with mock.patch.dict(os.environ, {"DATA_KEY": "k"}):
            R = {"ops": {}, "hist": [{"estado": "fechada"}]}
            c = {"travao_reiniciar_pico": "2026-11-06"}
            self.assertEqual(E.estado_pico(R, c, 18.0), ("ok", 18.0))
            E.guardar_pico(R, 25.0)                                        # sobe depois
            self.assertEqual(E.estado_pico(R, c, 19.0), ("ok", 25.0))      # o mesmo pedido nao recomeca outra vez

    def test_modo_seguro_nao_abre_mas_continua_a_gerir_posicoes(self):
        msgs, chamadas = [], []

        def privado(metodo, path, corpo=None):
            chamadas.append((metodo, path))
            if "trade/order?" in path:
                return {"code": "0", "data": [{"state": "canceled", "accFillSz": "0"}]}
            return {"code": "0", "data": []}
        st = {"real": {"ops": {"AAA": {"inst": "AAA-USD_UM_XPERP-1", "ordId": "1", "estado": "pendente", "valido_ate": NOW + 999, "lim": 1}},
                       "hist": [], "pico": 21.9}}
        with mock.patch.dict(os.environ, {"DATA_KEY": ""}), mock.patch.object(E, "_chaves", return_value=("k", "s", "p")), \
                mock.patch.object(E, "privado", privado), mock.patch.object(E, "cfg", return_value=dict(E.CFG_PADRAO, real=True)), \
                mock.patch.object(E, "reconciliar", lambda *a: None), mock.patch.object(E, "equity", return_value=20.0), \
                mock.patch.object(E, "xperps", side_effect=AssertionError("nao devia procurar contratos")), \
                mock.patch.object(E, "abrir", side_effect=AssertionError("nao devia abrir")):
            E.correr(st, [("BBB", {"t_sig": NOW, "tipo": "recuo"})], NOW, msgs)
        self.assertTrue(any("modo seguro" in m for m in msgs))
        self.assertTrue(any("trade/order?" in p for _, p in chamadas))      # a ordem existente foi acompanhada
        self.assertEqual(st["real"]["hist"][-1]["estado"], "cancelada")
        self.assertNotIn("/api/v5/trade/order", [p for m, p in chamadas if m == "POST"])

    def test_travao_continua_a_funcionar_com_o_pico_cifrado(self):
        msgs = []
        with mock.patch.dict(os.environ, {"DATA_KEY": "teste-segredo"}):
            st = {"real": {"ops": {}, "hist": []}}
            E.guardar_pico(st["real"], 40.0)                        # maximo 40; saldo 20 = -50% > travao de 45%
            with mock.patch.object(E, "_chaves", return_value=("k", "s", "p")), \
                    mock.patch.object(E, "cfg", return_value=dict(E.CFG_PADRAO, real=True, travao_queda_pct=45)), \
                    mock.patch.object(E, "reconciliar", lambda *a: None), mock.patch.object(E, "equity", return_value=20.0), \
                    mock.patch.object(E, "xperps", side_effect=AssertionError("nao devia procurar contratos")):
                E.correr(st, [("AAA", {"t_sig": NOW, "tipo": "recuo"})], NOW, msgs)
            self.assertTrue(any("travão ligado" in m for m in msgs))
            self.assertNotIn("pico", st["real"])
            self.assertAlmostEqual(E.ler_pico(st["real"]), 40.0)


class Canceladas(unittest.TestCase):
    def test_historico_pendente_passa_a_cancelada(self):
        R = {"ops": {}, "hist": [{"asset": "TRUMP", "estado": "pendente", "lim": 1.153}, {"asset": "HUMA", "estado": "fechada", "motivo": "stop ou objetivo"}]}
        E.migrar_publico(R, NOW)
        self.assertEqual([h["estado"] for h in R["hist"]], ["cancelada", "fechada"])
        self.assertIn("cancelada", R["hist"][0]["motivo"])

    def test_ordem_cancelada_na_corretora_fica_cancelada(self):
        op = {"inst": "X-USD_UM_XPERP-1", "ordId": "1", "estado": "pendente", "valido_ate": NOW + 999, "lim": 1}
        with mock.patch.object(E, "privado", return_value={"code": "0", "data": [{"state": "canceled", "accFillSz": "0"}]}):
            self.assertTrue(E.acompanhar("X", op, NOW, []))
        self.assertEqual((op["estado"], op["motivo"]), ("cancelada", "cancelada sem executar"))

    def test_ordem_caducada_fica_cancelada(self):
        op = {"inst": "X-USD_UM_XPERP-1", "ordId": "1", "estado": "pendente", "valido_ate": NOW - 1, "lim": 1}
        respostas = iter([{"code": "0", "data": [{"state": "live"}]},                       # consulta: viva e caducada
                          {"code": "0", "data": [{"sCode": "0"}]},                           # pedido de cancelamento
                          {"code": "0", "data": [{"state": "canceled", "accFillSz": "0"}]}])  # estado final na OKX
        with mock.patch.object(E, "privado", lambda *a, **k: next(respostas)):
            self.assertTrue(E.acompanhar("X", op, NOW, []))
        self.assertEqual(op["estado"], "cancelada"); self.assertIn("caducou", op["motivo"])


if __name__ == "__main__":
    unittest.main()
