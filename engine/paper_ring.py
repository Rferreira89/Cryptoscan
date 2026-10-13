"""Papel ao vivo automatico para os lutadores qualificados no combate
(decisao do Rui, 2026-10-13). Cada qualificado com funcao de sinal em
tools/arena_ringue.SINAIS que nao tenha papel proprio (o Bounce ja tem o
seu em engine/paper_bounce.py) passa a operar em papel aqui, sem mais
nenhuma intervencao. As operacoes fechadas entram na arena como operacoes
ao vivo desse lutador. Nunca gera ordens nem mensagens de compra.
"""
from . import promo, trade

TF = 14400
MAX_POS = 6
FEE_PCT, SLIP_PCT = 0.25, 0.1
OWN_PAPER = ("BOUNCE_G0", "BOUNCE_V1", "BOUNCE_V2", "BOUNCE_V3")


def update(state, rows, bars, now, market_ok=True):
    st = state.setdefault("paper_ring", {})
    reg = promo.registry()
    active = [k for k, _ in promo.qualified(state) if k in reg and k not in OWN_PAPER]
    for k in set(st) | set(active):
        b = st.setdefault(k, {"open": {}, "closed": [], "last": {}})
        for a in list(b["open"]):
            pos, c4 = b["open"][a], bars.get(a)
            if not c4:
                continue
            for x in c4:
                if x["t"] < pos["next_t"] or pos["closed"]:
                    continue
                trade.step(pos, x["o"], x["h"], x["l"], x["c"], x["t"] + TF)
                pos["next_t"] = x["t"] + TF
            if pos["closed"]:
                b["closed"] = (b["closed"] + [{
                    "asset": a, "opened_at": pos["opened_at"],
                    "closed_at": pos.get("closed_at") or now, "r": round(pos["r"], 3),
                    "reason": pos["exit_reason"], "entry": pos["entry"],
                    "stop": pos["stop0"], "tp": list(pos["tps"]),
                    "partials": list(pos["partials"]),
                    "breakeven": pos.get("breakeven", True)}])[-300:]
                del b["open"][a]
        if k not in active or not market_ok:
            continue
        for r in rows:
            a, c4 = r.get("asset"), bars.get(r.get("asset"))
            if not c4 or a in b["open"] or len(b["open"]) >= MAX_POS:
                continue
            try:
                sig = reg[k](c4, r["price"], None)
            except Exception:
                continue
            if not sig or now - sig["t_sig"] > TF or b["last"].get(a) == sig["t_sig"]:
                continue
            b["last"][a] = sig["t_sig"]
            if not (sig["stop"] < r["price"] < sig["tp"][0]):
                continue
            pos = trade.open_position(sig, r["price"], sig["t_sig"], FEE_PCT, SLIP_PCT,
                                      breakeven=sig.get("breakeven", True))
            pos["next_t"] = c4[-1]["t"] + TF
            if sig.get("hold_s"):
                pos["max_hold"] = sig["hold_s"]
            b["open"][a] = pos
    return {k: {"n": len(v["closed"]), "open": sorted(v["open"])} for k, v in st.items()}
