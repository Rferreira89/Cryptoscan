"""(24/10) Precos reais da Bybit UE em vez da CoinGecko quando o servidor europeu os leu ha pouco."""
import unittest

from engine import scanner

NOW = 1_800_000_000


class PrecosBybit(unittest.TestCase):
    def test_substitui_preco_spread_e_volume(self):
        cg = {"SEI": {"pair": "SEI/USDC", "last": 0.0576, "volume_usd": 13599, "spread_pct": 0.07, "stale": True, "url": "u"}}
        by = {"t": NOW - 600, "m": {"SEI": [0.05485, 0.05484, 0.05486, 250000.0], "NOVA": [1.0, 0.999, 1.001, 50000.0]}}
        v = scanner.bybit_venue(cg, by, NOW)
        self.assertEqual(v["SEI"]["last"], 0.05485)
        self.assertFalse(v["SEI"]["stale"])
        self.assertAlmostEqual(v["SEI"]["spread_pct"], 0.0365, places=3)
        self.assertEqual(v["SEI"]["volume_usd"], 250000.0)
        self.assertEqual(v["SEI"]["url"], "u")
        self.assertEqual(v["NOVA"]["pair"], "NOVA/USDC")            # par que a CoinGecko nao tinha

    def test_dados_velhos_nao_substituem(self):
        cg = {"SEI": {"last": 0.0576}}
        self.assertIs(scanner.bybit_venue(cg, {"t": NOW - 3600, "m": {"SEI": [1, 1, 1, 1]}}, NOW), cg)
        self.assertIs(scanner.bybit_venue(cg, None, NOW), cg)


if __name__ == "__main__":
    unittest.main()


class UltimoForaDoLivro(unittest.TestCase):
    def test_usa_meio_do_livro(self):
        from engine.scanner import bybit_venue
        v = bybit_venue({}, {"t": 1000, "m": {"SEI": [0.05246, 0.05321, 0.05325, 42330.0]}}, 1100)
        self.assertAlmostEqual(v["SEI"]["last"], 0.05323)
        v = bybit_venue({}, {"t": 1000, "m": {"BTC": [80216.8, 80207.5, 80216.8, 1.0]}}, 1100)
        self.assertEqual(v["BTC"]["last"], 80216.8)


class Abertas(unittest.TestCase):
    def test_so_operacoes_abertas(self):
        from engine import execucao
        ex = {"ops": {"SEI-SHORT_TURTLE-1": {"asset": "SEI", "status": "aberta", "lado": "SHORT", "entrada": 0.05715,
                                              "qty": 102.5, "usdc": 5.85, "stop": 0.0656, "t": 5,
                                              "partes": [{"tp": 0.0457}]},
                      "X-1": {"asset": "X", "status": "recusada"}, "Y-1": {"asset": "Y", "status": "fechada",
                                                                           "entrada": 1, "qty": 1}}}
        a = execucao.abertas(ex)
        self.assertEqual([x["asset"] for x in a], ["SEI"])
        self.assertEqual((a[0]["lado"], a[0]["tp"], a[0]["qty"]), ("SHORT", 0.0457, 102.5))
        self.assertEqual(execucao.abertas(None), [])
