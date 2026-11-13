"""(13/11, B3) Arquivo diario de derivados: uma linha por moeda/fonte/dia, so acrescenta, nunca apaga."""
import os
import tempfile
import unittest

from tools import derivados_diario as D


class Diario(unittest.TestCase):
    def test_acrescenta_sem_duplicar_nem_apagar(self):
        scan = {"generated_at": 86400 * 20000 + 60, "universe": [
            {"asset": "BTC", "price": 1.0, "derivatives": {"venue": "binance", "funding_rate": 0.0001, "ls_ratio": 2.0,
                                                          "oi_chg_24h_pct": 3.0, "liquidations": {"complete": False}}}]}
        okx = {"funding": {"BTC-USDT-SWAP": [[86400 * 20000 + 100, -0.0002]]}}
        d = tempfile.mkdtemp()
        ls = D.linhas_scan(scan) + D.linhas_okx(okx)
        self.assertEqual(D.acrescentar(d, ls), 2)
        self.assertEqual(D.acrescentar(d, ls), 0)                    # mesma leitura no mesmo dia: nada novo
        scan2 = dict(scan, generated_at=86400 * 20001 + 60)
        self.assertEqual(D.acrescentar(d, D.linhas_scan(scan2)), 1)  # dia seguinte: acrescenta
        f = os.path.join(d, os.listdir(d)[0])
        txt = open(f).read().splitlines()
        self.assertEqual(len(txt), 4)                                # cabecalho + 3, nada apagado
        self.assertIn("0.01", txt[1])                                # funding 0,01%/8h


if __name__ == "__main__":
    unittest.main()
