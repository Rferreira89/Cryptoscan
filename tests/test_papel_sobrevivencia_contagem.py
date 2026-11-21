"""(21/11, OK do Rui) Motor de sobrevivencia do papel: so conta operacoes que o piloto real conseguiria fazer (spread
<= 0,3%), um resultado por acontecimento; o papel continua a simular estrategias bloqueadas (sem dinheiro); uma
estrategia ja bloqueada so volta a ser elegivel para o real com 20+ acontecimentos negociaveis de media positiva."""
import unittest

from tools import autonomo as AU
from tools.hunter import papel as P


def op(b, r, spread, ac="1H@1|BTC+4.0%", t=1):
    return {"b": b, "r": r, "acontecimento": ac, "t_sinal": t, "custos_previstos": {"spread_pct": spread}}


class Contagem(unittest.TestCase):
    def test_acontecimento_de_21_11(self):
        # 6 negociaveis + 26 iliquidas no mesmo acontecimento: um so resultado, so das negociaveis
        ops = [op(f"L{i}", -1.5, 0.1) for i in range(6)] + [op(f"I{i}", -12.0, 3.5) for i in range(26)]
        ra = P.r_por_acontecimento(ops)
        self.assertEqual(ra, [-1.5])
        self.assertTrue(AU.sobrevivencia(ra)["novas_entradas"])          # um acontecimento nao e 32 perdas seguidas

    def test_sem_spread_conhecido_nao_conta(self):
        self.assertFalse(P.negociavel({"custos_previstos": {"spread_pct": None}}))
        self.assertTrue(P.negociavel({"custos_previstos": {"spread_pct": 0.3}}))
        self.assertFalse(P.negociavel({"custos_previstos": {"spread_pct": 0.31}}))

    def test_perdas_reais_seguidas_continuam_a_bloquear(self):
        ops = [op("BTC", -1.0, 0.01, ac=f"a{i}", t=i) for i in range(6)]
        self.assertFalse(AU.sobrevivencia(P.r_por_acontecimento(ops))["novas_entradas"])

    def test_readmissao(self):
        self.assertFalse(P.readmitida([0.5] * 19))
        self.assertFalse(P.readmitida([-0.1] * 25))
        self.assertTrue(P.readmitida([0.2] * 20))

    def test_papel_ja_nao_rejeita_bloqueadas(self):
        import inspect
        self.assertNotIn('rejeita("estrategia bloqueada pelo motor de sobrevivencia")', inspect.getsource(P))


if __name__ == "__main__":
    unittest.main()
