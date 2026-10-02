"""Signal Engine: decisao final por ativo e ciclo de vida dos sinais.

Hierarquia (falha critica => NO TRADE):
 1 dados validos  2 liquidez/execucao na Bybit UE  3 regime identificado
 4 estrategia adequada ao regime  5 estrutura  6 setup valido
 7 confluencia  8 R:R  9 risco aceitavel  10 sem conflito grave

Um sinal emitido fica congelado: os niveis nao sao recalculados nem
reutilizados. Expira ao fim de signal_expiry_hours ou e invalidado.
"""
from . import (confluence, regime, risk, strategies, trade, validate,
               validation, venue)

H4 = 14400


def _fmt(x):
    return float(f"{x:.5g}")


def decide(row, c4, cfg, v, btc_reg, regime_changed, market_ok=True,
           block=None, disabled=()):
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

    if cfg["min_score"] > 0 and cfg.get("require_btc_above_sma200") \
            and not market_ok:
        chk(3, "filtro de mercado", False, "BTC abaixo da média de 200 dias")
        return stop("filtro de mercado: BTC abaixo da média de 200 dias, "
                    "sem compras novas")

    if cfg["min_score"] > 0 and block:
        chk(3, "risco de evento", False, block)
        return stop(f"NEWS RISK: {block}, sem compras novas")

    found = strategies.evaluate(c4, a4, a1, reg)
    out["rejected"] = [f"{s['strategy']}: {s['rejected']}" for s in found
                       if "rejected" in s]
    setups = []
    for s in found:
        if "rejected" in s:
            continue
        # So estrategias validadas em backtest geram operacoes REAIS. As
        # restantes correm em PAPEL (ou nao correm, conforme a configuracao).
        # min_score = 0 e o proprio backtest: nunca e travado.
        if cfg["min_score"] > 0 and s["strategy"] in disabled:
            out["rejected"].append(f"{s['strategy']}: estratégia desligada "
                                   "(registo ao vivo negativo)")
            continue
        if cfg["min_score"] > 0:
            st = validation.status(s["strategy"])
            s["validated"] = bool(st.get("validated"))
            s["mode"] = "REAL" if s["validated"] or \
                cfg.get("real_money_unvalidated") else "PAPER"
            if s["mode"] == "PAPER" and not cfg.get("paper_unvalidated", True):
                out["rejected"].append(
                    f"{s['strategy']}: estratégia não validada em backtest "
                    f"({st['label']})")
                continue
        setups.append(s)
    if not chk(4, "estratégia adequada ao regime", setups,
               ", ".join(s["strategy"] for s in setups)):
        return stop(out["rejected"][0] if out["rejected"] else
                    f"nenhuma estratégia aplicável em regime {reg['regime']}")

    ok = not (a4["structure"] == "BEARISH" and a1["structure"] == "BEARISH")
    if not chk(5, "estrutura", ok, f"1D {a1['structure']}, 4H {a4['structure']}"):
        return stop("estrutura de descida em 1D e 4H")

    best, fails = None, []
    for s in setups:
        # nunca arriscar mais por o score ser alto; arriscar menos quando a
        # estrategia nao esta validada
        rp = cfg["risk_pct"] if s.get("validated", True) else \
            min(cfg["risk_pct"], cfg.get("unvalidated_risk_pct", cfg["risk_pct"]))
        p, why = risk.plan(s, a4, a1, dict(cfg, risk_pct=rp))
        if p is None:
            fails.append(f"{s['strategy']}: {why}")
            continue
        sc = confluence.score(s, p, a4, an.get("mtf_conflict"), reg, btc_reg,
                              row.get("derivatives"), row["asset"] == "BTC",
                              regime_changed)
        # Alavancagem desta operacao: parte do valor configurado e so pode
        # descer, nunca subir por o score ser alto.
        lev, why = operation_leverage(cfg, p, sc, reg, a1, btc_reg,
                                      row["asset"] == "BTC")
        if lev < p["leverage"]["use"]:
            # com menos alavancagem a posicao encolhe e pode deixar de ser
            # executavel (ordem minima): nesse caso nao ha operacao
            p, why_not = risk.plan(s, a4, a1, dict(cfg, risk_pct=rp,
                                                   swing_leverage=lev))
            if p is None:
                fails.append(f"{s['strategy']}: {why_not} ({why})")
                continue
        p["leverage"]["reason"] = why
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
               mode=s.get("mode", "REAL"),
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


