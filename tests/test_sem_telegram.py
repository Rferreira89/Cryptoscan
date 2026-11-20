"""(20/11) Nenhum teste pode chegar ao Telegram do Rui, mesmo com as credenciais no ambiente do ciclo de producao."""
import os
import unittest

from engine import alerts


class SemTelegram(unittest.TestCase):
    def test_credenciais_retiradas_na_suite(self):
        self.assertFalse(any(k.startswith("TELEGRAM_") for k in os.environ))
        self.assertFalse(alerts.configured())


if __name__ == "__main__":
    unittest.main()
