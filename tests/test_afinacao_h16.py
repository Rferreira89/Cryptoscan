"""Afinacao H16: a reversao do movimento da sessao so usa velas fechadas, so
dispara na vela de 4H que fecha a sessao (08:00 UTC para a asiatica, 16:00 para
a europeia), exige a fase lateral do BTC, mede o movimento do fecho da sessao
contra a abertura da sessao e devolve um plano valido."""
import unittest
from unittest import mock

from tools import arena_ringue as AR
from tools.afinacao_h16_sessao_asia import GRID, sessao_sig

H4, DAY = AR.H4, AR.DAY
ASIA = 8 * 3600
# T0 e meia-noite UTC: c4[0] abre as 00:00, c4[1] as 04:00, c4[2] as 08:00...
T0 = 1_600_000_000 - 1_600_000_000 % DAY


def velas(n=400, px=100.0):
    return [{"t": T0 + k * H4, "o": px, "h": px * 1.01, "l": px * 0.99, "c": px,
             "v": 1.0, "tb": 0.5} for k in range(n)]


def queda_asia(c4, idx, abertura=100.0, fecho=96.0):
    """Faz a sessao asiatica que fecha na vela idx (abertura 00:00 = idx-1)
    cair de `abertura` para `fecho` (queda de 4%)."""
    c4[idx - 1] = dict(c4[idx - 1], o=abertura, h=abertura * 1.002, l=fecho, c=(abertura + fecho) / 2)
    c4[idx] = dict(c4[idx], o=(abertura + fecho) / 2, h=abertura * 1.001, l=fecho * 0.999, c=fecho)
    return c4


class H16(unittest.TestCase):
    def setUp(self):
        AR.CTX.update(daily={}, asset="TESTE")
        p = mock.patch.object(AR, "_fase_btc", return_value="lateral")
        self.fase = p.start()
        self.addCleanup(p.stop)

    def _idx_fecho_asia(self, c4):
        """Primeiro indice bem dentro da serie cuja vela fecha as 08:00 UTC."""
        for i in range(300, len(c4)):
            if (c4[i]["t"] + H4) % DAY == ASIA:
                return i
        raise AssertionError

    def test_so_na_vela_que_fecha_a_sessao(self):
        c4 = velas()
        i = self._idx_fecho_asia(c4)
        queda_asia(c4, i)
        fn = sessao_sig("L", -0.03, ASIA)
        self.assertIsNotNone(fn(c4[:i + 1]))                 # fecha as 08:00: avalia
        self.assertIsNone(fn(c4[:i]))                        # vela anterior (04:00): nao
        self.assertIsNone(fn(c4[:i + 2]))                    # 12:00: nao

    def test_so_velas_fechadas(self):
        """A funcao so olha para c4[:-1]+c4[-1] ja fechadas: mexer na vela
        a seguir ao sinal (ainda nao fechada no momento do sinal) nao muda nada."""
        c4 = velas()
        i = self._idx_fecho_asia(c4)
        queda_asia(c4, i)
        fn = sessao_sig("L", -0.03, ASIA)
        s1 = fn(c4[:i + 1])
        c4[i + 1] = dict(c4[i + 1], o=1.0, h=999.0, l=0.5, c=500.0)
        self.assertEqual(fn(c4[:i + 1]), s1)

    def test_exige_fase_lateral(self):
        c4 = velas()
        i = self._idx_fecho_asia(c4)
        queda_asia(c4, i)
        fn = sessao_sig("L", -0.03, ASIA)
        for fase in ("subida", "queda"):
            self.fase.return_value = fase
            self.assertIsNone(fn(c4[:i + 1]))
        self.fase.return_value = "lateral"
        self.assertIsNotNone(fn(c4[:i + 1]))

    def test_limiar_do_movimento(self):
        c4 = velas()
        i = self._idx_fecho_asia(c4)
        queda_asia(c4, i, abertura=100.0, fecho=98.0)        # queda de 2% apenas
        self.assertIsNone(sessao_sig("L", -0.03, ASIA)(c4[:i + 1]))
        queda_asia(c4, i, abertura=100.0, fecho=96.0)        # queda de 4%
        self.assertIsNotNone(sessao_sig("L", -0.03, ASIA)(c4[:i + 1]))

    def test_plano_valido(self):
        c4 = velas()
        i = self._idx_fecho_asia(c4)
        queda_asia(c4, i, abertura=100.0, fecho=96.0)
        s = sessao_sig("L", -0.03, ASIA)(c4[:i + 1])
        self.assertAlmostEqual(s["tp"][0], 100.0)            # objetivo = abertura da sessao
        self.assertEqual(s["partials"], [100])
        self.assertTrue(s["breakeven"])
        self.assertEqual(s["hold_s"], 16 * 3600)
        self.assertLess(s["stop"], 96.0)                     # stop abaixo do minimo da sessao
        self.assertTrue(s["stop"] < s["tp"][0])

    def test_controlo_europeu_fecha_as_16h(self):
        c4 = velas()
        i = next(k for k in range(300, len(c4)) if (c4[k]["t"] + H4) % DAY == 16 * 3600)
        queda_asia(c4, i)
        fn = sessao_sig("L", -0.03, 16 * 3600)
        self.assertIsNotNone(fn(c4[:i + 1]))
        self.assertNotIn("asiática", fn(c4[:i + 1])["gatilho"])

    def test_grelha(self):
        self.assertEqual(len(GRID), 6)
        self.assertEqual(GRID["A1"], ("L", -0.03, ASIA))
        self.assertEqual(GRID["A5"][2], 16 * 3600)           # controlos na sessao europeia


if __name__ == "__main__":
    unittest.main()
