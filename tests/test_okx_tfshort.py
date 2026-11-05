"""(05/11) TF-SHORT U2 em papel (preparacao isolada): regra, stop, tamanho, minimos, limites, financiamento,
universo validado separado, registos independentes, custos sem contagem dupla, qualidade dos dados e garantia de que
o modulo nao tem acesso a ordens."""
import unittest
from tools import okx_tfshort as T

DAY = 86400
INFO = {"ctVal": 1.0, "minSz": 0.01, "lotSz": 0.01}


def velas(fechos, usd=30e6, t0=0):
    return [{"t": t0 + k * DAY, "o": c, "h": c * 1.01, "l": c * 0.99, "c": c, "usd": usd} for k, c in enumerate(fechos)]


def desce(n=240, p0=100.0, passo=0.003):
    out, p = [], p0
    for k in range(n):                                   # queda com ruido (vol diaria ~2%)
        p *= (1 - passo) * (1.02 if k % 2 else 0.98)
        out.append(p)
    return out


def dd(f, px=None, validado=True, fund=None, usd=30e6):
    px = f[-1] if px is None else px
    return {"velas": velas(f, usd=usd), "px": px, "px_global": px, "fund": fund or [], "validado": validado}


NOW = 240 * DAY


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
    def test_entra_em_queda_e_sai_quando_volta_a_subir_com_custos_registados(self):
        f = desce(); st = {}
        ev = T.correr(st, {"AAA": dd(f)}, NOW, {"AAA": INFO})
        self.assertIn("AAA", st["conta"]["abertas"]); self.assertIn("AAA", st["sinais"]["abertas"])
        self.assertTrue(any(e[1] == "entrada" for e in ev))
        self.assertEqual(st["conta"]["capital"], T.CONTA0)              # o custo de entrada so conta no fecho (sem dupla)
        sobe = f + [f[-1] * (1.01 ** k) for k in range(1, 120)]
        T.correr(st, {"AAA": dd(sobe, fund=[(250 * DAY, 0.0001)])}, 360 * DAY, {"AAA": INFO})
        fe = st["conta"]["fechadas"][0]
        self.assertEqual(len(st["sinais"]["fechadas"]), 1)
        for k in ("pnl_usd", "custos_usd", "fund_usd", "R", "motivo"):
            self.assertIn(k, fe)
        self.assertAlmostEqual(st["conta"]["capital"], T.CONTA0 + fe["pnl_usd"], places=3)
        self.assertGreater(fe["fund_usd"], 0)                           # short recebe financiamento positivo

    def test_stop_de_protecao_e_espera_pela_saida_da_regra(self):
        f = desce(); st = {}
        T.correr(st, {"AAA": dd(f)}, NOW, {"AAA": INFO})
        stop = st["conta"]["abertas"]["AAA"]["stop"]
        f2 = f + [stop * 1.02]
        T.correr(st, {"AAA": dd(f2)}, NOW + DAY, {"AAA": INFO})
        self.assertEqual(st["conta"]["fechadas"][0]["motivo"], "stop")
        self.assertIn("AAA", st["parados"])
        T.correr(st, {"AAA": dd(f2 + [f[-1]])}, NOW + 2 * DAY, {"AAA": INFO})
        self.assertNotIn("AAA", st["conta"]["abertas"])

    def test_maximo_cinco_posicoes_e_bruta(self):
        f = desce(); st = {}
        dados = {f"C{k:02d}": dd(f) for k in range(8)}
        T.correr(st, dados, NOW, {a: INFO for a in dados})
        C = st["conta"]
        self.assertLessEqual(len(C["abertas"]), 5)
        self.assertLessEqual(sum(p["w"] for p in C["abertas"].values()), 0.5 + 1e-9)
        self.assertEqual(len(st["sinais"]["abertas"]), 8)
        self.assertTrue(C["ignoradas"])

    def test_abaixo_do_minimo_nao_entra(self):
        f = desce(); st = {}
        T.correr(st, {"AAA": dd(f)}, NOW, {"AAA": {"ctVal": 100.0, "minSz": 1, "lotSz": 1}})
        self.assertEqual(st["conta"]["abertas"], {})
        self.assertEqual(st["conta"]["ignoradas"][0]["motivo"], "abaixo_minimo")

    def test_exclui_btc_eth_sol_e_iliquidas(self):
        f = desce(); st = {}
        T.correr(st, {"BTC": dd(f), "ILQ": dd(f, usd=1e6)}, NOW, {"BTC": INFO, "ILQ": INFO})
        self.assertEqual(st["sinais"]["abertas"], {})


