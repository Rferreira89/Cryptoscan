"""Liga de estrategias ao vivo contra o acaso.

Cada sinal que o sistema emitiu ao vivo (modo real ou papel, executado pelo
Rui ou nao) e comparado com entradas ao acaso na MESMA moeda, ate 15 dias
antes ou depois da entrada real, com a MESMA geometria (stop e objetivos a
mesma distancia percentual, mesmas vendas parciais, mesmos custos). E o
mesmo metodo de tools/random_baseline.py, mas sobre os sinais reais, ou
seja, com dados que nao existiam quando as estrategias foram desenhadas.

So conta o sinal, nao a execucao do Rui: mede se a estrategia escolhe bons
momentos de entrada. Com menos de 30 operacoes fechadas o veredicto e
"amostra insuficiente".

Uso:
    python -m tools.liga <pasta_historico> <state.json> <audit.jsonl> [reps]
Escreve backtest/liga.json (lido pela pagina).
"""
import bisect
import json
import sys
import time

from engine import backtest as B
from engine import config
from tools import random_baseline as RB

MIN_N = 30
DEFAULT_PARTIALS = [50, 30, 20]


def partials_from_audit(path):
    out = {}
    try:
        with open(path) as f:
            for line in f:
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                if e.get("event") == "ISSUED" and e.get("signal"):
                    pt = (e["signal"].get("plan") or {}).get("partials")
                    if pt:
                        out[e["id"]] = pt
    except OSError:
        pass
    return out


def prepare(ledger, data, partials):
    """(ativo, lado, indice da entrada, geometria, R real, estrategia)."""
    idx = {a: [b["t"] for b in cs] for a, cs in data.items()}
    out, skipped = [], []
    for r in ledger:
        if r.get("kind") != "4H" or r.get("status") != "CLOSED":
            continue
        if r.get("result_r") is None or not r.get("entry") \
                or not r.get("opened_at"):
            continue
        ts = idx.get(r["asset"])
        if not ts or ts[-1] < r["opened_at"]:
            skipped.append(r["id"])           # historico ainda nao chega la
            continue
        side = "SHORT" if r.get("side") == "SHORT" else "LONG"
        e = r["entry"]
        geo = {"stop": r["stop"] / e - 1, "tp": [x / e - 1 for x in r["tp"]],
               "partials": r.get("partials") or partials.get(r["id"])
               or DEFAULT_PARTIALS}
        i = bisect.bisect_right(ts, r["opened_at"]) - 1  # vela da entrada
        name = r["strategy"] + (" (papel)" if r.get("mode") == "PAPER" else "")
        out.append((r["asset"], side, max(i, 0), geo, r["result_r"], name))
    return out, skipped


def verdict(row):
    if row["n"] < MIN_N:
        return "amostra insuficiente"
    return "bate o acaso" if row["vantagem"] else "não bate o acaso"


def main(folder, state_path, audit_path, reps=RB.REPS):
    data, _ = B.load_all(folder, min_bars=500)
    state = json.load(open(state_path))
    prepared, skipped = prepare(state.get("ledger", []), data,
                                partials_from_audit(audit_path))
    res = RB.run(prepared, data, config.load()["fee_pct"], reps) \
        if prepared else {}
    for k, v in res.items():
        v["veredicto"] = verdict(v)
    out = {"atualizado": int(time.time()), "reps": reps, "min_n": MIN_N,
           "sem_historico": len(skipped), "estrategias": res}
    with open("backtest/liga.json", "w") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
    print(json.dumps(out, indent=1, ensure_ascii=False))
    return out


if __name__ == "__main__":
    main(*sys.argv[1:4], *(int(x) for x in sys.argv[4:5]))
