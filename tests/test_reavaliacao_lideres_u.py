import unittest

from tools import arena_ringue as AR
from tools import reavaliacao_lideres_u as RL

H4, DAY = AR.H4, AR.DAY


def velas(n, t0=1_700_000_000 - (1_700_000_000 % H4)):
    out = []
    for i in range(n):
        p = 100 + (i % 7) - 3
        out.append({"t": t0 + i * H4, "o": p, "h": p + 2, "l": p - 2, "c": p + 0.5, "v": 1000.0, "bv": 500.0})
    return out


class TestReavaliacao(unittest.TestCase):
    def test_janelas_sem_sobreposicao(self):
        end = 1_795_190_400
        j = RL.janelas(end)
        self.assertEqual(j["reserva"][1], end)
        self.assertEqual(j["desenho"][1], j["reserva"][0])
        self.assertEqual(j["reserva"][1] - j["reserva"][0], RL.RES_DIAS * DAY)
        self.assertLess(j["antigo"][1], j["desenho"][0])

    def test_decide(self):
        self.assertEqual(RL.decide({"n": 5, "avg_r": 1.0, "acaso_p95": 0.0}), "AMOSTRA INSUFICIENTE")
        self.assertEqual(RL.decide({"n": 30, "avg_r": 0.2, "acaso_p95": 0.1}), "MANTEM")
        self.assertEqual(RL.decide({"n": 30, "avg_r": 0.2, "acaso_p95": 0.3}), "PERDE")
        self.assertEqual(RL.decide({"n": 30, "avg_r": -0.1, "acaso_p95": -0.5}), "PERDE")

    def test_sem_look_ahead(self):
        """A funcao de sinal so ve velas fechadas antes da entrada, e o resultado
        de uma operacao nao muda se as velas depois do fecho dela forem alteradas."""
        c4 = velas(400)
        vistos = []

        def fn(w):
            vistos.append(w[-1]["t"])
            if len(vistos) % 40 != 0:
                return None
            c = w[-1]["c"]
            return {"stop": c * 0.97, "tp": [c * 1.02], "partials": [100], "breakeven": True, "hold_s": 2 * DAY}

        above = {k: True for k in range(c4[0]["t"] // DAY - 2, c4[-1]["t"] // DAY + 2)}
        trs = RL.operacoes(fn, True, {"X": c4}, above, 0)
        self.assertTrue(trs)
        for t in trs:
            self.assertTrue(any(v + H4 <= t["t"] for v in vistos))
        # nunca viu a vela de entrada de nenhuma operacao antes de decidir
        entradas = {t["t"] for t in trs}
        self.assertFalse(entradas & set(vistos[i] for i in range(39, len(vistos), 40)))
        # mudar o futuro depois do fecho da 1.a operacao nao muda essa operacao
        t1 = trs[0]
        fut = [dict(x) for x in c4]
        for x in fut:
            if x["t"] > t1["t_fim"]:
                x.update(o=1.0, h=1.0, l=1.0, c=1.0)
        vistos.clear()
        trs2 = RL.operacoes(fn, True, {"X": fut}, above, 0)
        self.assertEqual((trs2[0]["t"], trs2[0]["r"]), (t1["t"], t1["r"]))

    def test_funcoes_sao_as_da_arena(self):
        self.assertIs(RL.LIDERES["BOUNCE_AMPLITUDE"][0], AR.sig_amplitude)
        self.assertFalse(RL.LIDERES["CAP_MERCADO_V2_N5K2"][1])
        self.assertTrue(RL.LIDERES["BOUNCE_ALVO"][1])


if __name__ == "__main__":
    unittest.main()
