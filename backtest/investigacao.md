# Diário de investigação

**Hipóteses testadas contra esta reserva: 7** (4 neste diário: compra de
quedas, compressão, oversold bounce 4H, day trade 1H; mais 3 no diário de
afinação, H1 a H3). Atualizado em 2026-10-11. Quanto maior este número,
maior a probabilidade de uma hipótese passar por sorte: com 7 testes, a
probabilidade de pelo menos um falso positivo a 5% já ronda os 30%.

Uma hipótese por entrada, com o veredicto. Método: `tools/research.py`
(decisão no fecho, execução na abertura seguinte, 0,25% de comissão + 0,1% de
slippage por lado desde 2026-10-07 (antes 0,1%), walk-forward, seis critérios declarados a priori, reserva
avaliada uma única vez). Janela desde 2026-10-03 (decisão do Rui): últimos 24
meses, 18 de desenho e 6 de reserva; menos de 40 operações fora da amostra
dá "AMOSTRA INSUFICIENTE".

## Fila de hipóteses pedidas pelo Rui (testar por esta ordem, antes de escolher outras)

1. (TESTADA em 2026-10-11, ver entrada "Oversold Bounce no 4H": NÃO
   VALIDADA.) **Oversold Bounce
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

2. (TESTADA em 2026-10-11, ver entrada "Day trade em 1H": NÃO VALIDADA.)
   **Day trade em 1H: recuo à EMA20 de 1H a favor da tendência de 4H.**
   O Rui quer day trade, NÃO scalp: nada abaixo de velas de 1H e nenhuma
   operação pensada para durar minutos. Lógica: dentro de uma tendência de
   4H, os recuos de 1H até à média curta são realização de lucros e não
   inversão; a vela que recupera a média retoma a tendência. O risco
   principal está declarado à partida: com stops curtos, a comissão real
   (0,25% + 0,1% de slippage por lado, cerca de 0,7% ida e volta) come uma
   parte grande de cada R, por isso a regra exige uma distância mínima de
   stop. Regra (só compras):
   - contexto: BTC acima da SMA200 diária; na moeda, EMA20 > EMA50 no 4H e
     fecho da última vela de 4H fechada acima da EMA50 de 4H (sem
     look-ahead: só velas de 4H já fechadas na hora da decisão);
   - gatilho em 1H: a vela fechada tem mínimo igual ou abaixo da EMA20 de
     1H e fecha acima dela, com RSI14 de 1H entre 40 e 60;
   - entrada na abertura da vela de 1H seguinte;
   - stop abaixo do mínimo das últimas 3 velas de 1H menos 0,2 ATR14 de
     1H; se ficar a menos de D% da entrada, a operação NÃO se faz (não se
     alarga o stop);
   - um único objetivo a k R; saída obrigatória ao fim de H horas;
   - no máximo 1 operação por moeda e 2 ao mesmo tempo (opção B do Rui).
   Grelha (6, escrita antes de testar): k ∈ {1,5; 2} × D ∈ {1,5%; 2,5%} com
   H = 24, mais H = 12 com k = 1,5 para D = 1,5% e D = 2,5%.
   Dados: ramo `history`, pasta `1h/` (cerca de 25 meses), carregados com
   `backtest.load_all(pasta + "/1h", min_bars=2000, tf=3600)`; o 4H vem da
   raiz do mesmo ramo. O teste contra o acaso tem de usar velas de 1H (o
   `tools/random_baseline.py` assume 4H: adaptar o passo para 3600 s e a
   janela para ±360 velas, ou seja os mesmos ±15 dias).
   Critérios: os seis de sempre MAIS o teste contra o acaso acima do
   percentil 95 MAIS reportar o custo médio por operação em R. Veredicto
   máximo: CANDIDATA (papel durante 30 operações ou 8 semanas antes de
   dinheiro real). Nada é ligado ao vivo.

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

## 2026-10-11 — Oversold Bounce no 4H (fila do Rui, hipótese 1)

**Veredicto: NÃO VALIDADA.** Falha 4 dos 7 critérios (dobras positivas,
estabilidade da grelha, grandes moedas, referência). Passa o teste contra o
acaso, o que é a primeira vez que acontece neste projeto, mas isso sozinho
não chega (ver leitura).

