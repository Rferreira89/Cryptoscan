"""(2026-11-11) Universo da Bybit UE: descoberta externa separada da execucao; a arena combate nos pares que a API da
Bybit UE lista, os shorts so nas moedas com margem e pagam o juro do emprestimo. Dados sinteticos (nada da rede)."""
import inspect
import unittest

from engine import sources
from tools import arena_ringue as AR

NOW = 1_800_000_000


def estado(idade=60, margem=("BTC", "ETH")):
    return {"bybit_tickers": {"t": NOW - idade, "m": {"BTC": [100.0, 99.99, 100.01, 5e6], "ETH": [10.0, 9.99, 10.01, 1e6],
                                                       "TINY": [1.0, 0.98, 1.02, 900.0]}},
            "margem_bybit": {"t": NOW - idade, "moedas": list(margem)}}


class Descoberta(unittest.TestCase):
    def test_bybit_internacional_nao_e_fonte(self):
        self.assertNotIn("bybit", [s.name for s in sources.ALL])

    def test_execucao_e_a_api_da_bybit_ue(self):
        from engine import account, executor
        self.assertEqual(account.BASE, "https://api.bybit.eu")
        self.assertIn("api.bybit.eu", inspect.getsource(executor))


class ArenaUniverso(unittest.TestCase):
    def test_usa_a_lista_direta_e_corta_pares_velhos_da_coingecko(self):
        cg = {"BTC": {"pair": "BTC/USDC", "last": 100.0, "spread_pct": 0.01, "volume_usd": 1e6, "stale": False},
              "OLD": {"pair": "OLD/USDC", "last": 1.0, "spread_pct": 0.1, "volume_usd": 1e6, "stale": False}}
        ven, fonte, mg = AR.universo_bybit_ue(estado(), NOW, fetch=lambda q: cg)
        self.assertEqual(fonte, "bybit_ue_direto")
        self.assertNotIn("OLD", ven)
        self.assertIn("TINY", ven)
        self.assertEqual(mg, {"BTC", "ETH"})

    def test_sem_lista_direta_recorre_a_coingecko_e_margem_desconhecida(self):
        cg = {"BTC": {"pair": "BTC/USDC", "last": 100.0, "spread_pct": 0.01, "volume_usd": 1e6, "stale": False}}
        ven, fonte, mg = AR.universo_bybit_ue(estado(idade=10 * 86400), NOW, fetch=lambda q: cg)
        self.assertEqual(fonte, "coingecko")
        self.assertIsNone(mg)

    def test_sem_nenhuma_lista_falha(self):
        def falha(q):
            raise sources.SourceError("x")
        with self.assertRaises(RuntimeError):
            AR.universo_bybit_ue({}, NOW, fetch=falha)


class ArenaShorts(unittest.TestCase):
    def test_juro_do_short_em_r(self):
        t = {"t": 0, "t_fim": 3 * 86400, "geo": {"stop": -0.05}}
        self.assertAlmostEqual(AR.juros_short_r(t, 0.03), 0.0003 * 3 / 0.05)
        self.assertEqual(AR.juros_short_r({"t": 0, "geo": {"stop": -0.05}}, 0.03), 0.0)

    def test_shorts_so_nas_moedas_com_margem(self):
        src = inspect.getsource(AR.run)
        self.assertIn("margem is None or a in margem", src)        # a guarda envolve o ciclo dos SHORT_SIGS
        self.assertLess(src.index("margem is None or a in margem"), src.index("SHORT_SIGS.items()"))
        self.assertIn("juros_short_r", src)


