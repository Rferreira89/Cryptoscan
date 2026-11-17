"""Geometria das saidas e simulacao com custos e funding.

Entrada na ABERTURA da vela seguinte ao sinal (com deslizamento). Na mesma vela, stop antes do alvo (conservador);
gap atravessa o stop -> sai na abertura. Saidas:
  fixa        stop k*ATR(tf_ref), alvo tp R, tempo maximo
  parcial     50% a 1R, o resto com stop na entrada e alvo tp R
  trailing    stop segue o extremo favoravel a k*ATR (dinamico por volatilidade), sem alvo
  inversao    sai no fecho da vela em que o sinal oposto da mesma familia dispara (alem de stop/tempo)
Custos por lado: comissao + deslizamento (em % do preco). Funding: soma das taxas que caem dentro da posicao
(LONG paga taxa positiva, SHORT recebe); fora do historico de funding usa o CENARIO pedido (sensibilidade).
Resultado em R (R = distancia de entrada ao stop inicial).
"""
COMISSAO = 0.05      # % por lado (X-Perps OKX, taker; cenarios de sensibilidade no motor)
DESLIZE = 0.05       # % por lado
RISCO_MIN_PCT = 0.2  # distancia minima ao stop em % do preco


def atr_serie(v, p=14):
    out = [None] * len(v)
    s = 0.0
    tr = [0.0] + [max(v[i]["h"] - v[i]["l"], abs(v[i]["h"] - v[i - 1]["c"]), abs(v[i]["l"] - v[i - 1]["c"]))
                  for i in range(1, len(v))]
    for i in range(1, len(v)):
        s += tr[i]
        if i > p:
            s -= tr[i - p]
        if i >= p:
            out[i] = s / p
    return out


def funding_entre(fund, t0, t1, lado, cenario_taxa=None):
    """Soma das taxas em (t0, t1] com o sinal do lado (custo positivo = paga). fund: [(t, taxa)] ordenado.
    Se o intervalo cai antes do primeiro registo, usa cenario_taxa por evento de 8 h (sensibilidade)."""
    sinal = 1.0 if lado == "LONG" else -1.0
    if fund and t0 >= fund[0][0] - 28800:              # o historico cobre o intervalo (eventos de 8 em 8 h)
        return sinal * sum(r for t, r in fund if t0 < t <= t1), "real"
    if cenario_taxa is None:
        return 0.0, "sem dados"
    n = max(0, int(t1 // 28800) - int(t0 // 28800))
    return sinal * n * cenario_taxa, "cenario"


def simular(v, i, lado, atr_ref, g, fund=None, cenario_taxa=None, inverso=None, comissao=COMISSAO, deslize=DESLIZE):
    """v: velas do tf do sinal; i: vela do sinal; atr_ref: ATR do tf de referencia no momento do sinal;
    g: {"tipo", "k", "tp", "hold"}; inverso: set de indices onde o sinal oposto dispara (saida por inversao)."""
    if i + 1 >= len(v) or not atr_ref or atr_ref <= 0:
        return None
    d = 1.0 if lado == "LONG" else -1.0
    e = v[i + 1]["o"] * (1 + d * deslize / 100)
    risco = g["k"] * atr_ref
    if risco < RISCO_MIN_PCT / 100 * e:       # stop mais perto do que 0,2% do preco: os custos dominam e o R explode
        return None                            # (17/11: um controlo com ATR quase nulo deu "vantagem" de 1,6e10 R)
    stop = e - d * risco
    alvo = e + d * g["tp"] * risco if g.get("tp") else None
    fim = min(len(v) - 1, i + g["hold"])
    if fim <= i:
        return None
    parte, realizado = 1.0, 0.0
    trail = stop
    extremo = e
    saida_i, motivo, px = None, None, None
    for j in range(i + 1, fim + 1):
        b = v[j]
        lo, hi = (b["l"], b["h"]) if d > 0 else (-b["h"], -b["l"])
        o = b["o"] * d
        st = trail * d
        if lo <= st:                                   # stop (ou gap atraves do stop)
            px = (min(st, o) if o <= st else st) * d
            saida_i, motivo = j, "stop"
            break
        if g["tipo"] == "parcial" and parte == 1.0 and hi >= (e + d * risco) * d:
            realizado += 0.5 * 1.0
            parte = 0.5
            trail = e                                   # resto com stop na entrada
            st = trail * d
        if alvo is not None and hi >= alvo * d:
            px, saida_i, motivo = alvo, j, "alvo"
            break
        if g["tipo"] == "trailing":
            extremo = max(extremo * d, hi) * d
            trail = extremo - d * g["k"] * atr_ref
        if inverso and j in inverso:
            px, saida_i, motivo = b["c"], j, "inversao"
            break
    if px is None:
        px, saida_i, motivo = v[fim]["c"], fim, "tempo"
    px_s = px * (1 - d * deslize / 100)
    bruto = realizado + parte * d * (px_s - e) / risco
    t0, t1 = v[i + 1]["t"], v[saida_i]["t"] + (v[1]["t"] - v[0]["t"])
    fr, fonte = funding_entre(fund or [], t0, t1, "LONG" if d > 0 else "SHORT", cenario_taxa)
    custo_pct = 2 * comissao + 100 * fr
    custos_r = e * custo_pct / 100 / risco
    return {"r": bruto - custos_r, "bruto_r": bruto, "custos_r": custos_r, "funding_pct": round(100 * fr, 5),
            "funding_fonte": fonte, "saida": motivo, "velas": saida_i - i, "t_saida": t1,
            "custo_sobre_risco": round(e * 2 * comissao / 100 / risco, 4)}


GEOMETRIAS_BASE = [{"tipo": "fixa", "k": k, "tp": tp, "hold": None} for k in (1.0, 1.5, 2.0, 2.5, 3.0)
                   for tp in (1.0, 1.5, 2.0, 3.0)] + \
                  [{"tipo": "parcial", "k": k, "tp": 2.0, "hold": None} for k in (1.5, 2.5)] + \
                  [{"tipo": "trailing", "k": k, "tp": None, "hold": None} for k in (1.5, 2.5, 3.0)]
