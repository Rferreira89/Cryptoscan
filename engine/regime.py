"""Market Regime Engine. Usa varias variaveis do diario, nunca so uma.

Votos independentes: medias (uma familia), estrutura, posicao face a
EMA50. A forca (ADX) e a volatilidade (percentil do ATR) qualificam.
"""
BULLISH = {"BULL", "STRONG BULL"}
BEARISH = {"BEAR", "STRONG BEAR"}


def classify(a):
    """a = analise do timeframe diario."""
    if not a or not a.get("ok"):
        return {"regime": "UNCLEAR", "high_volatility": False,
                "why": ["sem análise diária"]}
    hv = a.get("atr_pctile") is not None and a["atr_pctile"] >= 95
    if a["structure"] == "UNCLEAR":
        return {"regime": "UNCLEAR", "high_volatility": hv,
                "why": ["estrutura indefinida"]}
    bull = [a["ema_trend"] == "UP", a["structure"] == "BULLISH",
            a["close"] > a["ema50"]]
    bear = [a["ema_trend"] == "DOWN", a["structure"] == "BEARISH",
            a["close"] < a["ema50"]]
    nb, ns = sum(bull), sum(bear)
    strong = a["adx"] is not None and a["adx"] >= 25
    why = [f"médias {a['ema_trend']}", f"estrutura {a['structure']}",
           f"ADX {a['adx']}", f"ATR percentil {a.get('atr_pctile')}"]
    if nb == 3:
        reg = "STRONG BULL" if strong else "BULL"
    elif ns == 3:
        reg = "STRONG BEAR" if strong else "BEAR"
    elif nb == 2 and ns == 0:
        reg = "BULL"
    elif ns == 2 and nb == 0:
        reg = "BEAR"
    elif a["adx"] is not None and a["adx"] < 20 and a["structure"] == "NEUTRAL":
        reg = "RANGE"
    else:
        reg = "NEUTRAL"
    if hv and reg in ("NEUTRAL", "RANGE"):
        reg = "HIGH VOLATILITY"
    return {"regime": reg, "high_volatility": hv, "why": why}
