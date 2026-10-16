# Cryptoscan — motor de análise e sinais

Scanner de criptomoedas para operar em **spot e margem spot na Bybit UE** (pares em USDC). Corre sozinho no GitHub Actions: scan completo de 5 em 5 minutos e acompanhamento das operações abertas de minuto a minuto.

- Página: https://rferreira89.github.io/Cryptoscan/scanner/
- Dados publicados: ramo `data` (`scan.json`, `state.json`, `audit.jsonl`, `resumo.txt`)
- Paragem de emergência: criar um ficheiro `STOP` na raiz do repositório

## Objetivo e regras de equipa (decisão do Rui, 2026-10-14)

**Meta: levar o capital ao primeiro milhão (1 000 000 USDC).** Todos os agentes, analistas e lutadores trabalham para isto, com estas regras, que valem mais do que a pressa:

1. **Só operam com dinheiro estratégias que batem o acaso** (ringue de hora a hora: 20+ operações, R médio positivo e acima do percentil 95 das entradas ao acaso). A meta persegue-se com compostos e disciplina, **nunca aumentando o risco** para encurtar o caminho: uma perda grande atrasa a meta mais do que qualquer ganho a acelera. Marcos: 100, 250, 500, 1 000, 2 500, 5 000, 10 000 … (`engine/meta.py`, `/meta` no Telegram).
2. **Estratégias para todas as alturas do mercado.** Não queremos todos os analistas na mesma ideia. Hoje os campeões são quase todos da família "sobrevenda a virar"; a investigação deve procurar sobretudo famílias diferentes (tendência, rompimento, volatilidade, fluxo, derivados, macro, vendas a descoberto) e testá-las por regime: o ringue longo (`arena-longo.yml`, ramo `arena-longo`, `longo.json`) dá o resultado de cada lutador no último ano separado por **subida, lateral e descida**. Uma hipótese que ganhe num regime onde os campeões atuais não operam vale mais do que mais uma variante da sobrevenda.
3. **Diversificação:** no máximo 2 operações reais abertas da mesma família (`engine/promo.py`, `MAX_PER_FAMILY`).
4. **Prova real:** um campeão que no dinheiro real fique muito abaixo do combate é suspenso automaticamente.
5. **Regresso:** famílias mortas voltam com nome novo quando o regime muda, se o ringue longo mostrar que ganham nesse regime.
6. **Lugar no escritório só para quem leva a carteira ao objetivo (diretriz do Rui, 2026-10-15).** O próximo marco da meta é para ser atingido. Para entrar, bater o acaso no ringue; no dinheiro real, quem tiver 10 operações reais com resultado médio negativo perde o lugar até provar de novo (`engine/promo.py`, `LUCRO_MIN_N`). Cada lutador mostra o seu contributo real em USDC para o objetivo (`/meta`, cartão do lutador). Nenhuma diretriz autoriza mais risco: chega-se ao objetivo com operações lucrativas, não com apostas maiores.

## Código de conduta (a forma de pensar da equipa, decisão do Rui, 2026-10-16)

Todos os agentes (Diretor, departamentos, lutadores e agentes agendados) pensam assim. Cada princípio está ligado a regras que o programa cumpre (`engine/meta.py`, `CODIGO`; `/codigo` no Telegram):

1. **Primeiro proteger, depois ganhar.** Stop antes de entrar, risco sempre igual e pequeno; depois do TP1 a operação já não pode dar perda.
2. **Pensar em probabilidades, não em certezas.** Uma operação não importa; contam 100. Uma perda com as regras cumpridas não é um erro.
3. **Só entrar com vantagem provada.** Sem palpites: só campeões que batem o acaso, com evidência verificável e histórico positivo na fase atual do mercado.
4. **Paciência: esperar pela bola certa.** Entra-se quando o gatilho vira, nunca enquanto o preço cai. Ficar parado também é uma decisão.
5. **Cortar as perdas depressa, deixar os ganhos correr.** O stop sai sem discussão; depois do TP1 o resto segue para o objetivo final.
6. **Humildade: o mercado muda.** Quem perde a forma sai do ringue; quem não é lucrativo no dinheiro real perde o lugar.
7. **Aprender com cada operação.** Quem acerta, o que o Diretor rejeitou e porquê, e as lições de cada semana.
8. **Disciplina acima da emoção.** Nada de vingança depois de perder nem de euforia depois de ganhar; nunca mais risco para recuperar.

As rejeições do Diretor citam o princípio que defendem. Nenhum princípio autoriza mais risco nem menos honestidade sobre os resultados.

## Estado de validação

Nenhuma estratégia está validada. O backtest (2021 a 2026, custos incluídos) deu expectativa negativa para as estratégias de 4H, e as duas hipóteses em diário falharam a reserva.

Por decisão do utilizador (2026-10-02, `real_money_unvalidated` em `engine/config.py`), os sinais são mesmo assim emitidos como operações reais, com estas salvaguardas:

- posição fixa de 25 USDC por operação (decisão do utilizador), no máximo 2 operações em simultâneo incluindo a tendência diária; a posição é 25 USDC de margem própria vezes a alavancagem e encolhe até a perda no stop caber em 2,5 USDC (5% do capital, `max_risk_usdc` em `config.json`, decisão de 2026-10-03). `{"fixed_position_usdc": null}` volta à dimensão pelo risco
- alavancagem de swing (`swing_leverage`, teto de 10x por decisão do utilizador em 2026-10-07): multiplica a posição e o risco, limitada ao valor que mantém a liquidação estimada a pelo menos 2,5 vezes a distância do stop, com teto de 6x. `{"swing_leverage": 1}` desliga-a
- shorts em margem spot (`shorts`, por decisão do utilizador): espelho das estratégias de compra (`engine/short.py`), só com o BTC abaixo da média de 200 dias. No backtest deram −0,22R por operação, igual às compras. `{"shorts": false}` desliga-os
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
- `/capital 80` atualiza o capital de trading usado nos cálculos.
- Relatório diário às 8h (Lisboa) e semanal à segunda-feira.

## Agentes agendados

- Vigia (de 6 em 6 horas): relança o scanner se tiver parado.
- Notícias e eventos (diário): mantém `engine/events_extra.json`.
- Investigação (domingo): testa uma hipótese nova e regista em `backtest/investigacao.md`.
- Auditoria (sábado): testes, coerência do registo e calendário.
- Revisão de 30 dias (2026-11-01).

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
- O acompanhamento ao vivo usa o preço de cada passagem (1 minuto): movimentos mais curtos podem não ser vistos.
- O backtest usa os ativos hoje listados (viés de sobrevivência) e velas de 4H.
