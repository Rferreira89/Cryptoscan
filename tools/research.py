"""Fase 5b: teste de duas hipoteses em velas diarias, so compras em spot.

A) TENDENCIA: entra na quebra do maximo de N dias com o ativo e o BTC acima
   da media de 200 dias; stop inicial a k ATR; sai quando fecha abaixo do
   minimo de M dias. Risco de 1% por operacao, maximo 4 posicoes.
B) FORCA RELATIVA: todas as semanas compra as K moedas com maior retorno
   nos ultimos L dias (e positivo), em partes iguais; fora do mercado
   quando o BTC esta abaixo da media de 200 dias.

Decisoes no fecho diario, execucao na abertura seguinte. Custos: 0.1% de
comissao + 0.1% de slippage por lado.

Criterios de validacao DECLARADOS ANTES de olhar para os resultados:
 1. walk-forward fora da amostra: retorno > 0 e Sharpe > 0.5
 2. pelo menos 60% das janelas de teste positivas
 3. pelo menos 75% das configuracoes da grelha com retorno positivo
 4. tambem positivo no sub-universo das grandes moedas de 2021
 5. melhor Sharpe fora da amostra do que "BTC acima da SMA200"
 6. reserva (uma unica avaliacao): Sharpe > 0
"""
import itertools
import json
import math
import sys
import time

from engine import backtest as B

DAY = 86400
FEE, SLIP = 0.001, 0.001
MAJORS21 = ["BTC", "ETH", "BNB", "XRP", "ADA", "DOGE", "SOL", "DOT", "LTC",
            "LINK", "BCH", "XLM", "UNI", "AVAX", "TRX", "ATOM", "FIL", "ALGO",
            "AAVE", "NEAR", "ICP", "HBAR", "CRV", "INJ"]


