# Pré-registo — SHORT_SOBRECOMPRA e ATAQUE_1H
**Data:** 2026-11-15 (antes de qualquer teste)
**Decisão do Rui:** programa mais agressivo, mais operações, long+short, Bybit e OKX.

Não testar antes do histórico estar actualizado e de CAP_MERCADO_V2 / BOUNCE_LARGO estarem tratados no papel.

---

## 1. SHORT_SOBRECOMPRA (4H, só vendas)

**Lógica:** espelho do Bounce. Em tendência de queda ou lateral, subidas rápidas levam o RSI de 4H a sobrecompra; a primeira vela de rejeição marca o fim da pressão compradora.

**Regra (só vendas):**
- BTC abaixo da SMA200 diária **ou** regime lateral (basta uma).
- RSI14 de 4H acima de X numa das últimas 3 velas.
- Vela de 4H fecha abaixo do mínimo da anterior com RSI a descer.
- Volume da vela do sinal ≥ V × média de 20.
- Entrada na abertura seguinte (short).
- Stop: máximo da subida + 0,1 ATR14 (mínimo 1,25 ATR de distância).
- Objetivos: 50% na SMA20 de 4H (por baixo), resto no mínimo das 42 velas anteriores.
- Stop na entrada depois do 1.º objetivo.
- Saída ao fim de 5 dias se nada for atingido.

**Grelha (4, escrita antes de testar):**
- X ∈ {70, 75}
- V ∈ {2,0 ; 2,5}
- Sem funding na primeira passagem.

**Critérios:** seis de sempre + acaso ≥ percentil 90. Veredicto máximo: PARA PAPEL.
**Venues:** mesma regra em Bybit e OKX (execução por venue).

---

## 2. ATAQUE_1H (long + short, 1H)

**Lógica:** recuo curto a favor da tendência de 4H, saída rápida (12–24 h). Não é scalper de minutos. Stop com distância mínima ≥ 1,2% para os custos (~0,7% ida e volta) não comerem o R.

### 2.1 Long
- Contexto 4H: EMA20 > EMA50; fecho da última 4H fechada acima da EMA50.
- BTC: acima da SMA200 **ou** regime não de queda forte.
- Gatilho 1H: mínimo da vela ≤ EMA20 1H e fecha acima; RSI14 1H entre 35 e 55.
- Entrada na abertura da vela 1H seguinte.
- Stop: mínimo das últimas 3 velas 1H − 0,2 ATR14 1H; **só opera se (entrada−stop)/entrada ≥ 1,2%**.
- Objetivo único a k R.
- Saída obrigatória ao fim de H horas.
- Máx. 1 posição por moeda; no máximo 2 posições no total (long+short juntos).

### 2.2 Short (espelho)
- Contexto 4H: EMA20 < EMA50; fecho da última 4H fechada abaixo da EMA50.
- BTC: abaixo da SMA200 **ou** regime não de subida forte.
- Gatilho 1H: máximo da vela ≥ EMA20 1H e fecha abaixo; RSI14 1H entre 45 e 65.
- Entrada na abertura seguinte (short).
- Stop: máximo das últimas 3 velas 1H + 0,2 ATR14 1H; **só opera se (stop−entrada)/entrada ≥ 1,2%**.
- Objetivo único a k R; saída em H horas; mesmos limites de posição.

**Grelha (4 por lado, escrita antes de testar):**
- k ∈ {1,5 ; 2}
- H ∈ {12 ; 24} horas

Long e short contam como **duas hipóteses gémeas** (mesmo desenho de regra, lados opostos) para o contador de testes.

**Dados:** ramo `history`, pasta `1h/` + 4H na raiz. Acaso com velas de 1H (±360 velas ≈ ±15 dias).

**Critérios:** seis de sempre + acaso ≥ percentil 90 + reportar custo médio por operação em R.
Veredicto máximo: PARA PAPEL.
**Venues:** Bybit e OKX, mesma regra de sinal; execução e custos por venue.

---

## Ordem de teste (após CAP/BOUNCE no papel)

1. SHORT_SOBRECOMPRA (4 combinações)
2. ATAQUE_1H long (4)
3. ATAQUE_1H short (4)

Não misturar com optimização na reserva. Qualquer ≥ p90 → PARA PAPEL na mesma corrida (regra 2026-11-14).
Critério da conta só após ≥ 25 operações em papel.
