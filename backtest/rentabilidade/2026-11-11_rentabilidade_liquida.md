# Rentabilidade líquida e proteção de capital — auditoria de 2026-11-11

Ramo `investigacao/filtro-rentabilidade`, criado a partir de `investigacao/auditoria-agente` (que parte do main em
428c5a0). Nada foi fundido no main. Nada em `engine/`, `.github/`, `config.json`, `okx_config.json`, nas ordens, nas
posições ou nas tarefas agendadas foi tocado (§10).

## Conclusão em primeiro lugar

**Nenhuma estratégia de entrada cumpre o critério de expectativa líquida positiva demonstrável.**

- Dos 20 lutadores representativos simulados de 2021-08 a 2026-11 (22 432 operações, 10 217 acontecimentos), **15 são
  negativos** (intervalo de 90% por acontecimento todo abaixo de zero), **5 são inconclusivos** (à volta de zero) e
  **nenhum é positivo**.
- As estratégias com registo ao vivo (Bybit real, H40/H45 em papel e em real, pânico com ordem limite, short da lateral)
  são negativas ao vivo.
- A única regra positiva em termos absolutos nos três períodos é o **núcleo BTC** (tendência, sem ser uma entrada de
  4H). Mas a 2x não bate o BTC comprado e guardado em 2024–26.

O filtro pré-entrada, pre-registado antes de qualquer resultado, rejeita **99,9%** das operações históricas. As 30 que
aceita perdem todas. Como mecanismo de eliminação funciona; como fonte de vantagem foi **REJEITADO**, porque não há
vantagem para encontrar.

---

## 1. Estratégias: expectativa líquida

Valores em R líquido (comissão de 0,25% + deslize de 0,1% por lado, mais o spread real acima do deslize e, nos shorts,
o juro do empréstimo). IC90 por **acontecimento** (operações da mesma vela de 4H contam uma vez).

### 1a. Com dinheiro real ou papel ao vivo

| Estratégia | Onde | Evidência | Veredicto |
|---|---|---|---|
| Núcleo BTC (SMA50, 2x) | Bybit, **real** | Simulação diária com o histórico: 2021-08→2024-02 ×1,77 (+25%/ano, queda −86%); 2024-03→2026-05 ×1,23 (+10%/ano, −53%); reserva ×1,12 (−29%). A 1x: ×1,71 / ×1,32 / ×1,09, com quedas de −60% / −28% / −15%. BTC comprado e guardado: ×1,47 / ×1,31 / ×0,95. Juro de 10%/ano na parte alavancada, **não verificado** | **Positiva em absoluto**. A 2x não ganha ao BTC guardado em 2024–26 e duplica a queda; a 1x ganha sobretudo em queda máxima |
| 4H antigas (PULLBACK, BREAKOUT, LIQUIDITY_SWEEP, TREND_DAILY) | Bybit (desligadas) | Backtest −0,16R a −0,22R, IC95 todo < 0, mesmo com custos baixos (0,1% + 0,05%). **21 operações reais registadas: −0,48R por operação, −10,1R no total** (14 executadas: −0,43R) | **NEGATIVA** |
| H45 pânico do mercado | Bybit (suspensa do real a 10/11) | Backtest +0,12R/+0,34R; residual face ao BTC α = +0,12 (p = 0,21). Papel ao vivo: 21 op., −0,435R, IC90 [−0,79; −0,11] | **NEGATIVA ao vivo** |
| H40 pânico do mercado | OKX (real desligado: `panico_real` false) | Backtest +0,31R, α p = 0,06. Papel: 23 op., −0,50R, IC95 [−0,89; −0,12]. Real: 4 op., −1,04R líquido | **NEGATIVA ao vivo** |
| H46 recuo em tendência | OKX, **real a 1%** (`recuo_real` true) | Backtest +0,05R e +0,15R por metade; DSR 0,32–0,38 (não sobrevive ao desconto pelas tentativas); α não significativo, β ao BTC ≈ 20. 0 operações ao vivo | **INCONCLUSIVA**. O filtro rejeitá-la-ia (§4) |
| TF-SHORT U2 | OKX, papel | 23 sinais abertos desde 06/11, 0 fechados; backtest pre-registado +0,166R | **INCONCLUSIVA** (sem operações fechadas) |
| Pânico com ordem limite (H23) | papel | 21 op., −0,435R, 29% de acerto | **NEGATIVA** |
| Short do mínimo de 55 velas na lateral (H29) | papel | 20 op., −1,11R, 0% de acerto | **NEGATIVA** |
| Kronos K1 | sombra desligada | −0,052R por sinal fora da amostra | **NEGATIVA** |

