"""Papel dos "rejeitados" (decisao do Rui, 2026-10-11: "vejo muitas hipoteses
de bons trades que passam e nao ha sinais").

Responde com dados a essa pergunta: segue em papel TODOS os setups prontos
(gatilho cumprido, com plano) que o sistema NAO transformou em sinal, por
confluencia abaixo do minimo, conflito de sinais, limite de operacoes ou
exposicao correlacionada. Nao entram setups recusados por dados (volume,
preco desatualizado, divergencia): esses nao eram executaveis.

Entra na arena como concorrente "Rejeitados" (analista Oscar). Se os
rejeitados baterem o acaso e as estrategias ao vivo, os filtros estao a
deitar fora bons trades e devem ser revistos; se perderem, os filtros estao
a proteger o dinheiro. Nunca gera ordens nem mensagens.
"""
from . import trade

TF = 14400
MAX_POS = 10
FEE_PCT, SLIP_PCT = 0.25, 0.1
REASONS = ("confluência", "SIGNAL CONFLICT", "limite de operações",
           "exposição correlacionada")


def candidate(r):
    """Plano de um setup pronto que ficou de fora, ou None."""
    for d in (r.get("decision") or {}, r.get("decision_short") or {}):
        if not d or d.get("decision") not in ("WATCHLIST", "NO TRADE"):
            continue
        if d.get("state") != "READY" or not d.get("plan"):
            continue
        reason = d.get("reason") or ""
        if not any(x in reason for x in REASONS):
            continue
        if (d.get("strategy") or "").endswith("_SHORT"):
            continue                      # so compras, como a carteira real
        p = d["plan"]
        lo, hi = sorted(p["entry_zone"])
        if not (lo <= r["price"] <= hi * 1.002):
            continue                      # o preco tem de estar na zona
        return {"strategy": d.get("strategy"), "reason": reason[:80],
                "stop": p["stop"], "tp": list(p["tp"]),
                "partials": list(p.get("partials") or [50, 30, 20])}
    return None


def update(state, rows, bars, now):
    st = state.setdefault("paper_shadow", {"open": {}, "closed": []})
    st.setdefault("open", {})
    st.setdefault("closed", [])
    # acompanhar as abertas vela a vela de 4H
    for a in list(st["open"]):
        pos, c4 = st["open"][a], bars.get(a)
        if not c4:
            continue
        for x in c4:
            if x["t"] < pos["next_t"] or pos["closed"]:
                continue
            trade.step(pos, x["o"], x["h"], x["l"], x["c"], x["t"] + TF)
            pos["next_t"] = x["t"] + TF
        if pos["closed"]:
            st["closed"] = (st["closed"] + [{
                "asset": a, "strategy": pos.get("strategy"),
                "reason_in": pos.get("reason_in"),
                "opened_at": pos["opened_at"], "closed_at": pos.get("closed_at") or now,
                "r": round(pos["r"], 3), "reason": pos["exit_reason"],
                "entry": pos["entry"], "stop": pos["stop0"], "tp": list(pos["tps"]),
                "partials": list(pos["partials"]), "breakeven": True}])[-300:]
            del st["open"][a]
    # abrir novas
    for r in rows:
        a = r.get("asset")
        if not a or a in st["open"] or len(st["open"]) >= MAX_POS:
            continue
        c4 = bars.get(a)
        if not c4:
            continue
        cnd = candidate(r)
        if not cnd or not (cnd["stop"] < r["price"] < cnd["tp"][0]):
            continue
        pos = trade.open_position({"stop": cnd["stop"], "tp": cnd["tp"],
                                   "partials": cnd["partials"]},
                                  r["price"], now, FEE_PCT, SLIP_PCT)
        pos.update(next_t=c4[-1]["t"] + TF, strategy=cnd["strategy"],
                   reason_in=cnd["reason"])
        st["open"][a] = pos
    rs = [c["r"] for c in st["closed"]]
    return {"n": len(rs), "wins": sum(1 for x in rs if x > 0),
            "total_r": round(sum(rs), 2),
            "avg_r": round(sum(rs) / len(rs), 3) if rs else None,
            "open": sorted(st["open"])}
