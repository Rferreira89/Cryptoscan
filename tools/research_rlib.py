"""Base comum das investigacoes com stop e objetivos (operacoes medidas em R)
em velas de 4H ou de 1H. Usada por tools/research_bounce.py e
tools/research_day1h.py.

Metodo (o mesmo de tools/research.py, adaptado a operacoes com plano):
- o sinal e decidido no FECHO de uma vela, so com velas ja fechadas, e a
  entrada e na ABERTURA da vela seguinte;
- a operacao e gerida por engine/trade.py (a mesma logica do sistema ao
  vivo): stop, vendas parciais nos objetivos, stop na entrada depois do
  1.o objetivo, e se stop e objetivo sao tocados na mesma vela conta o stop;
- saida por tempo ao fim de `hold_s` segundos, ao fecho da vela;
- custos: 0,25% de comissao por lado (Bybit UE) + 0,1% de slippage por lado
  (na entrada, no stop e na saida por tempo; os objetivos sao ordens limite);
- carteira: no maximo `max_pos` operacoes, uma por moeda, `frac` do capital
  em cada uma; curva de capital marcada ao fecho de cada dia (UTC);
- teste contra o acaso: para cada operacao, a mesma geometria (stop e
  objetivos a mesma distancia percentual da entrada, mesmas parciais, mesma
  saida por tempo, mesmos custos) aplicada a entradas ao acaso na mesma
  moeda ate +-15 dias da entrada real.
"""
import bisect
import random

from engine import trade

DAY = 86400
FEE_PCT, SLIP_PCT = 0.25, 0.1


def ema(xs, n):
    out, k, e = [None] * len(xs), 2 / (n + 1), None
    for i, x in enumerate(xs):
        if i == n - 1:
            e = sum(xs[:n]) / n
        elif i >= n:
            e = x * k + e * (1 - k)
        out[i] = e
    return out


def sma(xs, n):
    out, s = [None] * len(xs), 0.0
    for i, x in enumerate(xs):
        s += x
        if i >= n:
            s -= xs[i - n]
        if i >= n - 1:
            out[i] = s / n
    return out


def rsi(c, n=14):
    """RSI de Wilder. O valor em i usa fechos ate i (inclusive)."""
    out = [None] * len(c)
    if len(c) <= n:
        return out
    g = sum(max(c[i] - c[i - 1], 0) for i in range(1, n + 1)) / n
    l = sum(max(c[i - 1] - c[i], 0) for i in range(1, n + 1)) / n
    out[n] = 100 if l == 0 else 100 - 100 / (1 + g / l)
    for i in range(n + 1, len(c)):
        d = c[i] - c[i - 1]
        g = (g * (n - 1) + max(d, 0)) / n
        l = (l * (n - 1) + max(-d, 0)) / n
        out[i] = 100 if l == 0 else 100 - 100 / (1 + g / l)
    return out


def atr(bars, n=14):
    """ATR de Wilder. O valor em i usa velas ate i (inclusive)."""
    out = [None] * len(bars)
    if len(bars) <= n:
        return out
    tr = [bars[0]["h"] - bars[0]["l"]] + [
        max(bars[i]["h"] - bars[i]["l"], abs(bars[i]["h"] - bars[i - 1]["c"]),
            abs(bars[i]["l"] - bars[i - 1]["c"])) for i in range(1, len(bars))]
    a = sum(tr[1:n + 1]) / n
    out[n] = a
    for i in range(n + 1, len(bars)):
        a = (a * (n - 1) + tr[i]) / n
        out[i] = a
    return out


def plan_at(sig, o):
    """Plano concreto na abertura `o`. None se o plano deixou de ser valido
    (abertura no stop ou abaixo, stop demasiado perto, objetivo ja passado)."""
    stop = sig["stop"]
    if o <= stop:
        return None
    if sig.get("min_stop") and (o - stop) / o < sig["min_stop"]:
        return None
    if sig.get("tp_r"):
        tps = [o + sig["tp_r"] * (o - stop)]
    else:
        tps = list(sig["tp"])
    if o >= tps[0]:
        return None
    return {"stop": stop, "tp": tps, "partials": list(sig["partials"])}


