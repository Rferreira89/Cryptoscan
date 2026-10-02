"""Passagem leve de 1 minuto: so acompanha o que esta aberto.

Nao analisa nem emite sinais novos (isso e o scan de 15 minutos). Le os
precos, verifica stops e objetivos, le as respostas do Telegram, atualiza
o registo e envia os alertas de venda.
"""
import json
import os
import statistics
import sys
import time

from . import config, ledger, paper_trend, run, scanner, signals

OUT = sys.argv[1] if len(sys.argv) > 1 else "out"


def needed_assets(state):
    a = {s["asset"] for s in state.get("signals", {}).values()
         if s["status"] in ("ACTIVE", "TRIGGERED")}
    return a | set(state.get("paper_trend", {}).get("positions", {}))


def prices_for(assets, data):
    out = {}
    for a in assets:
        px = [d[a]["last"] for d in data.values() if a in d and d[a]["last"]]
        if px:
            out[a] = statistics.median(px)
    return out


def tick(state, prices, cfg, now):
    events = signals.track(state, prices, cfg, now)
    events += paper_trend.check_stops(state, prices, cfg, now)
    ledger.apply(state, events)
    return events


def main():
    run.OUT = OUT
    state = run._load("state.json", None)
    res = run._load("scan.json", None)
    if state is None or res is None:
        print("sem estado anterior: nada a acompanhar")
        return
    cfg = config.load()
    now = int(time.time())
    replied = run.process_inbox(state)
    events, assets = [], needed_assets(state)
    if assets:
        _, data = scanner.collect_tickers()
        events = tick(state, prices_for(assets, data), cfg, now)
    res["monitored_at"] = now
    res["journal"] = ledger.view(state.get("ledger", []))
    res["active_signals"] = [s for s in state.get("signals", {}).values()
                             if s["status"] in ("ACTIVE", "TRIGGERED")]
    pt = state.get("paper_trend")
    if pt and res.get("paper_trend"):
        res["paper_trend"]["positions"] = pt["positions"]
        res["paper_trend"]["closed"] = pt["closed"][-15:]
    run.save(state, res, events)
    # so publica quando ha algo novo, ou de 5 em 5 minutos como sinal de vida
    if events or replied or now % 300 < 60:
        open(os.path.join(OUT, ".publish"), "w").close()
    print(f"monitor: {len(assets)} ativos, {len(events)} eventos")
    run.deliver(cfg, state, events)


if __name__ == "__main__":
    main()
