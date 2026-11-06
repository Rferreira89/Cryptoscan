"""Afinacao H14: o short em preco real com os niveis do espelho perde -1R no
stop, ganha menos do que o espelho no objetivo (fator m_stop/m_saida), o juro
desconta, o diario rapido e igual ao B.daily do prefixo (sem look-ahead) e a
operacao real nunca usa velas antes da entrada."""
import random
import unittest

from engine import backtest as B, short as SH
from tools import afinacao_h14_espelho as M

H4, DAY = M.H4, M.DAY
T0 = 1_600_000_000 - 1_600_000_000 % DAY


def serie(n=400, seed=3):
    rng = random.Random(seed)
    p, out = 100.0, []
    for i in range(n):
        o = p
        c = o * (1 + rng.uniform(-0.03, 0.03))
        h, l = max(o, c) * (1 + rng.uniform(0, 0.02)), min(o, c) * (1 - rng.uniform(0, 0.02))
        out.append({"t": T0 + i * H4, "o": o, "h": h, "l": l, "c": c, "v": 1.0, "tb": 0.5})
        p = c
    return out


def plano_espelho(m4, stop_f, tp_f):
    e = m4[-1]["c"]
    return {"stop": e * stop_f, "tp": [e * tp_f], "partials": [100], "breakeven": True,
            "hold_s": 30 * DAY}


class T(unittest.TestCase):
    def test_diario_rapido_igual_ao_prefixo(self):
        s = serie(300)
        M.registar_diario(s)
        for k in (40, 41, 100, 157, 299):
            self.assertEqual(M.daily_rapido(s[:k]), B.daily(s[:k]))

    def test_stop_menos_1R_e_ganho_encolhido(self):
        # espelho: entrada 1/100, stop 10% abaixo, objetivo 20% acima (2R no espelho)
        real = [{"t": T0, "o": 100, "h": 100, "l": 100, "c": 100, "v": 1.0}]
        real += [{"t": T0 + H4, "o": 100, "h": 100.1, "l": 100 / 1.2 * 0.999, "c": 84, "v": 1.0}]
        m4 = SH.mirror(real)
        sig = {"stop": 0.01 * 0.9, "tp": [0.01 * 1.2], "partials": [100]}
        pm, _ = M._sim(sig, m4[0]["o"], T0, m4, 1, 30 * DAY, "LONG")
        pr, _ = M._sim(dict(sig, stop=1 / sig["stop"], tp=[1 / x for x in sig["tp"]]),
                       real[0]["o"], T0, real, 1, 30 * DAY, "SHORT")
        self.assertGreater(pm["r"], 1.8)
        self.assertLess(pr["r"], pm["r"] - 0.3)          # 2R no espelho ~ 2*0.9/1.2 = 1.5R real antes de custos
        self.assertAlmostEqual(pr["r"], 1.37, delta=0.05)   # com comissao e slippage
        real2 = real[:1] + [{"t": T0 + H4, "o": 100, "h": 112, "l": 99.9, "c": 111, "v": 1.0}]
        pr2, _ = M._sim(dict(sig, stop=1 / sig["stop"], tp=[1 / x for x in sig["tp"]]),
                        real2[0]["o"], T0, real2, 1, 30 * DAY, "SHORT")
        self.assertEqual(pr2["exit_reason"], "STOP")
        self.assertAlmostEqual(pr2["r"], -1.0, delta=0.05)

    def test_juro_desconta(self):
        pos = {"opened_at": 0, "closed_at": 365 * DAY, "entry": 100, "risk_unit": 10}
        self.assertAlmostEqual(M.juro_r(pos), 2.0)

    def test_sem_look_ahead(self):
        real = serie(400)
        m4 = SH.mirror(real)
        visto = []

        def fn(x):
            visto.append(len(x))
            return plano_espelho(x, 0.95, 1.10) if len(x) % 37 == 0 else None
        trs = M.pares_trades("X", real, m4, 0, "T", fn)
        self.assertTrue(trs)
        for t in trs:
            i = next(k for k, x in enumerate(real) if x["t"] == t["t"])
            self.assertEqual(i % 37, 0)                 # entra na vela a seguir ao sinal (i-1 fechada)
            self.assertGreater(t["geo_real"]["stop"], 0)  # stop acima no short real
            self.assertLess(t["geo_real"]["tp"][0], 0)
            self.assertLessEqual(t["r_real_juro"], t["r_real"])
        # o sinal so ve velas fechadas ate i (nunca a vela de entrada)
        self.assertTrue(all(n < len(m4) for n in visto))


if __name__ == "__main__":
    unittest.main()
