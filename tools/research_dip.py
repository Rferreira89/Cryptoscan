"""Investigacao 2026-10-04: COMPRA DE QUEDAS em mercado de alta (diario).

HIPOTESE (escrita antes de correr qualquer teste)
Com o BTC acima da media de 200 dias, uma queda forte e rapida de uma moeda
(pelo menos k ATR de 20 dias em 3 dias) e muitas vezes venda forcada
(liquidacoes, panico) e nao mudanca de tendencia; o preco tende a recuperar
parte nos dias seguintes. Compra-se na abertura seguinte, sem stop de preco
(um stop apertado e o que mata a reversao a media), e sai-se por tempo ao fim
de H dias, ou mais cedo se o BTC fechar abaixo da media de 200 dias.
So compras, ate 4 posicoes em partes iguais (25% do capital cada), candidatos
ordenados pela maior queda. Universo: todas as moedas com historico.

GRELHA (12 configuracoes, fixada antes dos testes)
  k           : 2, 3      queda minima em ATR20 nos ultimos 3 dias
  H           : 3, 5, 10  dias de permanencia
  asset_trend : True, False  exigir a propria moeda acima da SMA200

JANELA (decisao do Rui, 2026-10-03): ultimos 24 meses; 18 de desenho e 6 de
reserva. Dados anteriores so aquecem indicadores e dao uma linha informativa.
Walk-forward dentro do desenho: treino 183 dias, teste 91 dias, passo 91
(4 dobras; os 548/183 de tools/research.py nao cabem em 18 meses).

CRITERIOS (os seis de tools/research.py) + regra de amostra: menos de 40
operacoes nas janelas de teste do walk-forward => AMOSTRA INSUFICIENTE.
Custos: 0.1% comissao + 0.1% slippage por lado. Linha informativa adicional
com a comissao real da Bybit UE (0.25%), que nao conta para o veredicto.
"""
import datetime as dt
import itertools
import json
import sys
import time

from engine import backtest as B
from tools.research import (FEE, SLIP, MAJORS21, Series, btc_sma200, metrics,
                            prepare)

GRID = [{"k": k, "H": H, "asset_trend": t} for k, H, t in
        itertools.product((2, 3), (3, 5, 10), (True, False))]
TRAIN, TEST, MIN_OOS_TRADES = 183, 91, 40


def run_dip(S, days, universe, k, H, asset_trend, n=3, max_pos=4, fee=FEE):
    """Decide no fecho do dia d so com velas ate d; executa na abertura de
    d+1. Devolve (curva [(dia, capital)], operacoes)."""
    cash, pos, curve, trades = 1.0, {}, [], []
    pend_in, pend_out = [], set()
    btc = S["BTC"]
    for d in days:
        for a in list(pos):                       # saidas na abertura
            i = S[a].pos.get(d)
            if a in pend_out and i is not None:
                p = pos.pop(a)
                got = p["units"] * S[a].o[i] * (1 - SLIP) * (1 - fee)
                cash += got
                trades.append({"asset": a, "entry_d": p["d"], "exit_d": d,
                               "ret": got / p["cost"] - 1})
        pend_out -= set(a for a in pend_out if a not in pos)
        eq = cash + sum(p["units"] * (S[a].o[S[a].pos[d]] if d in S[a].pos
                                      else p["last"]) for a, p in pos.items())
        for a in pend_in:                         # entradas na abertura
            i = S[a].pos.get(d)
            if i is None or a in pos or len(pos) >= max_pos:
                continue
            notional = min(eq / max_pos, cash)
            if notional < 0.01 * eq:
                continue
            units = notional / (S[a].o[i] * (1 + SLIP)) / (1 + fee)
            cash -= notional
            pos[a] = {"units": units, "d": d, "cost": notional, "held": 0,
                      "last": S[a].o[i]}
        pend_in = []
        bi = btc.pos.get(d)                       # fecho: marca e decide
        bull = bi is not None and btc.above200(bi)
        eq = cash
        for a, p in pos.items():
            i = S[a].pos.get(d)
            if i is not None:
                p["last"] = S[a].c[i]
                p["held"] += 1
            eq += p["units"] * p["last"]
            if p["held"] >= H or not bull:
                pend_out.add(a)
        curve.append((d, eq))
        if not bull:
            continue
        cands = []
        for a in universe:
            s = S[a]
            i = s.pos.get(d)
            if a in pos or i is None or i < 200 or not s.atr[i]:
                continue
            if asset_trend and not s.above200(i):
                continue
            drop = (s.c[i - n] - s.c[i]) / s.atr[i]
            if drop >= k:
                cands.append((drop, a))
        pend_in = [a for _, a in sorted(cands, reverse=True)]
    return curve, trades


def walk_forward(curves, trades, d0, d1, train=TRAIN, test=TEST):
    folds, chain, n_tr, start, best = [], [], 0, d0, None
    while start + train + test <= d1:
        a, b, c = start, start + train, start + train + test
        best = max(sorted(curves), key=lambda k: (metrics(curves[k], a, b)
                                                  or {"sharpe": -9})["sharpe"])
        n = sum(1 for t in trades.get(best, []) if b <= t["entry_d"] < c)
        folds.append({"train": [a, b], "test_days": [b, c], "chosen": best,
                      "test": metrics(curves[best], b, c), "trades": n})
        n_tr += n
        pts = [(d, e) for d, e in curves[best] if b <= d < c]
        chain += [pts[i][1] / pts[i - 1][1] for i in range(1, len(pts))]
        start += test
    eq, curve = 1.0, [(0, 1.0)]
    for j, r in enumerate(chain):
        eq *= r
        curve.append((j + 1, eq))
    return folds, metrics(curve), best, n_tr


