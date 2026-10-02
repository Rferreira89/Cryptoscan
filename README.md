# Cryptoscan — motor de análise e sinais

Scanner de criptomoedas para operar em **spot na Bybit UE** (pares em USDC, só compras, sem alavancagem). Corre sozinho no GitHub Actions de 15 em 15 minutos.

- Página: https://rferreira89.github.io/Cryptoscan/scanner/
- Dados publicados: ramo `data` (`scan.json`, `state.json`, `audit.jsonl`, `resumo.txt`)
- Paragem de emergência: criar um ficheiro `STOP` na raiz do repositório

## Estado de validação

Nenhuma estratégia está validada. O backtest (2021 a 2026, custos incluídos) deu expectativa negativa para as estratégias de 4H, e as duas hipóteses em diário falharam a reserva.

Por decisão do utilizador (2026-10-02, `real_money_unvalidated` em `engine/config.py`), os sinais são mesmo assim emitidos como operações reais, com estas salvaguardas:

- risco por operação reduzido a metade (0,5%) enquanto a estratégia não estiver validada
- sem compras novas com o BTC abaixo da média de 200 dias
- travão de perdas: −3R num dia, −6R numa semana ou 3 perdas seguidas suspendem sinais novos
- cada alerta traz o registo da estratégia no backtest

Para voltar ao modo de simulação: `{"real_money_unvalidated": false}` em `config.json`.

## Como está organizado

| Pasta | Conteúdo |
|---|---|
| `engine/sources.py`, `venue.py` | Dados de mercado (Binance, OKX, KuCoin) e lista/preços da Bybit UE |
| `engine/validate.py` | Validação de velas; dados inválidos nunca geram sinal |
| `engine/scanner.py` | Universo, filtro de liquidez, orquestração de cada scan |
| `engine/indicators.py`, `structure.py`, `analysis.py` | Indicadores, estrutura de mercado, price action |
| `engine/volume.py`, `liquidity.py`, `derivatives.py` | Volume e fluxo, liquidez, derivados (OKX) |
| `engine/regime.py`, `strategies.py`, `risk.py`, `confluence.py` | Regime, estratégias, plano de risco, score |
| `engine/signals.py`, `trade.py` | Decisão em 10 passos, ciclo de vida dos sinais, gestão da operação |
| `engine/paper_trend.py` | Filtro de mercado (BTC vs média de 200 dias) e tendência diária em papel |
| `engine/backtest.py`, `stats.py`, `validation.py` | Backtest, métricas, walk-forward, Monte Carlo, veredicto |
| `engine/alerts.py`, `run.py` | Telegram e execução de um scan |
| `engine/monitor.py` | Passagem de 5 minutos: stops, objetivos e respostas do Telegram |
| `engine/ledger.py`, `inbox.py` | Registo de operações e confirmação de execuções |
| `engine/events.py`, `review.py`, `reports.py` | Calendário de eventos, revisão das estratégias, relatórios |
| `tools/` | Descarga de histórico, backtest completo e investigação |
| `backtest/` | Resultados publicados |
| `tests/` | Testes automáticos; correm antes de cada scan |
| `scanner/` | Página para telemóvel |

## Telegram

- Botões "Executei" / "Não executei" em cada alerta de compra.
- `/preco LINK 14.25` regista o preço real de entrada.
- Relatório diário às 8h (Lisboa) e semanal à segunda-feira.

## Manutenção

- `engine/events.py`: acrescentar as datas do CPI de 2027 quando o BLS as publicar (o sistema avisa quando o calendário fica desatualizado).
- Uma estratégia desligada pela revisão automática só volta a ligar apagando-a de `disabled` no `state.json` do ramo `data`.

## Parâmetros

Valores por omissão em `engine/config.py`; podem ser alterados num `config.json` na raiz (por exemplo `{"risk_pct": 0.5}`).

## Refazer o backtest

1. Correr o workflow "Historico para backtest" (atualiza o ramo `history`).
2. `python -m tools.run_backtest <pasta_do_historico>` e `python -m tools.research <pasta_do_historico>`.
3. Publicar `backtest/*.json`.

## Limitações conhecidas

- A API da Bybit recusa ligações do GitHub: preços e pares da Bybit UE vêm da CoinGecko; não há passo de preço nem quantidade mínima por ordem.
- Derivados só da OKX.
- O acompanhamento ao vivo usa o preço de cada scan (15 minutos): movimentos mais curtos podem não ser vistos.
- O backtest usa os ativos hoje listados (viés de sobrevivência) e velas de 4H.
