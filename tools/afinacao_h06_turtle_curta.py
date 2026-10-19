"""Afinacao H6 (2026-10-19): Tartarugas com saidas curtas (TURTLE_CURTA).

O gatilho e o do TURTLE do ringue (fecho de 4H acima do maximo dos 20 dias
anteriores, fecho anterior abaixo; BTC acima da SMA200); so mudam o stop
(multiplos de N, ATR diario de 20 dias), os objetivos e o tempo maximo.
Grelha escrita antes de testar (backtest/afinacao.md, H6).

Uso: python -m tools.afinacao_h06_turtle_curta <pasta_history> <saida.json>
"""
import calendar
import json
import random
import sys
import time

from engine import arena, backtest as B, paper_bounce as PB
from tools import arena_ringue as AR

DAY, H4 = AR.DAY, AR.H4
B_START = calendar.timegm((2021, 8, 1, 0, 0, 0))
B_END = calendar.timegm((2024, 10, 11, 0, 0, 0))

# nome: (stop em N, objetivos em R, partes, dias, trail_r)
GRID = {
    "T1": (2.0, (1.5,), (100,), 5, None),
    "T2": (2.0, (1.0, 2.0), (50, 50), 5, None),
    "T3": (1.5, (1.5, 3.0), (50, 50), 10, 1.0),
    "T4": (1.5, (1.0, 2.0), (50, 50), 5, None),
    "T5": (1.0, (1.5, 3.0), (50, 50), 5, 1.0),
    "T6": (2.0, (2.0, 5.0), (50, 50), 10, 1.0),
}


def turtle_core(c4):
    """(maximo de 20 dias, N) quando a ultima vela fechada rompe; senao None.
    Igual a arena_ringue.sig_turtle, so com dias completos ja fechados."""
    d = [x for x in B.daily(c4[-240:]) if x["t"] + DAY <= c4[-1]["t"] + H4]
    if len(d) < 25:
        return None
    hi20 = max(x["h"] for x in d[-21:-1])
    if not (c4[-1]["c"] > hi20 >= c4[-2]["c"]):
        return None
    tr = [max(d[k]["h"], d[k - 1]["c"]) - min(d[k]["l"], d[k - 1]["c"])
          for k in range(len(d) - 20, len(d))]
    return hi20, sum(tr) / 20


def turtle_var(k_n, rs, parts, days, trail):
    def f(c4):
        core = turtle_core(c4)
        if not core:
            return None
        hi20, n = core
        e = c4[-1]["c"]
        stop = e - k_n * n
        if not 0 < stop < e * 0.995:
            return None
        r = e - stop
        p = {"stop": stop, "tp": [e + m * r for m in rs], "partials": list(parts),
             "breakeven": True, "hold_s": days * DAY, "atr": PB.atr(c4[-100:])[-1],
             "gatilho": f"rompimento do máximo de 20 dias ({hi20:.6g}), saída curta"}
        if trail:
            p["trail_r"] = trail
        return p
    return f


def pct_vs_random(trs, bars, seed=8):
    lists = [arena.control_rs(bars[t["asset"]], t["t"], t["geo"], "LONG",
                              random.Random(seed + i), reps=AR.REPS) for i, t in enumerate(trs)]
    ls = [c for c in lists if c]
    if not ls:
        return None
    r2 = random.Random(seed + 2)
    means = [sum(r2.choice(c) for c in ls) / len(ls) for _ in range(1000)]
    mean = sum(t["r"] for t in trs) / len(trs)
    return round(100 * sum(1 for m in means if m < mean) / len(means), 1)


def summary(trs, bars, rmap, seed=7, regimes=True):
    if not trs:
        return {"n": 0}
    j = AR.judge(trs, bars, random.Random(seed))
    j["percentil_acaso"] = pct_vs_random(trs, bars)
    by_a = {}
    for t in trs:
        by_a.setdefault(t["asset"], []).append(t["r"])
    best = max(by_a, key=lambda a: sum(by_a[a]))
    rest = [t["r"] for t in trs if t["asset"] != best]
    years = {}
    for t in trs:
        years.setdefault(time.gmtime(t["t"]).tm_year, []).append(t["r"])
    j.update(sem_melhor=best, avg_sem_melhor=round(sum(rest) / len(rest), 3) if rest else None,
             anos={y: [len(v), round(sum(v) / len(v), 3)] for y, v in sorted(years.items())})
    if regimes:
        j["por_regime"] = {}
        for rg in ("subida", "lateral", "queda"):
            sub = [t for t in trs if rmap.get((t["t"] - DAY) // DAY) == rg]
            if sub:
                s = AR.judge(sub, bars, random.Random(seed))
                s["percentil_acaso"] = pct_vs_random(sub, bars)
                j["por_regime"][rg] = {k: s[k] for k in ("n", "avg_r", "acaso_mediana",
                                                         "acaso_p95", "percentil_acaso")}
    return j


def run(bars):
    btc = bars["BTC"]
    AR.CTX.update(btc=btc, funding={}, oi={}, macro={}, ls={}, bars=bars, rank={})
    above = AR.btc_above(btc)
    trades = {}
    for key, cfg in GRID.items():
        out = []
        for a in sorted(bars):
            out += [t for _, t in AR.generic_trades(a, bars[a], above, B_START, key,
                                                    turtle_var(*cfg))]
        trades[key] = sorted(out, key=lambda t: t["t"])
        print(key, len(trades[key]), flush=True)
    return trades


def main(folder, dest):
    bars, skipped = B.load_all(folder, min_bars=1500)
    end = max(x["t"] for x in bars["BTC"]) + H4
    rmap = AR.regime_by_day(bars["BTC"])
    trades = run(bars)
    res = {"moedas": len(bars), "fora": skipped, "fim": end, "janelas": {}}
    for key, trs in trades.items():
        w = {"B": [t for t in trs if B_START <= t["t"] < B_END],
             "A": [t for t in trs if t["t"] >= B_END],
             "C90": [t for t in trs if t["t"] >= end - 90 * DAY]}
        res["janelas"][key] = {k: summary(v, bars, rmap) for k, v in w.items()}
        for k in ("B", "A", "C90"):
            x = res["janelas"][key][k]
            print(key, k, {q: x.get(q) for q in ("n", "avg_r", "acaso_mediana", "acaso_p95",
                                                 "percentil_acaso", "avg_sem_melhor", "anos")},
                  {rg: (v["n"], v["avg_r"], v["acaso_p95"], v["percentil_acaso"])
                   for rg, v in (x.get("por_regime") or {}).items()}, flush=True)
    with open(dest, "w") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
