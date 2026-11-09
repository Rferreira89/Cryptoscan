import json
import tempfile
import unittest
from pathlib import Path

from engine.opportunity_funnel import record_event


class TestOpportunityFunnel(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "data" / "opportunity_funnel.jsonl"

    def tearDown(self):
        self.temp.cleanup()

    def test_regista_evento(self):
        event = record_event(
            self.path,
            stage="signal_generated",
            exchange="OKX",
            market="CRYPTO",
            symbol="BTC-USDT",
            side="LONG",
            strategy="H40",
        )

        self.assertEqual(event["stage"], "signal_generated")
        self.assertEqual(event["side"], "LONG")
        self.assertTrue(self.path.exists())

    def test_preserva_eventos_anteriores(self):
        for symbol in ("BTC-USDT", "ETH-USDT"):
            record_event(
                self.path,
                stage="universe_detected",
                exchange="OKX",
                market="CRYPTO",
                symbol=symbol,
            )

        lines = self.path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 2)

    def test_json_valido(self):
        record_event(
            self.path,
            stage="execution_candidate",
            exchange="Bybit",
            market="CRYPTO",
            symbol="ETH-USDT",
            side="SHORT",
            metrics={"spread_pct": 0.001},
        )

        event = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(event["metrics"]["spread_pct"], 0.001)

    def test_rejeita_etapa_invalida(self):
        with self.assertRaises(ValueError):
            record_event(
                self.path,
                stage="etapa_inventada",
                exchange="OKX",
                market="CRYPTO",
                symbol="BTC-USDT",
            )

    def test_rejeita_direcao_invalida(self):
        with self.assertRaises(ValueError):
            record_event(
                self.path,
                stage="signal_generated",
                exchange="OKX",
                market="CRYPTO",
                symbol="BTC-USDT",
                side="BUY",
            )

    def test_ignora_metricas_nao_finitas(self):
        event = record_event(
            self.path,
            stage="signal_generated",
            exchange="OKX",
            market="CRYPTO",
            symbol="BTC-USDT",
            metrics={
                "valid": 1.5,
                "invalid": float("nan"),
            },
        )

        self.assertEqual(event["metrics"], {"valid": 1.5})


if __name__ == "__main__":
    unittest.main()
