"""(14/11) Agente OKX: se a lista de contratos vier vazia (API publica da OKX sem resposta), a volta nao pode contar
"atrasadas 0" (prenderia as voltas seguintes da janela de 4H em volta leve, sem gerir o papel), nem apagar a cache do
financiamento ou o radar. A parte do dinheiro real corre na mesma."""
import json, os, tempfile, unittest
from unittest import mock

from tools import okx_agente as A

H4 = A.H4
BASE = 1794024000            # 2026-11-07 04:00 UTC (fecho de vela de 4H)


def estado():
    return {"resumo": {"t": BASE - H4 + 8 * 60, "contratos": 289, "analisados": 289},
            "volta": {"t": BASE - H4 + 8 * 60, "saltada": False, "saltadas": 3, "t_completa": BASE - H4 + 8 * 60,
                      "atrasadas": 0, "leves": 5},
            "pend": {}, "abertas": {}, "fechadas": [], "ultimo": {},
            "funding": {"AAA-USDT-SWAP": [[1, 0.0001]], "BBB-USDT-SWAP": [[1, -0.0002]]},
            "radar": {"btc_24h": -1.5, "lista": [{"a": "AAA"}]}}


class SemLista(unittest.TestCase):
    def _main(self, st0, now, lista):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "okx.json")
        json.dump(st0, open(p, "w"))
        with mock.patch.object(A.time, "time", return_value=now), mock.patch.object(A.time, "sleep"), \
                mock.patch.object(A, "moedas", return_value=lista), mock.patch.object(A, "velas", return_value=[]), \
                mock.patch.object(A, "executar_real") as ex, mock.patch.object(A, "telegram"), \
                mock.patch.object(A, "radar_quase", return_value={"btc_24h": None, "lista": []}) as rq, \
                mock.patch("builtins.print"):
            A.main(p)
        return json.load(open(p)), ex, rq

    def test_lista_vazia_marca_atraso_e_guarda_cache_e_radar(self):
        agora = BASE + 8 * 60                                           # janela nova -> volta completa
        st, ex, rq = self._main(estado(), agora, {})
        self.assertTrue(ex.called)                                      # dinheiro real gerido na mesma
        self.assertFalse(st["volta"]["leve"])
        self.assertGreater(st["volta"]["atrasadas"], 0)
        self.assertEqual(st["volta"]["sem_lista"], 1)
        self.assertFalse(A.volta_leve(st, agora + 3600))                # a volta seguinte volta a ser completa
        self.assertEqual(set(st["funding"]), {"AAA-USDT-SWAP", "BBB-USDT-SWAP"})
        self.assertEqual(st["radar"], estado()["radar"])
        self.assertFalse(rq.called)
        self.assertEqual(st["resumo"]["analisados"], 0)                 # o resumo diz a verdade sobre esta volta

    def test_contador_sem_lista_sobrevive_a_volta_seguinte(self):
        agora = BASE + 8 * 60
        st, _, _ = self._main(estado(), agora, {})
        st2, _, _ = self._main(st, agora + 3600, {})
        self.assertEqual(st2["volta"]["sem_lista"], 2)
        self.assertGreater(st2["volta"]["atrasadas"], 0)

    def test_lista_normal_continua_a_limpar_a_cache_de_contratos_retirados(self):
        agora = BASE + 8 * 60
        c = [{"t": BASE - H4 * k, "o": 1, "h": 1, "l": 1, "c": 1} for k in range(60)][::-1]
        lista = {"AAA": {"inst": "AAA-USDT-SWAP"}}
        d = tempfile.mkdtemp()
        p = os.path.join(d, "okx.json")
        json.dump(estado(), open(p, "w"))
        with mock.patch.object(A.time, "time", return_value=agora), mock.patch.object(A.time, "sleep"), \
                mock.patch.object(A, "moedas", return_value=lista), mock.patch.object(A, "velas", return_value=c), \
                mock.patch.object(A, "executar_real"), mock.patch.object(A, "telegram"), \
                mock.patch.object(A, "radar_quase", return_value={"btc_24h": None, "lista": []}), \
                mock.patch("builtins.print"):
            A.main(p)
        st = json.load(open(p))
        self.assertEqual(set(st["funding"]), {"AAA-USDT-SWAP"})        # BBB saiu da OKX: cache limpa
        self.assertEqual(st["volta"]["atrasadas"], 0)
        self.assertNotIn("sem_lista", st["volta"])
        self.assertEqual(st["radar"], {"btc_24h": None, "lista": []})


if __name__ == "__main__":
    unittest.main()
