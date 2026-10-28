"""(28/10, auditoria F1) Depositos e levantamentos so pelos registos da Bybit; perdas nunca somem."""
import unittest

from engine import evolucao, inbox, risco, run


def msg(txt, t=100):
    return [{"message": {"chat": {"id": "admin"}, "date": t, "text": txt}}]


def base(eq=1000.0, t=0):
    st = {}
    evolucao.atualizar(st, eq, t, [], None)
    return st


class Fluxos(unittest.TestCase):
    def test_perda_grande_sem_registo_conta_como_perda_e_trava(self):
        st = base(1000.0, 0)
        evolucao.atualizar(st, 850.0, 3600, [], None, {"ok": True, "lista": []})   # -15% numa hora
        ev = st["evolucao"]
        self.assertEqual(ev["fluxos"], [])
        self.assertEqual(ev["por_confirmar"][-1][1], -150.0)
        self.assertAlmostEqual(ev["g"], -150.0)
        n = risco.nivel(st, 850.0)
        self.assertIn("travão", n["motivo"])                    # o travao ve a perda
        avisos = run.salto_aviso(st)
        self.assertTrue(avisos and "/fluxo -150.00" in avisos[0])
        self.assertEqual(run.salto_aviso(st), [])               # so uma vez

    def test_levantamento_registado_na_bybit_e_fluxo(self):
        st = base(1000.0, 0)
        mv = {"ok": True, "lista": [{"t": 3000, "tipo": "transferência", "sinal": -1, "usd": 300.0}]}
        evolucao.atualizar(st, 700.0, 3600, [], None, mv)
        ev = st["evolucao"]
        self.assertEqual(ev["fluxos"][-1], [3600, -300.0, "bybit"])
        self.assertAlmostEqual(ev["g"], 0.0)
        self.assertNotIn("travão", risco.nivel(st, 700.0)["motivo"])

    def test_deposito_na_funding_e_transferencia_nao_conta_duas_vezes(self):
        st = base(100.0, 0)
        mv = {"ok": True, "lista": [{"t": 3000, "tipo": "depósito", "sinal": 1, "usd": 300.0},
                                    {"t": 3100, "tipo": "transferência", "sinal": 1, "usd": 300.0}]}
        evolucao.atualizar(st, 400.0, 3600, [], None, mv)
        self.assertEqual(st["evolucao"]["fluxos"][-1][1], 300.0)

    def test_sem_permissao_pede_confirmacao_e_fluxo_manual_corrige(self):
        st = base(100.0, 0)
        evolucao.atualizar(st, 400.0, 3600, [], None, {"ok": False, "lista": []})   # deposito sem registo
        self.assertAlmostEqual(st["evolucao"]["g"], 300.0)                           # parece ganho
        inbox.apply(st, msg("/fluxo 300"), "admin")
        ev = st["evolucao"]
        self.assertEqual(ev["fluxos"][-1], [3600, 300.0, "manual"])
        self.assertAlmostEqual(ev["g"], 0.0)
        self.assertEqual(ev["por_confirmar"], [])
        q = evolucao.nav_queda(ev, 400.0)
        self.assertAlmostEqual(q[0], 0.0, places=6)

    def test_variacao_pequena_nao_e_fluxo_nem_pergunta(self):
        st = base(1000.0, 0)
        evolucao.atualizar(st, 990.0, 3600, [], None, {"ok": True, "lista": []})
        self.assertEqual(st["evolucao"]["fluxos"], [])
        self.assertFalse(st["evolucao"].get("por_confirmar"))


if __name__ == "__main__":
    unittest.main()
