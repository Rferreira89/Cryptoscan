# Decisão operacional — do que existe ao piloto (11/11/2026, 23h30)

- Base: main 428c5a0, confirmado às 23h. Este ramo (`investigacao/universo-bybit-ue`) está 0 commits atrás do main e à frente com os commits de 11/11. Sem merge.
- Só se usam resultados com a elegibilidade corrigida: os shorts da Bybit UE só contam nas 32 moedas com margem que têm histórico (as 37 da lista menos AERO, HYPE, MNT, POPCAT e ZORA, que não têm velas no ramo history).
- O juro do empréstimo é uma hipótese: testei 0, 0,03% e 0,06% por dia.
- Ambientes separados: HISTÓRICO, FORA DA AMOSTRA, RESERVA (contaminada), PAPEL e REAL.

## 1. Três candidatas, por qualidade da evidência e viabilidade

### 1.ª SHORT_TURTLE, só na fase lateral do BTC, Bybit UE Spot Margin

**Instrumentos.** As 32 moedas com margem e histórico. Na execução, só as que também passam a liquidez da Bybit UE (cerca de 22 hoje).

**Regra.** É a que já existe (`tools/arena_ringue.SHORT_SIGS["SHORT_TURTLE"]`, espelho da Tartaruga):
- entrada: short quando o fecho de 4H perde o mínimo de 20 dias;
- stop a 2 N (N = ATR diário de 20 dias). A mediana é 11,1% do preço (p10 6,8%, p90 16,8%);
- objetivos a 2R e 5R, metade em cada; stop para a entrada depois do 1.º objetivo, depois segue o preço a 1R;
- saída ao fim de 20 dias;
- só quando o regime diário do BTC é `lateral` (`regime_by_day`, só dias passados). Hoje está lateral desde 28/10.

**Custos.** 0,25% de comissão + 0,1% de deslize por lado (0,7% ida e volta). O juro está por confirmar:
- 0,03%/dia × 8,7 dias (duração mediana) ≈ 0,02R por operação;
- 0,06%/dia ≈ 0,05R.

**Resultados por dia independente (IC90 por bootstrap de dias), juro de 0,03%/dia:**

| Amostra | Operações | Dias | R/op | R/dia | IC90 por dia |
|---|---|---|---|---|---|
| A: 2021-06 a 2024-05 (histórico, pré-registado no H10) | 303 | 113 | +0,25 | +0,23 | [+0,06; +0,40] |
| B: 2024-06 até à reserva (fora do período A) | 401 | 120 | +0,09 | +0,28 | [+0,09; +0,46] |
| Moedas que o H10 NÃO usou (fora do universo do estudo) | 201 | 123 | +0,12 | +0,20 | [+0,02; +0,38] |
| Reserva 2026-05-08 a 11-08 (contaminada) | 46 | 22 | +0,43 | +0,07 | [−0,37; +0,49] |
| Com juro de 0,06%/dia, períodos A e B | — | — | +0,22 / +0,06 | +0,20 / +0,25 | os dois > 0 |

- Arena corrigida, 365 dias, lateral, só margem e com juro: 179 operações, +0,40R.
- As últimas 45 operações (bloco reservado) dão −0,11R. A regra de deriva da produção (−0,15R) não dispara com o universo corrigido. Com o universo antigo dava −0,16R, e é isso que hoje a põe em papel.
- Real: 1 operação executada (SEI +1,31R). AVAX e ICP aparecem como reais mas nunca executaram, por isso não contam.

**Riscos e limitações:**
- **Resultados irregulares:** meses de −1R por operação e meses de +1,5R.
- **Meses recentes negativos:** ago/2026 (7 operações, −1,01R) e out/2026 (6, −1,01R).
- **Paper de lateral negativo:** o papel de shorts em lateral da produção (FASES_LATERAL, H29, uma regra diferente mas do mesmo mecanismo) deu −1,11R em 20 operações num só dia de novembro.
- **Viés de sobrevivência:** as moedas com margem são as de hoje; não há lista histórica de margem da Bybit UE.
- **Preços externos:** as velas são da Binance (USDT) e a execução é na Bybit UE (USDC), com volume pequeno.

