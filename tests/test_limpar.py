"""(27/10) /limpar: operacoes fechadas fora do programa e travao a descontar levantamentos."""
import unittest

from engine import inbox, promo, risco, ledger


def msg(txt, t=100):
    return [{"message": {"chat": {"id": "admin"}, "date": t, "text": txt}}]


class Limpar(unittest.TestCase):
    def st(self):
        return {"ledger": [{"id": "SEI-SHORT_TURTLE-1", "asset": "SEI", "kind": "4H", "mode": "REAL",
                            "status": "OPEN", "executed": True, "strategy": "SHORT_TURTLE",
                            "issued_at": risco.DESDE + 10, "result_r": None}],
                "nucleo": {"pos": {}, "pedidos": {"BTC": 5}},
                "risco": {"pico": 366.19},
                "evolucao": {"fluxos": [[10, 110.0], [50, -120.55], [60, -108.21], [70, -119.45]]}}

    def test_limpar_liberta_e_nao_conta(self):
        st = self.st()
        inbox.apply(st, msg("/limpar desde 40"), "admin")
        r = st["ledger"][0]
        self.assertTrue(r["fora_programa"])
        self.assertEqual(promo.family_open(st), {})
        self.assertIn("SEI-SHORT_TURTLE-1", ledger.declined(st)[0])
        r.update(status="CLOSED", result_r=1.5)              # o sinal fecha mais tarde em papel
        self.assertEqual(risco.prova(st["ledger"]), (0, 0))
        self.assertEqual(st["nucleo"]["pedidos"], {})

    def test_travao_desconta_levantamentos(self):
        st = self.st()
        inbox.apply(st, msg("/limpar desde 40"), "admin")
        n = risco.nivel(st, 0.87)
        self.assertAlmostEqual(st["risco"]["pico"], 17.98, places=2)   # 366,19 - 348,21
        n = risco.nivel(st, 300.87 + 0)                                  # sem deposito registado: novo pico
        st2 = self.st(); inbox.apply(st2, msg("/limpar desde 40"), "admin"); risco.nivel(st2, 0.87)
        st2["evolucao"]["fluxos"].append([80, 300.0])
        n = risco.nivel(st2, 300.87)
        self.assertLess(n["dd"], 0.10)                                   # deposito nao e ganho nem perda
        self.assertNotIn("travão", n["motivo"])

    def test_sem_marcador_nao_reaplica_historico(self):
        st = self.st()
        risco.nivel(st, 350.0)
        self.assertEqual(st["risco"]["pico"], 366.19)


if __name__ == "__main__":
    unittest.main()


class PicoManual(unittest.TestCase):
    def test_pico_corrigido(self):
        st = {"ledger": [], "risco": {"pico": 120.55},
              "evolucao": {"fluxos": [[50, -120.55], [70, -119.45]]}}
        inbox.apply(st, msg("/limpar pico 17.98"), "admin")
        risco.nivel(st, 0.87)
        self.assertEqual(st["risco"]["pico"], 17.98)
        st["evolucao"]["fluxos"].append([90, 300.0])
        n = risco.nivel(st, 300.87)
        self.assertEqual(st["risco"]["pico"], 317.98)
        self.assertLess(n["dd"], 0.10)
