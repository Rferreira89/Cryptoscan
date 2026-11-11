# Universo Bybit UE e plano de rentabilidade (11/11/2026, 22h)

Ramo `investigacao/universo-bybit-ue`, a partir do main 428c5a0. Nada foi integrado no main.
Só R e percentagens; nunca dinheiro da conta.

## 1. Bybit UE: o que o código usa (verificado no código)

| Pergunta | Resposta |
|---|---|
| REST da conta e execução | `https://api.bybit.eu`, em `engine/account.py` BASE e `engine/executor.py`. Corre no servidor europeu (o GitHub não chega à Bybit). |
| REST de mercado da Bybit UE | O mesmo `api.bybit.eu`: `/v5/market/tickers` (spot), `/v5/market/instruments-info` (spot). Lido de 15 em 15 min pelo servidor europeu e guardado em `state.bybit_tickers` e `state.margem_bybit`. |
| Bybit internacional | `engine/sources.Bybit` (`api.bybit.com`) existe mas não está em `sources.ALL`: não é usada. Só aparece em `tools/eu/teste.py`, um teste manual de comparação. |
| WebSocket | Não há WebSocket da Bybit. O único do código é o de liquidações da Binance (`tools/eu/liquidacoes.py`). |
| Endpoint de instrumentos | `/v5/market/instruments-info?category=spot`. O filtro `quoteCoin=USDC`, `marginTrading` both/utaOnly e `status=Trading` dá a lista de margem. O executor lê o `minOrderAmt` de cada par na hora de colocar a ordem. |
| Origem dos 967 | Moedas base (não pares) da união das fontes de descoberta: Binance (776 pares USDT), KuCoin (803) e OKX (477), via `engine/scanner.build_universe`. É um universo externo de descoberta, não o catálogo da Bybit UE. |
| Catálogo real da Bybit UE | 108 pares spot USDC na API da Bybit UE (a CoinGecko mostra 105 moedas e 125 pares, com EUR e PLN; não há USDT). |
| Negociáveis pela conta | 108 em spot (lista de tickers ativa). O mínimo de ordem é lido na hora; a referência de configuração é 5 USDC. |
| Spot Margin, com short possível | 37 moedas. |
| Com liquidez e spread suficientes | 26, com mediana de 20 dias ≥ 25 mil USD/24h e spread ≤ 0,3%. Só 2 passam 1 M USD/dia (BTC, ETH) e 6 passam 250 mil. |
| Short e liquidez ao mesmo tempo | 22. |
| Chegam à análise do scan | 68. Os outros 40 pares da Bybit UE não passam o filtro externo (volume ≥ 1 M e spread ≤ 20 bps nas fontes Binance/OKX/KuCoin) ou não existem lá. Todos têm volume inferior a 81 mil USD/dia na Bybit UE. |

A tabela completa (108 instrumentos: fonte, mercado, short, volume, spread, mínimo, motivo) está em
`universo_bybit_ue_2026-11-11.md` e `.json`, gerada por `tools/universo_bybit_ue.py`.

### Mistura de universos encontrada e corrigida neste ramo

1. **Arena: shorts em moedas sem margem.** Os lutadores SHORT combatiam em todas as moedas líquidas, incluindo as que a conta não pode vender a descoberto (por exemplo INJ, NEAR, GRASS, LIT).
   - Correção: `run(..., margem=)` só põe shorts nas moedas com margem.
   - Antes, a promoção barrava estas moedas ao vivo, mas os veredictos da arena eram calculados com elas.
2. **Arena: universo vindo da CoinGecko.** Agora usa a lista direta da API da Bybit UE (`state.bybit_tickers`, o mesmo do scanner), com até 6 h de idade. A CoinGecko fica como recurso, e os pares que a Bybit UE já não lista são cortados.
3. **Arena: shorts sem juro do empréstimo.** Agora `juros_short_r` desconta o juro diário × dias / distância do stop. A referência é 0,03%/dia, NÃO VERIFICADA; o valor real é por moeda e a configuração `juros_margem_dia_pct` sobrepõe-se.
4. **Rótulo enganador, não é um erro de execução.** `counts.pairs_seen` = 967 são moedas externas. O executor só usa pares que existem na Bybit UE: `não listado na Bybit UE` exclui o resto.

### Comissões da Bybit UE

- Taxa única de 0,25% por lado desde 5/10/2026 (antes: 0,10% maker e 0,25% taker), segundo uma fonte secundária.
- A arena e o papel já usam 0,25% + 0,1% de deslize por lado, ou seja 0,7% ida e volta, mais o spread real acima de 0,2%.
- Com spreads medianos de 0,02% a 0,20% e o mínimo de 5 USDC, o custo total ida e volta numa alt líquida fica entre 0,7% e 0,9%.

