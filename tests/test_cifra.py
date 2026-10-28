"""(28/10) Cifra dos dados financeiros: AES-256-CTR + HMAC, igual com e sem a biblioteca."""
import json
import os
import tempfile
import unittest
from unittest import mock

from engine import cifra as C


class Cifra(unittest.TestCase):
    def test_vetor_fips197_aes256(self):
        k = bytes(range(32))
        p = bytes.fromhex("00112233445566778899aabbccddeeff")
        self.assertEqual(C.aes256_bloco(k, p).hex(), "8ea2b7ca516745bfeafc49904b496089")

    def test_ctr_puro_igual_a_biblioteca_quando_existe(self):
        k, iv = os.urandom(32), b"\xff" * 15 + b"\xfe"            # o contador passa o limite
        dados = os.urandom(1000)
        puro = C._ctr_puro(k, iv, dados)
        try:
            from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        except Exception:
            self.skipTest("sem a biblioteca cryptography")
        e = Cipher(algorithms.AES(k), modes.CTR(iv)).encryptor()
        self.assertEqual(puro, e.update(dados) + e.finalize())

    def test_ida_e_volta_e_selo(self):
        env = C.cifrar_bytes(b'{"equity": 347.31}', "segredo-teste")
        self.assertTrue(C.e_envelope(env))
        self.assertNotIn("347", json.dumps(env))
        self.assertEqual(C.decifrar_bytes(env, "segredo-teste"), b'{"equity": 347.31}')
        with self.assertRaises(C.Invalido):
            C.decifrar_bytes(env, "outra")
        mau = dict(env, dados=env["dados"][:-4] + "AAAA")
        with self.assertRaises(C.Invalido):
            C.decifrar_bytes(mau, "segredo-teste")

    def test_sem_chave_fica_em_claro_e_cifrado_sem_chave_nao_le(self):
        with mock.patch.dict(os.environ, {"DATA_KEY": ""}):
            self.assertEqual(C.fechar_obj({"a": 1}), {"a": 1})
            env = C.cifrar_bytes(b"{}", "x")
            with self.assertRaises(C.SemChave):
                C.abrir_obj(env)

    def test_ficheiros_e_linha_de_comandos(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"DATA_KEY": "pw-teste"}):
            p = os.path.join(d, "state.json")
            C.gravar_texto(p, '{"capital": 120.55}')
            self.assertNotIn("120", open(p).read())
            self.assertEqual(json.loads(C.ler_texto(p)), {"capital": 120.55})
            C._main(["abrir", p])
            self.assertEqual(json.load(open(p)), {"capital": 120.55})
            C._main(["fechar", p])
            self.assertTrue(C.e_envelope(json.load(open(p))))
            q = os.path.join(d, "dados.json")
            json.dump({"conta": {"equity": 9}, "deriv": [1]}, open(q, "w"))
            C._main(["fechar-campo", q, "conta"])
            dd = json.load(open(q))
            self.assertTrue(C.e_envelope(dd["conta"]))
            self.assertEqual(dd["deriv"], [1])
            C._main(["abrir-campo", q, "conta"])
            self.assertEqual(json.load(open(q))["conta"], {"equity": 9})


if __name__ == "__main__":
    unittest.main()
