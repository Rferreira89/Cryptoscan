"""Indice do mercado de 0 a 100 (22/10, pedido do Rui: "um indice de mercado
de alta ou baixa"). 0 = baixa forte, 50 = lateral, 100 = alta forte.

Componentes (so dados fechados, sem afinacao a resultados):
  - tendencia do BTC (40%): fecho acima/abaixo das medias de 50 e 200 dias e
    a media de 50 acima/abaixo da de 200;
  - momento do BTC (30%): retorno de 30 dias entre -20% e +20%;
  - amplitude (30%): % das moedas analisadas com o fecho diario acima da
    propria media de 50 dias.
Diz tambem o que falta para a regra de fase do programa (engine/arena.market_regime)
mudar para subida ou queda. So informa: a fase que decide continua a ser a regra.
"""
DAY = 86400


def _clip(x, a, b):
    return max(a, min(b, x))


def rotulo(v):
    return ("baixa forte" if v < 20 else "baixa" if v < 40 else "lateral" if v <= 60 else
            "alta" if v <= 80 else "alta forte")


def calcular(btc_d, diarios=None):
    d = [x for x in btc_d or [] if x]
    if len(d) < 200:
        return None
    c = [x["c"] for x in d]
    s50, s200, r30 = sum(c[-50:]) / 50, sum(c[-200:]) / 200, c[-1] / c[-31] - 1
    pts = (1 if c[-1] > s200 else -1) + (1 if c[-1] > s50 else -1) + (1 if s50 > s200 else -1)
    tend = (pts + 3) / 6 * 100
    mom = (_clip(r30, -0.2, 0.2) + 0.2) / 0.4 * 100
    acima = tot = 0
    for a, cd in (diarios or {}).items():
        if not cd or len(cd) < 50:
            continue
        cc = [x["c"] for x in cd]
        tot += 1
        acima += cc[-1] > sum(cc[-50:]) / 50
    amp = acima / tot * 100 if tot >= 10 else None
    v = 0.4 * tend + 0.3 * mom + 0.3 * (amp if amp is not None else 50)
    fase = ("subida" if c[-1] > s50 > s200 and r30 > 0.08 else
            "queda" if c[-1] < s50 < s200 and r30 < -0.08 else "lateral")
    pct = lambda x: round(x * 100, 1)
    falta = {
        "subida": [{"regra": "BTC acima da média de 50 dias", "ok": c[-1] > s50, "dist_pct": pct(s50 / c[-1] - 1)},
                   {"regra": "média de 50 acima da de 200", "ok": s50 > s200, "dist_pct": pct(s200 / s50 - 1)},
                   {"regra": "BTC a subir mais de 8% em 30 dias", "ok": r30 > 0.08, "dist_pct": pct(0.08 - r30)}],
        "queda": [{"regra": "BTC abaixo da média de 50 dias", "ok": c[-1] < s50, "dist_pct": pct(1 - s50 / c[-1])},
                  {"regra": "média de 50 abaixo da de 200", "ok": s50 < s200, "dist_pct": pct(s50 / s200 - 1)},
                  {"regra": "BTC a cair mais de 8% em 30 dias", "ok": r30 < -0.08, "dist_pct": pct(r30 + 0.08)}]}
    return {"valor": round(v), "rotulo": rotulo(v), "fase_regra": fase,
            "componentes": {"tendencia": round(tend), "momento": round(mom),
                            "amplitude": None if amp is None else round(amp), "moedas": tot},
            "btc": {"preco": c[-1], "media50": round(s50, 2), "media200": round(s200, 2), "r30_pct": pct(r30)},
            "falta": falta}


def historico(state, ind, now, passo=3600, dias=60):
    """Guarda um valor por hora (60 dias) para o grafico."""
    if not ind:
        return state.get("indice_hist") or []
    h = state.setdefault("indice_hist", [])
    if not h or now - h[-1][0] >= passo:
        h.append([int(now), ind["valor"]])
    del h[:-int(dias * DAY / passo)]
    return h
