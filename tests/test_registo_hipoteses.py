import copy
import json
import os
import tempfile
import unittest

from tools import registo_hipoteses as R


def ficha(id_="T1", **kw):
    f = {"id": id_, "familia": "F", "justificacao": "liquidez asiatica", "fonte_dados": "history 4H",
         "universo": "todas as moedas do history", "direcao": "LONG", "temporalidade": "4H",
         "entrada": "abertura das 04h UTC", "saida": "fecho da mesma vela",
         "custos": {"por_lado_pct": 0.35, "nota": "0,25% + 0,1%"},
         "h0": "retorno medio liquido <= 0", "metrica_primaria": {"nome": "r_liquido_medio"},
         "criterios_rejeicao": ["r_liquido_medio <= 0", "p_holm > 0,05"],
         "protocolo": "prospetivo 60 dias", "grelha": [{"h": 1}],
         "exploracao": {"inicio": "2021-01-01", "fim": "2026-05-08"},
         "validacao": {"tipo": "prospetiva", "inicio": "2026-11-12"}}
    f.update(kw)
    return f


Q = "2026-11-11T12:00:00Z"


class TestCadeia(unittest.TestCase):
    def setUp(self):
        self.L = []
        for i in range(3):
            R.acrescentar(self.L, "nota", f"N{i}", {"x": i}, Q)

    def test_integra(self):
        self.assertEqual(R.verificar(self.L), [])

    def test_alterar_linha_antiga_parte_a_cadeia(self):
        m = copy.deepcopy(self.L)
        m[1]["dados"]["x"] = 99
        self.assertTrue(R.verificar(m))

    def test_apagar_linha_do_meio(self):
        m = copy.deepcopy(self.L)
        del m[1]
        self.assertTrue(R.verificar(m))

    def test_encurtar_detetado_contra_versao_anterior(self):
        self.assertTrue(R.verificar_prefixo(self.L, self.L[:2]))
        self.assertEqual(R.verificar_prefixo(self.L[:2], self.L), [])

    def test_gravar_so_acrescenta(self):
        with tempfile.TemporaryDirectory() as d:
            f = os.path.join(d, "r.jsonl")
            R.gravar(self.L[:2], f)
            R.gravar(self.L, f)
            self.assertEqual(len(R.ler(f)), 3)
            outra = []
            R.acrescentar(outra, "nota", "Z", {}, Q)
            with self.assertRaises(R.RegistoErro):
                R.gravar(outra, f)                     # nao e continuacao do que esta no disco


class TestFicha(unittest.TestCase):
    def test_ficha_completa_entra(self):
        L = []
        rec = R.pre_registar(L, ficha(), Q)
        self.assertEqual(rec["tipo"], "pre_registo")

    def test_campos_obrigatorios(self):
        for campo in ("h0", "metrica_primaria", "criterios_rejeicao", "justificacao", "exploracao"):
            f = ficha()
            f.pop(campo)
            with self.assertRaises(R.RegistoErro):
                R.pre_registar([], f, Q)

    def test_familia_direcao_grelha_custos(self):
        for kw in ({"familia": "Z"}, {"direcao": "COMPRA"}, {"grelha": [{}] * 7},
                   {"custos": {"por_lado_pct": 0.1}}):
            with self.assertRaises(R.RegistoErro):
                R.pre_registar([], ficha(**kw), Q)

    def test_validacao_nao_pode_sobrepor_exploracao(self):
        f = ficha(validacao={"tipo": "reserva", "inicio": "2026-05-01", "fim": "2026-11-08"})
        with self.assertRaises(R.RegistoErro):
            R.pre_registar([], f, Q)

    def test_prospetiva_comeca_depois_do_registo(self):
        with self.assertRaises(R.RegistoErro):
            R.pre_registar([], ficha(validacao={"tipo": "prospetiva", "inicio": "2026-11-01"}), Q)

    def test_id_repetido(self):
        L = []
        R.pre_registar(L, ficha(), Q)
        with self.assertRaises(R.RegistoErro):
            R.pre_registar(L, ficha(), Q)


