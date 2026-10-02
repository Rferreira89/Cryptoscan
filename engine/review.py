"""Revisao automatica das estrategias com base no registo AO VIVO.

Uma estrategia com 30 ou mais operacoes reais fechadas e resultado
acumulado negativo e desligada (STRATEGY RETIRED) e deixa de gerar
sinais. Para a voltar a ligar e preciso apaga-la de state["disabled"].
"""
from . import ledger

MIN_TRADES = 30


def update(state, now):
    dis = state.setdefault("disabled", {})
    events = []
    by = ledger.summary(state.get("ledger", []))["by_strategy"]
    for strat, v in by.items():
        if strat not in dis and v["n"] >= MIN_TRADES and v["sum_r"] < 0:
            dis[strat] = {"since": now, "n": v["n"], "sum_r": v["sum_r"]}
            events.append({"t": now, "event": "STRATEGY_DISABLED",
                           "id": f"review-{strat}", "strategy": strat,
                           "n": v["n"], "sum_r": v["sum_r"]})
    return dis, events
