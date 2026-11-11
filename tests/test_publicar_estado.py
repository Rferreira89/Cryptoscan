"""(11/11, auditoria P3) Publicacao do estado com tentativas, falha persistente, aviso unico e recuperacao.
Nada vai a rede: o git e o Telegram sao substituidos; a pasta local e temporaria."""
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import publicar_estado as P  # noqa: E402


class R:
    def __init__(self, code, err=""):
        self.returncode, self.stderr, self.stdout = code, err, ""


class GitFalso:
    """Falha o push as primeiras `falhas` vezes; regista todas as chamadas."""

    def __init__(self, falhas):
        self.falhas = falhas
        self.chamadas = []

    def __call__(self, pasta, *args):
        self.chamadas.append(args)
        if args[0] == "push":
            if self.falhas > 0:
                self.falhas -= 1
                return R(1, "remote: fatal error in commit_refs")
            return R(0)
        return R(0)

    def pushes(self):
        return sum(1 for a in self.chamadas if a[0] == "push")


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.pasta = os.path.join(self.tmp.name, "trabalho")
        os.makedirs(self.pasta)
        self.env = mock.patch.dict(os.environ, {"ESTADO_LOCAL": os.path.join(self.tmp.name, "local")})
        self.env.start()
        json.dump({"volta": {"t": 200}, "real": {"ops": {}}}, open(os.path.join(self.pasta, "okx.json"), "w"))
        self.avisos = []

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def pub(self, git):
        return P.publicar(self.pasta, "okx", ["okx.json", "cofre_okx.json"], push_url="https://x:SEGREDO@h/r",
                          dormir=lambda s: None, git=git, avisar=lambda t: self.avisos.append(t) or True)


class Publicar(Base):
    def test_falha_transitoria_recupera_na_tentativa_seguinte(self):
        g = GitFalso(falhas=1)
        self.assertTrue(self.pub(g))
        self.assertEqual(g.pushes(), 2)
        self.assertEqual(P.ler_falhas("okx")["seguidas"], 0)
        self.assertFalse(os.path.exists(os.path.join(P.pasta_local("okx"), "okx.json")))   # copia apagada
        self.assertEqual(self.avisos, [])

    def test_falha_em_todas_as_tentativas_guarda_copia_e_nao_avisa_a_primeira(self):
        g = GitFalso(falhas=99)
        self.assertFalse(self.pub(g))
        self.assertEqual(g.pushes(), len(P.ESPERAS) + 1)
        self.assertTrue(os.path.exists(os.path.join(P.pasta_local("okx"), "okx.json")))
        self.assertEqual(P.ler_falhas("okx")["seguidas"], 1)
        self.assertEqual(self.avisos, [])

    def test_falha_persistente_avisa_uma_so_vez(self):
        for _ in range(4):
            self.pub(GitFalso(falhas=99))
        self.assertEqual(len(self.avisos), 1)
        self.assertIn("não é publicado", self.avisos[0])
        self.assertNotIn("SEGREDO", self.avisos[0])

    def test_recuperacao_avisa_e_limpa_o_contador(self):
        for _ in range(2):
            self.pub(GitFalso(falhas=99))
        self.assertTrue(self.pub(GitFalso(falhas=0)))
        self.assertEqual(len(self.avisos), 2)
        self.assertIn("recuperada", self.avisos[1])
        self.assertEqual(P.ler_falhas("okx"), {"seguidas": 0, "avisado": False})

    def test_so_publica_ficheiros_presentes_e_nunca_corre_o_agente(self):
        g = GitFalso(falhas=0)
        self.pub(g)
        add = [a for a in g.chamadas if a[0] == "add"][0]
        self.assertEqual(add, ("add", "okx.json"))                     # o cofre nao existe: nao e inventado
        self.assertFalse(any("okx_agente" in " ".join(a) for a in g.chamadas))

    def test_url_com_credencial_nao_aparece_no_registo(self):
        g = GitFalso(falhas=99)
        with mock.patch("builtins.print") as pr:
            self.pub(g)
        texto = " ".join(str(c) for c in pr.call_args_list)
        self.assertNotIn("SEGREDO", texto)


class Recuperar(Base):
    def test_usa_a_copia_local_mais_recente(self):
        self.pub(GitFalso(falhas=99))                                  # volta de t=200 nao publicada
        json.dump({"volta": {"t": 100}}, open(os.path.join(self.pasta, "okx.json"), "w"))   # ramo ficou em t=100
        self.assertTrue(P.recuperar(self.pasta, "okx", "okx.json"))
        self.assertEqual(json.load(open(os.path.join(self.pasta, "okx.json")))["volta"]["t"], 200)

    def test_ignora_copia_mais_antiga(self):
        self.pub(GitFalso(falhas=99))
        json.dump({"volta": {"t": 300}}, open(os.path.join(self.pasta, "okx.json"), "w"))
        self.assertFalse(P.recuperar(self.pasta, "okx", "okx.json"))
        self.assertEqual(json.load(open(os.path.join(self.pasta, "okx.json")))["volta"]["t"], 300)

    def test_copia_ilegivel_nunca_substitui(self):
        open(os.path.join(P.pasta_local("okx"), "okx.json"), "w").write("{partido")
        self.assertFalse(P.recuperar(self.pasta, "okx", "okx.json"))

    def test_sem_estado_publicado_usa_a_copia(self):
        self.pub(GitFalso(falhas=99))
        os.remove(os.path.join(self.pasta, "okx.json"))
        self.assertTrue(P.recuperar(self.pasta, "okx", "okx.json"))

    def test_estado_recuperado_evita_mensagens_repetidas(self):
        # o estado recuperado traz os avisos ja enviados: o agente nao os volta a mandar
        json.dump({"volta": {"t": 200}, "real": {"avisados": ["p:HUMA:1"], "colocados": ["HUMA:1"]}},
                  open(os.path.join(self.pasta, "okx.json"), "w"))
        self.pub(GitFalso(falhas=99))
        json.dump({"volta": {"t": 100}, "real": {}}, open(os.path.join(self.pasta, "okx.json"), "w"))
        P.recuperar(self.pasta, "okx", "okx.json")
        st = json.load(open(os.path.join(self.pasta, "okx.json")))
        self.assertIn("p:HUMA:1", st["real"]["avisados"])
        self.assertIn("HUMA:1", st["real"]["colocados"])


