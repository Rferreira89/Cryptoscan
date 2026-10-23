"""Afinacao H8 (2026-10-23): short dos compradores apinhados (SHORT_FUNDING).

Precos reais: f24 = media das liquidacoes de funding em (fecho - 24h, fecho],
cada uma convertida para 8 horas. Com f24 >= X e o fecho de 4H abaixo do minimo
da vela anterior, short na abertura seguinte com stop no fecho + k ATR(4H).
Corre sobre as velas espelhadas, como todos os shorts do ringue. Grelha
escrita antes de testar (afinacao.md, H8).

Uso: python -m tools.afinacao_h08_funding <pasta_history> <saida.json>
"""
import bisect
import calendar
import gzip
import json
import os
import random
import sys

from engine import backtest as B, paper_bounce as PB, short as SH
from tools import arena_ringue as AR
from tools.afinacao_h07_falhado import summary

DAY, H4 = AR.DAY, AR.H4
B_START = calendar.timegm((2024, 10, 1, 0, 0, 0))
A_START = calendar.timegm((2025, 10, 1, 0, 0, 0))
F_END = calendar.timegm((2026, 10, 1, 0, 0, 0))       # ultimo funding: 2026-09-30

# nome: (X por 8h, k ATR, objetivos em R, partes, dias)
GRID = {
    "X2G1": (0.0002, 1.5, (2.0,), (100,), 3),
    "X2G2": (0.0002, 3.0, (2.0,), (100,), 5),
    "X2G3": (0.0002, 3.0, (1.0, 3.0), (50, 50), 5),
    "X4G1": (0.0004, 1.5, (2.0,), (100,), 3),
    "X4G2": (0.0004, 3.0, (2.0,), (100,), 5),
    "X4G3": (0.0004, 3.0, (1.0, 3.0), (50, 50), 5),
}


def funding_8h(fr, t):
    """Media das liquidacoes em (t - 24h, t], cada uma convertida para 8 horas.
    None se nao houver liquidacao nas ultimas 24h. So usa instantes <= t."""
    if not fr:
        return None
    ts = [x[0] for x in fr]
    j = bisect.bisect_right(ts, t)
    vals = []
    for k in range(j - 1, -1, -1):
        if ts[k] <= t - DAY:
            break
        iv = (ts[k] - ts[k - 1]) if k > 0 else 8 * 3600
        iv = min(max(iv, 3600), 8 * 3600)
        vals.append(fr[k][1] * 8 * 3600 / iv)
    return sum(vals) / len(vals) if vals else None


def short_funding_var(x, k, rs, parts, days):
    """Funcao de sinal no ESPELHO (formato SHORT_SIGS)."""
    def f(m4):
        if len(m4) < 120:
            return None
        t = m4[-1]["t"] + H4
        f24 = funding_8h((AR.CTX.get("funding") or {}).get(AR.CTX.get("asset")), t)
        if f24 is None or f24 < x:
            return None
        r = SH.mirror(m4[-101:])                      # precos reais
        if not r[-1]["c"] < r[-2]["l"]:
            return None
        at = PB.atr(r)[-1]
        if not at:
            return None
        stop_real = r[-1]["c"] + k * at
        if not 0.005 <= stop_real / r[-1]["c"] - 1 <= 0.20:
            return None
        e, stop = m4[-1]["c"], 1 / stop_real
        risk = e - stop
        return {"stop": stop, "tp": [e + m * risk for m in rs], "partials": list(parts),
                "breakeven": True, "hold_s": days * DAY, "atr": PB.atr(m4[-100:])[-1],
                "gatilho": f"funding alto ({f24 * 100:.3f}% por 8h) e o preço a falhar: compradores apinhados"}
    return f


def load_funding(folder):
    out = {}
    d = os.path.join(folder, "funding")
    for fn in sorted(os.listdir(d)):
        if fn.endswith(".csv.gz"):
            with gzip.open(os.path.join(d, fn), "rt") as f:
                rows = [tuple(float(v) for v in l.split(",")[:2]) for l in f if l.strip()]
            out[fn[:-7]] = sorted((int(t), r) for t, r in rows)
    return out


def main(folder, dest, only=None):
    bars, skipped = B.load_all(folder, min_bars=1500)
    funding = load_funding(folder)
    bars = {a: c for a, c in bars.items() if a in funding or a == "BTC"}
    btc = bars["BTC"]
    AR.CTX.update(btc=btc, funding=funding, oi={}, macro={}, ls={}, bars=bars, rank={})
    rmap = AR.regime_by_day(btc)
    always = {k: True for k in AR.btc_above(btc)}
    mbars = {a: SH.mirror(c) for a, c in bars.items()}
    res = {"moedas": len(bars), "fora": skipped, "janelas": {}}
    for key, cfg in GRID.items():
        if only and key not in only:
            continue
        fn = short_funding_var(*cfg)
        trs = []
        for a in sorted(bars):
            if a not in funding:
                continue
            trs += [t for _, t in AR.generic_trades(a, mbars[a], always, B_START, key, fn)
                    if t["t"] < F_END]
        trs.sort(key=lambda t: t["t"])
        w = {"B": [t for t in trs if t["t"] < A_START], "A": [t for t in trs if t["t"] >= A_START],
             "C90": [t for t in trs if t["t"] >= F_END - 90 * DAY],
             "L365": [t for t in trs if t["t"] >= F_END - 365 * DAY]}
        res["janelas"][key] = {k: summary(v, mbars, rmap) for k, v in w.items()}
        for k in w:
            x = res["janelas"][key][k]
            print(key, k, {q: x.get(q) for q in ("n", "avg_r", "acaso_mediana", "acaso_p95",
                                                 "percentil_acaso", "sem_melhor", "avg_sem_melhor", "anos")},
                  {rg: (v["n"], v["avg_r"], v["acaso_p95"], v["percentil_acaso"])
                   for rg, v in (x.get("por_regime") or {}).items()}, flush=True)
        with open(dest, "w") as f:
            json.dump(res, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3:] or None)