def prepare(data):
    """{ativo: {dia: vela}} e lista ordenada de dias."""
    d = {a: {x["t"] // DAY: x for x in B.daily(c)} for a, c in data.items()}
    days = sorted(set().union(*[set(v) for v in d.values()]))
    return d, days


class Series:
    """Indicadores diarios de um ativo, indexados pelo dia. O valor do dia
    usa apenas velas ate esse dia (inclusive)."""

    def __init__(self, bars):
        self.days = sorted(bars)
        self.pos = {d: i for i, d in enumerate(self.days)}
        b = [bars[d] for d in self.days]
        self.o = [x["o"] for x in b]
        self.h = [x["h"] for x in b]
        self.l = [x["l"] for x in b]
        self.c = [x["c"] for x in b]
        self.dv = [x["c"] * x["v"] for x in b]
        n = len(b)
        self.sma200 = [None] * n
        s = 0.0
        for i in range(n):
            s += self.c[i]
            if i >= 200:
                s -= self.c[i - 200]
            if i >= 199:
                self.sma200[i] = s / 200
        tr = [self.h[0] - self.l[0]] + [
            max(self.h[i] - self.l[i], abs(self.h[i] - self.c[i - 1]),
                abs(self.l[i] - self.c[i - 1])) for i in range(1, n)]
        self.atr = [None] * n
        for i in range(19, n):
            self.atr[i] = sum(tr[i - 19:i + 1]) / 20

    def ret(self, i, L):
        return self.c[i] / self.c[i - L] - 1 if i >= L else None

    def above200(self, i):
        return self.sma200[i] is not None and self.c[i] > self.sma200[i]


def run_trend(S, days, universe, N, k, M, btc_filter, risk=0.01, max_pos=4,
              cap=0.25):
    cash, pos, curve, trades = 1.0, {}, [], []
    pend_in, pend_out = [], set()
    btc = S["BTC"]
    for d in days:
        # 1) execucao na abertura das ordens decididas ontem; stops
        for a in list(pos):
            s = S[a]
            i = s.pos.get(d)
            if i is None:
                continue
            p, px = pos[a], None
            if a in pend_out or s.o[i] <= p["stop"]:
                px = s.o[i] * (1 - SLIP)
            elif s.l[i] <= p["stop"]:
                px = p["stop"] * (1 - SLIP)
            if px is not None:
                cash += p["units"] * px * (1 - FEE)
                trades.append({"asset": a, "entry_d": p["d"], "exit_d": d,
                               "r": (p["units"] * px * (1 - FEE) - p["cost"])
                               / p["risk"]})
                del pos[a]
        pend_out = set()
        eq = cash + sum(p["units"] * S[a].c[S[a].pos[d] - 1]
                        for a, p in pos.items() if S[a].pos.get(d, 0) > 0)
        for a, atr in pend_in:
            s = S[a]
            i = s.pos.get(d)
            if i is None or a in pos or len(pos) >= max_pos:
                continue
            entry = s.o[i] * (1 + SLIP)
            stop = entry - k * atr
            if stop <= 0:
                continue
            notional = min(risk * eq / (entry - stop) * entry, cap * eq, cash)
            if notional < 0.01 * eq:
                continue
            units = notional / entry / (1 + FEE)
            cash -= notional
            pos[a] = {"units": units, "stop": stop, "d": d, "cost": notional,
                      "risk": units * (entry - stop) + 2 * FEE * notional}
        pend_in = []
        # 2) fecho: marca o capital e decide para amanha
        eq = cash
        for a, p in pos.items():
            s = S[a]
            i = s.pos.get(d)
            eq += p["units"] * (s.c[i] if i is not None else p["cost"] / p["units"])
            if i is not None and i >= M and s.c[i] < min(s.l[i - M:i]):
                pend_out.add(a)
        curve.append((d, eq))
        bi = btc.pos.get(d)
        if btc_filter and (bi is None or not btc.above200(bi)):
            continue
        cands = []
        for a in universe:
            s = S[a]
            i = s.pos.get(d)
            if a in pos or i is None or i < max(N, 200) or s.atr[i] is None:
                continue
            if s.above200(i) and s.c[i] > max(s.h[i - N:i]):
                cands.append((s.ret(i, 90) or 0, a, s.atr[i]))
        pend_in = [(a, atr) for _, a, atr in sorted(cands, reverse=True)]
    return curve, trades


def run_momentum(S, days, universe, L, K, btc_filter, top_liquid=30):
    cash, pos, curve, n_tr, target = 1.0, {}, [], 0, None
    btc = S["BTC"]
    for d in days:
        if target is not None:                    # executa na abertura
            for a in list(pos):
                i = S[a].pos.get(d)
                if a not in target and i is not None:
                    cash += pos.pop(a) * S[a].o[i] * (1 - SLIP) * (1 - FEE)
                    n_tr += 1
            eq = cash + sum(u * S[a].o[S[a].pos[d]] for a, u in pos.items()
                            if d in S[a].pos)
            for a in target:
                i = S[a].pos.get(d)
                if a in pos or i is None:
                    continue
                notional = min(eq / K, cash)
                if notional <= 0:
                    continue
                pos[a] = notional / (S[a].o[i] * (1 + SLIP)) / (1 + FEE)
                cash -= notional
                n_tr += 1
            target = None
        eq = cash
        for a, u in pos.items():
            i = S[a].pos.get(d)
            eq += u * S[a].c[i] if i is not None else 0
        curve.append((d, eq))
        if d % 7:
            continue
        bi = btc.pos.get(d)
        if btc_filter and (bi is None or not btc.above200(bi)):
            target = []
            continue
        rows = []
        for a in universe:
            s = S[a]
            i = s.pos.get(d)
            if i is None or i < max(L, 120):
                continue
            rows.append((sum(s.dv[i - 29:i + 1]), s.ret(i, L), a))
        liquid = sorted(rows, reverse=True)[:top_liquid]
        ranked = sorted(((r, a) for _, r, a in liquid if r and r > 0),
                        reverse=True)
        target = [a for _, a in ranked[:K]]
    return curve, n_tr


def metrics(curve, d0=None, d1=None):
    pts = [(d, e) for d, e in curve if (d0 is None or d >= d0)
           and (d1 is None or d < d1)]
    if len(pts) < 30:
        return None
    rets = [pts[i][1] / pts[i - 1][1] - 1 for i in range(1, len(pts))]
    eq = peak = 1.0
    dd = 0.0
    for r in rets:
        eq *= 1 + r
        peak = max(peak, eq)
        dd = max(dd, 1 - eq / peak)
    m = sum(rets) / len(rets)
    sd = math.sqrt(sum((r - m) ** 2 for r in rets) / len(rets))
    yrs = len(rets) / 365
    cagr = eq ** (1 / yrs) - 1 if eq > 0 else -1
    return {"return_pct": round((eq - 1) * 100, 1),
            "cagr_pct": round(cagr * 100, 1),
            "max_drawdown_pct": round(dd * 100, 1),
            "sharpe": round(m / sd * math.sqrt(365), 2) if sd else 0.0,
            "calmar": round(cagr / dd, 2) if dd > 0 else None,
            "invested_pct": round(100 * sum(1 for r in rets if r != 0)
                                  / len(rets))}


def btc_sma200(S, days):
    s, eq, on, curve = S["BTC"], 1.0, False, []
    for d in days:
        i = s.pos.get(d)
        if i is None or i < 1:
            curve.append((d, eq))
            continue
        if on:
            eq *= s.c[i] / s.c[i - 1]
        want = s.above200(i)
        if want != on:
            eq *= 1 - FEE - SLIP
            on = want
        curve.append((d, eq))
    return curve


def walk_forward(curves, d0, d1, train=548, test=183):
    """curves: {config: curva}. Escolhe pelo Sharpe do treino; encadeia os
    retornos do teste."""
    folds, chain, start = [], [], d0
    while start + train + test <= d1:
        a, b, c = start, start + train, start + train + test
        best = max(curves, key=lambda k: (metrics(curves[k], a, b) or
                                          {"sharpe": -9})["sharpe"])
        m = metrics(curves[best], b, c)
        folds.append({"train": [a, b], "test": [b, c], "chosen": best,
                      "test": m})
        pts = [(d, e) for d, e in curves[best] if b <= d < c]
        chain += [pts[i][1] / pts[i - 1][1] for i in range(1, len(pts))]
        start += test
    eq, curve = 1.0, [(0, 1.0)]
    for k, r in enumerate(chain):
        eq *= r
        curve.append((k + 1, eq))
    return folds, metrics(curve), best


def family(name, grid, runner, S, days, d_warm, d_split, base_curve):
    out = {"grid": {}, "name": name}
    curves, curves_maj = {}, {}
    for cfg in grid:
        key = json.dumps(cfg, sort_keys=True)
        curves[key] = runner(S, days, sorted(S), **cfg)[0]
        curves_maj[key] = runner(S, days, [a for a in MAJORS21 if a in S],
                                 **cfg)[0]
        out["grid"][key] = {"all": metrics(curves[key], d_warm, d_split),
                            "majors21": metrics(curves_maj[key], d_warm, d_split)}
    pos = [k for k, v in out["grid"].items() if v["all"]["return_pct"] > 0]
    out["grid_positive_share"] = round(len(pos) / len(grid), 2)
    folds, oos, last = walk_forward(curves, d_warm, d_split)
    fm, oos_m, _ = walk_forward(curves_maj, d_warm, d_split)
    _, base_oos, _ = walk_forward({"b": base_curve}, d_warm, d_split)
    out.update(walk_forward={"folds": folds, "oos": oos,
                             "folds_positive": sum(
                                 1 for f in folds if f["test"]["return_pct"] > 0)},
               walk_forward_majors21=oos_m, baseline_oos=base_oos,
               deploy_config=json.loads(last))
    crit = {
        "1_oos_retorno_e_sharpe": oos["return_pct"] > 0 and oos["sharpe"] > 0.5,
        "2_janelas_positivas": out["walk_forward"]["folds_positive"]
        / len(folds) >= 0.6,
        "3_grelha_estavel": out["grid_positive_share"] >= 0.75,
        "4_grandes_moedas_2021": oos_m["return_pct"] > 0,
        "5_melhor_que_btc_sma200": oos["sharpe"] > base_oos["sharpe"]}
    out["criteria_design"] = crit
    out["passed_design"] = all(crit.values())
    return out, curves[last], curves_maj[last]


def main(folder):
    data, _ = B.load_all(folder)
    bars, days = prepare(data)
    S = {a: Series(v) for a, v in bars.items()}
    t0, t1 = days[0], days[-1]
    d_split = t0 + int(0.8 * (t1 - t0))
    d_warm = t0 + 210
    base = btc_sma200(S, days)
    res = {"generated_at": int(time.time()),
           "period_days": {"start": t0, "warm": d_warm, "split": d_split,
                           "end": t1},
           "costs": {"fee_pct": FEE * 100, "slippage_pct": SLIP * 100},
           "baseline_btc_sma200_design": metrics(base, d_warm, d_split),
           "families": {}}
    grids = {
        "TREND": ([{"N": N, "k": k, "M": M, "btc_filter": f}
                   for N, k, M, f in itertools.product(
                       (20, 55), (2, 3), (10, 20), (True, False))], run_trend),
        "MOMENTUM": ([{"L": L, "K": K, "btc_filter": f}
                      for L, K, f in itertools.product(
                          (30, 60, 90), (3, 5), (True, False))], run_momentum)}
    for name, (grid, runner) in grids.items():
        fam, curve, curve_maj = family(name, grid, runner, S, days, d_warm,
                                       d_split, base)
        # RESERVA: so a configuracao que seria posta em producao, uma vez
        fam["holdout"] = {"all": metrics(curve, d_split, t1 + 1),
                          "majors21": metrics(curve_maj, d_split, t1 + 1),
                          "baseline_btc_sma200": metrics(base, d_split, t1 + 1)}
        fam["criteria_holdout"] = {"6_reserva_sharpe_positivo":
                                   fam["holdout"]["all"]["sharpe"] > 0}
        fam["validated"] = fam["passed_design"] and \
            fam["criteria_holdout"]["6_reserva_sharpe_positivo"]
        if name == "TREND":
            _, tr = run_trend(S, days, sorted(S), **fam["deploy_config"])
            tr = [t for t in tr if d_warm <= t["entry_d"] < d_split]
            rs = [t["r"] for t in tr]
            wins = [r for r in rs if r > 0]
            fam["deploy_trades_design"] = {
                "n": len(rs), "win_rate": round(100 * len(wins) / len(rs), 1),
                "expectancy_r": round(sum(rs) / len(rs), 2),
                "avg_win_r": round(sum(wins) / len(wins), 2),
                "avg_loss_r": round(sum(r for r in rs if r <= 0)
                                    / max(1, len(rs) - len(wins)), 2),
                "avg_days": round(sum(t["exit_d"] - t["entry_d"] for t in tr)
                                  / len(tr), 1)}
        res["families"][name] = fam
    with open("backtest/research.json", "w") as f:
        json.dump(res, f, indent=1)
    return res


if __name__ == "__main__":
    r = main(sys.argv[1])
    print("base design", r["baseline_btc_sma200_design"])
    for n, f in r["families"].items():
        print("=====", n, "grid+ share", f["grid_positive_share"])
        for k, v in f["grid"].items():
            a, m = v["all"], v["majors21"]
            print(f"  {k:52s} ret {a['return_pct']:8.1f}% dd {a['max_drawdown_pct']:5.1f}% sh {a['sharpe']:5.2f} inv {a['invested_pct']:3d}% | maj ret {m['return_pct']:7.1f}% sh {m['sharpe']:5.2f}")
        for fo in f["walk_forward"]["folds"]:
            print("  fold", fo["chosen"], fo["test"])
        print("  WF oos", f["walk_forward"]["oos"], "| majors", f["walk_forward_majors21"], "| base", f["baseline_oos"])
        print("  criteria", f["criteria_design"], "passed_design", f["passed_design"])
        print("  deploy", f["deploy_config"], f.get("deploy_trades_design"))
        print("  HOLDOUT", f["holdout"], f["criteria_holdout"], "VALIDATED", f["validated"])
