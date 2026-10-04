# Diário de investigação

Uma hipótese por entrada, com o veredicto. Método: `tools/research.py`
(decisão no fecho, execução na abertura seguinte, 0,1% de comissão + 0,1% de
slippage por lado, walk-forward, seis critérios declarados a priori, reserva
avaliada uma única vez). Janela desde 2026-10-03 (decisão do Rui): últimos 24
meses, 18 de desenho e 6 de reserva; menos de 40 operações fora da amostra
dá "AMOSTRA INSUFICIENTE".

## Hipóteses anteriores a este diário (até 2026-10-02, período 2021-2026)

Nenhuma validada. 4H: recuo, quebra com reteste, sweep de liquidez, fundo de
range (cerca de -0,2R por operação, igual ao acaso). Diário: tendência
(quebra de máximos) e força relativa semanal (ganharam no desenho, perderam
na reserva). Única regra robusta: BTC acima da média de 200 dias.

## 2026-10-04 — Compra de quedas em mercado de alta (diário)

**Veredicto: AMOSTRA INSUFICIENTE** (19 operações fora da amostra, mínimo 40).
Além disso falha 2 dos 6 critérios: não seria validada mesmo com mais operações.

- **Hipótese** (escrita e guardada em commit antes dos testes): com o BTC
  acima da SMA200, uma queda de pelo menos k ATR20 em 3 dias é venda forçada
  e tende a recuperar. Compra na abertura seguinte, sem stop de preço, saída
  ao fim de H dias ou se o BTC fechar abaixo da SMA200. Até 4 posições de 25%.
  Universo: todas as moedas com histórico.
- **Grelha** (12): k ∈ {2, 3}; H ∈ {3, 5, 10}; exigir a moeda acima da sua
  SMA200 ∈ {sim, não}.
- **Janela**: desenho 2024-10-02 a 2026-04-01; reserva 2026-04-02 a
  2026-10-01. Walk-forward: treino 183 dias, teste 91, 4 dobras.
- **Desenho**: 8 de 12 configurações positivas (67%). Com k=3 quase não há
  operações (7 a 9 em 18 meses). Manter 10 dias é pior do que 3. O filtro
  "moeda acima da SMA200" piora sempre. Referência BTC>SMA200 no desenho:
  +15,3%, Sharpe 0,45, queda máxima 32,4%.
- **Walk-forward fora da amostra** (364 dias): +36,1%, Sharpe 1,23, queda
  máxima 20,4%, só 19 operações. Dobras: +14,2% / -2,1% / +21,7% / 0,0% (sem
  operações) = 2 de 4 positivas. Grandes moedas: +15,9%, Sharpe 1,08.
  Referência nas mesmas datas: +3,8%, Sharpe 0,28.
- **Configuração escolhida**: k=2, H=3, sem filtro da moeda. No desenho: 91
  operações, 51,6% ganhadoras, +1,68% médio, pior -19,6%.
- **Reserva (uma avaliação)**: +14,5%, Sharpe 1,51, queda máxima 5,6%, 11
  operações (média +5,1%, muito dependente de uma de +34,9%). Referência no
  mesmo período: +22,2%, Sharpe 1,93. Ou seja, positiva mas abaixo de
  simplesmente ter BTC. Com comissão real de 0,25%: +13,5%.
- **Critérios**: 1 sim; 2 NÃO (50% das dobras, mínimo 60%); 3 NÃO (67% da
  grelha, mínimo 75%); 4 sim; 5 sim; 6 sim.
- **Período antigo (informativo, não conta)**: 2021-07-30 a 2024-10-01 a
  mesma configuração daria -13,6% (Sharpe -0,13, 109 operações, -0,39% médio)
  contra +64,6% da referência.
- **Leitura**: o resultado fora da amostra vem de poucas operações em dois
  trimestres, com um ganho grande a pesar muito. Não há prova de vantagem.
  Nada foi ligado ao vivo.
- Código: `tools/research_dip.py`; teste sem look-ahead:
  `tests/test_research_dip.py`; números: `backtest/research_dip.json`.