def operation_leverage(cfg, plan, sc, reg, a1, btc_reg, is_btc):
    """Quanto alavancar NESTA operacao e porque. Devolve (valor, motivo)."""
    base = plan["leverage"]["use"]
    if cfg.get("swing_leverage", 1.0) <= 1:
        return 1.0, "alavancagem desligada na configuração"
    if sc["conflicts"]:
        return 1.0, "sem margem: há um conflito (" + sc["conflicts"][0] + ")"
    if reg["high_volatility"] or (a1.get("atr_pctile") or 0) >= 90:
        return 1.0, "sem margem: volatilidade diária muito alta"
    if reg["regime"] not in regime.BULLISH:
        return min(base, 1.0), f"sem margem: regime {reg['regime']}"
    if not is_btc and btc_reg not in regime.BULLISH:
        return min(base, 1.5), f"reduzida: BTC em regime {btc_reg}"
    if base < cfg["swing_leverage"]:
        return base, ("reduzida pelo stop largo, para manter a liquidação "
                      "longe do stop")
    return base, "condições normais: tendência a favor e sem conflitos"


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


def trading_halt(sigs, cfg, now):
    """Travao de perdas das operacoes reais. Devolve o motivo ou None."""
    closed = sorted((s for s in sigs.values() if s["status"] == "CLOSED"
                     and s.get("mode", "REAL") == "REAL"),
                    key=lambda s: s["closed_at"])
    day = sum(s["result_r"] for s in closed if now - s["closed_at"] < 86400)
    week = sum(s["result_r"] for s in closed if now - s["closed_at"] < 7 * 86400)
    if day <= -cfg["max_daily_loss_r"]:
        return f"perda diária de {day:.1f}R atingiu o limite"
    if week <= -cfg["max_weekly_loss_r"]:
        return f"perda semanal de {week:.1f}R atingiu o limite"
    n = cfg["cooldown_after_losses"]
    last = closed[-n:]
    if len(last) == n and all(s["result_r"] <= 0 for s in last) \
            and now - last[-1]["closed_at"] < 86400:
        return f"{n} perdas seguidas: pausa de 24 horas"
    return None


def correlation(ca, cb, n=60):
    """Correlacao dos retornos diarios dos ultimos n dias (ou None)."""
    if not ca or not cb:
        return None
    a = {x["t"]: x["c"] for x in ca[-n - 1:]}
    b = {x["t"]: x["c"] for x in cb[-n - 1:]}
    ts = sorted(set(a) & set(b))
    if len(ts) < 30:
        return None
    ra = [a[ts[i]] / a[ts[i - 1]] - 1 for i in range(1, len(ts))]
    rb = [b[ts[i]] / b[ts[i - 1]] - 1 for i in range(1, len(ts))]
    ma, mb = sum(ra) / len(ra), sum(rb) / len(rb)
    va = sum((x - ma) ** 2 for x in ra)
    vb = sum((x - mb) ** 2 for x in rb)
    if va == 0 or vb == 0:
        return None
    return sum((x - ma) * (y - mb) for x, y in zip(ra, rb)) / (va * vb) ** 0.5


MAX_CORRELATED, CORR_LIMIT = 2, 0.8


