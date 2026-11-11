"""(11/11, revisao) executar.yml (executor real da Bybit): nunca corre sem o estado e o registo de execucoes, e o
registo e publicado com tentativas. Os blocos do proprio workflow correm em bash com um git falso (sem rede, sem
executor: o executor e substituido por um marcador)."""
import os
import stat
import subprocess
import tempfile
import unittest

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")


def script():
    with open(os.path.join(RAIZ, ".github", "workflows", "executar.yml"), encoding="utf-8") as f:
        linhas = f.read().split("\n")
    i = next(k for k, l in enumerate(linhas) if l.strip() == "run: |") + 1
    ind = len(linhas[i]) - len(linhas[i].lstrip())
    out = []
    for l in linhas[i:]:
        if l.strip() and len(l) - len(l.lstrip()) < ind:
            break
        out.append(l[ind:])
    return "\n".join(out)


class Executar(unittest.TestCase):
    def correr(self, rc_ls=0, fetch_data=True, fetch_exec=True, falhas_push=0):
        d = tempfile.mkdtemp()
        cont = os.path.join(d, "n")
        open(cont, "w").write("0")
        git = os.path.join(d, "git")
        open(git, "w").write(f"""#!/bin/bash
case "$1" in
  ls-remote) exit {rc_ls};;
  fetch) if [ "$4" = data ]; then {'exit 0' if fetch_data else 'exit 128'}; else {'exit 0' if fetch_exec else 'exit 128'}; fi;;
  show) echo '{{}}';;
  push) n=$(cat {cont}); n=$((n+1)); echo $n > {cont}; [ $n -le {falhas_push} ] && {{ echo "fatal https://x:TOKEN@h" >&2; exit 1; }}; exit 0;;
  *) exit 0;;
esac
""")
        os.chmod(git, os.stat(git).st_mode | stat.S_IEXEC)
        py = os.path.join(d, "python3")
        open(py, "w").write(f"""#!/bin/bash
if [ "$2" = engine.executor ]; then echo EXECUTOR_CORREU; touch {d}/ex/out/exec.json; fi
exit 0
""")
        os.chmod(py, os.stat(py).st_mode | stat.S_IEXEC)
        corpo = "sleep() { :; }\n" + script().replace("/tmp/ex", os.path.join(d, "ex")).replace("/tmp/push.err", os.path.join(d, "push.err"))
        r = subprocess.run(["bash", "-e", "-c", corpo], capture_output=True, text=True,
                           env={**os.environ, "PATH": d + ":" + os.environ["PATH"], "PUSH_URL": "https://x:TOKEN@h"})
        return r, int(open(cont).read())

    def test_caminho_normal(self):
        r, n = self.correr()
        self.assertIn("EXECUTOR_CORREU", r.stdout)
        self.assertEqual(r.returncode, 0)
        self.assertEqual(n, 1)

    def test_sem_estado_do_scan_nao_executa(self):
        r, _ = self.correr(fetch_data=False)
        self.assertNotIn("EXECUTOR_CORREU", r.stdout)
        self.assertNotEqual(r.returncode, 0)

    def test_registo_de_execucoes_ilegivel_nao_executa(self):
        for kw in ({"fetch_exec": False}, {"rc_ls": 128}):
            r, _ = self.correr(**kw)
            self.assertNotIn("EXECUTOR_CORREU", r.stdout, kw)
            self.assertNotEqual(r.returncode, 0)

    def test_primeira_execucao_sem_ramo(self):
        r, _ = self.correr(rc_ls=2)
        self.assertIn("EXECUTOR_CORREU", r.stdout)

    def test_push_falha_transitoria(self):
        r, n = self.correr(falhas_push=2)
        self.assertEqual(r.returncode, 0)
        self.assertEqual(n, 3)

    def test_push_falha_persistente_fica_vermelho_sem_credencial(self):
        r, n = self.correr(falhas_push=99)
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(n, 3)
        self.assertNotIn("TOKEN", r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
