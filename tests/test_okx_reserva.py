"""(07/11) Europa so lanca o agente OKX como reserva: a partir de hh:30 e se nenhuma volta comecou nesta hora."""
import json, os, subprocess, sys, tempfile, unittest

from tools import okx_reserva as R

H = 1794024000                    # 2026-11-07 04:00 UTC
RAIZ = os.path.join(os.path.dirname(__file__), "..")


class Reserva(unittest.TestCase):
    def test_regras(self):
        st = {"resumo": {"t": H + 8 * 60}}
        self.assertFalse(R.lancar(st, H + 5 * 60)[0])                       # antes de hh:30: e do scanner
        self.assertFalse(R.lancar({}, H + 14 * 60)[0])
        self.assertFalse(R.lancar(st, H + 32 * 60)[0])                      # ja correu nesta hora
        self.assertTrue(R.lancar({"resumo": {"t": H - 50 * 60}}, H + 32 * 60)[0])   # scanner parado: lanca
        self.assertTrue(R.lancar({}, H + 40 * 60)[0])                       # estado vazio: lanca
        self.assertTrue(R.lancar({"resumo": {"t": "x"}}, H + 50 * 60)[0])   # estado estragado: lanca

    def test_linha_de_comandos(self):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "okx.json")
        with open(p, "w") as f:
            json.dump({"resumo": {"t": 0}}, f)
        r = subprocess.run([sys.executable, os.path.join(RAIZ, "tools", "okx_reserva.py"), p], capture_output=True, text=True)
        self.assertIn("reserva do agente OKX:", r.stdout)
        self.assertIn(r.returncode, (0, 1))
        r = subprocess.run([sys.executable, os.path.join(RAIZ, "tools", "okx_reserva.py"), os.path.join(d, "nao.json")],
                           capture_output=True, text=True)
        self.assertIn(r.returncode, (0, 1))                                 # sem ficheiro nao rebenta

    def test_workflow_europa_usa_a_reserva(self):
        s = open(os.path.join(RAIZ, ".github", "workflows", "europa-dados.yml")).read()
        passo = s.split("Lancar o agente OKX", 1)[1].split("- name:", 1)[0]
        self.assertIn("python3 tools/okx_reserva.py /tmp/eu-okx.json", passo)
        self.assertNotIn('+%M)" -lt 15', passo)
        self.assertIn("okx-agente.yml/dispatches", passo)


if __name__ == "__main__":
    unittest.main()
