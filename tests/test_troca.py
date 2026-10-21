import unittest
from engine import troca, promo

DIA = 86400
NOW = 1_800_000_000


def rel(atual, novo):
    return {"acaso": {"lateral": {"testes": 10}}, "fases": {"lateral": {"atual": atual, "novo": novo}}}


class TrocaAutomatica(unittest.TestCase):
    def estado(self, r_a, r_n):
        lut = {"A": {"recentes": []}, "N": {"recentes": []}}
        st = {"arena": {"longo": {"lutadores": lut}}}
        t0 = NOW - 30 * DIA
        for d in range(25):
            troca.registar(st, rel(["A"], ["N"]), "lateral", t0 + d * DIA)
            for j in range(2):                                # 2 operacoes por dia para a frente
                lut["A"]["recentes"].append([t0 + (d + 1) * DIA + j * 3600 + 100, r_a])
                lut["N"]["recentes"].append([t0 + (d + 1) * DIA + j * 3600 + 200, r_n])
        return st

    def test_troca_so_com_dados_e_margem(self):
        st = self.estado(0.1, 0.4)
        msg = troca.decidir(st, NOW)
        self.assertIn("filtro novo", msg)
        self.assertEqual(st["troca_filtro"]["ativo"], "novo")
        self.assertIsNone(troca.decidir(st, NOW))               # nao repete
        st2 = self.estado(0.1, 0.12)                             # diferenca abaixo da margem: fica
        self.assertIsNone(troca.decidir(st2, NOW))
        self.assertEqual(st2["troca_filtro"]["ativo"], "atual")

    def test_sem_dias_suficientes_ou_novo_vazio_fica_o_atual(self):
        st = {"arena": {"longo": {"lutadores": {"A": {"recentes": [[NOW - DIA, 1.0]]}}}}}
        for d in range(5):
            troca.registar(st, rel(["A"], []), "lateral", NOW - (10 - d) * DIA)
        self.assertIsNone(troca.decidir(st, NOW))
        self.assertIsNone(troca.registar({}, {"fases": {}}, "lateral", NOW).get("medicao"))

    def test_com_o_novo_ativo_so_entram_os_que_passam_o_novo(self):
        lr = lambda pn: {"por_regime": {"lateral": {"n": 30, "avg_r": .4, "acaso_p95": .1, "metades": [.3, .5], "passa_novo": pn}}}
        st = {"arena": {"longo": {"lutadores": {"X": lr(True), "Y": lr(False)}}}}
        self.assertEqual(sorted(k for k, _ in promo.regime_qualified(st, "lateral")), ["X", "Y"])
        st["troca_filtro"] = {"ativo": "novo"}
        self.assertEqual([k for k, _ in promo.regime_qualified(st, "lateral")], ["X"])


if __name__ == "__main__":
    unittest.main()
