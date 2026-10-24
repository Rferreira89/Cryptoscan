"""(24/10) Volume minimo proporcional ao tamanho da ordem (OK do Rui)."""
import unittest

from engine import config, venue


class VolumeOrdem(unittest.TestCase):
    cfg = dict(config.DEFAULTS, min_venue_volume_usd=1500, venue_vol_por_ordem=200)

    def test_piso_afasta_moedas_mortas(self):
        v = {"pair": "SPK/USDC", "last": 1.0, "spread_pct": 0.1, "volume_usd": 58, "stale": False}
        ok, why = venue.check(v, 1.0, self.cfg)
        self.assertFalse(ok)
        self.assertIn("volume baixo na Bybit UE", why)

    def test_moeda_fina_passa_com_ordem_pequena(self):
        v = {"pair": "W/USDC", "last": 1.0, "spread_pct": 0.18, "volume_usd": 3565, "stale": False}
        self.assertTrue(venue.check(v, 1.0, self.cfg)[0])
        self.assertIsNone(venue.vol_ordem(v, 6, self.cfg))           # 6 USDC: precisa de 1200
        self.assertIn("ordem de 20 USDC", venue.vol_ordem(v, 20, self.cfg))   # precisa de 4000

    def test_spread_continua_igual(self):
        v = {"pair": "HUMA/USDC", "last": 1.0, "spread_pct": 0.44, "volume_usd": 50000, "stale": False}
        self.assertIn("spread elevado na Bybit UE", venue.check(v, 1.0, self.cfg)[1])

    def test_sem_volume_conhecido_nao_bloqueia_aqui(self):
        self.assertIsNone(venue.vol_ordem({"pair": "X/USDC"}, 20, self.cfg))


if __name__ == "__main__":
    unittest.main()
