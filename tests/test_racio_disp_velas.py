"""(18/11) Historico longo de 4H para o filtro de dispersao (RACIO_DISP) no papel ao vivo, sem mudar o que a analise
recebe. Prova: com >= 600 velas continuas o filtro da percentil e o sinal sai; com 500 (o que o scanner tinha) nao."""
import math
import unittest
from unittest import mock

from engine import promo, scanner, sources
from tools import arena_ringue as AR

H4 = 14400
FIM = 1_800_000_000 // H4 * H4          # fecho alinhado


def velas(n, fim=FIM, base=100.0, deriva=0.0, ultimas=30, extra=0.0):
    """n velas fechadas ate 'fim'; deriva por vela e, nas ultimas 'ultimas', um passo extra (cria dispersao)."""
    out, p = [], base
    for k in range(n):
        t = fim - (n - k) * H4
        p *= math.exp(deriva + (extra if k >= n - ultimas else 0.0) + 0.002 * math.sin(k * 0.7 + base))
        out.append({"t": t, "o": p, "h": p * 1.01, "l": p * 0.99, "c": p, "v": 1000.0, "tb": 500.0})
    return out


def universo(n, moedas=25):
    """Moedas com dispersao baixa ao longo do historico e alta nas ultimas 30 velas."""
    bars = {"BTC": velas(n, base=50000.0)}
    for i in range(moedas):
        bars[f"C{i:02d}"] = velas(n, base=10.0 + i, extra=(i - moedas / 2) * 0.004)
    return bars


SERIE = velas(2000) + [{"t": FIM, "o": 1.0, "h": 1.0, "l": 1.0, "c": 1.0, "v": 1.0, "tb": 0.5}]   # ultima em formacao


class Fonte:
    """Fonte falsa: devolve as 'limit' velas mais recentes da mesma serie (a OKX mais recente primeiro)."""
    def __init__(self, name, n):
        self.name, self.n, self.pedidos = name, n, []

    def candles(self, base, tf, limit=500):
        self.pedidos.append(limit)
        cs = SERIE[-min(limit, self.n):]
        return list(reversed(cs)) if self.name == "okx" else list(cs)


class Filtro(unittest.TestCase):
    def tearDown(self):
        AR.CTX.pop("bars_disp", None)
        AR._DISP["chave"] = None

    def sinal(self, bars_vivo, longas=None):
        sempre = lambda c4: {"gatilho": "base", "t_sig": c4[-1]["t"] + H4}
        promo.set_context([], bars_vivo, longas)        # como o papel ao vivo
        AR._DISP["chave"] = None
        f = AR.com_dispersao(sempre, 50)
        return f(bars_vivo["C24"])

    def test_com_600_velas_ha_sinal(self):
        longas = universo(640)
        vivo = {a: c[-500:] for a, c in longas.items()}
        s = self.sinal(vivo, longas)
        self.assertIsNotNone(s)
        self.assertIn("dispersão entre moedas no percentil", s["gatilho"])

    def test_com_500_velas_nao_ha_sinal(self):
        vivo = {a: c[-500:] for a, c in universo(640).items()}
        self.assertIsNone(self.sinal(vivo))
        self.assertIsNone(self.sinal({a: c[-570:] for a, c in universo(640).items()}))   # 570: ainda curto
        self.assertIsNotNone(self.sinal({a: c[-571:] for a, c in universo(640).items()}, {a: c[-571:] for a, c in universo(640).items()}))

    def test_set_context_so_poe_as_longas_quando_existem(self):
        b = universo(300)
        promo.set_context([], b, {"BTC": b["BTC"]})
        self.assertIn("bars_disp", AR.CTX)
        promo.set_context([], b)
        self.assertNotIn("bars_disp", AR.CTX)
        self.assertEqual(len(AR.CTX["bars"]["BTC"]), 300)   # as funcoes de sinal continuam com as velas de sempre


