# Diário de afinação dos sinais

Hipóteses testadas sobre as estratégias que já estão ao vivo, uma por
entrada, com o veredicto. Hipóteses testadas até agora: 1.

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