class Revisao(Base):
    """(11/11, revisao adversarial)"""

    def test_ramo_mudou_desde_a_falha_descarta_a_copia(self):
        with mock.patch.dict(os.environ, {"ESTADO_SHA_BASE": "aaa"}):
            self.pub(GitFalso(falhas=99))
        json.dump({"volta": {"t": 100}}, open(os.path.join(self.pasta, "okx.json"), "w"))
        self.assertFalse(P.recuperar(self.pasta, "okx", "okx.json", sha_atual="bbb"))
        self.assertEqual(json.load(open(os.path.join(self.pasta, "okx.json")))["volta"]["t"], 100)

    def test_ramo_igual_ao_da_falha_recupera(self):
        with mock.patch.dict(os.environ, {"ESTADO_SHA_BASE": "aaa"}):
            self.pub(GitFalso(falhas=99))
        json.dump({"volta": {"t": 100}}, open(os.path.join(self.pasta, "okx.json"), "w"))
        self.assertTrue(P.recuperar(self.pasta, "okx", "okx.json", sha_atual="aaa"))

    def test_sucesso_apaga_tambem_um_cofre_antigo_que_nesta_volta_nao_existe(self):
        open(os.path.join(self.pasta, "cofre_okx.json"), "w").write("{}")
        self.pub(GitFalso(falhas=99))                                   # volta falhada com cofre
        os.remove(os.path.join(self.pasta, "cofre_okx.json"))
        self.pub(GitFalso(falhas=0))                                    # volta boa sem cofre
        self.assertEqual(sorted(os.listdir(P.pasta_local("okx"))), ["falhas.json"])


class Workflow(unittest.TestCase):
    def test_agente_okx_usa_publicacao_e_recuperacao(self):
        y = open(os.path.join(os.path.dirname(__file__), "..", ".github", "workflows", "okx-agente.yml")).read()
        self.assertIn("publicar_estado.py recuperar /tmp/okx okx okx.json", y)
        self.assertIn("publicar_estado.py publicar /tmp/okx okx okx.json cofre_okx.json", y)
        self.assertLess(y.index("recuperar /tmp/okx"), y.index("python3 tools/okx_agente.py"))   # recupera ANTES do agente
        self.assertNotIn("git push -q -f", y)

    def test_publicacao_num_passo_que_corre_sempre(self):
        y = open(os.path.join(os.path.dirname(__file__), "..", ".github", "workflows", "okx-agente.yml")).read()
        i = y.index("- name: Publicar o estado")
        self.assertIn("if: always()", y[i:i + 200])
        self.assertIn('if [ ! -s /tmp/okx/okx.json ]', y[i:])

    def bloco_de_leitura(self):
        y = open(os.path.join(os.path.dirname(__file__), "..", ".github", "workflows", "okx-agente.yml")).read().split("\n")
        a = next(k for k, l in enumerate(y) if "rm -rf /tmp/okx" in l)
        b = next(k for k, l in enumerate(y) if "publicar_estado.py recuperar" in l)
        ind = len(y[a]) - len(y[a].lstrip())
        return "\n".join(l[ind:] for l in y[a:b])

    def correr_leitura(self, rc_ls, fetch_ok=True):
        import subprocess
        import stat
        d = tempfile.mkdtemp()
        g = os.path.join(d, "git")
        open(g, "w").write(f"""#!/bin/bash
case "$1" in
  ls-remote) exit {rc_ls};;
  fetch) {'exit 0' if fetch_ok else 'exit 128'};;
  show) echo '{{"volta": {{"t": 1}}}}';;
  rev-parse) echo abc123;;
esac
""")
        os.chmod(g, os.stat(g).st_mode | stat.S_IEXEC)
        corpo = self.bloco_de_leitura().replace("/tmp/okx", os.path.join(d, "okx")) + "\necho LEITURA_OK\n"
        r = subprocess.run(["bash", "-e", "-c", corpo], capture_output=True, text=True,
                           env={**os.environ, "PATH": d + ":" + os.environ["PATH"]})
        return r, d

    def test_ramo_existe_e_le(self):
        r, d = self.correr_leitura(0)
        self.assertIn("LEITURA_OK", r.stdout)
        self.assertEqual(open(os.path.join(d, "okx", ".sha_base")).read().strip(), "abc123")

    def test_primeira_volta_sem_ramo(self):
        r, _ = self.correr_leitura(2)
        self.assertIn("LEITURA_OK", r.stdout)

    def test_erro_de_rede_cancela_a_volta_em_vez_de_partir_vazio(self):
        for rc, ok in ((128, True), (0, False)):
            r, d = self.correr_leitura(rc, fetch_ok=ok)
            self.assertNotIn("LEITURA_OK", r.stdout)
            self.assertNotEqual(r.returncode, 0)
            self.assertFalse(os.path.exists(os.path.join(d, "okx", "okx.json")))


if __name__ == "__main__":
    unittest.main()
