"""Afinacao H17 (2026-11-18): reversao do racio moeda/BTC so com dispersao alta
do universo (RACIO_DISP, compra; SHORT_RACIO_DISP, short na lateral).

Dispersao = amplitude interquartil dos retornos logaritmicos de 30 velas de 4H
das moedas com vela naquele fecho (minimo 20). Percentil face aos 1080 valores
anteriores (180 dias, minimo 540). So velas fechadas. Regras-base da H9 (R4) e
da H10 (Q1, so lateral), sem afinar. Grelha escrita antes de testar
(backtest/afinacao.md, H17). A dispersao e o filtro estao em tools/arena_ringue.py.

Uso: python -m tools.afinacao_h17_dispersao <pasta_history> <saida.json> [D1 D2 ...]
"""
import json
import sys

from engine import backtest as B, short as SH
from tools import arena_ringue as AR
from tools.afinacao_h09_racio import B_END, B_START, corr_diaria, racio_var, summary
from tools.afinacao_h10_racio_short import racio_short
from tools.arena_ringue import com_dispersao

DAY, H4 = AR.DAY, AR.H4
# nome: (lado, percentil minimo ou None, percentil maximo ou None)
GRID = {
    "D1": ("L", 50, None),
    "D2": ("L", 70, None),
    "D3": ("L", None, 50),     # controlo
    "D4": ("S", 50, None),
    "D5": ("S", 70, None),
    "D6": ("S", None, 50),     # controlo
    "REF_L": ("L", None, None),  # referencia sem filtro (R4 da H9)
    "REF_S": ("S", None, None),  # referencia sem filtro (Q1 da H10, so lateral)
}
CANDIDATAS = ("D1", "D2", "D4", "D5")

def sinal(lado, pmin=None, pmax=None):
    base = racio_var(120, 2.5, 2.0, 3, 35) if lado == "L" else racio_short(120, 2.5, 2.0, 3, 35, ("lateral",))
    return com_dispersao(base, pmin, pmax) if pmin is not None or pmax is not None else base


def trades(lado, fn, key, bars, mbars, above, always, t0):
    out = []
    for a in sorted(bars):
        if a == "BTC":
            continue
        if lado == "L":
            out += [t for _, t in AR.generic_trades(a, bars[a], above, t0, key, fn)]
        else:
            for _, t in AR.generic_trades(a, mbars[a], always, t0, key, fn):
                t = dict(t, side="SHORT")
                j = AR.juros_short_r(t, AR.JUROS_MARGEM_DIA_PCT)
                out.append(dict(t, r=t["r"] - j, juros_r=round(j, 4)))
    return sorted(out, key=lambda t: t["t"])


def main(folder, dest, only=None):
    bars, skipped = B.load_all(folder, min_bars=1500)
    btc = bars["BTC"]
    AR.CTX.update(btc=btc, funding={}, oi={}, macro={}, ls={}, bars=bars, rank={}, daily={})
    end = max(x["t"] for x in btc) + H4
    rmap = AR.regime_by_day(btc)
    above = AR.btc_above(btc)
    always = {k: True for k in above}
    mbars = {a: SH.mirror(c) for a, c in bars.items()}
    res = {"moedas": len(bars), "fora": skipped, "fim": end, "janelas": {}}
    ref = {"L": trades("L", AR.sig_x30, "X30", bars, mbars, above, always, B_START),
           "S": trades("S", AR.SHORT_SIGS["SHORT_X30"], "SX30", bars, mbars, above, always, B_START)}
    for key, (lado, pmin, pmax) in GRID.items():
        if only and key not in only:
            continue
        trs = trades(lado, sinal(lado, pmin, pmax), key, bars, mbars, above, always, B_START)
        jb = bars if lado == "L" else mbars
        w = {"B": [t for t in trs if t["t"] < B_END], "A": [t for t in trs if t["t"] >= B_END],
             "C90": [t for t in trs if t["t"] >= end - 90 * DAY],
             "L365": [t for t in trs if t["t"] >= end - 365 * DAY]}
        res["janelas"][key] = {k: summary(v, jb, rmap) for k, v in w.items()}
        res["janelas"][key]["corr_x30"] = {
            "B": corr_diaria(w["B"], [t for t in ref[lado] if t["t"] < B_END]),
            "A": corr_diaria(w["A"], [t for t in ref[lado] if t["t"] >= B_END])}
        for k in w:
            x = res["janelas"][key][k]
            print(key, k, {q: x.get(q) for q in ("n", "avg_r", "acaso_mediana", "acaso_p95",
                                                 "percentil_acaso", "sem_melhor", "avg_sem_melhor", "anos")},
                  {rg: (v["n"], v["avg_r"], v["acaso_p95"], v["percentil_acaso"])
                   for rg, v in (x.get("por_regime") or {}).items()}, flush=True)
        print(key, "corr_x30", res["janelas"][key]["corr_x30"], flush=True)
        with open(dest, "w") as f:
            json.dump(res, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3:] or None)
