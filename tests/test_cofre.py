"""(28/10, OK do Rui) Cofre: completo cifrado, copias publicas sem dinheiro, transicao segura."""
import json
import os
import tempfile
import unittest
from unittest import mock

from engine import cifra, europa, publico, run

STATE = {"capital": 120.55, "ledger": [{"id": "SEI-1", "asset": "SEI", "status": "OPEN", "result_r": None,
                                         "position_usdc": 5.85, "risk_usdc": 0.89, "risk_pct": 0.25}],
         "arena": {"vivos": 9}}
RES = {"generated_at": 1, "status_global": "OK", "conta": {"equity": 347.31},
       "universe": [{"asset": "SEI", "price": 0.0548, "decision": {"plan": {"position_usdc": 5.85, "stop": 0.0656}}}],
       "arena": {"vivos": 9}}


class Cofre(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.old = run.OUT
        run.OUT = self.d

    def tearDown(self):
        run.OUT = self.old

    def env(self, key="pw-teste"):
        return mock.patch.dict(os.environ, {"CRYPTOSCAN_COFRE": "1", "DATA_KEY": key})

    def test_ida_e_volta_e_copias_sem_dinheiro(self):
        with self.env():
            run.save(STATE, RES, [{"event": "ISSUED", "id": "SEI-1", "signal": {"plan": {"position_usdc": 5.85}}}])
            for f in ("cofre_scan.json", "cofre_state.json", "cofre_audit.jsonl"):
                self.assertTrue(cifra.e_envelope(json.load(open(os.path.join(self.d, f)))), f)
            pub = open(os.path.join(self.d, "scan.json")).read() + open(os.path.join(self.d, "state.json")).read() \
                + open(os.path.join(self.d, "audit.jsonl")).read()
            for v in ("347.31", "120.55", "5.85", "0.89"):
                self.assertNotIn(v, pub)
            self.assertIn('"vivos":9', pub)                          # os agentes continuam a ver a arena
            self.assertEqual(run._load("state.json", None), STATE)
            self.assertEqual(run._load("scan.json", None), RES)

    def test_transicao_le_o_completo_antigo_e_o_audit(self):
        json.dump(STATE, open(os.path.join(self.d, "state.json"), "w"))
        open(os.path.join(self.d, "audit.jsonl"), "w").write(json.dumps({"event": "OLD", "risk_usdc": 1}) + "\n")
        with self.env():
            st = run._load("state.json", None)
            self.assertEqual(st, STATE)
            run.save(st, RES, [])
            self.assertIn('"OLD"', cifra.ler_texto(os.path.join(self.d, "cofre_audit.jsonl")))
            aud = open(os.path.join(self.d, "audit.jsonl")).read()
            self.assertIn('"OLD"', aud)
            self.assertNotIn("risk_usdc", aud)

    def test_copia_publica_sozinha_para_o_scan(self):
        json.dump(publico.state(STATE), open(os.path.join(self.d, "state.json"), "w"))
        with self.env():
            with self.assertRaises(RuntimeError):
                run._load("state.json", None)

    def test_sem_chave_fica_em_claro_mas_no_cofre(self):
        with self.env(key=""):
            run.save(STATE, RES, [])
            self.assertEqual(json.load(open(os.path.join(self.d, "cofre_state.json"))), STATE)
            self.assertEqual(run._load("state.json", None), STATE)

    def test_cofre_cifrado_e_chave_errada_nao_recomeca_vazio(self):
        with self.env():
            run.save(STATE, RES, [])
        with self.env(key="errada"):
            with self.assertRaises(cifra.Invalido):
                run._load("state.json", None)

    def test_ciclo_antigo_fica_igual(self):
        with mock.patch.dict(os.environ, {"CRYPTOSCAN_COFRE": "", "DATA_KEY": ""}):
            run.save(STATE, RES, [])
            self.assertFalse(os.path.exists(os.path.join(self.d, "cofre_state.json")))
            self.assertEqual(json.load(open(os.path.join(self.d, "state.json"))), STATE)


class ContaCifrada(unittest.TestCase):
    def test_europa_decifra_a_conta(self):
        import time
        with mock.patch.dict(os.environ, {"DATA_KEY": "pw"}), tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump({"t": time.time(), "conta": cifra.fechar_obj({"ok": True, "equity": 9})}, f)
        with mock.patch.dict(os.environ, {"DATA_KEY": "pw"}):
            self.assertEqual(europa.load(path=f.name)["conta"]["equity"], 9)
        with mock.patch.dict(os.environ, {"DATA_KEY": ""}):
            self.assertFalse(europa.load(path=f.name)["conta"]["ok"])        # sem chave: sem conta, sem lixo
        os.unlink(f.name)


if __name__ == "__main__":
    unittest.main()
