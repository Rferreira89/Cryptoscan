"""(2026-11-11) Auditoria de rentabilidade das estrategias existentes: acontecimentos por dia, intervalos agrupados,
tetos de posicoes, regime sem retrospetiva, stops so com velas fechadas, regras de classificacao e walk-forward que
nao toca na reserva. Dados sinteticos (nada vem da rede)."""
import inspect
import random
import unittest

from tools import auditoria_rentabilidade as A

DAY = 86400
H4 = 14400


def op(dia, r, ativo="X", h=0, dur=3 * DAY, est="E"):
    t = dia * DAY + h * 3600
    return {"t_entrada": t, "t_saida": t + dur, "R": r, "ativo": ativo, "estrategia": est}


class Metricas(unittest.TestCase):
    def test_dia_com_muitas_operacoes_nao_vale_por_muitos_acontecimentos(self):
        # 1 dia com 20 ganhos e 19 dias com 1 perda: por operacao parece bom, por acontecimento e mau
        ops = [op(100, 1.0, f"A{i}") for i in range(20)] + [op(101 + i, -0.5) for i in range(19)]
        m = A.metricas(ops, random.Random(1), 500)
        self.assertEqual(m["dias"], 20)
        self.assertGreater(m["media_op"], 0)
        self.assertLess(m["media_dia"], 0)

    def test_intervalo_agrupado_mais_largo_que_o_ingenuo(self):
        rnd = random.Random(2)
        ops = []
        for d in range(40):                       # dias inteiros a ganhar ou a perder juntos
            s = rnd.choice((1.0, -1.0))
            ops += [op(200 + d, s + rnd.gauss(0, 0.05), f"A{k}") for k in range(10)]
        lo, hi = A.bootstrap_op_agrupado(ops, 1000, random.Random(3))
        se_ingenuo = (sum((o["R"] - 0) ** 2 for o in ops) / len(ops)) ** 0.5 / len(ops) ** 0.5
        self.assertGreater(hi - lo, 2 * 1.645 * se_ingenuo * 1.5)

    def test_drawdown_e_pf(self):
        m = A.metricas([op(1, 2.0), op(2, -1.0), op(3, -1.0), op(4, 1.0)], reps=100)
        self.assertEqual(m["max_dd_r"], -2.0)
        self.assertAlmostEqual(m["pf"], 1.5)


