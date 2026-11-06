"""(06/11) Hipoteses em dados novos: registo valido e H52 so le dados posteriores ao registo (dados sinteticos)."""
import csv
import importlib.util
import json
import os
import tempfile
import unittest

RAIZ = os.path.join(os.path.dirname(__file__), "..")
CAMPOS = ["data", "moeda", "validado", "o", "h", "l", "c", "volume_usd", "px_xperp", "px_global",
          "fund_xperp_24h", "oi_usd_global", "oi_xperp"]


def h52():
    spec = importlib.util.spec_from_file_location("h52", os.path.join(RAIZ, "backtest/estudos/novos/h52_short_oi_queda.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def gravar(d, linhas):
    with open(os.path.join(d, "2026-12.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=CAMPOS)
        w.writeheader()
        w.writerows(linhas)


def mercado(n_dias=16, sinal_dia=12):
    """40 moedas a cair 1%/dia (regime de descida); a AAA tem queda -6% com OI +10% no dia sinal_dia."""
    out = []
    for k in range(40):
        m = "AAA" if k == 0 else f"M{k:02d}"
        p = 100.0
        for i in range(n_dias):
            o, c, oi = p, p * 0.99, 1e8
            if m == "AAA" and i == sinal_dia:
                c, oi = p * 0.94, 1.1e8
            if m == "AAA" and i > sinal_dia:
                oi = 1.1e8
            out.append({"data": f"2026-12-{i + 1:02d}", "moeda": m, "validado": 1, "o": o, "h": o * 1.01, "l": c * 0.99,
                        "c": c, "volume_usd": 5e7, "px_xperp": c, "px_global": c, "fund_xperp_24h": 0.0001,
                        "oi_usd_global": oi, "oi_xperp": 1e6})
            p = c
    return out


class HipotesesNovas(unittest.TestCase):
    def test_registo_completo(self):
        hs = json.load(open(os.path.join(RAIZ, "backtest/hipoteses_novas.json"), encoding="utf-8"))
        ids = [h["id"] for h in hs]
        self.assertEqual(len(ids), len(set(ids)))
        for h in hs:
            for c in ("registada_em", "entrada", "stop", "saida", "tamanho", "universo", "regime", "custos",
                      "criterio_sucesso", "minimo_operacoes", "codigo"):
                self.assertIn(c, h)
            self.assertGreaterEqual(h["minimo_operacoes"], 30)
            self.assertTrue(os.path.exists(os.path.join(RAIZ, h["codigo"])))

    def test_h52_uma_operacao_e_a_acumular(self):
        M = h52()
        with tempfile.TemporaryDirectory() as d:
            gravar(d, mercado())
            r = M.avaliar(d, "2026-11-30")
            self.assertEqual(r["operacoes"], 1)
            self.assertEqual(r["estado"], "a acumular: 1 de 30")

    def test_h52_ignora_dados_anteriores_ao_registo(self):
        M = h52()
        with tempfile.TemporaryDirectory() as d:
            gravar(d, mercado())
            self.assertEqual(M.avaliar(d, "2026-12-05")["operacoes"], 0)   # sem 10 dias de aquecimento antes do sinal
            self.assertEqual(M.avaliar(d)["dias_de_dados"], 16)

    def test_h52_so_le_via_dados_para_avaliar(self):
        src = open(os.path.join(RAIZ, "backtest/estudos/novos/h52_short_oi_queda.py"), encoding="utf-8").read()
        self.assertIn("dados_para_avaliar", src)
        for p in ("open(", "history", "/api/v5/trade"):
            self.assertNotIn(p, src)


if __name__ == "__main__":
    unittest.main()
