"""(11/11) Robustez: Holm contra o exemplo classico, bootstrap reprodutivel, walk-forward sem fuga de informacao,
regimes sem futuro, sensibilidade, dependencia diaria. Tambem verifica as operacoes de backtest: saida depois da
entrada (sem olhar para o futuro na contabilidade das operacoes)."""
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from backtest.quant import robustez as Rb  # noqa: E402

DIA = 86400


def ops_serie(rs, t0=1_600_000_000, passo=DIA, **extra):
    return [{"R": r, "t_entrada": t0 + i * passo, "t_saida": t0 + i * passo + 3 * DIA, **extra} for i, r in enumerate(rs)]


class Holm(unittest.TestCase):
    def test_exemplo_classico(self):
        # p = 0.01, 0.04, 0.03, 0.005 (m = 4): ajustados 0.03, 0.06, 0.06, 0.02; rejeita so as duas mais pequenas
        r = Rb.holm({"a": 0.01, "b": 0.04, "c": 0.03, "d": 0.005})
        self.assertAlmostEqual(r["d"]["p_ajustado"], 0.02)
        self.assertAlmostEqual(r["a"]["p_ajustado"], 0.03)
        self.assertAlmostEqual(r["c"]["p_ajustado"], 0.06)
        self.assertAlmostEqual(r["b"]["p_ajustado"], 0.06)
        self.assertEqual({k for k, v in r.items() if v["rejeita"]}, {"a", "d"})

    def test_monotono_e_limitado_a_um(self):
        r = Rb.holm({"x": 0.9, "y": 0.8})
        self.assertLessEqual(r["x"]["p_ajustado"], 1.0)
        self.assertGreaterEqual(r["x"]["p_ajustado"], r["y"]["p_ajustado"])


class Media(unittest.TestCase):
    def test_dependencia_soma_por_dia(self):
        ops = ops_serie([1, 1, 1], passo=60) + ops_serie([-1], t0=1_600_000_000 + 5 * DIA)
        self.assertEqual(Rb.por_dia(ops), [3, -1])

    def test_teste_media(self):
        rnd = random.Random(3)
        xs = [0.5 + rnd.gauss(0, 1) for _ in range(200)]
        m, t, p, n = Rb.teste_media(xs)
        self.assertLess(p, 0.001)
        _, _, p0, _ = Rb.teste_media([rnd.gauss(0, 1) for _ in range(200)])
        self.assertGreater(p0, 0.01)

    def test_bootstrap_reprodutivel_e_coerente(self):
        rnd = random.Random(5)
        xs = [0.3 + rnd.gauss(0, 1) for _ in range(150)]
        a = Rb.bootstrap_blocos(xs, n_boot=500, semente=1)
        b = Rb.bootstrap_blocos(xs, n_boot=500, semente=1)
        self.assertEqual(a, b)
        self.assertLess(a["ic"][0], a["media"])
        self.assertGreater(a["ic"][1], a["media"])

    def test_sem_melhores(self):
        rs = [-1] * 19 + [30]
        self.assertLess(Rb.sem_melhores(rs), 0)


