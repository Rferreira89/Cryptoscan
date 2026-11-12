"""(12/11) Cobertura: as moedas com margem na Bybit UE entram na analise mesmo fora do filtro externo de descoberta;
as que nao estao na Bybit UE, ou falham por outra razao, continuam fora."""
import unittest

from engine import scanner

NOW = 1_800_000_000


def linha(a, motivos, on_venue=True):
    return {"asset": a, "excluded_for": list(motivos), "eligible": not motivos, "on_venue": on_venue}


class Margem(unittest.TestCase):
    ST = {"margem_bybit": {"t": NOW, "moedas": ["MNT", "AVNT", "SEI", "FORA"]}}

    def test_inclui_so_executaveis_excluidas_pelo_filtro_externo(self):
        uni = [linha("SEI", []), linha("MNT", ["volume baixo"]), linha("AVNT", ["spread excessivo", "volume baixo"]),
               linha("FORA", ["volume baixo"], on_venue=False), linha("DOGE", ["volume baixo"]),
               linha("MNT2", ["divergencia entre fontes"])]
        eleg = [uni[0]]
        novas = scanner.incluir_margem(uni, eleg, self.ST, NOW)
        self.assertEqual([r["asset"] for r in novas], ["MNT", "AVNT"])
        self.assertTrue(all(r["eligible"] and "margem" in r["incluida_por"] for r in novas))

    def test_divergencia_de_precos_nunca_e_ignorada(self):
        st = {"margem_bybit": {"t": NOW, "moedas": ["X"]}}
        uni = [linha("X", ["volume baixo", "divergencia entre fontes"])]
        self.assertEqual(scanner.incluir_margem(uni, [], st, NOW), [])

    def test_lista_de_margem_velha_ou_ausente_nao_inclui_nada(self):
        uni = [linha("MNT", ["volume baixo"])]
        self.assertEqual(scanner.incluir_margem(uni, [], {}, NOW), [])
        velha = {"margem_bybit": {"t": NOW - 8 * 86400, "moedas": ["MNT"]}}
        self.assertEqual(scanner.incluir_margem(uni, [], velha, NOW), [])

    def test_nao_duplica(self):
        uni = [linha("SEI", [])]
        self.assertEqual(scanner.incluir_margem(uni, uni, self.ST, NOW), [])


if __name__ == "__main__":
    unittest.main()
