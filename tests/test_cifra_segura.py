import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from engine import cifra


class TestGravarTextoObrigatorio(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.path = Path(self.temp_dir.name) / "cofre.json"

    def test_recusa_escrita_sem_chave(self):
        with patch.object(cifra, "senha", return_value=""):
            with self.assertRaises(cifra.SemChave):
                cifra.gravar_texto_obrigatorio(
                    self.path, '{"segredo": 123}'
                )

        self.assertFalse(self.path.exists())

    def test_grava_envelope_cifrado(self):
        with patch.object(cifra, "senha", return_value="chave-teste"):
            cifra.gravar_texto_obrigatorio(
                self.path, '{"segredo": 123}'
            )

        conteudo = self.path.read_text(encoding="utf-8")
        envelope = json.loads(conteudo)

        self.assertIn("cifra", envelope)
        self.assertIn("selo", envelope)
        self.assertNotIn("segredo", conteudo)

    def test_recupera_conteudo_original(self):
        original = '{"segredo": 123}'

        with patch.object(cifra, "senha", return_value="chave-teste"):
            cifra.gravar_texto_obrigatorio(self.path, original)

            envelope = json.loads(
                self.path.read_text(encoding="utf-8")
            )
            recuperado = cifra.decifrar_bytes(envelope).decode("utf-8")

        self.assertEqual(recuperado, original)

    def test_falha_na_escrita_preserva_destino(self):
        original = "conteudo-anterior"
        self.path.write_text(original, encoding="utf-8")

        with patch.object(cifra, "senha", return_value="chave-teste"):
            with patch.object(
                cifra.os,
                "replace",
                side_effect=OSError("falha simulada")
            ):
                with self.assertRaises(OSError):
                    cifra.gravar_texto_obrigatorio(
                        self.path, '{"novo": true}'
                    )

        self.assertEqual(
            self.path.read_text(encoding="utf-8"),
            original
        )

        temporarios = list(
            Path(self.temp_dir.name).glob(".cryptoscan-*")
        )
        self.assertEqual(temporarios, [])

    def test_leitura_com_ler_texto(self):
        original = '{"segredo": 456}'

        with patch.object(cifra, "senha", return_value="chave-teste"):
            cifra.gravar_texto_obrigatorio(self.path, original)
            recuperado = cifra.ler_texto(self.path)

        self.assertEqual(recuperado, original)

    def test_leitura_cifrada_sem_chave(self):
        with patch.object(cifra, "senha", return_value="chave-teste"):
            cifra.gravar_texto_obrigatorio(
                self.path, '{"segredo": 789}'
            )

        with patch.object(cifra, "senha", return_value=""):
            with self.assertRaises(cifra.SemChave):
                cifra.ler_texto(self.path)

    def test_leitura_cifrada_com_chave_errada(self):
        with patch.object(cifra, "senha", return_value="chave-correta"):
            cifra.gravar_texto_obrigatorio(
                self.path, '{"segredo": 789}'
            )

        with patch.object(cifra, "senha", return_value="chave-errada"):
            with self.assertRaises(cifra.Invalido):
                cifra.ler_texto(self.path)

    def test_leitura_texto_antigo_sem_cifra(self):
        original = '{"formato": "antigo", "valor": 123}'
        self.path.write_text(original, encoding="utf-8")

        recuperado = cifra.ler_texto(self.path)

        self.assertEqual(recuperado, original)


if __name__ == "__main__":
    unittest.main()
