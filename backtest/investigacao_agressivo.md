# Investigação agressivo — 2026-11-16

## Motor central de oportunidades (papel)

- `engine/opportunity_engine.py`: classifica setups por regime, R/R, distância de stop e histórico.
- `paper_ring.py`: só abre se score >= 25. Regista o score na posição e no Telegram.
- `regime_select.py`: prioriza lado adequado ao regime.

## Capacidade LONG/SHORT

- Longs sem veto BTC.
- SHORT_SOBRECOMPRA em papel.
- paper_trend e paper_bounce com limites aumentados.

Produção intacta.
