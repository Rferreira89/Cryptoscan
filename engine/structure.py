"""Market Structure Engine + Price Action Engine.

Swings: pivots fractais com K velas de cada lado. Um pivot na vela i so e
conhecido na vela i+K - nunca e usado antes disso (sem look-ahead).
"""
K = 3


def swings(c, k=K):
    """Lista de pivots confirmados, alternando topo/fundo.

    Cada pivot: {i, t, price, kind: 'H'|'L', confirmed_i}.
    """
    piv = []
    for i in range(k, len(c) - k):
        win = c[i - k:i + k + 1]
        is_h = c[i]["h"] == max(x["h"] for x in win) and \
            all(c[i]["h"] > x["h"] for x in c[i - k:i])
        is_l = c[i]["l"] == min(x["l"] for x in win) and \
            all(c[i]["l"] < x["l"] for x in c[i - k:i])
        for kind, ok, price in (("H", is_h, c[i]["h"]), ("L", is_l, c[i]["l"])):
            if not ok:
                continue
            p = {"i": i, "t": c[i]["t"], "price": price, "kind": kind,
                 "confirmed_i": i + k}
            if piv and piv[-1]["kind"] == kind:
                better = price > piv[-1]["price"] if kind == "H" \
                    else price < piv[-1]["price"]
                if better:
                    piv[-1] = p
            else:
                piv.append(p)
    return piv


def label(piv):
    last = {"H": None, "L": None}
    for p in piv:
        prev = last[p["kind"]]
        if prev is None:
            p["label"] = None
        elif p["kind"] == "H":
            p["label"] = "HH" if p["price"] > prev["price"] else "LH"
        else:
            p["label"] = "HL" if p["price"] > prev["price"] else "LL"
        last[p["kind"]] = p
    return piv


def analyse(c, k=K):
    """Estrutura no fecho da ultima vela de c."""
    piv = label(swings(c, k))
    highs = [p for p in piv if p["kind"] == "H"]
    lows = [p for p in piv if p["kind"] == "L"]
    out = {"trend": "NEUTRAL", "last_high": None, "last_low": None,
           "sequence": [p["label"] for p in piv[-6:] if p["label"]],
           "event": None}
    if len(highs) < 2 or len(lows) < 2:
        out["trend"] = "UNCLEAR"
        return out
    hl, ll = highs[-1]["label"], lows[-1]["label"]
    if hl == "HH" and ll == "HL":
        out["trend"] = "BULLISH"
    elif hl == "LH" and ll == "LL":
        out["trend"] = "BEARISH"
    out["last_high"], out["last_low"] = highs[-1]["price"], lows[-1]["price"]

    # BOS / CHOCH: primeiro fecho para la do ultimo pivot confirmado.
    # So conta o fecho de velas posteriores a confirmacao do pivot.
    def first_break(p, up):
        for j in range(p["confirmed_i"] + 1, len(c)):
            if (c[j]["c"] > p["price"]) if up else (c[j]["c"] < p["price"]):
                return j
        return None

    cand = []
    j = first_break(highs[-1], True)
    if j is not None:
        prior_bear = hl == "LH"
        cand.append((j, "CHOCH" if prior_bear else "BOS", "UP",
                     highs[-1]["price"]))
    j = first_break(lows[-1], False)
    if j is not None:
        prior_bull = ll == "HL"
        cand.append((j, "CHOCH" if prior_bull else "BOS", "DOWN",
                     lows[-1]["price"]))
    if cand:
        j, typ, direction, level = max(cand)
        out["event"] = {"type": typ, "direction": direction, "level": level,
                        "bars_ago": len(c) - 1 - j}
    return out


def patterns(c):
    """Padroes na ultima vela fechada. Contexto apenas - nunca um sinal."""
    if len(c) < 2:
        return []
    a, b = c[-2], c[-1]
    rng = b["h"] - b["l"]
    if rng <= 0:
        return []
    body = abs(b["c"] - b["o"])
    up_w = b["h"] - max(b["o"], b["c"])
    lo_w = min(b["o"], b["c"]) - b["l"]
    out = []
    if body / rng < 0.1:
        out.append("DOJI")
    if lo_w >= 2 * body and lo_w / rng >= 0.6 and body / rng >= 0.1:
        out.append("PIN_BAR_BULL")
    if up_w >= 2 * body and up_w / rng >= 0.6 and body / rng >= 0.1:
        out.append("PIN_BAR_BEAR")
    pa_body_lo, pa_body_hi = min(a["o"], a["c"]), max(a["o"], a["c"])
    # engolfo so conta se a vela anterior tiver corpo relevante
    a_rng = a["h"] - a["l"]
    if a_rng <= 0 or (pa_body_hi - pa_body_lo) / a_rng < 0.3:
        pa_body_lo, pa_body_hi = float("inf"), float("-inf")
    if b["c"] > b["o"] and a["c"] < a["o"] and b["o"] <= pa_body_lo \
            and b["c"] >= pa_body_hi > pa_body_lo:
        out.append("ENGULFING_BULL")
    if b["c"] < b["o"] and a["c"] > a["o"] and b["o"] >= pa_body_hi \
            and b["c"] <= pa_body_lo < pa_body_hi:
        out.append("ENGULFING_BEAR")
    if b["h"] < a["h"] and b["l"] > a["l"]:
        out.append("INSIDE_BAR")
    return out
