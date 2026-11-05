"""(05/11) TF-SHORT U2 em papel (preparacao isolada): regra, stop, tamanho, minimos, limites, financiamento e
garantia de que o modulo nao tem acesso a ordens."""
import unittest
from tools import okx_tfshort as T

DAY = 86400


def velas(fechos, usd=30e6, t0=0):
    return [{"t": t0 + k * DAY, "o": c, "h": c * 1.01, "l": c * 0.99, "c": c, "usd": usd} for k, c in enumerate(fechos)]


INFO = {"ctVal": 1.0, "minSz": 0.01, "lotSz": 0.01}


def desce(n=240, p0=100.0, passo=0.003):
    out, p = [], p0
    for k in range(n):                                   # queda com ruido (vol diaria ~2%)
        p *= (1 - passo) * (1.02 if k % 2 else 0.98)
        out.append(p)
    return out


class Regra(unittest.TestCase):
    def test_estado_medias(self):
        self.assertIsNone(T.estado_medias([1.0] * 199))
        self.assertEqual(T.estado_medias([float(k) for k in range(1, 260)]), 4)
        self.assertEqual(T.estado_medias([float(k) for k in range(260, 1, -1)]), 0)

    def test_peso_e_teto(self):
        self.assertAlmostEqual(T.peso(0.05), 0.05)
        self.assertEqual(T.peso(0.001), 1.0)
        self.assertEqual(T.peso(0), 0.0)

    def test_tamanho_arredonda_para_baixo_e_respeita_minimo(self):
        n, nom, mn, cabe = T.tamanho(20.0, 0.05, 10.0, INFO)       # alvo 1 USD -> 0.10 contrato
        self.assertAlmostEqual(n, 0.1); self.assertTrue(cabe)
        self.assertFalse(T.tamanho(20.0, 0.05, 10.0, {"ctVal": 1.0, "minSz": 1.0, "lotSz": 1.0})[3])

    def test_r_short_com_custos_e_financiamento(self):
        R, ret = T.r_op(100.0, 90.0, 0.05, 0.001)
        self.assertAlmostEqual(ret, 0.10 - 2 * T.CUSTO + 0.001, places=5)
        self.assertAlmostEqual(R, round(ret / 0.10, 3))


