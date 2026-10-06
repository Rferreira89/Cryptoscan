"""Passagem leve de 1 minuto: so acompanha o que esta aberto.

Nao analisa nem emite sinais novos (isso e o scan de 5 minutos). Le os
precos, verifica stops e objetivos, le as respostas do Telegram, atualiza
o registo e envia os alertas de venda.
"""
import json
import os
import statistics
import sys
import time

from . import config, ledger, paper_trend, run, scanner, signals, sources

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


def ranges_for(assets, since):
    """Minimo e maximo de cada ativo nas velas de 1 minuto desde `since`.
    Uma fonte que responda chega; se nenhuma responder, fica sem intervalo
    e o acompanhamento usa so o preco atual."""
    out = {}
    for a in assets:
        for src in sources.ALL:
            try:
                c = [x for x in src.candles(a, "1m", limit=15)
                     if x["t"] >= since - 60]
            except Exception:       # fonte sem 1m ou em falha: tenta a seguinte
                continue
            if c:
                out[a] = (min(x["l"] for x in c), max(x["h"] for x in c))
                break
    return out


def open_assets(state):
    return {s["asset"] for s in state.get("signals", {}).values()
            if s["status"] == "TRIGGERED"}


def tick(state, prices, cfg, now, ranges=None):
    events = signals.track(state, prices, cfg, now, ranges)
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
        since = state.get("monitor_t") or now - 120
        rng = ranges_for(open_assets(state), max(since, now - 840))
        events = tick(state, prices_for(assets, data), cfg, now, rng)
    state["monitor_t"] = now
    res["monitored_at"] = now
    res["journal"] = ledger.view(state.get("ledger", []))
    res["active_signals"] = [s for s in state.get("signals", {}).values()
                             if s["status"] in ("ACTIVE", "TRIGGERED")]
    pt = state.get("paper_trend")
    if pt and res.get("paper_trend"):
        res["paper_trend"]["positions"] = pt["positions"]
        res["paper_trend"]["closed"] = pt["closed"][-15:]
    run.save(state, res, events)
    # so publica quando ha algo novo (o scan de 5 minutos e o sinal de vida)
    if events or replied:
        open(os.path.join(OUT, ".publish"), "w").close()
    print(f"monitor: {len(assets)} ativos, {len(events)} eventos")
    run.deliver(cfg, state, events)


if __name__ == "__main__":
    main()
