"""(29/10) Papel da compra no panico (H23 L10): sinal, ordem limite, objetivo, stop e ordem perdida."""
import unittest

from engine import papel_panico as P

H4 = 14400


def velas(n=60, base=100.0, queda_final=True):
    out = []
    for i in range(n):
        c = base
        if queda_final and i >= n - 18:
            c = base * (1 - 0.12 * (i - (n - 19)) / 18)        # cai 12% nas ultimas 18 velas
        out.append({"t": i * H4, "o": c, "h": c * 1.005, "l": c * 0.995, "c": c})
    return out


def funding(t_fim, extremo=True):
    fs = [((t_fim - (300 - k) * 8 * 3600), 0.0001) for k in range(300)]
    if extremo:
        fs[-1] = (fs[-1][0], -0.001)
    return fs


class PapelPanico(unittest.TestCase):
    def test_sinal_so_com_panico_e_financiamento_extremo(self):
        c4 = velas()
        self.assertIsNotNone(P.sinal(c4, funding(c4[-1]["t"])))
        self.assertIsNone(P.sinal(c4, funding(c4[-1]["t"], extremo=False)))
        self.assertIsNone(P.sinal(velas(queda_final=False), funding(c4[-1]["t"])))

    def test_executa_e_fecha_no_objetivo(self):
        c4 = velas()
        st, eu = {}, {"moedas": {"SEI": {"funding": funding(c4[-1]["t"])}}}
        P.update(st, {"SEI": c4}, eu, 0)
        pend = st["papel_panico"]["pend"]["SEI"]
        lim = pend["lim"]
        c4.append({"t": c4[-1]["t"] + H4, "o": lim * 1.002, "h": lim * 1.003, "l": lim * 0.999, "c": lim})
        P.update(st, {"SEI": c4}, eu, 0)
        op = st["papel_panico"]["abertas"]["SEI"]
        c4.append({"t": c4[-1]["t"] + H4, "o": lim, "h": op["alvo"] * 1.01, "l": lim * 0.999, "c": op["alvo"]})
        r = P.update(st, {"SEI": c4}, eu, 0)
        self.assertEqual(r["n"], 1)
        self.assertEqual(st["papel_panico"]["fechadas"][0]["motivo"], "objetivo")
        self.assertAlmostEqual(st["papel_panico"]["fechadas"][0]["r"], 2.0, delta=0.1)

    def test_ordem_nao_executada_conta_e_nao_repete_o_sinal(self):
        c4 = velas()
        st, eu = {}, {"moedas": {"SEI": {"funding": funding(c4[-1]["t"])}}}
        P.update(st, {"SEI": c4}, eu, 0)
        for _ in range(2):
            c4.append({"t": c4[-1]["t"] + H4, "o": c4[-1]["c"] * 1.02, "h": c4[-1]["c"] * 1.03,
                       "l": c4[-1]["c"] * 1.015, "c": c4[-1]["c"] * 1.02})
        r = P.update(st, {"SEI": c4}, eu, 0)
        self.assertEqual(r["ordens_nao_executadas"], 1)
        self.assertEqual(r["abertas"], [])


if __name__ == "__main__":
    unittest.main()
