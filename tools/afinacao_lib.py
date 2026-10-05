"""Base comum das afinacoes (agente de afinacao dos sinais).

Janela de dados (decisao do Rui, 2026-10-03): ultimos 18 meses de velas.
Os primeiros 12 meses sao o DESENHO, os ultimos 6 a RESERVA. O que vem
antes so aquece indicadores e da uma linha informativa ("periodo antigo").

Reproduz o sistema ao vivo: compras so com o BTC acima da media de 200
dias, shorts (espelho) so com o BTC abaixo, no maximo
cfg["max_open_positions"] operacoes em simultaneo, custos do backtest
(comissao de config.json, slippage de engine/backtest.py, juros do short).

Gerar os candidatos (demorado, guarda cache por ativo):
    python -m tools.afinacao_lib <pasta_historico> <pasta_cache>
"""
import os
import pickle
import sys
import time

from engine import backtest as B
from engine import config, short, stats

DAY = 86400
WINDOW_D, HOLD_D = 548, 183            # 18 meses e 6 meses
DESIGN_D = WINDOW_D - HOLD_D           # 365 dias
WF_TRAIN0_D, WF_TEST_D = 121, 61       # treino inicial 4 meses, teste 2 meses
CFG = dict(config.load(), swing_leverage=1.0, capital_usdc=None,
           fixed_position_usdc=None)


def window(data):
    """(t0, split, t1): inicio do desenho, inicio da reserva, fim."""
    t1 = data["BTC"][-1]["t"] + B.H4
    return t1 - WINDOW_D * DAY, t1 - HOLD_D * DAY, t1


def btc_above_sma200(c4_btc):
    """{dia: True/False} conhecido no fecho desse dia."""
    d1 = B.daily(c4_btc)
    out = {}
    for k in range(200, len(d1) + 1):
        sma = sum(x["c"] for x in d1[k - 200:k]) / 200
        out[d1[k - 1]["t"] // DAY] = d1[k - 1]["c"] > sma
    return out


def generate(folder, cache_dir, period="janela"):
    """Candidatos e simulacoes por ativo e lado, com cache em disco.
    period: "janela" (ultimos 18 meses) ou "antigo" (antes disso)."""
    from tools.run_backtest_short import simulate as sim_short
    data, skipped = B.load_all(folder)
    t0, _, _ = window(data)
    rng = dict(start_t=t0) if period == "janela" else dict(end_t=t0)
    os.makedirs(cache_dir, exist_ok=True)
    reg = {"L": B.regimes(data["BTC"]),
           "S": B.regimes(short.mirror(data["BTC"]))}
    t = time.time()
    for a in sorted(data):
        for side in ("L", "S"):
            fn = os.path.join(cache_dir, f"{period}_{a}_{side}.pkl")
            if os.path.exists(fn):
                continue
            if side == "L":
                cs = B.candidates(a, data[a], reg["L"], CFG, **rng)
                rs = [B.simulate(c, data[a], CFG) for c in cs]
                nb = [B.simulate(c, data[a], CFG, breakeven=False) for c in cs]
            else:
                cs = B.candidates(a, short.mirror(data[a]), reg["S"], CFG, **rng)
                for c in cs:
                    c["strategy"] += short.SUFFIX
                rs = [sim_short(c, data[a]) for c in cs]
                nb = None
            for c in cs:
                c["side"] = side
            pickle.dump((cs, rs, nb), open(fn + ".tmp", "wb"))
            os.replace(fn + ".tmp", fn)
            print(f"{period} {a} {side}: {len(cs)} ({time.time() - t:.0f}s)",
                  flush=True)
    return data, skipped


def load_cache(cache_dir, period="janela"):
    cands, res = [], []
    for fn in sorted(os.listdir(cache_dir)):
        if fn.startswith(period + "_") and fn.endswith(".pkl"):
            cs, rs, _ = pickle.load(open(os.path.join(cache_dir, fn), "rb"))
            cands += cs
            res += rs
    return cands, res


def live_filter(cands, res, above):
    """Filtro de mercado do sistema ao vivo: compras com o BTC acima da
    media de 200 dias, shorts com o BTC abaixo (dia fechado anterior)."""
    kc, kr = [], []
    for c, r in zip(cands, res):
        up = above.get((c["t"] - DAY) // DAY)
        if up is None or (c["side"] == "L") != up:
            continue
        kc.append(c)
        kr.append(r)
    return kc, kr


def trades(cands, res, min_score=None, keep=None, cfg=CFG):
    """Operacoes fechadas com as regras de carteira do sistema ao vivo.
    keep(c): filtro adicional sobre o candidato (a hipotese em teste)."""
    if keep is not None:
        idx = [k for k, c in enumerate(cands) if keep(c)]
        cands, res = [cands[k] for k in idx], [res[k] for k in idx]
    return stats.select(cands, res, cfg, min_score)


def mean_r(tr):
    return sum(t["r"] for t in tr) / len(tr) if tr else None


def summ(tr):
    if not tr:
        return {"n": 0, "win": None, "r": None}
    return {"n": len(tr),
            "win": round(100 * sum(t["r"] > 0 for t in tr) / len(tr), 1),
            "r": round(mean_r(tr), 3)}


def in_design(t, t0, split):
    return t0 <= t["t"] < split and t["exit_t"] < split


def walk_forward(run, grid, base, t0, split, min_train_n=20):
    """Walk-forward ancorado dentro do desenho. run(g) -> operacoes da
    configuracao g em toda a janela. Em cada dobra escolhe-se no treino
    (do inicio do desenho ate ao inicio do teste) a configuracao com
    melhor R medio e aplica-se ao teste de 2 meses seguinte. Compara com
    a configuracao atual (base) na mesma janela de teste."""
    allt = {g: run(g) for g in grid}
    if base not in allt:
        allt[base] = run(base)
    folds, oos, oos_base = [], [], []
    te0 = t0 + WF_TRAIN0_D * DAY
    while te0 + WF_TEST_D * DAY <= split + DAY:
        te1 = min(te0 + WF_TEST_D * DAY, split)
        best = None
        for g in grid:
            tr = [t for t in allt[g] if t0 <= t["t"] < te0 and t["exit_t"] < te0]
            if len(tr) >= min_train_n:
                e = mean_r(tr)
                if best is None or e > best[0]:
                    best = (e, g, len(tr))
        g = best[1] if best else base
        te = [t for t in allt[g] if te0 <= t["t"] < te1 and t["exit_t"] < split]
        tb = [t for t in allt[base] if te0 <= t["t"] < te1 and t["exit_t"] < split]
        oos += te
        oos_base += tb
        folds.append({"datas": [day(te0), day(te1)], "escolhida": g,
                      "treino_r": round(best[0], 3) if best else None,
                      "treino_n": best[2] if best else 0,
                      "teste": summ(te), "atual": summ(tb),
                      "melhora": bool(te and tb and mean_r(te) > mean_r(tb))})
        te0 = te1
    return folds, oos, oos_base


def without_best_asset(tr):
    """R medio sem a moeda que mais contribuiu."""
    by = {}
    for t in tr:
        by[t["asset"]] = by.get(t["asset"], 0) + t["r"]
    if not by:
        return None, None
    a = max(by, key=by.get)
    return a, summ([t for t in tr if t["asset"] != a])


def day(t):
    return time.strftime("%Y-%m-%d", time.gmtime(t))


if __name__ == "__main__":
    for p in sys.argv[3:] or ["janela"]:
        generate(sys.argv[1], sys.argv[2], p)
