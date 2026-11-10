# Resultados retrospetivos — 10/11/2026

Gerado pela corrida 42861911316 do workflow `quant-retrospetiva` (ramo `quant-dsr-pbo-residual`), com as cópias
públicas dos agentes, o estado completo (aberto só dentro da corrida), as velas de 4H do ramo history e os preços
horários do BTC da Binance pública. Só investigação: **não é autorização para usar em dinheiro real**.

## Leitura
- **H40 (pânico do mercado), BACKTEST, 393 operações.**
  - DSR 0,999–1,000 com N = 100 a 158 tentativas: o Sharpe por operação sobrevive ao desconto pelas tentativas.
  - Contra o BTC: β = +12,3 R por cada 100% do BTC, isto é, cerca de +0,12 R por cada 1% que o BTC sobe durante a
    operação.
  - α = +0,18 R por operação, IC95% [−0,01; +0,37], p = 0,058: no limiar, sem significância a 5%.
  - Do resultado total (+123 R), +52 R explicam-se pelo movimento do BTC na mesma janela e +71 R são residuais.
  - Quebra por regime: com o BTC abaixo da sua média de 20 dias (372 operações), α = +0,21 (p = 0,03). Com o BTC acima
    (21 operações), α = −0,60 (p < 0,001), mas a amostra é pequena.
  - Estabilidade: α = +0,26 na 1ª metade e +0,07 na 2ª (p = 0,40), enquanto β sobe de 9 para 17. A parte própria
    enfraqueceu na metade mais recente.
- **H40 (todos os sinais), 1071 operações.** DSR 0,72–0,78 (não passa 0,95); α = +0,04 (p = 0,39). Os sinais de
  pânico isolado diluem a regra.
- **H45 (pânico do mercado com custos Bybit), 393 operações.**
  - DSR 0,98–0,99.
  - α = +0,12 (p = 0,21): sem vantagem própria significativa além do BTC.
  - Na 2ª metade α ≈ 0.
- **H46, BACKTEST.**
  - RSI<30 (394 operações): DSR 0,32–0,38.
  - RSI<35 (1041 operações): DSR 0,03–0,05.
  - α não significativo nas duas; β ≈ 20, a exposição ao BTC mais alta das regras avaliadas.
  - Não passa o desconto pelas tentativas.
- **PBO por CSCV.**
  - H40 (todos vs só o pânico do mercado): PBO 0,21–0,46 consoante S, probabilidade de perda fora da amostra 3–6%.
  - H46 (RSI<30 vs RSI<35): PBO 0,17–0,26.
  - Com só 2 configurações o PBO é indicativo (pouca resolução).
  - Arena (PAPEL): 13 dias com fechos para 10 configurações; insuficiente para CSCV.
- **Real e papel ao vivo.** OKX real H40 (4 operações), papel H40 (21), papel H45 (20), fases lateral (20), arena
  (≤ 7 por lutador) e Bybit real (≤ 4 por estratégia): todos abaixo do mínimo de 30. Não se conclui nada.
- **H52, H53, H57, H58, H59.** Ainda sem operações fechadas publicadas.

## Diferença face aos estudos registados
O ramo history foi atualizado depois dos estudos (velas mais recentes; 68 em vez de 69 moedas com funding), por isso
as contagens diferem ligeiramente:

| Estudo | Registado | Esta corrida |
|---|---|---|
| H40, todos os sinais | 1044 | 1071 |
| H46 RSI<30 | 397 | 394 |
| H46 RSI<35 | 1048 | 1041 |

Com a cópia antiga dos dados (sessão local), o adaptador reproduziu as contagens registadas exatamente:
1044 / 393 / 393 / 397 / 1048.

## Limites
- **Operações sobrepostas:** o DSR por operação assume operações independentes. Operações do mesmo pânico estão
  correlacionadas, por isso o DSR é otimista; o Newey-West só corrige a autocorrelação em série.
- **β linear:** β é linear e calculado na janela da própria operação.
- **N conservador:** pode contar duas vezes a mesma ideia; mostram-se os dois valores de N.
- **Backtests:** usam os custos que cada estudo registou (H40 com futuros OKX, H45 com Bybit UE); nada foi recalibrado.

## Tabela completa (saída da corrida)
# Avaliacao quantitativa retrospetiva (2026-11-10 17:09 UTC)

