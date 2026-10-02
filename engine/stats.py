"""Performance Analytics, Walk-Forward e Monte Carlo sobre listas de
operacoes fechadas. Cada operacao: {r, risk_pct, entry_t, exit_t, ...}.
"""
import math
import random

YEAR = 365 * 86400


def select(cands, results, cfg, min_score=None, strategies=None,
           max_conflicts=1):
    """Aplica as regras de carteira do sistema ao vivo, por ordem temporal:
    score minimo, menos de 2 conflitos, uma operacao por ativo e limite de
    operacoes em simultaneo. Devolve as operacoes fechadas escolhidas."""
    ms = cfg["min_score"] if min_score is None else min_score
    order = sorted(range(len(cands)),
                   key=lambda k: (cands[k]["t"], -cands[k]["score"]))
    busy, open_until, out = {}, [], []
    for k in order:
        c, r = cands[k], results[k]
        if c["score"] < max(ms, 50) or c["n_conflicts"] > max_conflicts:
            continue
        if strategies is not None and c["strategy"] not in strategies:
            continue
        t = c["t"]
        if busy.get(c["asset"], 0) > t:
            continue
        open_until = [x for x in open_until if x > t]
        if len(open_until) >= cfg["max_open_positions"]:
            continue
        if r["status"] == "CLOSED":
            end = r["exit_t"]
            out.append(dict(c, **r))
        elif r["status"] == "OPEN_AT_END":
            end = float("inf")
        else:                                   # expirado/invalidado: 12h
            end = t + 3 * 14400
        busy[c["asset"]] = end
        open_until.append(end)
    return out


def streaks(rs):
    best = worst = cur_w = cur_l = 0
    for r in rs:
        if r > 0:
            cur_w, cur_l = cur_w + 1, 0
        else:
            cur_l, cur_w = cur_l + 1, 0
        best, worst = max(best, cur_w), max(worst, cur_l)
    return best, worst


def equity(trades):
    """Curva de capital: cada operacao arrisca risk_pct do capital atual."""
    eq, peak, dd, curve = 1.0, 1.0, 0.0, []
    for t in sorted(trades, key=lambda x: x["exit_t"]):
        eq *= 1 + t["r"] * t["risk_pct"] / 100
        peak = max(peak, eq)
        dd = max(dd, 1 - eq / peak)
        curve.append((t["exit_t"], eq))
    return eq, dd, curve


def boot_ci(rs, n=2000, seed=7):
    """IC 95% da expectancy por reamostragem."""
    if len(rs) < 10:
        return None
    rnd = random.Random(seed)
    m = sorted(sum(rnd.choices(rs, k=len(rs))) / len(rs) for _ in range(n))
    return [round(m[int(0.025 * n)], 3), round(m[int(0.975 * n)], 3)]


def metrics(trades, span_s=None):
    rs = [t["r"] for t in sorted(trades, key=lambda x: x["exit_t"])]
    n = len(rs)
    if n == 0:
        return {"n": 0}
    wins, losses = [r for r in rs if r > 0], [r for r in rs if r <= 0]
    gw, gl = sum(wins), -sum(losses)
    eq, dd, curve = equity(trades)
    best, worst = streaks(rs)
    mean = sum(rs) / n
    sd = math.sqrt(sum((r - mean) ** 2 for r in rs) / n) if n > 1 else 0
    dsd = math.sqrt(sum(min(r, 0) ** 2 for r in rs) / n)
    span = span_s or (max(t["exit_t"] for t in trades)
                      - min(t["entry_t"] for t in trades)) or 1
    per_year = n / (span / YEAR)
    cagr = eq ** (YEAR / span) - 1 if eq > 0 else -1
    return {
        "n": n, "win_rate": round(100 * len(wins) / n, 1),
        "avg_win_r": round(gw / len(wins), 2) if wins else 0,
        "avg_loss_r": round(-gl / len(losses), 2) if losses else 0,
        "expectancy_r": round(mean, 3), "expectancy_ci95": boot_ci(rs),
        "profit_factor": round(gw / gl, 2) if gl > 0 else None,
        "total_r": round(sum(rs), 1),
        "return_pct": round((eq - 1) * 100, 1),
        "cagr_pct": round(cagr * 100, 1),
        "max_drawdown_pct": round(dd * 100, 1),
        # por operacao, anualizado pelo numero de operacoes por ano
        "sharpe": round(mean / sd * math.sqrt(per_year), 2) if sd else None,
        "sortino": round(mean / dsd * math.sqrt(per_year), 2) if dsd else None,
        "calmar": round(cagr / dd, 2) if dd > 0 else None,
        "recovery_factor": round((eq - 1) / dd, 2) if dd > 0 else None,
        "longest_win_streak": best, "longest_loss_streak": worst,
        "avg_duration_days": round(sum(t["exit_t"] - t["entry_t"]
                                       for t in trades) / n / 86400, 1),
        "trades_per_year": round(per_year, 1)}