### 1b. Lutadores da arena (simulação completa 2021-08-01 → 2026-11-08, 70 moedas)

Os outros 30 lutadores são variantes do Oversold Bounce, com correlação 0,9 ou mais com o BOUNCE_X30.

| Lutador | Op. | Acont. | R líq./op. | R/acont. | IC90 por acontecimento | Queda máx. (R) | Veredicto |
|---|---|---|---|---|---|---|---|
| MAIORES_TENDENCIA | 77 | 73 | +0,020 | +0,039 | [−0,22; +0,30] | −12 | INCONCLUSIVA |
| TURTLE_FORTES | 512 | 371 | +0,021 | +0,026 | [−0,08; +0,13] | −56 | INCONCLUSIVA |
| SHORT_TURTLE (preço real) | 2217 | 937 | −0,019 | +0,012 | [−0,04; +0,06] | −194 | INCONCLUSIVA |
| TURTLE | 1423 | 902 | +0,099 | +0,006 | [−0,06; +0,07] | −112 | INCONCLUSIVA |
| VOLUME_ACUMULACAO | 246 | 215 | −0,103 | −0,115 | [−0,25; +0,02] | −29 | INCONCLUSIVA |
| FIBO_RECUO | 1484 | 865 | −0,132 | −0,107 | [−0,17; −0,05] | −239 | NEGATIVA |
| MOMENTUM | 521 | 144 | −0,135 | −0,112 | [−0,22; −0,00] | −78 | NEGATIVA |
| RETESTE | 2300 | 1237 | −0,124 | −0,163 | [−0,21; −0,12] | −308 | NEGATIVA |
| BOUNCE_HORAS | 1047 | 260 | −0,152 | −0,172 | [−0,25; −0,09] | −175 | NEGATIVA |
| CAPITULACAO | 326 | 102 | −0,133 | −0,174 | [−0,32; −0,03] | −56 | NEGATIVA |
| MAIORES_RECUO | 183 | 146 | −0,181 | −0,185 | [−0,31; −0,06] | −41 | NEGATIVA |
| REVERSAO_INTERVALO | 271 | 145 | −0,232 | −0,188 | [−0,28; −0,10] | −63 | NEGATIVA |
| SHORT_X30 (preço real) | 3687 | 1676 | −0,256 | −0,204 | [−0,23; −0,17] | −958 | NEGATIVA |
| BOUNCE_ISOLADA | 1612 | 377 | −0,041 | −0,206 | [−0,28; −0,14] | −215 | NEGATIVA |
| BOUNCE_X30 | 2078 | 510 | −0,098 | −0,216 | [−0,27; −0,16] | −269 | NEGATIVA |
| BOUNCE_FLUXO | 524 | 244 | −0,154 | −0,227 | [−0,31; −0,15] | −92 | NEGATIVA |
| SQUEEZE_BB | 1318 | 670 | −0,193 | −0,248 | [−0,31; −0,19] | −272 | NEGATIVA |
| DIP_TREND | 604 | 272 | −0,205 | −0,266 | [−0,34; −0,19] | −129 | NEGATIVA |
| BOUNCE_AMPLITUDE | 434 | 94 | −0,216 | −0,359 | [−0,48; −0,24] | −121 | NEGATIVA |
| BRK_ESPACO | 1568 | 977 | −0,373 | −0,368 | [−0,42; −0,32] | −584 | NEGATIVA |

Os shorts são simulados em **preço real**, com o sinal no espelho. No espelho, como faz o ringue, o SHORT_TURTLE dava
+0,236R por operação; em preço real dá +0,025R antes do juro e do spread, e −0,019R depois. É o enviesamento do espelho
que a afinação H14 já tinha medido. Quando corri o filtro sobre os shorts do espelho, ele "encontrou" uma vantagem no
SHORT_TURTLE que não existe; corrigi isso antes de tirar conclusões.

## 2–3. Custos reais e se os 0,7% de ida e volta estão certos

