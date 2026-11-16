# Pré-registo — LONG_BOUNCE_1H
**Data:** 2026-11-16 (antes de qualquer teste)
**Decisão do Rui:** programa mais agressivo com long + short.

As lógicas anteriores de long em 1H falharam:
- ATAQUE_1H long (recuo à EMA20 + RSI 35-55): R ≈ -0,26
- LONG_TENDENCIA_1H (rompimento + volume): R ≈ -0,22

Esta é uma hipótese **nova**: bounce de curto prazo dentro de um contexto 4H de alta.

---

## LONG_BOUNCE_1H (só compras, 1H)

**Lógica:** em tendência de alta de 4H, comprar o primeiro recuo forte em 1H (RSI baixo + fecho acima da EMA20 de 1H).

**Regra (só compras):**
- Contexto 4H: EMA20 > EMA50 **e** fecho da última 4H acima da EMA50.
- Gatilho 1H: RSI14 de 1H ≤ 40 numa das últimas 2 velas **e** a vela actual fecha acima da EMA20 de 1H.
- Volume da vela do sinal ≥ 1,0 × média de volume das últimas 20 velas de 1H (opcional, testar com e sem).
- Entrada na abertura da vela 1H seguinte.
- Stop: mínimo das últimas 3 velas 1H − 0,2 ATR14 1H; **só opera se (entrada−stop)/entrada ≥ 1,2%**.
- Objetivo único a k R.
- Saída obrigatória ao fim de H horas.
- Máx. 1 posição por moeda.

**Grelha (4, escrita antes de testar):**
- k ∈ {1,5 ; 2,0}
- H ∈ {6 ; 12} horas

**Dados:** ramo `okx-1h` (1H) + `history` (4H).
**Critérios:** seis de sempre + acaso ≥ percentil 90. Veredicto máximo: PARA PAPEL.
**Venues:** Bybit e OKX, mesma regra de sinal.

Não activar em papel nem real antes de o research devolver R médio > 0 e percentil ≥ 90.
