"""Afinacao H4 (2026-10-14): tempo maximo mais curto no Bounce RSI 30 (Xavier).

Hipotese, grelha e criterios escritos ANTES dos testes em
backtest/afinacao.md (commit 776a4b7).

Gatilho e saida: exatamente tools/arena_ringue.sig_x30 (o que o ringue e o
papel usam), chamado vela a vela so com as velas ja fechadas. So muda o
tempo maximo (hold). Simulacao de carteira: tools/research_rlib.simulate
(4 x 25%, uma por moeda, primeiro o RSI mais baixo), 0,25% + 0,1% por lado.

Janela: 18 meses ate ao ultimo dia completo; 12 de desenho, 6 de reserva.
Walk-forward ancorado no desenho: treino inicial de 121 dias, 4 testes de
61 dias. Reserva avaliada uma vez so para a configuracao escolhida.

Uso: python -m tools.afinacao_h04_tempo <pasta_historico> [saida.json]
"""
import datetime as dt
import json
import random
import sys

from engine import backtest as B
from tools import arena_ringue as AR
from tools import research_rlib as R
from tools.afinacao_lib import btc_above_sma200

TF = B.H4
DAY = R.DAY
GRID = [0.5, 1, 1.5, 2, 3, 5]          # dias
CURRENT = 3
TRAIN0, TEST, NFOLDS = 121, 61, 4
WINDOW_BARS = 90


def months_back(last_day, m):
    e = dt.date(1970, 1, 1) + dt.timedelta(days=last_day + 1)
    y, mo = divmod(e.year * 12 + e.month - 1 - m, 12)
    return (dt.date(y, mo + 1, min(e.day, 28)) - dt.date(1970, 1, 1)).days


def window(last_day):
    """(inicio, corte, fim exclusivo) em dias: 18 meses, os ultimos 6 de reserva."""
    return months_back(last_day, 18), months_back(last_day, 6), last_day + 1


