# C4 — Reversão de curto prazo em índices, metais e ações (pré-registo)

Escrito e publicado **antes** de correr qualquer teste (Rui, 19–20/11/2026: "estratégias diferentes para cripto,
ações e metais", LONG e SHORT testados separadamente, por regime). Nada abaixo muda depois de ver resultados; uma
alteração exige um novo pré-registo com outro nome e conta como novos testes.

Contexto: o C2 (13/11) já testou seguimento de tendência nestes ativos (30 testes, nenhum passou; os shorts de
tendência foram sempre piores). Este estudo testa a família oposta, a reversão de curto prazo.

## Dados

- Diário, ramo `indices-diario` (Yahoo, ~15 anos, OHLC): índices `^GSPC` (S&P 500 → US500/SPY) e `^NDX`
  (Nasdaq 100 → US100/QQQ); metais `GC=F` (ouro → XAU) e `SI=F` (prata → XAG). Dias sem fecho são ignorados.
- Ações (classe "ações"), lista fixa agora, todas com perpétuo na OKX: AAPL AMD AMZN ADBE AMAT AVGO GOOGL IBM INTC
  KO LLY META MRVL MSFT MSTR MU NFLX NVDA ORCL QCOM TSLA TSM. Recolha pelo mesmo workflow (Yahoo, 15 anos, preços
  ajustados a desdobramentos). **Viés de sobrevivência**: a lista é de empresas que hoje existem e são grandes.
- Limites conhecidos: os futuros contínuos do Yahoo não estão ajustados à mudança de contrato (metais); o contrato
  da OKX pode divergir do ativo de base (prémio, horas sem volume).

## Regras (todas diárias; sinal no fecho do dia t, entrada na **abertura de t+1**)

| Regra | LONG | SHORT |
|---|---|---|
| **V3** (3 dias seguidos) | 3 fechos seguidos abaixo do fecho anterior | 3 fechos seguidos acima do fecho anterior |
| **RSI2** (RSI de Wilder, 2 dias) | RSI2 < 10 | RSI2 > 90 |

Saídas (iguais para todos; a primeira que acontecer):
- **Stop**: entrada ∓ 2 × ATR(14) do dia do sinal. Se o mínimo (LONG) / máximo (SHORT) do dia toca o stop, sai no
  stop; se a abertura já passou o stop, sai na abertura.
- **V3**: no fecho do primeiro dia com fecho acima (LONG) / abaixo (SHORT) do fecho anterior.
- **RSI2**: no fecho do primeiro dia com fecho acima (LONG) / abaixo (SHORT) da média de 5 dias.
- **Tempo**: no fecho do 5.º dia (V3) ou do 10.º dia (RSI2) em posição.
- Uma posição de cada vez por ativo, regra e lado; um sinal com posição aberta é ignorado.

Resultado em R: (saída − entrada) / (2 × ATR), com sinal para o SHORT; custos: 0,10% por lado (comissão e deslize)
e financiamento de 0,03% por dia em posição, sempre pago (conservador, como no C2), convertidos em R.

## Regime (do próprio ativo, no dia do sinal)

- **subida**: fecho acima da média de 200 dias e a média de 200 a subir em 20 dias;
- **descida**: fecho abaixo da média de 200 dias e a média a descer em 20 dias;
- **lateral**: o resto.

## Testes e critérios de aprovação

Uma célula = (classe, regra, lado, regime): classes índices (S&P 500 + Nasdaq 100), metais (ouro + prata) e ações
(22 ações em conjunto). 3 × 2 × 2 × 3 = **36 testes**, Holm a 5%. Uma célula aprova **só se cumprir tudo**:

1. pelo menos 30 operações;
2. R médio líquido > 0 em cada um dos três períodos por tempo (50% / 25% / 25% da série, os mesmos para todas as
   células), com pelo menos 5 operações em cada período;
3. bate o acaso: 2000 conjuntos de entradas ao acaso nos dias do mesmo regime, mesmo ativo, mesmo lado e mesmas
   saídas, com o mesmo número de entradas por ativo; p = fração dos conjuntos com R médio ≥ ao real; p de Holm
   (36 testes) < 0,05;
4. robustez: R médio > 0 com custos 25% mais altos, e > 0 sem o ativo que mais contribui (só se a classe tiver 2+
   ativos com operações).

Uma célula aprovada dá uma estratégia **candidata**, que vai para papel na OKX (perpétuo correspondente, entradas
e stops só com a bolsa de Nova Iorque aberta) e **só entra no piloto depois de 26/11**, com o OK do Rui. Os LONG e
os SHORT são aprovados em separado; nenhuma célula aprovada autoriza o lado oposto.

Código: `backtest/estudos/c4_reversao.py`; resultado: `backtest/estudos/c4_resultado.json`.

## Resultado (corrido a 20/11/2026, depois de publicado o pré-registo no commit b26aae1)

**1 de 36 células aprovada**: ações, RSI2, LONG, regime de descida — 1095 operações (22 ações, 2011-11 → 2026-11),
**+0,030R** por operação, acerto 64%, os três períodos positivos (+0,009 / +0,053 / +0,042), acaso p95 +0,011,
p de Holm 0,034, custos +25%: +0,017R, sem a TSM: +0,023R; 14 de 22 ações positivas.

Todas as outras 35 falharam, incluindo **todas as células de metais** (12 de 12 negativas) e **todos os SHORT**
das três classes. Nos índices nada passou (o melhor, RSI2 LONG em subida, p de Holm 0,165).

Limites da célula aprovada (não mudam o veredicto, mas condicionam o uso):
- a vantagem é pequena: um custo extra de ida e volta de ~0,23% do preço (risco médio 2×ATR ≈ 7,5% do preço)
  anula-a. Na OKX vimos spreads de 0,06% (SPCX) a 0,94% (GEV): só serve em ações com spread muito baixo;
- viés de sobrevivência forte para esta regra: compra quedas de ações que hoje sabemos que sobreviveram e cresceram;
- o financiamento real dos perpétuos de ações da OKX não foi medido (usou-se 0,03%/dia).
Próximo passo possível: papel na OKX com spread ≤ 0,10% e só com a bolsa de Nova Iorque aberta; nada no piloto
antes de 26/11.
