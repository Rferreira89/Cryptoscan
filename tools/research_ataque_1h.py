"""Investigacao ATAQUE_1H (long + short) — pre-registo 2026-11-15.

Grelha: k in {1.5, 2.0} x H in {12, 24}h por lado.
1H: loader proprio (ignora stubs). Avaliacao: simulate + vs_random + reserva
(sem depender de folds com test=None no walk-forward 4H-day).
Uso: python -m tools.research_ataque_1h <pasta_4h> <pasta_1h> [saida.json]
"""
import gzip
import json
import os
import sys
import traceback

from engine import backtest as B
from engine import short as SH
from tools import research_rlib as R
from tools.research import MAJORS21, Series, prepare, metrics
from tools.research_dip import window
from tools.research_squeeze import btc_sma200

H1 = 3600
DAY = R.DAY
PCTIL_MIN = 90
MIN_STOP = 0.012
GRID = [{"k": k, "H": h} for k in (1.5, 2.0) for h in (12, 24)]


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


def _ctx4(c4):
    if not c4 or len(c4) < 60:
        return None, None, None
    c = [x["c"] for x in c4]
    return _ema_list(c, 20)[-1], _ema_list(c, 50)[-1], c4[-1]["c"]


def long_signals(c1, c4, k_r, hold_h):
    out = {}
    if not c1 or len(c1) < 40:
        return out
    e20_4, e50_4, c4c = _ctx4(c4) if c4 else (None, None, None)
    if e20_4 is not None and e50_4 is not None:
        if not (e20_4 > e50_4 and c4c > e50_4):
            return out
    closes = [b["c"] for b in c1]
    rs, at, ema20 = R.rsi(closes), R.atr(c1), _ema_list(closes, 20)
    hold_s = hold_h * 3600
    for i in range(30, len(c1) - 1):
        if rs[i] is None or at[i] is None or ema20[i] is None:
            continue
        b = c1[i]
        if not (b["l"] <= ema20[i] and b["c"] > ema20[i]):
            continue
        if not (35 <= rs[i] <= 55):
            continue
        stop = min(x["l"] for x in c1[i - 2:i + 1]) - 0.2 * at[i]
        if stop <= 0:
            continue
        out[c1[i]["t"] + H1] = {
            "stop": stop, "tp_r": k_r, "partials": [100], "breakeven": False,
            "rank": -rs[i], "min_stop": MIN_STOP, "hold_s": hold_s}
    return out


def short_signals_mirrored(c1_mir, c4, k_r, hold_h):
    out = {}
    if not c1_mir or len(c1_mir) < 40:
        return out
    e20_4, e50_4, c4c = _ctx4(c4) if c4 else (None, None, None)
    if e20_4 is not None and e50_4 is not None:
        if not (e20_4 < e50_4 and c4c < e50_4):
            return out
    closes = [b["c"] for b in c1_mir]
    rs, at, ema20 = R.rsi(closes), R.atr(c1_mir), _ema_list(closes, 20)
    hold_s = hold_h * 3600
    for i in range(30, len(c1_mir) - 1):
        if rs[i] is None or at[i] is None or ema20[i] is None:
            continue
        b = c1_mir[i]
        if not (b["l"] <= ema20[i] and b["c"] > ema20[i]):
            continue
        if not (35 <= rs[i] <= 55):
            continue
        stop = min(x["l"] for x in c1_mir[i - 2:i + 1]) - 0.2 * at[i]
        if stop <= 0:
            continue
        out[c1_mir[i]["t"] + H1] = {
            "stop": stop, "tp_r": k_r, "partials": [100], "breakeven": False,
            "rank": -rs[i], "min_stop": MIN_STOP, "hold_s": hold_s}
    return out


def rstats(trades):
    rs = [t["r"] for t in trades if t.get("r") is not None]
    n = len(rs)
    if not n:
        return {"n": 0, "r": None}
    return {"n": n, "r": round(sum(rs) / n, 3)}


def avaliar_cfg(nome, cfg, data_sim, sigs, d0, ds, d1):
    """Uma combinacao: desenho / reserva / acaso (percentil)."""
    hold_s = cfg["H"] * 3600
    print("simulate", nome, cfg, flush=True)
    curve, trades = R.simulate(data_sim, sigs, H1, hold_s, None)
    des = [t for t in trades if d0 <= t["entry_d"] < ds]
    res = [t for t in trades if ds <= t["entry_d"] < d1]
    oos = des  # fora-amostra simplificado = desenho (reportamos reserva a parte)
    # acaso em todas as op. com entry_d >= d0 (desenho+reserva)
    all_t = [t for t in trades if t["entry_d"] >= d0]
    rnd = R.vs_random(all_t, data_sim, H1, hold_s, 360, reps=500)
    pct = rnd.get("percentil")
    n_fa = rnd.get("n") or len(all_t)
    r_real = rnd.get("r_real")
    if r_real is None and all_t:
        r_real = round(sum(t["r"] for t in all_t) / len(all_t), 3)
    m_des = metrics(curve, d0, ds) if curve else {"return_pct": 0, "sharpe": 0}
    m_res = metrics(curve, ds, d1) if curve else {"return_pct": 0, "sharpe": 0}
    if pct is not None and pct >= PCTIL_MIN:
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


def main(folder4, folder1, out="backtest/research_ataque_1h.json"):
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
    mir1 = {a: SH.mirror(c) for a, c in data1.items()}

    res = {"moedas": len(assets), "ultima_vela_btc_1h": data1["BTC"][-1]["t"],
           "janela": {"d0": d0, "ds": ds, "d1": d1},
           "pre_registo": "backtest/pre_registo_short_ataque_1h.md",
           "nota": "evaluate simplificado (vs_random); walk-forward day folds instaveis em 1H"}

    long_out, short_out = {}, {}
    for cfg in GRID:
        key = json.dumps(cfg, sort_keys=True)
        sigs_l = {a: long_signals(data1[a], data4.get(a), cfg["k"], cfg["H"]) for a in data1}
        print("nsinais long", cfg, sum(len(v) for v in sigs_l.values()), flush=True)
        long_out[key] = avaliar_cfg("LONG", cfg, data1, sigs_l, d0, ds, d1)

        sigs_s = {a: short_signals_mirrored(mir1[a], data4.get(a), cfg["k"], cfg["H"]) for a in mir1}
        print("nsinais short", cfg, sum(len(v) for v in sigs_s.values()), flush=True)
        short_out[key] = avaliar_cfg("SHORT", cfg, mir1, sigs_s, d0, ds, d1)

    res["ATAQUE_1H_LONG"] = long_out
    res["ATAQUE_1H_SHORT"] = short_out
    with open(out, "w") as f:
        json.dump(res, f, indent=1)
    print("ok", out, flush=True)
    return res


if __name__ == "__main__":
    try:
        args = sys.argv[1:]
        if len(args) < 2:
            raise SystemExit("uso: python -m tools.research_ataque_1h <4h> <1h> [out.json]")
        r = main(args[0], args[1], args[2] if len(args) > 2 else "backtest/research_ataque_1h.json")
        for lado in ("ATAQUE_1H_LONG", "ATAQUE_1H_SHORT"):
            print("===", lado, flush=True)
            for k, v in (r.get(lado) or {}).items():
                print(k, v.get("veredicto"), v.get("operacoes_fora_amostra"),
                      v.get("r_medio_fora_amostra"), v.get("percentil_acaso"), flush=True)
    except Exception:
        traceback.print_exc()
        sys.exit(1)
