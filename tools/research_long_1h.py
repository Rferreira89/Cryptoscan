"""Investigacao LONG_TENDENCIA_1H v2 — 2026-11-16.

Ajuste apos 0 sinais na v1. Filtros mais abertos:
- RSI 40-70 (antes 50-70)
- rompimento maximo das ultimas 3 velas (antes 5)
- volume >= 1.2x (grelha V in {1.2, 1.5})
Contexto 4H mantido.
Uso: python -m tools.research_long_1h <pasta_4h> <pasta_1h> [saida.json]
"""
import gzip
import json
import os
import sys
import traceback

from engine import backtest as B
from tools import research_rlib as R
from tools.research import Series, prepare, metrics
from tools.research_dip import window

H1 = 3600
PCTIL_MIN = 90
MIN_STOP = 0.012
GRID = [{"k": k, "H": h, "V": v} for k in (1.5, 2.0) for h in (8, 16) for v in (1.2, 1.5)]


def load_1h_folder(folder, min_bars=200):
    out = {}
    for fn in sorted(os.listdir(folder)):
        if not fn.endswith(".csv.gz"):
            continue
        path = os.path.join(folder, fn)
        if os.path.getsize(path) < 100:
            continue
        asset = fn.replace(".csv.gz", "")
        try:
            rows = []
            with gzip.open(path, "rt") as f:
                for line in f:
                    z = line.strip().split(",")
                    if len(z) < 6:
                        continue
                    rows.append({
                        "t": int(float(z[0])), "o": float(z[1]), "h": float(z[2]),
                        "l": float(z[3]), "c": float(z[4]), "v": float(z[5]),
                    })
            rows.sort(key=lambda x: x["t"])
            if len(rows) >= min_bars:
                out[asset] = rows
        except Exception as e:
            print("skip", asset, type(e).__name__, flush=True)
    return out


def _ema_list(xs, n):
    if len(xs) < n:
        return [None] * len(xs)
    out, k, e = [None] * len(xs), 2 / (n + 1), None
    for i, x in enumerate(xs):
        if i == n - 1:
            e = sum(xs[:n]) / n
        elif i >= n:
            e = x * k + e * (1 - k)
        out[i] = e
    return out


def long_tendencia_signals(c1, c4, k_r, hold_h, vol_mult):
    """Sinais de LONG_TENDENCIA_1H v2."""
    out = {}
    if not c1 or len(c1) < 40 or not c4 or len(c4) < 60:
        return out
    # contexto 4H
    c4_closes = [b["c"] for b in c4]
    e20_4 = _ema_list(c4_closes, 20)[-1]
    e50_4 = _ema_list(c4_closes, 50)[-1]
    if e20_4 is None or e50_4 is None or not (e20_4 > e50_4 and c4[-1]["c"] > e50_4):
        return out
    # EMA20 4H a subir (fecho actual > fecho de 4 velas atras)
    if len(c4) < 8 or c4[-1]["c"] <= c4[-5]["c"]:
        return out

    closes = [b["c"] for b in c1]
    rs = R.rsi(closes)
    at = R.atr(c1)
    hold_s = hold_h * 3600
    for i in range(30, len(c1) - 1):
        if rs[i] is None or at[i] is None:
            continue
        if not (40 <= rs[i] <= 70):
            continue
        # rompimento do maximo das ultimas 3 velas
        hi3 = max(c1[j]["h"] for j in range(i - 3, i))
        if c1[i]["c"] <= hi3:
            continue
        # volume
        vavg = sum(c1[j]["v"] for j in range(i - 20, i)) / 20.0
        if vavg <= 0 or c1[i]["v"] < vol_mult * vavg:
            continue
        stop = min(c1[j]["l"] for j in range(i - 3, i + 1)) - 0.15 * at[i]
        if stop <= 0:
            continue
        te = c1[i]["t"] + H1
        out[te] = {
            "stop": stop, "tp_r": k_r, "partials": [100], "breakeven": False,
            "rank": -rs[i], "min_stop": MIN_STOP, "hold_s": hold_s}
    return out


def rstats(trades):
    rs = [t["r"] for t in trades if t.get("r") is not None]
    n = len(rs)
    if not n:
        return {"n": 0, "r": None}
    return {"n": n, "r": round(sum(rs) / n, 3)}