def group(trades, key, span_s=None):
    g = {}
    for t in trades:
        g.setdefault(key(t), []).append(t)
    return {str(k): metrics(v, span_s) for k, v in sorted(g.items(), key=lambda kv: str(kv[0]))}


def monte_carlo(trades, runs=5000, seed=11):
    """Reamostra a sequencia de operacoes: distribuicao de resultados."""
    pairs = [(t["r"], t["risk_pct"]) for t in trades]
    if len(pairs) < 30:
        return None
    rnd, n = random.Random(seed), len(pairs)
    finals, dds, lstreak = [], [], []
    for _ in range(runs):
        eq = peak = 1.0
        dd = cur = worst = 0
        for r, rp in rnd.choices(pairs, k=n):
            eq *= 1 + r * rp / 100
            peak = max(peak, eq)
            dd = max(dd, 1 - eq / peak)
            cur = cur + 1 if r <= 0 else 0
            worst = max(worst, cur)
        finals.append(eq)
        dds.append(dd)
        lstreak.append(worst)
    q = lambda xs, p: sorted(xs)[min(len(xs) - 1, int(p * len(xs)))]
    pc = lambda x: round((x - 1) * 100, 1)
    return {"runs": runs, "trades_per_run": n,
            "return_pct": {"p5": pc(q(finals, .05)), "p50": pc(q(finals, .5)),
                           "p95": pc(q(finals, .95))},
            "max_drawdown_pct": {"p50": round(q(dds, .5) * 100, 1),
                                 "p95": round(q(dds, .95) * 100, 1),
                                 "p99": round(q(dds, .99) * 100, 1)},
            "longest_loss_streak": {"p50": q(lstreak, .5), "p95": q(lstreak, .95)},
            "prob_loss_pct": round(100 * sum(f < 1 for f in finals) / runs, 1),
            "prob_drawdown_over_20pct": round(
                100 * sum(d > 0.20 for d in dds) / runs, 1)}


def walk_forward(cands, results, cfg, t0, t1, train_s, test_s, grid,
                 min_train_n=30):
    """Em cada janela: escolhe na parte de treino a configuracao com melhor
    expectancy e aplica-a, sem alteracoes, a janela de teste seguinte."""
    folds, oos = [], []
    start = t0
    while start + train_s + test_s <= t1:
        tr0, tr1, te1 = start, start + train_s, start + train_s + test_s
        best = None
        for g in grid:
            tr = [t for t in select(cands, results, cfg, g["min_score"],
                                    g["strategies"])
                  if tr0 <= t["t"] < tr1 and t["exit_t"] < tr1]
            if len(tr) < min_train_n:
                continue
            e = sum(t["r"] for t in tr) / len(tr)
            if best is None or e > best[0]:
                best = (e, g, len(tr))
        fold = {"train": [tr0, tr1], "test": [tr1, te1]}
        if best is None or best[0] <= 0:
            fold.update(chosen=None, note="nenhuma configuracao com "
                        "expectancy positiva no treino: nao operar", n=0)
        else:
            te = [t for t in select(cands, results, cfg, best[1]["min_score"],
                                    best[1]["strategies"])
                  if tr1 <= t["t"] < te1]
            oos += te
            fold.update(chosen=best[1], train_expectancy=round(best[0], 3),
                        train_n=best[2], n=len(te),
                        test_expectancy=round(sum(t["r"] for t in te) / len(te), 3)
                        if te else None)
        folds.append(fold)
        start += test_s
    return folds, oos
