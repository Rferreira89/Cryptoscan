"""Gestao de uma operacao aberta. A MESMA logica serve o acompanhamento ao
vivo e o backtest, para que os dois nao possam divergir.

Regras: vendas parciais nos TPs; depois do TP1 o stop sobe para a entrada.
Pressupostos conservadores dentro de uma vela: se o stop e um TP sao
tocados na mesma vela, conta o stop; se a vela abre abaixo do stop, sai ao
preco de abertura (gap). Resultado em R = multiplos do risco inicial.
"""
MAX_HOLD_SECONDS = 30 * 86400


def open_position(plan, fill_price, t, fee_pct, slip_pct=0.0, breakeven=True):
    fee = fee_pct / 100
    entry = fill_price * (1 + slip_pct / 100)
    stop0 = plan["stop"]
    return {"entry": entry, "stop0": stop0, "stop": stop0,
            "tps": list(plan["tp"]), "partials": list(plan["partials"]),
            "remaining": 100.0, "tp_hit": 0, "realized": 0.0, "fee": fee,
            "slip": slip_pct / 100, "opened_at": t, "breakeven": breakeven,
            "risk_unit": entry - stop0 + fee * (entry + stop0),
            "closed": False, "r": None, "exit_reason": None}


def _sell(pos, pct, price):
    pos["realized"] += pct / 100 * (price - pos["entry"]
                                    - pos["fee"] * (price + pos["entry"]))
    pos["remaining"] -= pct


def _finish(pos, reason, t):
    pos.update(closed=True, exit_reason=reason, closed_at=t,
               r=round(pos["realized"] / pos["risk_unit"], 3))


def step(pos, o, h, l, c, t):
    """Avanca uma vela (ou um preco pontual: o=h=l=c). Devolve eventos."""
    ev = []
    if pos["closed"]:
        return ev
    reason = "STOP" if pos["stop"] < pos["entry"] else "BREAKEVEN"
    if o <= pos["stop"]:                               # gap para la do stop
        px = o * (1 - pos["slip"])
        _sell(pos, pos["remaining"], px)
        _finish(pos, reason, t)
        return [{"event": reason, "price": px, "r": pos["r"]}]
    if l <= pos["stop"]:
        px = pos["stop"] * (1 - pos["slip"])
        _sell(pos, pos["remaining"], px)
        _finish(pos, reason, t)
        return [{"event": reason, "price": px, "r": pos["r"]}]
    while pos["remaining"] > 1e-9 and pos["tp_hit"] < len(pos["tps"]) \
            and h >= pos["tps"][pos["tp_hit"]]:
        k = pos["tp_hit"]
        tp = pos["tps"][k]
        pct = pos["partials"][k] if k < len(pos["tps"]) - 1 else pos["remaining"]
        _sell(pos, pct, tp)
        pos["tp_hit"] += 1
        ev.append({"event": f"TP{k + 1}", "price": tp, "sold_pct": pct})
        if k == 0 and pos.get("breakeven", True):
            pos["stop"] = pos["entry"]                 # stop para a entrada
            if l <= pos["entry"] and h > l:            # mesma vela: conservador
                _sell(pos, pos["remaining"], pos["entry"] * (1 - pos["slip"]))
                _finish(pos, "BREAKEVEN", t)
                ev.append({"event": "BREAKEVEN", "price": pos["entry"],
                           "r": pos["r"]})
                return ev
    if pos["remaining"] <= 1e-9:
        _finish(pos, ev[-1]["event"], t)       # objetivo que fechou a posicao
        ev[-1]["r"] = pos["r"]
    elif t - pos["opened_at"] >= MAX_HOLD_SECONDS:
        _sell(pos, pos["remaining"], c * (1 - pos["slip"]))
        _finish(pos, "TIME", t)
        ev.append({"event": "TIME", "price": c, "r": pos["r"]})
    return ev