def avaliar_cfg(cfg, data_sim, sigs, d0, ds, d1):
    hold_s = cfg["H"] * 3600
    print("simulate", cfg, flush=True)
    curve, trades = R.simulate(data_sim, sigs, H1, hold_s, None)
    des = [t for t in trades if d0 <= t["entry_d"] < ds]
    res = [t for t in trades if ds <= t["entry_d"] < d1]
    all_t = [t for t in trades if t["entry_d"] >= d0]
    rnd = R.vs_random(all_t, data_sim, H1, hold_s, 360, reps=400)
    pct = rnd.get("percentil")
    n_fa = rnd.get("n") or len(all_t)
    r_real = rnd.get("r_real")
    if r_real is None and all_t:
        r_real = round(sum(t["r"] for t in all_t) / len(all_t), 3)
    m_des = metrics(curve, d0, ds) if curve else {"return_pct": 0}
    m_res = metrics(curve, ds, d1) if curve else {"return_pct": 0}
    if pct is not None and pct >= PCTIL_MIN and (r_real or 0) > 0:
        ver = "PARA PAPEL"
    elif n_fa >= 15 and pct is not None and pct > 80:
        ver = "RECRUTAR"
    elif n_fa < 40:
        ver = "AMOSTRA INSUFICIENTE"
    else:
        ver = "NAO VALIDADA"
    return {
        "operacoes_fora_amostra": n_fa,
        "operacoes_desenho": len(des),
        "operacoes_reserva": len(res),
        "r_medio_fora_amostra": r_real,
        "r_medio_reserva": rstats(res).get("r"),
        "percentil_acaso": pct,
        "desenho_return_pct": m_des.get("return_pct"),
        "reserva_return_pct": m_res.get("return_pct"),
        "veredicto": ver,
    }


def main(folder4, folder1, out="backtest/research_long_1h.json"):
    print("load 4h", folder4, flush=True)
    data4, _ = B.load_all(folder4)
    print("load 1h", folder1, flush=True)
    data1 = load_1h_folder(folder1, min_bars=200)
    assets = [a for a in data1 if a in data4 and data1[a] and data4[a]]
    data1 = {a: data1[a] for a in assets}
    data4 = {a: data4[a] for a in assets}
    print("moedas_comuns", len(assets), "btc1h", len(data1.get("BTC") or []), flush=True)
    if not data1.get("BTC"):
        raise SystemExit("sem BTC em 1h")

    bars, days = prepare(data4)
    S = {"BTC": Series(bars["BTC"])}
    d0, ds, d1 = window(S["BTC"].days[-1])
    print("janela d0,ds,d1", d0, ds, d1, flush=True)

    res = {"moedas": len(assets), "ultima_vela_btc_1h": data1["BTC"][-1]["t"],
           "janela": {"d0": d0, "ds": ds, "d1": d1},
           "pre_registo": "backtest/pre_registo_long_1h.md",
           "nota": "LONG_TENDENCIA_1H v2 — filtros abertos"}

    out_grid = {}
    for cfg in GRID:
        key = json.dumps(cfg, sort_keys=True)
        sigs = {a: long_tendencia_signals(data1[a], data4.get(a), cfg["k"], cfg["H"], cfg["V"]) for a in data1}
        print("nsinais", cfg, sum(len(v) for v in sigs.values()), flush=True)
        out_grid[key] = avaliar_cfg(cfg, data1, sigs, d0, ds, d1)

    res["LONG_TENDENCIA_1H"] = out_grid
    with open(out, "w") as f:
        json.dump(res, f, indent=1)
    print("ok", out, flush=True)
    return res


if __name__ == "__main__":
    try:
        args = sys.argv[1:]
        if len(args) < 2:
            raise SystemExit("uso: python -m tools.research_long_1h <4h> <1h> [out.json]")
        r = main(args[0], args[1], args[2] if len(args) > 2 else "backtest/research_long_1h.json")
        for k, v in (r.get("LONG_TENDENCIA_1H") or {}).items():
            print(k, v.get("veredicto"), v.get("operacoes_fora_amostra"),
                  v.get("r_medio_fora_amostra"), v.get("percentil_acaso"), flush=True)
    except Exception:
        traceback.print_exc()
        sys.exit(1)
