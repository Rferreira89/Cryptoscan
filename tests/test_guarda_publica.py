"""(19/11, ordem do Rui) Guarda geral dos ficheiros publicos: apanha valores financeiros absolutos e dados de conta
nos ficheiros GERADOS pelo codigo (piloto_publico.json, okx.json, estados), bloqueia a publicacao das vistas e nunca
para o trading. Os numeros das fixtures sao inventados."""
import copy
import json
import os
import shutil
import sys
import tempfile
import unittest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.join(RAIZ, "tools"))
from engine import guarda_publica as G  # noqa: E402
import piloto_okx as P  # noqa: E402
import publicar_estado as PE  # noqa: E402
from tests import test_piloto_duas_posicoes as T2  # noqa: E402


class Detecao(unittest.TestCase):
    def test_apanha_dinheiro_tamanhos_e_conta(self):
        maus = {"saldos": {"BTC": 0.01}, "risk_usdc": 1.2, "qty": 3, "conta": {"equity": 50.0}, "apiKey": "x",
                "a": [{"pnl_liquido": -0.4}], "nocional": 14.28, "contratos": 3, "margem_livre": 4.1,
                "motivo": "tamanho minimo (livre depois das 1 posicoes abertas: risco 0.0240, nocional 14.28)",
                "txt": "saldo 12.5 USDC", "m2": "margem livre 4.1"}
        campos = {c.split(".")[0].split("[")[0] for c, _ in G.verificar(maus)}
        self.assertEqual(campos, set(maus))

    def test_deixa_o_que_e_publico_de_proposito(self):
        bons = {"preco_efetivo": 142.89, "stop": 137.92, "preco_atual": 144.54, "r": 0.581, "r_aberto": 0.33,
                "risco_usado_pct": 90.4, "nocional_usado_pct": 28.6, "n": 12, "t_fecho": 1795075614,
                "capital_max": 20.0, "nocional_max": 20.0, "risco_max_op": 0.25, "lotes_bybit": {"m": {"XLM": [0.1, 1.0]}},
                "funding": {"XLM-USDT-SWAP": [[1795000000, 0.0001]]}, "juros_bybit": {"m": {"XLM": 0.0002}},
                "motivo": "tamanho minimo (1 contratos) passaria o risco (livre: risco 25% do orcamento)",
                "motivo2": "risco agregado passaria 5% (aberto 2.8%)", "resumo": {"contratos": 289},
                "liga": {"tabela": [{"pos": 1}]}, "copy:hyperliquid:0xbbd7": {"estado": "ok"}, "liquidity_score": 0.8,
                "position": {"fee": 0.0025}}
        self.assertEqual(G.verificar(bons), [])

    def test_ficheiro_cifrado_nao_e_lido(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump({"cifra": "v1", "dados": "AAAA"}, f)
        try:
            self.assertEqual(G.verificar_ficheiro(f.name), [])
        finally:
            os.remove(f.name)


class GeradosPeloCodigo(T2.Base):
    def test_piloto_publico_gerado_sem_valores(self):
        # duas posicoes e uma rejeicao por tamanho minimo com o orcamento residual (o caso da fuga de 7453957)
        api = T2.MultiOKX()
        api.spec[T2.inst_id("BBB")]["minSz"] = "5"
        self.corre(api, T2.sinal("boa", "AAA", atr=0.05))
        self.corre(api, T2.sinal("fraca", "BBB", t_fecho=T2.NOW0 + 900 - 660, atr=0.05), now=T2.NOW0 + 900)
        with open(os.path.join(self.d, "piloto_publico.json")) as f:
            pub = json.load(f)
        motivos = json.dumps(pub["sinais_perdidos"])
        self.assertIn("tamanho minimo", motivos)
        self.assertEqual(G.verificar(pub), [])

    def test_motivo_antigo_persistido_nao_volta_a_sair(self):
        api = T2.MultiOKX()
        self.corre(api)
        caminho = os.path.join(self.d, "piloto_estado.json")
        with open(caminho) as f:
            st = json.load(f)
        antigo = "tamanho minimo (1 contratos) passaria o risco (livre depois das 1 posicoes abertas: risco 0.0240, nocional 14.28)"
        st.setdefault("sinais_perdidos", []).append({"t": T2.NOW0, "sinal": "x|Y|1", "motivo": antigo})
        st.setdefault("oportunidades", {})["x|Y|1"] = {"t": T2.NOW0, "decisao": "REJEITADA", "motivo": antigo, "origem": "x"}
        st.setdefault("eventos", []).append({"t": T2.NOW0, "txt": antigo})
        with open(caminho, "w") as f:
            json.dump(st, f)
        self.corre(api, now=T2.NOW0 + 900)
        with open(os.path.join(self.d, "piloto_publico.json")) as f:
            pub = json.load(f)
        self.assertEqual(G.verificar(pub), [], [c for c, _ in G.verificar(pub)][:5])

    def test_estado_do_agente_okx_gerado_sem_valores(self):
        from tests.test_okx_agente import Execucao
        t = Execucao("test_funil_regista_decisoes_sem_repetir")
        t.setUp() if hasattr(t, "setUp") else None
        try:
            now = 2_000_000_000
            ok = {"tipo": "espelho", "lado": "SHORT", "stop": 0.0260, "alvo": 0.0200, "t_sig": now - 600,
                  "estrategia": "SHORT_TURTLE", "origem": "okx"}
            st, _, _ = t._esp([("XLM", ok)], 0.0236)
        finally:
            t.tearDown()
            t.doCleanups()                                   # desfaz os mock.patch do setUp (nao contaminar outros testes)
        self.assertEqual(G.verificar(st), [], [c for c, _ in G.verificar(st)][:5])


class Publicacao(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.avisos = []

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def escreve(self, nome, d):
        with open(os.path.join(self.d, nome), "w") as f:
            json.dump(d, f)

    def test_vista_com_fuga_nao_e_publicada(self):
        self.escreve("piloto_publico.json", {"t": 1, "motivo": "saldo 12.5 USDC", "ops": []})
        self.escreve("piloto_estado.json", {"cifra": "v1", "dados": "AAAA"})
        f = PE.guardar_publicos(self.d, ["piloto_estado.json", "piloto_publico.json"], avisar=self.avisos.append, agora=5)
        self.assertEqual(list(f), ["piloto_publico.json"])
        with open(os.path.join(self.d, "piloto_publico.json")) as fh:
            fica = json.load(fh)
        self.assertNotIn("12.5", json.dumps(fica))
        self.assertEqual(fica["publicacao_bloqueada"]["campos"], ["motivo"])          # diz o campo
        with open(os.path.join(self.d, "piloto_estado.json")) as fh:
            self.assertEqual(json.load(fh), {"cifra": "v1", "dados": "AAAA"})         # o estado cifrado segue igual
        self.assertTrue(self.avisos and "piloto_publico.json" in self.avisos[0])

    def test_estado_do_agente_com_fuga_publica_e_avisa(self):
        d = {"t": 1, "real": {"ops": {}}, "conta": {"equity": 50.0}}
        self.escreve("okx.json", d)
        f = PE.guardar_publicos(self.d, ["okx.json", "cofre_okx.json"], avisar=self.avisos.append)
        self.assertIn("okx.json", f)
        with open(os.path.join(self.d, "okx.json")) as fh:
            self.assertEqual(json.load(fh), d)                                         # nao para o executor
        self.assertIn("corrigir na origem", self.avisos[0])

    def test_sem_fuga_nada_muda(self):
        d = {"t": 1, "ops": [{"r": 0.5, "preco_efetivo": 1.0}]}
        self.escreve("piloto_publico.json", d)
        self.assertEqual(PE.guardar_publicos(self.d, ["piloto_publico.json"], avisar=self.avisos.append), {})
        with open(os.path.join(self.d, "piloto_publico.json")) as fh:
            self.assertEqual(json.load(fh), d)
        self.assertEqual(self.avisos, [])

    def test_publicar_corre_a_guarda_antes_do_push(self):
        self.escreve("piloto_publico.json", {"t": 1, "nocional": 14.28})
        chamadas = []

        class R:
            returncode, stdout, stderr = 0, "", ""

        def git(pasta, *a):
            chamadas.append(a)
            if a[0] == "add":
                with open(os.path.join(pasta, "piloto_publico.json")) as fh:
                    chamadas.append(("conteudo", fh.read()))
            return R()
        antigo = os.environ.get("ESTADO_LOCAL")
        os.environ["ESTADO_LOCAL"] = self.d
        self.addCleanup(lambda: os.environ.pop("ESTADO_LOCAL") if antigo is None else os.environ.__setitem__("ESTADO_LOCAL", antigo))
        PE.publicar(self.d, "teste", ["piloto_publico.json"], push_url="x", git=git, avisar=self.avisos.append)
        conteudo = next(c[1] for c in chamadas if c[0] == "conteudo")
        self.assertNotIn("14.28", conteudo)
        self.assertIn("publicacao_bloqueada", conteudo)


if __name__ == "__main__":
    unittest.main()


class LoteDoPlano(unittest.TestCase):
    """(19/11) plan.lote.qtd e plan.lote.risco_efetivo sairam no state.json e no scan.json publicos (sinal XLM)."""
    LOTE = {"signals": {"XLM-X-1": {"plan": {"stop": 0.15, "lote": {"qtd": 36.8, "passo": 0.1, "qtd_min": 0.1,
                                                                     "preco_limite": 0.1363, "risco_efetivo": 0.66}}}}}

    def test_guarda_apanha(self):
        campos = {c.rsplit(".", 1)[-1] for c, _ in G.verificar(self.LOTE)}
        self.assertTrue({"qtd", "risco_efetivo"} <= campos, campos)

    def test_copia_publica_tira_na_origem(self):
        from engine import publico
        limpo = publico.state(self.LOTE)
        lote = limpo["signals"]["XLM-X-1"]["plan"]["lote"]
        self.assertNotIn("qtd", lote)
        self.assertNotIn("risco_efetivo", lote)
        self.assertEqual(lote["preco_limite"], 0.1363)                    # precos continuam publicos
        self.assertEqual(G.verificar(limpo), [])


class TextoComDoisValores(unittest.TestCase):
    """(19/11) promo_lost no state.json publico: 'risco efetivo depois do arredondamento (0.839) passa o autorizado
    (0.823) USDC' (AVAX, 14/11). A guarda apanha, a copia publica tira os dois e o motivo novo ja nao tem moeda."""
    TXT = "plano: lote: risco efetivo depois do arredondamento (0.839) passa o autorizado (0.823) USDC"

    def test_guarda_e_copia_publica(self):
        from engine import publico
        self.assertTrue(G.verificar({"reason": self.TXT}))
        limpo = publico.limpar_texto(self.TXT)
        self.assertNotIn("0.839", limpo)
        self.assertNotIn("0.823", limpo)
        self.assertEqual(G.verificar({"reason": limpo}), [])

    def test_motivo_na_origem_sem_moeda(self):
        import inspect
        from engine import promo
        src = inspect.getsource(promo)
        self.assertNotIn("passa o autorizado ({float(mr):.3f}) USDC", src)
        self.assertIn("% do autorizado", src)
