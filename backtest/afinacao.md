# Diário de afinação dos sinais

Hipóteses testadas sobre as estratégias que já estão ao vivo, uma por
entrada, com o veredicto. Hipóteses testadas até agora: 3.

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