So investigacao. Ambientes separados; nada aqui altera estrategias ou risco. Valores em R.

Tentativas contadas: minimo 100, conservador 158 ({'agendadas': 25, 'offline': 75, 'novas_registadas': 5, 'lutadores_arena': 53}).
BTC: 14333 pontos, 2021-01-01 a 2026-11-10.

| Ambiente | Estrategia | n | R medio | DSR (N min) | DSR (N cons.) | beta BTC | alfa (p) | Veredito residual |
|---|---|---|---|---|---|---|---|---|
| BACKTEST | H40 (panico do mercado) | 393 | +0.314 | 1.000 | 0.999 | +12.35 | +0.180 (0.06) | sem evidencia de vantagem propria alem do BTC |
| BACKTEST | H40 (todos os sinais) | 1071 | +0.101 | 0.775 | 0.724 | +14.35 | +0.041 (0.39) | sem evidencia de vantagem propria alem do BTC |
| BACKTEST | H45 (panico do mercado, custos Bybit) | 393 | +0.254 | 0.988 | 0.982 | +12.36 | +0.120 (0.21) | sem evidencia de vantagem propria alem do BTC |
| BACKTEST | H46 (RSI<30) | 394 | +0.119 | 0.382 | 0.323 | +20.10 | +0.071 (0.26) | sem evidencia de vantagem propria alem do BTC |
| BACKTEST | H46 (RSI<35) | 1041 | +0.028 | 0.046 | 0.033 | +20.51 | -0.032 (0.43) | sem evidencia de vantagem propria alem do BTC |
| BYBIT_REAL | BOUNCE_SQUEEZE | 4 | +0.015 | insuf. (4) | insuf. (4) | – | – | 4 observacoes alinhadas (minimo 30) |
| BYBIT_REAL | BOUNCE_X30 | 2 | -1.000 | insuf. (2) | insuf. (2) | – | – | 2 observacoes alinhadas (minimo 30) |
| BYBIT_REAL | BREAKOUT | 3 | -1.000 | insuf. (3) | insuf. (3) | – | – | 3 observacoes alinhadas (minimo 30) |
| BYBIT_REAL | LIQUIDITY_SWEEP | 2 | -0.219 | insuf. (2) | insuf. (2) | – | – | 2 observacoes alinhadas (minimo 30) |
| BYBIT_REAL | PULLBACK | 1 | -1.000 | insuf. (1) | insuf. (1) | – | – | 1 observacoes alinhadas (minimo 30) |
| BYBIT_REAL | SHORT_TURTLE | 1 | +1.307 | insuf. (1) | insuf. (1) | – | – | 1 observacoes alinhadas (minimo 30) |
| BYBIT_REAL | TREND_DAILY | 1 | -1.000 | insuf. (1) | insuf. (1) | – | – | 1 observacoes alinhadas (minimo 30) |
| OKX_REAL | H40 | 4 | -1.043 | insuf. (4) | insuf. (4) | – | – | 4 observacoes alinhadas (minimo 30) |
| PAPEL | ARENA:BOUNCE_G0 | 1 | +0.017 | insuf. (1) | insuf. (1) | – | – | 1 observacoes alinhadas (minimo 30) |
| PAPEL | ARENA:BOUNCE_V1 | 1 | -1.024 | insuf. (1) | insuf. (1) | – | – | 1 observacoes alinhadas (minimo 30) |
| PAPEL | ARENA:BOUNCE_V2 | 7 | -0.615 | insuf. (7) | insuf. (7) | – | – | 7 observacoes alinhadas (minimo 30) |
| PAPEL | ARENA:BOUNCE_V3 | 1 | -0.924 | insuf. (1) | insuf. (1) | – | – | 1 observacoes alinhadas (minimo 30) |
| PAPEL | ARENA:BOUNCE_X30 | 2 | -1.000 | insuf. (2) | insuf. (2) | – | – | 2 observacoes alinhadas (minimo 30) |
| PAPEL | ARENA:BOUNCE_X30_LIQ | 6 | -0.559 | insuf. (6) | insuf. (6) | – | – | 6 observacoes alinhadas (minimo 30) |
| PAPEL | ARENA:BREAKOUT | 1 | -1.000 | insuf. (1) | insuf. (1) | – | – | 1 observacoes alinhadas (minimo 30) |
| PAPEL | ARENA:LIQUIDITY_SWEEP | 1 | -1.000 | insuf. (1) | insuf. (1) | – | – | 1 observacoes alinhadas (minimo 30) |
| PAPEL | ARENA:PULLBACK | 1 | -1.000 | insuf. (1) | insuf. (1) | – | – | 1 observacoes alinhadas (minimo 30) |
| PAPEL | ARENA:REJEITADOS | 3 | -0.659 | insuf. (3) | insuf. (3) | – | – | 3 observacoes alinhadas (minimo 30) |
| PAPEL | ARENA:TREND_DAILY | 1 | -1.010 | insuf. (1) | insuf. (1) | – | – | 0 observacoes alinhadas (minimo 30) |
| PAPEL | FASES_LATERAL | 20 | -1.113 | insuf. (20) | insuf. (20) | – | – | 20 observacoes alinhadas (minimo 30) |
| PAPEL | H40 | 21 | -0.482 | insuf. (21) | insuf. (21) | – | – | 21 observacoes alinhadas (minimo 30) |
| PAPEL | H45 | 20 | -0.421 | insuf. (20) | insuf. (20) | – | – | 19 observacoes alinhadas (minimo 30) |
| — | H46 | 0 | – | – | – | – | – | sem operacoes fechadas publicadas |
| — | H52 | 0 | – | – | – | – | – | sem operacoes fechadas publicadas |
| — | H53 | 0 | – | – | – | – | – | sem operacoes fechadas publicadas |
| — | H57 | 0 | – | – | – | – | – | sem operacoes fechadas publicadas |
| — | H58 | 0 | – | – | – | – | – | sem operacoes fechadas publicadas |
| — | H59 | 0 | – | – | – | – | – | sem operacoes fechadas publicadas |

