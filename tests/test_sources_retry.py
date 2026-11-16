"""Regressao: respeitar Retry-After quando uma API devolve HTTP 429."""
import io
import unittest
from email.message import Message
from unittest import mock
from urllib.error import HTTPError

from engine import sources


class RetryAfter(unittest.TestCase):
    def test_429_respeita_retry_after_e_recupera(self):
        headers = Message()
        headers["Retry-After"] = "17"
        erro = HTTPError("https://example.test", 429, "Too Many Requests", headers, None)
        with mock.patch.object(sources.urllib.request, "urlopen",
                               side_effect=[erro, io.BytesIO(b'{"ok": true}')]), \
             mock.patch.object(sources.time, "sleep") as dormir:
            self.assertEqual(sources._get("https://example.test"), {"ok": True})
        dormir.assert_called_once_with(17.0)

    def test_429_sem_retry_after_usa_backoff(self):
        erro = HTTPError("https://example.test", 429, "Too Many Requests", Message(), None)
        with mock.patch.object(sources.urllib.request, "urlopen",
                               side_effect=[erro, io.BytesIO(b'{"ok": true}')]), \
             mock.patch.object(sources.time, "sleep") as dormir:
            self.assertEqual(sources._get("https://example.test"), {"ok": True})
        dormir.assert_called_once_with(sources.RETRY_WAIT)

    def test_retry_after_anomalo_tem_limite(self):
        headers = Message()
        headers["Retry-After"] = "999999"
        erro = HTTPError("https://example.test", 429, "Too Many Requests", headers, None)
        self.assertEqual(sources._retry_delay(erro, 0), 90.0)


if __name__ == "__main__":
    unittest.main()
