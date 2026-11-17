"""(17/11) Regressao da falha de 16/11 (03:15-12:20 UTC, 9 h sem scanner): um commit que falha os testes na main
nao pode parar a producao. tools/codigo_bom.sh testa cada commit novo uma vez e mantem o ultimo codigo bom."""
import os
import re
import shutil
import subprocess
import tempfile
import unittest

RAIZ = os.path.join(os.path.dirname(__file__), "..")
SCRIPT = os.path.abspath(os.path.join(RAIZ, "tools", "codigo_bom.sh"))
WF = os.path.join(RAIZ, ".github", "workflows")


def sh(cmd, cwd):
    return subprocess.run(["bash", "-c", cmd], cwd=cwd, capture_output=True, text=True)


@unittest.skipUnless(shutil.which("git") and shutil.which("bash"), "precisa de git e bash")
class CodigoBom(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.origem = os.path.join(self.d, "origem")
        self.trab = os.path.join(self.d, "trab")
        os.makedirs(self.origem)
        sh("git init -q -b main && git config user.email t@t && git config user.name t && "
           "echo 1 > a && git add a && git commit -qm bom1", self.origem)
        sh(f"git clone -q {self.origem} {self.trab}", self.d)

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def commit(self, msg, mau=False):
        extra = "touch MAU && git add MAU" if mau else "git rm -q --ignore-unmatch MAU"
        sh(f"echo {msg} >> a && git add a && {extra} && git commit -qm {msg}", self.origem)
        return sh("git rev-parse HEAD", self.origem).stdout.strip()

    def ciclo(self, estado="true"):
        """Corre validar_codigo com o estado anterior (variaveis) e devolve as variaveis e o HEAD."""
        r = sh(f"{estado}; export CODIGO_BOM_TESTES='test ! -f MAU'; unset TELEGRAM_BOT_TOKEN; set -eo pipefail; "
               f"source {SCRIPT}; validar_codigo; "
               "echo \"BOM=$BOM\"; echo \"MAU=${MAU:-}\"; echo \"OK=$CODIGO_OK\"; echo \"AVISO=${AVISO_MAU:-}\"; "
               "echo \"HEAD=$(git rev-parse HEAD)\"", self.trab)
        self.assertEqual(r.returncode, 0, r.stderr)
        return dict(re.findall(r"^(\w+)=(.*)$", r.stdout, re.M))

    def test_commit_reprovado_nao_entra_e_o_bom_continua(self):
        v = self.ciclo()
        bom1 = sh("git rev-parse HEAD", self.origem).stdout.strip()
        self.assertEqual((v["BOM"], v["OK"], v["HEAD"]), (bom1, "1", bom1))
        mau = self.commit("partido", mau=True)
        v = self.ciclo(f"BOM={bom1}")
        self.assertEqual((v["BOM"], v["MAU"], v["OK"], v["HEAD"]), (bom1, mau, "1", bom1))
        self.assertIn("reprovado", v["AVISO"])
        # o mesmo commit mau nao volta a ser testado nem avisado
        v = self.ciclo(f"BOM={bom1}; MAU={mau}")
        self.assertEqual((v["HEAD"], v["AVISO"]), (bom1, ""))
        # corrigido na main: o commit seguinte passa e entra
        bom2 = self.commit("corrigido")
        v = self.ciclo(f"BOM={bom1}; MAU={mau}")
        self.assertEqual((v["BOM"], v["MAU"], v["OK"], v["HEAD"]), (bom2, "", "1", bom2))

    def test_reinicio_retoma_o_bom_publicado(self):
        bom1 = sh("git rev-parse HEAD", self.origem).stdout.strip()
        self.commit("partido", mau=True)
        v = self.ciclo(f"CODIGO_BOM_INICIAL={bom1}")       # job relancado: le o codigo_bom.txt do ramo data
        self.assertEqual((v["BOM"], v["OK"], v["HEAD"]), (bom1, "1", bom1))

    def test_sem_codigo_bom_conhecido_corre_a_main_sem_validar(self):
        self.commit("partido", mau=True)
        v = self.ciclo()
        novo = sh("git rev-parse HEAD", self.origem).stdout.strip()
        self.assertEqual((v["BOM"], v["OK"], v["HEAD"]), ("", "0", novo))   # o scan volta a testar e nao corre


class Workflows(unittest.TestCase):
    def test_producao_usa_o_codigo_validado(self):
        for f in ("executar", "okx-agente", "europa-dados", "arena"):
            s = open(os.path.join(WF, f"{f}.yml"), encoding="utf-8").read()
            self.assertIn("codigo_bom.txt", s, f)
            self.assertIn("|| true)", s, f)            # sem ficheiro nao pode rebentar com bash -e

    def test_scanner_valida_antes_de_correr(self):
        s = open(os.path.join(WF, "scan.yml"), encoding="utf-8").read()
        self.assertIn("source /tmp/codigo_bom.sh && validar_codigo", s)
        self.assertIn("git add codigo_bom.txt", s)
        self.assertNotIn("git fetch -q origin main && git reset -q --hard FETCH_HEAD", s)

    def test_codigo_compila(self):
        """Commits com texto cortado (16/11: engine/config.py e engine/promo.py) apanhados logo."""
        import py_compile
        for pasta in ("engine", "tools"):
            for raiz, _, fs in os.walk(os.path.join(RAIZ, pasta)):
                for n in fs:
                    if n.endswith(".py"):
                        py_compile.compile(os.path.join(raiz, n), doraise=True)


if __name__ == "__main__":
    unittest.main()
