"""Relatorio diario e semanal por Telegram, e alerta de saude do sistema."""
import datetime
from zoneinfo import ZoneInfo

from . import ledger
from .strategies import px_str

TZ = ZoneInfo("Europe/Lisbon")
STR = {"PULLBACK": "recuo", "BREAKOUT": "quebra", "LIQUIDITY_SWEEP": "sweep",
       "RANGE": "range", "TREND_DAILY": "tendência diária"}


def _open_lines(state):
    """Operacoes em curso. As marcadas "nao executei" ficam de fora: o Rui
    nao as tem; continuam so a ser seguidas para as estatisticas."""
    out, skip = [], []
    no_ids, no_trend = ledger.declined(state)
    for k, s in state.get("signals", {}).items():
        if k in no_ids or s.get("id") in no_ids:
            if s["status"] in ("ACTIVE", "TRIGGERED"):
                skip.append(s["asset"])
            continue
        if s["status"] == "TRIGGERED":
            out.append(f"• {s['asset']} ({STR.get(s['strategy'], s['strategy'])})"
                       f": stop {px_str(s['position']['stop'])}, TPs "
                       f"{s['position']['tp_hit']}/3")
        elif s["status"] == "ACTIVE":
            out.append(f"• {s['asset']}: à espera de entrada até "
                       f"{px_str(s['plan']['entry_zone'][1])}")
    for a, p in state.get("paper_trend", {}).get("positions", {}).items():
        if a in no_trend:
            skip.append(a)
            continue
        out.append(f"• {a} (tendência diária): stop {px_str(p['stop0'])}")
    return out, skip


def daily(res, state):
    mf = res.get("market_filter") or {}
    c = res.get("counts", {})
    watch = [r for r in res["universe"]
             if r["decision"]["decision"] == "WATCHLIST"
             and r["decision"].get("plan")]
    watch.sort(key=lambda r: -r["decision"]["score"])
    L = ["📋 RELATÓRIO DIÁRIO",
         f"Mercado: BTC {'acima' if mf.get('btc_above_sma200') else 'abaixo'} "
         f"da média de 200 dias ({mf.get('distance_pct', 0):+.1f}%), regime "
         f"{(res.get('market_regime') or {}).get('btc')}.",
         f"Analisados {c.get('deep_checked')} ativos: {c.get('long')} com "
         f"sinal, {c.get('watchlist')} em vigilância."]
    ne = res.get("next_event")
    if res.get("event_block"):
        L.append(f"⛔ Sem compras novas: {res['event_block']}.")
    elif ne:
        when = datetime.datetime.fromtimestamp(ne["t"], TZ)
        L.append(f"Próximo evento: {ne['name']}, {when:%d/%m às %H:%M}.")
    if res.get("calendar_stale"):
        L.append("⚠️ Calendário de eventos desatualizado: pede-me para o "
                 "atualizar.")
    if res.get("halt"):
        L.append(f"⛔ Operações suspensas: {res['halt']}.")
    op, skip = _open_lines(state)
    L.append("Operações em curso:\n" + "\n".join(op) if op
             else "Sem operações em curso.")
    if skip:
        L.append("Não executadas (só seguidas para as estatísticas, sem "
                 "avisos): " + ", ".join(sorted(set(skip))) + ".")
    if watch:
        L.append("A vigiar:\n" + "\n".join(
            f"• {r['asset']} ({STR.get(r['decision']['strategy'])}): "
            f"{r['decision']['reason']}" for r in watch[:5]))
    if res["status_global"] != "OK":
        bad = [n for n, s in res["sources"].items() if not s["ok"]]
        L.append("⚠️ Dados degradados: " + (", ".join(bad) or "Bybit UE"))
    return "\n".join(L)


def weekly(state, now):
    """Separa os sinais (todos, para medir as estrategias) das operacoes que
    o Rui executou (o dinheiro dele): so estas falam em % do capital."""
    led = state.get("ledger", [])
    s = ledger.summary(led, since=now - 7 * 86400)
    a = ledger.summary(led)
    L = ["📈 RELATÓRIO SEMANAL"]
    if any(r.get("executed") is not None for r in led):
        m = ledger.summary(led, since=now - 7 * 86400, executed_only=True)
        mt = ledger.summary(led, executed_only=True)
        if m["closed"]:
            L.append(f"As tuas operações esta semana: {m['closed']} fechadas, "
                     f"acerto {m['win_rate']:.0f}%, {m['total_r']:+.2f}R "
                     f"({m['capital_pct']:+.2f}% do capital).")
        else:
            L.append("As tuas operações: nenhuma fechada esta semana.")
        L.append(f"Desde o início: {mt['closed']} fechadas, "
                 f"{mt['total_r']:+.2f}R; {mt['open']} em curso.")
    if not s["closed"]:
        L.append("Sinais: nenhum fechado esta semana.")
    else:
        L.append(f"Sinais fechados esta semana (contam também os que não "
                 f"executaste): {s['closed']}, acerto {s['win_rate']:.0f}%, "
                 f"{s['total_r']:+.2f}R.")
        for k, v in s["by_strategy"].items():
            L.append(f"• {STR.get(k, k)}: {v['n']} sinais, {v['sum_r']:+.2f}R")
    L.append(f"Sinais desde o início: {a['closed']} fechados, "
             f"{a['total_r']:+.2f}R, queda máxima {a['max_drawdown_r']:.1f}R.")
    return "\n".join(L)


def due(res, state, now):
    """Mensagens a enviar agora: [(tipo, texto)]. Atualiza o estado."""
    out = []
    loc = datetime.datetime.fromtimestamp(now, TZ)
    rep = state.setdefault("reports", {})
    day = loc.strftime("%Y-%m-%d")
    if loc.hour >= 8 and rep.get("daily") != day:
        rep["daily"] = day
        out.append(("daily", daily(res, state)))
        if loc.weekday() == 0 and rep.get("weekly") != day:
            rep["weekly"] = day
            out.append(("weekly", weekly(state, now)))
    health = res["status_global"]
    if rep.get("health", "OK") != health:
        if health != "OK":
            bad = [n for n, s in res["sources"].items() if not s["ok"]]
            if not (res.get("venue_source") or {}).get("ok"):
                bad.append("Bybit UE")
            out.append(("health", "⚠️ SISTEMA DEGRADADO — sem dados de: "
                        + ", ".join(bad) + ". Sinais dependentes ficam "
                        "suspensos até recuperar."))
        else:
            out.append(("health", "✅ Sistema recuperado: todas as fontes de "
                        "dados a responder."))
        rep["health"] = health
    return out
