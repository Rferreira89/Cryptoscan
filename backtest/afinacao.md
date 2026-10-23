# Diário de afinação dos sinais

Hipóteses testadas sobre as estratégias que já estão ao vivo, uma por
entrada, com o veredicto. Hipóteses testadas até agora: 6.

## Decisões do Rui (valem para todas as execuções)

- 2026-10-03: NÃO restringir o universo de moedas. Não testar nem propor
  hipóteses que excluam moedas por serem pequenas ou pouco líquidas: pode
  haver boas oportunidades em qualquer uma. (Os filtros de spread e de
  volume que o motor já tem ficam como estão.)

## Fila de hipóteses pedidas pelo Rui (testar por esta ordem, antes de escolher outras)

1. (TESTADA em 2026-10-05, ver entrada H1: o score não prevê o resultado.)
   **O score prevê o resultado?** O motor só emite sinais com score de 65
   ou mais, mas nunca foi verificado se um score mais alto ganha mais.
   Testar: R médio por operação por faixas de score (65-69, 70-74, 75-79,
   80+) e a correlação entre score e resultado. Se o score separar ganhos
   de perdas, a hipótese a validar é um score mínimo mais alto (grelha:
   65, 70, 75, 80). Se não separar, dizer isso sem rodeios e indicar que
   famílias do score (regime, htf, structure, trigger, flow, liquidity,
   derivatives, rr) têm relação com o resultado e quais não têm: essa
   análise é a base da hipótese seguinte.

