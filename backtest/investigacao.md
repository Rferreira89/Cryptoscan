# Diário de investigação

**Hipóteses testadas contra esta reserva: 27** (12 neste diário: compra de
quedas, compressão, oversold bounce 4H, day trade 1H, bounce com outras
saídas, sweep a mercado, funding negativo, quebra com compradores,
capitulação do mercado, atraso face ao BTC, resiliente, impulso de
amplitude; mais 15 no diário de afinação, H1 a H13, H15 e H16). Atualizado
em 2026-11-14 (sem hipótese nova nesta corrida nem nas anteriores desde
2026-10-20; a afinação testou a H13 em 2026-11-04, a H14 em 2026-11-06,
uma medição de lutadores existentes que não conta como hipótese nova, a
H15 em 2026-11-11 e a H16 em 2026-11-13, ambas rejeitadas). O contador global do
programa (`engine/hipoteses.py` mais `backtest/hipoteses_offline.json`,
contra dados que incluem esta reserva) já vai em 87 (ringue longo,
2026-11-04), mais os estudos H38–H41 de 03–04/11 em `backtest/estudos/`.
Quanto maior este número, maior a probabilidade de uma hipótese passar por
sorte: com 27 testes, a probabilidade de pelo menos um falso positivo a 5%
já ronda os 75% (e as várias configurações de cada grelha aumentam-na
ainda mais).

Uma hipótese por entrada, com o veredicto. Método: `tools/research.py`
(decisão no fecho, execução na abertura seguinte, 0,25% de comissão + 0,1% de
slippage por lado desde 2026-10-07 (antes 0,1%), walk-forward, seis critérios declarados a priori, reserva
avaliada uma única vez). Janela desde 2026-10-03 (decisão do Rui): últimos 24
meses, 18 de desenho e 6 de reserva; menos de 40 operações fora da amostra
dá "AMOSTRA INSUFICIENTE".

## AUTORIZAÇÃO PRÉVIA DO RUI PARA DINHEIRO REAL — 2026-11-01

O Rui autorizou ("Sim dou", 01/11/2026) que uma estratégia nova passe a dinheiro real SEM novo pedido quando
cumprir as DUAS condições: (1) passa o CRITÉRIO DA CONTA nas duas metades do histórico; (2) tem pelo menos 30
operações em papel ao vivo com média positiva. Os agentes continuam a NÃO poder ligar dinheiro real: quando uma
estratégia cumprir as duas condições, o agente avisa (notificação) e a ligação ao dinheiro é feita numa sessão
com o Claude, dividindo o capital com a tendência BTC (núcleo a 2x). Caminho para o papel ao vivo: ENTRADA NO
RINGUE (função de sinal em SINAIS de tools/arena_ringue.py, com teste).

## CRITÉRIO DA CONTA — obrigatório desde 2026-11-01 (decisão do Rui)

O H32 mostrou que a compra no pânico (+0,08R por sinal, aprovada pelo critério único) PERDE dinheiro
quando operada como o Rui opera: uma conta, uma posição, o valor todo (metade recente −0,22R, a conta
perde 93% a 1x e vai a zero a 3x). A vantagem só existia tomando todos os sinais ao mesmo tempo.
A partir de agora, nenhuma hipótese recebe "PARA PAPEL" nem "CANDIDATA" sem passar também:
1. Simulação AO NÍVEL DA CONTA: uma conta com capital pequeno, no máximo 1 posição (o valor todo) e
   também com 2 posições; quando há vários sinais ao mesmo tempo, escolher ao acaso (várias repetições),
   juros compostos, custos reais. Ver `backtest/estudos/h32_uma_conta.py` e `h33_conta_tendencia.py`.
2. Nas duas metades: conta a crescer a 1x e retorno/queda máxima melhor do que BTC comprado sempre
   (no H33, 2024-03 a 2026-10, BTC comprado sempre deu +43%/ano com 28% de queda máxima e nenhuma
   regra testada lhe ganhou).
3. Reportar também a 3x só como informação: com o valor todo, stop de X% custa 3·X% da conta.
Uma estratégia que só ganha "em média por sinal" não serve a uma conta de 20$.

## DECISÕES EXECUTIVAS — 2026-11-14 (auditoria independente)

Sessão com o Rui. Decisões binárias a partir da auditoria do relatório do agente de investigação (24.ª corrida sem hipótese nova).

### Decisões sobre as cinco propostas

1. **Frequência das corridas → SEMANAL** enquanto a fila de hipóteses estiver vazia e não existirem dados novos materiais. Corridas diárias sem informação nova só geram ruído e custo. APROVADO.

2. **Regresso de mortos** só se **ambas as metades** do ringue longo forem positivas. APROVADO (filtro anti-overfitting).

3. **Morte rápida a contar acontecimentos** em vez de operações. ALTERADO: manter operações até existir definição operacional clara de "acontecimento independente". Não mudar a regra sem essa definição.

4. **Corte de clones só com representantes vivos**. CONFIRMADO. O código em `tools/arena_ringue.py` (`def clones`) já exclui `mortos` e quem tem `veredicto == "MORTA"`. O commit de 2026-11-13 23:33 resolveu o defeito. Nenhuma alteração de código necessária.

5. **CAPITULACAO_R2** — decisão obrigatória na próxima corrida. Não pode ficar "fora da classificação". Avaliar separadamente:
   - a função `sig_capitulacao` (46 op., +0,08R no combate);
   - o lutador CAPITULACAO_R2 (3 op., −0,66R).
   Decisão binária: manter / matar / reescrever. Se a função tiver edge e o lutador a destruir, matar o lutador e registar a função como sinal candidato a nova implementação.

### Ordem operacional para a próxima corrida do agente de investigação

1. Executar primeiro o workflow **Historico para backtest** e reportar o novo atraso.
2. Confirmar que o corte de clones continua a comparar apenas com vivos (já está no código).
3. Autópsia de qualquer lutador que atinja critérios de morte (incluindo candidatos a morte rápida: BREAKOUT_R2, SHORT_SQUEEZE, MAIORES_TENDENCIA, BOUNCE_MEDO).
4. Decidir formalmente CAPITULACAO_R2 (função vs lutador) com decisão binária.
5. Se a fila de hipóteses permanecer vazia, registar "sem novas hipóteses" e **não gerar artificialmente**.
6. Frequência: semanal até nova ordem ou até existência de dados novos materiais.
7. Reportar apenas factos, resultados de testes e decisões binárias. Sem narrativas de esgotamento.

### O que não fazer

- Não inventar hipóteses novas enquanto a fila estiver vazia.
- Não recrutar.
- Não reativar BOUNCE_AMPLITUDE só pelo 15/15 (amostra pequena, inatividade recente, chumbo no critério da conta).
- Não deixar lutadores "fora da classificação" sem decisão.

### Notas de auditoria (para memória)

- 27 testes contra a reserva → risco de pelo menos um falso positivo ~75%. Disciplina de múltiplos testes continua a ser o ponto fraco.
- Separação rígida LONG/SHORT reduz o universo de descoberta; a reavaliar mais tarde.
- 24 corridas sem hipótese nova não prova esgotamento real do espaço de ideias; pode ser estreiteza do mecanismo de geração.
