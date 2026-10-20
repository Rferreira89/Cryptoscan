"""Investigacao 2026-10-20: IMPULSO_AMPLITUDE (4H, so compras). Hipotese nova
(fila do Rui vazia, mortos sem sucessor), escrita antes de testar (commit
f5c237b).

LOGICA: "breadth thrust" de Zweig. Quando o mercado passa em poucos dias de
quase todas as moedas fracas para quase todas fortes, e dinheiro novo a
entrar em todo o lado; costuma marcar o inicio de uma subida de semanas.
Riscos declarados: acontecimentos raros, operacoes agrupadas nos mesmos dias,
a familia "comprar forca" perdeu sempre neste projeto.

REGRAS (decisao no fecho da vela i de 4H, so velas ja fechadas):
  amplitude: A(i) = fracao das moedas (>= 20 com vela nesse instante) com
             fecho acima da sua SMA20 de 4H
  impulso  : A(i) >= U, A(i-1) < U e min(A nas 60 velas anteriores) <= 0,30
  moedas   : as que fecham i acima da sua SMA20; carteira 4 x 25%, uma por
             moeda, primeiro a menos esticada ((fecho - SMA20) / ATR14)
  entrada  : abertura da vela i+1; stop = fecho - 2 ATR14; um objetivo a 3R;
             sem stop na entrada; saida ao fim de H dias
  mercado  : BTC acima da SMA200 diaria (ultimo dia fechado), se pedido
GRELHA (6): U in {0,75; 0,85} x H in {5, 10} com o filtro do BTC; mais
            U = 0,75 x H in {5, 10} sem o filtro.

Uso: python -m tools.research_impulso <historico>
"""
import json
import sys

from engine import backtest as B
from tools import research_rlib as R
from tools.afinacao_lib import btc_above_sma200
from tools.research import MAJORS21, Series, prepare
from tools.research_dip import window
from tools.research_squeeze import btc_sma200

TF = B.H4
GRID = ([{"U": u, "H": h, "btc": True} for u in (0.75, 0.85) for h in (5, 10)]
        + [{"U": 0.75, "H": h, "btc": False} for h in (5, 10)])
LOW, LOOK, MIN_COINS, STOP_ATR, TP_R = 0.30, 60, 20, 2.0, 3


def above_ma(c4):
    """{t de abertura: (acima da SMA20?, esticamento em ATR)} so com passado."""
    c = [x["c"] for x in c4]
    ma, at = R.sma(c, 20), R.atr(c4)
    out = {}
    for i, b in enumerate(c4):
        if ma[i] is None:
            continue
        ext = (c[i] - ma[i]) / at[i] if at[i] else None
        out[b["t"]] = (c[i] > ma[i], ext, at[i])
    return out


def breadth(states):
    """{t de abertura: A(t)} com pelo menos MIN_COINS moedas."""
    cnt = {}
    for st in states.values():
        for t, (up, _, _) in st.items():
            n, k = cnt.get(t, (0, 0))
            cnt[t] = (n + 1, k + up)
    return {t: k / n for t, (n, k) in cnt.items() if n >= MIN_COINS}


def thrusts(amp, u):
    """Instantes de abertura t das velas cujo fecho da o impulso."""
    ts = sorted(amp)
    out = set()
    for j in range(1, len(ts)):
        t, tp = ts[j], ts[j - 1]
        if tp != t - TF or not (amp[t] >= u > amp[tp]):
            continue
        prev = [amp[x] for x in ts[max(0, j - LOOK):j] if x >= t - LOOK * TF]
        if prev and min(prev) <= LOW:
            out.add(t)
    return out


def signals(c4, st, th, btc_up, use_btc):
    """{t de fecho (= abertura da entrada): sinal} para uma moeda."""
    out = {}
    for b in c4:
        t = b["t"]
        if t not in th or t not in st:
            continue
        up, ext, at = st[t]
        if not up or not at or ext is None:
            continue
        tc = t + TF
        if use_btc and not btc_up.get((tc - R.DAY) // R.DAY):
            continue
        stop = b["c"] - STOP_ATR * at
        if stop <= 0:
            continue
        out[tc] = {"stop": stop, "tp_r": TP_R, "partials": [100],
                   "breakeven": False, "rank": ext}
    return out


def all_signals(data, u, btc_up, use_btc, assets=None):
    states = {a: above_ma(c4) for a, c4 in data.items()}
    th = thrusts(breadth(states), u)
    return {a: signals(data[a], states[a], th, btc_up, use_btc)
            for a in (assets or data)}


def main(folder, out="backtest/research_impulso.json"):
    data, _ = B.load_all(folder)
    btc_up = btc_above_sma200(data["BTC"])
    bars, days = prepare(data)
    S = {"BTC": Series(bars["BTC"])}
    d0, ds, d1 = window(S["BTC"].days[-1])
    majors = [a for a in MAJORS21 if a in data]
    base = btc_sma200(S, days)
    cache = {}

    def runner(cfg, universe):
        k = (cfg["U"], cfg["btc"])
        if k not in cache:
            cache[k] = all_signals(data, cfg["U"], btc_up, cfg["btc"])
        return R.simulate(data, cache[k], TF, cfg["H"] * R.DAY, universe)

    res = R.evaluate("IMPULSO_AMPLITUDE", GRID, runner, data, TF,
                     lambda cfg: cfg["H"] * R.DAY, 90, majors, base, d0, ds,
                     d1, warm=days[0] + 210)
    ths = {u: sorted(thrusts(breadth({a: above_ma(c) for a, c in data.items()}), u))
           for u in (0.75, 0.85)}
    res["impulsos"] = {str(u): {"n": len(v), "desenho": sum(1 for t in v if d0 <= t // R.DAY < ds),
                                "reserva": sum(1 for t in v if ds <= t // R.DAY < d1)}
                       for u, v in ths.items()}
    with open(out, "w") as f:
        json.dump(res, f, indent=1)
    return res


if __name__ == "__main__":
    print(json.dumps(main(sys.argv[1]), indent=1))
