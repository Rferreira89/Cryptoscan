"""(11/11, P7) Historico agregado do mapa de exposicao: idempotente, sem dados privados, manual separado do diario."""
import os
import sys
import tempfile
import unittest

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.join(RAIZ, "tools"))
import exposicao_historico as H  # noqa: E402
import exposicao_diaria as D  # noqa: E402

MAPA = {"t": 1794380000, "blocos": {
    "okx_real": {"n": 1, "long": 1, "short": 0, "apostas_efetivas": 1.0, "grupos_correlacionados": [],
                 "conflitos": {"mesmo_ativo_oposto": {}, "grupo_oposto": [], "mesma_exposicao": {}}, "sem_precos": []},
    "papel": {"n": 39, "long": 6, "short": 33, "apostas_efetivas": 4.2,
              "grupos_correlacionados": [{"n": 12, "lado": "SHORT", "ativos": ["A"]}],
              "conflitos": {"mesmo_ativo_oposto": {"HUMA": ["x", "y"]}, "grupo_oposto": [], "mesma_exposicao": {"DOGE": [1, 2]}},
              "sem_precos": ["Z"]}},
    "dados_em_falta": [], "okx_posicoes_reais": {"AAA": {"entrada": 1.23, "atual": 1.3, "r": 0.4}}}


class Historico(unittest.TestCase):
    def test_entrada_so_contagens(self):
        e = H.entrada(MAPA, "2026-11-11", "diario")
        self.assertEqual(e["blocos"]["papel"]["short"], 33)
        self.assertEqual(e["blocos"]["papel"]["maior_grupo"], 12)
        self.assertEqual(e["blocos"]["papel"]["conflitos_mesmo_ativo_oposto"], 1)
        self.assertNotIn("okx_posicoes_reais", e)
        self.assertEqual(H.sem_privados([e]), [])
        self.assertNotIn("1.23", str(e))

    def test_idempotente_no_mesmo_dia_e_tipo(self):
        h = H.atualizar([], H.entrada(MAPA, "2026-11-11", "diario"))
        h = H.marcar_enviado(h, "2026-11-11", "diario")
        h = H.atualizar(h, H.entrada(MAPA, "2026-11-11", "diario"))
        self.assertEqual(len(h), 1)
        self.assertTrue(h[0]["enviado"])                        # repetir nao apaga o envio ja feito

    def test_manual_nao_conta_como_diario(self):
        h = H.atualizar([], H.entrada(MAPA, "2026-11-10", "manual"))
        h = H.marcar_enviado(h, "2026-11-10", "manual")
        self.assertFalse(H.ja_houve_diario(h, "2026-11-10"))
        h = H.atualizar(h, H.entrada(MAPA, "2026-11-10", "diario"))
        self.assertEqual(len(h), 2)
        h = H.marcar_enviado(h, "2026-11-10", "diario")
        self.assertTrue(H.ja_houve_diario(h, "2026-11-10"))

    def test_gravar_e_ler_com_linha_partida(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "h.jsonl")
            H.gravar(p, [H.entrada(MAPA, "2026-11-11", "diario")])
            with open(p, "a") as f:
                f.write("{partida\n")
            self.assertEqual(len(H.ler(p)), 1)

    def test_titulo_marca_execucao_manual(self):
        self.assertIn("manual", D.titulo(True))
        self.assertNotIn("manual", D.titulo(False))


class Workflows(unittest.TestCase):
    def ler(self, nome):
        return open(os.path.join(RAIZ, ".github", "workflows", nome)).read()

    def test_ciclo_do_scan_so_conta_execucoes_diarias(self):
        y = self.ler("scan.yml")
        self.assertIn('contains("(diario)")', y)
        self.assertIn("-f origem=diario", y)

    def test_mapa_regista_e_nao_repete_envio(self):
        y = self.ler("exposicao-diaria.yml")
        self.assertIn("exposicao_historico.py registar", y)
        self.assertIn("ja-enviado", y)
        self.assertIn("run-name:", y)
        self.assertIn("publicar_estado.py publicar /tmp/exh exposicao", y)


if __name__ == "__main__":
    unittest.main()
