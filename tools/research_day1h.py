"""Investigacao 2026-10-11: DAY TRADE EM 1H, recuo a EMA20 de 1H a favor da
tendencia de 4H (so compras). Hipotese 2 da fila do Rui (2026-10-09).

HIPOTESE (escrita e guardada em commit antes de correr qualquer teste)
Dentro de uma tendencia de 4H, os recuos de 1H ate a media curta sao
realizacao de lucros e nao inversao; a vela que recupera a media retoma a
tendencia. Risco declarado a partida: com stops curtos, os custos (0,7% ida
e volta) comem uma parte grande de cada R; por isso ha distancia minima de
stop.

REGRAS (decisao no fecho da vela i de 1H, so com velas ja fechadas)
  mercado  : BTC fechou o ultimo dia completo acima da SMA200 diaria
  tendencia: na moeda, na ultima vela de 4H JA FECHADA no fecho de i:
             EMA20 > EMA50 e fecho acima da EMA50
  gatilho  : minimo(i) <= EMA20 de 1H e fecho(i) > EMA20 de 1H, com RSI14
             de 1H entre 40 e 60
  entrada  : abertura da vela i+1
  stop     : minimo das velas i-2..i menos 0,2 ATR14 de 1H; se ficar a
             menos de D da abertura de entrada, NAO ha operacao
  objetivo : um so, a k R da entrada (100%)
  tempo    : saida ao fecho da vela em que se completam H horas
  carteira : uma operacao por moeda, 2 ao mesmo tempo, 25% do capital em
             cada; com mais sinais do que vagas, primeiro a tendencia de 4H
             mais forte (EMA20/EMA50)

GRELHA (6, a da fila do Rui, fixada antes dos testes)
  H=24: k 1,5 e 2 x D 1,5% e 2,5%;  H=12: k 1,5 com D 1,5% e D 2,5%

DADOS: velas de 1H do ramo history (pasta 1h/, desde 2024-09) e 4H da raiz.
JANELA: ultimos 24 meses ate ao ultimo dia completo; 18 de desenho, 6 de
reserva; walk-forward treino 183 dias, teste 91 (4 dobras). Nao ha "periodo
antigo" em 1H (o historico de 1H comeca um mes antes da janela).

CUSTOS: 0,25% de comissao + 0,1% de slippage por lado.

CRITERIOS: os seis de tools/research.py mais o 7.o (R medio fora da amostra
acima do percentil 95 de 1000 series de entradas ao acaso com a mesma
geometria, +-360 velas de 1H = +-15 dias), e reporta-se o custo medio por
operacao em R. Menos de 40 operacoes nas dobras de teste => AMOSTRA
INSUFICIENTE. Veredicto maximo: CANDIDATA (papel primeiro).
"""
import bisect
import json
import os
import sys

from engine import backtest as B
from tools import research_rlib as R
from tools.afinacao_lib import btc_above_sma200
from tools.research import MAJORS21, Series, prepare
from tools.research_dip import window
from tools.research_squeeze import btc_sma200

TF = 3600
GRID = [{"k": 1.5, "D": 0.015, "H": 24}, {"k": 2.0, "D": 0.015, "H": 24},
        {"k": 1.5, "D": 0.025, "H": 24}, {"k": 2.0, "D": 0.025, "H": 24},
        {"k": 1.5, "D": 0.015, "H": 12}, {"k": 1.5, "D": 0.025, "H": 12}]


def trend_4h(c4):
    """(aberturas, forca): forca[j] = EMA20/EMA50 - 1 se a vela j de 4H esta
    em tendencia (EMA20 > EMA50 e fecho > EMA50), senao None."""
    c = [x["c"] for x in c4]
    e20, e50 = R.ema(c, 20), R.ema(c, 50)
    st = [e20[j] / e50[j] - 1 if e50[j] is not None and e20[j] > e50[j]
          and c[j] > e50[j] else None for j in range(len(c4))]
    return [x["t"] for x in c4], st


def signals(c1, c4, btc_up, k, D):
    """{t da abertura da entrada: sinal}. So usa velas de 1H 0..i, velas de
    4H ja fechadas no fecho de i e dias completos."""
    c = [x["c"] for x in c1]
    e20, rs, at = R.ema(c, 20), R.rsi(c), R.atr(c1)
    t4, st = trend_4h(c4)
    out = {}
    for i in range(60, len(c1)):
        x = c1[i]
        if not (x["l"] <= e20[i] < x["c"] and 40 <= rs[i] <= 60):
            continue
        tc = x["t"] + TF
        if not btc_up.get(tc // R.DAY - 1):
            continue
        j = bisect.bisect_right(t4, tc - B.H4) - 1    # ultima 4H fechada
        if j < 0 or st[j] is None or tc - (t4[j] + B.H4) >= B.H4:
            continue
        stop = min(y["l"] for y in c1[i - 2:i + 1]) - 0.2 * at[i]
        if stop <= 0:
            continue
        out[tc] = {"stop": stop, "tp_r": k, "min_stop": D, "partials": [100],
                   "rank": -st[j]}
    return out


def main(folder, out="backtest/research_day1h.json"):
    d4, _ = B.load_all(folder)
    d1h, _ = B.load_all(os.path.join(folder, "1h"), min_bars=2000, tf=TF)
    data = {a: v for a, v in d1h.items() if a in d4}
    btc_up = btc_above_sma200(d4["BTC"])
    bars, days = prepare({"BTC": d4["BTC"]})
    S = {"BTC": Series(bars["BTC"])}
    d0, ds, d1 = window(S["BTC"].days[-1])
    first = max(v[0]["t"] for v in data.values()) // R.DAY + 4
    d0 = max(d0, first)
    majors = [a for a in MAJORS21 if a in data]
    base = btc_sma200(S, days)
    cache = {}

    def runner(cfg, universe):
        key = (cfg["k"], cfg["D"])
        if key not in cache:
            cache[key] = {a: signals(data[a], d4[a], btc_up, *key)
                          for a in data}
        return R.simulate(data, cache[key], TF, cfg["H"] * 3600, universe,
                          max_pos=2)

    res = R.evaluate("DAYTRADE_1H_EMA20", GRID, runner, data, TF,
                     lambda cfg: cfg["H"] * 3600, 360, majors, base, d0, ds, d1)
    with open(out, "w") as f:
        json.dump(res, f, indent=1)
    return res


if __name__ == "__main__":
    print(json.dumps(main(sys.argv[1]), indent=1))
