"""Investigacao SHORT_SOBRECOMPRA (4H) — pre-registo 2026-11-15.

Grelha: X in {70, 75} x V in {2.0, 2.5}. So vendas.
Metodo: velas espelhadas (engine.short.mirror) + tools/research_rlib.evaluate.
Percentil >= 90.

Uso: python -m tools.research_short_ataque <historico> [saida.json]
"""
import json
import sys
import traceback

from engine import backtest as B
from engine import short as SH
from tools import research_rlib as R
from tools.research import MAJORS21, Series, prepare
from tools.research_dip import window
from tools.research_squeeze import btc_sma200

TF = B.H4
PCTIL_MIN = 90
SS_GRID = [{"X": x, "V": v} for x in (70, 75) for v in (2.0, 2.5)]
SS_HOLD = 5 * R.DAY


def ss_signals_mirrored(c4_mir, x, v):
    out = {}
    if len(c4_mir) < 60:
        return out
    closes = [b["c"] for b in c4_mir]
    rs = R.rsi(closes)
    at = R.atr(c4_mir)
    for i in range(40, len(c4_mir) - 1):
        if rs[i] is None or at[i] is None or rs[i - 1] is None:
            continue
        thr = 100 - x
        window_rs = [rs[j] for j in range(i - 2, i + 1) if rs[j] is not None]
        if not window_rs or min(window_rs) >= thr:
            continue
        if not (c4_mir[i]["c"] > c4_mir[i - 1]["h"] and rs[i] > rs[i - 1]):
            continue
        vavg = sum(c4_mir[j]["v"] for j in range(i - 20, i)) / 20.0
        if vavg <= 0 or c4_mir[i]["v"] < v * vavg:
            continue
        lo = min(c4_mir[j]["l"] for j in range(i - 5, i + 1)) - 0.1 * at[i]
        stop = min(lo, c4_mir[i]["c"] - 1.25 * at[i])
        if stop <= 0:
            continue
        ma20 = sum(closes[i - 19:i + 1]) / 20.0
        hi42 = max(c4_mir[j]["h"] for j in range(max(0, i - 41), i + 1))
        te = c4_mir[i]["t"] + TF
        # rank: research_rlib.simulate ordena por rank (menor primeiro = prioritario)
        rank = float(rs[i]) if rs[i] is not None else 50.0
        if ma20 > c4_mir[i]["c"] * 1.01:
            two = hi42 > ma20 * 1.005
            out[te] = {"stop": stop, "tp": [ma20, hi42] if two else [ma20],
                       "partials": [50, 50] if two else [100], "breakeven": True,
                       "rank": rank}
        else:
            out[te] = {"stop": stop, "tp_r": 2.0, "partials": [100], "breakeven": True,
                       "rank": rank}
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
            "percentil_acaso": pct, "criterios": crit,
            "seis_passam": all(crit[k] for k in crit if not str(k).startswith("7_")),
            "veredicto": ver}


def _ret_pct(r):
    try:
        cell = next(iter((r.get("grid") or {}).values()))
        return float((cell.get("all") or {}).get("return_pct") or 0)
    except Exception:
        return 0.0


def main(folder, out="backtest/research_short_ataque.json"):
    print("load", folder, flush=True)
    data, _ = B.load_all(folder)
    print("moedas", len(data), "btc", len(data.get("BTC") or []), flush=True)
    if not data.get("BTC"):
        raise SystemExit("sem BTC no historico")
    mir = {a: SH.mirror(c) for a, c in data.items() if c}
    bars, days = prepare(data)
    S = {"BTC": Series(bars["BTC"])}
    d0, ds, d1 = window(S["BTC"].days[-1])
    majors = [a for a in MAJORS21 if a in data]
    base = btc_sma200(S, days)
    warm = days[0] + 210
    res = {"moedas": len(data), "ultima_vela_btc": data["BTC"][-1]["t"],
           "pre_registo": "backtest/pre_registo_short_ataque_1h.md"}

    cache = {}

    def ss_runner(cfg, universe):
        key = (cfg["X"], cfg["V"])
        if key not in cache:
            print("sinais", key, flush=True)
            cache[key] = {a: ss_signals_mirrored(mir[a], cfg["X"], cfg["V"]) for a in mir}
            print("nsinais", key, sum(len(v) for v in cache[key].values()), flush=True)
        return R.simulate(mir, cache[key], TF, SS_HOLD, universe)

    full = {}
    for cfg in SS_GRID:
        print("evaluate", cfg, flush=True)
        full[json.dumps(cfg, sort_keys=True)] = R.evaluate(
            "SHORT_SOBRECOMPRA", [cfg], ss_runner, mir, TF, lambda c: SS_HOLD, 90,
            majors, base, d0, ds, d1, warm=warm)
    share = sum(1 for r in full.values() if _ret_pct(r) > 0) / max(len(full), 1)
    res["SHORT_SOBRECOMPRA"] = {k: linha(r, share) for k, r in full.items()}
    res["SHORT_SOBRECOMPRA_fracao_grelha"] = share
    res["ATAQUE_1H"] = {"estado": "pendente", "motivo": "requer historico 1h/"}
    with open(out, "w") as f:
        json.dump(res, f, indent=1)
    print("ok", out, flush=True)
    return res


if __name__ == "__main__":
    try:
        r = main(*sys.argv[1:3])
        for k, v in r.get("SHORT_SOBRECOMPRA", {}).items():
            print(k, v.get("veredicto"), v.get("operacoes_fora_amostra"),
                  v.get("r_medio_fora_amostra"), v.get("percentil_acaso"), flush=True)
    except Exception:
        traceback.print_exc()
        sys.exit(1)
