"""Motor central de oportunidades para papel (investigacao-agressivo).

Reune sinais, classifica por qualidade estimada e devolve os melhores.
Nao abre ordens reais. Nao altera risco nem capital de producao.

Score simples (0-100):
- regime alinhado: +30
- R/R >= 1.5: +25
- volume relativo alto: +15
- stop distance razoavel (0.8-3%): +15
- estrategia com historico positivo em papel: +15
"""


def _rr(sig, price):
    try:
        stop = float(sig.get("stop") or 0)
        tp = (sig.get("tp") or [0])[0]
        tp = float(tp)
        px = float(price)
        if stop <= 0 or tp <= 0 or px <= 0:
            return 0.0
        risk = abs(px - stop)
        reward = abs(tp - px)
        return reward / risk if risk > 0 else 0.0
    except Exception:
        return 0.0


def score(sig, price, fase=None, side=None, strat_r=None):
    """Devolve (score, detalhes)."""
    s = 0
    det = {}
    side = (side or sig.get("side") or "LONG").upper()
    # regime
    from . import regime_select
    if regime_select.prefer(fase, side):
        s += 30
        det["regime"] = 30
    # R/R
    rr = _rr(sig, price)
    det["rr"] = round(rr, 2)
    if rr >= 2.0:
        s += 25
    elif rr >= 1.5:
        s += 18
    elif rr >= 1.0:
        s += 10
    # stop distance
    try:
        dist = abs(float(price) - float(sig.get("stop") or 0)) / float(price)
        det["stop_pct"] = round(dist * 100, 2)
        if 0.008 <= dist <= 0.03:
            s += 15
        elif dist > 0:
            s += 5
    except Exception:
        pass
    # historico da estrategia (opcional)
    if strat_r is not None and strat_r > 0:
        s += 15
        det["hist"] = 15
    return min(s, 100), det


def rank(opps, top_n=8):
    """opps: lista de dicts com keys sig, price, fase, side, strat, strat_r.
    Devolve os top_n ordenados por score."""
    scored = []
    for o in opps:
        sc, det = score(o.get("sig") or {}, o.get("price"),
                        o.get("fase"), o.get("side"), o.get("strat_r"))
        scored.append(dict(o, score=sc, detail=det))
    scored.sort(key=lambda x: -x["score"])
    return scored[:top_n]
