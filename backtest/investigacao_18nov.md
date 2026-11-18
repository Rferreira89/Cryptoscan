# Investigação isolada de 18/11 (ordem de trabalho, prioridade 6)

Ramo `investigacao/afinacao-18nov`. Não muda produção, sinais, critérios, REAL_OK nem a
classificação de autorização real. Só R (sem valores em dinheiro).

## H17: regra-base do RACIO_DISP e as velas necessárias

Código: `tools/investigacao_h17_base.py`. Resultado: `backtest/investigacao_h17_base.json`.

**1. Velas.** Cortei o histórico real de todas as moedas às últimas N velas de 4H e contei
em quantos dos últimos 30 fechos o filtro de dispersão tem percentil:

| Velas por moeda | Fechos com percentil (de 30) |
|---|---|
| 300 / 500 / 569 / 570 | 0 |
| 600 / 1100 | 30 |

O mínimo exato para o fecho mais recente é **571** (30 de retorno + 540 de histórico + 1),
não 570; para os últimos 30 fechos, 600. Confirmado no código: o papel ao vivo
(`engine/paper_ring.py`, via `promo.set_context`) usa as velas do scanner (500, ou 300
numa fonte), por isso **o RACIO_DISP nunca dá sinal ao vivo** (o filtro devolve None em
silêncio). No ringue (`arena_ringue.fetch`, ~1890 velas) funciona. Não mexi no scanner.

**2. Regra-base R4 sem filtro** (rácio moeda/BTC, BTC acima da média de 200 dias, 769
operações desde o início de B; intervalo de 90% por bootstrap de dias, 5000 vezes):

| Janela | Op. | R médio | IC 90% | P(R ≤ 0) |
|---|---|---|---|---|
| Tudo | 769 | +0,057 | −0,065 a +0,183 | 0,22 |
| Sem os últimos 90 d | 681 | +0,029 | −0,093 a +0,156 | 0,35 |
| Últimos 90 d | 88 | +0,269 | −0,214 a +0,692 | 0,20 |
| 2021 / 2023 / 2024 | 43 / 195 / 240 | +0,155 / +0,089 / +0,052 | todos incluem 0 | |
| 2025 | 203 | −0,082 | −0,303 a +0,174 | 0,69 |

Leitura: a regra-base é positiva em 4 de 5 anos, mas nenhum intervalo exclui zero, e
sem os últimos 90 dias fica em +0,03R. O "percentil 100 do acaso" da H17 mede outra coisa
(face a entradas ao acaso com a mesma geometria, que perdem por custos); não prova que a
regra ganha dinheiro. **Sem evidência para promover nem a R4 nem o RACIO_DISP.** Antes de
qualquer papel ao vivo do RACIO_DISP seria preciso dar ao scanner ≥ 600 velas (decisão
do Rui; não feito).

## H18: controlo ao acaso neutro à tendência, com juros

Código: `tools/investigacao_h18_controlo.py`. Resultado: `backtest/investigacao_h18_controlo.json`.
Operações reais do ringue (`AR.generic_trades`, último ano; shorts em velas espelhadas e
com juros descontados). Para cada operação, 30 entradas ao acaso com a mesma geometria:
C0 = como a arena (±90 velas de 4H à volta da entrada); C1 = C0 com juros nos shorts;
C2 = só as 90 velas antes da entrada; C3 = qualquer vela do histórico da moeda (neutro ao
momento), com juros nos shorts.

| Estratégia, janela | Op. | Real | C0 arena | C1 +juros | C2 só antes | C3 neutro |
|---|---|---|---|---|---|---|
| TURTLE, 365 d (*) | 212 | +0,23 | +0,57 | +0,54 | +1,18 | **−0,11** |
| SHORT_TURTLE, 365 d | 694 | +0,22 | +0,62 | +0,56 | +0,96 | **+0,19** |
| SHORT_TURTLE, 90 d | 108 | +0,01 | +0,53 | +0,51 | +0,54 | **+0,20** |

(*) as 212 operações do TURTLE caem todas nos últimos 90 dias (o filtro do BTC acima da
média de 200 dias só as deixa aí); a linha de 90 d é igual.

Leitura:

1. **O controlo da arena está enviesado para cima nas estratégias de tendência.** A janela
   de ±90 velas é escolhida porque houve uma rutura nesse sítio: as velas antes da entrada
   estão abaixo do preço da rutura e a tendência que a produziu continua. O C2 (só velas
   anteriores) mostra-o com mais força (+1,18R). Não é uma questão de "olhar para o
   futuro" nas velas; é o próprio sítio da janela que já sabe que houve rutura.
2. **Os juros explicam pouco**: C0 → C1 baixa ≈ 0,05R nos shorts. O grosso da diferença é
   a tendência da janela.
3. **Contra o controlo neutro (C3)**: o TURTLE fica +0,33R acima (+0,23 contra −0,11); o
   SHORT_TURTLE fica igual ao acaso no ano (+0,22 contra +0,19) e abaixo nos últimos 90 dias
   (+0,01 contra +0,20). Ou seja, a geometria do short ganhou pela descida do mercado, não
   pela entrada.