class UniversoValidado(unittest.TestCase):
    def test_nao_validada_so_no_registo_de_sinais(self):
        f = desce(); st = {}
        T.correr(st, {"AAA": dd(f, validado=False), "BBB": dd(f)}, NOW, {"AAA": INFO, "BBB": INFO})
        self.assertIn("AAA", st["sinais"]["abertas"]); self.assertFalse(st["sinais"]["abertas"]["AAA"]["validado"])
        self.assertNotIn("AAA", st["conta"]["abertas"]); self.assertIn("BBB", st["conta"]["abertas"])
        self.assertIn({"moeda": "AAA", "t": NOW, "motivo": "fora_do_universo_validado"}, st["conta"]["ignoradas"])

    def test_volume_binance_desconhecido_conta_como_nao_validado(self):
        f = desce(); st = {}
        d = dd(f); d["validado"] = None
        T.correr(st, {"AAA": d}, NOW, {"AAA": INFO})
        self.assertNotIn("AAA", st["conta"]["abertas"])
        self.assertTrue(any("sem volume da Binance" in x for x in st["qualidade"][-1]["falhas"]))

    def test_resumo_separa_os_tres_registos(self):
        st = {"sinais": {"abertas": {}, "fechadas": [{"R": 1.0, "motivo": "regra", "validado": True}] * 3 +
                         [{"R": -1.0, "motivo": "stop", "validado": False}] * 2},
              "conta": {"capital": 20.5, "abertas": {}, "fechadas": [{"R": 0.5, "motivo": "regra", "custos_usd": 0.01, "fund_usd": 0.002}],
                        "ignoradas": [{"moeda": "X", "t": 1, "motivo": "abaixo_minimo"}] * 4}}
        r = T.resumo(st)
        self.assertEqual(r["sinais_validados"]["fechadas"], 3); self.assertEqual(r["sinais_fora_do_universo_validado"]["fechadas"], 2)
        self.assertEqual(r["conta_executavel"]["fechadas"], 1); self.assertEqual(r["conta_executavel"]["ignoradas_por_motivo"], {"abaixo_minimo": 4})
        self.assertFalse(r["pronto_para_avaliar"])                       # 3 sinais nao fazem 30 operacoes
        st["sinais"]["fechadas"] *= 10
        self.assertFalse(T.resumo(st)["pronto_para_avaliar"])            # nem 50 sinais teoricos
        st["conta"]["fechadas"] *= 30
        self.assertTrue(T.resumo(st)["pronto_para_avaliar"])


class Qualidade(unittest.TestCase):
    def test_preco_comparado_com_o_perpetuo_global_atual(self):
        f = desce()
        ok = dd(f, px=10.0); ok["px_global"] = 10.1                     # 1%: sem alerta (dia de queda nao conta)
        mau = dd(f, px=10.0); mau["px_global"] = 10.5
        fal = T.qualidade({"OK": ok, "MAU": mau}, {"OK": INFO, "MAU": INFO}, NOW)
        self.assertFalse(any(x.startswith("OK") and "difere" in x for x in fal))
        self.assertTrue(any(x.startswith("MAU") and "difere" in x for x in fal))

    def test_velas_velhas_ficam_de_fora(self):
        f = desce(); st = {}
        T.correr(st, {"AAA": dd(f)}, NOW + 10 * DAY, {"AAA": INFO})
        self.assertEqual(st["sinais"]["abertas"], {})
        self.assertTrue(any("velas velhas" in x for x in st["qualidade"][-1]["falhas"]))


class Ensaio(unittest.TestCase):
    def test_relatorio_universo_minimos_e_falhas(self):
        f = desce()
        dados = {"AAA": dd(f, fund=[(1, 0.0001)]), "BBB": dd(f[:100]), "CCC": dd(f, usd=1e6), "DDD": dd(f, validado=False)}
        dados["DDD"]["px_global"] = f[-1] * 1.05
        infos = {a: INFO for a in ("AAA", "BBB", "CCC", "DDD", "EEE", "BTC")}
        r = T.ensaio(dados, infos)
        self.assertEqual(r["xperps_cripto"], 6); self.assertEqual(r["excluidas"], ["BTC"])
        self.assertEqual(r["sem_velas_globais"], ["EEE"]); self.assertEqual(r["historia_curta"], ["BBB"])
        self.assertEqual(r["iliquidas"], 1); self.assertEqual(r["elegiveis"], 2); self.assertEqual(r["elegiveis_validados"], 1)
        self.assertTrue(any("DDD" in x and "difere" in x for x in r["falhas"]))

    def test_corre_como_script(self):
        src = open(T.__file__, encoding="utf-8").read()
        self.assertLess(src.index("def ensaio("), src.index('if __name__ == "__main__":'))
        self.assertLess(src.index("def main_ensaio("), src.index('if __name__ == "__main__":'))


class SemOrdens(unittest.TestCase):
    def test_modulo_nao_tem_chave_nem_ordens(self):
        src = open(T.__file__, encoding="utf-8").read()
        for proibido in ("/api/v5/trade", "/api/v5/account", "OKX_API", "privado(", "set-leverage"):
            self.assertNotIn(proibido, src)

    def test_workflow_de_papel_sem_chaves_da_okx(self):
        wf = open(".github/workflows/okx-tfshort-papel.yml", encoding="utf-8").read()
        for proibido in ("OKX_API", "OKX_PASSPHRASE", "okx_exec", "DATA_KEY"):
            self.assertNotIn(proibido, wf)
        self.assertIn("--gravar", wf)


if __name__ == "__main__":
    unittest.main()