**Drawdown no piloto** (teto de 3 abertas, blocos de 30 operações seguidas sorteados no histórico antes da reserva):
- P(soma < 0) = 11%;
- P(drawdown ≤ −6R) = 40%; P(≤ −10R) = 27%;
- mediana de +8,7R.
- O teto de 3 deixa passar cerca de 40 operações por ano de lateral; 30 operações levam 6 a 9 meses.

**Capital mínimo.** Com o mínimo de ordem de referência de 5 USDC e um stop de 11%: 110 USDC a 0,5% de risco por operação, 55 USDC a 1%. Para cobrir stops até 17%, 170 USDC a 0,5%. O saldo real está cifrado e não é lido aqui.

### 2.ª TF-SHORT U2, OKX X-Perps (hoje só papel)

**Regra.** É a de `tools/okx_tfshort.py`:
- s = número de médias de 20, 50, 100 e 200 dias abaixo do fecho;
- short com s ≤ 1, saída com s ≥ 3;
- stop entrada + 3 ATR20;
- universo de volume ≥ 20 M.

Refiz o livro "sinais" com as funções da produção, sobre velas diárias do ramo history, incluindo 185 moedas retiradas da bolsa (84 moedas usadas). Custos de 0,17% por lado e funding real quando existe (589 de 761 operações).

| Amostra | Operações | Dias | R/op (IC90 agrupado) | R/dia (IC90) |
|---|---|---|---|---|
| Antes da reserva | 732 | 345 | +0,15 [+0,01; +0,29] | +0,09 [+0,00; +0,18] |
| 1.ª metade / 2.ª metade | 352 / 380 | 172 / 173 | +0,09 / +0,20 | +0,07 / +0,11 (os dois IC incluem 0) |
| Reserva (contaminada) | 29 | 26 | −0,22 | **−0,26 [−0,51; −0,01]** |

- Teto de 5 abertas: +0,23R por operação, mas só cerca de 38 operações por ano. P(soma < 0 em 30 operações) = 39%.
- O resultado bate com o backtest citado no código (+0,15 a +0,17R).
- Limitações:
  - os últimos 6 meses são negativos;
  - o papel ao vivo (desde 05/11) tem 23 sinais abertos e 0 fechados;
  - a conta simulada ignora 29 sinais abaixo do mínimo do contrato;
  - o executor da OKX não tem esta estratégia: um piloto real precisava de código novo no executor.

### 3.ª H40 pânico do mercado, OKX (real desligado)

- +0,09 a +0,14R por operação com o teto de 3, mas por dia independente o IC90 inclui zero com qualquer preenchimento.
- No real, 0 de 5 ordens de pânico de mercado encheram.
- Não serve para piloto. Continua em papel, que a correção técnica A4 deve tornar conservador.

**Conclusão.** Nenhuma estratégia tem vantagem demonstrada em dinheiro real. A SHORT_TURTLE em lateral é a única com evidência fora da amostra em dois períodos e num universo de moedas que o estudo não usou, já com a elegibilidade corrigida e com juro. Chega para um **piloto experimental pequeno**, não para produção.

## 2. Carteira por regime (o que existe hoje)

| Regime | Bybit UE | OKX |
|---|---|---|
| Lateral (atual) | **SHORT_TURTLE em margem** (candidata a piloto) | TF-SHORT (papel) |
| Queda | SHORT_X30/ISOLADA: em queda com margem +0,07R/dia, IC inclui 0 → sombra | TF-SHORT (papel), QUEBRA_MINIMO_SHORT (sombra a partir de 12/11) |
| Subida | Bounce/DIP: poucos dias → sombra | H46 (sem vantagem por dia; real ligado a 1%), MOMENTO_RISCO_ON (sombra) |
| Extremos | — (H45 perde) | H40 de mercado em papel, com controlo por acontecimento: não melhora |
| Intradiário | BOUNCE_1H morto | **Faltam dados**: não há velas de 1h ou 15m dos X-Perps da OKX no ramo history |