def x30_signals(c4, btc_up, t_from=0):
    """{t da abertura da entrada: sinal} com o gatilho do ringue. O sinal da
    vela i so ve c4[:i+1] e o filtro do BTC do ultimo dia completo."""
    rs = R.rsi([x["c"] for x in c4])
    out = {}
    for i in range(250, len(c4) - 1):
        tc = c4[i]["t"] + TF
        if tc < t_from or not btc_up.get(tc // DAY - 1):
            continue
        s = AR.sig_x30(c4[max(0, i - 299):i + 1])   # a funcao so le as ultimas 300
        if not s:
            continue
        out[tc] = {"stop": s["stop"], "tp": list(s["tp"]),
                   "partials": list(s["partials"]), "breakeven": True,
                   "gate": s["tp"][0], "rank": min(rs[i - 2:i + 1])}
    return out


def mean(xs):
    return sum(xs) / len(xs) if xs else None


def stats(tr):
    if not tr:
        return {"n": 0}
    r = [t["r"] for t in tr]
    ex = {}
    for t in tr:
        ex[t["exit"]] = ex.get(t["exit"], 0) + 1
    by = {}
    for t in tr:
        by.setdefault(t["asset"], []).append(t["r"])
    best = max(by, key=lambda a: sum(by[a]))
    rest = [t["r"] for t in tr if t["asset"] != best]
    return {"n": len(r), "acerto_pct": round(100 * sum(x > 0 for x in r) / len(r), 1),
            "r_medio": round(mean(r), 3), "r_total": round(sum(r), 2),
            "saidas": ex, "melhor_moeda": best,
            "sem_melhor_moeda": {"n": len(rest),
                                 "r_medio": round(mean(rest), 3) if rest else None},
            "moedas": len(by)}


def in_days(tr, a, b):
    return [t for t in tr if a <= t["entry_d"] < b]


def vs_random(groups, data, reps=1000, seed=11):
    """groups: [(hold_s, operacoes)]. Uma entrada de controlo por operacao."""
    pools, real = [], []
    for h, trs in groups:
        for t in trs:
            p = R.control_rs(data[t["asset"]], t["i"], t["geo"], TF, h, WINDOW_BARS)
            if p:
                pools.append(p)
                real.append(t["r"])
    if not real:
        return {"n": 0, "vantagem": False}
    rng = random.Random(seed)
    m = mean(real)
    dist = sorted(sum(rng.choice(p) for p in pools) / len(pools) for _ in range(reps))
    p95 = dist[int(0.95 * (len(dist) - 1))]
    return {"n": len(real), "r_real": round(m, 3),
            "r_acaso_mediana": round(dist[len(dist) // 2], 3),
            "r_acaso_p95": round(p95, 3),
            "percentil": round(100 * sum(1 for x in dist if x < m) / len(dist), 1),
            "vantagem": m > p95}


def main(folder, out="backtest/afinacao_h04_tempo.json"):
    data, skipped = B.load_all(folder, min_bars=300)
    btc_up = btc_above_sma200(data["BTC"])
    last_day = (data["BTC"][-1]["t"] + TF) // DAY - 1
    d0, ds, d1 = window(last_day)
    warm = months_back(last_day, 18 + 24)          # linha informativa
    sigs = {a: x30_signals(c, btc_up, warm * DAY) for a, c in data.items()}
    trades = {}
    for h in GRID:
        _, tr = R.simulate(data, sigs, TF, int(h * DAY))
        trades[h] = [t for t in tr if t["entry_d"] < d1]
    iso = lambda d: str(dt.date(1970, 1, 1) + dt.timedelta(days=d))
    grid = {str(h): stats(in_days(trades[h], d0, ds)) for h in GRID}
    # walk-forward ancorado no desenho
    folds, oos, cur_oos = [], [], []
    for f in range(NFOLDS):
        a = d0 + TRAIN0 + f * TEST
        b = min(a + TEST, ds)
        best, best_r = CURRENT, None
        for h in GRID:
            tr = in_days(trades[h], d0, a)
            if len(tr) >= 20 and (best_r is None or mean([t["r"] for t in tr]) > best_r):
                best, best_r = h, mean([t["r"] for t in tr])
        te = in_days(trades[best], a, b)
        cu = in_days(trades[CURRENT], a, b)
        oos.append((best, te))
        cur_oos += cu
        rt, rc = mean([t["r"] for t in te]), mean([t["r"] for t in cu])
        folds.append({"teste": [iso(a), iso(b - 1)], "escolha_dias": best,
                      "n": len(te), "r_medio": None if rt is None else round(rt, 3),
                      "atual_n": len(cu), "atual_r": None if rc is None else round(rc, 3),
                      "melhor": (rt if rt is not None else 0) > (rc if rc is not None else 0)})
    oos_tr = [t for _, te in oos for t in te]
    cands = [h for h in GRID if grid[str(h)]["n"] >= 30]
    chosen = max(cands, key=lambda h: grid[str(h)]["r_medio"])
    res = {"hipotese": "H4 tempo maximo do BOUNCE_X30", "moedas": len(data),
           "fora": skipped, "janela": {"desenho": [iso(d0), iso(ds - 1)],
                                       "reserva": [iso(ds), iso(d1 - 1)],
                                       "ultima_vela": data["BTC"][-1]["t"]},
           "grelha_desenho": grid, "walk_forward": {
               "janelas": folds, "fora_da_amostra": stats(oos_tr),
               "atual_mesmas_janelas": stats(cur_oos),
               "janelas_melhor": sum(f["melhor"] for f in folds)},
           "escolhida_dias": chosen}
    # informativo: periodo antigo (nao conta)
    res["periodo_antigo"] = {"dias": [iso(warm), iso(d0 - 1)],
                             **{str(h): stats(in_days(trades[h], warm, d0))
                                for h in (chosen, CURRENT)}}
    if chosen != CURRENT:
        hold = in_days(trades[chosen], ds, d1)          # RESERVA: uma vez
        res["reserva"] = stats(hold)
        res["reserva_atual_referencia"] = stats(in_days(trades[CURRENT], ds, d1))
        res["acaso"] = {
            "walk_forward": vs_random([(int(h * DAY), te) for h, te in oos], data),
            "reserva": vs_random([(int(chosen * DAY), hold)], data),
            "fora_da_amostra": vs_random([(int(h * DAY), te) for h, te in oos]
                                         + [(int(chosen * DAY), hold)], data)}
    else:   # rejeitada: so a versao atual na reserva, como referencia (nada e escolhido)
        hold = in_days(trades[CURRENT], ds, d1)
        res["reserva_atual_referencia"] = stats(hold)
        res["acaso_atual_reserva"] = vs_random([(int(CURRENT * DAY), hold)], data)
    res["acaso_atual_walk_forward"] = vs_random([(int(CURRENT * DAY), cur_oos)], data)
    with open(out, "w") as f:
        json.dump(res, f, indent=1, ensure_ascii=False)
    return res


if __name__ == "__main__":
    print(json.dumps(main(sys.argv[1], *sys.argv[2:]), indent=1, ensure_ascii=False))
