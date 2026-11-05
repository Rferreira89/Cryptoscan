import json
import os
import tempfile
import unittest

from tools import fetch_derivados as F

T0 = 1735689600            # 2025-01-01 00:00 UTC
CAB = ["create_time", "symbol", "sum_open_interest", "sum_open_interest_value", "count_toptrader_long_short_ratio",
       "sum_toptrader_long_short_ratio", "count_long_short_ratio", "sum_taker_long_short_vol_ratio"]


class Agrega(unittest.TestCase):
    def test_ultimo_oi_e_medias_por_vela_de_4h(self):
        L = [["2025-01-01 00:00:00", "BTCUSDT", "100", "1000", "0", "2.0", "1.0", "0.8"],
             ["2025-01-01 03:55:00", "BTCUSDT", "120", "1200", "0", "4.0", "3.0", "1.2"],
             ["2025-01-01 04:00:00", "BTCUSDT", "130", "1300", "0", "1.0", "1.0", "1.0"]]
        a = F.agrega(L)
        self.assertEqual(sorted(a), [T0, T0 + 14400])
        v = a[T0]
        self.assertEqual((v[0], v[1], v[5]), (120.0, 1200.0, 2))
        self.assertAlmostEqual(v[2] / v[5], 3.0)
        self.assertAlmostEqual(v[4] / v[5], 1.0)


class Fase2(unittest.TestCase):
    def test_velas_de_30_min_separam_contas_e_posicoes_e_rejeitam_oi_invalido(self):
        L = [CAB,
             ["2025-01-01 00:00:00", "X", "100", "1000", "1.5", "2.0", "1.1", "0.8"],
             ["2025-01-01 00:25:00", "X", "110", "1100", "2.5", "4.0", "1.3", "1.2"],
             ["2025-01-01 00:30:00", "X", "0", "0", "1", "1", "1", "1"],            # OI 0: invalido
             ["2025-01-01 00:35:00", "X", "120", "", "1", "1", "1", ""]]
        v, mas = F.agrega30(L)
        self.assertEqual(mas, 1)
        self.assertEqual(sorted(v), [T0, T0 + 1800])
        a = v[T0]
        self.assertEqual(a[1], "110.0000")                         # ultimo OI da vela
        self.assertEqual((a[3], a[4], a[5], a[6], a[7]), ("2.0000", "3.0000", "1.2000", "1.0000", "2"))
        b = v[T0 + 1800]
        self.assertEqual((b[2], b[6]), ("", ""))                   # vazio fica vazio, nunca estimado

    def test_liquidacoes_sell_e_long_buy_e_short(self):
        L = [["time", "side", "order_type", "time_in_force", "original_quantity", "price", "average_price",
              "order_status", "last_fill_quantity", "accumulated_fill_quantity"],
             [str(T0 * 1000 + 5000), "SELL", "LIMIT", "IOC", "2", "10", "9", "FILLED", "2", "2"],
             [str(T0 * 1000 + 9000), "BUY", "LIMIT", "IOC", "1", "11", "12", "FILLED", "1", "1"]]
        r = F.agrega_liq(L)
        self.assertEqual(r[T0], [str(T0), "18.00", "12.00", "2"])

    def test_dias_em_falta_e_datas_do_indice(self):
        self.assertEqual(F.intervalos_em_falta(["2025-01-01", "2025-01-02", "2025-01-05", "2025-01-06", "2025-01-08"]),
                         [["2025-01-03", "2025-01-04"], ["2025-01-07", "2025-01-07"]])
        ch = ["data/futures/um/daily/metrics/XUSDT/XUSDT-metrics-2025-01-02.zip",
              "data/futures/um/daily/metrics/XUSDT/XUSDT-metrics-2025-01-02.zip.CHECKSUM",
              "data/futures/um/daily/metrics/XUSDT/XUSDT-metrics-2025-01-01.zip"]
        self.assertEqual(F.datas_do_indice(ch), ["2025-01-01", "2025-01-02"])
        self.assertEqual(F.datas_do_indice(["a/X-fundingRate-2024-03.zip"], mensal=True), ["2024-03"])

    def test_funde_nunca_perde_velas(self):
        self.assertEqual(F.funde({1: ["1", "a"], 2: ["2", "b"]}, {2: ["2", "c"], 3: ["3", "d"]}),
                         {1: ["1", "a"], 2: ["2", "c"], 3: ["3", "d"]})

    def test_recolha_retoma_nao_repete_e_marca_erros(self):
        chamadas = []

        def listar(prefixo):
            if "/metrics/" in prefixo:
                return [f"{prefixo}XUSDT-metrics-2025-01-0{d}.zip" for d in (1, 2, 4)]
            if "fundingRate" in prefixo:
                return [f"{prefixo}XUSDT-fundingRate-2025-01.zip"]
            return []

        def baixar(url):
            chamadas.append(url)
            if "2025-01-02" in url and len([c for c in chamadas if "2025-01-02" in c]) == 1:
                return "erro"
            if "fundingRate" in url:
                return [["calc_time", "funding_interval_hours", "last_funding_rate"], [str(T0 * 1000), "8", "0.0001"]]
            d = url.split("metrics-")[1][:10]
            return [CAB, [f"{d} 00:00:00", "X", "100", "1000", "1", "1", "1", "1"]]
        with tempfile.TemporaryDirectory() as p:
            pe = F._estado(p, "X")
            F.recolhe_moeda(p, "X", pe, __import__("time").time(), listar, baixar)
            e = pe[1]
            self.assertEqual(e["m"], ["2025-01-01", "2025-01-04"])          # o dia com erro fica por fazer
            self.assertIn("m:2025-01-02", e["erros"])
            n1 = len(chamadas)
            pe2 = F._estado(p, "X")
            F.recolhe_moeda(p, "X", pe2, __import__("time").time(), listar, baixar)
            self.assertEqual(pe2[1]["m"], ["2025-01-01", "2025-01-02", "2025-01-04"])
            self.assertEqual(len(chamadas) - n1, 1)                          # so o dia que faltava
            self.assertEqual(len(F.ler_csv(os.path.join(p, "metrics30m", "X.csv.gz"))), 3)
            r = F.resumo_moeda(p, "X", pe2[1], "retirada")
            self.assertEqual((r["oi_dias"], r["oi_dias_em_falta"], r["oi_intervalos_em_falta"]), (3, 1, [["2025-01-03", "2025-01-03"]]))
            self.assertEqual((r["funding_meses"], r["liq_dias"], r["grupo"]), (1, 0, "retirada"))
            with open(os.path.join(p, "estado", "X.json")) as f:
                self.assertEqual(json.load(f)["m"], pe2[1]["m"])


if __name__ == "__main__":
    unittest.main()