**Comissões oficiais.** Bybit UE spot, VIP0, pares cripto: **0,10% maker / 0,25% taker** (página "Benefits of the VIP
Program", atualizada a 2026-07-02). OKX: perpétuos 0,02% / 0,05%; spot EEA 0,08% / 0,10% com conta de derivados e
0,20% / 0,35% sem ela. As da OKX vêm de **fontes secundárias**: não consegui ler a página oficial.

**Spread real da Bybit UE** (`liquidez.json`: 22 dias, 82 moedas, amostras do scanner): mediana 0,14%, p25 0,06%,
p75 0,21%, p90 0,27%. BTC e ETH 0,01%, SOL 0,02%, ENA 0,05%, TRUMP 0,18%, PUMP 0,31%, HUMA 0,36%, BONK 0,45%.

**Deslize medido nas entradas reais da Bybit** (12 execuções com preço): +0,05% em média (mediana +0,03%; pior +0,55%).
**Deslize nos stops reais da OKX** (4 operações): −0,04R em média; pior −0,22R (salto de preço no PARTI).

| Ida e volta (Bybit UE spot) | BTC/ETH | Moeda mediana | p75 | p90 |
|---|---|---|---|---|
| taker + taker + spread | 0,51% | 0,64% | 0,71% | 0,77% |
| + 0,1% de deslize por lado | 0,71% | 0,84% | 0,91% | 0,97% |
| maker na entrada, taker na saída | 0,36% | 0,42% | 0,45% | 0,49% |

**Veredicto sobre os 0,7%.**

- Está **certo para a moeda mediana** (0,64% + deslize medido de cerca de 0,1% ≈ 0,74%).
- É **exagerado para BTC e ETH** (≈ 0,55%).
- É **curto para o quartil caro** (0,85–1%), que é onde caem muitas das altcoins pequenas que os lutadores escolhem.
- Uma entrada maker poupa ~0,2%, mas as entradas com ordem limite perderam mais em papel (H23: −0,435R), por
  seleção adversa. Não é poupança grátis.
- O juro do short em margem spot (assumido 0,05%/dia ≈ 18%/ano) e o juro do núcleo alavancado **não estão verificados**:
  não encontrei a taxa publicada da Bybit UE.
- **Preenchimentos parciais e ordens não executadas**: 7 das 21 operações reais da Bybit não foram executadas, e há
  ordens com "a ordem não mostrou execução". O registo de execuções (`execucoes/exec.json`) está cifrado e não o li.

**O que importa é o custo em R, não em %.** Custo em R = ida e volta / distância do stop.

- Nas 21 operações reais da Bybit o stop mediano foi de 5,9% e o custo mediano de **0,10R**.
- Duas operações com stop de cerca de 1% (ENA BREAKOUT, BNB PULLBACK) custaram **0,54R e 0,70R** só em custos.
- Uma estratégia com stops curtos precisa de uma vantagem bruta enorme. Nenhuma a tem.

## 4–5. Filtro de rentabilidade líquida pré-entrada (`tools/filtro_rentabilidade.py`)

Foi pre-registado no registo central (`FILTRO_RENTABILIDADE_F1`) **antes de correr**, com os parâmetros fixos:

1. **Vantagem estimada**: R médio **por acontecimento** das operações da mesma estratégia **já fechadas** antes da
   entrada. Há teste de que o futuro não entra.
2. **Encolhida para zero**: priori de 10 acontecimentos com média 0 e desvio-padrão de 1R, para que poucos resultados
   iguais não pareçam certeza.
3. **Incerteza**: limite inferior de 95% (z = 1,645).
4. **Custo desta operação**: (spread real da moeda − 0,2% de deslize já simulado) / stop%, mais o juro nos shorts.
5. **Aceita só se** o limite inferior menos o custo extra for maior do que 0,05R e houver pelo menos 20 acontecimentos.
   Caso contrário rejeita. Inconclusivo não conta como vantagem.

O filtro só pode retirar operações; nunca acrescenta nem relaxa nada.

## 9. Comparação histórica (20 lutadores, 2021-08 → 2026-11-08)

| | Operações | Acont. | R líq./op. | R total | Queda máx. (R) |
|---|---|---|---|---|---|
| Sem filtro | 22 432 | 10 217 | −0,139 | −3 114 | −3 132 |
| **F1 aceites** | **30** | 15 | **−0,996** | −30 | −30 |
| F1 rejeitadas | 22 402 | 10 202 | −0,138 | −3 085 | −3 102 |
| F1p (estimativa pontual, sem incerteza) aceites | 1 388 | 893 | −0,215 | −299 | −306 |

| | Sem filtro | F1 aceites | F1 R evitado |
|---|---|---|---|
| Exploração (até 2026-05-08) | 19 615 op., −0,147R | 30 op., −0,996R | +2 844R |
| Reserva (2026-05-08 → 11-08) | 2 817 op., −0,085R | 0 op. | +240R |

**Oportunidades perdidas.** As rejeitadas incluem 10 006 operações ganhadoras (+8 154R), mas vêm com perdedoras que
somam mais: no total as rejeitadas valem −3 085R. Não há um subconjunto ganhador identificável de antemão.

**Leitura.**

1. Como regra de eliminação, o F1 tira praticamente tudo e evita 3 085R de perdas simuladas.
2. As 30 operações aceites perderam todas. São 24 SHORT_TURTLE entre maio e julho de 2022, logo a seguir à queda, e
   6 TURTLE em março de 2024, no topo. **A vantagem estimada no fim de uma tendência é enganadora na viragem.** É um
   aviso contra qualquer filtro baseado só no desempenho recente.
3. Sem incerteza (F1p), o filtro é **pior do que não filtrar** (−0,215R contra −0,139R): persegue o ruído.
4. Informação posterior, que não conta como teste: com a correção de Bonferroni pelos 20 lutadores (z = 2,81), o filtro
   não aceita nenhuma operação.
5. **Operações reais da Bybit**: o F1 teria rejeitado as 21, que perderam −10,1R.

Veredicto registado: **REJEITADA** como fonte de vantagem; o teto era EXPLORATÓRIA, porque o histórico já tinha sido
visto. O mecanismo vale como travão, não como gerador de operações.

## 6. Bloqueios na Bybit e oportunidades perdidas na OKX

**Bybit — porque não há entradas reais de 4H desde 23/10.** Os bloqueios vêm em cadeia (`engine/promo.py`):

1. Desde 28/10, o real exige estar em `real_autorizados`, e a lista está **vazia**. Sozinho, este bloqueio já chega para
   impedir qualquer campeão.
2. Mesmo sem ele, o campeão da fase lateral tem de ter pelo menos 20 operações, R de pelo menos 0,15, estar acima do p95
   do acaso e ganhar nas duas metades do ano. Só a REVERSAO_INTERVALO se qualifica no combate, com +0,026R; na
   simulação completa dá −0,19R por acontecimento.
3. A família da sobrevenda está só em papel.
4. O SHORT_TURTLE está em papel por deriva (−0,16R nas últimas 63 operações da lateral). Em preço real é inconclusivo.
5. 30 lutadores estão suspensos por "não pagar as contas do mês".
6. A H45 está suspensa do real (papel −0,435R).

Antes de 27/10, das 100 oportunidades perdidas registadas: liquidez 38 (volume baixo 15, spread alto 13, preço
desatualizado 8), plano 33 (moeda sem margem para short 20, abaixo da ordem mínima 13), diversificação 26.

**Avaliação:** todos os bloqueios estão de acordo com a evidência. **Nenhum bloqueia uma estratégia com vantagem
líquida demonstrável, por isso não há nada a desbloquear.** O núcleo BTC continua a funcionar.

**OKX — oportunidades que não chegaram ao real** (`tools/rejeicoes.py`, ficheiro `rejeicoes_2026-11-11.txt`):

| Motivo | N | Resultado em papel | Avaliação |
|---|---|---|---|
| H40 suspensa do real | 22 | 12 com resultado: −0,89R, IC90 [−1,01; −0,77] | bloqueio justificado |
| H45 suspensa do real | 21 | −0,435R, IC90 [−0,79; −0,11] | bloqueio justificado |
| TF-SHORT fora do universo validado | 15 | desconhecido | sem par em papel |
| TF-SHORT abaixo do mínimo do contrato (20 $) | 8 | desconhecido | operacional |
| H40 sem X-Perp negociável | 10 | 3 com resultado: +1,2R | inconclusivo (3 resultados) |
| H40 pânico isolado | 4 | +0,33R | inconclusivo; o isolado em papel no total dá −0,55R (20 op.) |

Na conta simulada de 20 $ o TF-SHORT ignorou 95 sinais (fora do universo ou abaixo do mínimo). Não há resultado
fechado que mostre se foram perdas evitadas ou oportunidades perdidas. **Não há nenhuma oportunidade perdida na OKX com
vantagem demonstrada.**

## 7. O que não foi feito, de propósito

Não relaxei nenhum filtro, não aumentei a frequência e não criei nenhuma estratégia nova. O filtro só retira.

## 10. Proposta de integração (precisa da tua autorização; nada disto está ligado)

| Passo | O que muda | Impacto esperado |
|---|---|---|
| **I1 — sombra** | O scanner e o agente da OKX calculam a decisão F1 de cada sinal e só a registam (`filtro_sombra` no estado), sem efeito nas ordens | Zero na execução. Mede a decisão de forma prospetiva, em dados que nenhum teste viu (a validação que o registo exige) |
| **I2 — portão** | Depois de 30 acontecimentos na sombra: o F1 com Bonferroni pelo número de estratégias vivas passa a ser uma condição a mais em `promo.champions` e no agente da OKX (só retira) | Na Bybit: nada muda hoje (já está a zero). Na OKX: a **H46 recuo real** deixa de entrar (estimativa: LB ≈ +0,04R antes do agrupamento, abaixo da margem). Volume real ≈ 0 até haver vantagem |
| **I3 — histórico misto** | A estimativa usa o papel e o real ao vivo com prioridade sobre o backtest e marca "backtest não confirmado" quando o ao vivo fica 2 erros-padrão abaixo (H40/H45: +0,25R no backtest contra −0,44R no papel) | Fecha o caminho "passa no backtest → real" que já custou −4R na OKX |
| **I4 — proteção na viragem** | O estimador ignora as operações de uma fase de mercado diferente da atual, ou exige as duas metades positivas | Ataca o modo de falha visto (aceitar no fim da tendência). Sem prova ainda: entraria só pela sombra |
| **I5 — núcleo** | Rever a alavancagem do núcleo (2x): em 2024–26, 2x deu ×1,23 com queda de −53%, contra ×1,32 e −28% a 1x. E confirmar o juro real da Bybit UE | Menos queda com retorno igual ou maior em 2024–26. Decisão tua |

**Limitações.**

- Spreads de apenas 22 dias recentes, aplicados a todo o histórico.
- Universo só com as moedas listadas hoje (viés de sobrevivência, favorável às compras).
- H40, H45 e H46 não foram re-simuladas operação a operação (os estudos precisam do ramo das delistadas); usei os
  resultados registados e o papel.
- O registo de execuções está cifrado: não medi os preenchimentos parciais.
- Comissões da OKX de fontes secundárias; juro de margem da Bybit UE não verificado.
- O núcleo foi simulado com velas diárias derivadas das de 4H.

## 11. Ficheiros

- `tools/filtro_rentabilidade.py`: o filtro, as métricas e a comparação.
- `tools/filtro_operacoes.py`: as operações com hora de fecho e stop; shorts em preço real.
- `tools/custos_reais.py`: a reconciliação de custos.
- Testes:
  - `tests/test_filtro_rentabilidade.py`: sem look-ahead, encolhimento, custos, só retira;
  - `tests/test_filtro_operacoes.py`;
  - `tests/test_custos_reais.py`.
- Resultados em `backtest/rentabilidade/`: `filtro_2026-11-11.json`, `custos_2026-11-11.json`,
  `rejeicoes_2026-11-11.txt` e `operacoes_lutadores_2026-11-11.json.gz` (reprodutível: o filtro dá exatamente o mesmo
  resultado a partir deste ficheiro).
- Registo central: pre-registo e resultado do `FILTRO_RENTABILIDADE_F1` (cadeia íntegra).

Fontes das comissões: [Bybit UE — Benefits of the VIP Program](https://www.bybit.eu/en-EU/help-center/article/Benefits-of-the-VIP-Program);
[okx-fee-analysis (GitHub)](https://github.com/zsgkdt42/okx-fee-analysis);
[MEXC Learn — OKX Fees Explained 2026](https://www.mexc.com/learn/article/okx-fees-explained-2026-which-of-okx-three-fee-schedules-is-your-account-secretly-on-/1).
