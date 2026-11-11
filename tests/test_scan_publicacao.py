"""(11/11, revisao) A publicacao do estado no ciclo do scan (Bybit): tenta 3 vezes, devolve erro se falhar, e o
executor da Bybit so e lancado se o estado foi publicado. Corre as funcoes do proprio scan.yml em bash, com um
`git` falso (nada vai a rede)."""
import os
import re
import stat
import subprocess
import tempfile
import unittest


RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")


def script_do_ciclo():
    """O bloco 'run' do passo 'Ciclo de scans', sem a indentacao do YAML (so biblioteca padrao: este teste tambem
    corre no ciclo do scan, que nao instala o PyYAML)."""
    with open(os.path.join(RAIZ, ".github", "workflows", "scan.yml"), encoding="utf-8") as f:
        linhas = f.read().split("\n")
    i = next(k for k, l in enumerate(linhas) if "name: Ciclo de scans" in l)
    i = next(k for k in range(i, len(linhas)) if linhas[k].strip() == "run: |") + 1
    ind = len(linhas[i]) - len(linhas[i].lstrip())
    out = []
    for l in linhas[i:]:
        if l.strip() and len(l) - len(l.lstrip()) < ind:
            break
        out.append(l[ind:])
    return "\n".join(out)


def funcoes():
    s = script_do_ciclo()
    ini = s.index("publish() {")
    fim = s.index("while [")
    return s[ini:fim]


class Publicacao(unittest.TestCase):
    def correr(self, falhas, extra):
        d = tempfile.mkdtemp()
        cont = os.path.join(d, "n")
        open(cont, "w").write("0")
        git = os.path.join(d, "git")
        open(git, "w").write(f"""#!/bin/bash
if [ "$1" = push ]; then
  n=$(cat {cont}); n=$((n+1)); echo $n > {cont}
  if [ $n -le {falhas} ]; then echo "remote: fatal error in commit_refs https://x:TOKEN@h/r" >&2; exit 1; fi
fi
exit 0
""")
        os.chmod(git, os.stat(git).st_mode | stat.S_IEXEC)
        os.makedirs(os.path.join(d, "out"))
        for f in ("scan.json", "state.json"):
            open(os.path.join(d, "out", f), "w").write("{}")
        corpo = "set -eo pipefail\nsleep() { :; }\n" + funcoes() + extra
        r = subprocess.run(["bash", "-c", corpo], cwd=d, capture_output=True, text=True,
                           env={**os.environ, "PATH": d + ":" + os.environ["PATH"], "PUSH_URL": "https://x:TOKEN@h/r"})
        return r, int(open(cont).read())

    def test_falha_transitoria_publica_a_segunda(self):
        r, n = self.correr(1, 'publish scan && echo PUBLICADO\n')
        self.assertIn("PUBLICADO", r.stdout)
        self.assertEqual(n, 2)

    def test_falha_persistente_devolve_erro_sem_matar_o_ciclo(self):
        r, n = self.correr(99, 'if publish scan; then echo LANCA_EXECUTOR; else echo NAO_LANCA; fi\npublish erro || true\necho CICLO_CONTINUA\n')
        self.assertIn("NAO_LANCA", r.stdout)
        self.assertNotIn("LANCA_EXECUTOR", r.stdout)
        self.assertIn("CICLO_CONTINUA", r.stdout)
        self.assertEqual(n, 6)                                   # 3 tentativas em cada uma das duas publicacoes
        self.assertNotIn("TOKEN", r.stdout + r.stderr)

    def test_executor_so_e_lancado_depois_de_publicar(self):
        s = script_do_ciclo()
        self.assertRegex(s, r"if publish scan; then\s+if \[ -f out/\.exec \]")
        self.assertIn('if [ -f out/.exec ] && [ "$PUB" = 0 ]', s)
        self.assertIsNone(re.search(r"^\s+publish erro\s*$", s, re.M))   # nenhuma chamada solta (set -e)


if __name__ == "__main__":
    unittest.main()
