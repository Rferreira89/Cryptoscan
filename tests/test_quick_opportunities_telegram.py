import unittest

from engine import quick_opportunities_telegram as T


class QuickOpportunitiesTelegramTests(unittest.TestCase):
    def candidate(self, **updates):
        row = {
            "asset": "ETH", "family": "momentum", "side": "LONG",
            "signal_t": 1790000000, "signal_close": 3000.0,
            "stop": 2950.0, "target": 3100.0, "max_hold_bars": 8,
            "regime": "bullish", "score": 2,
            "reason": "momentum confirmado",
        }
        row.update(updates)
        return row

    def test_message_marks_candidate_as_unvalidated_and_no_order(self):
        message = T.format_candidate(self.candidate())
        self.assertIn("CANDIDATO NÃO VALIDADO", message)
        self.assertIn("Sem ordem enviada", message)
        self.assertIn("SHORT não é executável em spot", message)
        self.assertIn("ETH | LONG", message)

    def test_signal_id_changes_by_candle_and_side(self):
        base = self.candidate()
        self.assertNotEqual(T._signal_id(base),
                            T._signal_id(self.candidate(signal_t=1790001800)))
        self.assertNotEqual(T._signal_id(base),
                            T._signal_id(self.candidate(side="SHORT")))

    def test_notify_sends_one_message_per_candidate(self):
        sent_messages = []
        def sender(message):
            sent_messages.append(message)
            return len(sent_messages)
        result = T.notify_candidates([self.candidate(),
                                      self.candidate(side="SHORT")],
                                     sender=sender)
        self.assertEqual(len(sent_messages), 2)
        self.assertEqual(len(result), 2)
        self.assertTrue(all(x["message_id"] for x in result))

    def test_invalid_side_is_rejected_by_formatter(self):
        with self.assertRaises(ValueError):
            T.format_candidate(self.candidate(side="FLAT"))

    def test_empty_scan_does_not_send(self):
        sent = []
        result = T.scan_candles({}, sender=lambda msg: sent.append(msg) or 1)
        self.assertEqual(result["candidates"], [])
        self.assertEqual(result["telegram_sent"], [])
        self.assertEqual(sent, [])


if __name__ == "__main__":
    unittest.main()