## 2. Execução: preenchimento conservador das ordens limite

Os estudos H40, H45 e H46 enchem a ordem limite quando o mínimo da vela toca no limite. Refiz-os exigindo que o preço passe o limite em 0,1% e em 0,3%. Os valores são os de antes da reserva:

| | toque | 0,1% | 0,3% |
|---|---|---|---|
| H40 mercado, R/op (teto de 3 abertas) | +0,35 (+0,10) | +0,33 (+0,08) | +0,33 (+0,10) |
| H46 RSI<30, R/op (teto de 3) | +0,03 (−0,02) | +0,03 (−0,01) | −0,01 (−0,08) |
| H46 RSI<35, R/op (teto de 3) | −0,01 (+0,03) | −0,04 (−0,01) | −0,06 (0,00) |

A H40 aguenta o preenchimento conservador; a H46 desce para zero ou abaixo. No real, a H40 teve 5 de 9 ordens limite por encher e as 4 que encheram eram de pânico isolado. Isto é seleção adversa: as ordens limite só enchem quando o preço continua a cair.

## 3. Plano executável

### A. Correções técnicas
1. **Arena com o universo real da Bybit UE** (feito neste ramo): `tools/arena_ringue.py` (`universo_bybit_ue`, `run(margem=)`, `juros_short_r`), testes em `tests/test_universo_bybit_ue.py`. Aceitação:
   - a arena regista `universo_fonte=bybit_ue_direto`;
   - `shorts_universo` contém só moedas com margem;
   - os R dos shorts levam `juros_r`;
   - a suite completa passa.
   - Para integrar é preciso o teu OK: muda os veredictos da arena, que alimentam a promoção.
2. **Publicar o mínimo de ordem e o passo de cada par da Bybit UE.** Em `engine/account.py`, ler `lotSizeFilter.minOrderAmt` de todos os pares USDC na mesma chamada de `margem()` e publicar `state.minimos_bybit`. Teste com uma resposta sintética. Aceitação: a auditoria do universo deixa de usar a referência de 5 USDC.
3. **Renomear `pairs_seen` para `moedas_descoberta_externa`** e acrescentar `pares_bybit_ue` a `counts`, em `engine/scanner.py` e no scanner HTML. Só nomes, sem efeito nas ordens.
4. **Papel da H40 com preenchimento conservador.** Em `engine/papel_panico.update` e `tools/okx_agente.py`, mudar `l <= lim` para "negócio abaixo do limite" (0,1% ou um tick). Aceitação: o papel deixa de encher as ordens que o real não encheu (como TRUMP e WLD a 06/11). Mexe no papel, não no real, mas o papel decide a avaliação.
5. **Registar a geometria dos sinais perdidos da Bybit** (`state.promo_lost`: entrada, stop, objetivos). Sem isto, os sinais rejeitados só se medem com o substituto de 72 h.

### B. Melhorias com evidência económica
- Nenhuma passou: o filtro de stop largo da H46 caiu com as moedas retiradas e os tetos de posições tiram a vantagem da H40.
- **H40 (OKX):** a vantagem está nos dias de colapso com muitos sinais. Com o mesmo risco total, a alternativa é dividir o risco do dia por todos os sinais em vez de tomar 3. Por acontecimento isso dá −0,01R por dia (63 dias), ou seja sem vantagem. Não implementar.

### C. Precisa de dados novos ou validação em sombra
1. Família Bounce na Bybit UE em regime `subida` (BOUNCE_X30 +0,55R em 35 operações), mas só 6 dias. Critério: ≥ 20 dias independentes em subida, nas 26 moedas executáveis, depois de corrigida a arena.
2. Shorts na Bybit UE em regime `queda`, só nas 22 moedas com margem e liquidez, com juro: SHORT_X30 (+0,43R em queda) e SHORT_FALSO_ROMP (+0,34R, limite inferior por dia −0,004). Refazer na arena corrigida; sombra até ≥ 20 dias em queda.
3. OKX: MOMENTO_RISCO_ON e QUEBRA_MINIMO_SHORT (pré-registadas, a começar a 12/11).
4. Shorts rejeitados por `plano` na Bybit: +2,1% em 72 h (33 sinais, 6 dias). Precisa da correção A5 para medir com stop e objetivo.

### D. Manter suspensas ou abandonar
- H45 (pânico com custos Bybit): perde por dia; o pânico só faz sentido na OKX.
- H40 pânico isolado: papel −0,55R (20 operações), real 4 de 4 no stop.
- FASES_LATERAL e MACRO (papel negativo).
- Lutadores da arena com 365 dias negativos e fora da amostra negativos: BRK_ESPACO, SQUEEZE_BB, MOMENTUM, FIBO_RECUO, MAIORES_FUNDING, BREAKOUT, LIQUIDITY_SWEEP e os clones.

