"""Investigacao SHORT_SOBRECOMPRA (4H) — pre-registo 2026-11-15.

Grelha: X in {70, 75} x V in {2.0, 2.5}. So vendas.
Metodo: velas espelhadas (engine.short.mirror) + tools/research_rlib.evaluate
(mesmos custos, janela, walk-forward e acaso que CAP/BOUNCE). Percentil >= 90.

ATAQUE_1H (long/short 1H): requer pasta 1h/; nesta versao regista-se como pendente.

Uso: python -m tools.research_short_ataque <historico> [saida.json]
"""
import json
import sys

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


def _rsi(c, n=14):
    return R.rsi(c, n)


def _atr(bars):
    return R.atr(bars)


def ss_signals_mirrored(c4_mir, x, v):
    """Sinais de sobrecompra no espelho (= short no preco real).
    No espelho: RSI baixo + vela a recuperar = short no real."""
    out = {}
    if len(c4_mir) < 60:
        return out
    closes = [b["c"] for b in c4_mir]
    rs = _rsi(closes)
    at = _atr(c4_mir)
    for i in range(40, len(c4_mir) - 1):
        if rs[i] is None or at[i] is None:
            continue
        # no espelho: RSI < (100-X) nas ultimas 3 e vela fecha acima do max anterior
        thr = 100 - x
        window_rs = [rs[j] for j in range(i - 2, i + 1) if rs[j] is not None]
        if not window_rs or min(window_rs) >= thr:
            continue
        if not (c4_mir[i]["c"] > c4_mir[i - 1]["h"] and rs[i] > rs[i - 1]):
            continue
        vavg = sum(c4_mir[j]["v"] for j in range(i - 20, i)) / 20
        if vavg <= 0 or c4_mir[i]["v"] < v * vavg:
            continue
        lo = min(c4_mir[j]["l"] for j in range(i - 5, i + 1)) - 0.1 * at[i]
        stop = min(lo, c4_mir[i]["c"] - 1.25 * at[i])
        if stop <= 0:
            continue
        ma20 = sum(closes[i - 19:i + 1]) / 20
        hi42 = max(c4_mir[j]["h"] for j in range(max(0, i - 41), i + 1))
        te = c4_mir[i]["t"] + TF
        if ma20 > c4_mir[i]["c"] * 1.01:
            out[te] = {"stop": stop, "tp": [ma20, hi42] if hi42 > ma20 * 1.005 else [ma20],
                       "partials": [50, 50] if hi42 > ma20 * 1.005 else [100],
                       "breakeven": True}
        else:
            out[te] = {"stop": stop, "tp_r": 2.0, "partials": [100], "breakeven": True}
    return out


def linha(res, share):
    crit = {k: v for k, v in res["criteria"].items() if not k.startswith("7_")}
    crit["3_grelha_estavel"] = share >= 0.75
    fa = res["random"]["fora_da_amostra"]
    pct = fa.get("percentil")
    crit["7_acaso_percentil_90"] = pct is not None and pct >= PCTIL_MIN
    n_wf = res["walk_forward"]["oos_trades"]
    n_fa = fa.get("n") or 0
    if crit["7_acaso_percentil_90"]:
        ver = "PARA PAPEL"
    elif n_fa >= 15 and pct is not None and pct > 80:
        ver = "RECRUTAR"
    elif n_wf < 40:
        ver = "AMOSTRA INSUFICIENTE"
    else:
        ver = "NAO VALIDADA"
    return {"operacoes_fora_amostra": fa.get("n"), "operacoes_walk_forward": n_wf,
            "operacoes_reserva": (res["holdout"]["trades"] or {}).get("n"),
            "r_medio_fora_amostra": fa.get("r_real"), "percentil_acaso": pct,
            "criterios": crit, "seis_passam": all(v for k, v in crit.items() if not k.startswith("7_")),
            "veredicto": ver}


def main(folder, out="backtest/research_short_ataque.json"):
    data, _ = B.load_all(folder)
    mir = {a: SH.mirror(c) for a, c in data.items()}
    bars, days = prepare(data)
    S = {"BTC": Series(bars["BTC"])}
    d0, ds, d1 = window(S["BTC"].days[-1])
    majors = [a for a in MAJORS21 if a in data]
    base = btc_sma200(S, days)
    warm = days[0] + 210
    res = {"moedas": len(data), "ultima_vela_btc": data["BTC"][-1]["t"],
           "pre_registo": "backtest/pre_registo_short_ataque_1h.md",
           "nota": "SHORT_SOBRECOMPRA via velas espelhadas; R no espelho = R short no real"}

    cache = {}

    def ss_runner(cfg, universe):
        key = (cfg["X"], cfg["V"])
        if key not in cache:
            cache[key] = {a: ss_signals_mirrored(mir[a], cfg["X"], cfg["V"]) for a in mir}
        return R.simulate(mir, cache[key], TF, SS_HOLD, universe)

    full = {}
    for cfg in SS_GRID:
        full[json.dumps(cfg, sort_keys=True)] = R.evaluate(
            "SHORT_SOBRECOMPRA", [cfg], ss_runner, mir, TF, lambda c: SS_HOLD, 90,
            majors, base, d0, ds, d1, warm=warm)
    share = sum(1 for r in full.values()
                if next(iter(r["grid"].values()))["all"]["return_pct"] > 0) / max(len(full), 1)
    res["SHORT_SOBRECOMPRA"] = {k: dict(linha(r, share), detalhe_omitido=True) for k, r in full.items()}
    res["SHORT_SOBRECOMPRA_fracao_grelha"] = share
    res["ATAQUE_1H"] = {"estado": "pendente", "motivo": "requer historico 1h/ e runner dedicado"}

    with open(out, "w") as f:
        json.dump(res, f, indent=1)
    return res


if __name__ == "__main__":
    r = main(*sys.argv[1:3])
    print("SHORT_SOBRECOMPRA fracao_grelha", r.get("SHORT_SOBRECOMPRA_fracao_grelha"))
    for k, v in r.get("SHORT_SOBRECOMPRA", {}).items():
        print("SHORT_SOBRECOMPRA", k, {q: v[q] for q in (
            "operacoes_fora_amostra", "r_medio_fora_amostra", "percentil_acaso", "veredicto")})
    print("ATAQUE_1H", r.get("ATAQUE_1H"))
