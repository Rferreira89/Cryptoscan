"""Afinacao H7 (2026-10-21): short do rompimento falhado (SHORT_FALHADO).

Precos reais: rompimento na vela b = gatilho do TURTLE (fecho acima do maximo
dos 20 dias anteriores, fecho anterior abaixo); falha na vela i (b < i <= b+K)
= primeiro fecho de novo abaixo desse maximo. Short na abertura seguinte,
stop no maximo de b..i + 0,1 ATR(4H). Corre sobre as velas espelhadas, como
todos os shorts do ringue. Grelha escrita antes de testar (afinacao.md, H7).

Uso: python -m tools.afinacao_h07_falhado <pasta_history> <saida.json>
"""
import calendar
import json
import random
import sys
import time

from engine import backtest as B, paper_bounce as PB, short as SH
from tools import arena_ringue as AR
from tools.afinacao_h06_turtle_curta import pct_vs_random, turtle_core

DAY, H4 = AR.DAY, AR.H4
B_START = calendar.timegm((2021, 8, 1, 0, 0, 0))
B_END = calendar.timegm((2024, 10, 11, 0, 0, 0))

# nome: (K velas, objetivos em R, partes, dias)
GRID = {
    "F1": (1, (1.0, 2.0), (50, 50), 3),
    "F2": (2, (1.0, 2.0), (50, 50), 3),
    "F3": (3, (1.0, 2.0), (50, 50), 5),
    "F4": (2, (1.5,), (100,), 3),
    "F5": (2, (1.5, 3.0), (50, 50), 5),
    "F6": (6, (1.0, 2.0), (50, 50), 5),
}


def falha_core(r, k_max):
    """(hi20, b, stop_real) se a ultima vela fechada de `r` (precos reais) e o
    primeiro fecho abaixo do maximo de 20 dias depois de um rompimento ate
    k_max velas antes; senao None. So usa r (velas ja fechadas)."""
    n = len(r)
    if n < 260 or not r[-1]["c"] < r[-2]["c"]:
        return None
    for j in range(1, k_max + 1):
        b = n - 1 - j
        core = turtle_core(r[:b + 1])
        if not core:
            continue
        hi20 = core[0]
        if r[-1]["c"] >= hi20 or any(x["c"] < hi20 for x in r[b + 1:n - 1]):
            continue
        at = PB.atr(r[-100:])[-1]
        if at is None:
            return None
        return hi20, b, max(x["h"] for x in r[b:]) + 0.1 * at
    return None


def falhado_var(k_max, rs, parts, days):
    """Funcao de sinal no ESPELHO (formato SHORT_SIGS)."""
    def f(m4):
        if len(m4) < 260 or not m4[-1]["c"] > m4[-2]["c"]:   # real: fecho a descer
            return None
        r = SH.mirror(m4[-260:])
        core = falha_core(r, k_max)
        if not core:
            return None
        hi20, _, stop_real = core
        e_real = r[-1]["c"]
        if not 0.005 <= stop_real / e_real - 1 <= 0.15:
            return None
        e, stop = m4[-1]["c"], 1 / stop_real
        risk = e - stop
        return {"stop": stop, "tp": [e + m * risk for m in rs], "partials": list(parts),
                "breakeven": True, "hold_s": days * DAY, "atr": PB.atr(m4[-100:])[-1],
                "gatilho": f"rompimento falhado do máximo de 20 dias ({hi20:.6g}): compradores presos"}
    return f


def summary(trs, bars, rmap, seed=7):
    if not trs:
        return {"n": 0}
    j = AR.judge(trs, bars, random.Random(seed))
    j["percentil_acaso"] = pct_vs_random(trs, bars)
    by_a, years = {}, {}
    for t in trs:
        by_a.setdefault(t["asset"], []).append(t["r"])
        years.setdefault(time.gmtime(t["t"]).tm_year, []).append(t["r"])
    best = max(by_a, key=lambda a: sum(by_a[a]))
    rest = [t["r"] for t in trs if t["asset"] != best]
    j.update(sem_melhor=best, avg_sem_melhor=round(sum(rest) / len(rest), 3) if rest else None,
             anos={y: [len(v), round(sum(v) / len(v), 3)] for y, v in sorted(years.items())},
             por_regime={})
    for rg in ("subida", "lateral", "queda"):
        sub = [t for t in trs if rmap.get((t["t"] - DAY) // DAY) == rg]
        if sub:
            s = AR.judge(sub, bars, random.Random(seed))
            j["por_regime"][rg] = {k: s[k] for k in ("n", "avg_r", "acaso_mediana", "acaso_p95")}
            j["por_regime"][rg]["percentil_acaso"] = pct_vs_random(sub, bars)
    return j


def main(folder, dest, only=None):
    bars, skipped = B.load_all(folder, min_bars=1500)
    btc = bars["BTC"]
    AR.CTX.update(btc=btc, funding={}, oi={}, macro={}, ls={}, bars=bars, rank={})
    end = max(x["t"] for x in btc) + H4
    rmap = AR.regime_by_day(btc)
    always = {k: True for k in AR.btc_above(btc)}            # shorts: sem filtro do BTC
    mbars = {a: SH.mirror(c) for a, c in bars.items()}
    res = {"moedas": len(bars), "fora": skipped, "fim": end, "janelas": {}}
    for key, cfg in GRID.items():
        if only and key not in only:
            continue
        trs = []
        for a in sorted(bars):
            trs += [t for _, t in AR.generic_trades(a, mbars[a], always, B_START, key,
                                                    falhado_var(*cfg))]
        trs.sort(key=lambda t: t["t"])
        w = {"B": [t for t in trs if t["t"] < B_END], "A": [t for t in trs if t["t"] >= B_END],
             "C90": [t for t in trs if t["t"] >= end - 90 * DAY]}
        res["janelas"][key] = {k: summary(v, mbars, rmap) for k, v in w.items()}
        for k in ("B", "A", "C90"):
            x = res["janelas"][key][k]
            print(key, k, {q: x.get(q) for q in ("n", "avg_r", "acaso_mediana", "acaso_p95",
                                                 "percentil_acaso", "avg_sem_melhor", "anos")},
                  {rg: (v["n"], v["avg_r"], v["acaso_p95"], v["percentil_acaso"])
                   for rg, v in (x.get("por_regime") or {}).items()}, flush=True)
        with open(dest, "w") as f:
            json.dump(res, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3:] or None)
