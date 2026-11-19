"""(19/11, evolucao continua) piloto_publico.json vai para o repositorio PUBLICO: o motivo "tamanho minimo ... (livre
depois das N posicoes abertas: risco X, nocional Y)" levava X e Y em USDC. Agora sai em % do orcamento, e os motivos
antigos que ainda estao no estado sao limpos na publicacao."""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import piloto_okx as P  # noqa: E402

CFG = json.load(open(P.CFG_FICHEIRO))


class TestSemValores(unittest.TestCase):
    def test_limpa_motivo_antigo(self):
        m = ("tamanho minimo (0.01 contratos) passaria o risco ou o nocional autorizados "
             "(livre depois das 1 posicoes abertas: risco 0.0240, nocional 14.28)")
        out = P.sem_valores(m)
        self.assertNotIn("0.0240", out)
        self.assertNotIn("14.28", out)
        self.assertIn("risco (valor omitido)", out)
        self.assertIn("tamanho minimo (0.01 contratos)", out)     # o resto do motivo fica

    def test_percentagens_e_outros_textos_ficam(self):
        for m in ("spread 0.768% acima de 0.3% (liquidez)", "risco 3% do orcamento, nocional 29% do orcamento",
                  "chegou 134 min depois do fecho da vela (maximo 60)", "precisaria de 12x (maximo autorizado 10x)"):
            self.assertEqual(P.sem_valores(m), m)
        self.assertIsNone(P.sem_valores(None))

    def test_dimensionar_motivo_em_percentagem(self):
        c = dict(CFG)
        inst = {"ctVal": "1", "ctMult": "1", "ctValCcy": "AAA", "lotSz": "1", "minSz": "1000", "lever": "20"}
        pl = {"entrada": 1.0, "stop": 0.95, "lado": "LONG"}
        orc = {"abertas": 1, "risco_livre": c["risco_max_op"] * 0.25, "nocional_livre": c["nocional_max"] * 0.5,
               "margem_livre": 1.0}
        n, motivo = P.dimensionar(pl, inst, c, 0.05, orc=orc)
        self.assertIsNone(n)
        self.assertIn("tamanho minimo", motivo)
        self.assertIn("risco 25% do orcamento", motivo)
        self.assertIn("nocional 50% do orcamento", motivo)
        self.assertNotIn(f"{orc['risco_livre']:.4f}", motivo)

    def test_publico_limpa_estado_antigo(self):
        m = "tamanho minimo (1 contratos) passaria o risco (livre depois das 1 posicoes abertas: risco 0.0240, nocional 14.28)"
        st = {"portas": {}, "recusadas_pelo_executor": {}, "bloqueio": None, "suspenso": None, "ops": [],
              "sinais_perdidos": [{"t": 1, "sinal": "x|AAA|1", "motivo": m}],
              "oportunidades": {"x|AAA|1": {"t": 1, "motivo": m, "decisao": "REJEITADA", "margem_livre": 5.0}},
              "eventos": [{"t": 1, "txt": "nota", "motivo": m, "motivos": [m]}]}
        try:
            pub = P.publico(st, CFG, {}, 2)
        except (KeyError, TypeError) as e:     # estado minimo: se faltar algum campo, o teste diz qual
            self.fail(f"estado de teste incompleto: {e!r}")
        texto = json.dumps(pub)
        self.assertNotIn("14.28", texto)
        self.assertNotIn("0.0240", texto)
        self.assertEqual(pub["sinais_perdidos"][0]["sinal"], "x|AAA|1")


if __name__ == "__main__":
    unittest.main()
