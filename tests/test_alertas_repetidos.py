"""(24/10) A mesma mensagem nao sai duas vezes em 6 horas, mesmo que o scan seja repetido."""
import io
import json
import os
import tempfile
import unittest
from unittest import mock

from engine import alerts


class Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class SemRepeticoes(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.old = alerts.DEDUP_FILE, alerts._SENT
        alerts.DEDUP_FILE, alerts._SENT = os.path.join(self.d, "tg.json"), None
        self.env = mock.patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "t", "TELEGRAM_CHAT_ID": "1"})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        alerts.DEDUP_FILE, alerts._SENT = self.old

    def test_repetida_nao_sai_e_sobrevive_a_um_novo_processo(self):
        n = []
        def fake(req, timeout=15):
            n.append(1)
            return Resp(json.dumps({"ok": True}).encode())
        with mock.patch.object(alerts.urllib.request, "urlopen", side_effect=fake):
            self.assertTrue(alerts.send("Sinal SEI"))
            self.assertFalse(alerts.send("Sinal SEI"))
            alerts._SENT = None                       # como um scan novo (outro processo)
            self.assertFalse(alerts.send("Sinal SEI"))
            self.assertTrue(alerts.send("Sinal AAVE"))
        self.assertEqual(len(n), 2)


if __name__ == "__main__":
    unittest.main()
