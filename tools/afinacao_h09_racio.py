"""Afinacao H9 (2026-10-26): reversao a media do racio moeda/BTC (RACIO_BTC).

racio = fecho da moeda / fecho do BTC na mesma vela de 4H; z do racio face as
ultimas N velas. Sinal: z da vela anterior <= -Z, racio a virar para cima e
moeda a fechar acima do fecho anterior (opcional: RSI 4H >= 35, fora da
sobrevenda). Stop a k ATR, objetivo no preco que devolve o racio a media.
So velas fechadas. Grelha escrita antes de testar (afinacao.md, H9).

Uso: python -m tools.afinacao_h09_racio <pasta_history> <saida.json> [R1 R2 ...]
"""
import calendar
import json
import random
import sys
import time

from engine import backtest as B, paper_bounce as PB
from tools import arena_ringue as AR
from tools.afinacao_h06_turtle_curta import pct_vs_random

DAY, H4 = AR.DAY, AR.H4
B_START = calendar.timegm((2021, 8, 1, 0, 0, 0))
B_END = calendar.timegm((2024, 10, 11, 0, 0, 0))

# nome: (N velas, Z, k ATR, dias, RSI minimo ou None)
GRID = {
    "R1": (120, 2.0, 2.0, 3, None),
    "R2": (120, 2.0, 2.0, 3, 35),
    "R3": (120, 2.5, 2.0, 3, None),
    "R4": (120, 2.5, 2.0, 3, 35),
    "R5": (120, 2.0, 3.0, 5, 35),
    "R6": (60, 2.0, 2.0, 3, 35),
}


def btc_close(t):
    """Fecho do BTC na vela de 4H que abre em t (None se nao houver)."""
    b = AR.CTX.get("btc") or []
    cache = AR.CTX.get("_btcc")
    if not cache or cache[0] is not b or cache[1] != len(b):
        cache = (b, len(b), {x["t"]: x["c"] for x in b})
        AR.CTX["_btcc"] = cache
    return cache[2].get(t)


def racio_z(c4, n):
    """(z da vela anterior, racio anterior, racio atual, media) com as n velas
    ate a anterior inclusive, ou None se faltar o BTC em alguma vela."""
    if len(c4) < n + 2:
        return None
    w = c4[-(n + 1):]
    rs = []
    for x in w:
        b = btc_close(x["t"])
        if not b:
            return None
        rs.append(x["c"] / b)
    base = rs[:-1]                       # ate a vela anterior (inclusive)
    m = sum(base) / n
    sd = (sum((v - m) ** 2 for v in base) / n) ** 0.5
    if sd <= 0:
        return None
    return (base[-1] - m) / sd, base[-1], rs[-1], m


def racio_var(n, z, k, days, rsi_min=None):
    """Funcao de sinal de compra (formato NEW_SIGS)."""
    def f(c4):
        if len(c4) < max(n + 2, 120) or not c4[-1]["c"] > c4[-2]["c"]:
            return None
        q = racio_z(c4, n)
        if not q:
            return None
        z0, r0, r1, m = q
        if z0 > -z or not r1 > r0:
            return None
        w = c4[-200:]
        if rsi_min is not None:
            rs = PB.rsi([x["c"] for x in w])[-1]
            if rs is None or rs < rsi_min:
                return None
        at = PB.atr(w[-100:])[-1]
        if at is None:
            return None
        e = c4[-1]["c"]
        stop = e - k * at
        if stop <= 0 or not 0.005 <= 1 - stop / e <= 0.20:
            return None
        tp = e * m / r1
        if tp < e * 1.01:
            return None
        return {"stop": stop, "tp": [tp], "partials": [100], "breakeven": True,
                "hold_s": days * DAY, "atr": at,
                "gatilho": f"rácio com o BTC {z0:.1f} desvios abaixo da média a virar"}
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


def corr_diaria(a, b):
    """Correlacao dos R somados por dia (dias com operacoes em qualquer um)."""
    da, db = {}, {}
    for t in a:
        da[t["t"] // DAY] = da.get(t["t"] // DAY, 0) + t["r"]
    for t in b:
        db[t["t"] // DAY] = db.get(t["t"] // DAY, 0) + t["r"]
    ks = sorted(set(da) | set(db))
    if len(ks) < 10:
        return None
    x, y = [da.get(k, 0) for k in ks], [db.get(k, 0) for k in ks]
    mx, my = sum(x) / len(x), sum(y) / len(y)
    sx = sum((v - mx) ** 2 for v in x) ** 0.5
    sy = sum((v - my) ** 2 for v in y) ** 0.5
    if not sx or not sy:
        return None
    return round(sum((p - mx) * (q - my) for p, q in zip(x, y)) / (sx * sy), 3)


def main(folder, dest, only=None):
    bars, skipped = B.load_all(folder, min_bars=1500)
    btc = bars["BTC"]
    AR.CTX.update(btc=btc, funding={}, oi={}, macro={}, ls={}, bars=bars, rank={})
    end = max(x["t"] for x in btc) + H4
    rmap = AR.regime_by_day(btc)
    above = AR.btc_above(btc)
    res = {"moedas": len(bars), "fora": skipped, "fim": end, "janelas": {}}
    iso = []
    for a in sorted(bars):
        if a != "BTC":
            iso += [t for _, t in AR.generic_trades(a, bars[a], above, B_START, "ISO", AR.sig_isolada)]
    for key, cfg in GRID.items():
        if only and key not in only:
            continue
        trs = []
        for a in sorted(bars):
            if a == "BTC":
                continue
            trs += [t for _, t in AR.generic_trades(a, bars[a], above, B_START, key, racio_var(*cfg))]
        trs.sort(key=lambda t: t["t"])
        w = {"B": [t for t in trs if t["t"] < B_END], "A": [t for t in trs if t["t"] >= B_END],
             "C90": [t for t in trs if t["t"] >= end - 90 * DAY]}
        res["janelas"][key] = {k: summary(v, bars, rmap) for k, v in w.items()}
        res["janelas"][key]["corr_isolada"] = {
            "B": corr_diaria(w["B"], [t for t in iso if t["t"] < B_END]),
            "A": corr_diaria(w["A"], [t for t in iso if t["t"] >= B_END])}
        for k in ("B", "A", "C90"):
            x = res["janelas"][key][k]
            print(key, k, {q: x.get(q) for q in ("n", "avg_r", "acaso_mediana", "acaso_p95",
                                                 "percentil_acaso", "avg_sem_melhor", "anos")},
                  {rg: (v["n"], v["avg_r"], v["acaso_p95"], v["percentil_acaso"])
                   for rg, v in (x.get("por_regime") or {}).items()}, flush=True)
        print(key, "corr", res["janelas"][key]["corr_isolada"], flush=True)
        with open(dest, "w") as f:
            json.dump(res, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3:] or None)
