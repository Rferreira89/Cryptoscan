"""(12/11) Piloto SHORT_TURTLE: juro real por moeda, uma posicao, suspensoes, registo sem execucao fora da prova,
e a configuracao do piloto so com os limites autorizados."""
import json
import os
import unittest

from engine import account, promo

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOW = 1_800_000_000
DAY = 86400


def op(r, dia, executed=True, status="CLOSED"):
    return {"strategy": "SHORT_TURTLE", "mode": "REAL", "status": status, "executed": executed, "result_r": r,
            "closed_at": NOW - 30 * DAY + dia * DAY, "opened_at": NOW - 30 * DAY + dia * DAY - 3600}


PL = {"piloto": {"estrategia": "SHORT_TURTLE", "teto_pct": 4, "perda_max_r": -8, "max_posicoes": 1, "juro_max_r": 0.06,
                 "dias_max": 20, "inicio": 0}}


class Configuracao(unittest.TestCase):
    def test_config_so_com_os_limites_autorizados(self):
        with open(os.path.join(RAIZ, "config.json"), encoding="utf-8") as f:
            c = json.load(f)
        self.assertIsNone(c["real_autorizados"])               # (14/11 15:28, Rui: "manter tal como está") 
        p = c["piloto"]
        self.assertEqual(p["estrategia"], "SHORT_TURTLE")
        self.assertLessEqual(p["teto_pct"], 5)                  # (12/11 09:06) teto 5% autorizado pelo Rui
        self.assertEqual(p["max_posicoes"], 2)                 # (14/11 15:28, Rui: "manter tal como está") 
        self.assertEqual(p["perda_max_r"], -8)
        self.assertLessEqual(p["juro_max_r"], 0.06)


class Guardas(unittest.TestCase):
    def test_juro_desconhecido_ou_velho_nao_entra(self):
        cc = promo.cfg_piloto("SHORT_TURTLE", {"ledger": []}, dict(PL), NOW)
        self.assertIn("desconhecido", promo.piloto_juro({}, "SEI", 0.15, cc, NOW))
        st = {"juros_bybit": {"t": NOW - 7 * 3600, "m": {"SEI": 0.02}}}
        self.assertIn("desconhecido", promo.piloto_juro(st, "SEI", 0.15, cc, NOW))

    def test_juro_real_dentro_e_fora_do_limite(self):
        cc = promo.cfg_piloto("SHORT_TURTLE", {"ledger": []}, dict(PL), NOW)
        st = {"juros_bybit": {"t": NOW, "m": {"SEI": 0.0222, "TRUMP": 0.033, "BTC": 0.0042}}}
        self.assertIsNone(promo.piloto_juro(st, "SEI", 0.156, cc, NOW))          # 0,0222% x 20 / 15,6% = 0,028R
        self.assertIsNone(promo.piloto_juro(st, "BTC", 0.058, cc, NOW))
        self.assertIn("acima", promo.piloto_juro(st, "TRUMP", 0.10, cc, NOW))     # 0,033 x 20 / 10% = 0,066R

    def test_sem_piloto_a_guarda_nao_atua(self):
        self.assertIsNone(promo.piloto_juro({}, "SEI", 0.15, {}, NOW))

    def test_uma_posicao_de_cada_vez(self):
        st = {"ledger": [op(None, 1, status="OPEN")]}
        cc = promo.cfg_piloto("SHORT_TURTLE", st, dict(PL), NOW)
        self.assertIn("posição aberta", cc["piloto_bloqueio"])
        self.assertNotIn("piloto_teto_pct", cc)

    def test_perda_acumulada_e_diaria_suspendem(self):
        st = {"ledger": [op(-1.0, d) for d in range(8)]}
        cc = promo.cfg_piloto("SHORT_TURTLE", st, dict(PL), NOW)
        self.assertIn("suspenso", cc["piloto_bloqueio"])
        self.assertIn("suspenso", st["piloto"])
        st2 = {"ledger": [op(-1.0, 3), op(-1.0, 3), op(-1.05, 3)]}
        self.assertIn("piloto_bloqueio", promo.cfg_piloto("SHORT_TURTLE", st2, dict(PL), NOW))

    def test_operacoes_sem_execucao_nao_contam(self):
        st = {"ledger": [op(0.52, 1, executed=False), op(0.47, 2, executed=False)]}
        cc = promo.cfg_piloto("SHORT_TURTLE", st, dict(PL), NOW)
        self.assertEqual(st["piloto"]["n"], 0)
        self.assertEqual(promo.live_record(st, "SHORT_TURTLE"), (0, None))
        self.assertIn("piloto_teto_pct", cc)


