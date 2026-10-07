"""Investigacao 2026-10-07: COMPRESSAO DE VOLATILIDADE seguida de EXPANSAO
(diario, so compras).

HIPOTESE (escrita e guardada em commit antes de correr qualquer teste)
A volatilidade agrupa-se: depois de um periodo de amplitude invulgarmente
estreita costuma vir um movimento largo. Em mercado de alta (BTC acima da
media de 200 dias) esse movimento tende a ser para cima. Uma quebra de
maximos que sai de uma caixa apertada tem o risco perto (o meio da caixa) e
menos compradores atrasados do que uma quebra depois de uma subida longa,
que foi a entrada que falhou nos testes anteriores.

REGRAS
  caixa      : maximo e minimo dos N dias ANTERIORES ao dia do sinal
  compressao : a largura da caixa (max-min)/fecho esta entre os q mais
               baixos dos ultimos 120 dias dessa mesma medida
  gatilho    : o fecho do dia passa acima do maximo da caixa, com o BTC
               acima da SMA200
  entrada    : abertura do dia seguinte
  saida      : na abertura seguinte a (a) H dias em carteira, ou (b) um
               fecho abaixo do meio da caixa, ou (c) BTC fechar abaixo da
               SMA200. Sem stop intradiario.
  carteira   : ate 4 posicoes de 25% do capital; candidatos ordenados pela
               caixa mais apertada (percentil mais baixo).

GRELHA (12 configuracoes, fixada antes dos testes)
  N : 10, 20        dias da caixa
  q : 0.2, 0.4      percentil maximo da largura
  H : 5, 10, 20     dias de permanencia

JANELA (decisao do Rui, 2026-10-03): ultimos 24 meses ate a ultima vela
diaria completa; 18 de desenho e 6 de reserva. Dados anteriores so aquecem
indicadores e dao uma linha informativa que nao conta.
Walk-forward dentro do desenho: treino 183 dias, teste 91, passo 91.

CUSTOS: 0.25% de comissao (taxa real da Bybit UE) + 0.1% de slippage por
lado, tambem na referencia "BTC acima da SMA200".

CRITERIOS: os seis de tools/research.py. Menos de 40 operacoes nas janelas
de teste do walk-forward => AMOSTRA INSUFICIENTE.
"""
import datetime as dt
import itertools
import json
import sys
import time

from engine import backtest as B
from tools.research import MAJORS21, Series, metrics, prepare
from tools.research_dip import tstats, walk_forward, window

FEE, SLIP = 0.0025, 0.001
LOOK = 120
GRID = [{"N": N, "q": q, "H": H} for N, q, H in
        itertools.product((10, 20), (0.2, 0.4), (5, 10, 20))]
MIN_OOS_TRADES = 40


def boxes(s, N):
    """Por indice i: (maximo, minimo, percentil da largura) da caixa formada
    pelos dias i-N..i-1. Nada do dia i nem posterior entra na caixa."""
    n = len(s.c)
    hi, lo, w, pct = [None] * n, [None] * n, [None] * n, [None] * n
    for i in range(N, n):
        hi[i], lo[i] = max(s.h[i - N:i]), min(s.l[i - N:i])
        w[i] = (hi[i] - lo[i]) / s.c[i - 1]
    for i in range(N + LOOK - 1, n):
        past = w[i - LOOK + 1:i + 1]
        pct[i] = sum(1 for x in past if x < w[i]) / LOOK
    return hi, lo, pct