def run_trade(bars, j, plan, tf, hold_s, fee_pct=FEE_PCT, slip_pct=SLIP_PCT):
    """Abre na abertura da vela j e segue ate fechar. So le velas de j em
    diante. Devolve (posicao fechada, indice da ultima vela) ou None se o
    historico acabar antes do fecho."""
    b = bars[j]
    pos = trade.open_position(plan, b["o"], b["t"], fee_pct, slip_pct)
    k = j
    while True:
        x = bars[k]
        advance(pos, x, tf, hold_s)
        if pos["closed"]:
            return pos, k
        k += 1
        if k >= len(bars):
            return None


def advance(pos, x, tf, hold_s):
    """Uma vela: stop/objetivos e, se continuar aberta, saida por tempo."""
    trade.step(pos, x["o"], x["h"], x["l"], x["c"], x["t"] + tf)
    if not pos["closed"] and x["t"] + tf - pos["opened_at"] >= hold_s:
        trade._sell(pos, pos["remaining"], x["c"] * (1 - pos["slip"]))
        trade._finish(pos, "TIME", x["t"] + tf)


def simulate(data, sigs, tf, hold_s, universe=None, max_pos=4, frac=0.25,
             fee_pct=FEE_PCT, slip_pct=SLIP_PCT):
    """data: {moeda: velas}. sigs: {moeda: {t_abertura_da_entrada: sinal}}.
    O sinal em t foi decidido no fecho da vela anterior (t - tf).
    Devolve (curva [(dia, capital)], operacoes fechadas)."""
    uni = sorted(universe if universe is not None else data)
    idx = {a: {b["t"]: i for i, b in enumerate(data[a])} for a in uni}
    by_t = {}
    for a in uni:
        for t, s in sigs.get(a, {}).items():
            by_t.setdefault(t, []).append((s["rank"], a, s))
    times = sorted(set(t for a in uni for t in idx[a]))
    cash, pos, curve, trades = 1.0, {}, [], []

    def equity():
        return cash + sum(p["notional"] + p["units"] * (
            p["p"]["realized"] + p["p"]["remaining"] / 100
            * (p["last"] - p["p"]["entry"])) for p in pos.values())

    for t in times:
        if t in by_t:                              # entradas na abertura
            eq = equity()
            for _, a, s in sorted(by_t[t], key=lambda z: (z[0], z[1])):
                i = idx[a].get(t)
                if i is None or a in pos or len(pos) >= max_pos:
                    continue
                o = data[a][i]["o"]
                plan = plan_at(s, o)
                notional = min(frac * eq, cash)
                if plan is None or notional < 0.01 * eq:
                    continue
                p = trade.open_position(plan, o, t, fee_pct, slip_pct)
                cash -= notional
                pos[a] = {"p": p, "notional": notional, "last": o, "i": i,
                          "units": notional / p["entry"], "plan": plan, "o": o}
        for a in list(pos):                        # gestao na vela
            i = idx[a].get(t)
            if i is None:
                continue
            x, q = data[a][i], pos[a]
            advance(q["p"], x, tf, hold_s)
            q["last"] = x["c"]
            if q["p"]["closed"]:
                pnl = q["units"] * q["p"]["realized"]
                cash += q["notional"] + pnl
                trades.append({
                    "asset": a, "i": q["i"], "entry_t": t if i == q["i"]
                    else data[a][q["i"]]["t"], "exit_t": q["p"]["closed_at"],
                    "entry_d": data[a][q["i"]]["t"] // DAY,
                    "r": q["p"]["r"], "ret": pnl / q["notional"],
                    "exit": q["p"]["exit_reason"],
                    "risk_pct": 100 * (q["o"] - q["plan"]["stop"]) / q["o"],
                    "geo": {"stop": q["plan"]["stop"] / q["o"] - 1,
                            "tp": [z / q["o"] - 1 for z in q["plan"]["tp"]],
                            "partials": q["plan"]["partials"]}})
                del pos[a]
        if (t + tf) % DAY == 0:
            curve.append((t // DAY, equity()))
    return curve, trades


def control_rs(bars, i, geo, tf, hold_s, window, fee_pct=FEE_PCT,
               slip_pct=SLIP_PCT):
    """R de todas as entradas de controlo possiveis: abertura de cada vela
    ate `window` velas antes ou depois da entrada real i, mesma geometria."""
    out = []
    for j in range(max(0, i - window), min(len(bars) - 2, i + window) + 1):
        o = bars[j]["o"]
        plan = {"stop": o * (1 + geo["stop"]),
                "tp": [o * (1 + z) for z in geo["tp"]],
                "partials": geo["partials"]}
        r = run_trade(bars, j, plan, tf, hold_s, fee_pct, slip_pct)
        if r is not None:
            out.append(r[0]["r"])
    return out


def vs_random(trades, data, tf, hold_s, window, reps=1000, seed=7):
    """R medio real contra a distribuicao do R medio de `reps` series de
    entradas ao acaso (uma entrada de controlo por operacao real)."""
    if not trades:
        return {"n": 0, "vantagem": False}
    rng = random.Random(seed)
    pools = [control_rs(data[t["asset"]], t["i"], t["geo"], tf, hold_s, window)
             for t in trades]
    pools = [p for p in pools if p]
    real = sum(t["r"] for t in trades) / len(trades)
    dist = sorted(sum(rng.choice(p) for p in pools) / len(pools)
                  for _ in range(reps))
    p95 = dist[int(0.95 * (len(dist) - 1))]
    return {"n": len(trades), "r_real": round(real, 3),
            "r_acaso_mediana": round(dist[len(dist) // 2], 3),
            "r_acaso_p95": round(p95, 3),
            "percentil": round(100 * sum(1 for x in dist if x < real)
                               / len(dist), 1),
            "vantagem": real > p95}


def rstats(tr):
    if not tr:
        return {"n": 0}
    r = [t["r"] for t in tr]
    w = [x for x in r if x > 0]
    ex = {}
    for t in tr:
        ex[t["exit"]] = ex.get(t["exit"], 0) + 1
    return {"n": len(r), "win_rate": round(100 * len(w) / len(r), 1),
            "r_medio": round(sum(r) / len(r), 3),
            "ret_medio_pct": round(100 * sum(t["ret"] for t in tr) / len(tr), 2),
            "risco_medio_pct": round(sum(t["risk_pct"] for t in tr) / len(tr), 2),
            "custo_medio_r": round(sum(
                2 * (FEE_PCT + SLIP_PCT) / t["risk_pct"] for t in tr) / len(tr), 3),
            "saidas": ex}


def closed_day_index(ts, tc, tf):
    """Indice da ultima vela (de duracao tf, aberturas em ts) ja FECHADA no
    instante tc; -1 se nenhuma."""
    return bisect.bisect_right(ts, tc - tf) - 1


def evaluate(name, grid, runner, data, tf, hold_of, window_bars, majors,
             base_curve, d0, ds, d1, warm=None, min_oos=40, reps=1000):
    """Grelha -> walk-forward no desenho -> reserva (uma vez, so a
    configuracao escolhida) -> teste contra o acaso -> veredicto.
    runner(cfg, universo) -> (curva, operacoes); hold_of(cfg) -> segundos."""
    import datetime as dt
    import json
    import time
    from tools.research import metrics
    from tools.research_dip import walk_forward

    curves, cmaj, trades, g = {}, {}, {}, {}
    for cfg in grid:
        key = json.dumps(cfg, sort_keys=True)
        curves[key], trades[key] = runner(cfg, None)
        cmaj[key] = runner(cfg, majors)[0]
        g[key] = {"all": metrics(curves[key], d0, ds),
                  "majors21": metrics(cmaj[key], d0, ds),
                  "trades": rstats([t for t in trades[key]
                                    if d0 <= t["entry_d"] < ds])}
    share = sum(1 for v in g.values() if v["all"]["return_pct"] > 0) / len(g)
    folds, oos, last, n_oos = walk_forward(curves, trades, d0, ds)
    _, oos_m, _, _ = walk_forward(cmaj, {}, d0, ds)
    _, base_oos, _, _ = walk_forward({"b": base_curve}, {}, d0, ds)
    fpos = sum(1 for f in folds if f["test"]["return_pct"] > 0)
    oos_tr = [t for f in folds for t in trades[f["chosen"]]
              if f["test_days"][0] <= t["entry_d"] < f["test_days"][1]]
    crit = {"1_oos_retorno_e_sharpe": oos["return_pct"] > 0 and oos["sharpe"] > 0.5,
            "2_janelas_positivas": fpos / len(folds) >= 0.6,
            "3_grelha_estavel": share >= 0.75,
            "4_grandes_moedas_2021": oos_m["return_pct"] > 0,
            "5_melhor_que_btc_sma200": oos["sharpe"] > base_oos["sharpe"]}
    # RESERVA: uma unica avaliacao, so da configuracao escolhida
    cfg = json.loads(last)
    hold_tr = [t for t in trades[last] if ds <= t["entry_d"] < d1]
    hold = {"all": metrics(curves[last], ds, d1),
            "majors21": metrics(cmaj[last], ds, d1),
            "baseline_btc_sma200": metrics(base_curve, ds, d1),
            "trades": rstats(hold_tr)}
    crit["6_reserva_sharpe_positivo"] = hold["all"]["sharpe"] > 0
    # ACASO (7.o criterio): todas as operacoes fora da amostra
    rnd = {"walk_forward": {"n": 0}, "reserva": {"n": 0}}
    by_h = {}
    for f in folds:
        h = hold_of(json.loads(f["chosen"]))
        by_h.setdefault(h, []).extend(
            t for t in trades[f["chosen"]]
            if f["test_days"][0] <= t["entry_d"] < f["test_days"][1])
    if len(by_h) == 1:
        h = next(iter(by_h))
        rnd["walk_forward"] = vs_random(by_h[h], data, tf, h, window_bars, reps)
    else:       # dobras com permanencias diferentes: controlos por dobra
        rnd["walk_forward"] = {"por_permanencia": {
            str(h): vs_random(v, data, tf, h, window_bars, reps)
            for h, v in by_h.items()}}
    rnd["reserva"] = vs_random(hold_tr, data, tf, hold_of(cfg), window_bars, reps)
    # veredicto do 7.o criterio: conjunto fora da amostra com a geometria de
    # cada operacao e a permanencia da configuracao que a gerou
    allp, real = [], []
    for h, v in list(by_h.items()) + [(hold_of(cfg), hold_tr)]:
        for t in v:
            p = control_rs(data[t["asset"]], t["i"], t["geo"], tf, h, window_bars)
            if p:
                allp.append(p)
                real.append(t["r"])
    if real:
        rng = random.Random(11)
        m = sum(real) / len(real)
        dist = sorted(sum(rng.choice(p) for p in allp) / len(allp)
                      for _ in range(reps))
        p95 = dist[int(0.95 * (len(dist) - 1))]
        rnd["fora_da_amostra"] = {
            "n": len(real), "r_real": round(m, 3),
            "r_acaso_mediana": round(dist[len(dist) // 2], 3),
            "r_acaso_p95": round(p95, 3),
            "percentil": round(100 * sum(1 for x in dist if x < m) / len(dist), 1),
            "vantagem": m > p95}
    else:
        rnd["fora_da_amostra"] = {"n": 0, "vantagem": False}
    crit["7_acima_do_p95_do_acaso"] = bool(rnd["fora_da_amostra"]["vantagem"])
    passed = all(crit.values())
    verdict = ("AMOSTRA INSUFICIENTE" if n_oos < min_oos else
               "CANDIDATA" if passed else "NAO VALIDADA")
    iso = lambda d: str(dt.date(1970, 1, 1) + dt.timedelta(days=d))
    res = {"generated_at": int(time.time()), "hypothesis": name,
           "assets": len(data),
           "window": {"design": [iso(d0), iso(ds - 1)],
                      "holdout": [iso(ds), iso(d1 - 1)]},
           "costs": {"fee_pct": FEE_PCT, "slippage_pct": SLIP_PCT},
           "grid": g, "grid_positive_share": round(share, 2),
           "baseline_btc_sma200_design": metrics(base_curve, d0, ds),
           "walk_forward": {"folds": folds, "oos": oos, "folds_positive": fpos,
                            "oos_trades": n_oos, "oos_trade_stats": rstats(oos_tr),
                            "majors21": oos_m, "baseline": base_oos},
           "deploy_config": cfg, "holdout": hold, "random": rnd,
           "criteria": crit, "passed_all_seven": passed, "verdict": verdict}
    if warm is not None and warm < d0:
        res["info_old_period"] = {
            "days": [iso(warm), iso(d0 - 1)],
            "all": metrics(curves[last], warm, d0),
            "baseline": metrics(base_curve, warm, d0),
            "trades": rstats([t for t in trades[last]
                              if warm <= t["entry_d"] < d0])}
    return res
