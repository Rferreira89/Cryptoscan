"""Afinacao H5 (2026-10-16): shorts da sobrecompra so em mercado de descida.

Grelha (escrita antes de testar, backtest/afinacao.md): sinal em
{SHORT_X30, SHORT_ISOLADA} x filtro em {Q: regime do BTC "queda" no ultimo dia
fechado; S: BTC abaixo da SMA200 no ultimo dia fechado}. Corre com o metodo do
ringue (generic_trades sobre as velas espelhadas, judge contra o acaso).

Uso: python -m tools.afinacao_h05_short_queda <pasta_history> <saida.json>
"""
import calendar
import json
import random
import sys
import time

from engine import backtest as B, short as SH
from tools import arena_ringue as AR

DAY = AR.DAY
B_START = calendar.timegm((2021, 8, 1, 0, 0, 0))
B_END = calendar.timegm((2025, 10, 11, 0, 0, 0))
A_END = calendar.timegm((2026, 10, 11, 0, 0, 0))


def gates(btc):
    reg = AR.regime_by_day(btc)
    above = AR.btc_above(btc)
    return {"Q": lambda t: reg.get((t - DAY) // DAY) == "queda",
            "S": lambda t: above.get((t - DAY) // DAY) is False}


def gated(fn, gate):
    def f(m4):
        if not gate(m4[-1]["t"] + AR.H4):
            return None
        return fn(m4)
    return f


def run(bars):
    btc = bars["BTC"]
    AR.CTX.update(btc=btc, funding={}, oi={}, macro={}, ls={}, bars=bars, rank={})
    g = gates(btc)
    always = {k: True for k in AR.btc_above(btc)}
    mbars = {a: SH.mirror(c) for a, c in bars.items()}
    base = {"X30": AR.SHORT_SIGS["SHORT_X30"], "ISOLADA": AR.SHORT_SIGS["SHORT_ISOLADA"]}
    trades = {}
    for sn, fn in base.items():
        for gn, gt in g.items():
            key = f"{sn}_{gn}"
            out = []
            for a in sorted(bars):
                # B e A numa so passagem: t0 = inicio de B (so passado em cada vela)
                out += [t for _, t in AR.generic_trades(a, mbars[a], always, B_START, key,
                                                        gated(fn, gt))]
            trades[key] = sorted(out, key=lambda t: t["t"])
    return trades, mbars


def summary(trs, mbars, seed=7):
    if not trs:
        return {"n": 0}
    rng = random.Random(seed)
    j = AR.judge(trs, mbars, rng)
    rs = [t["r"] for t in trs]
    by_a = {}
    for t in trs:
        by_a.setdefault(t["asset"], []).append(t["r"])
    best = max(by_a, key=lambda a: sum(by_a[a]))
    rest = [t["r"] for t in trs if t["asset"] != best]
    years = {}
    for t in trs:
        years.setdefault(time.gmtime(t["t"]).tm_year, []).append(t["r"])
    j.update(sem_melhor=best, avg_sem_melhor=round(sum(rest) / len(rest), 3) if rest else None,
             anos={y: [len(v), round(sum(v) / len(v), 3)] for y, v in sorted(years.items())},
             dias_distintos=len({t["t"] // DAY for t in trs}),
             avg_r_sem_custo_juros=round(sum(rs) / len(rs), 3))
    # percentil do resultado face ao acaso (mesma distribuicao do judge)
    from engine import arena
    lists = [arena.control_rs(mbars[t["asset"]], t["t"], t["geo"], "LONG", random.Random(seed + 1),
                              reps=AR.REPS) for t in trs]
    ls = [c for c in lists if c]
    r2 = random.Random(seed + 2)
    means = [sum(r2.choice(c) for c in ls) / len(ls) for _ in range(1000)]
    mean = sum(rs) / len(rs)
    j["percentil_acaso"] = round(100 * sum(1 for m in means if m < mean) / len(means), 1)
    return j


def main(folder, dest):
    bars, skipped = B.load_all(folder, min_bars=1500)
    trades, mbars = run(bars)
    res = {"moedas": len(bars), "fora": skipped, "janelas": {}}
    for key, trs in trades.items():
        wb = [t for t in trs if B_START <= t["t"] < B_END]
        wa = [t for t in trs if B_END <= t["t"] < A_END]
        wc = [t for t in trs if A_END - 90 * DAY <= t["t"] < A_END]
        res["janelas"][key] = {"B": summary(wb, mbars), "A": summary(wa, mbars),
                               "C90": {"n": len(wc)}}
        b, a = res["janelas"][key]["B"], res["janelas"][key]["A"]
        print(key, "B:", {k: b.get(k) for k in ("n", "avg_r", "acaso_mediana", "acaso_p95",
                                                "percentil_acaso", "avg_sem_melhor", "anos")},
              "| A:", {k: a.get(k) for k in ("n", "avg_r", "acaso_p95", "percentil_acaso")},
              "| C90:", len(wc), flush=True)
    with open(dest, "w") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
