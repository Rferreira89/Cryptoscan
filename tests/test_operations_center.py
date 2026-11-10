"""(10/11) Operations Center (scanner/index.html + scanner/central/): os testes dos modulos do browser correm em Node.
Camada de dados, estados dos agentes, reconciliacao, cofre, indicadores, so leitura e um so piso."""
import os
import shutil
import subprocess
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
TESTES = os.path.join(AQUI, "..", "scanner", "central", "testes", "dados.test.mjs")


@unittest.skipUnless(shutil.which("node"), "node nao instalado")
class OperationsCenter(unittest.TestCase):
    def test_modulos_do_browser(self):
        r = subprocess.run(["node", "--test", TESTES], capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr[-2000:])

    def test_pagina_principal_e_versao_anterior(self):
        idx = open(os.path.join(AQUI, "..", "scanner", "index.html"), encoding="utf-8").read()
        v1 = open(os.path.join(AQUI, "..", "scanner", "v1.html"), encoding="utf-8").read()
        self.assertIn("central/app.js", idx)
        self.assertIn('href="v1.html"', idx)
        self.assertIn('fetch("./v1.html', v1)                # a versao anterior ja nao salta para a nova
        self.assertIn("Concept &amp; Creative Direction", idx)   # (10/11, Atlas) autoria do conceito


if __name__ == "__main__":
    unittest.main()
