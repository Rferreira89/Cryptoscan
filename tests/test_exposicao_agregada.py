"""(19/11, ordem do Rui, ponto 3) Exposicao agregada do REAL entre executores (Bybit UE, OKX executor antigo, piloto
OKX): a mesma aposta em contas diferentes nao passa despercebida. So leitura: nada e bloqueado nem somado em dinheiro."""
import json
import os
import random
import shutil
import tempfile
import unittest

from tools import exposicao_diaria as E


def serie(rs, base, ruido, n=100, p0=1.0):
    out, p = [], p0
    for k in range(n):
        p *= 1 + base[k] + rs.gauss(0, ruido)
        out.append(p)
    return out


class Base(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def grava(self, nome, d):
        with open(os.path.join(self.d, nome), "w") as f:
            json.dump(d, f)

    def hoje(self, piloto_ops=(), sinais=None):
        """O estado real de 19/11: XLM SHORT na Bybit (SHORT_TURTLE) e no executor OKX antigo (espelho)."""
        self.grava("state.json", {"ledger": [{"executed": True, "status": "OPEN", "asset": "XLM", "side": "SHORT",
                                              "strategy": "SHORT_TURTLE", "risk_pct": 2.8}],
                                  "signals": sinais or {}})
        self.grava("okx.json", {"real": {"ops": {"XLM": {"estado": "aberta", "lado": "SHORT", "estrategia": "espelho",
                                                         "entrada": 0.13745, "stop": 0.15363, "alvo": 0.11802,
                                                         "risco_pct": 2.34, "stop_ok": 1}}}})
        self.grava("piloto_publico.json", {"ops": list(piloto_ops)})

    def correr(self, extra=None):
        rs = random.Random(7)
        base = [rs.gauss(0, 0.01) for _ in range(100)]
        series = {"XLM": serie(rs, base, 0.002, p0=0.138), "XRP": serie(rs, base, 0.002), "BTC": serie(rs, [0] * 100, 0.01)}
        series.update(extra or {})
        return E.correr(self.d, obter=lambda m: series.get(m, []))


class Agregado(Base):
    def test_hoje_xlm_short_e_a_mesma_aposta_em_dois_executores(self):
        self.hoje()
        out = self.correr()
        m = out["real_agregado"]["mesmo_ativo_e_lado"]
        self.assertEqual([(x["ativo"], x["lado"], x["n"]) for x in m], [("XLM", "SHORT", 2)])
        self.assertEqual(m[0]["executores"], ["Bybit UE", "OKX executor antigo"])
        self.assertEqual(m[0]["risco_pct_por_conta"], {"Bybit UE": 2.8, "OKX executor antigo": 2.34})   # % de cada conta, nunca somado
        self.assertIn("a mesma aposta em 2 posições", E.texto(out))
        r = out["okx_posicoes_reais"]["XLM"]                                     # o short tem R e distancias
        self.assertEqual(r["lado"], "SHORT")
        self.assertGreater(r["dist_stop_pct"], 0)

    def test_terceira_posicao_equivalente_nao_passa_despercebida(self):
        self.hoje(piloto_ops=[{"base": "XLM", "lado": "SHORT", "estado": "aberta", "estrategia": "x"}])
        out = self.correr()
        m = out["real_agregado"]["mesmo_ativo_e_lado"][0]
        self.assertEqual((m["ativo"], m["n"]), ("XLM", 3))
        self.assertEqual(m["executores"], ["Bybit UE", "OKX executor antigo", "piloto OKX"])
        self.assertIn("a mesma aposta em 3 posições", E.texto(out))

    def test_sinal_pendente_que_aumentaria_a_concentracao(self):
        self.hoje(piloto_ops=[{"base": "XLM", "lado": "SHORT", "estado": "pendente", "estrategia": "x"}])
        out = self.correr()
        c = out["sinais_que_aumentam_concentracao"]
        self.assertEqual(len(c), 1)
        self.assertIn("piloto OKX: XLM SHORT", c[0]["sinal"])
        self.assertEqual(c[0]["n_apos_entrar"], 3)
        self.assertIn("Sinal que aumentaria a concentração", E.texto(out))

    def test_ativo_correlacionado_no_mesmo_lado_tambem_conta(self):
        self.hoje(piloto_ops=[{"base": "XRP", "lado": "SHORT", "estado": "aberta", "estrategia": "x"}])
        out = self.correr()
        g = out["real_agregado"]["grupos_correlacionados"]
        self.assertTrue(any(set(x["ativos"]) == {"XLM", "XRP"} and x["lado"] == "SHORT" for x in g), g)

    def test_lado_contrario_nao_e_concentracao(self):
        self.hoje(piloto_ops=[{"base": "XLM", "lado": "LONG", "estado": "aberta", "estrategia": "x"}])
        out = self.correr()
        self.assertEqual([x["n"] for x in out["real_agregado"]["mesmo_ativo_e_lado"]], [2])

    def test_fechadas_nao_contam(self):
        self.hoje(piloto_ops=[{"base": "XLM", "lado": "SHORT", "estado": "fechada", "estrategia": "x"}])
        out = self.correr()
        self.assertEqual(out["real_agregado"]["mesmo_ativo_e_lado"][0]["n"], 2)

    def test_so_leitura_e_sem_dinheiro(self):
        self.hoje()
        out = self.correr()
        from engine import guarda_publica as G
        self.assertEqual(G.verificar(out["real_agregado"]), [])
        src = open(E.__file__).read()
        for proibido in ("POST", "/order", "privado(", "post("):
            self.assertNotIn(proibido, src)


if __name__ == "__main__":
    unittest.main()


class Historico(unittest.TestCase):
    def test_historico_guarda_as_contagens_do_agregado(self):
        from tools import exposicao_historico as EH
        mapa = {"t": 1, "blocos": {}, "real_agregado": {"n": 3, "mesmo_ativo_e_lado": [{"ativo": "XLM", "n": 3}],
                                                         "grupos_correlacionados": []},
                "sinais_que_aumentam_concentracao": [{"sinal": "x"}]}
        e = EH.entrada(mapa, "2026-11-19", "manual")
        self.assertEqual(e["real_agregado"], {"n": 3, "mesma_aposta_ativos": 1, "mesma_aposta_maior_n": 3,
                                              "grupos_correlacionados": 0, "sinais_que_aumentam_concentracao": 1})
        self.assertNotIn("XLM", json.dumps(e))
