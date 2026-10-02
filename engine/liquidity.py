"""Liquidity Engine: liquidez em repouso, equal highs/lows, sweeps, FVG e
order blocks. Tudo descritivo. Um sweep NAO e uma reversao: fica marcado
como nao confirmado ate haver um fecho posterior que o confirme.
"""
from . import indicators as I
from . import structure as S

LOOKBACK = 150
RECENT = 8


def analyse(c):
    if len(c) < 60:
        return None
    atr = I.atr(c)[-1]
    if not atr:
        return None
    n = len(c)
    px = c[-1]["c"]
    start = max(0, n - LOOKBACK)
    piv = [p for p in S.swings(c) if p["i"] >= start]
    highs = [p for p in piv if p["kind"] == "H"]
    lows = [p for p in piv if p["kind"] == "L"]

    # Um nivel so se considera "tomado" se for ultrapassado por mais do que
    # a tolerancia; assim dois topos quase iguais contam como equal highs.
    tol = 0.1 * atr

    def untouched_high(p):
        return all(x["h"] <= p["price"] + tol for x in c[p["i"] + 1:])

    def untouched_low(p):
        return all(x["l"] >= p["price"] - tol for x in c[p["i"] + 1:])

    above = sorted((p["price"] for p in highs if untouched_high(p)
                    and p["price"] > px))
    below = sorted((p["price"] for p in lows if untouched_low(p)
                    and p["price"] < px), reverse=True)

    def equal(levels):
        for a, b in zip(levels, levels[1:]):
            if abs(a - b) <= tol:
                return round((a + b) / 2, 10)
        return None

    out = {"pools_above": above[:2], "pools_below": below[:2],
           "equal_highs": equal(above), "equal_lows": equal(below),
           "sweep": None, "fvg_below": None, "fvg_above": None,
           "order_block": None}

    # Sweep: a vela j ultrapassa um pivot ja confirmado e fecha de volta.
    for j in range(n - 1, max(n - 1 - RECENT, 0), -1):
        cj, found = c[j], None
        for p in highs:
            if p["confirmed_i"] < j and cj["h"] > p["price"] > cj["c"] and \
                    all(x["h"] <= p["price"] for x in c[p["i"] + 1:j]):
                conf = any(x["c"] < cj["l"] for x in c[j + 1:])
                found = {"side": "HIGH", "level": p["price"],
                         "bars_ago": n - 1 - j, "confirmed": conf}
        for p in lows:
            if p["confirmed_i"] < j and cj["l"] < p["price"] < cj["c"] and \
                    all(x["l"] >= p["price"] for x in c[p["i"] + 1:j]):
                conf = any(x["c"] > cj["h"] for x in c[j + 1:])
                found = {"side": "LOW", "level": p["price"],
                         "bars_ago": n - 1 - j, "confirmed": conf}
        if found:
            out["sweep"] = found
            break

    # FVG por preencher, com dimensao minima de 0.25 ATR.
    for i in range(n - 1, max(start, 2) - 1, -1):
        lo, hi = c[i - 2]["h"], c[i]["l"]          # gap de alta
        if hi - lo >= 0.25 * atr and out["fvg_below"] is None and hi < px \
                and all(x["l"] > lo for x in c[i + 1:]):
            out["fvg_below"] = [lo, hi]
        hi2, lo2 = c[i - 2]["l"], c[i]["h"]        # gap de baixa
        if hi2 - lo2 >= 0.25 * atr and out["fvg_above"] is None and lo2 > px \
                and all(x["h"] < hi2 for x in c[i + 1:]):
            out["fvg_above"] = [lo2, hi2]
        if out["fvg_below"] and out["fvg_above"]:
            break

    # Order block: ultima vela contraria antes do impulso que quebrou a
    # estrutura. So conta se o preco ainda nao fechou para la da zona.
    ev = S.analyse(c)["event"]
    if ev and ev["bars_ago"] <= 30:
        j = n - 1 - ev["bars_ago"]
        up = ev["direction"] == "UP"
        for k in range(j, max(j - 15, 0), -1):
            ck = c[k]
            if (ck["c"] < ck["o"]) if up else (ck["c"] > ck["o"]):
                held = all((x["c"] >= ck["l"]) if up else (x["c"] <= ck["h"])
                           for x in c[k + 1:])
                if held:
                    out["order_block"] = {
                        "side": "DEMAND" if up else "SUPPLY",
                        "zone": [ck["l"], ck["h"]], "bars_ago": n - 1 - k}
                break
    return out


def book_metrics(bids, asks, order_usd=10_000):
    """bids/asks: [(preco, qtd)] ordenados a partir do topo do livro.

    Instantaneo do livro: ordens passivas podem ser canceladas, por isso o
    desequilibrio e so informativo. O que interessa aqui e o slippage.
    """
    if not bids or not asks or asks[0][0] <= 0 or bids[0][0] <= 0:
        return None
    mid = (bids[0][0] + asks[0][0]) / 2
    bid_usd = sum(p * q for p, q in bids if p >= mid * 0.99)
    ask_usd = sum(p * q for p, q in asks if p <= mid * 1.01)
    covers = bids[-1][0] <= mid * 0.99 and asks[-1][0] >= mid * 1.01
    need, cost, qty = order_usd, 0.0, 0.0
    for p, q in asks:
        take = min(q, need / p)
        cost += take * p
        qty += take
        need -= take * p
        if need <= 1e-9:
            break
    slip = None if need > 1e-6 or qty == 0 else (cost / qty / mid - 1) * 1e4
    tot = bid_usd + ask_usd
    return {"depth_1pct_usd": round(tot), "depth_complete": covers,
            "imbalance": round((bid_usd - ask_usd) / tot, 3) if tot else None,
            "slippage_bps_10k": None if slip is None else round(slip, 2)}