- **Hipótese e regras** (escritas e guardadas em commit antes dos testes,
  ac48883): com o BTC acima da SMA200 diária, RSI14 de 4H abaixo de X numa
  das últimas 3 velas; gatilho = fecho acima do máximo da vela anterior com
  RSI a subir; entrada na abertura seguinte; stop no mais baixo de (mínimo
  das últimas 6 velas menos 0,1 ATR) e (fecho menos 1,25 ATR); 1.º objetivo
  na média de 20 velas de 4H (50%), 2.º no máximo dos 7 dias anteriores;
  depois do 1.º o stop passa para a entrada; saída por tempo ao fim de H
  dias; sem operação se o 1.º objetivo ficar a menos de 1% do fecho. Até 4
  operações de 25%, uma por moeda. Universo: 63 moedas.
- **Grelha** (5, a da fila): X=25/H=3, X=25/H=7, X=30/H=3, X=30/H=7,
  X=30/H=3 com a moeda acima da EMA200 diária.
- **Custos**: 0,25% de comissão + 0,1% de slippage por lado (objetivos são
  ordens limite, sem slippage).
- **Janela**: desenho 2024-10-10 a 2026-04-09; reserva 2026-04-10 a
  2026-10-09. Walk-forward: treino 183 dias, teste 91, 4 dobras.
- **Desenho**: só 1 de 5 configurações positiva (20%). X=25/H=3: +19,8%,
  Sharpe 0,59, queda máxima 17,9%, 119 operações, 62,2% ganhadoras,
  +0,04R. As outras: −10,8% a −49,2% (−0,09R a −0,23R). Manter 7 dias é
  sempre pior do que 3; o filtro da EMA200 da moeda piora. Referência
  BTC>SMA200 no desenho: +12,2%, Sharpe 0,40, queda máxima 33,4%.
- **Walk-forward fora da amostra** (364 dias): +10,3%, Sharpe 0,51, queda
  máxima 22,1%, 93 operações, 57,0% ganhadoras, −0,04R médio (retorno
  médio +0,49% por operação; o R médio é negativo porque as perdas caem
  nas operações de stop mais curto). Dobras: +14,6% / −15,5% / +13,8% /
  0,0% (sem operações, BTC abaixo da SMA200) = 2 de 4. Grandes moedas:
  −1,1%, Sharpe 0,04. Referência nas mesmas datas: +11,7%, Sharpe 0,60.
- **Configuração escolhida**: X=25, H=3, sem filtro da moeda.
- **Reserva (uma avaliação)**: +9,9%, Sharpe 2,52, queda máxima 1,1%, mas
  só 10 operações (7 ganhadoras, +0,97R médio). Referência no mesmo
  período: +18,7%, Sharpe 1,62. Grandes moedas na reserva: −0,1%.
- **Contra o acaso** (1000 séries, ±90 velas, mesma geometria): fora da
  amostra completo (103 operações) +0,056R contra mediana ao acaso de
  −0,246R e p95 de −0,103R: percentil 100. Só walk-forward (93): −0,042R
  contra −0,264R, percentil 99,5. Só reserva (10): percentil 100.
- **Critérios**: 1 sim (à justa: Sharpe 0,51, mínimo 0,5); 2 NÃO (50%,
  mínimo 60%); 3 NÃO (20% da grelha, mínimo 75%); 4 NÃO (grandes moedas
  −1,1%); 5 NÃO (Sharpe 0,51 contra 0,60 da referência); 6 sim; 7 sim.
- **Período antigo (informativo, não conta)**: 2021-07-30 a 2024-10-09 a
  mesma configuração daria −45,0% (Sharpe −0,92, 182 operações, 46,2%
  ganhadoras, −0,20R) contra +57,4% da referência.
- **Leitura**: o momento de entrada é melhor do que o acaso (as entradas ao
  acaso com este stop e estes objetivos perdem cerca de −0,25R; as do
  gatilho ficam perto de zero). Mas "melhor do que o acaso" não é "ganha
  dinheiro": a geometria (stop largo, 7,8% em média; objetivo perto; stop
  na entrada depois do 1.º objetivo) é má, e o gatilho só a compensa até ao
  empate. O resultado depende de uma única configuração em cinco, de moedas
  pequenas (nas grandes dá zero) e no período antigo perde. Com 7 hipóteses
  já testadas contra esta reserva, um percentil alto numa amostra de 103
  operações não pode ser lido como prova. Nada foi ligado ao vivo.