class Volta(unittest.TestCase):
    def test_entra_em_queda_e_sai_quando_volta_a_subir(self):
        f = desce(); st = {}
        dados = {"AAA": {"velas": velas(f), "px": f[-1], "fund": []}}
        ev = T.correr(st, dados, 240 * DAY, {"AAA": INFO})
        self.assertIn("AAA", st["conta"]["abertas"]); self.assertIn("AAA", st["sinais"]["abertas"])
        self.assertTrue(any(e[1] == "entrada" for e in ev))
        sobe = f + [f[-1] * (1.01 ** k) for k in range(1, 120)]
        T.correr(st, {"AAA": {"velas": velas(sobe), "px": sobe[-1], "fund": [(250 * DAY, 0.0001)]}}, 360 * DAY, {"AAA": INFO})
        fe = st["sinais"]["fechadas"]
        self.assertEqual(len(fe), 1); self.assertIn(fe[0]["motivo"], ("regra", "stop"))

    def test_stop_de_protecao_e_espera_pela_saida_da_regra(self):
        f = desce(); st = {}
        T.correr(st, {"AAA": {"velas": velas(f), "px": f[-1], "fund": []}}, 240 * DAY, {"AAA": INFO})
        stop = st["conta"]["abertas"]["AAA"]["stop"]
        f2 = f + [stop * 1.02]                                          # salto acima do stop, medias ainda em baixo
        T.correr(st, {"AAA": {"velas": velas(f2), "px": stop * 1.02, "fund": []}}, 241 * DAY, {"AAA": INFO})
        self.assertEqual(st["conta"]["fechadas"][0]["motivo"], "stop")
        self.assertIn("AAA", st["parados"])
        T.correr(st, {"AAA": {"velas": velas(f2 + [f[-1]]), "px": f[-1], "fund": []}}, 242 * DAY, {"AAA": INFO})
        self.assertNotIn("AAA", st["conta"]["abertas"])                 # nao reentra antes de s >= 3

    def test_maximo_cinco_posicoes_e_bruta(self):
        f = desce(); st = {}
        dados = {f"C{k:02d}": {"velas": velas(f), "px": f[-1], "fund": []} for k in range(8)}
        T.correr(st, dados, 240 * DAY, {a: INFO for a in dados})
        C = st["conta"]
        self.assertLessEqual(len(C["abertas"]), 5)
        self.assertLessEqual(sum(p["w"] for p in C["abertas"].values()), 0.5 + 1e-9)
        self.assertEqual(len(st["sinais"]["abertas"]), 8)                # o registo de sinais nao tem limites
        self.assertTrue(C["ignoradas"])

    def test_abaixo_do_minimo_nao_entra(self):
        f = desce(); st = {}
        T.correr(st, {"AAA": {"velas": velas(f), "px": f[-1], "fund": []}}, 240 * DAY, {"AAA": {"ctVal": 100.0, "minSz": 1, "lotSz": 1}})
        self.assertEqual(st["conta"]["abertas"], {})
        self.assertEqual(st["conta"]["ignoradas"][0]["motivo"], "abaixo_minimo")

    def test_exclui_btc_eth_sol_e_iliquidas(self):
        f = desce(); st = {}
        dados = {"BTC": {"velas": velas(f), "px": f[-1], "fund": []}, "ILQ": {"velas": velas(f, usd=1e6), "px": f[-1], "fund": []}}
        T.correr(st, dados, 240 * DAY, {"BTC": INFO, "ILQ": INFO})
        self.assertEqual(st["sinais"]["abertas"], {})

    def test_resumo_30_operacoes(self):
        st = {"conta": {"fechadas": [{"R": 0.1, "motivo": "regra"}] * 30, "abertas": {}}, "sinais": {"fechadas": [], "abertas": {}}}
        self.assertTrue(T.resumo(st)["pronto_para_avaliar"])


class SemOrdens(unittest.TestCase):
    def test_modulo_nao_tem_chave_nem_ordens(self):
        src = open(T.__file__, encoding="utf-8").read()
        for proibido in ("/api/v5/trade", "/api/v5/account", "OKX_API", "privado(", "set-leverage"):
            self.assertNotIn(proibido, src)


if __name__ == "__main__":
    unittest.main()


class Ensaio(unittest.TestCase):
    def test_relatorio_universo_minimos_e_falhas(self):
        f = desce()
        dados = {"AAA": {"velas": velas(f), "px": f[-1], "fund": [(1, 0.0001)]},
                 "BBB": {"velas": velas(f[:100]), "px": f[99], "fund": []},
                 "CCC": {"velas": velas(f, usd=1e6), "px": f[-1], "fund": []},
                 "DDD": {"velas": velas(f), "px": f[-1] * 1.05, "fund": []}}
        infos = {a: INFO for a in ("AAA", "BBB", "CCC", "DDD", "EEE", "BTC")}
        r = T.ensaio(dados, infos)
        self.assertEqual(r["xperps_cripto"], 6); self.assertEqual(r["excluidas"], ["BTC"])
        self.assertEqual(r["sem_velas_globais"], ["EEE"]); self.assertEqual(r["historia_curta"], ["BBB"])
        self.assertEqual(r["iliquidas"], 1); self.assertEqual(r["elegiveis"], 2)
        self.assertEqual(r["sinais_hoje"], 2)
        self.assertTrue(any("DDD" in x and "difere" in x for x in r["falhas"]))
        self.assertTrue(any("DDD" in x and "financiamento" in x for x in r["falhas"]))
        self.assertFalse(any(x.startswith("AAA") for x in r["falhas"]))