def track(state, prices, cfg, now):
    """Acompanha sinais e operacoes abertas com os precos dados.
    prices: {ativo: preco}. Devolve eventos."""
    sigs = state.setdefault("signals", {})
    events = []

    def close(key, status, why):
        s = sigs[key]
        s.update(status=status, closed_at=now, close_reason=why)
        events.append({"t": now, "event": status, "id": key,
                       "asset": s["asset"], "reason": why})

    for key, s in list(sigs.items()):
        px = prices.get(s["asset"])
        if s["status"] == "ACTIVE":
            if px is not None and px <= s["plan"]["stop"]:
                close(key, "INVALIDATED", "preço atingiu o stop antes da entrada")
            elif px is not None and px > s["plan"]["tp"][0]:
                close(key, "INVALIDATED", "preço chegou ao TP1 sem dar entrada")
            elif now >= s["expires_at"]:
                close(key, "EXPIRED", "validade do sinal terminou")
            elif px is not None and px <= s["plan"]["entry_zone"][1]:
                s.update(status="TRIGGERED", triggered_at=now,
                         position=trade.open_position(
                             s["plan"], px, now, cfg["fee_pct"]))
                events.append({"t": now, "event": "TRIGGERED", "id": key,
                               "asset": s["asset"], "price": px})
        elif s["status"] == "TRIGGERED" and px is not None:
            # acompanhamento com o preço de cada scan (15 min): pavios mais
            # curtos do que isso podem não ser vistos
            pos = s["position"]
            for e in trade.step(pos, px, px, px, px, now):
                events.append(dict(e, t=now, id=key, asset=s["asset"]))
            if pos["closed"]:
                s.update(status="CLOSED", closed_at=now, result_r=pos["r"],
                         close_reason=pos["exit_reason"])
                tk = state.setdefault("track", {}).setdefault(
                    f"{s.get('mode', 'REAL')}:{s['strategy']}",
                    {"n": 0, "wins": 0, "sum_r": 0.0})
                tk["n"] += 1
                tk["wins"] += pos["r"] > 0
                tk["sum_r"] = round(tk["sum_r"] + pos["r"], 3)
        elif s["status"] in ("EXPIRED", "INVALIDATED", "CLOSED") and \
                now - s.get("closed_at", now) > 30 * 86400:
            del sigs[key]

    return events


def update_state(state, rows, cfg, now, daily=None):
    """Acompanha, expira, invalida e emite sinais. Devolve eventos."""
    sigs = state.setdefault("signals", {})
    events = track(state, {r["asset"]: r["price"] for r in rows}, cfg, now)
    live = {s["asset"] for s in sigs.values()
            if s["status"] in ("ACTIVE", "TRIGGERED")}
    halt = trading_halt(sigs, cfg, now)
    state["halt"] = halt
    if halt:
        for r in rows:
            if r["decision"]["decision"] == "LONG":
                r["decision"].update(decision="NO TRADE",
                                     reason="TRADING HALTED: " + halt)

    def used(mode):
        return sum(1 for s in sigs.values()
                   if s["status"] in ("ACTIVE", "TRIGGERED")
                   and s.get("mode", "REAL") == mode)
    trend_open = len(state.get("paper_trend", {}).get("positions", {}))
    slots = {m: cfg["max_open_positions"] - used(m)
             - (trend_open if m == "REAL" else 0) for m in ("REAL", "PAPER")}
    cands = sorted((r for r in rows if r["decision"]["decision"] == "LONG"
                    and r["asset"] not in live),
                   key=lambda r: -r["decision"]["score"])
    for r in cands:
        d = r["decision"]
        # exposicao efetiva: posicoes muito correlacionadas sao o mesmo risco
        held = live | set(state.get("paper_trend", {}).get("positions", {}))
        corr = {}
        for h in held:
            c = correlation((daily or {}).get(r["asset"]), (daily or {}).get(h))
            if c is not None:
                corr[h] = round(c, 2)
        if sum(1 for c in corr.values() if c > CORR_LIMIT) >= MAX_CORRELATED:
            d.update(decision="WATCHLIST", reason=(
                "exposição correlacionada: já há " + str(MAX_CORRELATED)
                + " posições com correlação acima de " + str(CORR_LIMIT)))
            continue
        if slots[d["mode"]] <= 0:
            d.update(decision="WATCHLIST",
                     reason="limite de operações em simultâneo atingido")
            continue
        slots[d["mode"]] -= 1
        live.add(r["asset"])
        key = f"{r['asset']}-{d['strategy']}-{now}"
        sig = {"id": key, "asset": r["asset"], "pair": d["venue"]["pair"],
               "venue": d["venue"]["name"], "direction": "LONG",
               "strategy": d["strategy"], "timeframe": "4H / 1D",
               "plan": d["plan"], "score": d["score"],
               "score_label": d["score_label"], "regime": d["regime"],
               "confidence": d["confidence"], "conflicts": d["conflicts"],
               "explain": explain(r), "issued_at": now,
               "expires_at": now + cfg["signal_expiry_hours"] * 3600,
               "status": "ACTIVE", "mode": d["mode"], "correlation": corr,
               "validation": validation.status(d["strategy"])}
        sig["validated"] = bool(sig["validation"].get("validated"))
        sigs[key] = sig
        events.append({"t": now, "event": "ISSUED", "id": key,
                       "asset": r["asset"], "signal": sig,
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
