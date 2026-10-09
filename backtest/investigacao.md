# Diário de investigação

Uma hipótese por entrada, com o veredicto. Método: `tools/research.py`
(decisão no fecho, execução na abertura seguinte, 0,1% de comissão + 0,1% de
slippage por lado, walk-forward, seis critérios declarados a priori, reserva
avaliada uma única vez). Janela desde 2026-10-03 (decisão do Rui): últimos 24
meses, 18 de desenho e 6 de reserva; menos de 40 operações fora da amostra
dá "AMOSTRA INSUFICIENTE".

## Fila de hipóteses pedidas pelo Rui (testar por esta ordem, antes de escolher outras)

1. (PEDIDA em 2026-10-09, testar na próxima execução.) **Oversold Bounce
   no 4H.** Lógica: em mercado de alta, quedas rápidas levam o RSI de 4H a
   sobrevenda por venda forçada; a primeira vela de recuperação marca o fim
   da pressão vendedora. Difere da "compra de quedas" de 2026-10-04
   (diário, sem gatilho) e do sweep de liquidez ao vivo (exige furar um
   fundo): aqui o gatilho é RSI + vela de recuperação no 4H. Regra (só
   compras, com o BTC acima da SMA200): RSI14 de 4H abaixo de X numa das
   últimas 3 velas; entrada na abertura seguinte a uma vela de 4H que fecha
   acima do máximo da vela anterior com RSI a subir; stop abaixo do mínimo
   da queda (mínimo de 1,25 ATR); objetivos na média de 20 velas de 4H e no
   último máximo relevante; saída ao fim de H dias se nada for atingido.
   Grelha (escrever antes de testar, no máximo 6): X ∈ {25, 30}; H ∈ {3, 7};
   exigir a moeda acima da sua EMA200 diária ∈ {sim, não} (com X=30, H=3).
   Critérios: os seis de sempre MAIS o teste contra o acaso
   (tools/random_baseline, mesma geometria) acima do percentil 95. Comissão
   de 0,25% por lado. Veredicto máximo: CANDIDATA (papel durante 30
   operações ou 8 semanas antes de dinheiro real).

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

## 2026-10-07 — Compressão de volatilidade seguida de expansão (diário)

**Veredicto: AMOSTRA INSUFICIENTE** (39 operações fora da amostra, mínimo 40).
Na prática é uma rejeição: falha 3 dos 6 critérios e só 2 das 12
configurações ganham no desenho. Uma operação a mais não mudaria nada.

- **Hipótese** (escrita e guardada em commit antes dos testes, 425ffdf): a
  volatilidade agrupa-se; com o BTC acima da SMA200, um fecho acima do máximo
  de uma caixa de N dias invulgarmente estreita (largura entre os q mais
  baixos dos últimos 120 dias) inicia um movimento para cima. Compra na
  abertura seguinte; saída ao fim de H dias, ou com fecho abaixo do meio da
  caixa, ou com o BTC abaixo da SMA200. Até 4 posições de 25%. Universo:
  64 moedas com histórico.
- **Grelha** (12): N ∈ {10, 20}; q ∈ {0,2; 0,4}; H ∈ {5, 10, 20}.
- **Custos**: 0,25% de comissão + 0,1% de slippage por lado (taxa real da
  Bybit UE), também na referência. A entrada de 2026-10-04 usou 0,1%.
- **Janela**: desenho 2024-10-02 a 2026-04-01; reserva 2026-04-02 a
  2026-10-01 (última vela do histórico: 2026-10-01). Walk-forward: treino
  183 dias, teste 91, 4 dobras.
- **Desenho**: 2 de 12 configurações positivas (17%). Com N=10 todas perdem
  (-21% a -40%). Melhores: N=20/q=0,4/H=20 com +14,8% (Sharpe 0,44, queda
  máxima 44,9%) e N=20/q=0,2/H=5 com +14,5%. Taxa de acerto entre 25% e 45%:
  o contrário de "acerto alto". Quedas máximas de 38% a 63%. Referência
  BTC>SMA200 no desenho: +12,2%, Sharpe 0,40, queda máxima 33,4%.
- **Walk-forward fora da amostra** (364 dias): +4,8%, Sharpe 0,32, queda
  máxima 37,4%, 39 operações (43,6% ganhadoras, +1,73% médio, melhor
  +106,5%, pior -30,2%). Dobras: -1,0% / +25,3% / -15,6% / 0,0% (sem
  operações) = 1 de 4 positivas. Grandes moedas: +33,1%, Sharpe 0,97, queda
  máxima 17,8%. Referência nas mesmas datas: +2,6%, Sharpe 0,23.
- **Configuração escolhida**: N=20, q=0,4, H=20. No desenho: 56 operações,
  39,3% ganhadoras, +2,74% médio, pior -36,9%, melhor +106,5%.
- **Reserva (uma avaliação)**: +25,4%, Sharpe 1,59, queda máxima 11,5%, mas
  só 5 operações (4 ganhadoras). Referência no mesmo período: +22,0%, Sharpe
  1,92. Cinco operações não provam nada.
- **Critérios**: 1 NÃO (Sharpe 0,32, mínimo 0,5); 2 NÃO (25% das dobras,
  mínimo 60%); 3 NÃO (17% da grelha, mínimo 75%); 4 sim; 5 sim (0,32 contra
  0,23, margem mínima); 6 sim.
- **Período antigo (informativo, não conta)**: 2021-11-27 a 2024-10-01 a
  mesma configuração daria +24,8% (Sharpe 0,39, queda máxima 52,7%, 95
  operações) contra +87,5% da referência (Sharpe 0,79).
- **Leitura**: a quebra a sair de uma caixa apertada não é melhor entrada do
  que a quebra simples já rejeitada. O pouco ganho vem de raras operações
  muito grandes (+100%), com acerto baixo e quedas fundas; é o perfil de uma
  aposta de cauda, não de uma vantagem. Única pista: nas grandes moedas o
  resultado é sempre melhor do que no universo todo (9 de 12 configurações
  positivas no desenho), como já tinha acontecido. Nada foi ligado ao vivo.
- Código: `tools/research_squeeze.py`; teste sem look-ahead:
  `tests/test_research_squeeze.py`; números: `backtest/research_squeeze.json`.