### Cobertura por regime, corretora e direção (lacunas)

| Regime | Bybit UE spot | Bybit UE margem (short) | OKX X-Perps |
|---|---|---|---|
| Subida | Bounce/DIP (inconclusivo, poucos dias) | — | H46 (sem vantagem demonstrada), MOMENTO_RISCO_ON (sombra) |
| Lateral | nada positivo | nada positivo | nada |
| Queda / pânico | — | SHORT_X30/FALSO_ROMP (inconclusivo) | H40 mercado (vantagem só sem teto), QUEBRA_MINIMO_SHORT (sombra) |
| Intradiário (1h/15m) | BOUNCE_1H morto | — | sem dados de 15m; sazonalidade de 1h abaixo do custo |

Lacunas reais:
- regime lateral (é o atual em muitas moedas);
- intradiário na OKX, onde o custo de 0,2% o permite: faltam velas de 15m/1h de X-Perps no ramo history.

---

# Fecho (11/11, 23h): arena com shorts só onde a Bybit UE deixa vender

Scripts em `backtest/estudos/universo/`.
- `arena_shorts.py` corre o `arena_ringue.run` real, só com os lutadores SHORT.
- `comparar_arena.py` usa `tools/auditoria_rentabilidade.py` do ramo `investigacao/expansao-rentabilidade`.

Dados: velas de 4H do ramo history, nas moedas que a Bybit UE lista hoje: 70 moedas, 32 delas com margem.

## Arena de 365 dias: antiga, só margem, e só margem com juro de 0,03%/dia (juro não verificado)

| Lutador | Antiga: n / dias / R/op / R/dia / veredicto | Só margem | Margem e juro | Operações antigas sem margem |
|---|---|---|---|---|
| SHORT_FALSO_ROMP (só papel de estudo) | 102 / 51 / +0,29 / **+0,28** / SOBE | 36 / 25 / +0,25 / **+0,01** / SOBE | 36 / 25 / +0,24 / **+0,00** / SOBE | 65% (R +0,32) |
| SHORT_TURTLE | 676 / 166 / +0,26 / +0,25 / MORTA (90 d) | 299 / 105 / +0,27 / +0,25 | 299 / 105 / +0,23 / +0,22 | 56% (R +0,25) |
| SHORT_X30 | 902 / 209 / −0,14 / −0,08 / MORTA | 422 / 121 / −0,14 / −0,10 | 422 / 121 / −0,16 / −0,11 | 53% |
| SHORT_ISOLADA | 753 / 195 / −0,12 / −0,08 / MORTA | 341 / 110 / −0,14 / −0,10 | 341 / 110 / −0,15 / −0,11 | 55% |
| SHORT_FLUXO | 349 / 135 / −0,20 / −0,11 / MORTA | 170 / 72 / −0,21 / −0,09 | 170 / 72 / −0,22 / −0,11 | 51% |
| SHORT_MAIORES_* | só BTC, ETH e SOL: não muda | — | juro −0,02R | 0% |

**Por regime (365 d).** Em queda, SHORT_X30 passa de +0,35R (112 operações) para +0,60R (51) e SHORT_ISOLADA de +0,29R para +0,53R (43).
- Ambos têm `SOBE` em queda nas três versões.
- Em subida e lateral perdem sempre.

**Por moeda.** O detalhe está nos JSON. A maior parte do ganho antigo da SHORT_FALSO_ROMP vinha de moedas sem margem (NXPC, STRK, XPL, RESOLV, ANIME, HOME…).

**Arena de 90 dias.** Todos os shorts estão MORTA nas três versões.
- Cerca de metade das operações era em moedas sem margem.
- O juro custa entre 0,01 e 0,03R por operação.

## Promoções antigas baseadas em operações impossíveis?

- **SHORT_TURTLE**, campeão em lateral (`campeoes_estudo`): veio do estudo H10, com 25 moedas, das quais 5 sem margem (NEAR, TRX, PUMP, XPL, BCH). Refeito só com margem e com juro continua **APTA** em lateral:
  - período A: +0,23R por operação, +0,25R por dia, 102 dias;
  - período B: +0,17R por operação, +0,18R por dia, 117 dias.
  - A promoção não dependia de operações impossíveis.
- **SHORT_FALSO_ROMP**: a vantagem por dia dependia de moedas sem margem; nas moedas executáveis fica em +0,00R por dia. Está só em papel de estudo (fora de `REAL_OK`), por isso não houve dinheiro real envolvido.
  - Com a regra atual da arena continuaria `SOBE`, porque a regra conta operações e não dias.