## 3. Plano do piloto SHORT_TURTLE (só com autorização)

- **Risco por operação:** 0,5%, metade do atual (1%). Não se aumenta nada.
- **Máximo em simultâneo:** 3 posições, todas da SHORT_TURTLE.
- **Instrumentos:** só moedas com margem confirmada e liquidez da Bybit UE. O executor já recusa as que não têm margem.
- **Perda máxima acumulada:** −10R, ou seja −5% do capital a 0,5%. Ao atingir, suspende sozinho. A probabilidade histórica de chegar lá em 30 operações, mesmo com a vantagem real, é de 27%. É o preço de um piloto honesto.
- **Outras suspensões automáticas:**
  - perda ≤ −3R num dia;
  - juro real médio > 0,06R por operação;
  - a fase do BTC sair de lateral (não abre novas);
  - os travões existentes (−3R por dia, −6R por semana).
- **Decisão às 30 operações executadas:**
  - média < 0 → termina;
  - soma abaixo do p05 esperado (−8,4R) → termina;
  - média ≥ 0 → decide-se contigo se continua, igual ou alterado.
- **Comparação real × esperado:** +0,33R por operação esperado; banda de 30 operações entre −8,4R (p05) e +8,7R (p50).
- **Implementação:** `engine/piloto.py` (feito, testado, **não ligado**). Conta só operações reais executadas na corretora.
- **Risco financeiro máximo do piloto:** −5% do capital da Bybit UE, mais o deslize de stops em gap (historicamente −1,05 a −1,10R no pior caso por operação).

## 4. O que falta para pôr o piloto a funcionar (por ordem)

1. **Integrar as correções A** do ramo: arena com elegibilidade real, contagens e leitor de margem. Precisa do teu OK.
2. **Confirmar a margem e o juro reais:** `python -m engine.account --margem saida.json` no servidor europeu (só GET, chave só de leitura). Precisa do teu OK, porque é uma execução nova no servidor.
3. **Corrigir no registo as operações reais sem execução** (AVAX e ICP). Precisa do teu OK: está proibido desde 11/11.
4. **Ligar `engine/piloto.py`** ao controlo de entradas novas (só bloqueia). É uma alteração de código no ramo, a integrar com OK.
5. **Autorizar:** `real_autorizados: ["SHORT_TURTLE"]` e risco de 0,5% para esta estratégia. Decisão tua.

## 5. Mais oportunidades qualificadas (sem perder expectativa)

- **Universo:** 15 moedas com margem estão fora da execução por volume na Bybit UE (BNB, DOT, APT, CRV, TRUMP…). Não se baixa o piso: o custo do spread já está no limite.
- **OKX intradiário:** recolher velas públicas de 1h dos X-Perps da OKX (workflow novo, só leitura; precisa de OK). É o único regime ainda sem dados.
- **TF-SHORT:** o papel continua; o executor da OKX só a recebe se o papel e a reserva voltarem a positivo.
- **Shorts em queda** (SHORT_X30/ISOLADA só com margem): sombra até ≥ 20 dias independentes em queda.

## 6. Decisões que são tuas

1. Integrar o grupo A do ramo `investigacao/universo-bybit-ue` (sem efeito em ordens; muda os números da arena).
2. Correr a leitura da margem e do juro no servidor europeu.
3. Corrigir o registo de AVAX e ICP.
4. Aprovar o piloto SHORT_TURTLE com os limites da secção 3, ou não.
5. Recolher velas de 1h da OKX.
