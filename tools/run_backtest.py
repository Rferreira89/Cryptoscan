"""Corre o backtest completo e escreve backtest/results.json.

Uso: python -m tools.run_backtest <pasta_historico> [cache.pkl]

Protocolo de validacao:
- DESENHO: primeiros 80% do periodo. Tudo o que e analise, comparacao de
  parametros e walk-forward acontece aqui.
- RESERVA: ultimos 20%. Avaliada UMA vez, com a configuracao fixa, e nunca
  usada para escolher parametros.
"""
import json
import os
import pickle
import sys
import time
from multiprocessing import Pool

from engine import backtest as B
from engine import config, stats

CFG = config.load()
DATA = {}
STRATS = ["PULLBACK", "BREAKOUT", "LIQUIDITY_SWEEP", "RANGE"]
MIN_SAMPLE = 100


def _work(args):
    asset, btc_reg = args
    c4 = DATA[asset]
    cands = B.candidates(asset, c4, btc_reg, CFG)
    res = {v: [B.simulate(c, c4, CFG, **kw) for c in cands]
           for v, kw in VARIANTS.items()}
    return asset, cands, res


VARIANTS = {"base": {}, "sem_breakeven": {"breakeven": False},
            "slippage_x3": {"slip_pct": 0.15}, "validade_6": {"expiry": 6}}


def baseline_btc(c4, t0, t1, fee=0.001):
    d = [x for x in B.daily(c4) if t0 <= x["t"] < t1]
    cl = [x["c"] for x in d]

    def run(signal):
        eq, peak, dd, pos, rets = 1.0, 1.0, 0.0, 0, []
        for k in range(1, len(d)):
            want = signal(k - 1)                     # decidido no fecho anterior
            if want != pos:
                eq *= 1 - fee
                pos = want
            r = cl[k] / cl[k - 1] - 1 if pos else 0.0
            eq *= 1 + r
            rets.append(r)
            peak = max(peak, eq)
            dd = max(dd, 1 - eq / peak)
        m = sum(rets) / len(rets)
        sd = (sum((r - m) ** 2 for r in rets) / len(rets)) ** 0.5
        return {"return_pct": round((eq - 1) * 100, 1),
                "max_drawdown_pct": round(dd * 100, 1),
                "sharpe": round(m / sd * 365 ** 0.5, 2) if sd else None}
    sma = lambda k, n: sum(cl[k - n + 1:k + 1]) / n if k >= n - 1 else None
    return {
        "buy_and_hold_btc": run(lambda k: 1),
        "btc_acima_sma200": run(lambda k: 1 if sma(k, 200) and cl[k] > sma(k, 200) else 0),
        "btc_sma50_sma200": run(lambda k: 1 if sma(k, 200) and sma(k, 50) > sma(k, 200) else 0),
        "btc_breakout_20d": run(lambda k: 1 if k >= 20 and cl[k] >= max(cl[k - 19:k + 1]) * 0.999
                                or (k >= 20 and cl[k] > min(cl[k - 9:k + 1]) * 1.0001
                                    and cl[k] > sma(k, 20)) else 0)}


def random_benchmark(split, seed=3, n_per=120):
    """Entradas ao acaso com a mesma gestao (stop 1.5 ATR, TPs a 1R/2R/3R).
    Mede quanto do resultado vem dos custos e das regras, e nao dos sinais."""
    import random
    import statistics
    from engine import indicators as I
    from engine import trade

    def run(fee, slip, be):
        rnd, rs = random.Random(seed), []
        for a in sorted(DATA):
            c = DATA[a]
            atr = I.atr(c)
            idx = [i for i in range(300, len(c) - 200)
                   if c[i]["t"] < split - 40 * 86400]
            for i in rnd.sample(idx, min(n_per, len(idx))):
                px, ru = c[i]["c"], 1.5 * atr[i]
                plan = {"stop": px - ru, "tp": [px + ru, px + 2 * ru, px + 3 * ru],
                        "partials": [50, 30, 20]}
                b = c[i + 1]
                if b["o"] <= plan["stop"] or b["o"] >= plan["tp"][0]:
                    continue
                pos = trade.open_position(plan, b["o"], b["t"], fee, slip, be)
                k = i + 1
                trade.step(pos, b["o"], b["h"], b["l"], b["c"], b["t"] + B.H4)
                while not pos["closed"] and k < len(c) - 1:
                    k += 1
                    b = c[k]
                    trade.step(pos, b["o"], b["h"], b["l"], b["c"], b["t"] + B.H4)
                if pos["closed"]:
                    rs.append(pos["r"])
        return {"n": len(rs), "expectancy_r": round(statistics.mean(rs), 3),
                "win_rate": round(100 * sum(r > 0 for r in rs) / len(rs), 1)}
    return {"com_custos_e_regras": run(CFG["fee_pct"], B.SLIP_PCT, True),
            "sem_custos": run(0.0, 0.0, True),
            "sem_custos_sem_stop_na_entrada": run(0.0, 0.0, False)}


