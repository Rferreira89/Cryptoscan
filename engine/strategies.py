"""Strategy Engine. So compras em spot (Bybit UE, sem alavancagem).

Cada estrategia devolve None (nao se aplica) ou um setup:
  {strategy, state: READY|WAITING, entry: [min, max], stop, trigger,
   notes: [...], rejects: [...]}
ou {"strategy":..., "rejected": motivo} quando o padrao existe mas falha um
filtro (falso sinal). READY = condicoes de entrada cumpridas na ultima
vela fechada de 4H. WAITING = vigiar; nunca gera entrada antecipada.

Nao implementadas nesta fase (ficam para depois do primeiro backtest):
Volatility Expansion/Contraction e Momentum puro. Trend Following esta
coberta por PULLBACK e BREAKOUT; Reversal por LIQUIDITY_SWEEP.

NENHUMA destas estrategias esta validada estatisticamente.
"""
from math import floor, log10

from .regime import BULLISH, BEARISH


def px_str(x):
    """Preco com 5 algarismos significativos, sem notacao cientifica."""
    if not x or x <= 0:
        return str(x)
    dec = max(0, 4 - floor(log10(x)))
    out = f"{x:.{dec}f}"
    return out.rstrip("0").rstrip(".") if "." in out else out


def _bull_trigger(c4, a4):
    last, prev = c4[-1], c4[-2]
    if "ENGULFING_BULL" in a4["patterns"] or "PIN_BAR_BULL" in a4["patterns"]:
        return True
    return last["c"] > last["o"] and last["c"] > prev["h"]


def pullback(c4, a4, a1, reg):
    if reg["regime"] not in BULLISH or a4["ema_trend"] == "DOWN":
        return None
    atr, px = a4["atr"], a4["close"]
    hi_zone, lo_zone = max(a4["ema20"], a4["ema50"]), min(a4["ema20"], a4["ema50"])
    recent_high = max(x["h"] for x in c4[-20:])
    if recent_high - px < 1.5 * atr:
        return None                                  # nao houve recuo
    if not (lo_zone - 0.5 * atr <= px <= hi_zone + 0.5 * atr):
        return None                                  # fora da zona de valor
    if a4["rsi"] > 62:
        return {"strategy": "PULLBACK", "rejected": "RSI 4H ainda elevado"}
    low5 = min(x["l"] for x in c4[-5:])
    stop = low5 - 0.3 * atr
    s = {"strategy": "PULLBACK", "stop": stop,
         "notes": [f"recuo de {round((recent_high - px) / atr, 1)} ATR até as "
                   "médias de 4H em tendência diaria de subida"]}
    if _bull_trigger(c4, a4):
        s.update(state="READY", entry=[px - 0.3 * atr, px],
                 trigger="vela de 4H confirmou a retoma")
    else:
        # entrada prevista = nivel do gatilho; o plano e indicativo ate la
        s.update(state="WAITING", entry=[px, c4[-1]["h"]],
                 trigger=f"fecho de 4H acima de {px_str(c4[-1]['h'])}")
    return s


