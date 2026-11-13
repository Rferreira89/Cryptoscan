"""(13/11, A1) Sombra das rejeitadas: plano completo, sem futuro, sem duplicados, regras de saida iguais, custos."""
import unittest

from engine import sombra_rejeitadas as S

TF = 14400


def vela(t, o, h, l, c):
    return {"t": t, "o": o, "h": h, "l": l, "c": c, "v": 1}


SIG = {"side": "SHORT", "stop": 110.0, "tp": [90.0, 80.0], "partials": [50, 50], "t_sig": 10 * TF,
       "hold_s": 20 * 86400, "breakeven": True, "atr": 4.0}


class Sombra(unittest.TestCase):
    def test_regista_com_plano_e_sem_duplicados(self):
        st = {"mercado": {"regime": "lateral"}, "juros_bybit": {"m": {"AAA": 0.02}}}
        k = S.registar(st, 10 * TF + 60, "AAA", "SHORT_TURTLE", "diversificação: x", SIG, 100.0, {"risk_pct": 1.5})
        self.assertIsNotNone(k)
        self.assertIsNone(S.registar(st, 10 * TF + 120, "AAA", "SHORT_TURTLE", "liquidez: y", SIG, 100.0))
        o = st["sombra_rejeitadas"]["abertas"][k]
        self.assertEqual((o["filtro"], o["regime"], o["lado"], o["plano"]["risk_pct"], o["plano"]["stop_pct"]),
                         ("diversificação", "lateral", "SHORT", 1.5, 10.0))
        self.assertAlmostEqual(o["juro_dia"], 0.0002)

    def test_sem_futuro_salta_a_vela_em_curso(self):
        st = {}
        S.registar(st, 10 * TF + 60, "AAA", "SHORT_TURTLE", "x: y", SIG, 100.0)
        # a vela que abre em t_sig (em curso no momento da decisao) toca no objetivo, mas nao conta
        bars = {"AAA": [vela(10 * TF, 100, 101, 85, 95)]}
        self.assertEqual(S.atualizar(st, bars, 11 * TF + 1), [])
        self.assertEqual(len(st["sombra_rejeitadas"]["abertas"]), 1)
        # a vela seguinte ainda nao fechou: tambem nao conta
        bars["AAA"].append(vela(11 * TF, 100, 115, 99, 112))
        self.assertEqual(S.atualizar(st, bars, 11 * TF + 100), [])
        f = S.atualizar(st, bars, 12 * TF + 1)
        self.assertEqual(f[0]["exit_reason"], "STOP")
        self.assertLess(f[0]["r"], -1.0)                 # stop com custos e deslize: pior que -1R

    def test_objetivos_e_juro_do_short(self):
        st = {"juros_bybit": {"m": {"AAA": 0.0}}}
        S.registar(st, 10 * TF + 60, "AAA", "SHORT_TURTLE", "x: y", SIG, 100.0)
        bars = {"AAA": [vela(10 * TF, 100, 100, 100, 100), vela(11 * TF, 99, 99, 79, 80)]}
        f = S.atualizar(st, bars, 12 * TF + 1)
        self.assertEqual(f[0]["exit_reason"], "TP2")
        self.assertGreater(f[0]["r"], 1.0)
        st2 = {}
        S.registar(st2, 10 * TF + 60, "AAA", "SHORT_TURTLE", "x: y", SIG, 100.0)
        f2 = S.atualizar(st2, bars, 12 * TF + 1)
        self.assertLess(f2[0]["r"], f[0]["r"])           # sem taxa conhecida: juro padrao descontado

    def test_resumo_por_filtro(self):
        st = {"sombra_rejeitadas": {"abertas": {}, "chaves": [], "fechadas": [
            {"filtro": "liquidez", "strategy": "S", "regime": "lateral", "corretora": "bybit_ue", "r": 1.5},
            {"filtro": "liquidez", "strategy": "S", "regime": "lateral", "corretora": "bybit_ue", "r": -1.0}]}}
        r = S.resumo(st)["por_filtro"]["liquidez"]
        self.assertEqual((r["n"], r["vencedoras_pct"], r["ganhos_perdidos_r"], r["perdas_evitadas_r"]), (2, 50.0, 1.5, 1.0))

    def test_plano_incoerente_nao_entra(self):
        self.assertIsNone(S.registar({}, 1, "AAA", "S", "x", dict(SIG, stop=95.0), 100.0))


if __name__ == "__main__":
    unittest.main()
