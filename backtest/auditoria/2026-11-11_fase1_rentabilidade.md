# Fase 1 — Rentabilidade das estratégias existentes (11/11/2026, 21h)

Só R, nunca dinheiro. Backtest, arena, papel, sombra e real nunca somados. Reserva 2026-05-08..11-08 contaminada:
o que se mede lá aparece à parte e não serve para validar.
Ferramentas: `tools/auditoria_rentabilidade.py`, `tools/h46_todas_moedas.py`. Testes: `tests/test_auditoria_rentabilidade.py`.
Resultados: `rentabilidade_2026-11-11.json`, `h46_sobrevivencia_2026-11-11.json`, `funil_2026-11-11_21h.json`.

## 1. Reconciliação (21:09 UTC)
- main remoto = 428c5a0. Desde 4937677 só há commits de agentes (vigia, evolucao, investigacao, H15 rejeitada); sem
  diferença em engine, config, okx_config, workflows, okx_exec ou okx_agente.
- OKX: real ligado; H40 `panico_real` desligado; H46 `recuo_real` ligado a 1%; teto de risco aberto 3%; 0 posições.
- Bybit: `real_autorizados` vazio; 0 posições; 27 estratégias suspensas pelo critério mensal; 4 desligadas.
- Nenhuma divergência entre relatórios e estado efetivo encontrada nesta passagem.
  - As 3 operações reais de pânico isolado (PENGU, CASHCAT, PARTI) batem com o histórico do `okx_config`.
  - Em 08/11 11:10 foram postos `so_mercado` false e `panico_real` true (OK do Rui).
  - Em 10/11 voltou `so_mercado` true (04:14) e `panico_real` false (04:48).
  - HUMA foi uma ordem adotada.

## 2. Classificação (61 estratégias)
- A: 0. B: 0. D (classe): 0. E: 3. C: 58. Bandeira D: 1.
- Regras escritas em `classificar()`. Backtest sozinho nunca chega a A. A arena só conta para B se o ano inteiro e os
  últimos 30 dias forem líquidos positivos, acima do acaso, e NÃO concentrados (≥ 10 dias distintos em 45).

| Corretora | Estratégia | Classe | Razão principal |
|---|---|---|---|
| OKX | H40 pânico do MERCADO | C + bandeira D | +0,31R/operação no backtest, mas −0,01R por dia (63 dias); 83% do R vem de 3 dias. Com o teto real de 3 abertas: +0,09R. 5 de 9 ordens reais canceladas sem executar. |
| OKX | H40 pânico ISOLADO | C | Papel −0,55R (20); real 4/4 no stop. Bem desligado. |
| OKX | H46 recuo RSI<30 (real a 1%) | C | Por dia +0,10R só nas moedas vivas; com as 185 retiradas +0,02R; com teto de 3 abertas −0,03R. 0 sinais desde 04/11 (regime). |
| OKX | TF-SHORT U2 | C | 0 fechadas no registo `conta`; o backtest citado não tem operações públicas para auditar. |
| OKX | MACRO (ações, índices, matérias-primas) | E | Papel 12 fechadas, média −6,85% (em %). |
| Bybit | H45 pânico (custos Bybit) | E | Papel −0,44R (21); backtest por dia −0,07R. |
| Bybit | FASES_LATERAL | E | Papel −1,11R, as 20 operações num só dia. |
| Bybit | 54 lutadores da arena | C | Nenhum passa as regras. Família Bounce positiva em `subida` (ex.: X30 +0,55R, 35 operações) mas só 6 dias. Shorts positivos em `queda` com limite inferior por dia < 0. |

## 3. Funil
- OKX: 289 contratos → 29 sinais H40 (25 isolados, 4 de mercado) → 6 colocados em real, papel −0,69R.
  - Rejeitados por H40 suspensa: 17, papel −0,89R (12 fechadas). Rejeição correta.
  - Rejeitados por pânico isolado: 4, +0,33R. Sem X-Perp: 1, +2,0R. Mínimo: 1. Amostra pequena.
  - H46: 0 sinais (BTC não está acima da SMA50 a subir).
- Execução OKX:
  - 9 ordens reais: 4 preenchidas (todas de pânico isolado, todas no stop); 5 de pânico de mercado canceladas sem executar.
  - Em 2 das canceladas o papel registou preenchimento (TRUMP +0,30R, WLD −0,42R).
  - O papel preenche ao TOCAR no limite (`low <= lim`); o real precisa de negócio no preço e chega cerca de 7 minutos depois da abertura da vela.
  - Seleção adversa: as limites só preencheram onde o preço continuou a cair. O papel da H40 está otimista.
- Bybit: 967 pares vistos → 68 elegíveis → 53 com dados válidos → 0 sinais.
  - Regime: 32 moedas em BEAR ou STRONG BEAR, onde nenhuma estratégia ativa se aplica.
  - Volume ou spread da Bybit UE: 14.
- Promoções perdidas na Bybit (100; 89 SHORT_TURTLE):
  - Teste substituto de 72 h: shorts rejeitados por `plano` +2,1% líquido (33 sinais, 6 dias).
  - Rejeitados por `liquidez` e `diversificação`: cerca de 0%.
  - Inconclusivo (6 dias); o registo não guarda stop nem objetivo.

## 4. Melhorias testadas (walk-forward)
- Método: metade dos dias antes da reserva para desenhar, a outra metade para validar. Holm por família.
- Filtros fixos antes de ver os resultados: regime BTC, stop largo (≥ 12%), stop curto (< 8%), dias com ≥ 3 sinais, dias com 1 sinal.
- Só um passou: H46 RSI<35 com stop largo, nas moedas vivas (validação +0,42R por dia, IC90 [0,15; 0,68]; Holm 0,034).
- **Rejeitado:** com as moedas retiradas incluídas, o mesmo filtro dá −0,01R por dia na validação. Era viés de sobrevivência.
- Teto de posições:
  - H40 de mercado: 0,35R por operação sem teto; 0,09R com teto de 3; 0,03R com teto de 1.
  - H46: cerca de 0 com qualquer teto.
  - A vantagem histórica da H40 vive em tomar todos os sinais dos poucos dias de colapso. Com o teto e os mínimos reais quase não é capturável.

## 5. Bybit vs OKX
- Custo em R por cada 0,1% extra: cerca de 0,013R (H40, stop mediano 8,6%) e 0,016R (H46, stop 7,1%).
- A H46 RSI<35 anula-se com +0,18% de custo. A H40 de mercado aguenta +2,5% (só sem teto).
- A mesma H40 com custos Bybit (H45) perde por dia. Pânico só faz sentido na OKX, e mesmo lá não está demonstrado por acontecimento.
- Os custos reais medidos na OKX (4 operações) foram 0,005 a 0,007R por operação, abaixo do assumido.

## 6. Sombra
- MOMENTO_RISCO_ON e QUEBRA_MINIMO_SHORT estão pré-registadas, com início a 12/11. Ainda 0 acontecimentos.
- Sinais bloqueados:
  - OKX: o papel H40 segue todos os sinais.
  - Bybit: `paper_shadow` só segue o limite de simultâneas (3 fechadas, −0,66R, 1 dia).
  - Bybit: `promo_lost` sem resultado. Passa a ser medido por `bloqueados_bybit()` na Fase 2.
