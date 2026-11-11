"""(2026-11-11) Triagem expandida por corretora e acompanhamento prospetivo em sombra: custos, lados, acontecimentos,
sem dados antes do pre-registo, sem sobreposicao, acaso agrupado. Dados sinteticos (nada vem da rede)."""
import random
import unittest

from tools import sombra_prospetiva as SP
from tools import triagem_anomalias as T
from tools import triagem_expandida as X

DAY = 86400


def painel(n_moedas=20, n_dias=160, d0=20000, efeito=0.0, semente=1, funding=0.0):
    """Painel diario sintetico. 'efeito': retorno diario extra das moedas pares (para plantar um sinal)."""
    rnd = random.Random(semente)
    p = {}
    for i in range(n_moedas):
        a = "BTC" if i == 0 else f"M{i}"
        c, dd = 100.0, {}
        for k in range(n_dias):
            o = c
            r = rnd.gauss(0, 0.02) + (efeito if i % 2 == 0 and i else 0.0)
            c = o * (1 + r)
            dd[d0 + k] = {"o": o, "c": c, "h": max(o, c) * 1.01, "l": min(o, c) * 0.99, "v": 1e6, "tb": 5e5,
                          "n": 6, "tbf": 0.5, "fund": funding}
        p[a] = dd
    return p


def subir(p):
    """BTC a subir devagar e de forma coerente (abertura = fecho anterior), acima da SMA50."""
    for d in sorted(p["BTC"]):
        c = 100 * 1.001 ** (d - 20000)
        p["BTC"][d].update(o=c / 1.001, c=c, h=c * 1.001, l=c / 1.002)


class Custos(unittest.TestCase):
    def test_long_paga_funding_short_recebe(self):
        p = painel(funding=0.001)
        fw = {a: 0.0 for a in p}
        liq_l, br_l, _ = SP.liquido(p, ["M1"], fw, 20050, 3, "LONG")
        liq_s, br_s, _ = SP.liquido(p, ["M1"], fw, 20050, 3, "SHORT")
        self.assertAlmostEqual(liq_l, 0.0 - 0.003 - X.CUSTOS["okx_perp"])
        self.assertAlmostEqual(liq_s, 0.0 + 0.003 - X.CUSTOS["okx_perp"])

    def test_custos_por_corretora(self):
        self.assertEqual(X.CUSTOS["bybit_spot"], 0.007)
        self.assertEqual(X.CUSTOS["okx_perp"], 0.002)


class Seccional(unittest.TestCase):
    def test_acontecimento_aceita_uma_moeda_e_quintil_exige_minimo(self):
        p = painel()
        so_uma = lambda p_, a, d: 1.0 if a == "M3" else None
        obs_ev = X.seccional(p, so_uma, "LONG*", 1, (20000 + 200) * DAY)
        obs_q = X.seccional(p, so_uma, "LONG", 1, (20000 + 200) * DAY)
        self.assertTrue(obs_ev)
        self.assertEqual(obs_q, [])

    def test_short_inverte_o_sinal(self):
        p = painel()
        todos = lambda p_, a, d: 1.0
        lo = X.seccional(p, todos, "LONG", 3, (20000 + 200) * DAY)
        sh = X.seccional(p, todos, "SHORT", 3, (20000 + 200) * DAY)
        for a, b in zip(lo, sh):
            self.assertAlmostEqual(a[0], -b[0])

    def test_corte_impede_retornos_depois_da_reserva(self):
        p = painel()
        corte = (20000 + 80) * DAY
        todos = lambda p_, a, d: 1.0
        n_curto = len(X.seccional(p, todos, "LONG", 3, corte))
        n_longo = len(X.seccional(p, todos, "LONG", 3, (20000 + 200) * DAY))
        self.assertLess(n_curto, n_longo)


class Sombra(unittest.TestCase):
    def test_nada_antes_do_pre_registo_e_sem_sobreposicao(self):
        p = painel(n_dias=160)
        r = SP.acompanhar(p, "QUEBRA_MINIMO_SHORT", 20120, (20000 + 160) * DAY, rng=random.Random(1), reps=50)
        dias = [SP._dia(e["dia"]) for e in r["eventos"]]
        self.assertTrue(all(d >= 20120 for d in dias))
        self.assertTrue(all(b - a >= 3 for a, b in zip(dias, dias[1:])))

    def test_mesma_funcao_de_sinal_que_a_triagem(self):
        btc = X.estado_btc(painel())
        nomes = {n for _, n, _, _ in X._sinais(btc)}
        for cfg in SP.HIPOTESES.values():
            self.assertIn(cfg["sinal"], nomes)

    def test_efeito_plantado_e_detetado_e_acaso_agrupado(self):
        # as moedas pares sobem 1%/dia: o momento de 7 dias apanha-as; o acaso (grupos ao calhas) nao
        p = painel(n_moedas=30, n_dias=260, efeito=0.01, semente=3)
        subir(p)                                          # BTC sempre a subir: acima da SMA50
        r = SP.acompanhar(p, "MOMENTO_RISCO_ON", 20060, (20000 + 260) * DAY, rng=random.Random(2), reps=200)
        self.assertGreater(r["acontecimentos"], 30)
        self.assertGreater(r["media_liquida_okx"], 0.01)
        self.assertLess(r["p_acaso_agrupado"], 0.05)

    def test_sem_efeito_nao_passa_o_acaso(self):
        p = painel(n_moedas=30, n_dias=260, efeito=0.0, semente=4)
        subir(p)
        r = SP.acompanhar(p, "MOMENTO_RISCO_ON", 20060, (20000 + 260) * DAY, rng=random.Random(2), reps=200)
        self.assertGreater(r["p_acaso_agrupado"], 0.05)

    def test_sem_pre_registo_nao_acompanha(self):
        from unittest import mock
        barras = {"BTC": [{"t": 20000 * DAY + i * 14400, "o": 1, "h": 1, "l": 1, "c": 1, "v": 1, "tb": 0.5} for i in range(400)]}
        with mock.patch.object(SP.B, "load_all", return_value=(barras, None)), \
                mock.patch.object(SP.T, "carregar_funding", return_value={}):
            r = SP.correr("nao-usada", linhas=[])
        self.assertTrue(all("sem pre-registo" in h["estado"] for h in r["hipoteses"]))

    def test_sem_corretoras(self):
        import inspect
        for mod in (SP, X):
            src = inspect.getsource(mod)
            for proibido in ("okx_exec", "privado(", "/trade/", "/v5/order", "urlopen"):
                self.assertNotIn(proibido, src)


if __name__ == "__main__":
    unittest.main()
