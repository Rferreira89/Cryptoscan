"""Teste contra entradas ao acaso (referencia obrigatoria).

Pergunta: as estrategias ao vivo escolhem entradas melhores do que o acaso?

Para cada operacao que o sistema fez no backtest (com as regras de carteira
do sistema ao vivo), cria uma operacao de CONTROLO: mesma moeda, mesmo lado,
entrada na abertura de uma vela de 4H escolhida ao acaso ate WINDOW_BARS
velas antes ou depois da entrada real, e a MESMA geometria do plano (stop e
objetivos a mesma distancia percentual da entrada, mesmas vendas parciais,
mesma regra de stop na entrada depois do 1.o objetivo, mesmos custos).
So muda o momento da entrada. Repete REPS vezes e compara o R medio da
estrategia com a distribuicao do R medio dos controlos.

Uma estrategia so tem vantagem nas entradas se ficar acima do percentil 95
dos controlos. Abaixo disso, o resultado e indistinguivel de entrar ao acaso.

Uso:
    python -m tools.random_baseline <pasta_historico> <pasta_cache> [reps]
(a cache e a mesma de tools/afinacao_lib.py; gera-a se faltar)
"""
import bisect
import json
import os
import random
import sys

from engine import backtest as B
from engine import short, trade

WINDOW_BARS = 90          # +-15 dias em velas de 4H: o mesmo contexto de mercado
REPS = 1000
MAX_BARS = 6 * 90         # tempo maximo de uma operacao de controlo (90 dias)
BORROW_DAILY_PCT = 0.05   # juros do short, como em tools/run_backtest_short.py


def geometry(plan, side):
    """Distancias relativas do plano a entrada de referencia (pior preco da
    zona): stop e objetivos em fracao do preco. Funciona nos dois lados."""
    ref = plan["entry_zone"][1] if side == "LONG" else plan["entry_zone"][0]
    return {"stop": plan["stop"] / ref - 1,
            "tp": [x / ref - 1 for x in plan["tp"]],
            "partials": list(plan["partials"])}


def control_trade(c4, j, geo, side, fee_pct, slip_pct=B.SLIP_PCT):
    """Abre na abertura da vela j com a geometria dada e segue ate fechar.
    So usa velas de j em diante (sem look-ahead). Devolve R ou None."""
    if j < 0 or j >= len(c4):
        return None
    b = c4[j]
    entry = b["o"]
    plan = {"stop": entry * (1 + geo["stop"]),
            "tp": [entry * (1 + x) for x in geo["tp"]],
            "partials": geo["partials"]}
    pos = trade.open_position(plan, entry, b["t"], fee_pct, slip_pct,
                              side=side)
    k = j
    trade.step(pos, b["o"], b["h"], b["l"], b["c"], b["t"] + B.H4)
    while not pos["closed"]:
        k += 1
        if k >= len(c4) or k - j > MAX_BARS:
            return None
        x = c4[k]
        trade.step(pos, x["o"], x["h"], x["l"], x["c"], x["t"] + B.H4)
    r = pos["r"]
    if side == "SHORT":
        days = (pos["closed_at"] - pos["opened_at"]) / 86400
        r -= BORROW_DAILY_PCT / 100 * days * pos["entry"] / pos["risk_unit"]
    return r


def prepare(trades, data, cfg):
    """Para cada operacao: (ativo, lado, indice da entrada real, geometria)."""
    out = []
    idx = {a: [b["t"] for b in cs] for a, cs in data.items()}
    for t in trades:
        side = "SHORT" if t.get("side") == "S" else "LONG"
        plan = t["plan"]
        if side == "SHORT":
            plan, _ = short.real_plan(plan, cfg)
            if plan is None:
                continue
        ts = idx.get(t["asset"])
        if not ts:
            continue
        i = bisect.bisect_left(ts, t.get("entry_t", t["t"]))
        out.append((t["asset"], side, i, geometry(plan, side), t["r"],
                    t["strategy"]))
    return out


def run(prepared, data, fee_pct, reps=REPS, seed=7, window=WINDOW_BARS):
    """Devolve, por estrategia e no total, o R medio real e a distribuicao
    do R medio dos controlos (lista com um valor por repeticao)."""
    rng = random.Random(seed)
    groups = {}
    for p in prepared:
        groups.setdefault(p[5], []).append(p)
    groups["TODAS"] = list(prepared)
    res = {}
    for name, ps in groups.items():
        real = sum(p[4] for p in ps) / len(ps)
        dist = []
        for _ in range(reps):
            rs = []
            for a, side, i, geo, _, _ in ps:
                c4 = data[a]
                lo, hi = max(0, i - window), min(len(c4) - 2, i + window)
                r = None
                for _try in range(5):          # vela sem fecho possivel: outra
                    r = control_trade(c4, rng.randint(lo, hi), geo, side,
                                      fee_pct)
                    if r is not None:
                        break
                if r is not None:
                    rs.append(r)
            if rs:
                dist.append(sum(rs) / len(rs))
        dist.sort()
        below = sum(1 for x in dist if x < real)
        res[name] = {"n": len(ps), "r_real": round(real, 3),
                     "r_acaso_mediana": round(dist[len(dist) // 2], 3),
                     "r_acaso_p95": round(dist[int(0.95 * (len(dist) - 1))], 3),
                     "percentil": round(100 * below / len(dist), 1),
                     "vantagem": real > dist[int(0.95 * (len(dist) - 1))]}
    return res


def main(folder, cache, reps=REPS):
    from tools import afinacao_lib as A
    data, _ = A.generate(folder, cache)
    cands, res = A.load_cache(cache)
    above = A.btc_above_sma200(data["BTC"])
    cands, res = A.live_filter(cands, res, above)
    off = set(A.CFG.get("disabled_strategies") or [])
    off |= {x + short.SUFFIX for x in off}
    trades = [t for t in A.trades(cands, res) if t["strategy"] not in off]
    prepared = prepare(trades, data, A.CFG)
    out = run(prepared, data, A.CFG["fee_pct"], reps)
    t0, _, t1 = A.window(data)
    out["_janela"] = [t0, t1]
    out["_reps"] = reps
    print(json.dumps(out, indent=1))
    os.makedirs("backtest", exist_ok=True)
    with open("backtest/random_baseline.json", "w") as f:
        json.dump(out, f, indent=1)
    return out


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else REPS)
