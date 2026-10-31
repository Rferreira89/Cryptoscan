"""(31/10) Arquivo permanente das liquidacoes em blocos de 5 minutos."""
import gzip
import json
import os
import tempfile
import unittest

from tools.eu import liquidacoes as L

DIA = 1793318400                       # 2026-10-30 00:00 UTC


class Arquivo(unittest.TestCase):
    def setUp(self):
        self.src, self.dst = tempfile.mkdtemp(), tempfile.mkdtemp()
        linhas = [{"t": DIA + 10, "s": "BTCUSDT", "lado": "SELL", "q": 0.5, "p": 70000},
                  {"t": DIA + 200, "s": "BTCUSDT", "lado": "SELL", "q": 0.1, "p": 70000},
                  {"t": DIA + 250, "s": "BTCUSDT", "lado": "BUY", "q": 1.0, "p": 70000},
                  {"t": DIA + 400, "s": "1000PEPEUSDT", "lado": "SELL", "q": 1000, "p": 0.01}]
        with open(os.path.join(self.src, "20261030.jsonl"), "w") as f:
            f.write("\n".join(json.dumps(x) for x in linhas) + "\nlixo\n")
        with open(os.path.join(self.src, "20261031.jsonl"), "w") as f:
            f.write(json.dumps({"t": DIA + 86400 + 5, "s": "ETHUSDT", "lado": "BUY", "q": 1, "p": 3000}) + "\n")

    def test_blocos_de_5_minutos(self):
        linhas = L.dia_5m(os.path.join(self.src, "20261030.jsonl"))
        self.assertEqual(linhas[0], f"{DIA},BTC,42000,70000,2,1")
        self.assertTrue(any(",PEPE," in x for x in linhas))
        self.assertEqual(len(linhas), 2)

    def test_so_dias_completos_e_uma_vez(self):
        agora = DIA + 86400 + 3600                     # 31/10 ainda a decorrer
        self.assertEqual(L.arquivar(self.dst, self.src, agora), ["20261030"])
        with gzip.open(os.path.join(self.dst, "20261030.csv.gz"), "rt") as g:
            txt = g.read()
        self.assertTrue(txt.startswith("t,moeda,longs_usd,shorts_usd,n_longs,n_shorts\n"))
        self.assertFalse(os.path.exists(os.path.join(self.dst, "20261031.csv.gz")))
        self.assertEqual(L.arquivar(self.dst, self.src, agora), [])          # nunca reescreve
        self.assertEqual(L.arquivar(self.dst, self.src, agora + 86400), ["20261031"])

    def test_guarda_45_dias_e_versao_nova(self):
        self.assertEqual(L.KEEP_DAYS, 45)
        self.assertEqual(L.VERSION, "7")


if __name__ == "__main__":
    unittest.main()
