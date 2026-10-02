"""Backtest dos shorts (espelho das estrategias de compra).

Uso: python -m tools.run_backtest_short <pasta_historico> [cache.pkl]

A analise corre sobre as velas invertidas, com as mesmas funcoes do
sistema ao vivo; a execucao e simulada em precos reais com trade.step
(side SHORT). Custos: comissao, slippage e juros do emprestimo da moeda
(BORROW_DAILY_PCT por dia, valor assumido: a taxa real da Bybit UE varia
por moeda e nao e conhecida). Acrescenta as estrategias *_SHORT a
backtest/results.json, avaliadas na janela de desenho (primeiros 80%).
"""
import json
import os
import pickle
import sys
import time
from multiprocessing import Pool

from engine import backtest as B
from engine import config, short, stats, trade
from tools.run_backtest import MIN_SAMPLE, STRATS, verdict

CFG = dict(config.load(), swing_leverage=1.0, capital_usdc=None,
           fixed_position_usdc=None)
DATA, MIR = {}, {}
BORROW_DAILY_PCT = 0.05


def simulate(cand, c4, expiry=B.EXPIRY_BARS, slip=B.SLIP_PCT):
    p, why = short.real_plan(cand["plan"], CFG)
    if p is None:
        return {"status": "REJECTED"}
    i, base = cand["i"], p["entry_zone"][0]
    pos = None
    for j in range(i + 1, min(i + 1 + expiry, len(c4))):
        b = c4[j]
        if b["o"] >= p["stop"]:
            return {"status": "INVALIDATED"}
        if b["h"] >= base:
            at_open = b["o"] >= base
            fill = b["o"] if at_open else base
            pos = trade.open_position(p, fill, b["t"], CFG["fee_pct"], slip,
                                      side="SHORT")
            lo = b["l"] if at_open else fill     # sem credito de TP a meio da vela
            trade.step(pos, fill, b["h"], min(lo, fill), b["c"], b["t"] + B.H4)
            k = j
            break
        if b["l"] < p["tp"][0]:
            return {"status": "INVALIDATED"}
    if pos is None:
        return {"status": "EXPIRED"}
    while not pos["closed"]:
        k += 1
        if k >= len(c4):
            return {"status": "OPEN_AT_END"}
        b = c4[k]
        trade.step(pos, b["o"], b["h"], b["l"], b["c"], b["t"] + B.H4)
    days = (pos["closed_at"] - pos["opened_at"]) / 86400
    r = pos["r"] - BORROW_DAILY_PCT / 100 * days * pos["entry"] / pos["risk_unit"]
    return {"status": "CLOSED", "r": round(r, 3), "exit": pos["exit_reason"],
            "entry_t": pos["opened_at"], "exit_t": pos["closed_at"],
            "tp_hit": pos["tp_hit"], "risk_pct": p["risk_pct"]}


def _work(args):
    asset, btc_reg_m = args
    cands = B.candidates(asset, MIR[asset], btc_reg_m, CFG)
    for c in cands:
        c["strategy"] += short.SUFFIX
    return asset, cands, [simulate(c, DATA[asset]) for c in cands]


def main(folder, cache=None):
    global DATA, MIR
    DATA, _ = B.load_all(folder)
    MIR = {a: short.mirror(c) for a, c in DATA.items()}
    t_first = min(c[0]["t"] for c in DATA.values())
    t_last = max(c[-1]["t"] for c in DATA.values())
    split = t_first + int(0.8 * (t_last - t_first))
    if cache and os.path.exists(cache):
        cands, res = pickle.load(open(cache, "rb"))
    else:
        btc_m = B.regimes(MIR["BTC"])
        cands, res, t = [], [], time.time()
        with Pool() as pool:
            for a, cs, rs in pool.imap_unordered(
                    _work, [(a, btc_m) for a in DATA]):
                cands += cs
                res += rs
                print(f"  {a}: {len(cs)} candidatos ({time.time() - t:.0f}s)",
                      flush=True)
        if cache:
            pickle.dump((cands, res), open(cache, "wb"))
    cfg = dict(config.load(), max_open_positions=4)
    design = lambda t: t["t"] < split and t["exit_t"] < split
    span = split - t_first
    out = json.load(open("backtest/results.json"))
    names = [s + short.SUFFIX for s in STRATS]
    allt = [t for t in stats.select(cands, res, cfg) if design(t)]
    out["shorts"] = {
        "generated_at": int(time.time()), "candidates": len(cands),
        "borrow_daily_pct_assumed": BORROW_DAILY_PCT,
        "design_all": stats.metrics(allt, span),
        "by_year": stats.group(allt, lambda t: time.gmtime(t["t"]).tm_year),
        "by_btc_regime_mirror": stats.group(allt, lambda t: t["btc_regime"], span),
        "holdout_all": stats.metrics(
            [t for t in stats.select(cands, res, cfg) if t["t"] >= split],
            t_last - split)}
    for s in names:
        tr = [t for t in stats.select(cands, res, cfg, strategies=[s])
              if design(t)]
        m = stats.metrics(tr, span)
        ok, label = verdict(m, None) if m["n"] else (False, "SEM OPERACOES")
        out["strategies"][s] = dict(m, validated=ok, label=label)
    with open("backtest/results.json", "w") as f:
        json.dump(out, f, indent=1)
    row = lambda n, m: print(n, {k: m.get(k) for k in (
        "n", "win_rate", "expectancy_r", "expectancy_ci95", "profit_factor",
        "max_drawdown_pct")})
    row("TODOS (desenho)", out["shorts"]["design_all"])
    row("RESERVA", out["shorts"]["holdout_all"])
    for s in names:
        row(s + " " + out["strategies"][s]["label"], out["strategies"][s])
    for k, m in out["shorts"]["by_year"].items():
        row("ano " + k, m)
    for k, m in out["shorts"]["by_btc_regime_mirror"].items():
        row("btc espelho " + k, m)


if __name__ == "__main__":
    main(*sys.argv[1:3])