def window(last_day):
    """(inicio, corte, fim exclusivo) em dias: 24 meses ate ao ultimo dia
    completo; os ultimos 6 meses sao a reserva."""
    e = dt.date(1970, 1, 1) + dt.timedelta(days=last_day + 1)

    def back(m):
        y, mo = divmod(e.year * 12 + e.month - 1 - m, 12)
        return (dt.date(y, mo + 1, e.day) - dt.date(1970, 1, 1)).days
    return back(24), back(6), last_day + 1


def tstats(tr):
    if not tr:
        return {"n": 0}
    r = [t["ret"] for t in tr]
    return {"n": len(r), "win_rate": round(100 * sum(x > 0 for x in r) / len(r), 1),
            "avg_ret_pct": round(100 * sum(r) / len(r), 2),
            "worst_pct": round(100 * min(r), 1), "best_pct": round(100 * max(r), 1)}


def main(folder):
    data, _ = B.load_all(folder)
    bars, days = prepare(data)
    S = {a: Series(v) for a, v in bars.items()}
    d0, ds, d1 = window(S["BTC"].days[-1])
    majors = [a for a in MAJORS21 if a in S]
    base = btc_sma200(S, days)
    curves, cmaj, trades, grid = {}, {}, {}, {}
    for cfg in GRID:
        key = json.dumps(cfg, sort_keys=True)
        curves[key], trades[key] = run_dip(S, days, sorted(S), **cfg)
        cmaj[key] = run_dip(S, days, majors, **cfg)[0]
        grid[key] = {"all": metrics(curves[key], d0, ds),
                     "majors21": metrics(cmaj[key], d0, ds),
                     "trades": tstats([t for t in trades[key]
                                       if d0 <= t["entry_d"] < ds])}
    share = sum(1 for v in grid.values() if v["all"]["return_pct"] > 0) / len(grid)
    folds, oos, last, n_oos = walk_forward(curves, trades, d0, ds)
    _, oos_m, _, _ = walk_forward(cmaj, {}, d0, ds)
    _, base_oos, _, _ = walk_forward({"b": base}, {}, d0, ds)
    fpos = sum(1 for f in folds if f["test"]["return_pct"] > 0)
    crit = {"1_oos_retorno_e_sharpe": oos["return_pct"] > 0 and oos["sharpe"] > 0.5,
            "2_janelas_positivas": fpos / len(folds) >= 0.6,
            "3_grelha_estavel": share >= 0.75,
            "4_grandes_moedas_2021": oos_m["return_pct"] > 0,
            "5_melhor_que_btc_sma200": oos["sharpe"] > base_oos["sharpe"]}
    # RESERVA: uma unica avaliacao, so da configuracao escolhida
    cfg = json.loads(last)
    hold = {"all": metrics(curves[last], ds, d1),
            "majors21": metrics(cmaj[last], ds, d1),
            "baseline_btc_sma200": metrics(base, ds, d1),
            "trades": tstats([t for t in trades[last] if ds <= t["entry_d"] < d1])}
    crit["6_reserva_sharpe_positivo"] = hold["all"]["sharpe"] > 0
    passed = all(crit.values())
    verdict = ("AMOSTRA INSUFICIENTE" if n_oos < MIN_OOS_TRADES else
               "VALIDADA" if passed else "NAO VALIDADA")
    warm = days[0] + 210
    c25, t25 = run_dip(S, days, sorted(S), fee=0.0025, **cfg)
    iso = lambda d: str(dt.date(1970, 1, 1) + dt.timedelta(days=d))
    res = {"generated_at": int(time.time()), "hypothesis": "DIP_BULL",
           "window": {"design": [iso(d0), iso(ds - 1)],
                      "holdout": [iso(ds), iso(d1 - 1)]},
           "costs": {"fee_pct": FEE * 100, "slippage_pct": SLIP * 100},
           "grid": grid, "grid_positive_share": round(share, 2),
           "baseline_btc_sma200_design": metrics(base, d0, ds),
           "walk_forward": {"folds": folds, "oos": oos, "folds_positive": fpos,
                            "oos_trades": n_oos, "majors21": oos_m,
                            "baseline": base_oos},
           "deploy_config": cfg, "holdout": hold, "criteria": crit,
           "verdict": verdict,
           "info_old_period": {"days": [iso(warm), iso(d0 - 1)],
                               "all": metrics(curves[last], warm, d0),
                               "baseline": metrics(base, warm, d0),
                               "trades": tstats([t for t in trades[last]
                                                 if warm <= t["entry_d"] < d0])},
           "info_fee_025": {"design": metrics(c25, d0, ds),
                            "holdout": metrics(c25, ds, d1)}}
    with open("backtest/research_dip.json", "w") as f:
        json.dump(res, f, indent=1)
    return res


if __name__ == "__main__":
    print(json.dumps(main(sys.argv[1]), indent=1))
