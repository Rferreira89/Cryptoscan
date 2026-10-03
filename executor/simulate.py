"""Executor em SIMULACAO: le state.json e escreve as ordens que colocaria.
Nao liga a nenhuma corretora.

    python -m executor.simulate <state.json> <pasta_de_saida>
"""
import json
import os
import sys
import time

from . import plan

LIVE = ("ACTIVE", "TRIGGERED")


def step(state, book, now, limits=plan.LIMITS):
    """Compara os sinais com o que ja foi feito (book) e devolve as acoes
    novas. book: {id: {"stage": ..., ...}} e alterado no sitio."""
    sigs = state.get("signals", {})
    times = state.get("scan_times") or []
    age = now - times[-1] if times else None
    stale = age is None or age > limits["max_state_age_s"]
    out = []

    def emit(o):
        out.append(dict(o, t=now, simulated=True))

    for key, s in sorted(sigs.items(), key=lambda kv: kv[1]["issued_at"]):
        b = book.get(key)
        st = s["status"]
        if b is None:
            if st not in LIVE:
                continue                     # ja terminou antes de o vermos
            if st == "TRIGGERED":
                book[key] = {"stage": "SKIPPED"}
                emit({"action": "SKIP", "id": key,
                      "reason": "já em curso quando o executor arrancou"})
                continue
            if stale:
                emit({"action": "WAIT", "id": key,
                      "reason": "estado desatualizado: sem ordens novas"})
                continue                     # volta a tentar no proximo passo
            n_open = sum(1 for x in book.values()
                         if x["stage"] in ("ENTRY", "OPEN", "BREAKEVEN"))
            why = plan.refuse(s, n_open, limits)
            if why:
                book[key] = {"stage": "SKIPPED"}
                emit({"action": "SKIP", "id": key, "reason": why})
                continue
            book[key] = {"stage": "ENTRY"}
            emit(plan.entry_order(s))
            continue
        if b["stage"] == "ENTRY":
            if st == "TRIGGERED":
                b["stage"] = "OPEN"
                for o in plan.protection_orders(s, limits):
                    emit(o)
            elif st not in LIVE:
                b["stage"] = "DONE"
                emit({"action": "CANCEL_ENTRY", "id": key,
                      "reason": s.get("close_reason", st)})
        if b["stage"] == "OPEN" and st == "TRIGGERED" \
                and s["position"]["tp_hit"] >= 1 \
                and s["position"].get("breakeven", True):
            b["stage"] = "BREAKEVEN"
            emit(plan.breakeven_order(s))
        if b["stage"] in ("OPEN", "BREAKEVEN") and st not in LIVE:
            b["stage"] = "DONE"
            emit({"action": "CANCEL_REST", "id": key,
                  "reason": s.get("close_reason", st),
                  "result_r": s.get("result_r")})
    return out


def main(state_path, out_dir, now=None):
    now = int(time.time()) if now is None else now
    os.makedirs(out_dir, exist_ok=True)
    bp = os.path.join(out_dir, "book.json")
    book = json.load(open(bp)) if os.path.exists(bp) else {}
    with open(state_path) as f:
        state = json.load(f)
    actions = step(state, book, now)
    with open(os.path.join(out_dir, "orders.jsonl"), "a") as f:
        for a in actions:
            f.write(json.dumps(a, ensure_ascii=False) + "\n")
    with open(bp, "w") as f:
        json.dump(book, f)
    print(f"simulação: {len(actions)} ações, {len(book)} sinais seguidos")
    for a in actions:
        print(" ", json.dumps(a, ensure_ascii=False))
    return actions


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "executor_out")