class TestReservaEVeredicto(unittest.TestCase):
    RES = {"inicio": "2026-05-08", "fim": "2026-11-08"}

    def _hip_reserva(self, L, id_):
        R.pre_registar(L, ficha(id_, exploracao={"inicio": "2024-11-08", "fim": "2026-05-08"},
                                validacao=dict(self.RES, tipo="reserva")), Q)

    def test_reserva_uma_so_vez(self):
        L = []
        self._hip_reserva(L, "A")
        R.usar_dados(L, "A", "reserva", self.RES, Q)
        with self.assertRaises(R.RegistoErro):
            R.usar_dados(L, "A", "reserva", self.RES, Q)

    def test_reserva_limpa_permite_candidata(self):
        L = []
        self._hip_reserva(L, "A")
        R.usar_dados(L, "A", "reserva", self.RES, Q)
        self.assertEqual(R.veredicto_maximo(L, "A"), "CANDIDATA")

    def test_reserva_ja_vista_so_permite_papel(self):
        L = []
        R.acrescentar(L, "retroativo", "VELHA", {"familia": "B", "janela": {"inicio": "2021-01-01",
                                                                             "fim": "2026-11-01"}}, Q)
        self._hip_reserva(L, "A")
        rec = R.usar_dados(L, "A", "reserva", self.RES, Q)
        self.assertEqual(rec["dados"]["ja_vista_por"], 1)
        self.assertEqual(R.veredicto_maximo(L, "A"), "PARA PAPEL")
        with self.assertRaises(R.RegistoErro):
            R.registar_resultado(L, "A", {"metricas": {"r_liquido_medio": 0.3}, "veredicto": "CANDIDATA"},
                                 "2026-11-12T00:00:00Z")
        ok = R.registar_resultado(L, "A", {"metricas": {"r_liquido_medio": 0.3}, "veredicto": "PARA PAPEL"},
                                  "2026-11-12T00:00:00Z")
        self.assertEqual(ok["dados"]["teto"], "PARA PAPEL")

    def test_sem_validacao_so_exploratoria(self):
        L = []
        R.pre_registar(L, ficha(), Q)
        self.assertEqual(R.veredicto_maximo(L, "T1"), "EXPLORATORIA")
        with self.assertRaises(R.RegistoErro):
            R.registar_resultado(L, "T1", {"metricas": {"r_liquido_medio": 1}, "veredicto": "PARA PAPEL"},
                                 "2026-11-12T00:00:00Z")
        R.registar_resultado(L, "T1", {"metricas": {"r_liquido_medio": -1}, "veredicto": "REJEITADA"},
                             "2026-11-12T00:00:00Z")

    def test_prospetiva_antes_do_registo_recusada(self):
        L = []
        R.pre_registar(L, ficha(), Q)
        with self.assertRaises(R.RegistoErro):
            R.usar_dados(L, "T1", "prospetiva", {"inicio": "2026-11-01"}, Q)
        R.usar_dados(L, "T1", "prospetiva", {"inicio": "2026-11-12"}, Q)
        self.assertEqual(R.veredicto_maximo(L, "T1"), "CANDIDATA")

    def test_resultado_exige_metrica_primaria_e_ordem(self):
        L = []
        R.pre_registar(L, ficha(), Q)
        with self.assertRaises(R.RegistoErro):
            R.registar_resultado(L, "T1", {"metricas": {"outra": 1}, "veredicto": "REJEITADA"},
                                 "2026-11-12T00:00:00Z")
        with self.assertRaises(R.RegistoErro):
            R.registar_resultado(L, "T1", {"metricas": {"r_liquido_medio": 1}, "veredicto": "REJEITADA"},
                                 "2026-11-10T00:00:00Z")
        with self.assertRaises(R.RegistoErro):
            R.registar_resultado(L, "SEM", {"metricas": {}, "veredicto": "REJEITADA"})

    def test_dados_sem_ficha(self):
        with self.assertRaises(R.RegistoErro):
            R.usar_dados([], "NADA", "reserva", self.RES, Q)


class TestRegistoDoRepositorio(unittest.TestCase):
    """O ficheiro guardado no repositorio esta integro e cobre o passado."""

    def test_integro(self):
        L = R.ler()
        self.assertTrue(L, "registo vazio")
        self.assertEqual(R.verificar(L), [])

    def test_semente_cobre_os_diarios(self):
        L = R.ler()
        ids = {r["id"] for r in L}
        for h in range(1, 16):
            self.assertIn(f"AFI-H{h}", ids)
        conta = sum(1 for r in L if r["tipo"] == "retroativo" and r["dados"].get("conta_reserva")
                    and r["dados"]["origem"] in ("investigacao", "afinacao"))
        self.assertEqual(conta, 26)            # o contador do diario em 2026-11-11
        for r in L:
            if r["tipo"] in ("retroativo", "pre_registo"):
                self.assertIn(r["dados"]["familia"], R.FAMILIAS)

    def test_classificador(self):
        self.assertEqual(R.classificar_familia("SHORT_SQUEEZE"), "C")
        self.assertEqual(R.classificar_familia("BOUNCE_X30"), "B")
        self.assertEqual(R.classificar_familia("Funding muito negativo"), "I")
        self.assertEqual(R.classificar_familia("TURTLE"), "D")


if __name__ == "__main__":
    unittest.main()
