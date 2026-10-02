"""Signal Engine: decisao final por ativo e ciclo de vida dos sinais.

Hierarquia (falha critica => NO TRADE):
 1 dados validos  2 liquidez/execucao na Bybit UE  3 regime identificado
 4 estrategia adequada ao regime  5 estrutura  6 setup valido
 7 confluencia  8 R:R  9 risco aceitavel  10 sem conflito grave

Um sinal emitido fica congelado: os niveis nao sao recalculados nem
reutilizados. Expira ao fim de signal_expiry_hours ou e invalidado.
"""
from . import confluence, regime, risk, strategies, validate, venue

H4 = 14400


def _fmt(x):
    return float(f"{x:.5g}")


def decide(row, c4, cfg, v, btc_reg, regime_changed):
    """Devolve o bloco 'decision' de um ativo."""
    checks, out = [], {"decision": "NO TRADE", "validated": False}

    def chk(n, name, ok, detail=""):
        checks.append({"n": n, "check": name, "ok": bool(ok), "detail": detail})
        return ok

    def stop(reason):
        out.update(reason=reason, checks=checks)
        return out

    an = row.get("analysis")
    ok = row.get("data_status") != validate.INVALID and an and \
        an["1d"]["ok"] and an["4h"]["ok"]
    if not chk(1, "dados válidos", ok, row.get("data_status") or ""):
        return stop("dados inválidos ou histórico insuficiente")

    v_ok, v_why = venue.check(v, row["price"], cfg)
    if not chk(2, "execução na Bybit UE", v_ok, "; ".join(v_why)):
        return stop(v_why[0])
    out["venue"] = {"name": cfg["venue"], "pair": v["pair"], "last": v["last"],
                    "spread_pct": v["spread_pct"], "url": v["url"]}

    a1, a4 = an["1d"], an["4h"]
    reg = regime.classify(a1)
    out["regime"] = reg["regime"]
    out["regime_changed"] = regime_changed
    ok = reg["regime"] not in ("UNCLEAR", "HIGH VOLATILITY")
    if not chk(3, "regime identificado", ok, reg["regime"]):
        return stop(f"regime {reg['regime']}: sem vantagem identificável")

    found = strategies.evaluate(c4, a4, a1, reg)
    setups = [s for s in found if "rejected" not in s]
    out["rejected"] = [f"{s['strategy']}: {s['rejected']}" for s in found
                       if "rejected" in s]
    if not chk(4, "estratégia adequada ao regime", setups,
               ", ".join(s["strategy"] for s in setups)):
        return stop(out["rejected"][0] if out["rejected"] else
                    f"nenhuma estratégia aplicável em regime {reg['regime']}")

    ok = not (a4["structure"] == "BEARISH" and a1["structure"] == "BEARISH")
    if not chk(5, "estrutura", ok, f"1D {a1['structure']}, 4H {a4['structure']}"):
        return stop("estrutura de descida em 1D e 4H")

    best, fails = None, []
    for s in setups:
        p, why = risk.plan(s, a4, a1, cfg)
        if p is None:
            fails.append(f"{s['strategy']}: {why}")
            continue
        sc = confluence.score(s, p, a4, an.get("mtf_conflict"), reg, btc_reg,
                              row.get("derivatives"), row["asset"] == "BTC",
                              regime_changed)
        cand = (s["state"] == "READY", sc["score"], s, p, sc)
        if best is None or cand[:2] > best[:2]:
            best = cand
    out["rejected"] += fails
    if best is None:
        chk(8, "R:R e stop", False, fails[0])
        return stop(fails[0])
    _, _, s, p, sc = best
    ready = s["state"] == "READY"
    out.update(strategy=s["strategy"], state=s["state"], trigger=s["trigger"],
               notes=s["notes"], score=sc["score"], score_label=sc["label"],
               families=sc["families"], conflicts=sc["conflicts"],
               plan={k: ([_fmt(x) for x in val] if k in ("entry_zone", "tp")
                         else _fmt(val) if k in ("entry_ref", "stop") else val)
                     for k, val in p.items()},
               confidence={
                   "data_quality": row.get("data_quality"),
                   "liquidity_quality": row.get("liquidity_score"),
                   "setup_quality": sc["score"],
                   "regime_compatibility": round(100 * sc["families"]["regime"]),
                   "historical_strategy_quality": None})   # sem backtest ainda
    chk(6, "setup válido (gatilho)", ready, s["trigger"])
    chk(7, "confluência", sc["score"] >= cfg["min_score"],
        f"{sc['score']}/100, mínimo {cfg['min_score']}")
    chk(8, "R:R", True, f"1:{p['rr']}")
    chk(9, "risco aceitável", True,
        f"stop {p['stop_pct']}%, posição {p['position_pct']}% do capital")
    grave = len(sc["conflicts"]) >= 2
    chk(10, "sem conflito grave", not grave, "; ".join(sc["conflicts"]))
    out["checks"] = checks
    if grave:
        out.update(decision="NO TRADE",
                   reason="SIGNAL CONFLICT: " + "; ".join(sc["conflicts"]))
    elif sc["score"] < 50:
        out.update(decision="NO TRADE",
                   reason=f"confluência insuficiente ({sc['score']}/100)")
    elif ready and sc["score"] >= cfg["min_score"]:
        out.update(decision="LONG", reason=s["trigger"])
    else:
        out.update(decision="WATCHLIST", reason=(
            s["trigger"] if not ready else
            f"confluência {sc['score']}/100 abaixo do mínimo {cfg['min_score']}"))
    return out


