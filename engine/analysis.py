"""Fase 2: junta indicadores, estrutura e price action por timeframe.

Descritivo. Nao gera LONG/SHORT - isso so existe depois da Strategy
Engine, do Risk Engine e do backtesting (Fases 4 e 5).

Anti-redundancia: EMA50/EMA200 e preco vs EMA200 medem todos tendencia e
contam como UMA familia ("trend"), nunca como confirmacoes independentes.
"""
from . import indicators as I
from . import structure as S

MIN_BARS = 210


def _r(v, nd=6):
    return None if v is None else round(v, nd)


def timeframe(c):
    if len(c) < MIN_BARS:
        return {"ok": False, "reason": f"histórico insuficiente ({len(c)}/{MIN_BARS})"}
    close = [x["c"] for x in c]
    px = close[-1]
    e20, e50, e200 = (I.ema(close, n)[-1] for n in (20, 50, 200))
    a, r, d = I.atr(c)[-1], I.rsi(close)[-1], I.adx(c)[-1]
    if px > e200 and e50 > e200:
        ema_trend = "UP"
    elif px < e200 and e50 < e200:
        ema_trend = "DOWN"
    else:
        ema_trend = "MIXED"
    # percentil do ATR% atual face as ultimas 200 velas (regime de volatilidade)
    atr_s = I.atr(c)
    hist = [atr_s[i] / close[i] for i in range(len(c) - 200, len(c))
            if atr_s[i] is not None]
    atr_pctile = round(100 * sum(1 for h in hist if h <= hist[-1]) / len(hist))
    st = S.analyse(c)
    return {"ok": True, "close": px, "ema20": _r(e20), "ema50": _r(e50),
            "ema200": _r(e200), "ema_trend": ema_trend,
            "trend_strength": "STRONG" if d >= 25 else "WEAK" if d < 20
            else "MODERATE",
            "adx": _r(d, 1), "rsi": _r(r, 1), "atr_pct": _r(a / px * 100, 2),
            "atr": _r(a, 10), "atr_pctile": atr_pctile,
            "dist_ema200_pct": _r((px / e200 - 1) * 100, 1),
            "structure": st["trend"], "sequence": st["sequence"],
            "swing_high": st["last_high"], "swing_low": st["last_low"],
            "event": st["event"], "patterns": S.patterns(c)}


def mtf_conflict(hi, lo):
    """Conflito entre o diario (hi) e o 4H (lo). None se nao houver."""
    if not (hi and lo and hi["ok"] and lo["ok"]):
        return None
    up_hi = hi["ema_trend"] == "UP" or hi["structure"] == "BULLISH"
    dn_hi = hi["ema_trend"] == "DOWN" or hi["structure"] == "BEARISH"
    if up_hi and not dn_hi and lo["structure"] == "BEARISH":
        return "4H bearish contra 1D bullish"
    if dn_hi and not up_hi and lo["structure"] == "BULLISH":
        return "4H bullish contra 1D bearish"
    if up_hi and dn_hi:
        return "1D: médias e estrutura discordam"
    return None


def multi(candles_by_tf):
    """candles_by_tf: {'1d': [...], '4h': [...]} ja validadas."""
    out = {tf: timeframe(c) for tf, c in candles_by_tf.items()}
    out["mtf_conflict"] = mtf_conflict(out.get("1d"), out.get("4h"))
    return out