- Código: `tools/research_bounce.py` e `tools/research_rlib.py`; teste sem
  look-ahead: `tests/test_research_bounce.py`; números:
  `backtest/research_bounce.json`.

## 2026-10-11 — Day trade em 1H: recuo à EMA20 de 1H a favor da tendência de 4H (fila do Rui, hipótese 2)

**Veredicto: NÃO VALIDADA.** Falha os 7 critérios. É o pior resultado até
hoje: perde em todas as configurações e é pior do que entrar ao acaso.

- **Hipótese e regras** (escritas e guardadas em commit antes dos testes,
  ac48883): BTC acima da SMA200 diária; na moeda, EMA20 > EMA50 e fecho
  acima da EMA50 na última vela de 4H já fechada; gatilho em 1H: mínimo na
  EMA20 de 1H ou abaixo e fecho acima, RSI14 de 1H entre 40 e 60; entrada na
  abertura seguinte; stop no mínimo das últimas 3 velas menos 0,2 ATR14 de
  1H, sem operação se ficar a menos de D; um objetivo a k R; saída ao fim
  de H horas; uma operação por moeda, 2 ao mesmo tempo, 25% cada.
  Universo: 63 moedas com 1H e 4H.
- **Grelha** (6, a da fila): H=24 com k ∈ {1,5; 2} × D ∈ {1,5%; 2,5%};
  H=12 com k=1,5 e D ∈ {1,5%; 2,5%}.
- **Custos**: 0,25% + 0,1% por lado.
- **Janela**: desenho 2024-10-10 a 2026-04-09; reserva 2026-04-10 a
  2026-10-09 (1H). Walk-forward: treino 183 dias, teste 91, 4 dobras.
  Correção de implementação feita antes de ver qualquer resultado: o início
  da janela passou a ser calculado pelo histórico de 1H do BTC (a primeira
  versão usava a moeda mais recente e não deixava dobras).
- **Desenho**: 0 de 6 configurações positivas. Retorno de −81,7% a −95,5%
  em 18 meses, Sharpe de −2,8 a −5,5, 950 a 1760 operações, 33% a 40%
  ganhadoras, −0,15R a −0,24R por operação. Referência: +12,2%.
- **Custo médio por operação**: 0,20R com D=2,5% (stop médio de 4,0%) e
  0,28R com D=1,5% (stop médio de 3,1%). Ou seja, mesmo sem custos a regra
  ficaria perto de zero ou negativa: os custos explicam a perda quase toda
  com D=2,5%, e com D=1,5% nem isso.
- **Walk-forward fora da amostra** (364 dias): −56,6%, Sharpe −2,12, queda
  máxima 61,7%, 550 operações, 35,1% ganhadoras, −0,151R. Dobras: −12,8% /
  −42,7% / −13,2% / 0,0% (sem operações) = 0 de 4. Grandes moedas: −54,2%.
  Referência nas mesmas datas: +11,7%, Sharpe 0,60.
- **Configuração escolhida**: k=2, D=2,5%, H=24 (a menos má).
- **Reserva (uma avaliação)**: −30,4%, Sharpe −2,71, queda máxima 35,2%,
  170 operações, 32,4% ganhadoras, −0,202R. Referência: +18,7%.
- **Contra o acaso** (1000 séries, ±360 velas de 1H): fora da amostra (720
  operações) −0,163R contra mediana ao acaso de −0,040R: percentil 0. Só
  walk-forward: percentil 1,2. Só reserva: percentil 0,7. O gatilho é PIOR
  do que entrar ao acaso com o mesmo stop e objetivo.
- **Critérios**: 1 NÃO; 2 NÃO; 3 NÃO; 4 NÃO; 5 NÃO; 6 NÃO; 7 NÃO.
- **Período antigo**: não existe histórico de 1H anterior à janela.
- **Leitura**: comprar o recuo à média curta em tendência é a mesma ideia
  do PULLBACK de 4H que já perdia, num prazo em que os custos pesam três
  vezes mais. Muitas operações (cerca de 2 por dia) multiplicam a perda em
  vez de a diluir. Com 0,7% de custos ida e volta, day trade em 1H com
  stops de 2% a 4% precisa de uma vantagem bruta acima de 0,2R por operação
  só para empatar; esta regra tem vantagem bruta nula ou negativa. Nada foi
  ligado ao vivo.
- Código: `tools/research_day1h.py`; teste sem look-ahead:
  `tests/test_research_day1h.py`; números: `backtest/research_day1h.json`.
