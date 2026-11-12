"""(12/11) Recolha de velas de 1h da OKX: so GET publico, so velas fechadas, incremental, formato estavel."""
import inspect
import os
import tempfile
import unittest
from unittest import mock

from tools import okx_velas_1h as V


class Recolha(unittest.TestCase):
    def test_so_leitura_publica(self):
        src = inspect.getsource(V)
        for proibido in ("OK-ACCESS-KEY", "API_KEY", "POST", "/trade/", "privado("):
            self.assertNotIn(proibido, src)

    def test_so_velas_fechadas_e_incremental(self):
        t0 = 1_800_000_000 // 3600 * 3600
        pag = [[str((t0 - k * 3600) * 1000), "1", "2", "0.5", "1.5", "10", "", "", "1" if k else "0"] for k in range(5)]
        with mock.patch.object(V, "get", side_effect=[pag, []]), mock.patch.object(V.time, "sleep"):
            r = V.velas("h", "X", t0 - 10 * 3600, {})
        self.assertNotIn(t0, r)                                  # a vela por fechar fica de fora
        self.assertEqual(len(r), 4)
        d = tempfile.mkdtemp()
        p = os.path.join(d, "x", "A.csv.gz")
        V.gravar(p, r)
        self.assertEqual(V.ler(p), {t: [str(x) for x in v] for t, v in r.items()})


if __name__ == "__main__":
    unittest.main()