def breakout(c4, a4, a1, reg, rvol_at):
    ev = a4["event"]
    if not ev or ev["direction"] != "UP" or ev["bars_ago"] > 6:
        return None
    if reg["regime"] in BEARISH:
        return {"strategy": "BREAKOUT",
                "rejected": "quebra em alta contra regime diário de descida"}
    atr, px, level = a4["atr"], a4["close"], ev["level"]
    j = len(c4) - 1 - ev["bars_ago"]
    rv = rvol_at(j)
    if px < level:
        return {"strategy": "BREAKOUT", "rejected": "FAKE BREAKOUT: preço "
                "voltou a fechar abaixo do nivel quebrado"}
    if rv is not None and rv < 1.2:
        return {"strategy": "BREAKOUT", "rejected":
                f"LOW VOLUME BREAKOUT: volume da quebra {rv}x a média"}
    zone = [level, level + 0.4 * atr]
    s = {"strategy": "BREAKOUT", "stop": level - 1.0 * atr, "entry": zone,
         "notes": [f"{ev['type']} em alta há {ev['bars_ago']} velas de 4H, "
                   f"volume {rv}x a média"]}
    retested = any(x["l"] <= zone[1] for x in c4[j + 1:]) and px >= level
    if px > level + 1.5 * atr:
        s.update(state="WAITING", notes=s["notes"] + ["MOVE EXTENDED"],
                 trigger=f"recuo até {px_str(zone[0])}-{px_str(zone[1])} (reteste)")
    elif retested and px <= zone[1] + 0.6 * atr and c4[-1]["c"] > c4[-1]["o"]:
        s.update(state="READY", trigger="reteste do nivel quebrado aguentou")
    else:
        s.update(state="WAITING",
                 trigger=f"reteste de {px_str(zone[0])}-{px_str(zone[1])} com fecho "
                         "de 4H positivo")
    return s


def sweep(c4, a4, a1, reg):
    sw = a4["liquidity"] and a4["liquidity"]["sweep"]
    if not sw or sw["side"] != "LOW" or sw["bars_ago"] > 6:
        return None
    if reg["regime"] == "STRONG BEAR":
        return {"strategy": "LIQUIDITY_SWEEP",
                "rejected": "sweep de fundo em regime de descida forte"}
    atr, px = a4["atr"], a4["close"]
    cs = c4[len(c4) - 1 - sw["bars_ago"]]
    s = {"strategy": "LIQUIDITY_SWEEP", "stop": cs["l"] - 0.3 * atr,
         "notes": [f"sweep do fundo {px_str(sw['level'])} há {sw['bars_ago']} "
                   "velas de 4H"]}
    if not sw["confirmed"]:
        s.update(state="WAITING", entry=[cs["c"], cs["h"]],
                 trigger=f"fecho de 4H acima de {px_str(cs['h'])} (confirmação)")
    elif px > cs["h"] + 1.0 * atr:
        s.update(state="WAITING", entry=[cs["c"], cs["h"]],
                 notes=s["notes"] + ["MOVE EXTENDED"],
                 trigger=f"recuo até {px_str(cs['h'])}")
    else:
        s.update(state="READY", entry=[px - 0.3 * atr, px],
                 trigger="sweep confirmado por fecho acima da vela do sweep")
    return s


def range_reversion(c4, a4, a1, reg):
    if reg["regime"] != "RANGE" or not a1["swing_high"] or not a1["swing_low"]:
        return None
    lo, hi, px = a1["swing_low"], a1["swing_high"], a4["close"]
    width = hi - lo
    if width < 4 * a1["atr"] or not lo < px < hi:
        return None
    if px > lo + 0.25 * width:
        return None                       # so interessa o quarto inferior
    s = {"strategy": "RANGE", "stop": lo - 0.5 * a1["atr"],
         "targets": [lo + width / 2, hi],
         "notes": [f"preço no quarto inferior do range diário "
                   f"{px_str(lo)}-{px_str(hi)}"]}
    if _bull_trigger(c4, a4):
        s.update(state="READY", entry=[px - 0.3 * a4["atr"], px],
                 trigger="rejeição do fundo do range em 4H")
    else:
        s.update(state="WAITING", entry=[lo, lo + 0.25 * width],
                 trigger=f"fecho de 4H acima de {px_str(c4[-1]['h'])}")
    return s


def evaluate(c4, a4, a1, reg):
    """Lista de setups e rejeicoes para um ativo."""
    vols = [x["v"] for x in c4]

    def rvol_at(j):
        base = sum(vols[j - 20:j]) / 20 if j >= 20 else 0
        return round(vols[j] / base, 2) if base > 0 else None

    out = []
    for fn in (pullback, sweep, range_reversion):
        r = fn(c4, a4, a1, reg)
        if r:
            out.append(r)
    r = breakout(c4, a4, a1, reg, rvol_at)
    if r:
        out.append(r)
    return out
