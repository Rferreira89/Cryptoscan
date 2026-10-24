# Diário de investigação

**Hipóteses testadas contra esta reserva: 20** (12 neste diário: compra de
quedas, compressão, oversold bounce 4H, day trade 1H, bounce com outras
saídas, sweep a mercado, funding negativo, quebra com compradores,
capitulação do mercado, atraso face ao BTC, resiliente, impulso de
amplitude; mais 8 no diário de afinação, H1 a H8). Atualizado em
2026-10-24 (sem hipótese nova nesta corrida nem na afinação). O
contador global do programa (`engine/hipoteses.py`, com os estudos fora do
programa em `backtest/hipoteses_offline.json`, contra dados que incluem
esta reserva) já vai em 57. Quanto maior este número, maior a
probabilidade de uma hipótese passar por sorte: com 20 testes, a
probabilidade de pelo menos um falso positivo a 5% já ronda os 64% (e as
várias configurações de cada grelha aumentam-na ainda mais).

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

4. (TESTADA em 2026-10-14, ver entrada "Funding muito negativo com o
   preço a aguentar": NÃO VALIDADA.) **Funding muito negativo com o preço a
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

5. (TESTADA em 2026-10-14, ver entrada "Quebra com compradores
   agressivos": NÃO VALIDADA.) **Quebra com compradores agressivos (4H, só
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
| BOUNCE_1H | 2026-10-14 (forma recente) | custos de 0,25R por operação e, mesmo sem custos, cerca de −0,03R em 24 meses (ver entrada de 2026-10-14) | sem sucessor (nenhuma correção única chega a zero) | — |
| TURTLE, SQUEEZE_BB | 2026-10-14 (forma recente) | o momento da entrada (comprar o rompimento): a mesma geometria com entradas ao acaso dá muito mais | família das quebras → QUEBRA_COMPRADORES (hipótese 5 da fila) | NÃO VALIDADA (2026-10-14; percentil 12,8 contra o acaso) |
| MOMENTUM, SHORT_X30, SHORT_FLUXO, SHORT_TURTLE, SHORT_ISOLADA | 2026-10-14 (forma recente) | MOMENTUM: 31 operações, pouco para autópsia; shorts fora desta investigação (só compras) | sem sucessor por agora | — |
| RETESTE, BRK_ESPACO | 2026-10-14 (forma recente) | família "comprar a quebra em 4H", já esgotada (ver 2026-10-14) | sem sucessor | — |
| CAPITULACAO | 2026-10-15 (forma recente; 20 op., −0,218R) | capitulação isolada numa moeda perde; só os colapsos do mercado inteiro recuperam, e o filtro BTC>SMA200 deita-os fora (ver entrada de 2026-10-15) | CAPITULACAO → CAP_MERCADO | AMOSTRA INSUFICIENTE (2026-10-15; 23 op. fora da amostra, percentil 36,4 contra o acaso; reserva 7 op., todas no stop) |
| VOLUME_ACUMULACAO | 2026-10-16 (forma recente; 45 op., −0,064R) | sem causa clara: no desenho as entradas ficam no percentil 82 do acaso (sem vantagem provada) e é a geometria (2R/4R, 5 dias) que perde, também com entradas ao acaso (ver entrada de 2026-10-17) | sem sucessor | — |
| FIBO_RECUO | 2026-10-17 (forma recente; 237 op., −0,095R) | o momento da entrada: no desenho −0,19R contra +0,01R ao acaso com a mesma geometria (percentil 0); os recuos de 50%–61,8% são impulsos a falhar (só 7% dos stops voltam ao objetivo); nenhum filtro único chega ao nível do acaso (ver entrada de 2026-10-17) | sem sucessor | — |
| MAIORES_FUNDING | 2026-10-18 (forma recente, morte rápida; 10 op., −0,676R) | o funding negativo nas maiores é sinal de fraqueza que continua, não de aperto: no desenho o gatilho com funding dá −0,32R (percentil 14 do acaso) e o mesmo gatilho sem funding −0,13R (percentil 43, igual ao acaso); a geometria (1,5R/3R em 3 dias) também perde com entradas ao acaso (ver entrada de 2026-10-20) | sem sucessor (tirar o filtro só leva ao nível do acaso; confirma a hipótese 4 da fila) | — |
| BOUNCE_MACRO | 2026-10-19 (forma recente; 51 op., −0,011R) | o próprio filtro macro: nos últimos 90 dias tirou ao BOUNCE_X30 (vivo, +0,28R) cerca de 16 operações que valeram em média +1,2R; as melhores sobrevendas acontecem quando a macro NÃO está calma (ver entrada de 2026-10-20) | sem sucessor (a correção é tirar o filtro, e isso é o BOUNCE_X30, já vivo; o contrário, BOUNCE_MEDO, já existe) | — |
| TURTLE_FORTES | 2026-10-22 06:35 UTC (forma recente; 35 op., +0,19R) | a mesma da TURTLE: com esta saída, entradas ao acaso dão +0,56R (p95 +0,93R), logo o momento de comprar o rompimento é pior do que o acaso; +0,78R nos primeiros 60 dias (subida), −0,51R nos últimos 30 (lateral); no estudo H11d falha 2021-24 (ver entrada de 2026-10-22) | sem sucessor (família das quebras esgotada; ver 2026-10-14) | — |
| BOUNCE_X30, BOUNCE_X30_LIQ, BOUNCE_X30_PAVIO, BOUNCE_ISOLADA, BOUNCE_SQUEEZE, BOUNCE_TRAIL, BOUNCE_NOREACT, BOUNCE_FLUXO, BOUNCE_FORTE, BOUNCE_HORAS, BOUNCE_ABSORCAO, BOUNCE_G0, BOUNCE_V2, BOUNCE_V3, DIP_TREND | 2026-10-22 (corte dos clones, 04:50 e 09:25 UTC) | não é desempenho: morreram como clones (resultados diários correlacionados 0,75 a 1,00). Defeito encontrado: o representante do grupo também morreu (PAVIO como clone da ISOLADA às 04:50, ISOLADA como clone da PAVIO, já morta, às 09:25), por isso a família inteira do Oversold Bounce, a única acima do acaso, ficou sem ninguém (ver entrada de 2026-10-22) | sem sucessor (um sucessor seria outro clone; a correção é no corte dos clones, numa sessão com o Rui) | — |
| BOUNCE_LSR | 2026-10-23 09:15 UTC (clone de BOUNCE_MACRO, correlação 0,96) | não é desempenho: no combate de 90 dias tinha 28 op., +0,108R, com o acaso a mediana −0,42R e p95 −0,17R (acima do p95). Foi morta como clone de BOUNCE_MACRO, que já estava morta desde 2026-10-19: é o mesmo defeito do corte dos clones de 2026-10-22, outra vez (ver entrada de 2026-10-23) | sem sucessor (seria outro clone; a correção é no corte dos clones, numa sessão com o Rui) | — |

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

- **BOUNCE_1H** (morto por forma recente; no combate atual 198 op.,
  −0,128R, acima do p95 do acaso, que é −0,178R). Autópsia nos últimos 24 meses de 1H (69 moedas,
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

## 2026-10-14 — Funding muito negativo com o preço a aguentar (fila do Rui, hipótese 4)

**Veredicto: NÃO VALIDADA.** Falha 6 dos 7 critérios; contra o acaso fica
no percentil 85,4 fora da amostra (abaixo do 95). Não vai para papel.

- **Regras e grelha**: as da fila e do pré-registo acima (commit b27b82e,
  antes dos testes). Grelha (4): P ∈ {10, 5} × filtro do BTC ∈ {sim, não}.
  Universo: 59 moedas com funding e velas de 4H.
- **Janela**: desenho 2024-10-01 a 2026-03-31; reserva 2026-04-01 a
  2026-09-30 (último dia com funding no ramo `history`). Walk-forward:
  treino 183 dias, teste 91, 4 dobras. Custos 0,25% + 0,1% por lado.
- **Desenho**: 0 de 4 configurações positivas. P=5 com BTC: −49,7%
  (Sharpe −0,87, 382 op., 39,3% de acerto, −0,099R); P=5 sem BTC: −83,3%
  (706 op., −0,148R); P=10 com BTC: −79,4% (473 op., −0,189R); P=10 sem
  BTC: −93,4% (887 op., −0,205R). Custo médio 0,15R por operação. O filtro
  do BTC ajuda sempre; quanto mais extremo o funding (P=5), menos mau.
  Referência BTC>SMA200 no desenho: +12,2%, Sharpe 0,40.
- **Walk-forward fora da amostra** (364 dias): −17,6%, Sharpe −0,23,
  queda máxima 44,6%, 267 operações, 41,9% de acerto, −0,026R. Dobras:
  +26,6% / −20,4% / −18,3% / 0,0% (sem operações com o filtro do BTC) =
  1 de 4. Grandes moedas: −29,3%. Referência nas mesmas datas: −2,0%,
  Sharpe 0,03.
- **Configuração escolhida**: P=5, com o filtro do BTC.
- **Reserva (uma avaliação)**: +5,6%, Sharpe 1,02, queda máxima 6,8%, 25
  operações (60% de acerto, +0,328R). Referência: +20,2%, Sharpe 1,79.
  Grandes moedas: −0,2%.
- **Contra o acaso** (1000 séries, ±90 velas, mesma geometria): fora da
  amostra (292 op.) +0,004R contra mediana −0,062R e p95 +0,043R:
  **percentil 85,4**. Só walk-forward (267): percentil 71,5. Só reserva
  (25): percentil 96,5 (amostra curta, não é o critério).
- **Critérios**: 1 NÃO; 2 NÃO (25%); 3 NÃO (0%); 4 NÃO; 5 NÃO; 6 sim; 7 NÃO.
- **Período antigo**: não existe (o funding do ramo começa em 2024-08).
- **Leitura**: o funding muito negativo dá um ligeiro avanço sobre o acaso
  (o momento é um pouco melhor do que uma entrada qualquer), mas pequeno
  demais para pagar 0,7% de custos ida e volta: fora da amostra fica em
  zero antes de custos de carteira e perde no conjunto. A reserva boa (25
  operações) é o mesmo período em que tudo o que compra sobrevenda ganhou;
  não muda a leitura. Nada foi ligado ao vivo nem ao ringue (o ringue já
  tem o BOUNCE_SQUEEZE, que usa funding negativo com o gatilho do Bounce).
- Código: `tools/research_funding.py`; teste sem look-ahead (velas e
  funding): `tests/test_research_funding.py`; números:
  `backtest/research_funding.json`.

## 2026-10-14 — Quebra com compradores agressivos (fila do Rui, hipótese 5; resposta à família das quebras da arena)

**Veredicto: NÃO VALIDADA.** Falha 6 dos 7 critérios e é PIOR do que o
acaso (percentil 12,8). Separar as quebras pela parte compradora não as
salva: as quebras de 4H continuam a reverter.

- **Regras e grelha**: as da fila e do pré-registo acima (commit b27b82e).
  Grelha (4): q ∈ {0,55; 0,60} × H ∈ {3, 7} dias. Universo: 62 moedas.
- **Janela**: desenho 2024-10-11 a 2026-04-10; reserva 2026-04-11 a
  2026-10-10 (última vela do histórico: 2026-10-11). Walk-forward: treino
  183 dias, teste 91, 4 dobras. Custos 0,25% + 0,1% por lado.
- **Desenho**: 0 de 4 configurações positivas. q=0,55: −51,0% (H=3, 329
  op., 37,7%, −0,168R) e −43,3% (H=7, −0,147R); q=0,60: −11,8% (H=3, 111
  op., 40,5%, −0,130R) e −15,2% (H=7, −0,146R). Custo médio 0,20R a 0,27R
  por operação. Referência: +12,2%, Sharpe 0,40.
- **Walk-forward fora da amostra** (364 dias): −24,3%, Sharpe −1,68,
  queda máxima 26,5%, 92 operações, 34,8% de acerto, −0,209R. Dobras:
  −8,0% / −7,2% / −11,3% / 0,0% (sem operações) = 0 de 4. Grandes moedas:
  −15,0%. Referência nas mesmas datas: +7,0%, Sharpe 0,41.
- **Configuração escolhida**: q=0,55, H=7.
- **Reserva (uma avaliação)**: +13,0%, Sharpe 0,95, queda máxima 21,1%, 75
  operações (45,3% de acerto, +0,086R). Referência: +19,3%, Sharpe 1,66.
  Grandes moedas: +8,4%.
- **Contra o acaso** (1000 séries, ±90 velas, mesma geometria): fora da
  amostra (167 op.) −0,077R contra mediana +0,021R e p95 +0,160R:
  **percentil 12,8**. Walk-forward: percentil 28,7 (3 dias) e 13,8 (7
  dias); reserva: 41,5.
- **Critérios**: 1 NÃO; 2 NÃO (0%); 3 NÃO (0%); 4 NÃO; 5 NÃO; 6 sim; 7 NÃO.
- **Período antigo (informativo, não conta)**: 2021-07-30 a 2024-10-10 a
  mesma configuração daria −46,3% (Sharpe −0,55, 492 operações, 35,2% de
  acerto, −0,142R) contra +57,4% da referência.
- **Leitura**: comprar quebras de 4H perde com ou sem compradores
  agressivos, e com a mesma geometria entrar ao acaso na mesma moeda dá
  mais. Com o BREAKOUT, a quebra com reteste, a compressão, o TURTLE, o
  SQUEEZE_BB e agora esta, a família "comprar a quebra em 4H" fica
  esgotada neste projeto: não voltar a ela sem uma ideia de outra natureza.
  Nada foi ligado ao vivo nem ao ringue.
- Código: `tools/research_taker_breakout.py`; teste sem look-ahead:
  `tests/test_research_taker_breakout.py`; números:
  `backtest/research_taker_breakout.json`.

## 2026-10-15 — Pré-registo (escrito antes de qualquer teste desta corrida)

A fila do Rui está vazia (hipóteses 1 a 5 testadas). Arena em 2026-10-15
(scan.json do ramo `data`): 20 lutadores vivos, `recrutar` falso. Mortos
novos sem sucessor: RETESTE e BRK_ESPACO (2026-10-14) e CAPITULACAO
(2026-10-15, 20 operações a −0,218R no combate, regime lateral). Duas
vagas: a primeira para um sucessor da arena (CAPITULACAO) e a segunda para
uma hipótese nova (fila vazia).

### Autópsia dos mortos (2026-10-15)

- **RETESTE** (244 op., +0,109R mas abaixo da mediana ao acaso) e
  **BRK_ESPACO** (206 op., −0,316R): família "comprar a quebra em 4H",
  declarada esgotada em 2026-10-14 (seis variantes, todas piores do que o
  acaso com a mesma geometria). Mesma causa (as quebras de 4H revertem),
  nenhuma correção nova: **sem sucessor**.
- **CAPITULACAO** (`sig_capitulacao` do ringue, saídas G0, 3 dias). Corri a
  mesma função vela a vela nos últimos 24 meses (até 2026-10-11) em 72
  moedas, uma operação de cada vez por moeda, custos 0,25% + 0,1% por lado,
  SEM o filtro do BTC: 294 operações, +0,137R (sem custos +0,247R), 62% de
  acerto. Mas o resultado vem quase todo de 5 dias de colapso do mercado
  inteiro (2026-02-06 com 47 sinais na mesma vela, 2025-11-05 com 27,
  2025-03-11 com 14, 2025-10-11 com 30, 2025-01-13): sem esses 5 dias, 172
  operações a −0,327R e 35% de acerto; a média por dia distinto é −0,10R.
  Com o filtro do ringue (BTC acima da SMA200): 111 operações, −0,081R;
  com o BTC abaixo: 183, +0,269R (porque os colapsos gerais caem aí).
  **Causa encontrada**: uma vela de capitulação isolada numa moeda é, na
  maior parte das vezes, venda informada (notícia da própria moeda) e
  continua a cair; a mesma vela quando o mercado inteiro é despejado ao
  mesmo tempo é venda forçada (liquidações) sem informação, e recupera.
  O filtro do BTC acima da SMA200 deita fora precisamente os colapsos
  gerais e fica com as capitulações isoladas. AVISO: esta autópsia já viu
  os 24 meses inteiros, reserva incluída; o teste abaixo não é
  independente dela, e o resultado só conta como indício. A prova é o
  papel ao vivo.

### Sucessor: CAP_MERCADO (CAPITULACAO só quando o mercado inteiro capitula)

- **Correção única**: o filtro de mercado muda. Em vez de "BTC acima da
  SMA200", exige-se que o mercado inteiro tenha sido despejado: na vela do
  sinal ou na anterior, pelo menos B das moedas com histórico nessa vela
  tiveram o mínimo pelo menos 7% abaixo do fecho da vela anterior (só
  velas que fecham no mesmo instante ou antes: sem look-ahead). Gatilho
  da moeda, stop, objetivos (50% na média de 20 velas, resto no máximo das
  42 anteriores), stop na entrada depois do 1.º e saída ao fim de 3 dias:
  exatamente os de `sig_capitulacao`.
- **Grelha (3)**: B ∈ {20%, 35%, 50%}.
- Carteira de 4 posições de 25%, uma por moeda, primeiro o maior volume
  relativo; custos 0,25% + 0,1% por lado; janela de 24 meses até ao último
  dia completo do histórico de 4H (desenho 18, reserva 6); walk-forward
  (treino 183, teste 91); os sete critérios; contra o acaso com a mesma
  geometria (±90 velas). Código: `tools/research_cap_mercado.py`.
- Expectativa declarada: poucos episódios (dezenas de dias em 24 meses) e
  no máximo 4 operações por episódio; o mais provável é AMOSTRA
  INSUFICIENTE ou um resultado dominado por 2 ou 3 colapsos.

### Hipótese nova: ATRASO_BTC (as moedas que não acompanharam um impulso do BTC)

- **Lógica**: o BTC lidera; quando sobe forte numa vela de 4H, as moedas
  com pouca liquidez reagem mais tarde (arbitragem e fluxo chegam com
  atraso). Uma moeda que quase não se mexeu nessa vela recupera o atraso
  nas horas seguintes. É uma ideia de entrada nova (nada de sobrevenda nem
  quebra da própria moeda). Risco declarado: uma moeda que não acompanha
  o BTC pode estar simplesmente fraca (sem procura), e a 4H a maior parte
  do atraso já pode ter sido arbitrada.
- **Regra** (só compras): BTC acima da SMA200 no último dia fechado; vela
  de 4H do BTC com fecho pelo menos X acima do fecho anterior; na mesma
  vela a moeda subiu no máximo 1/4 do que o BTC subiu; entrada na abertura
  seguinte; stop no fecho menos 1,5 ATR14; um objetivo a 2R; sem stop na
  entrada; saída ao fim de H dias. Prioridade: maior atraso (retorno do
  BTC menos retorno da moeda).
- **Grelha (4)**: X ∈ {1,5%; 2,5%} × H ∈ {1, 3} dias.
- Mesma carteira, custos, janela, walk-forward e sete critérios. Código:
  `tools/research_atraso_btc.py`.
- Expectativa declarada: NÃO VALIDADA é o mais provável; com 14 hipóteses
  contra esta reserva no fim desta corrida, só o papel pode provar algo.

## 2026-10-15 — CAP_MERCADO: CAPITULACAO só quando o mercado inteiro capitula (sucessor da arena)

**Veredicto: AMOSTRA INSUFICIENTE** (16 operações no walk-forward, 23 fora
da amostra com a reserva; mínimo 40). Mesmo com mais operações não seria
validada: falha 3 dos 7 critérios (dobras positivas, reserva, acaso) e na
reserva perde as 7 operações. Não vai para papel nem para o ringue.

- **Regra e grelha**: as do pré-registo acima (commit 5240ac0, antes dos
  testes). Gatilho de `sig_capitulacao`, saídas G0 (3 dias), filtro de
  mercado trocado por "pelo menos B das moedas com o mínimo 7% abaixo do
  fecho anterior na vela do sinal ou na anterior". Grelha (3): B ∈ {20%,
  35%, 50%}. Universo: 62 moedas.
- **Janela**: desenho 2024-10-11 a 2026-04-10; reserva 2026-04-11 a
  2026-10-10 (última vela do histórico: 2026-10-11). Walk-forward: treino
  183 dias, teste 91, 4 dobras. Custos 0,25% + 0,1% por lado.
- **Desenho**: 3 de 3 configurações positivas, mas com poucas operações e
  quase sem capital investido (8% a 9% do tempo). B=35%: +24,6% (Sharpe
  0,91, queda máxima 10,5%, 40 op., 60% de acerto, +0,068R); B=20%: +14,3%
  (46 op., −0,074R); B=50%: +14,4% (35 op., −0,058R). O retorno positivo
  com R médio negativo vem de poucos colapsos com subidas grandes (risco
  médio de 13% a 16% por operação). Referência: +12,2%, Sharpe 0,40.
- **Walk-forward fora da amostra** (364 dias): +14,1%, Sharpe 0,83, queda
  máxima 7,4%, só 16 operações, 56,2% de acerto, −0,026R. Dobras: −0,1% /
  +0,3% / +14,9% / −0,9% = 2 de 4 (a terceira, com o colapso de
  2026-02-06, faz o resultado todo). Grandes moedas: +21,3%, Sharpe 1,26.
  Referência nas mesmas datas: +7,0%, Sharpe 0,41.
- **Configuração escolhida**: B=20%.
- **Reserva (uma avaliação)**: −11,3%, Sharpe −1,85, queda máxima 13,0%,
  7 operações, 0% de acerto (todas no stop, −1,01R). Referência: +19,3%,
  Sharpe 1,66.
- **Contra o acaso** (1000 séries, ±90 velas, mesma geometria): fora da
  amostra (23 op.) −0,326R contra mediana −0,281R e p95 −0,054R:
  **percentil 36,4**. Só walk-forward (16): percentil 97,2; só reserva
  (7): percentil 0. Amostras minúsculas nos dois casos.
- **Critérios**: 1 sim; 2 NÃO (50%); 3 sim; 4 sim; 5 sim; 6 NÃO; 7 NÃO.
- **Período antigo (informativo, não conta)**: 2021-07-30 a 2024-10-10 a
  mesma configuração daria −21,3% (Sharpe −0,39, 75 operações, 48% de
  acerto, −0,148R) contra +57,4% da referência.
- **Leitura**: a autópsia acertou na descrição (os ganhos da capitulação
  vêm dos colapsos gerais), mas isso não é uma regra que se possa operar:
  são meia dúzia de episódios em dois anos, a carteira só apanha 4 moedas
  em cada um, e um colapso que continua a cair (reserva: 7 stops seguidos)
  apaga os ganhos de vários. A "regra" que a autópsia viu era, sobretudo,
  2 ou 3 dias de sorte, e esses dias já eram conhecidos antes do teste.
  A CAPITULACAO fica morta sem herdeiro.
- Código: `tools/research_cap_mercado.py`; teste sem look-ahead:
  `tests/test_research_cap_mercado.py`; números:
  `backtest/research_cap_mercado.json`.

## 2026-10-15 — ATRASO_BTC: moedas que não acompanharam um impulso do BTC (hipótese nova)

**Veredicto: NÃO VALIDADA.** Falha 6 dos 7 critérios; contra o acaso fica
no percentil 79,7 fora da amostra (abaixo do 95). Não vai para papel.

- **Regra e grelha**: as do pré-registo acima (commit 5240ac0). Grelha (4):
  X ∈ {1,5%; 2,5%} × H ∈ {1, 3} dias. Universo: 61 moedas (sem o BTC).
- **Janela**: desenho 2024-10-11 a 2026-04-10; reserva 2026-04-11 a
  2026-10-10. Walk-forward: treino 183 dias, teste 91, 4 dobras. Custos
  0,25% + 0,1% por lado.
- **Desenho**: 0 de 4 configurações positivas. X=1,5%: −28,4% (H=1, 192
  op., 35,9%, −0,106R) e −35,6% (H=3, −0,069R); X=2,5%: −12,5% (H=1, 32
  op., 28,1%, −0,237R) e −24,2% (H=3, −0,354R). Quanto maior o impulso do
  BTC, pior: a moeda que não acompanha um impulso forte está fraca, não
  atrasada. Referência: +12,2%, Sharpe 0,40.
- **Walk-forward fora da amostra** (364 dias): −9,7%, Sharpe −0,38, queda
  máxima 25,4%, 65 operações, 40,0% de acerto, −0,129R (custo médio
  0,19R). Dobras: +21,0% / −24,1% / −1,7% / 0,0% (sem operações) = 1 de 4.
  Grandes moedas: −0,5%. Referência nas mesmas datas: +7,0%, Sharpe 0,41.
- **Configuração escolhida**: X=2,5%, H=1.
- **Reserva (uma avaliação)**: +4,4%, Sharpe 0,81, queda máxima 4,7%, 16
  operações (62,5% de acerto, +0,322R). Referência: +19,3%, Sharpe 1,66.
- **Contra o acaso** (1000 séries, ±90 velas, mesma geometria): fora da
  amostra (81 op.) −0,040R contra mediana −0,114R e p95 +0,050R:
  **percentil 79,7**. Walk-forward: percentil 67,7 (1 dia) e 2,8 (3 dias,
  5 op.); reserva: 88,2.
- **Critérios**: 1 NÃO; 2 NÃO (25%); 3 NÃO (0%); 4 NÃO; 5 NÃO; 6 sim; 7 NÃO.
- **Período antigo (informativo, não conta)**: 2021-07-30 a 2024-10-10 a
  mesma configuração daria −21,9% (Sharpe −0,50, 136 operações, 36% de
  acerto, −0,164R) contra +57,4% da referência.
- **Leitura**: a 4H não há atraso para apanhar; a falta de reação ao BTC é
  sinal de fraqueza relativa, e a fraqueza continua. Com custos de 0,7% ida
  e volta e stops de 6% a 9%, nem um pequeno avanço sobre o acaso chegaria.
  Nada foi ligado ao vivo nem ao ringue.
- Código: `tools/research_atraso_btc.py`; teste sem look-ahead:
  `tests/test_research_atraso_btc.py`; números:
  `backtest/research_atraso_btc.json`.


## 2026-10-16 — Pré-registo (escrito antes de qualquer teste desta corrida)

A fila do Rui está vazia (hipóteses 1 a 5 testadas). Arena em 2026-10-16
(scan.json do ramo `data`): 21 lutadores vivos, `recrutar` falso. Nenhum
morto novo desde 2026-10-15: todos os mortos já têm linha na tabela dos
sucessores (MOMENTUM e os shorts ficaram "sem sucessor por agora"; o
MOMENTUM continua com 31 operações, pouco para autópsia). Uma vaga: uma
hipótese nova.

### Hipótese nova: RESILIENTE (moedas que aguentam uma queda forte do BTC)

- **Lógica**: o diário mostra duas vezes que a fraqueza relativa de uma
  moeda continua (capitulação isolada em 2026-10-15; moeda que não
  acompanha a subida do BTC, ATRASO_BTC). A pergunta simétrica, com lógica
  económica própria: quando o BTC cai forte numa vela de 4H, quase todas
  as moedas caem com ele (vendas de cesto, liquidações, arbitragem); uma
  moeda que quase não cai nessa vela tem compradores dispostos a absorver
  a venda (procura própria). Quando a pressão do BTC passa, essa procura
  continua a empurrar o preço. É uma entrada nova: não é sobrevenda, não é
  quebra da própria moeda, e compra força relativa num instante de stress
  (não a força relativa semanal já rejeitada). Riscos declarados: (1) a
  hipótese nasceu depois de ver o ATRASO_BTC, que usou a mesma reserva;
  (2) uma moeda pode "aguentar" por notícia própria já esgotada; (3) a 4H
  o efeito pode já estar arbitrado; (4) com o BTC acima da SMA200, quedas
  de 2,5% numa vela de 4H são raras e a amostra pode ser curta.
- **Regra** (só compras; decisão no fecho da vela i de 4H, só velas
  fechadas): BTC acima da SMA200 no último dia fechado; vela i do BTC com
  fecho pelo menos X abaixo do fecho anterior; na mesma vela a moeda caiu
  no máximo 1/4 do que o BTC caiu (retorno da moeda ≥ retorno do BTC × 1/4);
  entrada na abertura seguinte; stop no fecho menos 1,5 ATR14; um objetivo
  a 2R; sem stop na entrada; saída ao fim de H dias. Prioridade: maior
  resiliência (retorno da moeda menos retorno do BTC).
- **Grelha (4)**: X ∈ {1,5%; 2,5%} × H ∈ {1, 3} dias (a mesma forma da do
  ATRASO_BTC, para não escolher parâmetros depois de ver dados).
- Carteira 4 × 25%, uma por moeda; custos 0,25% + 0,1% por lado; janela de
  24 meses até ao último dia completo do histórico de 4H (desenho 18,
  reserva 6); walk-forward (treino 183, teste 91); os sete critérios;
  contra o acaso com a mesma geometria (±90 velas). Universo: todas as
  moedas com histórico, sem o BTC. Código: `tools/research_resiliente.py`.
- Expectativa declarada: NÃO VALIDADA é o mais provável. Com 16 hipóteses
  contra esta reserva no fim desta corrida (10 deste diário antes de hoje
  + 5 da afinação + esta), a probabilidade de pelo menos um falso positivo
  a 5% ronda os 56%; só o papel ao vivo pode provar algo.

## 2026-10-16 — RESILIENTE: moedas que aguentam uma queda forte do BTC (hipótese nova)

**Veredicto: AMOSTRA INSUFICIENTE** (5 operações no walk-forward, 19 fora
da amostra com a reserva; mínimo 40). Na prática é uma rejeição: falha os
7 critérios, nenhuma configuração ganha no desenho e é pior do que o acaso
(percentil 11,4). Não vai para papel nem para o ringue.

- **Regra e grelha**: as do pré-registo acima (commit 1ec4bb7, antes dos
  testes). Grelha (4): X ∈ {1,5%; 2,5%} × H ∈ {1, 3} dias. Universo: 61
  moedas (sem o BTC).
- **Janela**: desenho 2024-10-11 a 2026-04-10; reserva 2026-04-11 a
  2026-10-10 (última vela do histórico: 2026-10-11 08:00 UTC; histórico
  com 5 dias de atraso, dentro do limite de 7). Walk-forward: treino 183
  dias, teste 91, 4 dobras. Custos 0,25% + 0,1% por lado.
- **Desenho**: 0 de 4 configurações positivas. X=1,5%: −18,7% (H=1, 158
  op., 40,5% de acerto, −0,121R) e −24,2% (H=3, 145 op., 33,1%, −0,162R);
  X=2,5%: −0,5% (H=1, 42 op., 45,2%, −0,054R) e −30,5% (H=3, 42 op.,
  23,8%, −0,389R). Custo médio 0,10R a 0,11R por operação: mesmo sem
  custos ficaria perto de zero ou negativo. Manter 3 dias é sempre pior do
  que 1. Referência BTC>SMA200: +12,2%, Sharpe 0,40.
- **Walk-forward fora da amostra** (364 dias): +2,5%, Sharpe 0,36, queda
  máxima 4,2%, só 5 operações (60% de acerto, +0,101R). Dobras: +2,5% /
  0,0% / 0,0% / 0,0% (três dobras sem operações: com X=2,5% e o BTC acima
  da SMA200 quase não há quedas destas) = 1 de 4. Grandes moedas: −0,5%.
  Referência nas mesmas datas: +7,0%, Sharpe 0,41.
- **Configuração escolhida**: X=1,5%, H=3 (escolhida na última dobra).
- **Reserva (uma avaliação)**: −9,1%, Sharpe −1,32, queda máxima 9,8%, 14
  operações, 21,4% de acerto, −0,397R. Referência: +19,3%, Sharpe 1,66.
  Grandes moedas: −1,2%.
- **Contra o acaso** (1000 séries, ±90 velas, mesma geometria): fora da
  amostra (19 op.) −0,266R contra mediana +0,011R e p95 +0,425R:
  **percentil 11,4**. Só walk-forward (5): percentil 82,6; só reserva
  (14): percentil 3,5.
- **Critérios**: 1 NÃO; 2 NÃO (25%); 3 NÃO (0%); 4 NÃO; 5 NÃO; 6 NÃO; 7 NÃO.
- **Período antigo (informativo, não conta)**: 2021-07-30 a 2024-10-10 a
  mesma configuração daria −38,4% (Sharpe −0,33, 324 operações, 35,2% de
  acerto, −0,13R) contra +57,4% da referência.
- **Leitura**: a força relativa num instante de stress não continua a
  4H. Junto com o ATRASO_BTC, fecha a família "reação da moeda a uma vela
  forte do BTC": nem a que fica para trás numa subida recupera, nem a que
  aguenta uma queda segue a subir. A assimetria que o diário encontrou
  (fraqueza continua) não tem um lado comprador simétrico neste prazo.
  Nada foi ligado ao vivo nem ao ringue.
- Código: `tools/research_resiliente.py`; teste sem look-ahead:
  `tests/test_research_resiliente.py`; números:
  `backtest/research_resiliente.json`.

## 2026-10-17 — Autópsia de VOLUME_ACUMULACAO e FIBO_RECUO (sem sucessor; sem hipótese nova)

**Veredicto da corrida: nenhuma hipótese testada.** Os dois mortos novos
foram autopsiados; nenhum tem uma correção única que possa bater o acaso,
por isso não se inventa sucessor. A fila do Rui está vazia e não há hoje
uma hipótese nova com lógica económica séria que não seja variante de uma
já rejeitada. O contador fica em 16.

- **Arena** (scan.json do ramo `data`, 2026-10-17): 21 lutadores vivos,
  `recrutar` falso. Mortos novos sem sucessor: VOLUME_ACUMULACAO (Valter,
  morto a 2026-10-16: 45 op., −0,064R, mediana ao acaso +0,044R) e
  FIBO_RECUO (Fabio, morto a 2026-10-17, um dia depois de entrar: 237 op.,
  −0,095R, mediana ao acaso +0,088R, p95 +0,227R).
- **Método da autópsia** (novo, `tools/autopsia_arena.py`, teste sem
  look-ahead em `tests/test_autopsia_arena.py`): a mesma função de sinal do
  ringue vela a vela no histórico de 4H (ramo `history`, última vela
  2026-10-11 08:00 UTC, 6 dias de atraso), BTC acima da SMA200, uma
  operação de cada vez por moeda, custos 0,25% + 0,1% por lado, e SÓ a
  janela de desenho (2024-10-11 a 2026-04-10), para não gastar a reserva
  numa autópsia. Acaso: mesma moeda, ±90 velas, mesma geometria, 1000
  séries. Números em `backtest/autopsia_2026-10-17.json`.
- **VOLUME_ACUMULACAO** (desenho): 79 op., −0,026R, 43% de acerto; acaso
  mediana −0,137R, p95 +0,060R: **percentil 82,1**. Saídas: 40 stops
  (−1,02R), 24 por tempo (+0,62R), 8 no zero, 7 no 2.º objetivo. Custo
  médio 0,16R por operação (risco médio 5,3%). Leitura: o momento de
  entrada é um pouco melhor do que o acaso, mas sem significância (82 <
  95), e a geometria (2R e 4R, stop na entrada, 5 dias) perde mesmo com
  entradas ao acaso (−0,14R). Trocar a saída só levaria o resultado para o
  nível do acaso. **Sem causa clara → sem sucessor.**
- **FIBO_RECUO** (desenho): 506 op., −0,190R, 33% de acerto; acaso mediana
  +0,012R, p95 +0,102R: **percentil 0,0** (com a mesma geometria, entrar
  num dia qualquer na mesma moeda dá mais em todas as 1000 séries). Saídas:
  266 stops (53%), 153 por tempo (+0,29R), 55 no 2.º objetivo, 32 no zero.
  Só 23% chegam ao 1.º objetivo (o máximo do impulso). Os stops não são
  varridos e devolvidos: só 7% voltam ao 1.º objetivo dentro do prazo, e
  depois do stop o preço cai em mediana mais 1,1R. **Causa encontrada**:
  neste mercado, um recuo de 4H até 50%–61,8% de um impulso recente é, na
  maior parte das vezes, o impulso a falhar, e a vela que vira não marca o
  fim da descida. Por quartis no desenho: recuos rápidos (mais curtos do
  que o impulso) −0,38R e −0,30R contra −0,07R e −0,01R dos lentos; volume
  do recuo acima do do impulso −0,32R contra −0,06R com volume baixo. A
  leitura clássica ("recuo lento e sem volume é descanso; rápido e com
  volume é distribuição") confirma-se na direção, mas **nenhum quartil
  chega a zero nem à mediana ao acaso** (+0,01R), e o melhor filtro único
  (recuo pelo menos tão longo como o impulso) fica em −0,02R com 228 op.
  Como no BOUNCE_1H, nenhuma correção única chega ao nível do acaso:
  **sem sucessor**.
- **AVISO de contaminação** (registado por honestidade): durante a
  exploração dos filtros do FIBO_RECUO imprimi por engano, além do
  desenho, os mesmos subconjuntos na reserva (rapidez ≥ 1: 85 op.,
  −0,02R; volume do recuo < 0,7 do impulso: 80 op., +0,06R). Não houve
  teste nem escolha com base nisso, mas qualquer sucessor futuro do
  FIBO_RECUO com estes filtros já não tem reserva limpa e só pode ser
  julgado no papel ao vivo.
- **Sem hipótese nova hoje**: as ideias de entrada que restam com dados
  disponíveis são variantes do que já perdeu (recuos em tendência,
  quebras, reação ao BTC, funding, fluxo comprador) ou já estão no ringue
  (absorção, desalavancagem, funding com o gatilho do Bounce). Com 16
  hipóteses contra esta reserva (probabilidade de pelo menos um falso
  positivo a 5% perto de 56%), acrescentar uma fraca só aumenta o ruído.
- **Leitura geral**: o ringue de 90 dias confirma o diário. Os únicos
  lutadores acima do acaso são a família do Oversold Bounce (G0/V2/V3 +0,8R
  em 26 op.; X30 +0,39R em 109 op. contra mediana ao acaso −0,24R) e o
  DIP_TREND (+0,12R, também gatilho de sobrevenda); tudo o que compra força
  ou recuos "técnicos" (Fibonacci, recuo, quebras) morre abaixo do acaso.
  A prova continua a ter de vir do papel ao vivo, não de mais testes na
  mesma reserva.
- Proposta para a próxima corrida: o histórico de 4H terá 7 ou mais dias
  de atraso: correr primeiro o workflow "Historico para backtest". Sem
  mortos novos e sem hipótese séria, a corrida pode limitar-se a isso.

## 2026-10-18 — Sem hipótese nova hoje (histórico atualizado; sem mortos novos)

**Veredicto da corrida: nenhuma hipótese testada.** O contador fica em 16.

- **Histórico**: tinha 7 dias de atraso (última vela 2026-10-11 08:00
  UTC); corri o workflow "Historico para backtest" (execução 39121039567,
  sucesso). Última vela de 4H agora: 2026-10-18 08:00 UTC, 74 moedas.
- **Arena** (scan.json do ramo `data`, 2026-10-18): 21 lutadores vivos,
  `recrutar` falso. Nenhum morto novo desde FIBO_RECUO (2026-10-17): todos
  os 18 mortos já têm linha na tabela dos sucessores. Fila do Rui vazia.
- **Sem hipótese nova hoje**: mantém-se a leitura de 2026-10-17. As
  entradas que restam com os dados disponíveis (velas, fluxo comprador,
  funding) são variantes de famílias já rejeitadas (quebras, recuos,
  reação ao BTC, funding negativo) ou já estão no ringue (absorção,
  desalavancagem, fluxo, macro). Com 16 hipóteses contra a mesma reserva,
  uma hipótese fraca só aumenta o risco de um falso positivo.
- **Nota sobre a janela**: com o histórico atualizado, a janela de 24
  meses avança uma semana; a reserva passa a incluir 7 dias que nenhum
  teste viu. Isso não a "limpa": continua a ser quase toda a mesma reserva
  já usada 16 vezes. A prova continua a ser o papel ao vivo e o combate de
  hora a hora.
- Proposta para a próxima corrida: só autópsia se morrer alguém; uma
  hipótese nova só se trouxer uma fonte de informação ainda não usada (por
  exemplo, se o histórico passar a ter interesse em aberto dos perpétuos).

## 2026-10-20 — Pré-registo (escrito antes de qualquer teste desta corrida)

- **Arena** (scan.json do ramo `data`, 2026-10-20): 24 lutadores vivos
  (mínimo 5), `recrutar` falso. Mortos novos sem sucessor: MAIORES_FUNDING
  (Gonçalo, morto a 2026-10-18 por morte rápida: 10 op., −0,676R, 2
  ganhadoras) e BOUNCE_MACRO (Mário, morto a 2026-10-19: 51 op., −0,011R,
  abaixo da mediana ao acaso nessa altura). Fila do Rui vazia. Histórico de
  4H até 2026-10-18 08:00 UTC (2 dias de atraso); funding até 2026-10-01.
- Autópsias abaixo (só janela de desenho, 2024-10-19 a 2026-04-18). Um
  sucessor no máximo; se nenhum tiver causa clara, a vaga vai para uma
  hipótese nova (escrita aqui antes de testar).

### Hipótese nova: IMPULSO_AMPLITUDE (impulso de amplitude do mercado, 4H, só compras)

- **Lógica**: o "breadth thrust" de Zweig (bolsa americana, 1986):
  quando o mercado passa em poucos dias de quase todas as ações fracas
  para quase todas fortes, é dinheiro novo a entrar em todo o lado e não
  uma história de uma moeda; costuma marcar o início de uma subida de
  semanas. É uma família diferente das dos campeões (tendência/amplitude,
  não sobrevenda) e usa informação ainda não usada para comprar força: a
  amplitude do mercado inteiro (o BOUNCE_AMPLITUDE usa-a só para a
  sobrevenda). Riscos declarados: acontecimentos raros (amostra curta, é
  provável dar AMOSTRA INSUFICIENTE); operações agrupadas nos mesmos dias
  (correlação alta entre elas); a família "comprar força" perdeu sempre
  neste projeto (quebras, TURTLE), por isso o mais provável é NÃO
  VALIDADA.
- **Regras** (decisão no fecho da vela i de 4H, só velas fechadas):
  - amplitude A(i) = fração das moedas (pelo menos 20 com vela nesse
    instante) com fecho acima da sua média de 20 velas de 4H;
  - impulso: A(i) ≥ U, A(i−1) < U, e o mínimo de A nas 60 velas
    anteriores (10 dias) ≤ 0,30;
  - moedas compradas: as que fecham a vela i acima da sua média de 20
    (participam no impulso); carteira 4 × 25%, uma por moeda, primeiro a
    MENOS esticada (menor (fecho − SMA20) / ATR14);
  - entrada na abertura da vela i+1; stop no fecho menos 2 ATR14 de 4H;
    um objetivo a 3R; sem stop na entrada; saída ao fim de H dias;
  - filtro do BTC acima da SMA200 diária (último dia fechado) conforme a
    grelha.
- **Grelha (6)**: U ∈ {0,75; 0,85} × H ∈ {5, 10} dias com o filtro do
  BTC; mais U = 0,75 × H ∈ {5, 10} sem o filtro do BTC.
- **Método**: `tools/research_rlib.evaluate` (o de `tools/research.py`):
  custos 0,25% + 0,1% por lado, walk-forward no desenho (treino 183 dias,
  teste 91), grandes moedas, referência BTC>SMA200, reserva avaliada uma
  vez só para a configuração escolhida, contra o acaso (mesma moeda, ±90
  velas, mesma geometria, 1000 séries) acima do percentil 95. Menos de 40
  operações fora da amostra = AMOSTRA INSUFICIENTE.
- Contador depois desta corrida: 18 (11 neste diário antes de hoje + 6 da
  afinação + esta). Com 18 testes a probabilidade de pelo menos um falso
  positivo a 5% ronda os 60%.

### Autópsias (2026-10-20)

- **MAIORES_FUNDING** (Gonçalo; BTC, ETH e SOL; funding negativo na
  última liquidação, fecho acima da média de 20 velas e do máximo
  anterior; stop no mínimo de 6 velas; 50% a 1,5R e 50% a 3R; 3 dias).
  No ringue: 10 op., 2 ganhadoras, −0,676R (acaso: mediana −0,391R).
  Desenho (2024-10-19 a 2026-04-18, `tools/autopsia_arena.walk` com a
  função do ringue e o funding da Binance do ramo `history`; o ringue usa
  o da OKX): 68 op., 32,4% de acerto, **−0,318R**; acaso com a mesma
  geometria: mediana −0,205R, p95 −0,017R, **percentil 14,1**. Saídas: 31
  stops (−1,03R), 28 por tempo (+0,03R), 5 no zero, 4 no 2.º objetivo; só
  19% chegam ao 1.º objetivo; custo 0,21R por operação. Por moeda: BTC
  −0,45R (16), ETH −0,65R (13), SOL −0,15R (39). **Controlo**: o mesmo
  gatilho e o mesmo plano SEM a condição do funding dão 288 op., −0,126R,
  percentil 42,8 (igual ao acaso). **Causa**: o funding negativo
  seleciona os piores momentos (os vendidos têm razão mais vezes do que
  são apertados), e a geometria perde até com entradas ao acaso. Tirar o
  filtro só leva ao nível do acaso; não há uma correção única que crie
  vantagem. Junta-se à hipótese 4 da fila (funding muito negativo, todas
  as moedas, NÃO VALIDADA em 2026-10-14): a família "funding negativo
  → aperto" fica esgotada com estes dados. **Sem sucessor.**
- **BOUNCE_MACRO** (Mário; gatilho do BOUNCE_X30 só com a macro
  "favorável": VIX abaixo de 20, S&P 500 estável, dólar calmo). Não há
  histórico macro no ramo `history` nem rede para o Yahoo nesta corrida,
  por isso a autópsia usa o combate de 90 dias (`forma.json` do ramo
  `arena`, 2026-10-20) e compara com o pai: BOUNCE_X30 64 op., +0,283R
  (acaso: mediana −0,263R, p95 −0,087R); BOUNCE_MACRO 48 op., −0,031R
  (mediana −0,355R). Nos últimos 30 dias são as mesmas 33 operações
  (+0,073R): a macro esteve sempre favorável. Nos 60 dias antes, o X30 tem
  31 op. a +0,506R e o MACRO 15 a −0,261R: o filtro tirou cerca de 16
  operações que valeram em média cerca de +1,2R (conta aproximada, pela
  diferença dos totais). **Causa**: o filtro deita fora exatamente as
  sobrevendas em dias de medo ou neutros, que são as que mais recuperam.
  A correção é tirar o filtro, e isso é o BOUNCE_X30, já vivo; a variante
  contrária (BOUNCE_MEDO) já existe no código. **Sem sucessor.** Morreu
  com −0,011R e hoje teria a forma acima do p95 do acaso (−0,17R): a
  morte é definitiva e a amostra é curta, por isso não se lê nada a favor.
- Números: `backtest/autopsia_2026-10-20.json`.

## 2026-10-20 — IMPULSO_AMPLITUDE: impulso de amplitude do mercado (hipótese nova)

**Veredicto: NÃO VALIDADA.** Falha os 7 critérios. Perde em todas as
configurações e não bate o acaso (percentil 86,2 fora da amostra; o
mínimo é 95). Não vai para papel nem para o ringue.

- **Regra e grelha**: as do pré-registo acima (commit f5c237b, antes dos
  testes). Universo: 74 moedas.
- **Janela**: desenho 2024-10-18 a 2026-04-17; reserva 2026-04-18 a
  2026-10-17 (última vela 2026-10-18 08:00 UTC). Walk-forward: treino 183
  dias, teste 91, 4 dobras. Custos 0,25% + 0,1% por lado.
- **Nota de implementação** (registada por honestidade): com a amplitude
  medida em velas de 4H e a média de 20 velas, a amplitude oscila depressa
  e a regra dispara muito mais do que um "breadth thrust" clássico: 171
  impulsos no desenho e 58 na reserva (com U = 0,75). A regra testada foi
  a pré-registada, sem mudanças depois de ver os números; uma versão
  diária mais rara seria outra hipótese, contra a mesma reserva.
- **Desenho**: 0 de 6 configurações positivas. Com o filtro do BTC:
  U=0,75 −35,9% (H=5, 228 op., 34,6% de acerto, −0,05R) e −44,2% (H=10,
  202 op., −0,04R); U=0,85 −63,5% (H=5, −0,19R) e −62,5% (H=10, −0,20R).
  Sem o filtro: −59,9% e −67,4%. Quedas máximas de 66% a 86%. Custo médio
  0,12R a 0,13R por operação (risco médio 6,9%). Referência BTC>SMA200 no
  desenho: +8,7%, Sharpe 0,33, queda máxima 33,4%.
- **Walk-forward fora da amostra** (364 dias): **−45,5%**, Sharpe −1,13,
  queda máxima 57,4%, 160 operações, 32,5% de acerto, −0,138R. Dobras:
  +7,1% / −31,4% / −25,8% / 0,0% (sem operações) = 1 de 4. Grandes
  moedas: −53,0%. Referência nas mesmas datas: +5,0%, Sharpe 0,33.
- **Configuração escolhida**: U=0,75, H=10, com o filtro do BTC.
- **Reserva (uma avaliação)**: −1,9%, Sharpe −0,01, queda máxima 14,4%,
  32 op., 31,2% de acerto, +0,109R (o retorno médio por operação é
  −0,03%: o R positivo vem de stops curtos). Referência: +17,1%, Sharpe
  1,47. Grandes moedas: −14,1%.
- **Contra o acaso** (1000 séries, ±90 velas, mesma geometria): fora da
  amostra (192 op.) −0,097R contra mediana −0,194R e p95 −0,055R:
  **percentil 86,2**. Só walk-forward: percentis 77,7 (H=5, 118 op.) e
  75,2 (H=10, 42 op.); só reserva (32): percentil 64,2.
- **Critérios**: 1 NÃO; 2 NÃO (25%); 3 NÃO (0%); 4 NÃO; 5 NÃO; 6 NÃO; 7 NÃO.
- **Período antigo (informativo, não conta)**: 2021-07-30 a 2024-10-17 a
  mesma configuração daria −72,3% (Sharpe −0,82, 349 op., 25,2% de
  acerto, −0,20R) contra +60,0% da referência.
- **Leitura**: comprar as moedas que participam num salto de amplitude é,
  a 4H, comprar força depois de um repique do mercado inteiro, e perde
  como as quebras. O momento é um pouco melhor do que o acaso (percentil
  86), mas longe da significância, e a geometria (stop a 2 ATR, objetivo a
  3R) perde mesmo com entradas ao acaso (−0,19R). Mais uma confirmação de
  que, neste mercado, as entradas em força a 4H não têm vantagem; só a
  sobrevenda a virar a tem. Nada foi ligado ao vivo nem ao ringue.
- Código: `tools/research_impulso.py`; teste sem look-ahead:
  `tests/test_research_impulso.py`; números: `backtest/research_impulso.json`.
- Proposta para a próxima corrida: autópsia só se morrer alguém; hipótese
  nova só com uma fonte de informação nova (interesse em aberto ou rácio
  long/short com histórico no ramo `history`), ou uma família para o
  regime de descida que não seja venda a descoberto (por exemplo, ficar
  em USDC é a resposta certa e não precisa de teste).

## 2026-10-21 — Sem hipótese nova hoje (sem mortos novos; fila vazia)

**Veredicto da corrida: nenhuma hipótese testada.** O contador passa a 19
só pela H7 da afinação (SHORT_FALHADO, REJEITADA em 2026-10-21).

- **Histórico** (ramo `history`): última atualização 2026-10-18, 3 dias de
  atraso (abaixo dos 7), 74 moedas em 4H, 72 em 1H, 69 com funding. Não foi
  preciso correr o workflow.
- **Arena** (scan.json do ramo `data`, 2026-10-21): 24 lutadores vivos
  (mínimo 5), `recrutar` falso. Nenhum morto novo desde MAIORES_FUNDING e
  BOUNCE_MACRO (autopsiados em 2026-10-20): os 20 mortos têm todos linha na
  tabela dos sucessores. Fila do Rui vazia.
- **Combate de 90 dias** (`forma.json` do ramo `arena`, 2026-10-21 10:23
  UTC, 38 moedas): os lutadores acima do p95 do acaso continuam a ser só a
  família do Oversold Bounce (G0 +0,91R em 15 op.; X30 +0,37R em 65 op.,
  mediana ao acaso −0,26R; SQUEEZE +0,47R em 41 op.) e o DIP_TREND (+0,13R
  em 65 op., p95 −0,12R). Os vivos fora desta família (REVERSAO_INTERVALO,
  MAIORES_RECUO, MAIORES_TENDENCIA e os dois shorts das maiores) têm menos
  de 20 operações ou estão abaixo do acaso.
- **Porque não há hipótese nova**: as entradas de compra que restam com os
  dados do histórico (velas de 4H e 1H, fluxo comprador, funding) são
  variantes de famílias já rejeitadas (quebras, recuos técnicos, amplitude,
  reação ao BTC, funding negativo) ou já estão no ringue como variantes do
  Bounce (absorção, desalavancagem, fluxo, pavio, horas, rácio long/short).
  O ringue já mede o interesse em aberto ao vivo (36 moedas), mas o ramo
  `history` não tem histórico de interesse em aberto, por isso uma
  hipótese com ele não pode ser testada na janela de 24 meses. Com 19
  hipóteses contra a mesma reserva (cerca de 62% de probabilidade de pelo
  menos um falso positivo), mais uma hipótese fraca só aumenta o ruído; a
  prova útil é a que o papel ao vivo e o combate de hora a hora estão a
  juntar.
- Proposta para a próxima corrida: autópsia se morrer alguém; uma hipótese
  nova só com uma fonte de informação ainda não usada (interesse em aberto
  com histórico, se o ramo `history` o passar a guardar) ou uma ideia de
  entrada que não seja variante das famílias acima. Na corrida de
  2026-10-25 o histórico já terá 7 dias de atraso: correr primeiro o
  workflow "Historico para backtest".

## 2026-10-22 — Sem hipótese nova hoje; autópsias de TURTLE_FORTES e dos clones (sem sucessor)

**Veredicto da corrida: nenhuma hipótese testada.** O contador desta
reserva fica em 19 (nenhuma hipótese nova aqui nem na afinação desde a H7).
O contador global do programa vai em 41 (estudos H8 a H11 de 21 e 22/10).

- **Histórico** (ramo `history`): última atualização 2026-10-18, 4 dias de
  atraso (abaixo dos 7), 74 moedas em 4H, 72 em 1H, 69 com funding. O
  histórico de derivados (`derivados.json`, ramo `data`) só é recolhido
  desde 2026-10-20 e as moedas delistadas (ramo `history-delistadas`) só
  servem para testes sem viés de sobrevivência: nenhum dos dois dá uma
  fonte nova com 24 meses de dados.
- **Arena** (scan.json do ramo `data`, 2026-10-22 10:50 UTC): **9
  lutadores vivos** (mínimo 5), `recrutar` falso. Fila do Rui vazia.
  Mortos novos desde ontem: TURTLE_FORTES (forma recente) e 15 lutadores
  pelo corte dos clones (regra nova de 21/10, OK do Rui).

### Autópsia de TURTLE_FORTES (sem sucessor)

- Combate de 90 dias (`forma.json`, ramo `arena`): 35 op., 15 ganhadoras,
  +0,19R; com a mesma saída e entradas ao acaso: mediana **+0,56R**, p95
  +0,93R. Primeiros 60 dias (fase de subida): 19 op. a +0,78R; últimos 30
  dias (lateral): 16 op. a −0,51R. Estudo H11d (2021-24 e 2024-26, fase de
  subida): −0,00R e +0,42R, falha 2021-24.
- **Causa**: a mesma da TURTLE (2026-10-14): a saída larga em tendência
  ganha com quase qualquer entrada numa moeda que sobe; comprar o
  rompimento é pior do que entrar ao acaso nessa mesma moeda. Quando a
  fase passou a lateral, os rompimentos falharam. A família "comprar a
  quebra em 4H" já está esgotada (TURTLE, SQUEEZE_BB, RETESTE,
  BRK_ESPACO, QUEBRA_COMPRADORES): **sem sucessor**. Nota para o Rui:
  morreu às 06:35 UTC, minutos depois do commit que a deixava em papel na
  fase de subida (d30c1f2).

### Mortes pelo corte dos clones: defeito no corte (sem sucessor)

- Às 04:50 UTC o ringue longo escolheu BOUNCE_ISOLADA como representante
  do grupo do Oversold Bounce e matou BOUNCE_X30_PAVIO, BOUNCE_X30,
  BOUNCE_X30_LIQ, BOUNCE_SQUEEZE, BOUNCE_TRAIL, BOUNCE_NOREACT,
  BOUNCE_FLUXO, BOUNCE_FORTE, BOUNCE_HORAS, BOUNCE_ABSORCAO e DIP_TREND
  como clones dela. Às 09:25 UTC o ringue longo voltou a ordenar o grupo,
  agora com BOUNCE_X30_PAVIO (já morta) como representante, e matou
  BOUNCE_ISOLADA, BOUNCE_G0, BOUNCE_V2 e BOUNCE_V3 como clones dela.
- **Resultado**: o grupo inteiro morreu, incluindo o lutador que devia
  ficar ("o melhor de cada grupo fica", `tools/arena_ringue.clones`). No
  combate de 90 dias, ISOLADA (63 op., +0,26R, p95 do acaso −0,05R) e
  PAVIO (64 op., +0,29R, p95 −0,04R) estavam ambas acima do p95 do acaso:
  eram a única família com vantagem medida. Da família só restam vivos
  BOUNCE_LSR, BOUNCE_DESALAV, BOUNCE_AMPLITUDE e BOUNCE_V1 (todos com
  menos de 25 operações no combate).
- **Causa técnica** (leitura do código, sem mexer): `clones()` ordena os
  candidatos sem excluir os já mortos e escolhe o representante de novo
  em cada corrida; `engine/arena.py` mata um clone mesmo quando o
  representante já está morto. A correção (só contar representantes
  vivos, ou fixar o representante enquanto viver, e decidir se a ISOLADA
  ou a PAVIO renasce) é em `engine/` e na regra de morte: fica para uma
  sessão com o Rui. Um sucessor seria outra variante do Bounce e seria
  cortado como clone outra vez: **sem sucessor**.

### Porque não há hipótese nova

As ideias de compra que restam com os dados do histórico são variantes de
famílias já rejeitadas (quebras, recuos técnicos, amplitude, reação ao
BTC, funding negativo) ou do Bounce que já está no ringue. Com 19
hipóteses contra esta reserva (cerca de 62% de probabilidade de pelo menos
um falso positivo a 5%) e 41 no contador global, mais uma hipótese fraca
só aumenta o ruído.

- Proposta para a próxima corrida: autópsia se morrer alguém; uma
  hipótese nova só quando `derivados.json` tiver histórico suficiente ou
  com uma ideia de entrada que não seja variante das famílias acima. Na
  corrida de 2026-10-25 o histórico terá 7 dias de atraso: correr primeiro
  o workflow "Historico para backtest".

## 2026-10-23 — Sem hipótese nova hoje; BOUNCE_LSR morta como clone de uma morta (sem sucessor)

**Veredicto da corrida: nenhuma hipótese testada.** O contador desta
reserva passa a 20 só pela H8 da afinação (SHORT_FUNDING, rejeitada em
2026-10-23); o global vai em 57.

- **Histórico** (ramo `history`): última atualização 2026-10-18, 5 dias de
  atraso (abaixo dos 7): não foi preciso correr o workflow. Na corrida de
  2026-10-25 terá 7 dias: correr primeiro "Historico para backtest".
- **Arena** (scan.json do ramo `data`, 2026-10-23 10:51 UTC): **8
  lutadores vivos** (ontem 9; mínimo 5), `recrutar` falso. Fila do Rui
  vazia. Vivos: BOUNCE_AMPLITUDE, BOUNCE_DESALAV, BOUNCE_V1,
  REVERSAO_INTERVALO, MAIORES_RECUO, MAIORES_TENDENCIA, SHORT_SQUEEZE,
  SHORT_MAIORES_TENDENCIA. Morto novo: BOUNCE_LSR.

### BOUNCE_LSR: morta pelo mesmo defeito do corte dos clones (sem sucessor)

- Morreu às 09:15 UTC como "clone de Mário" (BOUNCE_MACRO), correlação
  diária 0,96. BOUNCE_MACRO está morta desde 2026-10-19 (forma recente).
- No combate de 90 dias (`forma.json`, ramo `arena`, 37 moedas): 28 op.,
  19 ganhadoras, +0,108R (+0,105R líquido); com a mesma saída e entradas ao
  acaso, mediana −0,418R e p95 −0,173R: **acima do p95 do acaso**. Não
  morreria por desempenho.
- **Causa**: confirmada no código (`tools/arena_ringue.clones`, linha
  1430): os candidatos a representante são todos os lutadores com 20 ou
  mais operações no combate, vivos ou mortos; o ringue continua a correr os
  mortos, por isso um morto melhor classificado continua a "ficar" como
  representante e mata os vivos parecidos com ele. É a segunda vez em dois
  dias (ontem toda a família do Bounce).
- **Risco a seguir**: BOUNCE_DESALAV (16 op., +0,47R, p95 do acaso
  −0,07R) e BOUNCE_AMPLITUDE (13 op., +0,74R, p95 +0,04R), os dois vivos
  acima do acaso, ainda não entram no corte por terem menos de 20
  operações; quando chegarem às 20 podem ser mortos como clones de
  BOUNCE_X30 ou BOUNCE_ISOLADA, já mortas. A correção (só considerar
  representantes vivos; decidir se algum morto pelo defeito renasce) muda a
  regra de morte e `engine/arena.py`: não a fiz, fica para uma sessão com o
  Rui, com prioridade.
- **Sem sucessor**: um sucessor seria outra variante do Bounce e seria
  cortado como clone outra vez.

### Porque não há hipótese nova

As ideias de compra possíveis com os dados de 24 meses do histórico (velas
de 4H e 1H, fluxo comprador, funding) continuam a ser variantes de
famílias rejeitadas (quebras, recuos, amplitude, reação ao BTC, funding
negativo, acumulação de volume) ou do Bounce já no ringue. Juntar um
filtro de funding a uma entrada rejeitada seria uma colecção de filtros, não
uma entrada nova. Com 20 hipóteses contra esta reserva (cerca de 64% de
probabilidade de pelo menos um falso positivo), uma hipótese fraca só
acrescenta ruído; a prova útil continua a vir do combate e do papel ao
vivo, e neste momento o maior risco para essa prova é o defeito do corte
dos clones.

- Proposta para a próxima corrida: correr primeiro o workflow do histórico
  (7 dias de atraso); autópsia se morrer alguém; uma hipótese nova só com
  uma fonte ainda não usada com histórico suficiente (`derivados.json`
  desde 2026-10-20) ou uma ideia de entrada que não seja variante das
  famílias acima.

## 2026-10-24 — Sem hipótese nova hoje (sem mortos novos; fila vazia)

**Veredicto da corrida: nenhuma hipótese testada.** O contador desta
reserva fica em 20 (a afinação não testou nada desde a H8); o global fica
em 57.

- **Histórico** (ramo `history`): última atualização 2026-10-18, 6 dias de
  atraso (abaixo dos 7): não foi preciso correr o workflow. Amanhã terá 7.
- **Arena** (scan.json do ramo `data`): **8 lutadores vivos** (mínimo 5),
  `recrutar` falso, os mesmos de ontem. Nenhum morto novo desde BOUNCE_LSR
  (2026-10-23), que já tem linha na tabela dos sucessores. Fila do Rui
  vazia.
- **Combate de 90 dias** (`forma.json`, ramo `arena`, 40 moedas): dos
  vivos, só BOUNCE_DESALAV (17 op., +0,53R) e BOUNCE_AMPLITUDE (16 op.,
  +0,70R) estão positivos; BOUNCE_V1 (8 op., −0,05R), MAIORES_RECUO (17
  op., −0,02R), REVERSAO_INTERVALO (19 op., −0,11R) e os restantes estão
  perto de zero ou negativos com poucas operações. O risco registado
  ontem aproxima-se: DESALAV e AMPLITUDE estão a 3 e 4 operações das 20
  que as põem no corte dos clones, e os representantes mortos da família
  do Bounce (X30, ISOLADA, PAVIO) continuam a contar como "o melhor do
  grupo". A correção é em `engine/` e na regra de morte: sessão com o Rui,
  com prioridade.
- **Porque não há hipótese nova**: as mesmas razões de 2026-10-21 a
  2026-10-23. As entradas de compra possíveis com 24 meses de velas de 4H
  e 1H, fluxo comprador e funding são variantes de famílias rejeitadas ou
  do Bounce já no ringue; a ideia de compra fora da sobrevenda com mais
  lógica (reversão à média do rácio moeda/BTC na lateral) é a H9 proposta
  pela afinação e fica para ela, para não ser contada duas vezes. Com 20
  hipóteses contra esta reserva (cerca de 64% de probabilidade de pelo
  menos um falso positivo a 5%), uma hipótese fraca só acrescenta ruído.
- Proposta para a próxima corrida: correr primeiro o workflow do
  histórico (7 dias de atraso); autópsia se morrer alguém (sobretudo se
  DESALAV ou AMPLITUDE morrerem como clones de uma morta); uma hipótese
  nova só com uma fonte ainda não usada com histórico suficiente ou uma
  entrada que não seja variante das famílias acima.
