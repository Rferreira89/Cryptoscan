import io
import unittest
import zipfile

from tools import fetch_delistadas as F


class Delistadas(unittest.TestCase):
    def test_candidatas_so_moedas_usdt_que_sairam(self):
        arquivo = {"BTCUSDT", "LUNAUSDT", "BTCUPUSDT", "USDCUSDT", "ETHBTC", "FTTUSDT"}
        estados = {"BTCUSDT": "TRADING", "LUNAUSDT": "BREAK", "FTTUSDT": "BREAK", "SRMUSDT": "BREAK"}
        self.assertEqual(F.candidatas(arquivo, estados), ["FTTUSDT", "LUNAUSDT", "SRMUSDT"])

    def test_zip_em_ms_e_em_microssegundos(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("a.csv", "1609459200000,1,2,0.5,1.5,100,0,0,0,40,0,0\n"
                                "1735689600000000,1,2,0.5,1.5,100,0,0,0,40,0,0\n")
        rows = F.linhas_zip(buf.getvalue())
        self.assertEqual([r[0] for r in rows], [1609459200, 1735689600])
        self.assertEqual(rows[0][6], "40")

    def test_meses_desde_2021(self):
        m = list(F.meses((2021, 3)))
        self.assertEqual(m, [(2021, 1), (2021, 2), (2021, 3)])


if __name__ == "__main__":
    unittest.main()
