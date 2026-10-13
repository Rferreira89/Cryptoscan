"""Investigacao 2026-10-13: OVERSOLD BOUNCE no 4H com uma saida melhor.
Hipotese 3 da fila do Rui (pedida em 2026-10-11).

HIPOTESE (escrita na fila antes de qualquer teste): o gatilho do Oversold
Bounce bate o acaso nos momentos de entrada (percentil 99,5 em 2026-10-11),
mas a saida original so empatava. Com uma saida diferente pode ter vantagem.

GATILHO: exatamente tools/research_bounce.signals, sem filtro da EMA200 da
moeda (BTC acima da SMA200 diaria; RSI14 4H abaixo de X numa das 3 ultimas
velas; fecho acima do maximo da anterior com RSI a subir; media de 20 velas
pelo menos 1% acima do fecho). Como no papel (engine/paper_bounce.plans),
nenhuma saida entra se a abertura seguinte ja estiver na media de 20 velas
ou acima.

SAIDAS (iguais as do papel ao vivo):
  V1 plano do sistema ao vivo (engine/risk.plan) com o stop do gatilho e a
     entrada ao preco de abertura; objetivos em niveis reais (min. 1R),
     vendas parciais do plano, stop na entrada depois do 1.o; 30 dias;
     sem operacao se o plano for recusado
  V2 stop = fecho do gatilho - 1,5 ATR14; um objetivo a 2R; sem stop na
     entrada; 3 dias
  V3 stop original do gatilho; um objetivo a 2R; sem stop na entrada; 3 dias

GRELHA (6, a da fila): {V1, V2, V3} x X in {25, 30}.
Carteira (4 de 25%, uma por moeda, primeiro o RSI mais baixo), custos
(0,25% + 0,1% por lado), janela (24 meses: 18 desenho + 6 reserva),
walk-forward e os 7 criterios de tools/research_rlib.evaluate.
"""
import json
import sys

from engine import backtest as B, config, risk
from tools import research_rlib as R
from tools.afinacao_lib import btc_above_sma200
from tools.research import MAJORS21, Series, prepare
from tools.research_bounce import signals
from tools.research_dip import window
from tools.research_squeeze import btc_sma200

TF = B.H4
GRID = [{"V": v, "X": x} for v in ("V1", "V2", "V3") for x in (25, 30)]
HOLD = {"V1": 30 * R.DAY, "V2": 3 * R.DAY, "V3": 3 * R.DAY}
CFG = dict(config.load(), swing_leverage=1.0, capital_usdc=None,
           fixed_position_usdc=None)


def _v1_fn(stop, a4, a1):
    def f(o):
        try:
            p, _ = risk.plan({"strategy": "OVERSOLD_BOUNCE", "entry": [o, o],
                              "stop": stop}, a4, a1, CFG)
        except (KeyError, TypeError, ValueError, ZeroDivisionError):
            return None
        if not p:
            return None
        return {"stop": p["stop"], "tp": list(p["tp"]),
                "partials": list(p["partials"]), "breakeven": True}
    return f


def variant_signals(c4, btc_up, X, V):
    """{t da abertura da entrada: sinal} com a saida V. Tudo o que o sinal
    usa vem de velas ate i (inclusive) e de dias ja fechados."""
    base = signals(c4, btc_up, X, False)
    if not base:
        return {}
    idx = {b["t"] + TF: i for i, b in enumerate(c4)}
    at = R.atr(c4) if V == "V2" else None
    out = {}
    for tc, s in base.items():
        i = idx[tc]
        gate = s["tp"][0]                         # media de 20 velas
        if V == "V3":
            out[tc] = {"stop": s["stop"], "tp_r": 2, "partials": [100],
                       "breakeven": False, "gate": gate, "rank": s["rank"]}
        elif V == "V2":
            st = c4[i]["c"] - 1.5 * at[i]
            if st <= 0:
                continue
            out[tc] = {"stop": st, "tp_r": 2, "partials": [100],
                       "breakeven": False, "gate": gate, "rank": s["rank"]}
        else:
            w4 = c4[max(0, i + 1 - B.WINDOW):i + 1]
            d1 = [x for x in B.daily(c4[max(0, i + 1 - 6 * B.WINDOW):i + 1])
                  if x["t"] + R.DAY <= tc]
            try:
                a4, a1 = B._tf(w4), B._tf(d1[-B.WINDOW:])
            except Exception:
                continue
            if not (a4.get("ok") and a1.get("ok")):
                continue
            out[tc] = {"plan_fn": _v1_fn(s["stop"], a4, a1), "gate": gate,
                       "stop": s["stop"], "rank": s["rank"]}
    return out


def main(folder, out="backtest/research_bounce_exits.json"):
    data, _ = B.load_all(folder)
    btc_up = btc_above_sma200(data["BTC"])
    bars, days = prepare(data)
    S = {"BTC": Series(bars["BTC"])}
    d0, ds, d1 = window(S["BTC"].days[-1])
    majors = [a for a in MAJORS21 if a in data]
    base = btc_sma200(S, days)
    cache = {}

    def runner(cfg, universe):
        k = (cfg["X"], cfg["V"])
        if k not in cache:
            cache[k] = {a: variant_signals(data[a], btc_up, *k) for a in data}
        return R.simulate(data, cache[k], TF, HOLD[cfg["V"]], universe)

    res = R.evaluate("OVERSOLD_BOUNCE_SAIDAS", GRID, runner, data, TF,
                     lambda cfg: HOLD[cfg["V"]], 90, majors, base, d0, ds,
                     d1, warm=days[0] + 210)
    with open(out, "w") as f:
        json.dump(res, f, indent=1)
    return res


if __name__ == "__main__":
    print(json.dumps(main(sys.argv[1]), indent=1))
