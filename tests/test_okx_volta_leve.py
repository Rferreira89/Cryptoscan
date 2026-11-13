"""(13/11) Agente OKX: entre dois fechos de vela de 4H a volta e "leve" (sem pedir velas a OKX), mas a parte do
dinheiro real (ordens, stops, sinais pendentes) corre sempre; na duvida (atrasos, janela nova) a volta e completa."""
import json, os, tempfile, unittest
from unittest import mock

from tools import okx_agente as A

H4 = A.H4
BASE = 1794024000            # 2026-11-07 04:00 UTC (fecho de vela de 4H)


def st_com(t_completa, atrasadas=0, t_resumo=None):
    return {"resumo": {"t": t_resumo or t_completa, "contratos": 289, "analisados": 289},
            "volta": {"t": t_completa, "saltada": False, "saltadas": 3, "t_completa": t_completa, "atrasadas": atrasadas},
            "pend": {"CP": {"t_sig": BASE - H4, "lim": 1.0, "atr": 0.1, "tipo": "mercado"}}, "abertas": {}}


class Decisao(unittest.TestCase):
    def test_leve_so_na_mesma_janela_e_sem_atrasos(self):
        self.assertTrue(A.volta_leve(st_com(BASE + 8 * 60), BASE + 68 * 60))           # 04:08 completa -> 05:08 leve
        self.assertTrue(A.volta_leve(st_com(BASE + 8 * 60), BASE + 3 * 3600 + 50 * 60))  # 07:50 ainda leve
        self.assertFalse(A.volta_leve(st_com(BASE + 8 * 60), BASE + H4 + 8 * 60))      # 08:08: vela nova -> completa
        self.assertFalse(A.volta_leve(st_com(BASE + 2 * 60), BASE + 68 * 60))          # completa antes da margem
        self.assertFalse(A.volta_leve(st_com(BASE + 8 * 60, atrasadas=1), BASE + 68 * 60))  # contrato atrasado
        self.assertFalse(A.volta_leve(st_com(BASE + 8 * 60, atrasadas=None), BASE + 68 * 60))
        self.assertFalse(A.volta_leve({"resumo": {"t": BASE + 8 * 60}}, BASE + 68 * 60))  # sem registo (estado antigo)
        self.assertFalse(A.volta_leve(st_com(BASE + 70 * 60), BASE + 68 * 60))         # relogio para tras
        self.assertFalse(A.volta_leve({}, BASE + 68 * 60))


