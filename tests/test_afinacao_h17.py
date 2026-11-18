"""Afinacao H17: a dispersao do universo so usa velas fechadas, o percentil so
compara com valores anteriores (sem look-ahead) e o filtro deixa passar ou corta
o sinal-base conforme o percentil."""
import random
import unittest
from unittest import mock

from engine import promo
from tools import afinacao_h17_dispersao as H
from tools import arena_ringue as AR
from tools.afinacao_h09_racio import racio_var

H4 = AR.H4
T0 = 1_600_000_000 - 1_600_000_000 % AR.DAY


def serie(n, passo, px=100.0):
    out = []
    for k in range(n):
        c = px * (1 + passo) ** k
        out.append({"t": T0 + k * H4, "o": c, "h": c * 1.01, "l": c * .99, "c": c, "v": 1.0, "tb": .5})
    return out


def universo(n=700, moedas=24):
    return {f"M{i}": serie(n, 0.0002 * (i - moedas / 2)) for i in range(moedas)}


class H17(unittest.TestCase):
    def setUp(self):
        AR._DISP.update(chave=None, t=[], d=[])
        antes = {k: AR.CTX.get(k) for k in ("bars", "btc", "_btcc")}
        self.addCleanup(AR.CTX.update, antes)

    def test_iqr(self):
        self.assertAlmostEqual(AR._iqr([0, 1, 2, 3, 4]), 2.0)

    def test_exige_moedas_minimas(self):
        self.assertEqual(AR.serie_dispersao(universo(moedas=AR.DISP_MOEDAS - 1))[0], [])

    def test_btc_fica_fora_da_medida(self):
        b = universo()
        self.assertEqual(AR.serie_dispersao(dict(b, BTC=serie(700, 0.05))), AR.serie_dispersao(b))

    def test_sem_look_ahead(self):
        b = universo()
        AR.CTX["bars"] = b
        t = b["M0"][600]["t"] + H4
        antes = AR.percentil_dispersao(t)
        self.assertIsNotNone(antes)
        AR._DISP.update(chave=None)
        AR.CTX["bars"] = {a: c[:601] + [dict(x, c=x["c"] * (3 if i % 2 else .2)) for x in c[601:]]
                          for i, (a, c) in enumerate(b.items())}
        self.assertEqual(AR.percentil_dispersao(t), antes)

    def test_sem_historico_nao_ha_percentil(self):
        b = universo()
        AR.CTX["bars"] = b
        self.assertIsNone(AR.percentil_dispersao(b["M0"][AR.DISP_RET + 5]["t"] + H4))

    def test_filtro_corta_e_deixa_passar(self):
        c4 = serie(10, 0)
        base = lambda _c: {"stop": 90.0, "tp": [110.0], "gatilho": "x"}
        with mock.patch.object(AR, "percentil_dispersao", return_value=60.0):
            self.assertIsNotNone(AR.com_dispersao(base, 50)(c4))
            self.assertIsNone(AR.com_dispersao(base, 70)(c4))
            self.assertIsNone(AR.com_dispersao(base, None, 50)(c4))
        with mock.patch.object(AR, "percentil_dispersao", return_value=None):
            self.assertIsNone(AR.com_dispersao(base, 50)(c4))

    def _caminhos(self, seed=3, n=900):
        """Moeda parada com ruido e BTC com arrancos: o racio cai sem a moeda entrar em sobrevenda."""
        r = random.Random(seed)
        def passeio(arranco):
            out, c = [], 100.0
            for k in range(n):
                extra = .03 if arranco and 150 <= k % 200 < 165 else 0
                o, c = c, c * (1 + r.gauss(0, .008) + extra)
                out.append({"t": T0 + k * H4, "o": o, "h": max(o, c) * 1.004, "l": min(o, c) * .996,
                            "c": c, "v": 1.0, "tb": .5})
            return out
        return passeio(False), passeio(True)

    def test_sinal_igual_ao_da_h9_e_sem_futuro(self):
        c4, btc = self._caminhos()
        AR.CTX.update(btc=btc, _btcc=None)
        h9 = racio_var(120, 2.5, 2.0, 3, 35)
        n = 0
        for i in range(130, len(c4)):
            a, b = AR.sig_racio(c4[:i + 1]), h9(c4[:i + 1])
            self.assertEqual(a and {k: a[k] for k in ("stop", "tp", "hold_s")},
                             b and {k: b[k] for k in ("stop", "tp", "hold_s")})
            n += bool(a)
        self.assertGreater(n, 0)
        i = next(i for i in range(130, len(c4)) if AR.sig_racio(c4[:i + 1]))
        fut = c4[:i + 1] + [dict(x, c=x["c"] * 5, h=x["h"] * 5) for x in c4[i + 1:]]
        self.assertEqual(AR.sig_racio(fut[:i + 1]), AR.sig_racio(c4[:i + 1]))

    def test_lutador_no_ringue_e_fora_do_dinheiro_real(self):
        self.assertIs(AR.NEW_SIGS["RACIO_DISP"], AR.sig_racio_disp)
        self.assertIn("RACIO_DISP", AR.SINAIS)
        self.assertNotIn("RACIO_DISP", promo.REAL_OK)

    def test_grelha_tem_controlos_e_seis_configuracoes(self):
        self.assertEqual(len([k for k in H.GRID if k.startswith("D")]), 6)
        self.assertNotIn("D3", H.CANDIDATAS)
        self.assertNotIn("D6", H.CANDIDATAS)


if __name__ == "__main__":
    unittest.main()