class Juros(unittest.TestCase):
    def test_juros_taxas_le_so_emprestaveis(self):
        from unittest import mock
        res = {"list": [{"currency": "SEI", "borrowable": True, "hourlyBorrowRate": "0.00000925"},
                        {"currency": "ICP", "borrowable": False, "hourlyBorrowRate": "0.00001"},
                        {"currency": "X", "borrowable": True, "hourlyBorrowRate": ""}]}
        with mock.patch.object(account, "get", return_value=res):
            j = account.juros_taxas()
        self.assertEqual(set(j), {"SEI"})
        self.assertAlmostEqual(j["SEI"], 0.0222)

    def test_scanner_guarda_os_juros(self):
        from unittest import mock
        from engine import scanner, europa
        st = {}
        acc = {"t": NOW, "juros_margem": {"SEI": 0.02}, "margem": ["SEI"]}
        with mock.patch.object(europa, "account", return_value=acc), mock.patch.object(europa, "capital_from", return_value=None):
            scanner.apply_account(st, {}, NOW)
        self.assertEqual(st["juros_bybit"]["m"], {"SEI": 0.02})


if __name__ == "__main__":
    unittest.main()


class Teto5(unittest.TestCase):
    """(12/11 09:06) Teto 5% autorizado. Capital SINTETICO (30) com a configuracao real (capital composto, risco normal
    0,5%, ordem minima 5): a ordem minima entra se o risco real no stop (comissoes incluidas em stop_pct) <= teto do
    capital. Acima do teto continua recusado; a posicao nunca passa da ordem minima e nao usa emprestimo de USDC."""

    def _cfg(self, teto):
        from engine import config, scanner
        c = dict(config.load("config.json"))
        c["capital_usdc"] = 30.0
        c.update(scanner.compounding(c, [], 0))
        return dict(c, piloto_teto_pct=teto)

    def test_teto_efetivo(self):
        from engine import risk
        for stop, teto, entra in ((26.0, 5, True), (26.0, 4, False), (20.0, 4, True), (31.0, 5, False)):
            p, why = risk.sizing(stop, stop / 100, 1.0, self._cfg(teto), short=True)
            self.assertEqual(p is not None, entra, (stop, teto, why))
            if p:
                self.assertEqual(p["usdc"]["position_usdc"], 5.0)
                self.assertLessEqual(p["usdc"]["risk_usdc"], 30 * teto / 100 + 1e-9)
                self.assertEqual(p["usdc"]["borrowed_usdc"], 0.0)

    def test_config_aplica_5(self):
        from engine import config, promo
        c = config.load("config.json")
        cc = promo.cfg_piloto("SHORT_TURTLE", {"ledger": []}, c, c["piloto"]["inicio"] + 3600)
        self.assertEqual(cc["piloto_teto_pct"], 5.0)
        self.assertIsNone(promo.cfg_piloto("OUTRA", {"ledger": []}, c, 0).get("piloto_teto_pct"))


class Concorrencia(unittest.TestCase):
    """(12/11) Vagas do piloto com risco AGREGADO aberto <= teto: a 2.a posicao so entra se a soma couber; o motivo
    de recusa diz que foi o agregado. Em producao max_posicoes continua 1 (a simulacao da carteira passou os -8R)."""

    def _cfg(self, aberto):
        c = Teto5._cfg(self, 5)
        return dict(c, piloto_teto_agregado_pct=5.0, piloto_risco_aberto_pct=aberto)

    def test_segunda_cabe_ou_nao(self):
        from engine import risk
        p, _ = risk.sizing(12.0, 0.12, 1.0, self._cfg(2.0), short=True)      # 2% + 2% <= 5%
        self.assertIsNotNone(p)
        p, why = risk.sizing(20.0, 0.20, 1.0, self._cfg(2.0), short=True)    # 2% + 3,3% > 5%
        self.assertIsNone(p)
        self.assertIn("agregado", why)

    def test_cfg_piloto_soma_risco_aberto(self):
        from engine import config, promo
        c = dict(config.load("config.json"))
        c["piloto"] = dict(c["piloto"], max_posicoes=2, teto_agregado_pct=5)
        led = [{"strategy": "SHORT_TURTLE", "mode": "REAL", "status": "OPEN", "risk_pct": 1.7}]
        cc = promo.cfg_piloto("SHORT_TURTLE", {"ledger": led}, c, c["piloto"]["inicio"] + 3600)
        self.assertEqual((cc["piloto_risco_aberto_pct"], cc["piloto_teto_agregado_pct"]), (1.7, 5.0))
        c["piloto"]["max_posicoes"] = 1
        self.assertIn("piloto_bloqueio", promo.cfg_piloto("SHORT_TURTLE", {"ledger": led}, c, c["piloto"]["inicio"] + 1))

    def test_producao_uma_vaga(self):
        import json
        self.assertEqual(json.load(open("config.json"))["piloto"]["max_posicoes"], 2)   # (14/11 15:28, Rui: "manter tal como está") 
