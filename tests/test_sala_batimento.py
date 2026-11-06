"""(06/11, evolucao continua) Sala de controlo: batimento do agente OKX e contagem real de contratos no radar.
Antes o radar dizia "220 criptos" fixo (sao 289) e nada mostrava ha quanto tempo o agente correu
(a paragem de 05/11, 06:30-10:15 UTC, nao se via no iPhone)."""
import json
import os
import re
import shutil
import subprocess
import unittest

HTML = os.path.join(os.path.dirname(__file__), "..", "scanner", "index.html")


def _src():
    return open(HTML, encoding="utf-8").read()


def _fn():
    m = re.search(r"^function batimentoOKX\(t,now\)\{.*\}$", _src(), re.M)
    return m.group(0) if m else None


class SalaBatimento(unittest.TestCase):
    def test_radar_sem_contagem_fixa(self):
        s = _src()
        self.assertNotIn("220 criptos", s)
        self.assertIn("R.contratos", s)

    def test_funcao_e_banner_ligados_a_sala(self):
        s = _src()
        self.assertIsNotNone(_fn())
        self.assertIn("batimentoOKX(R.t,Date.now()/1000)", s)
        self.assertIn("el.innerHTML=btB+contas", s)

    @unittest.skipUnless(shutil.which("node"), "sem node")
    def test_niveis(self):
        js = _fn() + "\nconst now=1800000000;console.log(JSON.stringify([" \
            "batimentoOKX(now-20*60,now),batimentoOKX(now-100*60,now),batimentoOKX(now-(3*60+45)*60,now)," \
            "batimentoOKX(0,now),batimentoOKX(now+30,now)]))"
        out = json.loads(subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=20).stdout)
        self.assertEqual([o["nivel"] for o in out], ["ok", "atraso", "parado", "sem", "ok"])
        self.assertEqual(out[0]["dur"], "20 min")
        self.assertEqual(out[2]["dur"], "3 h 45 min")
        self.assertIn("🔴", out[2]["txt"])
        self.assertEqual(out[4]["dur"], "0 min")        # relogio do telemovel adiantado: nunca negativo


if __name__ == "__main__":
    unittest.main()