def run_squeeze(S, days, universe, N, q, H, max_pos=4, fee=FEE, _cache=None):
    """Decide no fecho do dia d so com velas ate d; executa na abertura de
    d+1. Devolve (curva [(dia, capital)], operacoes)."""
    bx = {a: boxes(S[a], N) for a in universe}
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
        for a, mid in pend_in:                    # entradas na abertura
            i = S[a].pos.get(d)
            if i is None or a in pos or len(pos) >= max_pos:
                continue
            notional = min(eq / max_pos, cash)
            if notional < 0.01 * eq:
                continue
            units = notional / (S[a].o[i] * (1 + SLIP)) / (1 + fee)
            cash -= notional
            pos[a] = {"units": units, "d": d, "cost": notional, "held": 0,
                      "last": S[a].o[i], "mid": mid}
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
            if p["held"] >= H or not bull or p["last"] < p["mid"]:
                pend_out.add(a)
        curve.append((d, eq))
        if not bull:
            continue
        cands = []
        for a in universe:
            s = S[a]
            i = s.pos.get(d)
            if a in pos or i is None or i < 200:
                continue
            hi, lo, pct = bx[a]
            if pct[i] is None or pct[i] >= q or s.c[i] <= hi[i]:
                continue
            cands.append((pct[i], a, (hi[i] + lo[i]) / 2))
        pend_in = [(a, mid) for _, a, mid in sorted(cands)]
    return curve, trades


def btc_sma200(S, days, fee=FEE):
    """Referencia com os mesmos custos: BTC quando fecha acima da SMA200."""
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
            eq *= 1 - fee - SLIP
            on = want
        curve.append((d, eq))
    return curve


def main(folder, out="backtest/research_squeeze.json"):
    data, _ = B.load_all(folder)
    bars, days = prepare(data)
    S = {a: Series(v) for a, v in bars.items()}
    d0, ds, d1 = window(S["BTC"].days[-1])
    majors = [a for a in MAJORS21 if a in S]
    base = btc_sma200(S, days)
    curves, cmaj, trades, grid = {}, {}, {}, {}
    for cfg in GRID:
        key = json.dumps(cfg, sort_keys=True)
        curves[key], trades[key] = run_squeeze(S, days, sorted(S), **cfg)
        cmaj[key] = run_squeeze(S, days, majors, **cfg)[0]
        grid[key] = {"all": metrics(curves[key], d0, ds),
                     "majors21": metrics(cmaj[key], d0, ds),
                     "trades": tstats([t for t in trades[key]
                                       if d0 <= t["entry_d"] < ds])}
    share = sum(1 for v in grid.values() if v["all"]["return_pct"] > 0) / len(grid)
    folds, oos, last, n_oos = walk_forward(curves, trades, d0, ds)
    _, oos_m, _, _ = walk_forward(cmaj, {}, d0, ds)
    _, base_oos, _, _ = walk_forward({"b": base}, {}, d0, ds)
    fpos = sum(1 for f in folds if f["test"]["return_pct"] > 0)
    oos_tr = [t for f in folds for t in trades[f["chosen"]]
              if f["test_days"][0] <= t["entry_d"] < f["test_days"][1]]
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
    warm = days[0] + 210 + LOOK
    iso = lambda d: str(dt.date(1970, 1, 1) + dt.timedelta(days=d))
    res = {"generated_at": int(time.time()), "hypothesis": "SQUEEZE_BREAKOUT",
           "assets": len(S),
           "window": {"design": [iso(d0), iso(ds - 1)],
                      "holdout": [iso(ds), iso(d1 - 1)]},
           "costs": {"fee_pct": FEE * 100, "slippage_pct": SLIP * 100},
           "grid": grid, "grid_positive_share": round(share, 2),
           "baseline_btc_sma200_design": metrics(base, d0, ds),
           "walk_forward": {"folds": folds, "oos": oos, "folds_positive": fpos,
                            "oos_trades": n_oos, "oos_trade_stats": tstats(oos_tr),
                            "majors21": oos_m, "baseline": base_oos},
           "deploy_config": cfg, "holdout": hold, "criteria": crit,
           "passed_all_six": passed, "verdict": verdict,
           "info_old_period": {"days": [iso(warm), iso(d0 - 1)],
                               "all": metrics(curves[last], warm, d0),
                               "baseline": metrics(base, warm, d0),
                               "trades": tstats([t for t in trades[last]
                                                 if warm <= t["entry_d"] < d0])}}
    with open(out, "w") as f:
        json.dump(res, f, indent=1)
    return res


if __name__ == "__main__":
    print(json.dumps(main(sys.argv[1]), indent=1))