class ElegibilidadeShort(unittest.TestCase):
    INST = {"list": [
        {"baseCoin": "AVAX", "quoteCoin": "USDC", "status": "Trading", "marginTrading": "utaOnly",
         "lotSizeFilter": {"minOrderQty": "0.01", "minOrderAmt": "5", "maxOrderQty": "1000"}},
        {"baseCoin": "ICP", "quoteCoin": "USDC", "status": "Trading", "marginTrading": "none", "lotSizeFilter": {}},
        {"baseCoin": "OLD", "quoteCoin": "USDC", "status": "Closed", "marginTrading": "both", "lotSizeFilter": {}},
        {"baseCoin": "SEI", "quoteCoin": "USDC", "status": "Trading", "marginTrading": "both", "lotSizeFilter": {}},
        {"baseCoin": "AVAX", "quoteCoin": "EUR", "status": "Trading", "marginTrading": "both", "lotSizeFilter": {}}]}

    def test_sem_colateral_nao_inventa_taxa_nem_quantidade(self):
        from engine import account
        m = account.interpretar_margem(self.INST, None)
        self.assertEqual(set(m), {"AVAX", "ICP", "OLD", "SEI"})      # so pares USDC
        self.assertTrue(m["AVAX"]["short_possivel"])
        self.assertFalse(m["AVAX"]["confirmado"])
        self.assertIsNone(m["AVAX"]["taxa_dia_pct"])
        self.assertIsNone(m["AVAX"]["disponivel_para_emprestar"])
        self.assertFalse(m["ICP"]["short_possivel"])                 # sem margem spot (a recusa de 22/10)
        self.assertFalse(m["OLD"]["short_possivel"])                 # instrumento fechado / retirado
        self.assertEqual(m["AVAX"]["min_ordem_valor"], 5.0)

    def test_com_colateral_confirma_emprestimo_e_taxa(self):
        from engine import account
        col = {"list": [{"currency": "AVAX", "borrowable": True, "availableToBorrow": "120", "maxBorrowingAmount": "500",
                         "hourlyBorrowRate": "0.0000125"},
                        {"currency": "SEI", "borrowable": False, "availableToBorrow": "0", "hourlyBorrowRate": "0.00001"}]}
        m = account.interpretar_margem(self.INST, col)
        self.assertTrue(m["AVAX"]["confirmado"])
        self.assertAlmostEqual(m["AVAX"]["taxa_dia_pct"], 0.03)
        self.assertFalse(m["SEI"]["short_possivel"])                 # margem no catalogo, mas nao emprestavel
        self.assertEqual(m["SEI"]["disponivel_para_emprestar"], 0.0)

    def test_so_get_e_fora_da_execucao(self):
        from engine import account, executor, scanner
        src = inspect.getsource(account.margem_detalhe)
        self.assertNotIn("POST", src)
        self.assertNotIn("margem_detalhe", inspect.getsource(account.snapshot))
        self.assertNotIn("margem_detalhe", inspect.getsource(executor))
        self.assertNotIn("margem_detalhe", inspect.getsource(scanner))


class Retiradas(unittest.TestCase):
    def test_moeda_que_perde_a_margem_sai_dos_shorts(self):
        st = estado(margem=("BTC",))
        cg = {"ETH": {"pair": "ETH/USDC", "last": 10.0, "spread_pct": 0.01, "volume_usd": 1e6, "stale": False}}
        ven, fonte, mg = AR.universo_bybit_ue(st, NOW, fetch=lambda q: cg)
        self.assertIn("ETH", ven)                                     # continua negociavel a vista
        self.assertNotIn("ETH", mg)                                   # mas ja nao se vende a descoberto

    def test_lista_de_margem_velha_nao_vale(self):
        st = estado()
        st["margem_bybit"]["t"] = NOW - 8 * 86400
        _, _, mg = AR.universo_bybit_ue(st, NOW, fetch=lambda q: {})
        self.assertIsNone(mg)

    def test_valores_estranhos_nos_tickers_nao_rebentam(self):
        st = estado()
        st["bybit_tickers"]["m"]["BAD"] = [None, None, None, 0.0]
        ven, _, _ = AR.universo_bybit_ue(st, NOW, fetch=lambda q: {})
        self.assertIn("BAD", ven)                                     # entra, mas o filtro de liquidez exclui
        ok, _ = AR.liquid({"BAD": ven["BAD"]}, {"max_venue_spread_pct": 0.3, "min_venue_volume_usd": 25000})
        self.assertNotIn("BAD", ok)
