"""Registo automatico de operacoes (diario de trading).

Uma linha por operacao, construida a partir dos eventos do motor. Os
precos sao os do mercado no momento de cada scan, nao os das ordens do
utilizador: e o registo do que o sistema sinalizou, nao da conta real.
"""
MAX = 1000
CLOSERS = ("STOP", "BREAKEVEN", "TIME", "TP3")


def apply(state, events):
    led = state.setdefault("ledger", [])
    by_id = {r["id"]: r for r in led}
    for e in events:
        k = e["event"]
        if k == "ISSUED":
            s, p = e["signal"], e["signal"]["plan"]
            rec = {"id": e["id"], "kind": "4H", "asset": s["asset"],
                   "pair": s["pair"], "strategy": s["strategy"],
                   "mode": s.get("mode", "REAL"), "score": s["score"],
                   "issued_at": e["t"], "entry_zone": p["entry_zone"],
                   "stop": p["stop"], "tp": p["tp"], "rr": p["rr"],
                   "risk_pct": p["risk_pct"], "position_pct": p["position_pct"],
                   "status": "WAITING", "tp_hit": 0}
            led.append(rec)
            by_id[rec["id"]] = rec
        elif k == "PAPER_BUY":
            rec = {"id": f"{e['id']}-{e['t']}", "kind": "1D", "asset": e["asset"],
                   "pair": e["pair"], "strategy": "TREND_DAILY",
                   "mode": "REAL" if e.get("real") else "PAPER",
                   "issued_at": e["t"], "opened_at": e["t"],
                   "entry": e["price"], "stop": e["stop"],
                   "risk_pct": e.get("risk_pct"),
                   "position_pct": e["position_pct"], "status": "OPEN",
                   "tp_hit": 0}
            led.append(rec)
        elif k == "PAPER_SELL":
            rec = next((r for r in reversed(led)
                        if r["kind"] == "1D" and r["asset"] == e["asset"]
                        and r["status"] == "OPEN"), None)
            if rec:
                rec.update(status="CLOSED", closed_at=e["t"], exit=e["price"],
                           result_r=e["r"], reason=e["reason"])
        else:
            rec = by_id.get(e.get("id"))
            if not rec:
                continue
            if k == "TRIGGERED":
                rec.update(status="OPEN", opened_at=e["t"], entry=e["price"])
            elif k in ("EXPIRED", "INVALIDATED"):
                rec.update(status="CANCELLED", closed_at=e["t"],
                           reason=e["reason"])
            elif k.startswith("TP") and "r" not in e:
                rec["tp_hit"] = int(k[2])
            if "r" in e and k in CLOSERS:
                if k.startswith("TP"):
                    rec["tp_hit"] = 3
                rec.update(status="CLOSED", closed_at=e["t"], exit=e["price"],
                           result_r=e["r"], reason=k)
    del led[:-MAX]
    return led


def summary(led, since=None):
    closed = sorted((r for r in led if r["status"] == "CLOSED"
                     and r.get("mode", "REAL") == "REAL"
                     and (since is None or r["closed_at"] >= since)),
                    key=lambda r: r["closed_at"])
    rs = [r["result_r"] for r in closed]
    wins = [x for x in rs if x > 0]
    by = {}
    for r in closed:
        b = by.setdefault(r["strategy"], {"n": 0, "wins": 0, "sum_r": 0.0})
        b["n"] += 1
        b["wins"] += r["result_r"] > 0
        b["sum_r"] = round(b["sum_r"] + r["result_r"], 2)
    cum, curve, peak, dd = 0.0, [], 0.0, 0.0
    pct = 0.0                       # % do capital = R x risco de cada operacao
    for r in closed:
        cum += r["result_r"]
        pct += r["result_r"] * (r.get("risk_pct") or 0)
        peak = max(peak, cum)
        dd = max(dd, peak - cum)
        curve.append([r["closed_at"], round(cum, 2)])
    return {"closed": len(rs), "open": sum(r["status"] == "OPEN" for r in led),
            "waiting": sum(r["status"] == "WAITING" for r in led),
            "cancelled": sum(r["status"] == "CANCELLED" for r in led),
            "win_rate": round(100 * len(wins) / len(rs), 1) if rs else None,
            "total_r": round(sum(rs), 2),
            "capital_pct": round(pct, 2),
            "avg_win_r": round(sum(wins) / len(wins), 2) if wins else None,
            "avg_loss_r": round(sum(x for x in rs if x <= 0)
                                / (len(rs) - len(wins)), 2)
            if len(rs) > len(wins) else None,
            "max_drawdown_r": round(dd, 2), "by_strategy": by, "curve": curve}
