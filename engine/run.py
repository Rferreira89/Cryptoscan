import json
import os
import sys

from . import (alerts, config, inbox, ledger, paper_trend, reports, scanner,
               strategies, validation)

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
        L.append(f"  {r['asset']:8s} {d['decision']:9s} {d.get('mode', '-'):5s} "
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
    L.append(f"FILTRO DE MERCADO {res.get('market_filter')}")
    pt = res.get("paper_trend") or {}
    L.append(f"PAPEL TENDENCIA capital {pt.get('equity_pct')}% n {pt.get('n')} "
             f"posicoes {list((pt.get('positions') or {}))}")
    L.append(f"REGISTO {res.get('track_record')} TRAVAO {res.get('halt')}")
    L.append(f"SINAIS ATIVOS {len(res['active_signals'])}")
    for s in res["active_signals"]:
        L.append(f"  {s['id']} {s['status']} {s['plan']}")
    return L


def _px(x):
    return strategies.px_str(x)


def invest_line(position_pct, risk_pct, lev, usdc=None):
    """Linhas de dimensao e de alavancagem recomendada para a operacao."""
    why = f" — {lev['reason']}" if lev and lev.get("reason") else ""
    amt = f"{usdc:.2f} USDC, " if usdc else ""
    if not lev or lev.get("use", 1) <= 1:
        return (f"Alavancagem: 1x (sem margem){why}\n"
                f"Investir: {amt}{position_pct}% do capital (risco {risk_pct}%)")
    mine = (f"{usdc / lev['use']:.2f} USDC teus e {usdc - usdc / lev['use']:.2f} "
            "emprestados" if usdc else
            f"{lev['collateral_pct']}% teus e o resto emprestado")
    return (f"Alavancagem: {lev['use']:g}x{why}\n"
            f"Posição: {amt}{position_pct}% do capital, {mine} "
            f"(risco {risk_pct}%)\n"
            f"Liquidação estimada perto de {_px(lev['liquidation_est'])} "
            "(confirma na Bybit)")


def targets_line(p):
    """Objetivos e vendas, conforme o esquema de parciais da operacao."""
    parts = p.get("partials", [50, 30, 20])
    sells = [f"TP{i + 1} {_px(p['tp'][i])} (vender {parts[i]}%)"
             for i in range(3) if parts[i] > 0]
    txt = " · ".join(sells)
    if parts[0] == 0:
        txt += (f"\nAo chegar a {_px(p['tp'][0])}, sobe o stop para o preço "
                "de entrada (sem vender)")
    return txt


def paper_text(e, s, head, note):
    """Sinais de estrategias nao validadas: simulacao, nunca uma ordem."""
    p, k = s["plan"], e["event"]
    tag = f"📝 PAPEL (simulação) — {head} · {s['strategy']}"
    if k == "ISSUED":
        return (f"{tag}\nSetup: entrada {_px(p['entry_zone'][0])} a "
                f"{_px(p['entry_zone'][1])}, stop {_px(p['stop'])}, "
                f"TP1 {_px(p['tp'][0])} · TP2 {_px(p['tp'][1])} · "
                f"TP3 {_px(p['tp'][2])}, R:R 1:{p['rr']}, score {s['score']}.\n"
                f"{note}")
    if k == "TRIGGERED":
        return f"{tag}\nEntrada simulada a {_px(e['price'])}."
    if k in ("TP1", "TP2", "TP3"):
        r = f" Resultado final: {e['r']:+.2f}R." if "r" in e else ""
        return f"{tag}\n{k} atingido em {_px(e['price'])}.{r}"
    if k in ("STOP", "BREAKEVEN", "TIME"):
        txt = {"STOP": "Stop atingido", "BREAKEVEN": "Stop na entrada atingido",
               "TIME": "Tempo máximo atingido"}[k]
        return f"{tag}\n{txt} em {_px(e['price'])}. Resultado: {e['r']:+.2f}R."
    if k in ("EXPIRED", "INVALIDATED"):
        return f"{tag}\nSetup cancelado: {e['reason']}."
    return None


def alert_text(e, sigs, note):
    """Texto do Telegram para um evento. None = não notificar."""
    k = e["event"]
    if k == "MARKET_FILTER":
        return ("📊 REGIME DE MERCADO — o BTC passou para "
                + ("ACIMA" if e["above"] else "ABAIXO")
                + f" da média de 200 dias ({_px(e['close'])} vs "
                f"{_px(e['sma200'])}). "
                + ("Historicamente é o contexto favorável a compras."
                   if e["above"] else
                   "Historicamente é o contexto em que comprar perde mais."))
    if k == "WATCH":
        return (f"👀 PREPARA — {e['asset']} ({e['pair']}) · {e['strategy']}\n"
                f"Ainda não é sinal. Gatilho: {e['trigger']}.\n"
                f"Se acontecer: entrada {_px(e['entry'][0])} a "
                f"{_px(e['entry'][1])}, stop {_px(e['stop'])}, "
                f"1.º objetivo {_px(e['tp1'])}.")
    if k == "STRATEGY_DISABLED":
        return (f"⛔ ESTRATÉGIA DESLIGADA — {e['strategy']}: {e['n']} operações "
                f"ao vivo com resultado {e['sum_r']:+.2f}R. Deixa de gerar "
                "sinais.")
    if k == "PAPER_BUY" and e.get("real"):
        return (f"🟢 COMPRA — {e['asset']} ({e['pair']}, Bybit EU)\n"
                "TENDÊNCIA DIÁRIA · quebra do máximo de 20 dias\n"
                f"Ordem a mercado, perto de {_px(e['price'])}\n"
                + invest_line(e["position_pct"], e["risk_pct"],
                              usdc=e.get("position_usdc"), lev=
                              {"use": e.get("leverage", 1),
                               "reason": e.get("leverage_reason"),
                               "collateral_pct": e.get("collateral_pct"),
                               "liquidation_est": e.get("liquidation_est")})
                + "\n"
                f"Stop: {_px(e['stop'])} (-{e['stop_pct']}%)\n"
                "Sem objetivo fixo: aviso de venda quando o fecho diário "
                "ficar abaixo do mínimo de 20 dias.\n"
                f"{paper_trend.RECORD}")
    if k == "PAPER_SELL" and e.get("real"):
        why = {"STOP": "stop atingido", "TRAIL": "fecho diário abaixo do "
               "mínimo de 20 dias"}[e["reason"]]
        return (f"🔴 VENDA — {e['asset']} ({e['pair']}, Bybit EU)\n"
                f"TENDÊNCIA DIÁRIA: {why}. Vender toda a posição, perto de "
                f"{_px(e['price'])}. Resultado: {e['r']:+.2f}R.")
    if k == "PAPER_BUY":
        return (f"📝 PAPEL (simulação, não validado) — compra {e['asset']} "
                f"({e['pair']}) a {_px(e['price'])}, stop {_px(e['stop'])}, "
                f"{e['position_pct']}% do capital. Tendência diária.")
    if k == "PAPER_SELL":
        why = {"STOP": "stop atingido", "TRAIL": "fecho abaixo do mínimo "
               "de 20 dias"}[e["reason"]]
        return (f"📝 PAPEL (simulação, não validado) — venda {e['asset']} "
                f"({e['pair']}) a {_px(e['price'])}: {why}. "
                f"Resultado {e['r']:+.2f}R.")
    s = sigs.get(e["id"]) or e.get("signal")
    if not s:
        return None
    p = s["plan"]
    head = f"{s['asset']} ({s['pair']}, {s['venue']})"
    if s.get("mode") == "PAPER":
        return paper_text(e, s, head, note)
    if k == "ISSUED":
        return (f"🟢 COMPRA — {head}\n"
                f"{s['strategy']} · {s['timeframe']} · score {s['score']}/100\n"
                f"Ordem limite: {_px(p['entry_zone'][0])} a {_px(p['entry_zone'][1])}\n"
                f"{invest_line(p['position_pct'], p['risk_pct'], p.get('leverage'), p.get('position_usdc'))}\n"
                f"Stop: {_px(p['stop'])} (-{p['stop_pct']}%)\n"
                f"{targets_line(p)}\n"
                f"R:R 1:{p['rr']} · válido 12h\n{note}")
    if k == "TRIGGERED":
        return (f"🔵 ENTRADA — {head}\nPreço entrou na zona de compra "
                f"({_px(e['price'])}). Coloca o stop em {_px(p['stop'])}.")
    if k in ("TP1", "TP2", "TP3"):
        extra = " Sobe o stop para o preço de entrada." if k == "TP1" else ""
        if "r" in e:
            return (f"🟢 VENDA FINAL — {head}\n{k} atingido em "
                    f"{_px(e['price'])}: vender o resto da posição. "
                    f"Resultado: {e['r']:+.2f}R.")
        if not e["sold_pct"]:
            return (f"🟠 STOP PARA A ENTRADA — {head}\n{k} atingido em "
                    f"{_px(e['price'])}: não vendas, sobe só o stop para o "
                    "teu preço de entrada.")
        return (f"🟠 VENDA PARCIAL — {head}\n{k} atingido em {_px(e['price'])}: "
                f"vender {e['sold_pct']:.0f}% da posição.{extra}")
    if k in ("STOP", "BREAKEVEN", "TIME"):
        txt = {"STOP": "Stop atingido", "BREAKEVEN": "Stop na entrada atingido",
               "TIME": "Tempo máximo (30 dias) atingido"}[k]
        return (f"🔴 VENDA — {head}\n{txt} em {_px(e['price'])}: vender o "
                f"resto da posição. Resultado: {e['r']:+.2f}R.")
    if k in ("EXPIRED", "INVALIDATED"):
        return (f"⚪ CANCELAR — {head}\n{e['reason']}. Cancela a ordem de "
                "compra se ainda estiver aberta.")
    return None


def op_id(e):
    """Id da operacao no registo, para os botoes de confirmacao."""
    if e["event"] == "ISSUED":
        return e["id"]
    if e["event"] == "PAPER_BUY":
        return f"{e['id']}-{e['t']}"
    return None


def process_inbox(state):
    """Le respostas do Telegram e aplica-as ao registo."""
    chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not alerts.configured():
        return False
    ups = inbox.fetch(state)
    inbox.reply(inbox.apply(state, ups, chat), alerts.send)
    return bool(ups)


def deliver(cfg, state, events, extra=()):
    """Envia os alertas dos eventos (e relatorios) pelo Telegram."""
    if not (cfg.get("alerts") and alerts.configured()):
        return
    sigs = state.get("signals", {})
    for _, txt in extra:
        try:
            alerts.send(txt)
        except alerts.AlertError as err:
            print("ALERTA FALHOU", err)
    for e in events:
        if inbox.muted(state, e):
            continue
        s = sigs.get(e["id"]) or e.get("signal") or {}
        txt = alert_text(e, sigs, validation.note(s.get("strategy")))
        if not txt:
            continue
        oid = op_id(e)
        real = s.get("mode") != "PAPER" and e.get("real", True)
        try:
            alerts.send(txt, inbox.buttons(oid) if oid and real else None)
        except alerts.AlertError as err:
            print("ALERTA FALHOU", err)


def save(state, res, events):
    with open(os.path.join(OUT, "scan.json"), "w") as f:
        json.dump(res, f, separators=(",", ":"))
    with open(os.path.join(OUT, "state.json"), "w") as f:
        json.dump(state, f, separators=(",", ":"))
    if events:                      # audit log: so acrescenta, nunca reescreve
        with open(os.path.join(OUT, "audit.jsonl"), "a") as f:
            for e in events:
                f.write(json.dumps(e, separators=(",", ":")) + "\n")


def main():
    os.makedirs(OUT, exist_ok=True)
    state = _load("state.json", {})
    process_inbox(state)
    res, state, events = scanner.run(state=state)
    extra = reports.due(res, state, res["generated_at"]) if res["universe"] else []
    res["journal"] = ledger.view(state.get("ledger", []))
    save(state, res, events)
    text = "\n".join(summary(res))
    with open(os.path.join(OUT, "resumo.txt"), "w") as f:
        f.write(text + "\n")
    print(text)
    deliver(res.get("config", {}), state, events, extra)
    # falha o job se nenhuma fonte respondeu: nunca publicar dados vazios
    sys.exit(0 if res["universe"] else 1)


if __name__ == "__main__":
    main()
