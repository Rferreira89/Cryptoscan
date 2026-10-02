import json
import os
import sys

from . import alerts, scanner

OUT = sys.argv[1] if len(sys.argv) > 1 else "out"


def _load(name, default):
    p = os.path.join(OUT, name)
    if os.path.exists(p):
        try:
            with open(p) as f:
                return json.load(f)
        except ValueError:
            print(f"AVISO: {name} corrompido, a recomecar")
    return default


def summary(res):
    L = [f"STATUS {res['status_global']}"]
    for name, s in res["sources"].items():
        L.append(f"  {name:8s} " + (f"OK {s['pairs']} pares" if s["ok"]
                                    else "ERRO " + s["error"]))
    L.append(f"  bybit-eu {res.get('venue_source')}")
    if not res["universe"]:
        return L
    L.append(f"COUNTS {res['counts']}")
    L.append(f"DERIVADOS {res.get('derivatives_source')}")
    L.append(f"REGIME BTC {res['market_regime']['btc']}")
    for r in res["universe"]:
        d = r["decision"]
        L.append(f"  {r['asset']:8s} {d['decision']:9s} "
                 f"{d.get('regime', '-'):11s} {d.get('strategy', '-'):16s} "
                 f"{d.get('state', '-'):8s} score {d.get('score', '-')} | "
                 f"{d.get('reason', '')}")
        p = d.get("plan")
        if p:
            L.append(f"      entrada {p['entry_zone']} stop {p['stop']} "
                     f"tp {p['tp']} proj {p['tp_projected']} rr {p['rr']} "
                     f"stop {p['stop_pct']}% ({p['stop_atr']} ATR) "
                     f"pos {p['position_pct']}% risco {p['risk_pct']}%")
            L.append(f"      familias {d['families']} conflitos {d['conflicts']}")
        for x in d.get("rejected", []):
            L.append(f"      rejeitado {x}")
    L.append(f"SINAIS ATIVOS {len(res['active_signals'])}")
    for s in res["active_signals"]:
        L.append(f"  {s['id']} {s['status']} {s['plan']}")
    return L


def alert_text(s):
    p = s["plan"]
    return (f"SETUP {s['asset']} ({s['pair']}, {s['venue']})\n"
            f"{s['strategy']} · {s['timeframe']} · score {s['score']}/100\n"
            f"Entrada (limite): {p['entry_zone'][0]} - {p['entry_zone'][1]}\n"
            f"Stop: {p['stop']} (-{p['stop_pct']}%)\n"
            f"TP1 {p['tp'][0]} · TP2 {p['tp'][1]} · TP3 {p['tp'][2]}\n"
            f"R:R 1:{p['rr']} · posicao {p['position_pct']}% do capital\n"
            "NAO VALIDADO por backtest - apenas paper trading.")


def main():
    os.makedirs(OUT, exist_ok=True)
    state = _load("state.json", {})
    res, state, events = scanner.run(state=state)
    with open(os.path.join(OUT, "scan.json"), "w") as f:
        json.dump(res, f, separators=(",", ":"))
    with open(os.path.join(OUT, "state.json"), "w") as f:
        json.dump(state, f, separators=(",", ":"))
    if events:                      # audit log: so acrescenta, nunca reescreve
        with open(os.path.join(OUT, "audit.jsonl"), "a") as f:
            for e in events:
                f.write(json.dumps(e, separators=(",", ":")) + "\n")
    text = "\n".join(summary(res))
    with open(os.path.join(OUT, "resumo.txt"), "w") as f:
        f.write(text + "\n")
    print(text)
    if res.get("config", {}).get("alerts_unvalidated") and alerts.configured():
        for e in events:
            if e["event"] == "ISSUED":
                try:
                    alerts.send(alert_text(e["signal"]))
                except alerts.AlertError as err:
                    print("ALERTA FALHOU", err)
    # falha o job se nenhuma fonte respondeu: nunca publicar dados vazios
    sys.exit(0 if res["universe"] else 1)


if __name__ == "__main__":
    main()