class WalkForward(unittest.TestCase):
    def test_so_usa_operacoes_fechadas_antes_do_teste(self):
        vistos = []

        def criterio(rs):
            vistos.append(len(rs))
            return sum(rs) / len(rs)
        a = ops_serie([1.0] * 400, passo=DIA)
        b = ops_serie([-1.0] * 400, passo=DIA)
        wf = Rb.walk_forward({"A": a, "B": b}, treino_dias=100, teste_dias=50, criterio=criterio)
        for p in wf["passos"]:
            if p["escolhida"]:
                self.assertEqual(p["escolhida"], "A")
        for o in wf["oos"]:
            passo = next(p for p in wf["passos"] if p["teste_de"] <= o["t_entrada"] < p["teste_ate"])
            self.assertGreaterEqual(o["t_entrada"], passo["teste_de"])
        self.assertTrue(all(n <= 100 for n in vistos))                 # nunca mais operacoes do que a janela

    def test_futuro_nao_entra_no_treino(self):
        # A so e boa DEPOIS de t_corte; um walk-forward honesto nao a escolhe antes disso
        t0 = 1_600_000_000
        a = ops_serie([-1.0] * 200 + [2.0] * 200, t0=t0)
        b = ops_serie([0.1] * 400, t0=t0)
        wf = Rb.walk_forward({"A": a, "B": b}, treino_dias=60, teste_dias=30)
        primeiros = [p for p in wf["passos"] if p["escolhida"] and p["teste_ate"] <= t0 + 200 * DIA]
        self.assertTrue(primeiros)
        self.assertTrue(all(p["escolhida"] == "B" for p in primeiros))

    def test_operacao_ainda_aberta_no_inicio_do_teste_fica_fora_do_treino(self):
        t0 = 1_600_000_000
        ops = [{"R": 5.0, "t_entrada": t0 + 99 * DIA, "t_saida": t0 + 103 * DIA}] + ops_serie([0.0] * 30, t0=t0)
        wf = Rb.walk_forward({"A": ops}, treino_dias=100, teste_dias=10, minimo_treino=1, inicio=t0, fim=t0 + 120 * DIA,
                             criterio=lambda rs: 99 if 5.0 in rs else 0)
        self.assertNotEqual(wf["passos"][0]["nota_treino"], 99)


class Regimes(unittest.TestCase):
    def test_regime_usa_so_o_passado(self):
        btc = [[1_600_000_000 + i * 14400, 100.0] for i in range(400)] + [[1_600_000_000 + (400 + i) * 14400, 1000.0] for i in range(10)]
        t = btc[399][0]
        self.assertEqual(Rb.regime_btc(btc, t), "descida")              # o salto depois de t nao conta
        self.assertEqual(Rb.regime_btc(btc, btc[405][0]), "subida")

    def test_sem_historico_suficiente(self):
        self.assertIsNone(Rb.regime_btc([[1, 1.0]] * 10, 5))


class Sensibilidade(unittest.TestCase):
    def test_muda_de_sinal_e_fragil(self):
        s = Rb.sensibilidade({"RSI<30": [0.15] * 10, "RSI<35": [-0.05] * 10})
        self.assertTrue(s["fragil"])
        self.assertTrue(s["muda_de_sinal"])

    def test_estavel(self):
        self.assertFalse(Rb.sensibilidade({"a": [0.2] * 5, "b": [0.25] * 5})["fragil"])


class Avaliar(unittest.TestCase):
    def test_bateria(self):
        rnd = random.Random(9)
        ops = ops_serie([rnd.gauss(0.1, 1) for _ in range(120)], ativo="A")
        for i, o in enumerate(ops):
            o["ativo"] = "A" if i % 2 else "B"
        r = Rb.avaliar(ops, n_boot=200)
        self.assertEqual(r["n_operacoes"], 120)
        self.assertEqual(r["ativos"]["grupos"], 2)
        self.assertEqual(r["estabilidade"]["k"], 4)


class OperacoesDeBacktest(unittest.TestCase):
    def test_saida_depois_da_entrada_em_todos_os_registos_gravados(self):
        """Se houver um ficheiro de operacoes de backtest gerado (variavel QUANT_BT_OPS), nenhuma operacao pode sair
        antes de entrar (indicio de fuga de informacao na contabilidade)."""
        p = os.environ.get("QUANT_BT_OPS")
        if not p or not os.path.exists(p):
            self.skipTest("sem ficheiro de operacoes de backtest")
        import json
        ops = json.load(open(p))["operacoes"]
        self.assertTrue(all(o["t_saida"] > o["t_entrada"] for o in ops))


if __name__ == "__main__":
    unittest.main()