## PBO (CSCV) — configuracoes avaliadas sobre os mesmos dados
- PAPEL (arena): 10 configuracoes, 13 dias (2026-10-07 a 2026-11-05)
  - S=8, embargo=0: insuficiente: 13 periodos para 8 blocos (minimo 5 por bloco)
  - S=8, embargo=3: insuficiente: 13 periodos para 8 blocos (minimo 11 por bloco)
  - S=10, embargo=0: insuficiente: 13 periodos para 10 blocos (minimo 5 por bloco)
  - S=16, embargo=0: insuficiente: 13 periodos para 16 blocos (minimo 5 por bloco)
- BACKTEST H40 (todos vs so panico do mercado): 2 configuracoes, 287 dias (2024-12-12 a 2026-11-08)
  - S=8, embargo=0: PBO 0.46, prob. perda fora 0.06, degradacao -0.95, escolhida H40 (panico do mercado) — risco moderado de sobreajuste
  - S=8, embargo=3: PBO 0.46, prob. perda fora 0.06, degradacao -0.96, escolhida H40 (panico do mercado) — risco moderado de sobreajuste
  - S=10, embargo=0: PBO 0.35, prob. perda fora 0.05, degradacao -0.93, escolhida H40 (panico do mercado) — risco moderado de sobreajuste
  - S=16, embargo=0: PBO 0.21, prob. perda fora 0.03, degradacao -1.02, escolhida H40 (panico do mercado) — risco moderado de sobreajuste
- BACKTEST H46 (RSI<30 vs RSI<35): 2 configuracoes, 293 dias (2021-03-08 a 2026-10-25)
  - S=8, embargo=0: PBO 0.26, prob. perda fora 0.23, degradacao -0.82, escolhida H46 (RSI<30) — risco moderado de sobreajuste
  - S=8, embargo=3: PBO 0.24, prob. perda fora 0.24, degradacao -0.74, escolhida H46 (RSI<30) — risco moderado de sobreajuste
  - S=10, embargo=0: PBO 0.21, prob. perda fora 0.23, degradacao -0.86, escolhida H46 (RSI<30) — risco moderado de sobreajuste
  - S=16, embargo=0: PBO 0.17, prob. perda fora 0.22, degradacao -0.92, escolhida H46 (RSI<30) — selecao robusta fora da amostra

## Notas
- arena: 13 operacoes executadas em real ficaram fora da arena (contam como BYBIT_REAL)
- BACKTEST: H40, H45 e H46 a partir dos estudos registados (tools/quant_backtests.py), velas de 4H do ramo history