- **Registo de operações reais da Bybit:** tem 2 shorts REAL FECHADOS sem nenhuma execução na corretora. É o mesmo par já provado no ensaio do ledger: AVAX (+0,52R) e ICP (+0,47R). A ICP nem tem margem: foi recusada a 22/10.
  - Os resultados reais da arena e da promoção não os usam, porque filtram por `executed`.
  - A correção do ledger continua por autorizar.

## Elegibilidade real de shorts por moeda

- `engine/account.interpretar_margem` e `margem_detalhe` estão no ramo; não estão ligados ao snapshot, ao scanner nem ao executor.
- Usam só leituras (GET), com a chave só de leitura:
  - `instruments-info`: estado, margem spot, mínimos de quantidade e valor, máximo;
  - `account/collateral-info`: se a moeda é emprestável, quantidade disponível para empréstimo, máximo e taxa horária.
- **Limitação:** não consegui confirmar se a Bybit UE serve `collateral-info` (o acesso daqui à API está bloqueado e correr no servidor europeu é um workflow novo). Por isso, para cada moeda, a quantidade emprestável e a taxa estão **por confirmar**. O código devolve `None` e `confirmado=false`; nunca inventa.
- Para confirmar: `python -m engine.account --margem saida.json` no servidor europeu (precisa do teu OK).

## H40: preenchimento × tetos, por dia independente (antes da reserva, 53 dias)

| Preenchimento | Variante | Operações | R/op | R médio por dia, risco do dia dividido pelos sinais (IC90) | Dias + |
|---|---|---|---|---|---|
| toque | todos os sinais | 349 | +0,35 | −0,04 [−0,25; +0,19] | 24 / 53 |
| toque | teto 3 abertas | 106 | +0,14 | +0,07 [−0,18; +0,33] | 21 / 47 |
| toque | teto 1 aberta | 42 | +0,04 | +0,07 [−0,19; +0,35] | 17 / 40 |
| 0,1% | todos os sinais | 343 | +0,33 | −0,04 [−0,25; +0,18] | 23 / 53 |
| 0,1% | teto 3 | 107 | +0,09 | +0,03 [−0,21; +0,29] | 21 / 47 |
| 0,1% | teto 1 | 43 | −0,02 | +0,06 [−0,22; +0,35] | 17 / 40 |
| 0,3% | todos os sinais | 333 | +0,33 | −0,06 [−0,27; +0,17] | 22 / 53 |
| 0,3% | teto 3 | 105 | +0,11 | +0,04 [−0,19; +0,28] | 21 / 47 |
| 0,3% | teto 1 | 42 | −0,10 | −0,06 [−0,33; +0,23] | 16 / 40 |

- O risco agregado por acontecimento, que divide o mesmo risco pelos sinais do dia, é a coluna "R médio por dia". Em todas as variantes o IC90 inclui zero. Não há vantagem por acontecimento.
- O ganho de "todos os sinais" (+2,1 a +2,3R somados por dia) só existe arriscando mais nos dias com muitos sinais; 3 dias valem 84 a 94% do total. Não se recomenda.

## Decisão de integração

**A. Pode integrar-se: só elimina avaliações impossíveis ou erradas.**
1. Os shorts da arena passam a combater só em moedas com margem, `run(margem=)`.
2. O universo da arena passa a vir da API da Bybit UE.
3. Contagens com nomes corretos (`moedas_descoberta_externa`, `pares_bybit_ue`, `pares_bybit_ue_margem`, `moedas_analisadas`), mais os textos do painel; `pairs_seen` mantém-se por compatibilidade.
4. `interpretar_margem` e `margem_detalhe`, que são só leitura e não estão ligadas a nada.

Mesmo sendo correções, mudam os números que a arena publica. Recomendo integrar com uma nota no relatório da arena.

**B. Muda classificações ou critérios: precisa de validação.**
1. O juro de 0,03%/dia nos shorts da arena: o valor tem de vir de `collateral-info` antes de ser critério.
2. Passar a regra `SOBE`/morte da arena a contar dias independentes em vez de operações: é o caso SHORT_FALSO_ROMP.
3. A promoção por regime de SHORT_X30 e SHORT_ISOLADA em queda: melhora com a margem, mas é uma nova comparação múltipla. Fica só em sombra.

**C. Continua sem evidência suficiente.** H40 com qualquer teto ou agregação, H46, Bounce em subida, SHORT_MAIORES_TENDENCIA (15 operações).

**Execução real.** Este ramo não mexe em `engine/executor.py`, `tools/okx_exec.py`, `config.json`, `okx_config.json` nem `.github/workflows`. O `engine/scanner.py` só acrescenta contagens.