def explain(row):
    """Explicacao humana do sinal (WHY / WHY NOW / ...)."""
    d, an = row["decision"], row["analysis"]
    p = d["plan"]
    fam = sorted(d["families"].items(), key=lambda kv: kv[1])
    weakest = fam[0][0]
    return {
        "why": "; ".join(d["notes"]) + f". Regime diário {d['regime']}.",
        "why_now": d["trigger"],
        "confirms": [k for k, v in d["families"].items() if v >= 0.7],
        "invalidates": f"fecho de 4H abaixo de {strategies.px_str(p['stop'])}",
        "main_risk": (d["conflicts"][0] if d["conflicts"] else
                      f"ponto mais fraco da confluência: {weakest}"),
        "would_change": ("perda da estrutura de 4H, mudança do regime diário "
                         "ou o preço afastar-se da zona de entrada sem a tocar")}


def update_state(state, rows, cfg, now):
    """Emite, mantem, expira e invalida sinais. Devolve eventos de auditoria."""
    sigs = state.setdefault("signals", {})
    events = []
    by_asset = {r["asset"]: r for r in rows}

    def close(key, status, why):
        s = sigs[key]
        s.update(status=status, closed_at=now, close_reason=why)
        events.append({"t": now, "event": status, "id": key, "reason": why})

    for key, s in list(sigs.items()):
        if s["status"] in ("ACTIVE", "TRIGGERED"):
            r = by_asset.get(s["asset"])
            px = r["price"] if r else None
            if s["status"] == "ACTIVE":
                if px is not None and px <= s["plan"]["stop"]:
                    close(key, "INVALIDATED", "preço atingiu o stop antes da entrada")
                elif px is not None and px > s["plan"]["tp"][0]:
                    close(key, "INVALIDATED", "preço chegou ao TP1 sem dar entrada")
                elif now >= s["expires_at"]:
                    close(key, "EXPIRED", "validade do sinal terminou")
                elif px is not None and px <= s["plan"]["entry_zone"][1]:
                    s.update(status="TRIGGERED", triggered_at=now)
                    events.append({"t": now, "event": "TRIGGERED", "id": key,
                                   "price": px})
        elif now - s.get("closed_at", now) > 7 * 86400:
            del sigs[key]
    # sinais TRIGGERED: o acompanhamento ate stop/TP e a Fase 6 (paper trading)

    live = {s["asset"] for s in sigs.values()
            if s["status"] in ("ACTIVE", "TRIGGERED")}
    slots = cfg["max_new_signals"] - sum(
        1 for s in sigs.values() if s["status"] == "ACTIVE")
    cands = sorted((r for r in rows if r["decision"]["decision"] == "LONG"
                    and r["asset"] not in live),
                   key=lambda r: -r["decision"]["score"])
    for r in cands:
        d = r["decision"]
        if slots <= 0:
            d.update(decision="WATCHLIST",
                     reason="limite de sinais ativos em simultâneo atingido")
            continue
        slots -= 1
        key = f"{r['asset']}-{d['strategy']}-{now}"
        sig = {"id": key, "asset": r["asset"], "pair": d["venue"]["pair"],
               "venue": d["venue"]["name"], "direction": "LONG",
               "strategy": d["strategy"], "timeframe": "4H / 1D",
               "plan": d["plan"], "score": d["score"],
               "score_label": d["score_label"], "regime": d["regime"],
               "confidence": d["confidence"], "conflicts": d["conflicts"],
               "explain": explain(r), "issued_at": now,
               "expires_at": now + cfg["signal_expiry_hours"] * 3600,
               "status": "ACTIVE", "validated": False}
        sigs[key] = sig
        events.append({"t": now, "event": "ISSUED", "id": key, "signal": sig,
                       "features": {"analysis": r["analysis"],
                                    "derivatives": r.get("derivatives"),
                                    "families": d["families"],
                                    "checks": d["checks"],
                                    "data_status": r["data_status"],
                                    "price": r["price"]}})
    for r in rows:
        act = [s for s in sigs.values() if s["asset"] == r["asset"]
               and s["status"] in ("ACTIVE", "TRIGGERED")]
        if act:
            r["decision"]["active_signal"] = act[0]["id"]
    return events