2. (PEDIDA em 2026-10-09, testar na próxima execução, antes da H4 "sem
   stop na entrada".) **Stop de tempo.** Lógica: operações que não chegam
   ao 1.º objetivo em poucos dias prendem capital e uma das 2 vagas, e
   com 0,5% de comissão ida e volta o tempo parado só custa; o Rui
   reparou nisto com a PUMP (aberta há 5,5 dias sem chegar a lado
   nenhum). Regra: se ao fim de N dias depois da entrada o 1.º objetivo
   ainda não foi atingido, fechar o resto da posição ao fecho da vela de
   4H seguinte. Grelha: N = 2, 3, 5, 7 dias e a versão atual (30 dias).
   Medir também o efeito nas vagas: com o stop de tempo libertam-se vagas
   mais cedo, por isso corre a seleção de carteira (afinacao_lib.trades)
   com cada N e não só a simulação isolada. Critérios: os de sempre,
   incluindo ficar acima do percentil 95 das entradas ao acaso (os
   controlos com o mesmo stop de tempo). Se reduzir a perda mas continuar
   negativa, regista "reduz a perda, continua negativa".

## Entradas

### 2026-10-05 — H1: o score prevê o resultado? (score mínimo mais alto)

**Escrito antes de correr qualquer teste.**

- Hipótese: se o score medir a qualidade do setup, operações com score
  mais alto devem ganhar mais; nesse caso, subir o score mínimo torna o
  sistema mais exigente e melhora o R médio por operação.
- Diagnóstico (só na janela de desenho): R médio por faixa de score
  (65-69, 70-74, 75-79, 80+), correlação de Spearman entre score e R, e
  correlação de cada família do score (regime, htf, structure, trigger,
  flow, liquidity, derivatives, rr) com o R.
- Grelha (4 configurações): score mínimo 65 (atual), 70, 75, 80.
- Sistema simulado: o que está ao vivo. Compras só com o BTC acima da
  média de 200 dias, shorts só com o BTC abaixo, no máximo 2 operações em
  simultâneo, comissão de 0,25% por lado, slippage de 0,05%, juros de
  0,05% por dia nos shorts. Código: `tools/afinacao_lib.py` e
  `tools/afinacao_h01_score.py`.
- Janela: últimos 548 dias de velas (18 meses); desenho = primeiros 365
  dias, reserva = últimos 183 dias. Walk-forward ancorado no desenho:
  treino desde o início do desenho (primeiro treino de 121 dias), 4
  janelas de teste de 61 dias; em cada uma aplica-se o score mínimo com
  melhor R médio no treino (mínimo de 20 operações no treino, senão fica
  o atual) e compara-se com o score 65 na mesma janela.
- Configuração final: a de melhor R médio em todo o desenho com pelo
  menos 30 operações. Só essa é avaliada na reserva, uma única vez.
- Critérios para aprovar (todos): R médio > 0 fora da amostra no
  walk-forward; pelo menos 60 operações fora da amostra e 30 na reserva;
  melhor do que o score 65 em pelo menos 60% das janelas (3 de 4); R
  médio > 0 na reserva; R médio > 0 sem a melhor moeda.

**Resultados** (velas até 2026-10-02; 64 moedas com histórico suficiente,
8 recentes ficaram de fora por terem menos de 2500 velas: ASTER, AVNT,
PLUME, PUMP, ROBO, SKY, WAL, XPL).

- Janela: desenho de 2025-04-02 a 2026-04-02, reserva de 2026-04-02 a
  2026-10-02.
- Versão atual (score 65) no desenho: 127 operações, 36,2% de acerto,
  −0,101R por operação. Compras: 72 operações, −0,115R. Shorts: 55,
  −0,084R. Por estratégia: PULLBACK 27 (−0,02R), LIQUIDITY_SWEEP 26
  (−0,04R), BREAKOUT 18 (−0,32R), PULLBACK_SHORT 24 (−0,03R),
  BREAKOUT_SHORT 17 (−0,13R), LIQUIDITY_SWEEP_SHORT 13 (−0,06R), RANGE e
  RANGE_SHORT 1 cada. Nenhuma tem amostra para conclusões isoladas.
- R médio por faixa de score (desenho, operações com as regras de
  carteira):

  | Score | Operações | Acerto | R médio |
  |---|---|---|---|
  | 65-69 | 35 | 48,6% | −0,100 |
  | 70-74 | 24 | 29,2% | −0,118 |
  | 75-79 | 32 | 31,2% | −0,296 |
  | 80+ | 36 | 33,3% | +0,081 |

- Correlação de Spearman entre score e R: −0,17 nas 127 operações. Em
  todos os 1166 candidatos fechados do desenho com score de 50 ou mais
  (sem regras de carteira): −0,19, e −0,205R por operação; por faixas:
  50-54 −0,47R (12), 55-59 −0,25R (98), 60-64 −0,15R (180), 65-69 −0,24R
  (155), 70-74 −0,10R (164), 75-79 −0,30R (217), 80+ −0,19R (340). Estes
  candidatos repetem-se em velas seguidas, por isso não são independentes
  e o sinal da correlação vale mais do que o seu tamanho.
- **O score não separa ganhos de perdas.** A relação é nula ou
  ligeiramente invertida: scores mais altos têm menos acerto (33% acima
  de 80 contra 49% entre 65 e 69). O +0,08R da faixa 80+ nas operações
  não se confirma nos 340 candidatos da mesma faixa (−0,19R).
- Famílias do score (correlação com o R: operações 65+ / candidatos 50+):
  - regime: −0,15 / −0,18. Relação invertida: regime "melhor" deu pior.
  - rr: −0,18 / −0,19. Invertida: R:R prometido mais alto deu pior
    (alvos mais longe são atingidos menos vezes).
  - flow: −0,10 / −0,09. Ligeiramente invertida.
  - htf: −0,13 / −0,08. Ligeiramente invertida, com poucos casos de
    conflito.
  - structure: −0,02 / −0,04. Sem relação.
  - liquidity: +0,05 / 0,00. Sem relação.
  - trigger: +0,10 / +0,01. É a única com sinal certo: com vela de
    gatilho forte (engolfo ou pin bar) 39 operações deram +0,22R e 48,7%
    de acerto, contra −0,24R nas outras 88; nos candidatos, −0,12R (280)
    contra −0,23R (886). Diferença pequena e ainda não testada fora da
    amostra.
  - derivatives: sem histórico no backtest (sempre neutra), não avaliável.
- Grelha no desenho: score 65 → 127 operações, −0,101R; 70 → 117,
  −0,137R; 75 → 96, −0,150R; 80 → 66, −0,101R. Nenhuma positiva, nenhuma
  melhor do que a atual.
- Walk-forward (4 janelas de teste de 61 dias, 2025-08-01 a 2026-04-02):
  85 operações fora da amostra, 28,2% de acerto, −0,297R. O score 65 nas
  mesmas janelas: 80 operações, −0,208R. Janelas em que o filtro melhorou:
  0 de 4 (em três o treino escolheu o próprio 65; na última escolheu 80 e
  deu −0,16R contra +0,40R do 65).
- Configuração escolhida no desenho: score 65, ou seja, a atual. Sem a
  melhor moeda (UNI): 124 operações, −0,175R.
- Reserva (avaliada uma vez, score 65): 61 operações, 42,6% de acerto,
  −0,089R; sem a melhor moeda (OP): 59 operações, −0,142R. Fica como
  referência da versão atual na reserva para as próximas hipóteses.
- Linha informativa do período antigo (2021-01-01 a 2025-04-02, não conta
  para o veredicto): score 65 → 467 operações, −0,327R; 70 → −0,306R
  (414); 75 → −0,302R (347); 80 → −0,298R (209).
- Ao vivo: 2 operações abertas e executadas (PUMP, WLD), 1 sinal
  cancelado, 0 fechadas. Sem amostra; nada a concluir.

**Veredicto: REJEITADA.** Subir o score mínimo não melhora o resultado em
nenhum dos testes. O score, tal como está, não mede a qualidade do setup.

Notas para as próximas execuções:

- Os números desta janela usam a comissão de 0,25% por lado de
  `config.json`; o `backtest/results.json` antigo foi feito com outras
  condições e não é diretamente comparável.
- Próxima hipótese proposta (H2): exigir vela de gatilho forte (engolfo
  ou pin bar na vela do sinal) em todas as estratégias. É a única família
  com relação no sentido certo. Foi vista nos dados do desenho, por isso
  tem de passar o walk-forward e a reserva antes de valer alguma coisa.
- Hipóteses testadas até agora: 1.

### 2026-10-07 — H2: exigir vela de gatilho forte (engolfo ou pin bar)

**Escrito antes de correr qualquer teste.**

- Hipótese: uma vela de 4H de engolfo ou pin bar no momento do sinal
  mostra que o outro lado do mercado foi rejeitado nessa vela; sem ela, o
  setup é só "o preço chegou à zona". Exigir essa vela torna o sistema
  mais exigente e deve melhorar o R médio. Origem: no diagnóstico da H1
  foi a única família do score com relação no sentido certo (+0,22R em 39
  operações contra −0,24R em 88). Esse número foi visto no desenho, por
  isso não prova nada: o teste é o walk-forward e a reserva.
- Grelha (4 configurações): atual (sem filtro); gatilho forte exigido em
  todas as estratégias; só nas compras; só nos shorts. Nos shorts o
  padrão é o espelhado (engolfo ou pin bar de baixa).
- Sistema simulado: o que está ao vivo hoje, igual ao da H1 nas regras de
  carteira e nos custos (comissão de 0,25% por lado, slippage de 0,05%,
  juros nos shorts). O motor mudou desde a H1 (stop mínimo de 1,25 ATR,
  primeiro objetivo a no máximo 2,5R, estratégia RANGE desligada), por
  isso a versão atual é recalculada e os números da H1 já não servem de
  comparação direta. Código: `tools/afinacao_h02_gatilho.py`.
- Janela: a mesma da H1 (o histórico continua com velas até 2026-10-02):
  desenho de 2025-04-02 a 2026-04-02, reserva de 2026-04-02 a 2026-10-02.
  Walk-forward ancorado, 4 janelas de teste de 61 dias; em cada uma
  aplica-se a configuração com melhor R médio no treino (mínimo de 20
  operações no treino, senão fica a atual).
- Configuração final: a de melhor R médio em todo o desenho com pelo
  menos 30 operações. Só essa é avaliada na reserva, uma única vez. Se a
  escolhida for a atual, a hipótese fica rejeitada.
- Critérios para aprovar (todos): R médio > 0 fora da amostra no
  walk-forward; pelo menos 60 operações fora da amostra e 30 na reserva
  (senão AMOSTRA INSUFICIENTE); melhor do que a atual em pelo menos 3 das
  4 janelas; R médio > 0 na reserva; R médio > 0 sem a melhor moeda.
- Risco conhecido à partida: só cerca de 30% das operações têm gatilho
  forte, por isso é provável que a amostra não chegue aos mínimos.

**Resultados** (velas até 2026-10-02; 64 moedas, as mesmas 8 recentes de
fora por histórico curto).

- Janela: desenho de 2025-04-02 a 2026-04-02, reserva de 2026-04-02 a
  2026-10-02.
- Versão atual no desenho, com o motor de hoje: 119 operações, 37,0% de
  acerto, −0,201R por operação. Compras: 63, −0,238R. Shorts: 56,
  −0,161R. Por estratégia: PULLBACK 22 (+0,02R), LIQUIDITY_SWEEP 26
  (−0,16R), BREAKOUT 15 (−0,76R, 13% de acerto), PULLBACK_SHORT 28
  (−0,26R), BREAKOUT_SHORT 15 (+0,09R), LIQUIDITY_SWEEP_SHORT 12
  (−0,16R). Nenhuma tem amostra para conclusões isoladas.
- Nota: com o motor de 2026-10-05 a mesma janela deu −0,101R em 127
  operações (H1). As alterações de 4 a 7 de outubro (stop mínimo de 1,25
  ATR, primeiro objetivo a no máximo 2,5R) foram justificadas com o
  histórico de 2021 a 2026 e, na janela recente, o resultado ficou
  −0,10R pior. Com cerca de 120 operações essa diferença está dentro do
  ruído (erro-padrão perto de 0,12R): não prova que pioraram, mas também
  não há sinal de que tenham ajudado no mercado recente.
- Gatilho forte dentro das operações atuais (desenho): 28 operações com
  gatilho forte, 39,3% de acerto, −0,240R; 91 sem ele, 36,3%, −0,189R.
  **A vantagem vista na H1 (+0,22R contra −0,24R) desapareceu** com o
  motor de hoje: era ruído de uma amostra de 39 operações.
- Grelha no desenho: atual → 119 operações, −0,201R; todas → 61, −0,142R;
  só compras → 84, −0,110R; só shorts → 96, −0,243R. Nenhuma positiva.
- Walk-forward (4 janelas de teste de 61 dias, 2025-08-01 a 2026-04-02):
  56 operações fora da amostra, 37,5% de acerto, −0,257R. A versão atual
  nas mesmas janelas: 77 operações, −0,205R. Janelas em que o filtro
  melhorou: 1 de 4 (escolhas do treino: shorts, todas, todas, todas;
  testes −0,20R, −0,58R, −0,54R, +0,22R contra −0,20R, −0,47R, −0,32R,
  +0,19R da atual).
- Configurações fixas nas mesmas janelas de teste (sem escolha no
  treino, só informativo): todas → 46 operações, −0,154R; só compras →
  64, −0,086R; só shorts → 59, −0,295R.
- Configuração escolhida no desenho: gatilho forte só nas compras (84
  operações, −0,110R). Sem a melhor moeda (UNI): 81 operações, −0,188R.
- Reserva (avaliada uma vez): escolhida → 42 operações, 42,9% de acerto,
  −0,132R; atual → 50 operações, 44,0%, −0,084R. Na reserva o filtro
  ficou pior do que a versão atual. Sem a melhor moeda (PYTH): 40
  operações, −0,205R.
- Linha informativa do período antigo (2021-01-01 a 2025-04-02, não conta
  para o veredicto): atual → 347 operações, −0,227R; todas → 173,
  −0,164R; só compras → 244, −0,217R; só shorts → 276, −0,196R.
- Ao vivo (state.json de 2026-10-07): 5 operações fechadas, todas no
  stop, −1,17R de média (BREAKOUT 3, PULLBACK 2). Executadas pelo Rui: 3
  fechadas, −1,24R de média com o preço real de entrada, e 1 aberta
  (PUMP). Preço real contra o do sistema: ENA BREAKOUT 0,2470 contra
  0,24565 (0,55% pior), ENA PULLBACK 0,2401 contra 0,2400 (0,04% pior).
  A ENA PULLBACK fechou a −1,54R: a saída foi a 0,2261 com o stop em
  0,2314 (o preço passou o stop antes de a passagem seguinte o ver).
  Três dos stops caíram em 8 minutos na madrugada de 7 de outubro, na
  mesma queda de mercado, por isso não são 5 provas independentes. O
  travão de perdas está ativo (−3,6R num dia). **A amostra (5, e no
  máximo 3 por estratégia) não chega para concluir nada; o mínimo são 30
  por estratégia.**

**Veredicto: REJEITADA.** Falha quatro critérios: R médio negativo no
walk-forward (−0,257R, pior do que a atual), 56 operações fora da amostra
(mínimo 60), melhoria em 1 de 4 janelas, reserva negativa e pior do que a
atual. Exigir engolfo ou pin bar não melhora os sinais.

Notas para as próximas execuções:

- Duas hipóteses sobre "qualidade do setup" (score e vela de gatilho)
  falharam. O score e os seus componentes não distinguem operações boas
  de más; não vale a pena testar mais filtros tirados das famílias do
  score.
- Próxima hipótese proposta (H3): desligar o BREAKOUT de compra. No
  desenho deu −0,76R em 15 operações com 13% de acerto, na H1 −0,32R em
  18, e ao vivo 3 stops em 3. Lógica: nas altcoins, a compra do rompimento
  em 4H entra tarde e apanha o recuo. A amostra por estratégia é pequena,
  por isso o risco de AMOSTRA INSUFICIENTE é alto; a grelha deve comparar
  apenas: atual, sem BREAKOUT, sem BREAKOUT e sem BREAKOUT_SHORT.
- Hipóteses testadas até agora: 2. Com duas tentativas nos mesmos 18
  meses, a probabilidade de uma passar por acaso ainda é baixa, mas sobe
  a cada execução.

### 2026-10-09 — H3: desligar o BREAKOUT de compra

**Escrito antes de correr qualquer teste.**

- Hipótese: nas altcoins, a compra do rompimento em 4H entra tarde, com o
  movimento já feito, e apanha o recuo; desligar a estratégia BREAKOUT
  (compra) tira ao sistema as suas piores operações e melhora o R médio.
  Origem: no desenho deu −0,76R em 15 operações (H2) e −0,32R em 18 (H1),
  e ao vivo 3 stops em 3. Esses números foram vistos no desenho, por isso
  não provam nada: o teste é o walk-forward e a reserva.
- Grelha (3 configurações): atual; sem BREAKOUT; sem BREAKOUT e sem
  BREAKOUT_SHORT (o espelho, para ver se o problema é do rompimento em
  si ou só do lado da compra).
- Atenção ao efeito de carteira: com o limite de 2 operações em
  simultâneo, desligar uma estratégia liberta vagas e entram outras
  operações. A simulação refaz a carteira para cada configuração, por
  isso o resultado já inclui essa troca.
- Diagnóstico (só no desenho, informativo): R médio de todos os
  candidatos BREAKOUT e BREAKOUT_SHORT sem regras de carteira (amostra
  maior, mas com candidatos repetidos em velas seguidas).
- Sistema simulado: o que está ao vivo hoje, igual ao da H2 (o motor não
  mudou no que toca ao backtest desde 2026-10-07: as alterações foram ao
  acompanhamento ao vivo e à página). Comissão de 0,25% por lado,
  slippage de 0,05%, juros nos shorts. Código:
  `tools/afinacao_h03_breakout.py`.
- Janela: a mesma da H1 e da H2. O histórico tem velas até 2026-10-02
  (6,9 dias de atraso, abaixo do limite de 7 que obriga a atualizar):
  desenho de 2025-04-02 a 2026-04-02, reserva de 2026-04-02 a 2026-10-02.
  Walk-forward ancorado, 4 janelas de teste de 61 dias; em cada uma
  aplica-se a configuração com melhor R médio no treino (mínimo de 20
  operações no treino, senão fica a atual).
- Configuração final: a de melhor R médio em todo o desenho com pelo
  menos 30 operações. Só essa é avaliada na reserva, uma única vez. Se a
  escolhida for a atual, a hipótese fica rejeitada.
- Critérios para aprovar (todos): R médio > 0 fora da amostra no
  walk-forward; pelo menos 60 operações fora da amostra e 30 na reserva
  (senão AMOSTRA INSUFICIENTE); melhor do que a atual em pelo menos 3 das
  4 janelas; R médio > 0 na reserva; R médio > 0 sem a melhor moeda.
  Passar de negativo para menos negativo é "REDUZ A PERDA", não aprovação.
- Risco conhecido à partida: a reserva atual tem 50 operações; é a
  terceira vez que esta reserva é usada (H1, H2, H3), por isso já não é
  totalmente virgem.

**Resultados** (velas até 2026-10-02; 64 moedas, as mesmas 8 recentes de
fora por histórico curto).

- Janela: desenho de 2025-04-02 a 2026-04-02, reserva de 2026-04-02 a
  2026-10-02.
- Correção de fidelidade feita antes de ver a reserva: o backtest não
  aplicava `disabled_strategies`, e uma operação RANGE_SHORT (desligada
  ao vivo) entrava na carteira. As três configurações passaram a excluir
  as estratégias desligadas ao vivo. O total não mudou (a vaga foi ocupada
  por outra operação).
- Versão atual no desenho: 122 operações, 36,9% de acerto, −0,207R.
  Compras: 64, −0,221R. Shorts: 58, −0,191R. Por estratégia: PULLBACK 22
  (+0,02R), LIQUIDITY_SWEEP 27 (−0,12R), BREAKOUT 15 (−0,76R, 13% de
  acerto), PULLBACK_SHORT 29 (−0,29R), BREAKOUT_SHORT 17 (−0,04R),
  LIQUIDITY_SWEEP_SHORT 12 (−0,16R). Na H2 a mesma janela deu 119
  operações e −0,201R; a diferença de 3 operações vem de os candidatos
  terem sido gerados de novo e não a consegui atribuir a uma alteração
  concreta. Está dentro do ruído, mas fica registada.
- Diagnóstico, todos os candidatos de rompimento no desenho (sem regras
  de carteira, com repetições): BREAKOUT 93 candidatos, 28,0% de acerto,
  −0,301R; BREAKOUT_SHORT 86, 45,3%, +0,047R. O BREAKOUT de compra é
  mau, mas menos do que as 15 operações sugeriam (−0,30R e não −0,76R).
- Grelha no desenho: atual → 122 operações, −0,207R; sem BREAKOUT → 113,
  −0,162R; sem BREAKOUT e sem BREAKOUT_SHORT → 104, −0,160R. Nenhuma
  positiva. Sem os dois rompimentos saíram 32 operações e entraram 14
  de outras estratégias nas vagas libertadas, e essas também perderam: o
  PULLBACK passou de +0,02R (22) para −0,02R (26) e o LIQUIDITY_SWEEP de
  −0,12R (27) para −0,23R (29).
- Walk-forward (4 janelas de teste de 61 dias, 2025-08-01 a 2026-04-02):
  71 operações fora da amostra, 35,2% de acerto, −0,162R. A versão atual
  nas mesmas janelas: 78 operações, −0,216R. Janelas em que melhorou: 3
  de 4 (escolhas do treino: sem BREAKOUT, sem BREAKOUT, sem os dois, sem
  os dois; testes −0,11R, −0,44R, −0,16R, +0,08R contra −0,20R, −0,47R,
  −0,36R, +0,19R da atual).
- Configurações fixas nas mesmas janelas de teste (informativo): sem
  BREAKOUT → 75 operações, −0,183R; sem os dois → 69, −0,177R.
- Configuração escolhida no desenho: sem BREAKOUT e sem BREAKOUT_SHORT
  (104 operações, −0,160R; a diferença para "sem BREAKOUT" é de 0,002R,
  ou seja, nenhuma). Sem a melhor moeda (UNI): 100 operações, −0,230R.
- Reserva (avaliada uma vez): escolhida → 45 operações, 35,6% de acerto,
  **−0,232R**; atual → 52 operações, 42,3%, −0,119R. **Na reserva
  desligar os rompimentos ficou pior do que a versão atual.** Sem a
  melhor moeda (ICP): 44 operações, −0,286R. Porquê: na reserva o
  BREAKOUT de compra quase não operou (2 operações, as duas no stop) e o
  BREAKOUT_SHORT foi a melhor estratégia (11 operações, 64% de acerto,
  +0,28R); ao desligá-lo, as vagas foram para o PULLBACK_SHORT (de 15
  para 20 operações, −0,49R). A escolha do espelho no desenho assentava
  numa diferença de 0,002R e a reserva castigou-a. Não avaliei "sem
  BREAKOUT" sozinho na reserva: a regra é uma configuração, uma vez.
- Linha informativa do período antigo (2021-01-01 a 2025-04-02, não conta
  para o veredicto): atual → 339 operações, −0,208R; sem BREAKOUT → 289,
  −0,222R; sem os dois → 260, −0,266R. No período antigo desligar os
  rompimentos também não ajudava.
- Ao vivo (state.json de 2026-10-09): sem operações fechadas novas desde
  a H2. 5 fechadas, todas no stop, −1,00R de média (os stops passaram a
  contar ao preço do stop; antes a média era −1,17R). BREAKOUT 3 (0
  ganhas), PULLBACK 2 (0 ganhas). Executadas pelo Rui: 3 fechadas
  (BREAKOUT 2, PULLBACK 1), −1,00R de média, e 1 aberta (PUMP
  LIQUIDITY_SWEEP). Aberta em papel: ENA LIQUIDITY_SWEEP. Preço real
  contra o do sistema: ENA BREAKOUT 0,2470 contra 0,24565 (0,55% pior);
  ENA PULLBACK 0,2401 contra 0,2400 (0,04% pior). Na ENA BREAKOUT o stop
  estava a 1,03% da entrada do sistema; com a entrada real a distância
  foi 1,59%, ou seja, com a mesma quantidade a perda em USDC foi cerca de
  1,5 vezes a planeada. Um caso não faz regra, mas com stops tão curtos
  meio por cento de atraso na entrada pesa muito. **A amostra (5, no
  máximo 3 por estratégia) não chega para concluir nada; o mínimo são 30
  por estratégia.**

**Veredicto: REJEITADA.** No desenho reduz a perda (−0,16R contra −0,21R
no walk-forward, melhor em 3 de 4 janelas, 71 operações), mas continua
negativa, e na reserva fica pior do que a versão atual (−0,23R contra
−0,12R). Falha três critérios: R médio negativo no walk-forward, reserva
negativa, negativo sem a melhor moeda. O BREAKOUT de compra é a pior
estratégia no desenho, mas tirá-lo não torna o sistema positivo: as vagas
passam para operações que também perdem.

Notas para as próximas execuções:

- Três hipóteses de filtro de entrada falharam (score, vela de gatilho,
  desligar rompimentos). O resultado por estratégia muda de sinal entre o
  desenho e a reserva (BREAKOUT_SHORT −0,04R → +0,28R; PULLBACK_SHORT
  −0,29R → −0,30R a −0,49R; PULLBACK +0,02R → +0,42R), com 10 a 30
  operações cada: escolher estratégias com esta amostra é escolher ruído.
- A reserva de 2026-04-02 a 2026-10-02 já foi vista três vezes. Na
  próxima execução o histórico terá mais de 7 dias: correr o workflow
  "Historico para backtest" primeiro; a janela avança e a reserva ganha
  dados novos.
- Próxima hipótese proposta (H4), do lado da saída e não da entrada: não
  passar o stop para a entrada depois do 1.º objetivo. Lógica: com 37% de
  acerto e stops de 1,25 ATR, o recuo normal depois do 1.º objetivo tira
  a operação a zeros antes de chegar ao 2.º, e a comissão de 0,5% (ida e
  volta) transforma esses zeros em perdas pequenas. Grelha: atual; sem
  passagem para a entrada nas compras e nos shorts. `afinacao_lib.py` já
  guarda a simulação sem essa passagem para as compras (`nb`); falta
  fazer o mesmo para os shorts.
- Hipóteses testadas até agora: 3. Com três tentativas nos mesmos 18
  meses, a probabilidade de uma passar por acaso continua baixa, mas sobe
  a cada execução; nenhuma chegou perto de passar.

## Mudança de alvo (2026-10-13)

A arena matou as quatro estratégias que davam sinais reais (Recuo, Quebra,
Sweep, Tendência diária) e o lutador dos setups rejeitados. As hipóteses
H1 a H3 e a fila acima (stop de tempo, sem stop na entrada) eram sobre
essas estratégias e deixam de ter objeto. A partir da H4 este diário afina
os lutadores VIVOS da arena (as variantes do Oversold Bounce), para que
cheguem mais depressa e com mais margem ao critério de dinheiro real (30
operações ao vivo acima do percentil 95 do acaso e o sim do Rui).

### 2026-10-14 — H4: tempo máximo mais curto no Bounce RSI 30 (Xavier)

**Escrito antes de correr qualquer teste.**

- Lutador: BOUNCE_X30 ("Xavier"), o tronco de onde saem nove dos
  lutadores vivos (FLUXO, FORTE, SQUEEZE, ISOLADA, NOREACT, TRAIL, HORAS,
  DESALAV, MACRO, ...): uma melhoria na saída dele passa para todos. Gatilho
  exatamente o de `tools/arena_ringue.sig_x30` (o que o ringue e o papel
  usam): BTC acima da SMA200 diária; RSI14 de 4H abaixo de 30 numa das
  últimas 3 velas; fecho acima do máximo da vela anterior com o RSI a subir;
  stop no mínimo das 6 velas menos 0,1 ATR (no mínimo 1,25 ATR); 50% na
  média de 20 velas, resto no máximo das 42 velas anteriores; stop na
  entrada depois do 1.º objetivo. Hoje sai ao fim de 3 dias.
- Hipótese (saída): o ressalto de uma sobrevenda é rápido; se a moeda não
  chegou à média de 20 velas em pouco tempo, a pressão vendedora não
  acabou e o que resta é risco de voltar ao stop. Encurtar o tempo
  máximo corta essas operações perto da entrada (perda pequena em vez de
  −1R), liberta a moeda e a vaga mais cedo (mais operações por mês) e
  deve subir o R médio.
- Grelha (6 configurações, só muda o tempo máximo): 12 h, 1 dia, 1,5
  dias, 2 dias, 3 dias (atual), 5 dias (o sentido contrário, para ver se
  a relação é monótona).
- Simulação: `tools/research_rlib.simulate` (decisão no fecho, entrada na
  abertura seguinte, `engine/trade.py`, conta o stop se stop e objetivo
  caem na mesma vela), carteira de 4 operações de 25%, uma por moeda,
  primeiro o RSI mais baixo; comissão 0,25% + slippage 0,1% por lado.
  Universo: todas as moedas do ramo `history` com velas suficientes (sem
  excluir as recentes). Código: `tools/afinacao_h04_tempo.py`.
- Janela: últimos 18 meses até ao último dia completo do histórico;
  desenho = primeiros 12 meses, reserva = últimos 6. Walk-forward ancorado
  no desenho: primeiro treino de 121 dias, 4 janelas de teste de 61 dias;
  em cada uma aplica-se o tempo com melhor R médio no treino (mínimo de 20
  operações no treino, senão fica o atual) e compara-se com os 3 dias na
  mesma janela.
- Configuração final: a de melhor R médio em todo o desenho com pelo
  menos 30 operações. Só essa é avaliada na reserva, uma única vez. Se a
  escolhida for a atual (3 dias), a hipótese fica REJEITADA.
- Teste contra o acaso: as operações fora da amostra (janelas de teste e
  reserva), cada uma com controlos na mesma moeda até ±90 velas, mesma
  geometria e mesmo tempo máximo; 1000 séries.
- Critérios para APROVAR (todos): R médio > 0 fora da amostra no
  walk-forward; pelo menos 60 operações fora da amostra no desenho e 30 na
  reserva (senão AMOSTRA INSUFICIENTE); melhor do que os 3 dias em pelo
  menos 3 das 4 janelas; R médio > 0 na reserva; R médio > 0 sem a melhor
  moeda (fora da amostra e na reserva); acima do percentil 95 do acaso.
  Se ficar acima do percentil 95 do acaso sem ganhar à versão atual, não
  vai para o ringue: o Xavier já lá está com a mesma entrada.
- Hipóteses testadas até agora (com esta): 4 neste diário; 10 contra os
  mesmos dados contando o diário de investigação.

**Resultados** (velas até 2026-10-11 08:00 UTC, 3 dias de atraso; 69
moedas, nenhuma de fora; `backtest/afinacao_h04_tempo.json`).

- Janela: desenho de 2025-04-11 a 2026-04-10, reserva de 2026-04-11 a
  2026-10-10.
- Grelha no desenho (carteira de 4 × 25%):

  | Tempo máximo | Operações | Acerto | R médio | Sem a melhor moeda |
  |---|---|---|---|---|
  | 12 h | 184 | 40,8% | −0,140 | −0,153 |
  | 1 dia | 147 | 46,9% | −0,111 | −0,128 |
  | 1,5 dias | 139 | 49,6% | −0,123 | −0,145 |
  | 2 dias | 124 | 52,4% | −0,128 | −0,156 |
  | **3 dias (atual)** | 122 | 55,7% | **−0,084** | −0,115 |
  | 5 dias | 120 | 49,2% | −0,146 | −0,183 |

  Nenhuma positiva. Encurtar o tempo dá mais operações (até +50% com 12 h)
  mas baixa o acerto e o R médio: as operações cortadas cedo saem com
  perda pequena, mas muitas delas teriam chegado ao 1.º objetivo. A
  ideia "se não reage depressa, não vai reagir" não se confirma.
- Walk-forward (4 janelas de 61 dias, 2025-08-10 a 2026-04-10): o treino
  escolheu os 3 dias (a versão atual) em todas as janelas. 52 operações
  fora da amostra, 51,9% de acerto, −0,148R; sem a melhor moeda (EIGEN)
  −0,204R. Janelas melhores do que a atual: 0 de 4 (iguais nas duas
  primeiras; nas duas últimas, 2025-12-10 a 2026-04-10, não houve
  operações porque o BTC esteve abaixo da média de 200 dias).
- Configuração escolhida no desenho: 3 dias, ou seja, a atual. Pela regra
  declarada, a hipótese fica REJEITADA e a reserva não avalia nenhuma
  alternativa.
- Referência (só a versão atual, nada escolhido): reserva 30 operações,
  50,0% de acerto, +0,090R; sem a melhor moeda (TIA) −0,028R.
- Contra o acaso (versão atual, mesma geometria, ±90 velas, 1000 séries):
  walk-forward −0,148R contra mediana de −0,290R e p95 de −0,104R,
  **percentil 90,5**; reserva +0,090R contra mediana −0,170R e p95
  +0,153R, **percentil 91,0**. O gatilho do Xavier é melhor do que o acaso,
  mas não chega ao percentil 95 em nenhum dos dois blocos.
- Linha informativa do período antigo (2023-04-11 a 2025-04-10, não conta):
  3 dias → 380 operações, 48,2% de acerto, −0,218R.

**Veredicto: REJEITADA.** O tempo máximo de 3 dias já é o melhor da
grelha; qualquer tempo mais curto (ou mais longo) piora o R médio. Nada
entra no ringue.

Leitura importante para o Rui (não é uma hipótese, é o que os números
mostram): no combate dos últimos 90 dias o Xavier leva 92 operações a
+0,50R, acima do p95 do acaso. Nos 12 meses de desenho, com a mesma
função de sinal e a mesma saída, dá −0,08R (122 operações) e no período
antigo −0,22R (380). Na reserva (abril a outubro de 2026) dá +0,09R com a
carteira de 4 vagas. A forma recente do Bounce vem sobretudo de um
trimestre favorável; os 90 dias do ringue não chegam para dizer que a
vantagem é estável. Por isso o critério de 30 operações AO VIVO acima do
p95 continua a ser a prova que conta, e convém esperar que ele seja
cumprido também num período de mercado diferente.

Notas para as próximas execuções:

- A saída por tempo está afinada (3 dias). Não voltar a testar o tempo.
- O resultado está muito ligado ao regime: em 12 meses houve 4 meses sem
  operações (BTC abaixo da SMA200) e as janelas com operações perderam.
- Próxima hipótese proposta (H5), sobre a saída e sem mexer no gatilho:
  vender 100% na média de 20 velas (sem a segunda metade até ao máximo de
  7 dias). Nos 122 trades do desenho só 3 chegaram ao 2.º objetivo e 25
  saíram a zeros depois do 1.º: a segunda metade quase nunca paga e custa
  comissão e tempo. Grelha a fixar antes: parte vendida no 1.º objetivo ∈
  {50% (atual), 75%, 100%}, com e sem stop na entrada depois do 1.º.
- Hipóteses testadas até agora: 4 neste diário (H1 a H4); 10 contra os
  mesmos dados contando o diário de investigação. Com 10 tentativas, a
  probabilidade de pelo menos um falso positivo a 5% ronda os 40%.

### 2026-10-16 — H5: shorts da sobrecompra só em mercado de descida (SHORT_QUEDA)

**Escrito antes de correr qualquer teste.**

- Situação: regime atual (scan.json) **subida**. No ringue longo (365
  dias, longo.json de 2026-10-15) os vivos são todos de compra (sobrevenda
  + DIP_TREND) e ganham em subida e lateral; **na descida não há nenhum
  campeão vivo** (as compras nem operam com o BTC abaixo da SMA200). Os
  shorts morreram todos no combate de 90 dias, mas no ringue longo o
  SHORT_X30 ganha na descida (113 op., +0,351R, p95 do acaso +0,094) e o
  SHORT_ISOLADA também (96 op., +0,292R, p95 +0,113); perdem em subida e
  lateral, e foi aí que morreram (o ringue corre os shorts sem filtro).
- Hipótese (correção de um morto que ganha noutro regime): em mercado de
  descida, os ressaltos que levam o RSI de 4H acima de 70 são alívio sem
  compradores de fundo e falham; vender a viragem da sobrecompra só nesse
  regime tem vantagem. Só se acrescenta um filtro de regime a um short
  existente, sem mudar gatilho nem saídas (espelho de `sig_x30` /
  `sig_short_isolada`, objetivos G0, stop na entrada depois do 1.º, 3 dias).
- AVISO: a ideia nasce de ter visto a divisão por regime do ringue longo.
  A janela de 365 dias está portanto VISTA e só conta como informação. O
  teste que decide é fora dessa janela.
- Grelha (4): sinal ∈ {SHORT_X30, SHORT_ISOLADA} × filtro ∈ {Q: regime do
  BTC "queda" no último dia fechado (as regras de `regime_by_day`: fecho <
  SMA50 < SMA200 e −8% em 30 dias); S: BTC abaixo da SMA200 no último dia
  fechado}.
- Método: `tools/arena_ringue.generic_trades` sobre as velas espelhadas
  (exatamente como o ringue corre os shorts), uma operação de cada vez por
  moeda, entrada na abertura seguinte, 0,25% de comissão + 0,1% de
  slippage por lado; contra o acaso com `judge` (controlos na mesma moeda,
  ±90 velas, mesma geometria, no espelho). Histórico do ramo `history`
  (71 moedas, 4H desde 2021-01-01 até 2026-10-11). Juros da margem não
  entram no R do ringue; reporto à parte o custo estimado.
- Janelas: **B (decide, nunca vista com esta divisão)**: 2021-08-01 a
  2025-10-10 (inclui a descida de 2022). **A (vista, informativa)**:
  2025-10-11 a 2026-10-11. **C**: combate de 90 dias até 2026-10-11 (com
  o regime de subida/lateral deve dar 0 operações: um lutador de descida
  fica à espera do seu regime).
- Escolha: entre as configurações que cumprirem todos os critérios em B,
  a de maior R médio em B. Critérios (todos, em B): ≥ 40 operações; R
  médio > 0; acima do percentil 95 do acaso; R médio > 0 sem a melhor
  moeda; R médio > 0 em pelo menos metade dos anos civis com ≥ 10
  operações; e R médio > 0 em A (coerência). Se passar, entra no ringue
  como SHORT_QUEDA (chave nova, o ringue decide); REAL_OK não se mexe.
- Hipóteses testadas até agora (com esta): 5 neste diário; 15 contra os
  mesmos dados contando o diário de investigação (mas a janela B, com o
  filtro de descida, é um período onde os shorts nunca foram afinados).

**Resultados** (ramo `history`, velas de 4H até 2026-10-11; 68 moedas, ROBO
de fora por histórico curto; `backtest/afinacao_h05_short_queda.json`;
código `tools/afinacao_h05_short_queda.py`, teste sem look-ahead do filtro
`tests/test_afinacao_h05.py`).

| Config. | B: op. | B: R médio | B: acaso med./p95 | B: percentil | B: sem a melhor | A (vista): op., R, percentil |
|---|---|---|---|---|---|---|
| X30 + queda | 107 | −0,046 | −0,132 / +0,006 | 70,9 | −0,106 (ADA) | 110, +0,345, 100 |
| X30 + BTC<SMA200 | 603 | −0,296 | −0,234 / −0,180 | 0,6 | −0,305 | 623, −0,094, 85,8 |
| ISOLADA + queda | 77 | −0,118 | −0,137 / +0,019 | 43,3 | −0,157 (XRP) | 93, +0,283, 99,1 |
| ISOLADA + BTC<SMA200 | 431 | −0,300 | −0,240 / −0,178 | 1,1 | −0,311 | 537, −0,138, 29,3 |

- Por ano em B (X30 + queda): 2022 90 op. +0,093R; 2023 3 op. −0,84R;
  2024 14 op. −0,77R. A única descida longa do período (2022) dá um
  ganho pequeno, abaixo do p95 do acaso; as descidas curtas de 2023-2024
  perdem quase tudo. ISOLADA + queda: 2022 +0,024R (64), 2023-2024 −0,8R.
- "Abaixo da SMA200" é pior do que o acaso em todos os anos (percentil
  0,6 e 1,1): vender sobrecompra só porque o BTC está abaixo da média longa
  é vender os ressaltos que continuam.
- A janela A (vista) reproduz o ringue longo (110 op., +0,345R contra 113
  e +0,351R): o método é o mesmo e os números batem certo. Mas o ganho da
  descida de 2025-2026 não aparece na descida de 2022 nem nas de 2023-2024.
- Combate de 90 dias (C): 0 operações com o filtro de queda (não houve
  regime de queda nos últimos 90 dias), 54 com BTC<SMA200.
- Juros da margem não descontados: com saída em 3 dias no máximo custariam
  perto de 0,01R a 0,03R por operação; não mudam nenhum veredicto.
- Critérios em B (melhor configuração, X30 + queda): ≥ 40 op. sim (107);
  R médio > 0 NÃO (−0,046); acima do p95 NÃO (percentil 70,9); sem a
  melhor moeda NÃO (−0,106); anos positivos 1 de 3 NÃO; A > 0 sim.

**Veredicto: REJEITADA.** Nenhuma das 4 configurações ganha fora da janela
onde a ideia nasceu; a melhor fica no percentil 70,9 do acaso. A vantagem
dos shorts na descida que o ringue longo mostra é de um só episódio (a
descida de 2025-2026) e não se repete na de 2022. Nada entra no ringue.

Notas para as próximas execuções:

- Regimes sem campeão vivo: **descida** (nenhum lutador opera nela; as
  compras estão bloqueadas pelo filtro do BTC e os shorts morreram). Na
  subida e na lateral ganham os da sobrevenda e o DIP_TREND.
- Lição de método: o ringue longo é UM ano, com UM episódio por regime.
  Uma família que "ganha na descida" lá tem de ser confirmada noutra
  descida (2022 no ramo `history`) antes de entrar no ringue. Vale para
  qualquer proposta tirada do `por_regime`.
- Próxima hipótese proposta (H6), família diferente e para o regime atual
  (subida): TURTLE com outra saída. No ringue longo ganha +0,34R na subida
  (55 op.) e +0,27R na lateral, mas perde para o acaso (p95 +0,85): a
  geometria de 2R/5R com 20 dias é generosa para entradas ao acaso. Testar
  saídas mais curtas (1.º objetivo a 1,5R, tempo máximo 5 ou 10 dias,
  stop 1,5N) em B e confirmar em 2023-2024 (subidas) antes de olhar para
  os últimos 12 meses. Alternativa: shorts com tendência de descida já
  estabelecida E capitulação das compras (funding), se houver funding
  histórico de 2022.
- Hipóteses testadas até agora: 5 neste diário (H1 a H5); 15 contra os
  mesmos dados contando o diário de investigação (14 até 2026-10-15 + esta).

### 2026-10-19 — H6: Tartarugas com saídas curtas (TURTLE_CURTA)

**Escrito antes de correr qualquer teste.**

- Situação: regime atual (scan.json, `mercado`) **lateral** desde
  2026-10-17. Ringue de 90 dias (forma.json de 2026-10-19): todos os vivos
  com veredicto SOBE são da sobrevenda (BOUNCE_*) e o DIP_TREND (gatilho de
  sobrevenda). Ringue longo (longo.json de 2026-10-18): a sobrevenda ganha
  em subida e lateral; **na descida nenhum vivo opera**; fora da sobrevenda
  ninguém bate o acaso em regime nenhum. O TURTLE (rompimento, família
  diferente) tem R positivo em subida (56 op., +0,36R) e lateral (154 op.,
  +0,25R), mas abaixo do p95 do acaso (+0,83 / +0,90): a geometria (stop
  2N, 2R/5R, stop que segue a 1R, 20 dias) é tão generosa que entradas ao
  acaso dão mais. A investigação (2026-10-14) já registou que, com ESSA
  geometria, o momento de entrada fica no percentil 12,8.
- Hipótese (correção de um morto de outra família, proposta na H5): o
  rompimento do máximo de 20 dias em altcoins dá um impulso curto (dias)
  que depois se devolve; uma saída curta (objetivos a 1–1,5R, tempo máximo
  de 5–10 dias) captura o impulso e deixa de depender da tendência longa.
  O gatilho NÃO muda (4H fecha acima do máximo dos 20 dias anteriores com
  o fecho anterior abaixo; BTC acima da SMA200, como no ringue).
- Previsão honesta: é mais provável falhar (o rompimento já perdeu para o
  acaso em 4 lutadores e na QUEBRA_COMPRADORES); testa-se porque é a
  única família não-sobrevenda com R bruto positivo nos dois regimes.
- Grelha (6, stop em múltiplos de N = ATR diário de 20 dias; stop na
  entrada depois do 1.º objetivo em todas):
  T1 stop 2N, 100% a 1,5R, 5 dias; T2 stop 2N, 50/50 a 1R/2R, 5 dias;
  T3 stop 1,5N, 50/50 a 1,5R/3R, stop que segue a 1R, 10 dias;
  T4 stop 1,5N, 50/50 a 1R/2R, 5 dias; T5 stop 1N, 50/50 a 1,5R/3R, stop
  que segue a 1R, 5 dias; T6 stop 2N, 2R/5R, stop que segue a 1R, 10 dias
  (só o tempo encurta).
- Método: `tools/arena_ringue.generic_trades` (vela a vela, só passado,
  uma operação de cada vez por moeda, entrada na abertura seguinte, 0,25%
  + 0,1% por lado) e `judge` contra o acaso (mesma moeda, ±90 velas,
  mesma geometria). Histórico do ramo `history` (4H até 2026-10-18).
- Janelas: **B (decide)** 2021-08-01 a 2024-10-10, antes da janela de 24
  meses que a autópsia do TURTLE e a QUEBRA_COMPRADORES usaram. **A
  (vista, informativa)** 2024-10-11 até ao fim do histórico. **C**:
  últimos 90 dias (o combate do ringue). Cada janela também por regime do
  BTC (`regime_by_day`).
- Critérios (todos, em B): ≥ 40 operações; R médio > 0; acima do percentil
  95 do acaso; R médio > 0 sem a melhor moeda; R médio > 0 em pelo menos
  metade dos anos civis com ≥ 10 operações; R médio > 0 em A. Escolha: a
  de maior R médio em B entre as que passam. Se passar, entra no ringue
  como TURTLE_CURTA (o ringue decide); REAL_OK não se mexe.
- Hipóteses testadas até agora (com esta): 6 neste diário; 17 contra os
  mesmos dados contando o diário de investigação (16 até 2026-10-18).

**Resultados** (ramo `history`, 4H até 2026-10-18 12:00 UTC; 71 moedas,
ROBO de fora por histórico curto; BTC acima da SMA200 como no ringue, por
isso 2022 não tem operações; `backtest/afinacao_h06_turtle_curta.json`;
código `tools/afinacao_h06_turtle_curta.py`, teste do gatilho igual ao do
ringue e sem look-ahead em `tests/test_afinacao_h06.py`).

| Config. | B: op. | B: R médio | B: acaso med./p95 | B: percentil | B: subida / lateral (R) | A (vista): R, percentil | C 90 dias: op., R, percentil |
|---|---|---|---|---|---|---|---|
| T1 2N, 1,5R, 5d | 995 | −0,015 | +0,211 / +0,249 | 0,0 | −0,028 / +0,001 | +0,147, 0,0 | 255, +0,238, 50,8 |
| T2 2N, 1R/2R, 5d | 987 | −0,033 | +0,181 / +0,215 | 0,0 | −0,038 / −0,027 | +0,088, 0,0 | 262, +0,142, 9,9 |
| T3 1,5N, 1,5R/3R, trail, 10d | 943 | −0,102 | +0,303 / +0,360 | 0,0 | −0,114 / −0,088 | +0,058, 0,0 | 264, +0,179, 1,3 |
| T4 1,5N, 1R/2R, 5d | 1075 | −0,095 | +0,154 / +0,195 | 0,0 | −0,122 / −0,061 | +0,021, 0,0 | 283, +0,070, 8,6 |
| T5 1N, 1,5R/3R, trail, 5d | 1245 | −0,214 | +0,109 / +0,159 | 0,0 | −0,213 / −0,215 | −0,033, 0,0 | 309, +0,101, 74,1 |
| T6 2N, 2R/5R, trail, 10d | 819 | +0,002 | +0,395 / +0,453 | 0,0 | −0,023 / +0,032 | +0,174, 0,0 | 220, +0,281, 0,0 |

- Por ano em B: nenhuma configuração tem R médio positivo em mais de 2
  dos 3 anos, e 2024 é negativo em todas (−0,08R a −0,24R).
- O acaso com a MESMA geometria, na mesma moeda e ±15 dias à volta, dá
  +0,11R a +0,40R; o rompimento fica no **percentil 0,0 em todas as
  configurações, em B e em A, em subida e em lateral**. Encurtar as saídas
  baixa o resultado do acaso, mas o do rompimento cai ao mesmo ritmo: o
  problema não é a saída, é o momento de entrada. Comprar o fecho acima do
  máximo de 20 dias é, nestas moedas, comprar quase sempre perto de um topo
  local (confirma a autópsia de 2026-10-14 com outra janela e 6 geometrias).
- Cautela sobre o acaso: as moedas do histórico são as que estão hoje
  listadas (enviesamento de sobrevivência) e o filtro do BTC escolhe
  períodos de subida, por isso o acaso tem deriva positiva. Isso pesa nos
  dois lados por igual e não muda o percentil 0,0.
- Critérios em B (melhor, T6): ≥ 40 op. sim (819); R > 0 sim por pouco
  (+0,002); acima do p95 NÃO (percentil 0,0); sem a melhor moeda NÃO
  (−0,011); anos positivos 2 de 3 sim; A > 0 sim. T1 a T5 falham já no
  R médio.

**Veredicto: REJEITADA.** Nenhuma saída salva o rompimento de 20 dias:
todas as 6 ficam no percentil 0 do acaso. Nada entra no ringue;
REAL_OK não se mexe.

Notas para as próximas execuções:

- Regime atual **lateral**. Regimes sem campeão vivo: **descida** (nenhum
  lutador opera nela). Na subida e na lateral só ganha a sobrevenda (e o
  DIP_TREND, também gatilho de sobrevenda). A família do rompimento está
  esgotada: não voltar a afinar TURTLE, SQUEEZE_BB, BREAKOUT nem
  BRK_ESPACO pela saída.
- Pista que a H6 deixa (não é resultado, é hipótese): se o fecho acima do
  máximo de 20 dias fica tão abaixo do acaso, o **rompimento falhado**
  pode ter vantagem para o lado vendedor. Próxima hipótese proposta (H7,
  família vendas, regime lateral e descida, onde não há campeão): short
  quando uma vela de 4H rompe o máximo de 20 dias e a vela seguinte (ou
  até 2 velas depois) fecha de novo abaixo desse máximo; stop acima do
  máximo do rompimento, objetivos curtos (1R/2R), 3 a 5 dias. Decidir em
  B (2021-08 a 2024-10, incluindo 2022 porque os shorts correm sem filtro
  do BTC) e só depois olhar para os últimos 2 anos. Atenção: a ideia nasce
  de ver a H6, por isso A está vista para ela.
- Hipóteses testadas até agora: 6 neste diário (H1 a H6); 17 contra os
  mesmos dados contando o diário de investigação (16 até 2026-10-18 +
  esta). Com 17 tentativas a probabilidade de pelo menos um falso positivo
  a 5% ronda os 58%.

### 2026-10-21 — H7: short do rompimento falhado (SHORT_FALHADO)

**Escrito antes de correr qualquer teste.**

- Situação: regime atual (scan.json, `mercado`) **lateral** desde
  2026-10-17. Ringue de 90 dias (forma.json de 2026-10-21): os 11 vivos com
  veredicto SOBE são todos da sobrevenda a virar (BOUNCE_* e DIP_TREND).
  Ringue longo (longo.json de 2026-10-20): a sobrevenda ganha na subida e,
  mais fraca, na lateral; **na descida nenhum vivo opera** (só shorts
  mortos e dois shorts dos maiores com poucas operações). Fora da
  sobrevenda nenhum lutador bate o acaso em regime nenhum.
- Hipótese (família **vendas a descoberto / armadilha de compradores**,
  pista deixada pela H6): o fecho de 4H acima do máximo de 20 dias fica no
  percentil 0 do acaso em todas as geometrias (H6), isto é, compra-se quase
  sempre perto de um topo local. Se o rompimento **falha** (o preço volta a
  fechar abaixo do nível pouco depois), os compradores do rompimento ficam
  presos e as suas saídas empurram o preço para baixo: um short curto
  captura essa descida. Não é a sobrevenda espelhada (não usa RSI) e não
  depende do BTC abaixo da SMA200.
- Regra (preços reais; o ringue corre-a nas velas espelhadas como todos os
  shorts): hi20 = máximo dos 20 dias completos anteriores ao rompimento.
  Rompimento na vela b: fecho de b acima de hi20 com o fecho de b−1 abaixo
  ou igual (o gatilho do TURTLE). Falha na vela i (b < i ≤ b+K): é o
  PRIMEIRO fecho de novo abaixo de hi20 depois de b. Entrada na abertura
  seguinte. Stop: máximo das velas b..i + 0,1 ATR(4H, 14). Stop na entrada
  depois do 1.º objetivo. Sem filtro do BTC (como os shorts do ringue).
  Distância do stop entre 0,5% e 15%.
- Grelha (6, escrita antes de testar):
  F1 K=1, 50/50 a 1R/2R, 3 dias; F2 K=2, 50/50 a 1R/2R, 3 dias;
  F3 K=3, 50/50 a 1R/2R, 5 dias; F4 K=2, 100% a 1,5R, 3 dias;
  F5 K=2, 50/50 a 1,5R/3R, 5 dias; F6 K=6 (um dia), 50/50 a 1R/2R, 5 dias.
- Método: `tools/arena_ringue.generic_trades` sobre as velas espelhadas
  (vela a vela, só passado, uma operação de cada vez por moeda, entrada na
  abertura seguinte, 0,25% + 0,1% por lado) e `judge` contra o acaso no
  espelho (mesma moeda, ±90 velas, mesma geometria). Histórico do ramo
  `history` (4H até 2026-10-18).
- Janelas: **B (decide)** 2021-08-01 a 2024-10-10 (inclui a descida de
  2022, porque os shorts correm sem filtro do BTC). **A** 2024-10-11 até
  ao fim (vista em parte: a ideia nasce dos números da H6 nessa janela, por
  isso só informa). **C**: últimos 90 dias (o combate). Cada janela também
  por regime do BTC (`regime_by_day`).
- Critérios (todos, em B): ≥ 40 operações; R médio > 0; acima do percentil
  95 do acaso; R médio > 0 sem a melhor moeda; R médio > 0 em pelo menos
  metade dos anos civis com ≥ 10 operações; e R médio > 0 acima do p95 do
  acaso em pelo menos um dos regimes **lateral** ou **descida** com ≥ 20
  operações (o objetivo é cobrir onde não há campeão). A > 0 como
  confirmação. Escolha: a de maior R médio em B entre as que passam. Se
  passar, entra no ringue como SHORT_FALHADO em SHORT_SIGS (o ringue
  decide); REAL_OK não se mexe.
- Previsão honesta: mais provável falhar. Os shorts morreram todos no
  ringue e a H5 mostrou que a vantagem dos shorts na descida era de um só
  episódio; o percentil 0 da H6 pode ser só a deriva positiva do acaso
  (moedas sobreviventes) e não um sinal para o lado vendedor.
- Hipóteses testadas até agora (com esta): 7 neste diário; 19 contra os
  mesmos dados contando o diário de investigação (18 até 2026-10-20).

**Resultados** (ramo `history`, 4H até 2026-10-18 12:00 UTC; 71 moedas,
ROBO de fora por histórico curto; shorts sem filtro do BTC, por isso 2022
entra; `backtest/afinacao_h07_falhado.json`; código
`tools/afinacao_h07_falhado.py`; teste do gatilho, do plano no espelho e
sem look-ahead em `tests/test_afinacao_h07.py`).

| Config. | B: op. | B: R médio | B: acaso med./p95 | B: percentil | B: subida / lateral / descida (op., R, percentil) | A: R, percentil | C 90 dias: op., R, percentil |
|---|---|---|---|---|---|---|---|
| F1 K=1, 1R/2R, 3d | 750 | −0,223 | −0,333 / −0,286 | 100,0 | −0,23 (98,7) / −0,22 (99,9) / 25, −0,30 (53,7) | −0,151, 100,0 | 119, −0,168, 99,2 |
| F2 K=2, 1R/2R, 3d | 1007 | −0,207 | −0,319 / −0,281 | 100,0 | −0,21 (99,8) / −0,21 (99,9) / 39, −0,09 (89,7) | −0,165, 100,0 | 157, −0,193, 96,1 |
| F3 K=3, 1R/2R, 5d | 1148 | −0,199 | −0,322 / −0,285 | 100,0 | −0,21 (99,6) / −0,20 (100) / 47, −0,05 (90,2) | −0,138, 100,0 | 183, −0,166, 98,5 |
| F4 K=2, 1,5R, 3d | 1000 | −0,141 | −0,260 / −0,212 | 100,0 | −0,12 (100) / −0,17 (99,9) / 39, +0,08 (92,8) | −0,084, 100,0 | 157, −0,118, 97,0 |
| F5 K=2, 1,5R/3R, 5d | 1000 | −0,199 | −0,335 / −0,289 | 100,0 | −0,20 (100) / −0,22 (99,9) / 39, +0,11 (97,2) | −0,081, 100,0 | 157, −0,120, 99,6 |
| F6 K=6, 1R/2R, 5d | 1366 | −0,205 | −0,315 / −0,282 | 100,0 | −0,22 (99,5) / −0,21 (100) / 52, +0,00 (97,6) | −0,132, 100,0 | 218, −0,141, 99,2 |

- Por ano em B: todas as configurações negativas em todos os anos
  (2021 a 2024); 2023 é o pior (−0,27R a −0,35R).
- **O momento de entrada tem informação**: percentil 100 do acaso em B, em
  A e quase sempre no combate de 90 dias, nas 6 configurações, em subida e
  em lateral. É o espelho do que a H6 viu (o rompimento de 20 dias é um mau
  momento para comprar, por isso é um momento menos mau para vender).
- **Mas não dá dinheiro**: o acaso dos shorts com esta geometria perde
  −0,26R a −0,34R por operação (custos de 0,7% ida e volta sobre stops
  curtos, e moedas que hoje estão listadas, ou seja, que subiram). O
  rompimento falhado só reduz a perda para −0,14R a −0,22R. Bater um acaso
  que perde não chega: o critério é R médio > 0.
- Descida: R positivo em F4/F5/F6 (39 a 52 op. em B, 26 a 33 em A), com F5
  acima do p95 nas duas janelas (B +0,111, percentil 97,2; A +0,233,
  percentil 98,5). Amostra pequena, um só grande episódio de descida em B
  (2022) e escolhida depois de ver os números: não conta como prova.
- Critérios em B (melhor, F4): ≥ 40 op. sim (1000); R > 0 NÃO (−0,141);
  acima do p95 sim (percentil 100); sem a melhor moeda NÃO (−0,149); anos
  positivos 0 de 4 NÃO; lateral/descida com R > 0 acima do p95 NÃO em F4
  (descida percentil 92,8; só F5 passa este ponto, e F5 falha o R médio);
  A > 0 NÃO (−0,084).

**Veredicto: REJEITADA.** O rompimento falhado é o melhor momento de venda
que este diário já mediu face ao acaso (percentil 100 em todo o lado), mas
todas as 6 configurações perdem dinheiro em todos os anos. Nada entra no
ringue (morreria logo: o ringue exige R médio > 0); REAL_OK não se mexe.

Notas para as próximas execuções:

- Regime atual **lateral**. Regime sem campeão vivo: **descida**. Na
  subida e na lateral só ganha a sobrevenda (e o DIP_TREND).
- Lição: com 0,25% + 0,1% por lado, shorts de stop curto em altcoins
  partem de −0,3R por operação ao acaso. Qualquer short novo precisa de um
  momento muito melhor do que o acaso OU de uma geometria que custe menos
  (stops mais largos, objetivos maiores), e o rompimento falhado só tem o
  primeiro.
- Pista (não é resultado): **F5 só na descida** (rompimento falhado, K=2,
  1,5R/3R, 5 dias, só com o regime do BTC em descida) deu +0,11R (39 op.,
  p97) em B e +0,23R (26 op., p98,5) em A. Foi escolhido depois de ver os
  números e tem 65 operações em dois episódios: não há dados novos para o
  confirmar fora da amostra (o histórico começa em 2021). Proposta para a
  próxima execução (H8): pré-registar SHORT_FALHADO_QUEDA com a regra
  exata da F5 e um teste novo que não use os mesmos dados — por exemplo
  velas de 1H (ramo `history`, pasta `1h`) com os mesmos níveis diários,
  onde a entrada e o stop mudam; se passar, entra no ringue, onde só vai
  operar quando o regime virar para descida. Alternativa: usar o
  rompimento falhado como **saída antecipada** das compras abertas (fechar
  uma compra quando o preço rompe o máximo de 20 dias e volta a fechar
  abaixo dele), que ataca o lado "proteger o lucro" sem abrir shorts.
- Hipóteses testadas até agora: 7 neste diário (H1 a H7); 19 contra os
  mesmos dados contando o diário de investigação (18 até 2026-10-20 +
  esta). Com 19 tentativas a probabilidade de pelo menos um falso positivo
  a 5% ronda os 62%.

### 2026-10-23 — H8: short dos compradores apinhados (SHORT_FUNDING)

**Escrito antes de correr qualquer teste.**

- Situação: regime atual (scan.json, `mercado`) **lateral** desde
  2026-10-17. Ringue de 90 dias (forma.json de 2026-10-23 08:30 UTC): os 11
  vivos com veredicto SOBE são todos da sobrevenda (BOUNCE_* e DIP_TREND);
  os clones mortos a 22/10 voltaram a competir. Ringue longo (longo.json de
  2026-10-23): **subida** — ganha a sobrevenda e o PULLBACK (13 op.,
  +0,86R, p95 do acaso +0,45R); **lateral** — só a sobrevenda (ISOLADA,
  SQUEEZE, G0, V2, V3, DESALAV); nenhuma família fora dela bate o acaso na
  lateral (RETESTE +0,12R com p95 +0,34R; TURTLE +0,28R com p95 +1,02R);
  **queda** — SHORT_FALSO_ROMP (49 op., +0,53R, só papel) e os shorts de
  sobrecompra mortos (SHORT_X30 +0,49R, SHORT_ISOLADA +0,43R). Regime sem
  campeão fora da sobrevenda: **lateral** (o de hoje).
- Hipótese (família **derivados / vendas a descoberto**, não usa RSI nem
  níveis de 20 dias): quando o funding do perpétuo fica muito positivo, os
  compradores alavancados estão apinhados e pagam para manter a posição;
  num mercado sem tendência não vem o rompimento que os pagaria e, quando o
  preço começa a falhar, as saídas e liquidações empurram-no para baixo.
  Diferente do SHORT_SQUEEZE (que exige sobrecompra RSI > 70) e do estudo
  de investigação H4 (funding negativo, lado comprador).
- Regra (preços reais; o ringue corre-a no espelho como todos os shorts):
  f24 = média das liquidações de funding com instante em (fecho − 24h,
  fecho], cada uma convertida para 8 horas (taxa × 8h / intervalo entre
  liquidações). Condição: f24 ≥ X. Gatilho: fecho da vela de 4H abaixo do
  mínimo da vela anterior. Short na abertura seguinte. Stop: fecho + k ×
  ATR(4H, 14). Distância do stop entre 0,5% e 20%. Sem filtro do BTC.
  Limiar absoluto (não percentil por moeda) para funcionar no ringue, que
  só traz o funding da própria janela.
- Grelha (6, escrita antes de testar): X ∈ {0,02%, 0,04%} por 8h ×
  G1 k=1,5, 100% a 2R, 3 dias; G2 k=3, 100% a 2R, 5 dias;
  G3 k=3, 50/50 a 1R/3R, 5 dias (stops largos para os custos pesarem menos,
  lição da H7).
- Método: `tools/arena_ringue.generic_trades` nas velas espelhadas (só
  passado, uma operação de cada vez por moeda, entrada na abertura
  seguinte, 0,25% + 0,1% por lado) e `judge` + percentil contra o acaso no
  espelho (mesma moeda, ±90 velas, mesma geometria). Histórico do ramo
  `history`: velas de 4H até 2026-10-18; funding (Binance) de 2024-08-01 a
  2026-09-30.
- Janelas: **B (decide)** 2024-10-01 a 2025-09-30 (60 dias de funding
  antes). **A (confirma)** 2025-10-01 a 2026-09-30. **C**: últimos 90 dias
  com funding (2026-07-02 a 2026-09-30, o combate). **L**: últimos 365
  dias com funding, por regime do BTC (`regime_by_day`), como o ringue
  longo.
- Critérios (todos, em B): ≥ 40 operações; R médio > 0; acima do percentil
  95 do acaso; R médio > 0 sem a melhor moeda; R médio > 0 e acima do p95
  do acaso na **lateral** ou na **queda** com ≥ 20 operações; em A, R médio
  > 0. Escolha: a de maior R médio em B entre as que passam. Se passar,
  entra no ringue como SHORT_FUNDING em SHORT_SIGS (o ringue decide);
  REAL_OK não se mexe. Registo também o percentil face ao limiar do filtro
  novo (99,9 com o contador global).
- Previsão honesta: mais provável falhar. A H4 da investigação viu que o
  funding extremo dá um avanço pequeno sobre o acaso, pequeno demais para
  0,7% de custos ida e volta, e os shorts ao acaso partem de −0,3R (H7).
- Hipóteses testadas até agora (com esta): 8 neste diário; 20 contra os
  mesmos dados contando o diário de investigação (19 até 2026-10-22); 57 no
  contador global (37 estudos fora do programa).
