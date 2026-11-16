# Pré-registo — LONG_TENDENCIA_1H
**Data:** 2026-11-16 (antes de qualquer teste)
**Decisão do Rui:** programa mais agressivo com long + short em 1H.

O ATAQUE_1H long (recuo à EMA20 com RSI 35-55) falhou (R médio ≈ -0,26). Esta é uma hipótese **nova**, com lógica diferente.

---

## LONG_TENDENCIA_1H (só compras, 1H)

**Lógica:** continuação de tendência forte. Em vez de comprar o recuo, compra o rompimento de máximo recente com volume, dentro de um contexto 4H claramente de alta.

**Regra (só compras):**
- Contexto 4H: EMA20 > EMA50 **e** fecho da última 4H acima da EMA50 **e** EMA20 a subir (fecho actual > fecho de 4 velas atrás).
- Gatilho 1H: fecho acima do máximo das últimas 5 velas de 1H.
- Volume da vela do sinal ≥ V × média de volume das últimas 20 velas de 1H.
- RSI14 de 1H entre 50 e 70 (força sem sobrecompra extrema).
- Entrada na abertura da vela 1H seguinte.
- Stop: mínimo das últimas 4 velas 1H − 0,15 ATR14 1H; **só opera se (entrada−stop)/entrada ≥ 1,2%**.
- Objetivo único a k R.
- Saída obrigatória ao fim de H horas.
- Máx. 1 posição por moeda.

**Grelha (4, escrita antes de testar):**
- k ∈ {1,5 ; 2,0}
- H ∈ {8 ; 16} horas
- V ∈ {1,5 ; 2,0}   ← volume mínimo

(4 combinações principais; V pode ser fixado a 1,5 na primeira passagem se o tempo apertar.)

**Dados:** ramo `okx-1h` (1H) + `history` (4H).
**Critérios:** seis de sempre + acaso ≥ percentil 90. Veredicto máximo: PARA PAPEL.
**Venues:** Bybit e OKX, mesma regra de sinal.

Não activar em papel nem real antes de o research devolver R médio > 0 e percentil ≥ 90.
