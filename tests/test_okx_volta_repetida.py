"""(07/11) Agente OKX: a segunda volta na mesma hora (lancamentos duplicados) salta sem pedidos a OKX; nunca salta
logo depois de um fecho de vela de 4H nem quando a volta anterior e antiga."""
import json, os, tempfile, unittest
from unittest import mock

from tools import okx_agente as A
from tools import okx_macro as M

H4 = A.H4
BASE = 1794024000            # 2026-11-07 04:00 UTC (fecho de vela de 4H)


class VoltaRepetida(unittest.TestCase):
    def st(self, t):
        return {"resumo": {"t": t}}

    def test_regras(self):
        self.assertTrue(A.volta_repetida(self.st(BASE + 7 * 60), BASE + 11 * 60))           # 04:07 -> 04:11
        self.assertTrue(A.volta_repetida(self.st(BASE + 3600 + 44), BASE + 3600 + 8 * 60))  # 05:00 -> 05:08
        self.assertFalse(A.volta_repetida(self.st(BASE + 42), BASE + 8 * 60))               # 04:00:42: logo apos o fecho
        self.assertFalse(A.volta_repetida(self.st(BASE - 120), BASE + 3 * 60))              # janela de 4H anterior
        self.assertFalse(A.volta_repetida(self.st(BASE + 7 * 60), BASE + 28 * 60))          # 21 min: corre
        self.assertFalse(A.volta_repetida(self.st(BASE + 600), BASE + 300))                 # relogio para tras
        self.assertFalse(A.volta_repetida({}, BASE + 600))                                  # estado novo
        self.assertFalse(A.volta_repetida({"resumo": {}}, BASE + 600))

    def _correr(self, st, now):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "okx.json")
        json.dump(st, open(p, "w"))
        with mock.patch.object(A.time, "time", return_value=now), mock.patch.object(A, "get") as g, \
                mock.patch.object(A, "telegram") as tg, mock.patch.object(A, "correr", wraps=A.correr) as c, \
                mock.patch("builtins.print"):
            g.return_value = []
            A.main(p)
        return json.load(open(p)), g, tg, c, p

    def test_saltada_sem_pedidos_e_ficheiro_muda(self):
        st0 = {"resumo": {"t": BASE + 7 * 60, "contratos": 289, "analisados": 289}, "pend": {}, "abertas": {}}
        st, g, tg, c, p = self._correr(st0, BASE + 11 * 60)
        self.assertFalse(c.called)
        self.assertFalse(g.called)
        self.assertFalse(tg.called)
        self.assertEqual(st["resumo"], st0["resumo"])                  # batimento da volta verdadeira fica
        self.assertEqual(st["volta"], {"t": BASE + 11 * 60, "saltada": True, "saltadas": 1})
        # o macro tambem salta nesta volta
        with mock.patch.object(M.time, "time", return_value=BASE + 12 * 60), mock.patch.object(M, "correr") as mc, \
                mock.patch("builtins.print"):
            M.main(p)
        self.assertFalse(mc.called)

    def test_volta_normal_corre_e_macro_tambem(self):
        st, g, tg, c, p = self._correr({"resumo": {"t": BASE - 3600}}, BASE + 8 * 60)
        self.assertTrue(c.called)
        self.assertFalse(st["volta"]["saltada"])
        with mock.patch.object(M.time, "time", return_value=BASE + 9 * 60), \
                mock.patch.object(M, "correr", side_effect=lambda s: s.setdefault("macro", {"resumo": {
                    "analisados": 0, "sem_historico": 0, "abertas": [], "n": 0}}) and []) as mc, \
                mock.patch("builtins.print"), mock.patch.object(M.A, "telegram"):
            M.main(p)
        self.assertTrue(mc.called)


if __name__ == "__main__":
    unittest.main()
