"""Confluence Engine: score 0-100 da qualidade relativa do setup.

NAO e uma probabilidade de sucesso. Cada familia de informacao conta uma
so vez (anti-redundancia). Pesos para swing; ainda nao calibrados por
backtest - sao um ponto de partida declarado, nao um resultado.
"""
WEIGHTS = {"regime": 20, "htf": 10, "structure": 15, "trigger": 10,
           "flow": 15, "liquidity": 10, "derivatives": 10, "rr": 10}

LABELS = [(85, "EXCEPTIONAL CONFLUENCE"), (75, "HIGH QUALITY"),
          (65, "VALID SETUP"), (50, "WATCHLIST"), (0, "NO TRADE")]


def classify(score):
    return next(lbl for thr, lbl in LABELS if score >= thr)


def score(setup, plan, a4, mtf_conflict, reg, btc_reg, deriv, is_btc,
          regime_changed):
    f, conflicts = {}, []
    strat = setup["strategy"]

    r = {"STRONG BULL": 1.0, "BULL": 0.85, "NEUTRAL": 0.45, "RANGE": 0.4,
         "BEAR": 0.2, "STRONG BEAR": 0.05}.get(reg["regime"], 0.2)
    if strat == "RANGE" and reg["regime"] == "RANGE":
        r = 0.8
    if regime_changed:
        r *= 0.7                                   # transicao de regime
    if reg["high_volatility"]:
        r *= 0.7
    if not is_btc and btc_reg in ("BEAR", "STRONG BEAR"):
        r *= 0.6
        conflicts.append(f"BTC em regime {btc_reg}")
    f["regime"] = r

    f["htf"] = 0.3 if mtf_conflict else 1.0
    if mtf_conflict:
        conflicts.append(mtf_conflict)

    st = a4["structure"]
    f["structure"] = {"BULLISH": 1.0, "NEUTRAL": 0.55}.get(st, 0.2)
    if strat in ("LIQUIDITY_SWEEP", "RANGE") and st != "BULLISH":
        f["structure"] = 0.65       # nestas, estrutura de 4H ainda nao virou

    strong = any(p in a4["patterns"] for p in ("ENGULFING_BULL", "PIN_BAR_BULL"))
    f["trigger"] = (1.0 if strong else 0.8) if setup["state"] == "READY" else 0.35

    v = a4.get("volume") or {}
    fl = 0.5
    if v.get("flow_20") is not None:
        fl = 0.75 if v["flow_20"] > 0.02 else 0.35 if v["flow_20"] < -0.02 else 0.5
    if v.get("rvol") and v["rvol"] >= 1.3 and setup["state"] == "READY":
        fl = min(1.0, fl + 0.2)
    if v.get("divergence") == "BEARISH":
        fl = 0.1
        conflicts.append("fluxo vendedor com preço a subir")
    elif v.get("divergence") == "BULLISH":
        fl = min(1.0, fl + 0.2)
    f["flow"] = fl

    lq = a4.get("liquidity") or {}
    li = 0.5
    ob = lq.get("order_block")
    if ob and ob["side"] == "DEMAND" and ob["zone"][1] >= plan["stop"]:
        li += 0.2
    if lq.get("fvg_below") and lq["fvg_below"][1] >= plan["stop"]:
        li += 0.1
    sw = lq.get("sweep")
    if sw and sw["side"] == "LOW" and sw["confirmed"]:
        li += 0.2
    if sw and sw["side"] == "HIGH" and sw["bars_ago"] <= 3:
        li -= 0.3                     # acabou de varrer topos: risco de queda
    if 1 not in plan["tp_projected"]:
        li += 0.1                     # objetivo assente em liquidez real
    f["liquidity"] = max(0.0, min(1.0, li))

    if not deriv:
        f["derivatives"] = 0.5        # sem dados: neutro, nao favoravel
    else:
        d = 0.55
        fl_ = deriv["flags"]
        if deriv.get("positioning") in ("LONG_BUILDUP", "SHORT_COVERING"):
            d = 0.7
        if "CROWDED_SHORTS" in fl_:
            d = 0.85
        if "CROWDED_LONGS" in fl_ or "FUNDING_EXTREME_POSITIVE" in fl_:
            d = 0.1
            conflicts.append("posicionamento longo excessivo nos derivados")
        elif deriv.get("positioning") == "SHORT_BUILDUP":
            d = 0.3
        f["derivatives"] = d

    f["rr"] = max(0.0, min(1.0, 0.6 + 0.4 * (plan["rr"] - 2.0)))

    total = round(sum(WEIGHTS[k] * f[k] for k in WEIGHTS))
    return {"score": total, "label": classify(total),
            "families": {k: round(v, 2) for k, v in f.items()},
            "conflicts": conflicts}