def verdict(m, wf_pos_share):
    """Criterios para considerar uma estrategia validada."""
    if m["n"] < MIN_SAMPLE:
        lbl = "AMOSTRA INSUFICIENTE" if m["n"] else "SEM OPERACOES"
        return False, lbl
    ci = m["expectancy_ci95"]
    if ci and ci[1] < 0:
        return False, "RETIRADA: expectativa negativa"
    if not (ci and ci[0] > 0):
        return False, "EM REVISAO: vantagem nao demonstrada"
    if (m["profit_factor"] or 0) < 1.2:
        return False, "EM REVISAO: profit factor baixo"
    if wf_pos_share is not None and wf_pos_share < 0.6:
        return False, "EM REVISAO: instavel no walk-forward"
    return True, "VALIDADA"


def main(folder, cache=None):
    global DATA
    DATA, skipped = B.load_all(folder)
    print(f"{len(DATA)} ativos, {len(skipped)} excluidos", flush=True)
    t_first = min(c[0]["t"] for c in DATA.values())
    t_last = max(c[-1]["t"] for c in DATA.values())
    split = t_first + int(0.8 * (t_last - t_first))
    if cache and os.path.exists(cache):
        cands, res = pickle.load(open(cache, "rb"))
    else:
        btc_reg = B.regimes(DATA["BTC"])
        t = time.time()
        cands, res = [], {v: [] for v in VARIANTS}
        with Pool() as pool:
            for a, cs, rs in pool.imap_unordered(
                    _work, [(a, btc_reg) for a in DATA]):
                cands += cs
                for v in VARIANTS:
                    res[v] += rs[v]
                print(f"  {a}: {len(cs)} candidatos ({time.time() - t:.0f}s)",
                      flush=True)
        if cache:
            pickle.dump((cands, res), open(cache, "wb"))

    design = lambda t: t["t"] < split and t["exit_t"] < split
    hold = lambda t: t["t"] >= split
    span_d, span_h = split - t_first, t_last - split
    base = stats.select(cands, res["base"], CFG)
    d_tr, h_tr = [t for t in base if design(t)], [t for t in base if hold(t)]
    out = {
        "generated_at": int(time.time()),
        "period": {"start": t_first, "split": split, "end": t_last},
        "universe": {"assets": sorted(DATA), "excluded": skipped},
        "config": CFG,
        "costs": {"fee_pct_per_side": CFG["fee_pct"], "slippage_pct": B.SLIP_PCT},
        "caveats": [
            "Universo = ativos hoje listados na Bybit UE: vies de sobrevivencia "
            "(moedas que desapareceram nao entram), o que favorece o resultado.",
            "Sem historico de derivados: essa familia do score fica neutra.",
            "Precos da Binance em USDT, nao da Bybit UE em USDC.",
            "Execucao simulada em velas de 4H; no mesmo candle conta o stop.",
            "Os pesos e limiares nao foram otimizados: sao os valores iniciais."],
        "candidates": len(cands),
        "design": {"all": stats.metrics(d_tr, span_d),
                   "by_strategy": stats.group(d_tr, lambda t: t["strategy"], span_d),
                   "by_regime": stats.group(d_tr, lambda t: t["regime"], span_d),
                   "by_btc_regime": stats.group(d_tr, lambda t: t["btc_regime"], span_d),
                   "by_year": stats.group(d_tr, lambda t: time.gmtime(t["t"]).tm_year),
                   "by_asset_group": stats.group(
                       d_tr, lambda t: t["asset"] if t["asset"] in ("BTC", "ETH", "SOL")
                       else "ALTCOINS", span_d),
                   "by_exit": stats.group(d_tr, lambda t: t["exit"], span_d),
                   "monte_carlo": stats.monte_carlo(d_tr)},
        "baselines_design": baseline_btc(DATA["BTC"], t_first, split),
        "baselines_holdout": baseline_btc(DATA["BTC"], split, t_last)}

    # sensibilidade: parametros vizinhos nao devem destruir o resultado
    sens = {}
    for ms in (50, 55, 60, 65, 70, 75, 80):
        tr = [t for t in stats.select(cands, res["base"], CFG, ms) if design(t)]
        sens[f"min_score_{ms}"] = stats.metrics(tr, span_d)
    for v in VARIANTS:
        if v != "base":
            tr = [t for t in stats.select(cands, res[v], CFG) if design(t)]
            sens[v] = stats.metrics(tr, span_d)
    for rr in (2.5, 3.0):
        keep = [k for k, c in enumerate(cands) if c["plan"]["rr"] >= rr]
        tr = [t for t in stats.select([cands[k] for k in keep],
                                      [res["base"][k] for k in keep], CFG)
              if design(t)]
        sens[f"min_rr_{rr}"] = stats.metrics(tr, span_d)
    out["sensitivity"] = sens
    exps = [m["expectancy_r"] for k, m in sens.items()
            if k.startswith("min_score") and m.get("n", 0) >= 30]
    out["overfitting_flag"] = bool(exps) and (max(exps) > 0 > min(exps))

    # walk-forward dentro da janela de desenho
    grid = [{"min_score": ms, "strategies": ss}
            for ms in (55, 60, 65, 70, 75)
            for ss in ([STRATS] + [[s] for s in STRATS]
                       + [[a for a in STRATS if a != s] for s in STRATS])]
    folds, oos = stats.walk_forward(cands, res["base"], CFG, t_first, split,
                                    365 * 86400, 91 * 86400, grid)
    traded = [f for f in folds if f["n"]]
    out["walk_forward"] = {
        "folds": folds, "oos": stats.metrics(oos),
        "folds_traded": len(traded),
        "folds_positive": sum(1 for f in traded if (f["test_expectancy"] or 0) > 0)}

    # por estrategia: veredicto na janela de desenho
    out["strategies"] = {}
    for s in STRATS:
        tr = [t for t in stats.select(cands, res["base"], CFG, strategies=[s])
              if design(t)]
        m = stats.metrics(tr, span_d)
        f_s, _ = stats.walk_forward(
            cands, res["base"], CFG, t_first, split, 365 * 86400, 91 * 86400,
            [{"min_score": CFG["min_score"], "strategies": [s]}], min_train_n=10)
        tr_f = [f for f in f_s if f["n"]]
        share = (sum(1 for f in tr_f if (f["test_expectancy"] or 0) > 0)
                 / len(tr_f)) if len(tr_f) >= 4 else None
        ok, label = verdict(m, share) if m["n"] else (False, "SEM OPERACOES")
        out["strategies"][s] = dict(
            m, validated=ok, label=label, wf_positive_share=share,
            by_regime=stats.group(tr, lambda t: t["regime"], span_d))

    # RESERVA: avaliada uma unica vez com a configuracao fixa
    out["holdout"] = {"all": stats.metrics(h_tr, span_h),
                      "by_strategy": stats.group(h_tr, lambda t: t["strategy"], span_h)}
    out["random_entry_benchmark"] = random_benchmark(split)
    rb = out["random_entry_benchmark"]
    out["caveats"].append(
        "Referencia: entradas ao acaso com as mesmas regras e custos dao "
        f"{rb['com_custos_e_regras']['expectancy_r']:+.2f}R por operacao "
        f"({rb['sem_custos_sem_stop_na_entrada']['expectancy_r']:+.2f}R sem "
        "custos e sem stop na entrada). Com velas de 4H, quando o stop e um "
        "objetivo cabem na mesma vela assume-se o pior caso, o que torna o "
        "simulador algo pessimista.")
    os.makedirs("backtest", exist_ok=True)
    with open("backtest/results.json", "w") as f:
        json.dump(out, f, indent=1)
    print(json.dumps({k: out[k] for k in ("candidates", "strategies")}, indent=1)[:200])


if __name__ == "__main__":
    main(*sys.argv[1:3])
