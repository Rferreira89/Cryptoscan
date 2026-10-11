"""Investigacao 2026-10-11: OVERSOLD BOUNCE no 4H (so compras).
Hipotese 1 da fila do Rui (pedida em 2026-10-09).

HIPOTESE (escrita e guardada em commit antes de correr qualquer teste)
Em mercado de alta (BTC acima da media de 200 dias), quedas rapidas levam o
RSI de 4H a sobrevenda por venda forcada; a primeira vela de recuperacao
marca o fim da pressao vendedora e o preco tende a voltar a media.

REGRAS (decisao no fecho da vela i de 4H, so com velas ja fechadas)
  mercado  : BTC fechou o ultimo dia completo acima da sua SMA200 diaria
  sobrevenda: RSI14 de 4H abaixo de X em pelo menos uma das velas i-2, i-1, i
  gatilho  : fecho da vela i acima do maximo da vela i-1 e RSI(i) > RSI(i-1)
  tendencia: (opcional) a moeda fechou o ultimo dia completo acima da sua
             EMA200 diaria
  entrada  : abertura da vela i+1
  stop     : o mais baixo de (a) minimo das ultimas 6 velas (i-5..i) menos
             0,1 ATR14 e (b) fecho(i) menos 1,25 ATR14  -> o stop fica abaixo
             do minimo da queda e nunca a menos de 1,25 ATR
  objetivos: 1.o = media simples de 20 velas de 4H (valor no fecho de i);
             2.o = maximo das 42 velas (7 dias) anteriores a i. Vende 50% no
             1.o e o resto no 2.o; depois do 1.o o stop passa para a entrada
             (engine/trade.py, igual ao sistema ao vivo). Se o 2.o nao ficar
             pelo menos 0,5% acima do 1.o, ha um so objetivo (100%).
  sem operacao se o 1.o objetivo ficar a menos de 1% acima do fecho(i)
             (nao paga os 0,7% de custos), ou se a abertura seguinte ja
             estiver no stop ou no objetivo
  tempo    : saida ao fecho da vela em que se completam H dias
  carteira : ate 4 operacoes, uma por moeda, 25% do capital cada; se houver
             mais sinais do que vagas, primeiro o RSI mais baixo

GRELHA (5 configuracoes, a da fila do Rui, fixada antes dos testes)
  X=25 H=3 | X=25 H=7 | X=30 H=3 | X=30 H=7 | X=30 H=3 com EMA200 da moeda

JANELA (decisao do Rui, 2026-10-03): ultimos 24 meses ate ao ultimo dia
completo; 18 de desenho, 6 de reserva. Walk-forward no desenho: treino 183
dias, teste 91, passo 91 (4 dobras), escolha pelo Sharpe do treino.

CUSTOS: 0,25% de comissao + 0,1% de slippage por lado.

CRITERIOS (declarados antes): os seis de tools/research.py mais o 7.o:
R medio das operacoes fora da amostra (dobras de teste do walk-forward +
reserva) acima do percentil 95 de 1000 series de entradas ao acaso com a
mesma geometria (+-90 velas de 4H). Menos de 40 operacoes nas dobras de
teste => AMOSTRA INSUFICIENTE. Veredicto maximo: CANDIDATA (papel primeiro).
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
GRID = [{"X": 25, "H": 3, "trend": False}, {"X": 25, "H": 7, "trend": False},
        {"X": 30, "H": 3, "trend": False}, {"X": 30, "H": 7, "trend": False},
        {"X": 30, "H": 3, "trend": True}]
LOW_BARS, HIGH_BARS, MIN_ATR, MIN_TP1 = 6, 42, 1.25, 0.01


def above_ema200_daily(c4):
    """{dia: True/False} conhecido no fecho desse dia."""
    d1 = B.daily(c4)
    e = R.ema([x["c"] for x in d1], 200)
    return {x["t"] // R.DAY: x["c"] > e[k] for k, x in enumerate(d1)
            if e[k] is not None}


def signals(c4, btc_up, X, trend):
    """{t da abertura da entrada: sinal}. O sinal da vela i so usa velas
    0..i e dias completamente fechados ate ao fecho de i."""
    c = [x["c"] for x in c4]
    rs, at, ma = R.rsi(c), R.atr(c4), R.sma(c, 20)
    up = above_ema200_daily(c4) if trend else None
    out = {}
    for i in range(HIGH_BARS, len(c4)):
        if rs[i - 2] is None or at[i] is None:
            continue
        tc = c4[i]["t"] + TF
        day = tc // R.DAY - 1                  # ultimo dia completo
        if not btc_up.get(day):
            continue
        lowest = min(rs[i - 2:i + 1])
        if lowest >= X or not (c[i] > c4[i - 1]["h"] and rs[i] > rs[i - 1]):
            continue
        if trend and not up.get(day):
            continue
        tp1 = ma[i]
        if tp1 < c[i] * (1 + MIN_TP1):
            continue
        stop = min(min(x["l"] for x in c4[i - LOW_BARS + 1:i + 1]) - 0.1 * at[i],
                   c[i] - MIN_ATR * at[i])
        if stop <= 0:
            continue
        tp2 = max(x["h"] for x in c4[i - HIGH_BARS:i])
        two = tp2 >= tp1 * 1.005
        out[tc] = {"stop": stop, "tp": [tp1, tp2] if two else [tp1],
                   "partials": [50, 50] if two else [100], "rank": lowest}
    return out


def main(folder, out="backtest/research_bounce.json"):
    data, _ = B.load_all(folder)
    btc_up = btc_above_sma200(data["BTC"])
    bars, days = prepare(data)
    S = {"BTC": Series(bars["BTC"])}
    d0, ds, d1 = window(S["BTC"].days[-1])
    majors = [a for a in MAJORS21 if a in data]
    base = btc_sma200(S, days)
    cache = {}

    def runner(cfg, universe):
        k = (cfg["X"], cfg["trend"])
        if k not in cache:
            cache[k] = {a: signals(data[a], btc_up, *k) for a in data}
        return R.simulate(data, cache[k], TF, cfg["H"] * R.DAY, universe)

    res = R.evaluate("OVERSOLD_BOUNCE_4H", GRID, runner, data, TF,
                     lambda cfg: cfg["H"] * R.DAY, 90, majors, base, d0, ds,
                     d1, warm=days[0] + 210)
    with open(out, "w") as f:
        json.dump(res, f, indent=1)
    return res


if __name__ == "__main__":
    print(json.dumps(main(sys.argv[1]), indent=1))
