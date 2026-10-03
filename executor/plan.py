"""Ordens que o executor colocaria para cada sinal. Funcoes puras: nao
ligam a nada. SIMULACAO: nada aqui coloca ordens reais."""

LIMITS = {"max_open": 2, "max_position_usdc": 25.0, "max_risk_usdc": 1.0,
          "min_order_usdc": 5.0, "max_state_age_s": 600}


def _side(sig):
    return sig.get("direction", "LONG")


def entry_price(sig):
    """O motor da a entrada quando o preco toca o limite da zona: topo nas
    compras, base nos shorts (engine/signals.py, track)."""
    lo, hi = sorted(sig["plan"]["entry_zone"])
    return hi if _side(sig) == "LONG" else lo


def quantity(sig):
    return sig["plan"]["position_usdc"] / entry_price(sig)


def refuse(sig, open_count, limits=LIMITS):
    """Motivo para recusar um sinal novo, ou None."""
    p = sig["plan"]
    if sig.get("mode", "REAL") != "REAL":
        return "sinal em modo PAPEL"
    if not p.get("position_usdc"):
        return "sinal sem valor em USDC"
    if p["position_usdc"] > limits["max_position_usdc"] + 1e-9:
        return f"posição de {p['position_usdc']} USDC acima do limite"
    if p.get("risk_usdc", 0) > limits["max_risk_usdc"] + 1e-9:
        return f"risco de {p['risk_usdc']} USDC acima do limite"
    if open_count >= limits["max_open"]:
        return "limite de operações em simultâneo"
    return None


def entry_order(sig):
    buy = _side(sig) == "LONG"
    return {"action": "PLACE_ENTRY", "id": sig["id"], "pair": sig["pair"],
            "side": "BUY" if buy else "SELL", "type": "LIMIT",
            "price": entry_price(sig), "qty": quantity(sig),
            "usdc": sig["plan"]["position_usdc"],
            "leverage": (sig["plan"].get("leverage") or {}).get("use", 1.0),
            "expires_at": sig["expires_at"]}


def protection_orders(sig, limits=LIMITS):
    """Stop para a posicao toda e um objetivo por parcial. As parciais
    seguem engine/trade.py: o ultimo objetivo leva o que restar."""
    p, qty = sig["plan"], quantity(sig)
    close = "SELL" if _side(sig) == "LONG" else "BUY"
    out = [{"action": "PLACE_STOP", "id": sig["id"], "pair": sig["pair"],
            "side": close, "type": "STOP_MARKET", "trigger": p["stop"],
            "qty": qty}]
    left = 100.0
    for k, tp in enumerate(p["tp"]):
        pct = p["partials"][k] if k < len(p["tp"]) - 1 else left
        pct = min(pct, left)
        if pct <= 0:
            continue
        left -= pct
        o = {"action": "PLACE_TP", "id": sig["id"], "pair": sig["pair"],
             "side": close, "type": "LIMIT", "price": tp, "n": k + 1,
             "qty": qty * pct / 100, "usdc": qty * pct / 100 * tp}
        if o["usdc"] < limits["min_order_usdc"]:
            o["warning"] = "abaixo da ordem mínima"
        out.append(o)
    return out


def breakeven_order(sig):
    pos = sig["position"]
    return {"action": "MOVE_STOP", "id": sig["id"], "pair": sig["pair"],
            "trigger": pos["entry"],
            "qty": quantity(sig) * pos["remaining"] / 100}
