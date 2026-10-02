"""Data Validation Engine.

Recebe velas em bruto e devolve (velas_limpas, relatorio). Nunca preenche
dados em falta: so remove duplicados exatos e a vela ainda por fechar.
Estados: VALID, DEGRADED (utilizavel com aviso), DATA INVALID (sem sinal).
"""
import statistics

VALID, DEGRADED, INVALID = "VALID", "DEGRADED", "DATA INVALID"
MIN_HISTORY = {"1d": 200, "4h": 200}


def validate_candles(raw, tf_seconds, now, min_history=200):
    issues, fatal = [], []
    if not raw:
        return [], {"status": INVALID, "issues": ["sem velas"], "n": 0}

    bad_fields = sum(1 for c in raw if any(c[k] is None for k in "ohlcv"))
    if bad_fields:
        fatal.append(f"{bad_fields} velas com campos ilegiveis")
    rows = [c for c in raw if all(c[k] is not None for k in "ohlcv")]

    by_t, conflicts, dups = {}, 0, 0
    for c in rows:
        p = by_t.get(c["t"])
        if p is None:
            by_t[c["t"]] = c
        else:
            dups += 1
            if any(p[k] != c[k] for k in "ohlcv"):
                conflicts += 1
    if dups:
        issues.append(f"{dups} velas duplicadas removidas")
    if conflicts:
        fatal.append(f"{conflicts} timestamps com valores contraditorios")
    candles = [by_t[t] for t in sorted(by_t)]

    # vela ainda em formacao nao entra em nenhum calculo (evita look-ahead)
    candles = [c for c in candles if c["t"] + tf_seconds <= now]
    if not candles:
        return [], {"status": INVALID, "issues": ["sem velas fechadas"], "n": 0}

    misaligned = sum(1 for c in candles if c["t"] % tf_seconds)
    if misaligned:
        fatal.append(f"{misaligned} timestamps desalinhados da grelha")

    impossible = sum(
        1 for c in candles
        if min(c["o"], c["h"], c["l"], c["c"]) <= 0 or c["h"] < c["l"]
        or not (c["l"] <= c["o"] <= c["h"]) or not (c["l"] <= c["c"] <= c["h"])
        or c["v"] < 0)
    if impossible:
        fatal.append(f"{impossible} velas com precos impossiveis")

    span = (candles[-1]["t"] - candles[0]["t"]) // tf_seconds + 1
    missing = span - len(candles)
    if missing > 0:
        recent = candles[-50:]
        recent_missing = ((recent[-1]["t"] - recent[0]["t"]) // tf_seconds + 1
                          - len(recent))
        msg = f"{missing} velas em falta ({missing / span:.1%})"
        if recent_missing or missing / span > 0.01:
            fatal.append(msg + f", {recent_missing} nas ultimas 50")
        else:
            issues.append(msg)

    age = now - (candles[-1]["t"] + tf_seconds)
    if age > 2 * tf_seconds:
        fatal.append(f"dados atrasados {age / tf_seconds:.1f} velas")

    jumps = sum(1 for a, b in zip(candles, candles[1:])
                if abs(b["o"] / a["c"] - 1) > 0.10 and a["c"] > 0)
    if jumps:
        issues.append(f"{jumps} gaps >10% entre fecho e abertura")

    vols = [c["v"] for c in candles]
    zero = sum(1 for v in vols[-50:] if v == 0)
    if zero:
        issues.append(f"{zero} velas sem volume nas ultimas 50")
    med = statistics.median(vols)
    if med > 0:
        spikes = sum(1 for v in vols if v > 50 * med)
        if spikes:
            issues.append(f"{spikes} velas com volume >50x a mediana")

    if len(candles) < min_history:
        issues.append(f"historico insuficiente ({len(candles)}/{min_history})")

    status = INVALID if fatal else DEGRADED if issues else VALID
    return candles, {"status": status, "issues": fatal + issues,
                     "n": len(candles)}


def price_divergence(prices):
    """prices: {fonte: ultimo preco}. Devolve (desvio maximo %, estado)."""
    vals = [p for p in prices.values() if p and p > 0]
    if len(vals) < 2:
        return None, None
    med = statistics.median(vals)
    dev = max(abs(p / med - 1) for p in vals) * 100
    return dev, INVALID if dev > 2 else DEGRADED if dev > 0.5 else VALID
