"""(06/11, OK do Rui) scan.yml: o agente OKX e o vigia sao lancados uma vez por hora no primeiro ciclo entre
hh:07 e hh:30, e nao so no minuto hh:07 (que um scan demorado das hh:05 fazia saltar: 05/11, 3 h 45 min parado).
Simula o bloco real do ficheiro em bash, com gh e python3 falsos."""
import os
import re
import shutil
import subprocess
import unittest

YML = os.path.join(os.path.dirname(__file__), "..", ".github", "workflows", "scan.yml")


def bloco(nome="okx"):
    with open(YML, encoding="utf-8") as f:
        s = f.read()
    m = re.search(rf"# >>> lancamento-{nome}\n(.*?)\n\s*# <<< lancamento-{nome}", s, re.S)
    # o relogio vem da simulacao, nao de date
    return m.group(1).replace("${{ github.repository }}", "dono/repo").replace("NOW=$(date +%s); ", "") if m else None


@unittest.skipUnless(shutil.which("bash"), "sem bash")
class LancamentoOKX(unittest.TestCase):
    def correr(self, tempos, falha_gh=(), nome="okx"):
        """Corre o bloco para cada NOW (segundos); devolve os NOW em que o agente foi lancado e o vigia correu."""
        script = ("LOG=\"\"\n"
                  "gh() { if [ -n \"$FALHA\" ] && echo \" $FALHA \" | grep -q \" $NOW \"; then return 1; fi; LOG=\"$LOG agente:$NOW\"; }\n"
                  "timeout() { LOG=\"$LOG vigia:$NOW\"; }\n"
                  f"for NOW in {' '.join(map(str, tempos))}; do\n{bloco(nome)}\ndone\necho $LOG\n")
        env = dict(os.environ, FALHA=" ".join(map(str, falha_gh)))
        out = subprocess.run(["bash", "-c", script], capture_output=True, text=True, timeout=20, env=env).stdout.split()
        return ([int(x.split(":")[1]) for x in out if x.startswith("agente:")],
                [int(x.split(":")[1]) for x in out if x.startswith("vigia:")])

    def test_bloco_existe_e_sem_janela_de_um_minuto(self):
        self.assertIsNotNone(bloco())
        with open(YML, encoding="utf-8") as f:
            self.assertNotIn("-lt 480", f.read())

    def test_scan_demorado_ja_nao_salta_a_hora(self):
        h = 3600 * 500000
        # ciclos as hh:05:05, hh:08:05 (o minuto hh:07 foi saltado), hh:09:05, hh:31:05 e na hora seguinte
        ag, vi = self.correr([h + 305, h + 485, h + 545, h + 1865, h + 3600 + 305, h + 3600 + 425, h + 3600 + 485])
        self.assertEqual(ag, [h + 485, h + 3600 + 425])
        self.assertEqual(vi, ag)

    def test_uma_vez_por_hora_mesmo_com_ciclos_de_minuto(self):
        h = 3600 * 500000
        ag, _ = self.correr([h + s for s in range(5, 3600, 60)])
        self.assertEqual(len(ag), 1)

    def test_falha_do_gh_tenta_no_ciclo_seguinte(self):
        h = 3600 * 500000
        ag, vi = self.correr([h + 425, h + 485, h + 545], falha_gh=[h + 425])
        self.assertEqual(ag, [h + 485])
        self.assertEqual(vi, [h + 425, h + 485])          # o vigia corre na mesma quando o lancamento falha

    def test_depois_das_hh30_nao_lanca(self):
        h = 3600 * 500000
        ag, _ = self.correr([h + 1805, h + 3000])
        self.assertEqual(ag, [])


    # (06/11, OK do Rui) a arena tinha a mesma janela de um minuto (hh:23); 05/11 23h ficou sem combate
    def test_arena_uma_vez_por_hora_entre_hh23_e_hh50(self):
        self.assertIsNotNone(bloco("arena"))
        with open(YML, encoding="utf-8") as f:
            self.assertNotIn("-lt 1440", f.read())
        h = 3600 * 500000
        ag, _ = self.correr([h + 1385, h + 1500, h + 3005, h + 3600 + 1200, h + 3600 + 1505], nome="arena")
        self.assertEqual(ag, [h + 1385, h + 3600 + 1505])          # hh:24:05 saltado o minuto hh:23 -> ainda lanca
        ag, _ = self.correr([h + s for s in range(5, 3600, 60)], nome="arena")
        self.assertEqual(len(ag), 1)
        ag, _ = self.correr([h + 1385, h + 1445], falha_gh=[h + 1385], nome="arena")
        self.assertEqual(ag, [h + 1445])


if __name__ == "__main__":
    unittest.main()
