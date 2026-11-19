"""(19/11) Sombra ao vivo das rapidas: so le precos publicos, deteta na ultima vela fechada, resolve depois, nunca
inventa resultados quando faltam dados."""
import unittest

from tools import sombra_rapidas as S

H = 3600
T0 = 1_800_000_000 // H * H


def serie(n, p=1.0, ate=None):
    return [[str((T0 + k * H) * 1000), str(p), str(p * 1.001), str(p * 0.999), str(p), "100", "0", "0", "1"]
            for k in range(n if ate is None else ate)]


class Falso:
    def __init__(self, n=40):
        self.n = n
        self.evento = True
        self.pedidos = []

    def __call__(self, path):
        self.pedidos.append(path)
        if "public/instruments" in path:
            return [{"instId": "AAA-USDT-SWAP", "instCategory": "1"}, {"instId": "BTC-USDT-SWAP", "instCategory": "1"},
                    {"instId": "POUCO-USDT-SWAP", "instCategory": "1"}, {"instId": "LARGO-USDT-SWAP", "instCategory": "1"},
                    {"instId": "USDC-USDT-SWAP", "instCategory": "1"}, {"instId": "INTC-USDT-SWAP", "instCategory": "3"}]
        if "tickers" in path:
            liv = {"bidSz": "5000", "askSz": "5000"}
            return [dict(liv, instId="AAA-USDT-SWAP", volCcy24h="9000000", last="1", bidPx="0.9999", askPx="1.0001"),
                    dict(liv, instId="INTC-USDT-SWAP", volCcy24h="999999", last="30", bidPx="29.99", askPx="30.01"),
                    dict(liv, instId="USDC-USDT-SWAP", volCcy24h="99999999", last="1", bidPx="0.9999", askPx="1.0001"),
                    dict(liv, instId="BTC-USDT-SWAP", volCcy24h="5000", last="60000", bidPx="59999", askPx="60001"),
                    dict(liv, instId="POUCO-USDT-SWAP", volCcy24h="1000", last="1", bidPx="0.9999", askPx="1.0001"),
                    dict(liv, instId="LARGO-USDT-SWAP", volCcy24h="9000000", last="1", bidPx="0.99", askPx="1.01")]
        base = path.split("instId=")[1].split("-")[0]
        d = serie(self.n, 60000.0 if base == "BTC" else 1.0)
        if base == "AAA" and self.evento:
            k = 39                                            # rutura com volume na vela 39
            d[k] = [d[k][0], "1.0", "1.03", "0.999", "1.025", "900", "0", "0", "1"]
        return list(reversed(d))                              # a OKX manda a mais recente primeiro


class Volta(unittest.TestCase):
    def test_sem_estaveis_e_sem_chaves(self):
        g = Falso()
        self.assertEqual(S.universo(g), ["BTC", "AAA"])                # por volume em USD
        self.assertFalse(any("/account" in p or "/trade" in p for p in g.pedidos))

    def test_evento_na_ultima_vela_e_resolvido_depois(self):
        g = Falso(n=40)
        st = S.volta({}, now=T0 + 40 * H, get=g)
        ks = [k for k in st["abertas"] if k.startswith("R1|AAA")]
        self.assertEqual(len(ks), 1)
        self.assertEqual(st["fechadas"], [])
        g2 = Falso(n=45)
        st = S.volta(st, now=T0 + 45 * H, get=g2)
        self.assertNotIn(ks[0], st["abertas"])
        f = [x for x in st["fechadas"] if x["hip"] == "R1"][0]
        self.assertEqual(set(f["resultado"]), {"1h", "2h", "4h"})
        self.assertIn("R1|1h|LONG", st["resumo"])
        self.assertEqual(st["classificacao"], "SHADOW")

    def test_nao_repete_o_mesmo_evento(self):
        g = Falso(n=40)
        st = S.volta({}, now=T0 + 40 * H, get=g)
        n = len(st["abertas"])
        st = S.volta(st, now=T0 + 40 * H + 600, get=Falso(n=40))
        self.assertEqual(len(st["abertas"]), n)

    def test_sem_dados_nao_conta(self):
        st = {"abertas": {"R1|ZZZ|1|1": {"hip": "R1", "ativo": "ZZZ", "t": T0, "lado": 1}}, "fechadas": []}
        g = Falso(n=40)
        st = S.volta(st, now=T0 + 49 * H, get=g)
        f = [x for x in st["fechadas"] if x["ativo"] == "ZZZ"][0]
        self.assertTrue(f["sem_dados"])
        self.assertNotIn("R1|1h|LONG", {k for k in st["resumo"] if "ZZZ" in k})

    def test_elegibilidade_objetiva(self):
        g = Falso()
        self.assertEqual(S.universo(g), ["BTC", "AAA"])
        e = S.ELEG
        self.assertEqual((e["nao_cripto"], e["estavel"], e["volume"], e["spread"], e["elegiveis"]), (1, 1, 1, 1, 2))
        st = S.volta({}, now=T0 + 40 * H, get=Falso(n=40))
        self.assertEqual(st["elegibilidade"]["elegiveis"], 2)
        self.assertTrue(all(v.get("spread_bps") is not None for v in st["abertas"].values()))

    def test_eventos_de_acoes_saem(self):
        st0 = {"abertas": {"R2|INTC|1|-1": {"hip": "R2", "ativo": "INTC", "t": T0, "lado": -1}}, "fechadas": []}
        st = S.volta(st0, now=T0 + 40 * H, get=Falso(n=40))
        self.assertNotIn("R2|INTC|1|-1", st["abertas"])

    def test_okx_sem_resposta_nao_muda_nada(self):
        st0 = {"abertas": {"x": {"hip": "R1", "ativo": "AAA", "t": T0, "lado": 1}}, "fechadas": []}
        st = S.volta(st0, now=T0 + 3 * H, get=lambda p: None)
        self.assertEqual(st["abertas"], st0["abertas"])
        self.assertIn("ultima_falha", st)

    def test_ficheiro_publico_limpo(self):
        from engine import guarda_publica as G
        st = S.volta({}, now=T0 + 40 * H, get=Falso(n=40))
        st = S.volta(st, now=T0 + 45 * H, get=Falso(n=45))
        self.assertEqual(G.verificar(st), [])


if __name__ == "__main__":
    unittest.main()
