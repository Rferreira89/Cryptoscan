import json
import os
import sys

from . import alerts, scanner, strategies, validation

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


def _px(x):
    return strategies.px_str(x)


def alert_text(e, sigs, note):
    """Texto do Telegram para um evento. None = não notificar."""
    s = sigs.get(e["id"]) or e.get("signal")
    if not s:
        return None
    p, k = s["plan"], e["event"]
    head = f"{s['asset']} ({s['pair']}, {s['venue']})"
    if k == "ISSUED":
        return (f"🟢 COMPRA — {head}\n"
                f"{s['strategy']} · {s['timeframe']} · score {s['score']}/100\n"
                f"Ordem limite: {_px(p['entry_zone'][0])} a {_px(p['entry_zone'][1])}\n"
                f"Investir: {p['position_pct']}% do capital (risco {p['risk_pct']}%)\n"
                f"Stop: {_px(p['stop'])} (-{p['stop_pct']}%)\n"
                f"TP1 {_px(p['tp'][0])} (vender 50%) · TP2 {_px(p['tp'][1])} "
                f"(30%) · TP3 {_px(p['tp'][2])} (20%)\n"
                f"R:R 1:{p['rr']} · válido 12h\n{note}")
    if k == "TRIGGERED":
        return (f"🔵 ENTRADA — {head}\nPreço entrou na zona de compra "
                f"({_px(e['price'])}). Coloca o stop em {_px(p['stop'])}.")
    if k in ("TP1", "TP2", "TP3"):
        extra = " Sobe o stop para o preço de entrada." if k == "TP1" else ""
        r = f" Resultado final: {e['r']:+.2f}R." if "r" in e else ""
        return (f"🟠 VENDA PARCIAL — {head}\n{k} atingido em {_px(e['price'])}: "
                f"vender {e['sold_pct']:.0f}% da posição.{extra}{r}")
    if k in ("STOP", "BREAKEVEN", "TIME"):
        txt = {"STOP": "Stop atingido", "BREAKEVEN": "Stop na entrada atingido",
               "TIME": "Tempo máximo (30 dias) atingido"}[k]
        return (f"🔴 VENDA — {head}\n{txt} em {_px(e['price'])}: vender o "
                f"resto da posição. Resultado: {e['r']:+.2f}R.")
    if k in ("EXPIRED", "INVALIDATED"):
        return (f"⚪ CANCELAR — {head}\n{e['reason']}. Cancela a ordem de "
                "compra se ainda estiver aberta.")
    return None


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
    if res.get("config", {}).get("alerts") and alerts.configured():
        sigs = state.get("signals", {})
        for e in events:
            s = sigs.get(e["id"]) or e.get("signal") or {}
            txt = alert_text(e, sigs, validation.note(s.get("strategy")))
            if txt:
                try:
                    alerts.send(txt)
                except alerts.AlertError as err:
                    print("ALERTA FALHOU", err)
    # falha o job se nenhuma fonte respondeu: nunca publicar dados vazios
    sys.exit(0 if res["universe"] else 1)


if __name__ == "__main__":
    main()
