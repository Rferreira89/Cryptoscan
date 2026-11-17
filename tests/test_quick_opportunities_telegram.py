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

    def test_scan_universe_fetches_only_valid_usdc_sources(self):
        class Source:
            name = "okx"
            def candles(self, asset, tf, limit=100):
                self.assert_request(asset, tf, limit)
                return [{"t": 1800 * i, "o": 100.0, "h": 101.0,
                         "l": 99.0, "c": 100.0, "v": 10.0}
                        for i in range(100)]
            @staticmethod
            def assert_request(asset, tf, limit):
                if (asset, tf, limit) != ("ETH", "30m", 100):
                    raise AssertionError("request fora do contrato USDC 30m")

        result = T.scan_universe(
            [{"asset": "ETH", "sources": ["okx"], "volume_24h": 1000}],
            [Source()], now=1800 * 100, sender=lambda msg: 1)
        self.assertEqual(result["assets_requested"], 1)
        self.assertEqual(result["assets_with_valid_data"], 1)
        self.assertEqual(result["source_by_asset"], {"ETH": "okx"})
        self.assertEqual(len(result["candidates"]), 1)
        self.assertEqual(result["candidates"][0]["side"], "SHORT")
        self.assertEqual(len(result["telegram_sent"]), 1)


if __name__ == "__main__":
    unittest.main()


class Resumo(unittest.TestCase):
    """(17/11) uma mensagem por ciclo, nao uma por candidato."""

    def cand(self, asset, score, side="LONG"):
        return {"asset": asset, "family": "momentum", "side": side, "signal_t": 1799998200, "signal_close": 10.0,
                "stop": 9.0, "target": 12.0, "score": score, "venue": "OKX", "market_type": "USD_UM_XPERP",
                "instrument_id": f"{asset}-USD_UM_XPERP-310404", "asset_class": "crypto"}

    def test_uma_mensagem_com_todos_marcados_como_vistos(self):
        from engine import quick_opportunities_telegram as T
        enviadas = []
        cands = [self.cand(f"A{i}", i % 3) for i in range(14)] + [dict(self.cand("X", 9), side="FLAT")]
        sent = T.notify_digest(cands, sender=lambda m: enviadas.append(m) or 77, max_items=10)
        self.assertEqual(len(enviadas), 1)
        self.assertEqual(len(sent), 14)
        self.assertIn("14 candidato(s)", enviadas[0])
        self.assertIn("e mais 4", enviadas[0])
        self.assertIn("Sem ordem enviada", enviadas[0])
        self.assertLess(enviadas[0].index("A2 "), enviadas[0].index("A0 "))      # maior score primeiro

    def test_falha_no_envio_nao_marca_nada(self):
        from engine import quick_opportunities_telegram as T
        self.assertEqual(T.notify_digest([self.cand("A", 1)], sender=lambda m: None), [])
        self.assertEqual(T.notify_digest([], sender=lambda m: 1), [])
