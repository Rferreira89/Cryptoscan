# Fila de hipóteses para dados novos (10/11/2026)

Fila priorizada para o caçador noturno. Regras do Rui: cada hipótese é registada em
`backtest/hipoteses_novas.json` ANTES de ver dados e só é avaliada com dados posteriores ao registo
(`tools/recolha_dados.py → dados_para_avaliar`); no máximo uma por noite; sem variantes cosméticas; resultados
negativos ficam registados. Nada daqui vai a papel ou a real sem autorização do Rui.

Já registadas pelo caçador: H52 (short na queda com OI a subir, em descida) e H53.

| # | Lado | Regime | Hipótese | Razão económica | Dados (ramo dados-novos) |
|---|---|---|---|---|---|
| 1 | LONG | subida ou lateral | **Squeeze de shorts**: moeda acima da média de 20 dias com financiamento do X-Perp negativo (shorts a pagar) e OI a subir 2 dias seguidos → long D+1, saída D+3, stop 1,5× amplitude média | posicionamento vendedor apertado numa tendência que sobe: os shorts são forçados a comprar. É o contrário da H44 (excesso de longs), não uma variante dela | c, fund_xperp_24h, oi_usd_global |
| 2 | LONG | capitulação | **Desalavancagem do mercado todo**: mediana do dia ≤ −6% com OI agregado a cair ≥ 8% e financiamento médio negativo → long D+1 nas 5 maiores por volume, 3 dias | o pânico que limpa a alavancagem (liquidações) esgota os vendedores forçados; separa o pânico de desalavancagem (que a H40 não distingue) do pânico de notícias | c, volume_usd, oi_usd_global, fund_xperp_24h |
| 3 | SHORT | descida | **Subida sem dinheiro novo**: com o BTC abaixo da média de 50 dias, altcoin sobe ≥ 10% em 3 dias com OI a CAIR e financiamento positivo → short D+1, 3 dias | subida feita de shorts a fechar (OI a cair) e não de compradores novos não tem combustível em mercado de descida | c, oi_usd_global, fund_xperp_24h |
| 4 | — | todos | **Filtro "fora do universo validado" do TF-SHORT** (corta 67 sinais, resultado desconhecido): medir os sinais fora do universo pelo livro de sinais do papel quando fecharem | verificar se o filtro tem justificação estatística ao vivo, sem o remover | okx_tfshort.json (sinais) |

Não priorizado (já chumbado ou sem razão nova): perseguir quebras de máximos, RSI2, mechas, rotação de momento,
regresso à média de modelos de previsão (Kronos K1, rejeitado em 10/11), pânico isolado (H40 isolado: −0,42R ao vivo).

## Estado (10/11, 06:30 UTC)
- #1 → **H57**, #2 → **H58**, #3 → **H59**: registadas em `backtest/hipoteses_novas.json` com o código
  `backtest/estudos/novos/fila_1011.py` ANTES de qualquer avaliação. Hoje: 0 de 30 operações (os dados posteriores ao
  registo começam a 11/11). Nenhum resultado em dados anteriores foi calculado.
- #2 é diferente da H53 do caçador (recuo moderado de UMA moeda em mercado a subir); a H58 é o dia de pânico do
  mercado todo com desalavancagem.
- #4: medição feita em `tools/rejeicoes.py` (sinais independentes; R provisório a preço de mercado enquanto abertos).
