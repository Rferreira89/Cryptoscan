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


class Lotes(unittest.TestCase):
    """(12/11 09:20) Orcamento por lote: uma serie interrompida nao e gravada (nada fica a meio)."""

    def test_interrompida_nao_grava(self):
        d = tempfile.mkdtemp()
        with mock.patch.object(V, "instrumentos", return_value={"AAA": "AAA-USD_UM_XPERP"}), \
                mock.patch.object(V, "velas", side_effect=V.Interrompido("x")):
            m = V.correr(d, dias=10, orcamento=1, fios=1)
        self.assertFalse(m["completo"])
        self.assertEqual(m["por_fazer"], 2)
        self.assertFalse(os.path.exists(os.path.join(d, "AAA.csv.gz")))

    def test_completa_e_sem_a_vista(self):
        d = tempfile.mkdtemp()
        t = 1_800_000_000 // 3600 * 3600

        def falsa(host, i, desde, ja, fim=None):
            return {} if host == V.GLOBAL else {t: ["1", "1", "1", "1", "1"]}
        with mock.patch.object(V, "instrumentos", return_value={"AAA": "AAA-USD_UM_XPERP"}), \
                mock.patch.object(V, "velas", side_effect=falsa):
            m = V.correr(d, dias=10, fios=2)
        self.assertTrue(m["completo"])
        self.assertEqual(m["sem_substituto_a_vista"], ["AAA"])
        self.assertTrue(os.path.exists(os.path.join(d, "xperp", "AAA.csv.gz")))
        self.assertEqual(V.ler(os.path.join(d, "AAA.csv.gz")), {})

    def test_velas_respeita_fim(self):
        with self.assertRaises(V.Interrompido):
            V.velas("h", "X", 0, {}, fim=0)


if __name__ == "__main__":
    unittest.main()
