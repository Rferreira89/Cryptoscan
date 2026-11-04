"""Afinacao H13: as Tartarugas com o filtro do Sistema 1 so usam dias fechados,
sem filtro reproduzem o TURTLE do ringue, e o filtro so deixa passar o rompimento
quando o rompimento hipotetico anterior foi perdedor (stop de 2N antes da saida
pelo minimo de 10 dias)."""
import unittest
from unittest import mock

from engine import backtest as B
from tools import arena_ringue as AR
from tools import afinacao_h13_turtle_s1 as M

H4, DAY = AR.H4, AR.DAY
T0 = 1_600_000_000 - 1_600_000_000 % DAY


def dia(i, o, h, l, c):
    return {"t": T0 + i * DAY, "o": o, "h": h, "l": l, "c": c}


def plano(n=60):
    return [dia(i, 100, 101, 99, 100) for i in range(n)]


def velas(daily_ohlc, last=None):
    """Velas de 4H (6 por dia) a partir de (o, h, l, c) diarios; `last` = vela
    de 4H extra (do dia seguinte, por fechar) com o fecho dado."""
    out = []
    for i, (o, h, l, c) in enumerate(daily_ohlc):
        for k in range(6):
            t = T0 + i * DAY + k * H4
            oo = o if k == 0 else c
            out.append({"t": t, "o": oo, "h": h if k == 2 else max(oo, c),
                        "l": l if k == 3 else min(oo, c), "c": c, "v": 1.0, "tb": 0.5})
    if last is not None:
        i = len(daily_ohlc)
        out.append({"t": T0 + i * DAY, "o": 100, "h": max(100, last), "l": 99.5, "c": last,
                    "v": 1.0, "tb": 0.5})
    return out


class EstadoS1(unittest.TestCase):
    def test_perdedor(self):
        d = plano(30)
        d.append(dia(30, 100, 103, 100, 102))               # rompe o maximo de 20 dias (101)
        d.append(dia(31, 102, 102, 90, 91))                 # 2N (~4) contra: perdedor
        d += [dia(32 + k, 91, 92, 90.5, 91) for k in range(3)]
        self.assertEqual(M.estado_s1(d), ("perdedor", False))

    def test_ganhador(self):
        d = plano(30)
        d.append(dia(30, 100, 103, 100, 102))
        d += [dia(31 + k, 102 + k, 104 + k, 101 + k, 103 + k) for k in range(12)]
        d.append(dia(43, 112, 112, 100.5, 101))             # abaixo do minimo de 10 dias, sem tocar no stop
        self.assertEqual(M.estado_s1(d), ("ganhador", False))

    def test_aberto_antigo_bloqueia_recente_nao(self):
        d = plano(30)
        d.append(dia(30, 100, 103, 100, 102))
        d += [dia(31 + k, 102, 103, 101.5, 102) for k in range(2)]
        self.assertEqual(M.estado_s1(d), (None, False))    # aberto ha 3 dias: e o atual
        d += [dia(33 + k, 102, 103, 101.5, 102) for k in range(3)]
        self.assertEqual(M.estado_s1(d), (None, True))     # aberto ha mais: continuacao


class Sinal(unittest.TestCase):
    def setUp(self):
        AR.CTX["daily"] = {}
        AR.CTX["asset"] = "XYZ"

    def test_sem_filtro_igual_ao_turtle(self):
        base = [(100, 101, 99, 100)] * 40
        c4 = velas(base, last=105)
        self.assertEqual(M.turtle_s1(None)(c4), AR.sig_turtle(c4))
        self.assertIsNotNone(AR.sig_turtle(c4))

    def test_filtro(self):
        perd = [(100, 101, 99, 100)] * 30 + [(100, 103, 100, 102), (102, 102, 90, 91)] + \
               [(91, 100, 90.5, 99)] * 25
        c4 = velas(perd, last=105)
        s = M.turtle_s1("perdedor")(c4)
        self.assertIsNotNone(s)
        self.assertIn("perdedor", s["gatilho"])
        self.assertIsNone(M.turtle_s1("ganhador")(c4))
        sem = velas([(100, 101, 99, 100)] * 57, last=105)  # nenhum rompimento anterior
        self.assertIsNone(M.turtle_s1("perdedor")(sem))

    def test_fase(self):
        perd = [(100, 101, 99, 100)] * 30 + [(100, 103, 100, 102), (102, 102, 90, 91)] + \
               [(91, 100, 90.5, 99)] * 25
        c4 = velas(perd, last=105)
        with mock.patch.object(AR, "_fase_btc", return_value="subida"):
            self.assertIsNone(M.turtle_s1(*M.GRID["T2"])(c4))
            self.assertIsNotNone(M.turtle_s1(*M.GRID["T3"])(c4))

    def test_sem_look_ahead(self):
        """O sinal avaliado em c4[:i+1] nao muda com velas futuras, e a versao
        rapida dos dias da os mesmos dias fechados que AR._diario."""
        perd = [(100, 101, 99, 100)] * 30 + [(100, 103, 100, 102), (102, 102, 90, 91)] + \
               [(91, 100, 90.5, 99)] * 25
        c4 = velas(perd, last=105)
        fut = velas(perd + [(105, 106, 50, 51)] * 5)
        f = M.turtle_s1("perdedor")
        self.assertEqual(f(c4), f(fut[:len(c4) - 1] + [c4[-1]]))
        rap = M.dias_rapido({"XYZ": B.daily(fut)})
        for i in (100, 200, len(c4) - 1):
            self.assertEqual(rap(fut[:i + 1]), AR._diario(fut[:i + 1]))


if __name__ == "__main__":
    unittest.main()
