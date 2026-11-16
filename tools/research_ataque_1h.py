"""Investigacao ATAQUE_1H (long + short) — pre-registo 2026-11-15.

Grelha por lado: k in {1.5, 2.0} x H in {12, 24} horas.
Dados: 4H em <hist4>; 1H em <hist1> (ramo okx-1h). Ficheiros 1H vazios sao ignorados.
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
from tools.research import MAJORS21, Series, prepare
from tools.research_dip import window
from tools.research_squeeze import btc_sma200

H1 = 3600
PCTIL_MIN = 90
MIN_STOP = 0.012
GRID = [{"k": k, "H": h} for k in (1.5, 2.0) for h in (12, 24)]


def load_1h_folder(folder, min_bars=200):
    """Carrega *.csv.gz de 1H; salta ficheiros vazios ou invalidos (okx-1h tem stubs)."""
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
            if len(rows) < min_bars:
                continue
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
    e20 = _ema_list(c, 20)[-1]
    e50 = _ema_list(c, 50)[-1]
    return e20, e50, c4[-1]["c"]


def long_signals(c1, c4, k_r, hold_h):
    out = {}
    if not c1 or len(c1) < 40:
        return out
    e20_4, e50_4, c4c = _ctx4(c4) if c4 else (None, None, None)
    if e20_4 is not None and e50_4 is not None:
        if not (e20_4 > e50_4 and c4c > e50_4):
            return out
    closes = [b["c"] for b in c1]
    rs = R.rsi(closes)
    at = R.atr(c1)
    ema20 = _ema_list(closes, 20)
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
        te = c1[i]["t"] + H1
        out[te] = {"stop": stop, "tp_r": k_r, "partials": [100], "breakeven": False,
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
    rs = R.rsi(closes)
    at = R.atr(c1_mir)
    ema20 = _ema_list(closes, 20)
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
        te = c1_mir[i]["t"] + H1
        out[te] = {"stop": stop, "tp_r": k_r, "partials": [100], "breakeven": False,
                   "rank": -rs[i], "min_stop": MIN_STOP, "hold_s": hold_s}
    return out


def linha(res, share):
    crit = {k: v for k, v in (res.get("criteria") or {}).items() if not str(k).startswith("7_")}
    crit["3_grelha_estavel"] = share >= 0.75
    fa = ((res.get("random") or {}).get("fora_da_amostra")) or {}
    pct = fa.get("percentil")
    crit["7_acaso_percentil_90"] = pct is not None and pct >= PCTIL_MIN
    n_wf = (res.get("walk_forward") or {}).get("oos_trades") or 0
    n_fa = fa.get("n") or 0
    if crit["7_acaso_percentil_90"]:
        ver = "PARA PAPEL"
    elif n_fa >= 15 and pct is not None and pct > 80:
        ver = "RECRUTAR"
    elif n_wf < 40:
        ver = "AMOSTRA INSUFICIENTE"
    else:
        ver = "NAO VALIDADA"
    hold_tr = (res.get("holdout") or {}).get("trades")
    n_res = hold_tr.get("n") if isinstance(hold_tr, dict) else None
    return {"operacoes_fora_amostra": fa.get("n"), "operacoes_walk_forward": n_wf,
            "operacoes_reserva": n_res, "r_medio_fora_amostra": fa.get("r_real"),
            "percentil_acaso": pct, "criterios": crit, "veredicto": ver}


def _ret_pct(r):
    try:
        cell = next(iter((r.get("grid") or {}).values()))
        return float((cell.get("all") or {}).get("return_pct") or 0)
    except Exception:
        return 0.0


def _hold_of(cfg):
    return cfg["H"] * 3600


def avaliar_lado(nome, runner_factory, data_sim, majors, base, d0, ds, d1, warm):
    full = {}
    for cfg in GRID:
        print("evaluate", nome, cfg, flush=True)
        runner = runner_factory(cfg)
        full[json.dumps(cfg, sort_keys=True)] = R.evaluate(
            nome, [cfg], runner, data_sim, H1, _hold_of, 360,
            majors, base, d0, ds, d1, warm=warm)
    share = sum(1 for r in full.values() if _ret_pct(r) > 0) / max(len(full), 1)
    return {k: linha(r, share) for k, r in full.items()}, share


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
        raise SystemExit("sem BTC em 1h com barras suficientes")

    bars, days = prepare(data4)
    S = {"BTC": Series(bars["BTC"])}
    d0, ds, d1 = window(S["BTC"].days[-1])
    majors = [a for a in MAJORS21 if a in data1]
    base = btc_sma200(S, days)
    warm = days[0] + 210
    mir1 = {a: SH.mirror(c) for a, c in data1.items()}

    def long_factory(cfg):
        cache = {}

        def runner(cfg2, universe):
            key = (cfg2["k"], cfg2["H"])
            if key not in cache:
                cache[key] = {a: long_signals(data1[a], data4.get(a), cfg2["k"], cfg2["H"]) for a in data1}
                print("nsinais long", key, sum(len(v) for v in cache[key].values()), flush=True)
            return R.simulate(data1, cache[key], H1, cfg2["H"] * 3600, universe)
        return runner

    def short_factory(cfg):
        cache = {}

        def runner(cfg2, universe):
            key = (cfg2["k"], cfg2["H"])
            if key not in cache:
                cache[key] = {a: short_signals_mirrored(mir1[a], data4.get(a), cfg2["k"], cfg2["H"]) for a in mir1}
                print("nsinais short", key, sum(len(v) for v in cache[key].values()), flush=True)
            return R.simulate(mir1, cache[key], H1, cfg2["H"] * 3600, universe)
        return runner

    res = {"moedas": len(assets), "ultima_vela_btc_1h": data1["BTC"][-1]["t"],
           "pre_registo": "backtest/pre_registo_short_ataque_1h.md"}
    res["ATAQUE_1H_LONG"], res["ATAQUE_1H_LONG_fracao"] = avaliar_lado(
        "ATAQUE_1H_LONG", long_factory, data1, majors, base, d0, ds, d1, warm)
    res["ATAQUE_1H_SHORT"], res["ATAQUE_1H_SHORT_fracao"] = avaliar_lado(
        "ATAQUE_1H_SHORT", short_factory, mir1, majors, base, d0, ds, d1, warm)

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
        for lado, frk in (("ATAQUE_1H_LONG", "ATAQUE_1H_LONG_fracao"),
                          ("ATAQUE_1H_SHORT", "ATAQUE_1H_SHORT_fracao")):
            print(lado, "fracao", r.get(frk), flush=True)
            for k, v in (r.get(lado) or {}).items():
                print(k, v.get("veredicto"), v.get("operacoes_fora_amostra"),
                      v.get("r_medio_fora_amostra"), v.get("percentil_acaso"), flush=True)
    except Exception:
        traceback.print_exc()
        sys.exit(1)
