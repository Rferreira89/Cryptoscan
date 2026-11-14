
import json
import math
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from engine.opportunity_funnel import build_event, record_event


class TestBuildEvent(unittest.TestCase):

    def test_builds_valid_event(self):
        event = build_event(
            stage="signal_generated",
            exchange="BYBIT",
            market="linear",
            symbol="BTCUSDT",
            side="LONG",
            strategy="test_strategy",
            scan_id="scan-001",
            metrics={"rsi": 25.5, "volume": 100, "active": True},
        )

        self.assertEqual(event["schema_version"], 1)
        self.assertEqual(event["stage"], "signal_generated")
        self.assertEqual(event["side"], "LONG")
        self.assertEqual(event["symbol"], "BTCUSDT")
        self.assertEqual(event["metrics"]["rsi"], 25.5)
        self.assertIsNotNone(event["event_id"])

        timestamp = datetime.fromisoformat(event["timestamp"])
        self.assertIsNotNone(timestamp.tzinfo)

    def test_default_optional_values(self):
        event = build_event(
            stage="universe_detected",
            exchange="BYBIT",
            market="linear",
            symbol="ETHUSDT",
        )

        self.assertEqual(event["side"], "NONE")
        self.assertIsNone(event["strategy"])
        self.assertIsNone(event["reason"])
        self.assertIsNone(event["scan_id"])
        self.assertEqual(event["metrics"], {})

    def test_invalid_stage_raises_value_error(self):
        with self.assertRaises(ValueError):
            build_event(
                stage=["invalid"],
                exchange="BYBIT",
                market="linear",
                symbol="BTCUSDT",
            )

    def test_invalid_side_raises_value_error(self):
        with self.assertRaises(ValueError):
            build_event(
                stage="signal_generated",
                exchange="BYBIT",
                market="linear",
                symbol="BTCUSDT",
                side=["LONG"],
            )

    def test_required_text_must_not_be_empty(self):
        for field in ("exchange", "market", "symbol"):
            kwargs = {
                "stage": "signal_generated",
                "exchange": "BYBIT",
                "market": "linear",
                "symbol": "BTCUSDT",
            }
            kwargs[field] = "   "

            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    build_event(**kwargs)

    def test_required_text_must_be_string(self):
        with self.assertRaises(ValueError):
            build_event(
                stage="signal_generated",
                exchange=123,
                market="linear",
                symbol="BTCUSDT",
            )

    def test_optional_text_must_be_string_or_none(self):
        with self.assertRaises(ValueError):
            build_event(
                stage="signal_generated",
                exchange="BYBIT",
                market="linear",
                symbol="BTCUSDT",
                strategy=123,
            )

    def test_metrics_must_be_dictionary(self):
        with self.assertRaises(ValueError):
            build_event(
                stage="signal_generated",
                exchange="BYBIT",
                market="linear",
                symbol="BTCUSDT",
                metrics=["invalid"],
            )

    def test_metrics_keep_only_safe_values(self):
        metrics = {
            "boolean": True,
            "integer": 10,
            "float": 2.5,
            "nan": float("nan"),
            "positive_inf": float("inf"),
            "negative_inf": float("-inf"),
            "text": "invalid",
            "empty_key": 99,
            123: 88,
        }

        event = build_event(
            stage="signal_generated",
            exchange="BYBIT",
            market="linear",
            symbol="BTCUSDT",
            metrics=metrics,
        )

        self.assertEqual(
            event["metrics"],
            {
                "boolean": True,
                "integer": 10,
                "float": 2.5,
            },
        )

        self.assertTrue(
            all(
                not isinstance(value, float) or math.isfinite(value)
                for value in event["metrics"].values()
            )
        )


class TestRecordEvent(unittest.TestCase):

    def test_writes_valid_jsonl_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events" / "funnel.jsonl"

            event = record_event(
                path,
                stage="signal_generated",
                exchange="BYBIT",
                market="linear",
                symbol="BTCUSDT",
                side="LONG",
            )

            self.assertIsNotNone(event)
            self.assertTrue(path.exists())

            lines = path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 1)

            saved = json.loads(lines[0])
            self.assertEqual(saved["event_id"], event["event_id"])
            self.assertEqual(saved["symbol"], "BTCUSDT")

    def test_appends_multiple_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "funnel.jsonl"

            for symbol in ("BTCUSDT", "ETHUSDT"):
                record_event(
                    path,
                    stage="universe_detected",
                    exchange="BYBIT",
                    market="linear",
                    symbol=symbol,
                )

            lines = path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 2)

    def test_none_path_returns_none(self):
        with self.assertLogs(
            "engine.opportunity_funnel",
            level="ERROR",
        ):
            result = record_event(
                None,
                stage="signal_generated",
                exchange="BYBIT",
                market="linear",
                symbol="BTCUSDT",
            )

        self.assertIsNone(result)

    def test_directory_creation_failure_is_fail_safe(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "funnel.jsonl"

            with patch.object(
                Path,
                "mkdir",
                side_effect=PermissionError("permission denied"),
            ):
                with self.assertLogs(
                    "engine.opportunity_funnel",
                    level="ERROR",
                ):
                    result = record_event(
                        path,
                        stage="signal_generated",
                        exchange="BYBIT",
                        market="linear",
                        symbol="BTCUSDT",
                    )

            self.assertIsNone(result)

    def test_file_write_failure_is_fail_safe(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "funnel.jsonl"

            with patch.object(
                Path,
                "open",
                side_effect=OSError("disk unavailable"),
            ):
                with self.assertLogs(
                    "engine.opportunity_funnel",
                    level="ERROR",
                ):
                    result = record_event(
                        path,
                        stage="signal_generated",
                        exchange="BYBIT",
                        market="linear",
                        symbol="BTCUSDT",
                    )

            self.assertIsNone(result)

    def test_invalid_event_data_still_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "funnel.jsonl"

            with self.assertRaises(ValueError):
                record_event(
                    path,
                    stage="invalid_stage",
                    exchange="BYBIT",
                    market="linear",
                    symbol="BTCUSDT",
                )


if __name__ == "__main__":
    unittest.main()
