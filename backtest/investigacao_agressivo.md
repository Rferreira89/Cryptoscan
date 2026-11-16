# Investigação agressivo — 2026-11-16

## Motor de decisão (papel)

- `engine/regime_select.py`: prioriza LONG em subida, SHORT em descida, ambos em lateral/desconhecido.
- `paper_ring.py` usa `regime_select.prefer` antes de abrir posição.

## Capacidade LONG/SHORT em papel

- paper_ring: longs sem veto BTC; MAX_POS=12; regime-aware.
- paper_trend: MAX_POS=8; market_ok não veto.
- paper_bounce: MAX_POS=8.
- SHORT_SOBRECOMPRA_X70V25 continua em papel.

Produção intacta.
