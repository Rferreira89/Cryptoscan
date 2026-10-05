"""Afinacao H1 (2026-10-05): o score preve o resultado?

Uso: python -m tools.afinacao_h01_score <pasta_historico> <pasta_cache> [--reserva] [--antigo]

Diagnostico no DESENHO (faixas de score, correlacao de Spearman, familias
do score) e teste da grelha de score minimo 65/70/75/80 com walk-forward.
A reserva so e avaliada com --reserva, para a configuracao escolhida no
desenho. Os candidatos vem do cache de tools.afinacao_lib.
"""
import json
import sys

from engine import backtest as B
from tools import afinacao_lib as A

GRID, BASE = (65, 70, 75, 80), 65
BANDS = ((65, 70), (70, 75), (75, 80), (80, 101))
FAMILIES = ("regime", "htf", "structure", "trigger", "flow", "liquidity",
            "derivatives", "rr")


def _rank(xs):
    order = sorted(range(len(xs)), key=lambda k: xs[k])
    rk, i = [0.0] * len(xs), 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        for k in range(i, j + 1):
            rk[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return rk


def spearman(xs, ys):
    """(rho, z aproximado). |z| < 2: indistinguivel de zero."""
    n = len(xs)
    if n < 10:
        return None, None
    a, b = _rank(xs), _rank(ys)
    ma, mb = sum(a) / n, sum(b) / n
    va = sum((x - ma) ** 2 for x in a)
    vb = sum((y - mb) ** 2 for y in b)
    if not va or not vb:
        return None, None
    rho = sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (va * vb) ** 0.5
    return round(rho, 3), round(rho * (n - 1) ** 0.5, 2)


def main(folder, cache, holdout=False, antigo=False):
    data, _ = B.load_all(folder)
    t0, split, t1 = A.window(data)
    above = A.btc_above_sma200(data["BTC"])
    cands, res = A.live_filter(*A.load_cache(cache, "janela"), above)
    run = lambda ms: A.trades(cands, res, ms)
    des = lambda tr: [t for t in tr if A.in_design(t, t0, split)]
    out = {"janela": {"desenho": [A.day(t0), A.day(split)],
                      "reserva": [A.day(split), A.day(t1)]},
           "ativos": len(data)}

    base = des(run(BASE))
    out["desenho_atual"] = A.summ(base)
    out["por_lado"] = {s: A.summ([t for t in base if t["side"] == s])
                       for s in ("L", "S")}
    out["por_estrategia"] = {}
    for t in base:
        out["por_estrategia"].setdefault(t["strategy"], []).append(t)
    out["por_estrategia"] = {k: A.summ(v)
                             for k, v in sorted(out["por_estrategia"].items())}
    out["faixas"] = {f"{lo}-{hi - 1}" if hi < 101 else f"{lo}+":
                     A.summ([t for t in base if lo <= t["score"] < hi])
                     for lo, hi in BANDS}
    out["spearman_score"] = spearman([t["score"] for t in base],
                                     [t["r"] for t in base])
    # todos os candidatos fechados do desenho com score >= 50, sem regras
    # de carteira: mais amostra para ver a relacao score/resultado
    wide = [dict(c, **r) for c, r in zip(cands, res)
            if r["status"] == "CLOSED" and c["score"] >= 50
            and A.in_design(dict(c, **r), t0, split)]
    out["candidatos_50+"] = A.summ(wide)
    out["spearman_score_50+"] = spearman([t["score"] for t in wide],
                                         [t["r"] for t in wide])
    out["faixas_50+"] = {f"{lo}-{hi - 1}": A.summ(
        [t for t in wide if lo <= t["score"] < hi])
        for lo, hi in ((50, 55), (55, 60), (60, 65), (65, 70), (70, 75),
                       (75, 80), (80, 101))}
    fam = {}
    for f in FAMILIES:
        row = {}
        for name, tr in (("operacoes_65+", base), ("candidatos_50+", wide)):
            xs = [t["families"].get(f, 0.5) for t in tr]
            rho, z = spearman(xs, [t["r"] for t in tr])
            med = sorted(xs)[len(xs) // 2] if xs else None
            hi = [t for t in tr if t["families"].get(f, 0.5) > med]
            lo = [t for t in tr if t["families"].get(f, 0.5) <= med]
            row[name] = {"rho": rho, "z": z, "valores": len(set(xs)),
                         "acima_mediana": A.summ(hi), "resto": A.summ(lo)}
        fam[f] = row
    out["familias"] = fam

    out["grelha_desenho"] = {ms: A.summ(des(run(ms))) for ms in GRID}
    folds, oos, oos_base = A.walk_forward(run, GRID, BASE, t0, split)
    out["walk_forward"] = {
        "dobras": folds, "fora_da_amostra": A.summ(oos),
        "atual_fora_da_amostra": A.summ(oos_base),
        "janelas_melhores": sum(f["melhora"] for f in folds),
        "janelas": len(folds)}
    ok = [ms for ms in GRID if out["grelha_desenho"][ms]["n"] >= 30]
    chosen = max(ok, key=lambda ms: out["grelha_desenho"][ms]["r"]) if ok else BASE
    out["escolhida"] = chosen
    out["sem_melhor_moeda_desenho"] = A.without_best_asset(des(run(chosen)))

    if holdout:
        h = lambda ms: [t for t in run(ms) if t["t"] >= split]
        out["reserva"] = {"escolhida": A.summ(h(chosen)),
                          "atual": A.summ(h(BASE)),
                          "sem_melhor_moeda": A.without_best_asset(h(chosen))}
    if antigo:      # linha informativa: nao conta para aprovar nem rejeitar
        oc, orr = A.live_filter(*A.load_cache(cache, "antigo"), above)
        out["periodo_antigo"] = {ms: A.summ(
            [t for t in A.trades(oc, orr, ms) if t["exit_t"] < t0])
            for ms in GRID}
    print(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], "--reserva" in sys.argv,
         "--antigo" in sys.argv)
