# Investigação agressivo — 2026-11-16

## Motor central de oportunidades (papel)

- `engine/opportunity_engine.py`: classifica setups por regime, R/R, distância de stop e histórico.
- `paper_ring.py`: só abre se score >= 25. Regista o score na posição e no Telegram.
- `regime_select.py`: prioriza lado adequado ao regime.

## Capacidade LONG/SHORT

- Longs sem veto BTC.
- SHORT_SOBRECOMPRA em papel.
- paper_trend e paper_bounce com limites aumentados.

## Regra de activação real (Rui, 2026-11-16)

Quando uma estratégia demonstrar vantagem líquida consistente em papel
(R médio > 0, amostra suficiente, kill não activado), pode ser candidata
a activação automática em dinheiro real, **individualmente** e com os
limites de risco já autorizados.

Condições mínimas antes de propor:
- ≥ 25 operações em papel
- R médio > 0
- não morta pelo kill
- proposta explícita antes de qualquer activação

Produção intacta até essa proposta ser aceite.
