# Investigação agressivo — 2026-11-16

## Motor central de oportunidades (papel)

- `engine/opportunity_engine.py`: classifica setups por regime, R/R, distância de stop e histórico.
- `paper_ring.py`: só abre se score >= 25. Regista o score na posição e no Telegram.
- `regime_select.py`: prioriza lado adequado ao regime.

## Ações e metais (papel)

- `engine/macro_oportunidades.py`: gera sinais LONG e SHORT a partir de velas diárias de contratos não-cripto da OKX.
- Usa o mesmo `opportunity_engine` e `regime_select`.
- Distingue elegíveis (X-Perp vivo) de apenas informativos.
- Não envia ordens reais. Produção intacta.

## Capacidade LONG/SHORT

- Cripto: longs sem veto BTC; SHORT_SOBRECOMPRA em papel.
- Ações/metais: LONG e SHORT em papel via macro_oportunidades.

## Regra de activação real

Quando uma estratégia demonstrar vantagem líquida consistente em papel (≥ 25 op., R > 0, kill não activado), pode ser candidata a real individual com limites já autorizados. Proposta explícita antes de qualquer activação.

Produção intacta.
