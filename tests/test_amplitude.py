import unittest

from engine import amplitude, diretor


def row(a, chg, rsi):
    return {"asset": a, "chg_24h": chg, "analysis": {"4h": {"ok": True, "rsi": rsi}}}


class Amplitude(unittest.TestCase):
    def test_queda_das_altcoins_com_btc_parado(self):
        rows = [row("BTC", -0.8, 45)] + [row(f"A{i}", -7, 33) for i in range(12)] + [row("Z", 1, 50)]
        m = amplitude.medir(rows)
        self.assertEqual(m["estado"], "capitulação geral")       # queda forte >= 40% e RSI mediano < 40
        rows = [row("BTC", -0.5, 50)] + [row(f"A{i}", -4.5, 45) for i in range(12)]
        self.assertEqual(amplitude.medir(rows)["estado"], "queda das altcoins com o BTC parado")
        rows = [row(f"A{i}", 1, 75 if i < 4 else 55) for i in range(12)]
        self.assertEqual(amplitude.medir(rows)["estado"], "euforia")
        self.assertIsNone(amplitude.medir(rows[:5]))              # poucas moedas

    def test_aviso_so_quando_muda(self):
        st = {}
        calma = [row(f"A{i}", 0.5, 50) for i in range(12)]
        queda = [row("BTC", -0.5, 45)] + [row(f"A{i}", -8, 26) for i in range(12)]
        self.assertIsNone(amplitude.aviso(amplitude.atualizar(st, calma, 0)))
        self.assertIn("capitulação", amplitude.aviso(amplitude.atualizar(st, queda, 3600)))
        self.assertIsNone(amplitude.aviso(amplitude.atualizar(st, queda, 7200)))
        self.assertEqual(len(st["amplitude"]["hist"]), 3)

    def test_diretor_mostra_a_amplitude(self):
        diretor.AMPLITUDE = {"estado": "capitulação geral", "queda_forte_pct": 60, "rsi_mediano": 31,
                             "sobrevenda_pct": 30}
        try:
            reps = [{"agente": "X", "condicoes": ["gatilho"], "invalidacao": []}]
            L = diretor.conversation("ENA", {"decision": "LONG", "strategy": "BOUNCE_X30", "plan": {}}, reps, None, [])
            self.assertTrue(any(x["de"] == "Amplitude" and x["tom"] == "favor" for x in L))
        finally:
            diretor.AMPLITUDE = None


class LutadoraAmplitude(unittest.TestCase):
    def test_so_com_capitulacao_geral(self):
        from tools import arena_ringue as AR
        from unittest import mock
        c4 = [{"t": i * 14400, "o": 1, "h": 1, "l": 1, "c": 1} for i in range(10)]
        s0 = {"stop": 0.9, "tp": [1.1], "partials": [100], "breakeven": True, "hold_s": 1}
        with mock.patch.object(AR, "sig_x30", return_value=s0):
            with mock.patch.object(AR, "amplitude_em", return_value=0.30):
                self.assertIsNotNone(AR.sig_amplitude(c4))
            with mock.patch.object(AR, "amplitude_em", return_value=0.10):
                self.assertIsNone(AR.sig_amplitude(c4))

    def test_fracao_em_sobrevenda(self):
        from tools import arena_ringue as AR
        desce = [{"t": i * 14400, "c": 100 - i} for i in range(40)]
        sobe = [{"t": i * 14400, "c": 100 + i} for i in range(40)]
        AR.CTX["bars"] = {**{f"D{i}": desce for i in range(5)}, **{f"S{i}": sobe for i in range(5)}}
        AR.CTX.pop("_amp", None)
        self.assertAlmostEqual(AR.amplitude_em(39 * 14400 + 14400), 0.5)


if __name__ == "__main__":
    unittest.main()
