"""Investigacao 2026-10-14: FUNDING MUITO NEGATIVO COM O PRECO A AGUENTAR
(4H, so compras). Hipotese 4 da fila do Rui (pedida em 2026-10-11).

HIPOTESE (escrita na fila e no pre-registo de 2026-10-14 antes de testar):
funding muito negativo nos perpetuos quer dizer que ha muita gente vendida
a pagar para manter a posicao; se o preco nao cai, essas posicoes acabam
por ser fechadas a forca e empurram o preco para cima.

REGRAS (decisao no fecho da vela i de 4H, so com dados ja publicados):
  funding  : f24 = media das liquidacoes de funding com instante em
             (tc - 24h, tc], tc = fecho da vela i (com liquidacoes de 8h sao
             as ultimas 3). f24 < 0 E f24 abaixo do percentil P dos valores
             de f24 calculados em cada liquidacao dos 90 dias anteriores
             (tc - 90d, tc - 24h]; exige pelo menos 60 dias de historico de
             funding antes de tc (o ficheiro comeca em 2024-08)
  gatilho  : fecho(i) > maximo(i-1)
  mercado  : (opcional) BTC fechou o ultimo dia completo acima da SMA200
  entrada  : abertura da vela i+1
  stop     : fecho(i) - 1,5 ATR14 de 4H; um objetivo a 2R (100%); sem stop
             na entrada; saida ao fim de 3 dias
  carteira : 4 operacoes de 25%, uma por moeda; primeiro o f24 mais negativo
GRELHA (4): P in {10, 5} x filtro do BTC in {sim, nao}.
Custos, janela (24 meses ate ao ultimo dia com funding: 18 desenho + 6
reserva), walk-forward e os 7 criterios: tools/research_rlib.evaluate.

Uso: python -m tools.research_funding <historico>
"""
import bisect
import csv
import gzip
import json
import os
import sys

from engine import backtest as B
from tools import research_rlib as R
from tools.afinacao_lib import btc_above_sma200
from tools.research import MAJORS21, Series, prepare
from tools.research_dip import window
from tools.research_squeeze import btc_sma200

TF = B.H4
GRID = [{"P": p, "btc": b} for p in (10, 5) for b in (True, False)]
HOLD = 3 * R.DAY
LOOKBACK, MIN_HIST, WIN = 90 * R.DAY, 60 * R.DAY, R.DAY


def load_funding(folder):
    """{moeda: [(t, taxa)]} da pasta funding/ do ramo history."""
    out = {}
    d = os.path.join(folder, "funding")
    for fn in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        if fn.endswith(".csv.gz"):
            with gzip.open(os.path.join(d, fn), "rt") as f:
                rows = sorted((int(r[0]), float(r[1])) for r in csv.reader(f) if r)
            out[fn[:-7]] = rows
    return out


def f24_series(fr):
    """[(t, media das liquidacoes em (t-24h, t])] em cada liquidacao."""
    ts = [x[0] for x in fr]
    out = []
    for k, (t, _) in enumerate(fr):
        j = bisect.bisect_right(ts, t - WIN)
        v = [x[1] for x in fr[j:k + 1]]
        out.append((t, sum(v) / len(v)))
    return out


def funding_state(f24, tc, P):
    """(f24 atual, extremo?) conhecido no instante tc, ou None."""
    ts = [x[0] for x in f24]
    k = bisect.bisect_right(ts, tc) - 1
    if k < 0 or tc - f24[k][0] >= 8 * 3600 + 1 or tc - f24[0][0] < MIN_HIST:
        return None
    cur = f24[k][1]
    lo = bisect.bisect_right(ts, tc - LOOKBACK)
    hist = sorted(x[1] for x in f24[lo:k] if x[0] <= tc - WIN)
    if len(hist) < 30:
        return None
    thr = hist[int(P / 100 * (len(hist) - 1))]
    return cur, cur < 0 and cur < thr


def signals(c4, f24, btc_up, P, btc_filter):
    """{t da abertura da entrada: sinal}. A vela i so usa velas 0..i, o
    funding publicado ate ao fecho de i e dias completos ja fechados."""
    if not f24:
        return {}
    at = R.atr(c4)
    out = {}
    for i in range(20, len(c4)):
        if at[i] is None:
            continue
        b, tc = c4[i], c4[i]["t"] + TF
        if not b["c"] > c4[i - 1]["h"]:
            continue
        if btc_filter and not btc_up.get((tc - R.DAY) // R.DAY):
            continue
        st = funding_state(f24, tc, P)
        if not st or not st[1]:
            continue
        stop = b["c"] - 1.5 * at[i]
        if stop <= 0:
            continue
        out[tc] = {"stop": stop, "tp_r": 2, "partials": [100],
                   "breakeven": False, "rank": st[0], "f24": st[0]}
    return out


def main(folder, out="backtest/research_funding.json"):
    data, _ = B.load_all(folder)
    fund = load_funding(folder)
    data = {a: v for a, v in data.items() if a in fund or a == "BTC"}
    btc_up = btc_above_sma200(data["BTC"])
    bars, days = prepare(data)
    S = {"BTC": Series(bars["BTC"])}
    # funding mensal: a janela acaba no ultimo dia com funding do BTC
    d0, ds, d1 = window(min(S["BTC"].days[-1], fund["BTC"][-1][0] // R.DAY))
    f24 = {a: f24_series(v) for a, v in fund.items()}
    majors = [a for a in MAJORS21 if a in data]
    base = btc_sma200(S, days)
    cache = {}

    def runner(cfg, universe):
        k = (cfg["P"], cfg["btc"])
        if k not in cache:
            cache[k] = {a: signals(data[a], f24.get(a), btc_up, *k)
                        for a in data if a in f24}
        return R.simulate(data, cache[k], TF, HOLD, universe)

    res = R.evaluate("FUNDING_NEGATIVO", GRID, runner, data, TF,
                     lambda cfg: HOLD, 90, majors, base, d0, ds, d1)
    res["funding_moedas"] = len(fund)
    res["info_old_period"] = "nao existe: o funding do ramo history comeca em 2024-08"
    with open(out, "w") as f:
        json.dump(res, f, indent=1)
    return res


if __name__ == "__main__":
    print(json.dumps(main(sys.argv[1]), indent=1))