class Main(unittest.TestCase):
    def _correr(self, st, now, velas=None):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "okx.json")
        json.dump(st, open(p, "w"))
        with mock.patch.object(A.time, "time", return_value=now), mock.patch.object(A, "get", return_value=[]) as g, \
                mock.patch.object(A, "telegram") as tg, mock.patch.object(A, "correr", wraps=A.correr) as c, \
                mock.patch.object(A, "executar_real") as ex, mock.patch.object(A, "moedas", return_value=velas or {}), \
                mock.patch("builtins.print"):
            A.main(p)
        return json.load(open(p)), g, tg, c, ex

    def test_leve_sem_pedidos_de_velas_mas_com_execucao_real(self):
        st0 = st_com(BASE + 8 * 60)
        st, g, tg, c, ex = self._correr(st0, BASE + 68 * 60)
        self.assertFalse(c.called)
        self.assertFalse(g.called)                                      # nenhum pedido a OKX publica
        self.assertTrue(ex.called)                                      # dinheiro real gerido nesta volta
        self.assertEqual(ex.call_args[0][1], BASE + 68 * 60)
        self.assertEqual(st["resumo"]["t"], BASE + 68 * 60)             # batimento do vigia e da Sala de controlo
        self.assertEqual(st["resumo"]["analisados"], 289)
        self.assertEqual(st["pend"], st0["pend"])
        self.assertTrue(st["volta"]["leve"])
        self.assertEqual(st["volta"]["leves"], 1)
        self.assertEqual(st["volta"]["t_completa"], BASE + 8 * 60)
        self.assertEqual(st["volta"]["saltadas"], 3)

    def test_leve_manda_as_mensagens_do_executor_e_o_radar_diario(self):
        t19 = BASE - 4 * 3600 + 19 * 3600 - 24 * 3600 + 8 * 60   # 19:08 UTC (BASE e 04:00)
        t_comp = t19 - 3600                                       # 18:08: mesma janela 16:00-20:00
        st0 = st_com(t_comp)
        st0["radar"] = {"btc_24h": -1.0, "lista": []}
        d = tempfile.mkdtemp()
        p = os.path.join(d, "okx.json")
        json.dump(st0, open(p, "w"))
        with mock.patch.object(A.time, "time", return_value=t19), mock.patch.object(A, "get", return_value=[]), \
                mock.patch.object(A, "telegram") as tg, \
                mock.patch.object(A, "executar_real", side_effect=lambda s, n, m: m.append("🛡️ OKX real — X: teste")), \
                mock.patch("builtins.print"):
            A.main(p)
        textos = [a[0][0] for a in tg.call_args_list]
        self.assertTrue(any("OKX real" in t for t in textos))
        self.assertTrue(any("Radar diário" in t for t in textos))

    def test_janela_nova_faz_volta_completa_e_regista_atrasos(self):
        agora = BASE + H4 + 8 * 60
        ultima = BASE                                     # abertura da ultima vela fechada as 08:08 = 04:00
        c_ok = [{"t": ultima - H4 * k, "o": 1, "h": 1, "l": 1, "c": 1} for k in range(60)][::-1]
        c_atr = c_ok[:-1]                                 # a OKX ainda nao confirmou a ultima vela deste contrato
        lista = {"AAA": {"inst": "AAA-USDT-SWAP"}, "BBB": {"inst": "BBB-USDT-SWAP"}, "CCC": {"inst": "CCC-USDT-SWAP"}}
        series = {"AAA-USDT-SWAP": c_ok, "BBB-USDT-SWAP": c_atr, "CCC-USDT-SWAP": []}
        d = tempfile.mkdtemp()
        p = os.path.join(d, "okx.json")
        json.dump(st_com(BASE + 8 * 60), open(p, "w"))
        with mock.patch.object(A.time, "time", return_value=agora), mock.patch.object(A.time, "sleep"), \
                mock.patch.object(A, "moedas", return_value=lista), mock.patch.object(A, "velas", side_effect=lambda i: series[i]), \
                mock.patch.object(A, "executar_real") as ex, mock.patch.object(A, "telegram"), \
                mock.patch.object(A, "radar_quase", return_value={"btc_24h": None, "lista": []}), \
                mock.patch("builtins.print"):
            A.main(p)
        st = json.load(open(p))
        self.assertTrue(ex.called)
        self.assertFalse(st["volta"]["leve"])
        self.assertEqual(st["volta"]["t_completa"], agora)
        self.assertEqual(st["volta"]["atrasadas"], 2)     # BBB (vela por confirmar) e CCC (sem dados)
        self.assertFalse(A.volta_leve(st, agora + 3600))  # com atrasos, a volta seguinte volta a ser completa
        st["volta"]["atrasadas"] = 0
        self.assertTrue(A.volta_leve(st, agora + 3600))

    def test_saltada_guarda_o_registo_da_volta_completa(self):
        st0 = st_com(BASE + 8 * 60)
        st, g, tg, c, ex = self._correr(st0, BASE + 12 * 60)            # 4 min depois: volta repetida
        self.assertTrue(st["volta"]["saltada"])
        self.assertFalse(ex.called)
        self.assertEqual(st["volta"]["t_completa"], BASE + 8 * 60)
        self.assertEqual(st["volta"]["atrasadas"], 0)


if __name__ == "__main__":
    unittest.main()
