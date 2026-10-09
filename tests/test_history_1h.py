import csv
import gzip
import os
import tempfile
import unittest

from engine import backtest as B


class History1H(unittest.TestCase):
    def test_carrega_velas_de_1h(self):
        with tempfile.TemporaryDirectory() as d:
            with gzip.open(os.path.join(d, "AAA.csv.gz"), "wt", newline="") as f:
                w = csv.writer(f)
                t0 = 1_700_000_400 // 3600 * 3600
                for i in range(3000):
                    p = 100 + (i % 50) * 0.1
                    w.writerow([t0 + i * 3600, p, p + 0.5, p - 0.5, p + 0.1, 10, 5])
            data, skipped = B.load_all(d, min_bars=2000, tf=3600)
            self.assertEqual(skipped, {})
            self.assertEqual(len(data["AAA"]), 3000)
            # com a duracao de 4H o mesmo ficheiro nao e aceite tal e qual
            data4, _ = B.load_all(d, min_bars=2000)
            self.assertNotEqual(len(data4.get("AAA", [])), 3000)


if __name__ == "__main__":
    unittest.main()
