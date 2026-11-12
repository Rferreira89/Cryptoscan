"""(12/11) Motor de descoberta LONG: criterio fixo (tres periodos, dias independentes, Holm), custos por corretora,
comparacao passiva, redundancia e portao de espera. Dados sinteticos; so leitura."""
import inspect
import random
import unittest

from tools import descoberta_long as D

DAY = 86400


def ops(k, fase, r_por_periodo, dias=30, por_dia=1, stop=0.1, semente=1):
    rnd = random.Random(semente)
    out = []
    for inicio, media in zip((1672531200, D.T_TREINO, D.T_VALID), r_por_periodo):
        for d in range(dias):
            for j in range(por_dia):
                t = inicio + d * 3 * DAY + j * 3600
                out.append({"k": k, "fam": "teste", "a": f"M{j}", "t": t, "t_fim": t + 2 * DAY, "r": media + rnd.gauss(0, 0.3),
                            "stop": stop, "fase": fase})
    return out


class Criterio(unittest.TestCase):
    def test_vantagem_nos_tres_periodos_e_candidata(self):
        linhas, _ = D.avaliar(ops("BOA", "subida", (0.5, 0.5, 0.5)), {}, reps=300)
        l = [x for x in linhas if x["corretora"] == "bybit_ue"][0]
        self.assertTrue(l["candidata"])
        self.assertIn("real so com aprovacao", l["veredicto"])

    def test_um_periodo_negativo_chega_para_reprovar(self):
        linhas, _ = D.avaliar(ops("SO_TREINO", "subida", (0.8, 0.5, -0.2)), {}, reps=300)
        self.assertFalse(any(l["candidata"] for l in linhas))

    def test_muitas_operacoes_em_poucos_dias_nao_passam(self):
        linhas, _ = D.avaliar(ops("CONCENTRADA", "subida", (0.6, 0.6, 0.6), dias=5, por_dia=20), {}, reps=300)
        l = linhas[0]
        self.assertEqual(l["fora"]["dias"], 5)
        self.assertFalse(l["candidata"])                            # 100 operacoes, 5 acontecimentos

    def test_ruido_nao_passa_e_holm_nunca_baixa_o_p(self):
        todas = []
        for i in range(12):
            todas += ops(f"RUIDO{i}", "lateral", (0.0, 0.0, 0.0), semente=i)
        linhas, _ = D.avaliar(todas, {}, reps=200)
        # (na OKX o custo mais baixo e uma vantagem real do exemplo sintetico; o ruido puro ve-se nos custos Bybit)
        self.assertFalse(any(l["candidata"] for l in linhas if l["corretora"] == "bybit_ue"))
        self.assertTrue(all(l["p_holm"] >= l["p"] - 1e-9 for l in linhas))


class Custos(unittest.TestCase):
    def test_okx_mais_barata_mas_paga_financiamento(self):
        t = {"r": 0.0, "stop": 0.1, "t": 0, "t_fim": 0}
        self.assertAlmostEqual(D.r_okx(t), (0.007 - 0.002) / 0.1)
        longo = {"r": 0.0, "stop": 0.1, "t": 0, "t_fim": 30 * DAY}
        self.assertLess(D.r_okx(longo), 0)                          # 30 dias de financiamento comem a diferenca

    def test_passivo_btc_na_mesma_unidade(self):
        px = {0: 100.0, 14400 * 12: 110.0}
        self.assertAlmostEqual(D.r_passivo_btc({"t": 0, "t_fim": 14400 * 12, "stop": 0.1}, px), 1.0)
        self.assertIsNone(D.r_passivo_btc({"t": 0, "t_fim": 999999999, "stop": 0.1}, px))


class PortaoERedundancia(unittest.TestCase):
    def test_espera_quando_nada_passa_na_fase_atual(self):
        linhas, _ = D.avaliar(ops("BOA", "subida", (0.5, 0.5, 0.5)), {}, reps=300)
        self.assertFalse(D.portao(linhas, "lateral")["long_permitido"])
        self.assertIn("ESPERA", D.portao(linhas, "lateral")["decisao"])
        self.assertTrue(D.portao(linhas, "subida")["long_permitido"])

    def test_copias_sao_assinaladas(self):
        a = ops("ORIGINAL", "subida", (0.3, 0.3, 0.3), semente=5)
        b = [dict(o, k="COPIA", r=o["r"] + 0.01) for o in a]
        _, red = D.avaliar(a + b, {}, reps=100)
        self.assertEqual((red[0]["a"], red[0]["b"]), ("COPIA", "ORIGINAL"))


class SoInvestigacao(unittest.TestCase):
    def test_sem_chaves_nem_ordens(self):
        src = inspect.getsource(D)
        for proibido in ("API_KEY", "urlopen", "/v5/order", "/trade/", "privado(", "real_autorizados\"]", "config.json"):
            self.assertNotIn(proibido, src)

    def test_so_familias_long(self):
        self.assertFalse([k for ks in D.FAMILIAS.values() for k in ks if k.startswith("SHORT")])


if __name__ == "__main__":
    unittest.main()


class Classes(unittest.TestCase):
    def test_tres_classes(self):
        boa, _ = D.avaliar(ops("BOA", "subida", (0.5, 0.5, 0.5)), {}, reps=300)
        self.assertEqual(boa[0]["classe"], "VANTAGEM DEMONSTRADA")
        poucos, _ = D.avaliar(ops("POUCOS", "subida", (0.5, 0.5, 0.5), dias=6), {}, reps=300)
        self.assertEqual(poucos[0]["classe"], "INCONCLUSIVA")       # positivo mas sem dias suficientes
        ma, _ = D.avaliar(ops("MA", "subida", (0.1, -0.5, -0.5)), {}, reps=300)
        self.assertEqual(ma[0]["classe"], "SEM VANTAGEM (NEGATIVA)")

    def test_markdown_tem_todas_as_linhas(self):
        linhas, red = D.avaliar(ops("BOA", "subida", (0.5, 0.5, 0.5)), {}, reps=100)
        md = D.markdown({"resultados": linhas, "redundantes": red, "portao": D.portao(linhas, "subida")})
        self.assertEqual(md.count("| BOA |"), 2)