4. Limites: o C3 é neutro ao momento, mas mistura regimes diferentes da mesma moeda; 30
   repetições por operação; uma só semente. Serve para diagnosticar o enviesamento, não
   para promover ou despromover estratégias.
5. **Proposta (não feita):** a arena passar a mostrar o C3 ao lado do C0, e o veredicto das
   estratégias de tendência ser revisto com o C3. Muda critérios, por isso fica para o Rui.

## H40

Confirmado: nenhum nome da H40 / pânico está em `engine/promo.REAL_OK`, e no executor
antigo `panico_real` está `false` em `okx_config.json`. Fica fora. Nada mudado.

## Proposta de travão automático (NÃO implementado)

Código: `tools/investigacao_travao.py`. Resultado: `backtest/investigacao_travao.json`.

Método: 500 R reais (as 10 últimas operações de 50 lutadores do ringue longo), com desvio
0,91R, centrados e deslocados para cada vantagem verdadeira μ. 4000 sequências de 150
operações por μ e por regra. Dois modos: operações independentes e "fases" (a vantagem
alterna ±0,15R em fases de 25 operações, com a mesma média; imita boas e más fases de
mercado). "Falso bloqueio" = bloquear uma estratégia com μ > 0.

Probabilidade de bloqueio em 150 operações (modo fases; o independente é quase igual):

| Regra | μ −0,20 | −0,10 | −0,05 | 0 | +0,05 | +0,10 | +0,20 |
|---|---|---|---|---|---|---|---|
| K1 média < 0 com n ≥ 20 (**regra atual do `paper_ring`**) | 1,00 | 0,99 | 0,96 | 0,88 | **0,76** | **0,62** | **0,32** |
| K2 média < 0 com n ≥ 40 | 1,00 | 0,98 | 0,93 | 0,83 | 0,66 | 0,48 | 0,15 |
| K3 t < −1,645, n ≥ 20 | 0,93 | 0,68 | 0,50 | 0,34 | 0,21 | 0,13 | 0,05 |
| **K4 t < −2,33, n ≥ 20** | 0,80 | 0,45 | 0,28 | 0,16 | 0,09 | 0,06 | 0,02 |
| K5 média < −0,10 só em n = 30, 60, 100 | 0,93 | 0,72 | 0,56 | 0,39 | 0,25 | 0,15 | 0,04 |
| K6 queda ≥ 10R desde o pico | 1,00 | 0,96 | 0,88 | 0,72 | 0,51 | 0,29 | 0,05 |
| K7 Bayes P(μ<0) > 0,95, n ≥ 20 | 0,88 | 0,57 | 0,39 | 0,24 | 0,13 | 0,07 | 0,03 |
| K8 Bayes P(μ<0) > 0,90, n ≥ 30 | 0,94 | 0,69 | 0,51 | 0,32 | 0,18 | 0,09 | 0,02 |

R evitado (μ < 0) e R perdido (μ > 0) por sequência de 150 operações, modo fases:

| Regra | evitado μ −0,20 | evitado −0,10 | perdido +0,05 | perdido +0,10 | perdido +0,20 |
|---|---|---|---|---|---|
| K1 | 25,5 | 12,2 | 4,6 | 7,4 | 8,0 |
| K4 | 15,2 | 4,2 | 0,5 | 0,7 | 0,5 |
| K7 | 16,7 | 5,1 | 0,7 | 0,9 | 0,6 |
| K8 | 18,5 | 6,2 | 0,9 | 1,0 | 0,4 |

Conclusões:

1. **A regra que já existe no papel (`paper_ring`, KILL_N = 20, média < 0) é demasiado
   agressiva**: com o desvio real das operações (≈ 0,9R), mata 76% das estratégias com
   +0,05R e 62% das com +0,10R em 150 operações. Com 20 operações o erro padrão da média é
   ≈ 0,2R; uma média negativa a 20 operações diz quase nada. É só papel; não mudei nada.
2. **Proposta para o real (para decisão do Rui):** K4 (t < −2,33 com n ≥ 20, verificado a
   cada fecho) ou K8 (Bayes P(μ<0) > 0,90 com n ≥ 30). Falsos bloqueios de 6–9% para
   +0,10R, apanhando 80–94% das estratégias com −0,20R. O travão não fecha posições: só
   suspende entradas novas (como `estrategias_suspensas`), com reabertura manual.
3. Nenhuma regra apanha bem estratégias ligeiramente negativas (−0,05R) sem matar as
   ligeiramente positivas: com ≤ 150 operações essas são estatisticamente indistinguíveis.
   Para essas, o travão deve ser complementado pelos limites de perda em dinheiro do piloto
   (que já existem).
4. Limitações: operações tratadas como intercambiáveis entre estratégias (mesma forma da
   distribuição para todas); o modo "fases" é uma aproximação da dependência entre
   operações; o horizonte de 150 operações é arbitrário (um ano a poucas operações por
   semana).
