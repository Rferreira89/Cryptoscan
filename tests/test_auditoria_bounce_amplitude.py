import unittest
from unittest import mock

from engine import paper_bounce as PB
from tools import arena_ringue as R
from tools import auditoria_bounce_amplitude as A


class TestAuditoriaSoLeitura(unittest.TestCase):
    def test_sig_amp_filtra_pelo_limiar_sem_mudar_o_ringue(self):
        amp0 = R.AMP_MIN
        c4 = [{"t": 1000}]
        with mock.patch.object(R, "sig_x30", return_value={"stop": 1, "tp": [2]}), \
                mock.patch.object(R, "amplitude_em", return_value=0.23):
            self.assertIsNone(A.sig_amp(0.25)(c4))
            self.assertEqual(A.sig_amp(0.22)(c4)["amp"], 0.23)
        with mock.patch.object(R, "sig_x30", return_value=None):
            self.assertIsNone(A.sig_amp(0.0)(c4))
        self.assertEqual(R.AMP_MIN, amp0)

    def test_limiar_igual_ao_do_ringue_da_o_mesmo_que_o_ringue(self):
        c4 = [{"t": 1000}]
        for f in (0.10, 0.25, 0.40):
            with mock.patch.object(R, "sig_x30", return_value={"stop": 1, "tp": [2]}), \
                    mock.patch.object(R, "amplitude_em", return_value=f):
                self.assertEqual(R.sig_amplitude(c4) is None, A.sig_amp(R.AMP_MIN)(c4) is None)

    def test_custos_repostos_mesmo_com_erro(self):
        f0, s0 = PB.FEE_PCT, PB.SLIP_PCT
        with mock.patch.object(A, "operacoes", side_effect=RuntimeError("x")):
            with self.assertRaises(RuntimeError):
                A.com_custos({}, {}, 0, None, 9.9, 9.9)
        self.assertEqual((PB.FEE_PCT, PB.SLIP_PCT), (f0, s0))

    def test_registo_do_combate(self):
        st = {"arena": {"longo": {"lutadores": {"BOUNCE_AMPLITUDE": {
            "n": 16, "avg_r": 0.8, "recentes": [[100, 0.5], [100, 0.6]]}}}}}
        lu, rec = A.registo_combate(st)
        self.assertEqual(lu["n"], 16)
        self.assertEqual(len(rec), 2)
        self.assertEqual(A.resumo(rec)["n_acontecimentos"], 1)


if __name__ == "__main__":
    unittest.main()