class Tetos(unittest.TestCase):
    def test_teto_de_abertas(self):
        ops = [op(10, 1.0, f"A{i}", dur=2 * DAY) for i in range(5)] + [op(11, -1.0, "B", dur=DAY), op(13, -1.0, "C")]
        xs = A.limitar_simultaneas(ops, 3)
        self.assertEqual(len([o for o in xs if o["t_entrada"] // DAY == 10]), 3)
        self.assertNotIn("B", [o["ativo"] for o in xs])          # dia 11: as 3 do dia 10 ainda abertas
        self.assertIn("C", [o["ativo"] for o in xs])             # dia 13: ja fecharam

    def test_limite_por_dia_nao_olha_para_o_resultado(self):
        ops = [op(5, -1.0, "Z"), op(5, 3.0, "A"), op(5, 3.0, "B")]
        self.assertEqual([o["ativo"] for o in A.limitar_por_dia(ops, 1)], ["A"])   # ordem pelo ativo, nao pelo R
        ops2 = [op(5, 3.0, "Z"), op(5, -1.0, "A")]
        self.assertEqual([o["R"] for o in A.limitar_por_dia(ops2, 1)], [-1.0])


class SemRetrospetiva(unittest.TestCase):
    def test_regime_vale_para_o_dia_seguinte(self):
        btc = [(d * DAY + k * H4, 100.0) for d in range(60) for k in range(6)]
        btc += [(60 * DAY + k * H4, 1000.0) for k in range(6)]        # salto no dia 60
        reg = A.btc_regime(btc)
        self.assertFalse(reg[60])                                     # o dia 60 ainda usa o fecho do dia 59
        self.assertTrue(reg[61])

    def test_stop_so_com_velas_fechadas(self):
        bars = [{"t": i * H4, "o": 100, "h": 101, "l": 99, "c": 100} for i in range(60)]
        base = A.stop_pct(bars, 60 * H4)
        bars.append({"t": 60 * H4, "o": 100, "h": 200, "l": 50, "c": 100})   # vela gigante ainda por fechar
        self.assertEqual(A.stop_pct(bars, 60 * H4 + 100), base)
        self.assertAlmostEqual(base, 2 * 2 / 100 * 100)

    def test_sensibilidade_aos_custos(self):
        ops = [dict(op(1, 0.2), stop_pct=10.0), dict(op(2, 0.2), stop_pct=10.0)]
        s = A.sensibilidade(ops)
        self.assertAlmostEqual(s["r_por_0_1pct"], 0.01)
        self.assertAlmostEqual(s["custo_extra_que_anula_pct"], 2.0)


class Classificacao(unittest.TestCase):
    def test_backtest_sozinho_nunca_e_A(self):
        c, _ = A.classificar({"bt_fora": 0.5, "bt_fora_ic_inf": 0.2, "real": {}, "papel": {}})
        self.assertEqual(c, "B")

    def test_A_precisa_de_30_dias_reais_positivos(self):
        real = {"n": 60, "dias": 35, "media_dia": 0.2, "media_op": 0.2, "ic90_dia": [0.05, 0.3]}
        self.assertEqual(A.classificar({"real": real, "bt_fora": 0.1})[0], "A")
        self.assertNotEqual(A.classificar({"real": dict(real, dias=20), "bt_fora": 0.1})[0], "A")

    def test_E_negativa_ao_vivo_e_sem_prova(self):
        c, _ = A.classificar({"papel": {"n": 20, "media_op": -0.4}, "real": {}, "bt_fora": -0.05})
        self.assertEqual(c, "E")

    def test_D_so_sem_prova(self):
        self.assertEqual(A.classificar({"bloqueio": "ordens canceladas"})[0], "D")
        self.assertEqual(A.classificar({"bloqueio": "ordens canceladas", "bt_fora": -0.01})[0], "C")

    def test_arena_exige_ano_liquido_positivo(self):
        e = {"arena_fora_liq": 0.7, "arena_fora_n": 14, "acima_acaso": True, "arena_liq": -0.12}
        self.assertEqual(A.classificar(e)[0], "C")
        self.assertEqual(A.classificar(dict(e, arena_liq=0.1))[0], "B")


class WalkForward(unittest.TestCase):
    def test_nao_usa_a_reserva_e_corrige_holm(self):
        d0 = (A.CORTE - 400 * DAY) // DAY
        rnd = random.Random(4)
        ops = [dict(op(d0 + i, rnd.gauss(0.0, 1.0), f"A{i % 7}"), stop_pct=rnd.choice((5, 15))) for i in range(400)]
        ops += [dict(op(A.CORTE // DAY + i, 50.0), stop_pct=15) for i in range(30)]   # reserva enorme: nao pode contar
        wf = A.walk_forward(A.marcar_dia(ops), {}, A.FILTROS, random.Random(5), 300)
        x = wf["stop_largo_(>=12pct)"]
        self.assertLess(abs(x["validacao"]["media_dia"]), 1.0)
        self.assertFalse(x["passa"])
        self.assertTrue(all(v["p_holm"] >= (v["p_unilateral"] or 0) for k, v in wf.items() if not k.startswith("_")))


class Bloqueados(unittest.TestCase):
    def test_short_ganha_quando_cai_e_paga_custos(self):
        bars = {"M": [{"t": i * H4, "o": 100 - i, "h": 101 - i, "l": 99 - i, "c": 99 - i} for i in range(40)]}
        pl = [{"t": 5 * H4 - 10, "asset": "M", "strategy": "SHORT_X", "reason": "plano: x"},
              {"t": 5 * H4 - 10, "asset": "M", "strategy": "BOUNCE_X", "reason": "liquidez: y"}]
        r = A.bloqueados_bybit(pl, bars)["grupos"]
        self.assertGreater(r["SHORT_* | plano"]["liquido_medio_pct"], 0)
        self.assertLess(r["BOUNCE_X | liquidez"]["liquido_medio_pct"], 0)

    def test_sinal_sem_velas_suficientes_nao_conta(self):
        bars = {"M": [{"t": i * H4, "o": 1, "h": 1, "l": 1, "c": 1} for i in range(10)]}
        r = A.bloqueados_bybit([{"t": 5 * H4, "asset": "M", "strategy": "B", "reason": "x"}], bars)
        self.assertEqual(r["sem_dados"], 1)


class SemCorretoras(unittest.TestCase):
    def test_nao_chama_corretoras_nem_escreve_estado(self):
        src = inspect.getsource(A)
        for proibido in ("okx_exec", "privado(", "/trade/", "/v5/order", "urlopen", "publicar_estado", "cofre"):
            self.assertNotIn(proibido, src)


if __name__ == "__main__":
    unittest.main()