class Velas(unittest.TestCase):
    def test_analise_recebe_as_mesmas_velas_de_antes(self):
        for nome, antigo in scanner.LIMITE_ANTIGO.items():
            if nome == "bybit":
                continue
            src = Fonte(nome, 2000)
            curtas, longas = scanner._velas(src, "XLM", "4h")
            self.assertEqual(src.pedidos, [scanner.VELAS_LONGAS_4H])
            antes = sorted(Fonte(nome, 2000).candles("XLM", "4h", limit=antigo), key=lambda c: c["t"])
            self.assertEqual(curtas, antes)
        src = Fonte("binance", 2000)
        c, l = scanner._velas(src, "XLM", "1d")
        self.assertIsNone(l)
        self.assertEqual(src.pedidos, [500])           # o diario nao muda

    def test_pedido_longo_falhado_volta_ao_de_sempre(self):
        class Falha(Fonte):
            def candles(self, base, tf, limit=500):
                if limit == scanner.VELAS_LONGAS_4H:
                    raise sources.SourceError("x")
                return super().candles(base, tf, limit)
        c, l = scanner._velas(Falha("binance", 2000), "XLM", "4h")
        self.assertIsNone(l)
        self.assertEqual(len(c), 500)

    def test_longas_fechadas_sem_duplicados_e_continuas(self):
        cs = velas(640) + [dict(velas(640)[-1])]                     # um duplicado
        cs.append({"t": FIM, "o": 1, "h": 1, "l": 1, "c": 1, "v": 1})   # em formacao
        v = scanner.velas_longas_validas(cs, FIM + 60)
        self.assertEqual(len(v), 640)
        self.assertTrue(all(b["t"] - a["t"] == H4 for a, b in zip(v, v[1:])))
        self.assertTrue(all(c["t"] + H4 <= FIM + 60 for c in v))
        buraco = velas(640)
        del buraco[300]
        self.assertIsNone(scanner.velas_longas_validas(buraco, FIM + 60))
        self.assertIsNone(scanner.velas_longas_validas(velas(599), FIM + 60))
        self.assertIsNone(scanner.velas_longas_validas(None, FIM))

    def test_okx_pagina_sem_duplicar(self):
        todas = list(reversed(velas(900)))                           # mais recente primeiro, como a OKX
        pedidos = []

        def get(url, prm):
            pedidos.append(dict(prm))
            lim, after = prm["limit"], prm.get("after")
            xs = [c for c in todas if after is None or c["t"] * 1000 < after]
            if after is not None and pedidos.count:
                xs = [todas[0]] + xs                                   # a OKX repete uma vela: tem de sair
            return {"code": "0", "data": [[str(c["t"] * 1000), c["o"], c["h"], c["l"], c["c"], c["v"]] for c in xs[:lim]]}
        with mock.patch.object(sources, "_get", get), mock.patch.object(sources.OKX, "PAUSA_S", 0):
            cs = sources.OKX().candles("XLM", "4h", limit=640)
            curto = sources.OKX().candles("XLM", "4h")
        ts = [c["t"] for c in cs]
        self.assertEqual(len(ts), 640)
        self.assertEqual(len(set(ts)), 640)
        self.assertEqual(ts, sorted(ts, reverse=True))
        self.assertLessEqual(len([p for p in pedidos if p.get("after")]), sources.OKX.PAGINAS_MAX - 1)
        self.assertEqual(len(curto), 300)                             # por omissao: um so pedido, como antes

    def test_okx_pagina_seguinte_falhada_devolve_a_primeira(self):
        n = {"k": 0}

        def get(url, prm):
            n["k"] += 1
            if prm.get("after"):
                raise sources.SourceError("limite")
            return {"code": "0", "data": [[str(c["t"] * 1000), c["o"], c["h"], c["l"], c["c"], c["v"]]
                                          for c in reversed(velas(300))]}
        with mock.patch.object(sources, "_get", get), mock.patch.object(sources.OKX, "PAUSA_S", 0):
            self.assertEqual(len(sources.OKX().candles("XLM", "4h", limit=640)), 300)


if __name__ == "__main__":
    unittest.main()
