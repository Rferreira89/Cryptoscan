"""Afinacao H2 (2026-10-07): exigir vela de gatilho forte.

Uso: python -m tools.afinacao_h02_gatilho <pasta_historico> <pasta_cache> [--reserva] [--antigo]

Vela de gatilho forte = engolfo ou pin bar na vela de 4H do sinal (familia
"trigger" do score igual a 1.0; nos shorts e o padrao espelhado). Grelha:
atual (sem filtro), exigir em todas as estrategias, so nas compras, so nos
shorts. Walk-forward no DESENHO; a reserva so e avaliada com --reserva e
so para a configuracao escolhida no desenho. Os candidatos vem do cache de
tools.afinacao_lib.
"""
import json
import sys

from engine import backtest as B
from tools import afinacao_lib as A

BASE = "atual"
GRID = ("atual", "todas", "compras", "shorts")


def strong(c):
    return c["families"].get("trigger", 0) >= 0.999


KEEP = {"atual": None,
        "todas": strong,
        "compras": lambda c: c["side"] == "S" or strong(c),
        "shorts": lambda c: c["side"] == "L" or strong(c)}


def by(tr, key):
    out = {}
    for t in tr:
        out.setdefault(key(t), []).append(t)
    return {k: A.summ(v) for k, v in sorted(out.items())}


def main(folder, cache, holdout=False, antigo=False):
    data, _ = B.load_all(folder)
    t0, split, t1 = A.window(data)
    above = A.btc_above_sma200(data["BTC"])
    cands, res = A.live_filter(*A.load_cache(cache, "janela"), above)
    memo = {}

    def run(g):
        if g not in memo:
            memo[g] = A.trades(cands, res, keep=KEEP[g])
        return memo[g]
    des = lambda tr: [t for t in tr if A.in_design(t, t0, split)]
    out = {"janela": {"desenho": [A.day(t0), A.day(split)],
                      "reserva": [A.day(split), A.day(t1)]},
           "ativos": len(data)}
    base = des(run(BASE))
    out["desenho_atual"] = A.summ(base)
    out["atual_por_lado"] = by(base, lambda t: t["side"])
    out["atual_por_estrategia"] = by(base, lambda t: t["strategy"])
    out["atual_por_gatilho"] = by(base, lambda t: "forte" if strong(t) else "normal")
    out["grelha_desenho"] = {g: A.summ(des(run(g))) for g in GRID}
    folds, oos, oos_base = A.walk_forward(run, GRID, BASE, t0, split)
    out["walk_forward"] = {
        "dobras": folds, "fora_da_amostra": A.summ(oos),
        "atual_fora_da_amostra": A.summ(oos_base),
        "janelas_melhores": sum(f["melhora"] for f in folds),
        "janelas": len(folds)}
    # cada configuracao fixa nas mesmas janelas de teste (sem escolha)
    te0 = t0 + A.WF_TRAIN0_D * A.DAY
    out["fixas_nas_janelas_de_teste"] = {g: A.summ(
        [t for t in run(g) if te0 <= t["t"] < split and t["exit_t"] < split])
        for g in GRID}
    ok = [g for g in GRID if out["grelha_desenho"][g]["n"] >= 30]
    chosen = max(ok, key=lambda g: out["grelha_desenho"][g]["r"]) if ok else BASE
    out["escolhida"] = chosen
    out["escolhida_por_estrategia"] = by(des(run(chosen)), lambda t: t["strategy"])
    out["sem_melhor_moeda_desenho"] = A.without_best_asset(des(run(chosen)))

    if holdout:
        h = lambda g: [t for t in run(g) if t["t"] >= split]
        out["reserva"] = {"escolhida": A.summ(h(chosen)),
                          "atual": A.summ(h(BASE)),
                          "sem_melhor_moeda": A.without_best_asset(h(chosen))}
    if antigo:      # linha informativa: nao conta para aprovar nem rejeitar
        oc, orr = A.live_filter(*A.load_cache(cache, "antigo"), above)
        out["periodo_antigo"] = {g: A.summ(
            [t for t in A.trades(oc, orr, keep=KEEP[g]) if t["exit_t"] < t0])
            for g in GRID}
    print(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], "--reserva" in sys.argv,
         "--antigo" in sys.argv)
