# Diário de investigação

**Hipóteses testadas contra esta reserva: 9** (6 neste diário: compra de
quedas, compressão, oversold bounce 4H, day trade 1H, bounce com outras
saídas, sweep a mercado; mais 3 no diário de afinação, H1 a H3).
Atualizado em 2026-10-13. Quanto maior este número, maior a probabilidade
de uma hipótese passar por sorte: com 9 testes, a probabilidade de pelo
menos um falso positivo a 5% já ronda os 37% (e as várias configurações
de cada grelha aumentam-na ainda mais).

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

3. (TESTADA em 2026-10-13, ver entrada "Oversold Bounce no 4H com uma
   saída melhor": NÃO VALIDADA — PARA PAPEL.) **Oversold Bounce
   no 4H com uma saída melhor.** Origem: em 2026-10-11 o gatilho do
   Oversold Bounce foi o primeiro a bater o acaso nos momentos de entrada
   (percentil 99,5 fora da amostra), mas a saída original (stop largo,
   7,8% em média; 1.º objetivo perto; stop na entrada depois do 1.º) só
   chegava ao empate. Do lado contrário, as estratégias ao vivo têm entradas
   piores do que o acaso, mas a sua forma de sair dá +0,06R mesmo com
   entradas ao acaso (backtest/random_baseline.json). Hipótese: o gatilho do
   Oversold Bounce com uma destas saídas tem vantagem. O GATILHO NÃO MUDA
   (exatamente o de `tools/research_bounce.signals`, sem filtro da EMA200
   da moeda). Saídas (escritas antes de qualquer teste, iguais às do papel
   ao vivo em `engine/paper_bounce.py`):
   - V1 saída do sistema ao vivo: `engine/risk.plan` com o stop do gatilho
     e a entrada ao preço de abertura (objetivos em níveis reais com mínimo
     de 1R, vendas parciais do plano, stop na entrada depois do 1.º);
     tempo máximo de 30 dias; sem operação se o plano for recusado;
   - V2 stop curto: fecho da vela do gatilho menos 1,5 ATR14; um único
     objetivo a 2R; sem passar o stop para a entrada; saída ao fim de 3 dias;
   - V3 stop original do gatilho; um único objetivo a 2R; sem passar o stop
     para a entrada; saída ao fim de 3 dias.
   Grelha (6): {V1, V2, V3} × X ∈ {25, 30}. Mesma carteira (4 de 25%, uma
   por moeda, primeiro o RSI mais baixo), mesmos custos (0,25% + 0,1% por
   lado), mesma janela e walk-forward. Critérios: os seis de sempre MAIS o
   teste contra o acaso (mesma geometria de cada saída) acima do percentil
   95. AVISO a escrever no veredicto: a reserva já foi usada por 8
   hipóteses, por isso um bom resultado aqui só conta como indício; a prova
   tem de vir do papel ao vivo (`engine/paper_bounce.py`, a correr desde
   2026-10-11 com G0, V1, V2 e V3 em paralelo, X=25). Veredicto máximo:
   CANDIDATA. Nada é ligado ao vivo.

4. (PEDIDA em 2026-10-11.) **Funding muito negativo com o preço a
   aguentar (4H, só compras).** Lógica: funding muito negativo nos
   perpétuos quer dizer que há muita gente vendida a pagar para manter a
   posição; se o preço não cai, essas posições acabam por ser fechadas à
   força e empurram o preço para cima. É informação de derivados, diferente
   das velas onde já se procurou muito. Dados: ramo `history`, pasta
   `funding/` (funding de 8h dos perpétuos USDT da Binance, ficheiros
   mensais públicos; só até ao último mês completo, por isso a janela acaba
   aí). Universo: TODAS as moedas com funding (decisão do Rui: não
   restringir às grandes; a divisão grandes/pequenas é só informativa).
   Regra: média do funding das últimas 3 liquidações (24h) negativa E
   abaixo do percentil P do funding da própria moeda nos 90 dias
   anteriores (só dados já publicados na hora da decisão); gatilho: fecho
   de 4H acima do máximo da vela anterior; entrada na abertura seguinte;
   stop no fecho menos 1,5 ATR14 de 4H; um objetivo a 2R; sem stop na
   entrada; saída ao fim de 3 dias. Grelha (4): P ∈ {10, 5} × exigir BTC
   acima da SMA200 ∈ {sim, não}. Mesma carteira, custos, janela e critérios
   (seis de sempre + contra o acaso acima do percentil 95).

5. (PEDIDA em 2026-10-11.) **Quebra com compradores agressivos (4H, só
   compras).** Lógica: uma quebra de máximo em que a maior parte do volume
   é de compras a mercado (taker) mostra procura real; a mesma quebra sem
   compradores agressivos é muitas vezes falsa. O programa hoje só olha
   para o volume total. Dados: coluna 7 do histórico de 4H (volume
   comprador). Universo: TODAS as moedas. Regra: BTC acima da SMA200
   diária; fecho de 4H acima do máximo das 20 velas anteriores; volume da
   vela pelo menos 1,5 vezes a média de 20; parte compradora (volume
   comprador / volume) pelo menos q; entrada na abertura seguinte; stop no
   mínimo da vela da quebra menos 0,1 ATR14 (no mínimo 1 ATR, no máximo
   3 ATR, senão não há operação); um objetivo a 2R; sem stop na entrada;
   saída ao fim de H dias. Grelha (4): q ∈ {0,55; 0,60} × H ∈ {3, 7}.
   Mesma carteira, custos, janela e critérios.

### Regra do papel (decisão do Rui, 2026-10-11)
Qualquer hipótese que fique acima do percentil 95 contra o acaso fora da
amostra vai logo para papel ao vivo, mesmo que falhe outros critérios. O
agente de investigação não mexe em engine/: escreve no veredicto "PARA
PAPEL" e a ligação ao papel é feita numa sessão com o Rui, seguindo o
padrão de `engine/paper_bounce.py`: só mensagens marcadas
PAPEL, sem botões, sem ocupar vagas reais, protegida por try/except no
scan, com testes, e com todos os testes a passar antes do push. O papel
junta dados que nenhum teste viu, e é aí que se decide. Dinheiro real só
com o veredicto CANDIDATA, 30 operações ou 8 semanas de papel, e o sim do
Rui.

### Sucessores da arena (decisão do Rui, 2026-10-11)
Quando um concorrente morre na arena (`engine/arena.py`: 20 ou mais
operações e R médio <= -0,2R ou abaixo da mediana ao acaso), a investigação
faz a autópsia das operações dele, escreve ANTES de testar um sucessor com
uma correção principal que ataque a causa encontrada, testa-o com o método
completo e regista aqui o par. Um sucessor nunca substitui o morto em
silêncio: entra na arena como concorrente novo (via papel, numa sessão com
o Rui), e o morto fica registado. Um por corrida, na segunda vaga.

| Morto | Data da morte | Causa encontrada | Sucessor | Veredicto |
|---|---|---|---|---|
| PULLBACK, BREAKOUT, LIQUIDITY_SWEEP, TREND_DAILY, REJEITADOS | 2026-10-13 (forma recente, 90 dias) | ver entrada de 2026-10-13 | LIQUIDITY_SWEEP → SWEEP_MERCADO (os outros ficam por agora sem sucessor, ver autópsia) | NÃO VALIDADA (2026-10-13; percentil 4,8 contra o acaso) |

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

## 2026-10-13 — Pré-registo (escrito antes de qualquer teste desta corrida)

Duas vagas: a primeira para a fila do Rui (hipótese 3, Oversold Bounce com
uma saída melhor, regras e grelha já fixadas na fila; código
`tools/research_bounce_exits.py`) e a segunda para um sucessor da arena.

### Autópsia dos mortos (2026-10-13, janela de 24 meses, todas as moedas)

Morreram cinco lutadores no combate de hora a hora (forma recente de 90
dias): PULLBACK (−0,085R, 54 op.), LIQUIDITY_SWEEP (−0,181R, 50),
BREAKOUT (−0,411R, 37), TREND_DAILY (−0,611R, 26) e REJEITADOS (−0,073R,
76). Autópsia feita com os setups do motor ao vivo (`engine/backtest.
candidates` + `simulate`, score ≥ mínimo, BTC acima da SMA200) nos últimos
24 meses de 62 moedas do ramo `history` (o ledger real só tem 10 operações
fechadas, poucas para concluir).

- **BREAKOUT** (102 op., −0,47R, 22% de acerto): 61% dos stops em menos de
  um dia; nas 6 velas depois da entrada o preço desce em média 0,16R a
  0,21R; 74 de 102 entradas vêm depois de uma subida de mais de 3% em 6
  velas. Mesmo sem custos perde −0,28R. Causa: as quebras de 4H revertem
  neste mercado (entra-se no fim do movimento). A correção natural
  (esperar o reteste) já foi rejeitada, e a quebra com compradores
  agressivos é a hipótese 5 da fila do Rui: **sem sucessor novo hoje**.
- **PULLBACK** (161 op., −0,086R): sem custos ficaria em +0,08R; as perdas
  não têm um padrão claro (hora, regime e distância do stop dão diferenças
  pequenas e instáveis). **Causa clara não encontrada**: sem sucessor.
- **TREND_DAILY**: é a tendência diária, já rejeitada na reserva em 2026-10;
  sem correção nova. **REJEITADOS** é um grupo de controlo (o que os
  filtros deitam fora), não uma estratégia: não leva sucessor.
- **LIQUIDITY_SWEEP** (154 op., −0,287R, 34% de acerto): diferença grande
  conforme a forma de entrar. Quando a abertura seguinte já está dentro da
  zona de entrada e a operação abre logo (104 op.), dá −0,17R; quando a
  ordem limite fica à espera e só é preenchida mais tarde, com o preço a
  voltar para baixo (50 op.), dá −0,54R e o preço continua a cair depois
  (−0,14R nas 6 velas seguintes). É seleção adversa: a ordem limite só é
  apanhada quando o sweep está a falhar. Causa encontrada (com cautela:
  cerca de 2 desvios-padrão).

### Sucessor: SWEEP_MERCADO (LIQUIDITY_SWEEP sem ordem limite à espera)

- **Correção única**: o setup, o stop, os objetivos e as vendas parciais
  são exatamente os do LIQUIDITY_SWEEP ao vivo (score ≥ mínimo, BTC acima
  da SMA200 no último dia fechado); a única mudança é a execução: a
  operação abre a mercado na abertura da vela de 4H seguinte ao sinal ou
  não abre (nada de ordem limite à espera durante 3 velas).
- **Grelha (2, escrita antes de testar)**: A = abre sempre na abertura
  seguinte (se estiver entre o stop e o 1.º objetivo); B = só abre se a
  abertura seguinte estiver dentro da zona de entrada ou abaixo do topo.
- Stop na entrada depois do 1.º objetivo (como ao vivo); saída por tempo
  ao fim de 30 dias; carteira de 4 posições de 25%, uma por moeda, primeiro
  o score mais alto; custos 0,25% + 0,1% por lado; mesma janela,
  walk-forward e os sete critérios (contra o acaso: mesma geometria, ±90
  velas). Código: `tools/research_sweep_market.py`.
- Expectativa declarada: sem custos a entrada na abertura ficou perto de
  zero (−0,03R), por isso o mais provável é NÃO VALIDADA; o teste serve
  para confirmar ou afastar a causa.

## 2026-10-13 — Oversold Bounce no 4H com uma saída melhor (fila do Rui, hipótese 3)

**Veredicto: NÃO VALIDADA — PARA PAPEL.** Falha 3 dos 7 critérios (dobras
positivas, estabilidade da grelha, grandes moedas), mas fica acima do
percentil 95 contra o acaso fora da amostra (percentil 100). AVISO: a
reserva já foi usada por 8 hipóteses antes desta; um bom resultado aqui só
conta como indício. A prova tem de vir do papel e do combate.

- **Regras** (as da fila, fixadas antes de qualquer teste): gatilho
  exatamente o de `tools/research_bounce.signals` sem filtro da EMA200 da
  moeda; nenhuma saída entra se a abertura seguinte já estiver na média de
  20 velas ou acima (como no papel). V1 = plano do sistema ao vivo
  (`engine/risk.plan`, stop do gatilho, 30 dias); V2 = stop no fecho menos
  1,5 ATR14, um objetivo a 2R, sem stop na entrada, 3 dias; V3 = stop
  original, um objetivo a 2R, sem stop na entrada, 3 dias.
- **Grelha** (6): {V1, V2, V3} × X ∈ {25, 30}. Carteira de 4 × 25%, uma por
  moeda, primeiro o RSI mais baixo. Universo: 62 moedas.
- **Custos**: 0,25% + 0,1% por lado (objetivos são ordens limite).
- **Janela**: desenho 2024-10-11 a 2026-04-10; reserva 2026-04-11 a
  2026-10-10 (última vela do histórico: 2026-10-11 08:00 UTC).
  Walk-forward: treino 183 dias, teste 91, 4 dobras.
- **Desenho**: 2 de 6 configurações positivas (33%), as duas com X=25:
  V3/X=25 +36,6% (Sharpe 0,83, queda máxima 19,2%, 113 op., 53,1% de
  acerto, +0,149R) e V2/X=25 +23,6% (Sharpe 0,62, 117 op., +0,144R). Com
  X=30 todas perdem (−14% a −34%). V1 (a saída do sistema ao vivo) perde
  sempre (−31% e −34%, −0,27R e −0,16R). Referência BTC>SMA200: +12,2%,
  Sharpe 0,40.
- **Walk-forward fora da amostra** (364 dias): +42,2%, Sharpe 1,48, queda
  máxima 11,2%, 55 operações, 60,0% ganhadoras, +0,278R (custo médio
  0,15R por operação). Dobras: +26,7% / −4,4% / +17,3% / 0,0% (sem
  operações, BTC abaixo da SMA200) = 2 de 4. Grandes moedas: −8,5%,
  Sharpe −0,34. Referência nas mesmas datas: +7,0%, Sharpe 0,41.
- **Configuração escolhida**: V3, X=25 (stop original, objetivo a 2R, sem
  stop na entrada, 3 dias).
- **Reserva (uma avaliação)**: +10,5%, Sharpe 2,50, queda máxima 1,1%, só
  10 operações (7 ganhadoras, +0,768R). Referência: +19,3%, Sharpe 1,66.
  Grandes moedas: +0,2%.
- **Contra o acaso** (1000 séries, ±90 velas, mesma geometria): fora da
  amostra (65 op.) +0,353R contra mediana ao acaso de −0,235R e p95 de
  −0,027R: **percentil 100**. Só walk-forward (55): percentil 100. Só
  reserva (10): percentil 98,7.
- **Critérios**: 1 sim; 2 NÃO (50%); 3 NÃO (33%); 4 NÃO (grandes moedas
  −8,5%); 5 sim (1,48 contra 0,41); 6 sim; 7 sim.
- **Período antigo (informativo, não conta)**: 2021-07-30 a 2024-10-10 a
  mesma configuração daria −41,7% (Sharpe −0,71, 181 operações, 38,1% de
  acerto, −0,21R) contra +57,4% da referência.
- **Leitura**: a saída a 2R sem stop na entrada transforma o empate do
  Bounce original num ganho no período recente, e o momento de entrada
  continua muito melhor do que o acaso. Mas o resultado é frágil: só
  funciona com RSI abaixo de 25 (com 30 perde em todas as saídas), não
  funciona nas grandes moedas, depende de poucos trimestres e no período
  antigo perde muito. A saída do sistema ao vivo (V1) estraga o gatilho.
- **Papel / ringue**: a configuração escolhida (V3, X=25) e a V2/X=25 já
  são lutadores do combate de hora a hora (BOUNCE_V3 "Violeta" e
  BOUNCE_V2 "Vera", com funções em `SINAIS` de `tools/arena_ringue.py`),
  por isso não é preciso acrescentar nada: entram em papel ao vivo
  sozinhos quando se qualificarem. No combate dos últimos 90 dias (ramo
  `arena`, 2026-10-13) a V3 leva 26 operações a +0,71R e a V2 26 a
  +0,73R, ambas acima do p95 do acaso; esses 90 dias estão dentro da
  reserva, por isso não são prova independente. Dinheiro real só numa
  sessão com o Rui.
- Código: `tools/research_bounce_exits.py` (e `tools/research_rlib.py`, que
  passou a aceitar planos calculados à abertura e saídas sem stop na
  entrada); teste sem look-ahead: `tests/test_research_bounce_exits.py`;
  números: `backtest/research_bounce_exits.json`.

## 2026-10-13 — SWEEP_MERCADO: LIQUIDITY_SWEEP sem ordem limite à espera (sucessor da arena)

**Veredicto: NÃO VALIDADA.** Falha 6 dos 7 critérios e fica abaixo da
mediana do acaso (percentil 4,8). A causa suspeita (seleção adversa da
ordem limite) não explica a perda: a entrada a mercado também perde.

- **Hipótese e grelha**: as do pré-registo acima (commit dff0269, antes dos
  testes). A = abre sempre na abertura seguinte; B = só se essa abertura
  estiver no topo da zona de entrada ou abaixo. Setups do motor ao vivo
  (`engine/backtest.candidates`), score ≥ mínimo, BTC acima da SMA200.
- **Janela**: desenho 2024-10-11 a 2026-04-10; reserva 2026-04-11 a
  2026-10-10; 62 moedas. Walk-forward: treino 183, teste 91, 4 dobras.
  Custos 0,25% + 0,1% por lado.
- **Desenho**: 0 de 2 configurações positivas. A: −30,2% (Sharpe −1,25,
  79 op., 35,4% de acerto, −0,316R). B: −20,1% (Sharpe −0,87, 59 op.,
  37,3%, −0,251R). Referência: +12,2%.
- **Walk-forward fora da amostra**: −17,8%, Sharpe −1,11, queda máxima
  20,1%, 51 operações, 35,3% de acerto, −0,336R (custo 0,18R). Dobras:
  −2,0% / −11,1% / −5,6% / 0,0% = 0 de 4. Grandes moedas: −16,5%.
  Referência: +7,0%, Sharpe 0,41.
- **Configuração escolhida**: B.
- **Reserva (uma avaliação)**: +8,6%, Sharpe 1,02, queda máxima 6,8%, 14
  operações (50% de acerto, +0,20R). Referência: +19,3%, Sharpe 1,66.
- **Contra o acaso** (1000 séries, ±90 velas): fora da amostra (65 op.)
  −0,220R contra mediana ao acaso de +0,025R e p95 de +0,288R:
  **percentil 4,8**. Walk-forward: percentil 1,3; reserva: 49,9.
- **Critérios**: 1 NÃO; 2 NÃO; 3 NÃO; 4 NÃO; 5 NÃO; 6 sim; 7 NÃO.
- **Período antigo (informativo)**: 2021-07-30 a 2024-10-10: −10,5%
  (Sharpe −0,30, 54 op., −0,13R) contra +57,4% da referência.
- **Leitura**: tirar a ordem limite não salva o sweep. O que falha é o
  próprio setup (o momento em que o sweep é identificado), não a forma de
  executar: com a mesma geometria, entrar ao acaso na mesma moeda dá mais.
  A diferença da autópsia entre preenchimento imediato e tardio era, pelo
  que se vê aqui, sobretudo ruído. O LIQUIDITY_SWEEP fica morto sem
  herdeiro. Nada foi ligado ao vivo nem ao ringue.
- Código: `tools/research_sweep_market.py`; teste sem look-ahead:
  `tests/test_research_sweep_market.py`; números:
  `backtest/research_sweep_market.json`.

## 2026-10-14 — Pré-registo (escrito antes de qualquer teste desta corrida)

Duas vagas: a primeira para a fila do Rui (hipótese 4, funding muito
negativo); a segunda para um sucessor da arena, se a autópsia encontrar
uma causa com correção; se não encontrar, a segunda vaga volta à fila
(hipótese 5, quebra com compradores agressivos). Arena em 2026-10-14
(scan.json do ramo `data`): 19 lutadores vivos, `recrutar` falso.

### Autópsia dos mortos sem sucessor (2026-10-14)

Mortos ainda sem sucessor registado: BOUNCE_1H, TURTLE, SQUEEZE_BB,
MOMENTUM e quatro shorts (SHORT_X30, SHORT_FLUXO, SHORT_TURTLE,
SHORT_ISOLADA). Números do combate (forma.json do ramo `arena`, 90 dias).

- **BOUNCE_1H** (combate: 198 op., −0,128R, acima do p95 do acaso, que é
  −0,178R; morreu por R médio ≤ −0,2R? não: por −0,128R abaixo de zero com
  20+ operações e forma). Autópsia nos últimos 24 meses de 1H (69 moedas,
  a mesma função `bounce_1h_trades` do ringue): 1749 operações, −0,279R,
  41,8% de acerto. Risco médio 5,5% mas custo médio de 0,25R por operação;
  sem custos ficaria em cerca de −0,03R. Por distância do stop: <1,5% →
  −0,61R a −0,70R; 1,5–2% → −0,42R; 2–3% → −0,33R; ≥3% → −0,16R (910 op.).
  Causa: os custos pesam, mas mesmo sem custos não há vantagem bruta nos
  24 meses, e o melhor grupo (stops largos) continua negativo. Exigir um
  stop mínimo não chega a zero. **Sem sucessor** (não há uma correção que
  ataque uma causa e possa tornar a regra positiva).
- **TURTLE** (191 op., +0,28R, mas o acaso com a mesma geometria dá
  mediana +0,76R e p95 +0,92R) e **SQUEEZE_BB** (66 op., −0,47R contra
  mediana −0,08R): a geometria de seguimento de tendência funciona com
  entradas ao acaso; o que estraga é o momento da entrada (comprar o
  rompimento). É a mesma causa da autópsia do BREAKOUT de 2026-10-13: as
  quebras de 4H revertem neste mercado. A correção que ataca esta causa já
  está escrita pelo Rui: a hipótese 5 da fila (só quebras com compradores
  agressivos). Por isso não se escreve um sucessor à parte: a segunda vaga
  é a hipótese 5, registada como resposta à família das quebras.
- **MOMENTUM** (31 op.): amostra curta para autópsia; fica para depois.
- **Shorts**: a investigação desta rotina é só de compras; ficam
  registados sem sucessor.

### Hipótese 4 (fila do Rui): funding muito negativo com o preço a aguentar

Regras e grelha as da fila. Detalhes de implementação fixados agora, antes
de testar (`tools/research_funding.py`):
- f24 = média das liquidações de funding com instante em (fecho − 24h,
  fecho] (com liquidações de 8h são as últimas 3; algumas moedas liquidam
  de 4 em 4 horas). Extremo = f24 < 0 e abaixo do percentil P dos f24
  calculados em cada liquidação dos 90 dias anteriores (até fecho − 24h).
  Exige pelo menos 60 dias de funding antes (o ficheiro começa em
  2024-08-01) e 30 valores na janela de 90 dias.
- Gatilho: fecho de 4H acima do máximo da vela anterior; entrada na
  abertura seguinte; stop no fecho menos 1,5 ATR14; um objetivo a 2R; sem
  stop na entrada; 3 dias. Prioridade: f24 mais negativo.
- Grelha (4): P ∈ {10, 5} × filtro do BTC acima da SMA200 ∈ {sim, não}.
- Janela: o funding do ramo `history` só chega ao último mês completo
  (2026-09-30), por isso a janela de 24 meses acaba aí: desenho
  2024-10-01 a 2026-03-31, reserva 2026-04-01 a 2026-09-30. Sem linha do
  período antigo (não há funding antes de 2024-08).
- Universo: as 66 moedas com funding.

### Segunda vaga — hipótese 5 (fila do Rui): quebra com compradores agressivos

Regras e grelha as da fila (`tools/research_taker_breakout.py`). Detalhe
fixado agora: "stop no mínimo 1 ATR" quer dizer que, se o mínimo da vela
da quebra menos 0,1 ATR ficar a menos de 1 ATR do fecho, o stop desce para
fecho − 1 ATR; a mais de 3 ATR não há operação. Média de volume das 20
velas anteriores (sem a da quebra). Prioridade: maior parte compradora.
Grelha (4): q ∈ {0,55; 0,60} × H ∈ {3, 7} dias. Janela de 24 meses até
ao último dia completo do histórico de 4H.

Expectativa declarada: as duas são de lógica económica razoável, mas a
família das quebras perdeu em tudo até hoje; o mais provável na 5 é NÃO
VALIDADA. Com 12 hipóteses contra esta reserva no fim desta corrida, só o
papel ao vivo pode provar alguma coisa.
