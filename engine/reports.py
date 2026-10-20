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
    no_ids = set(no_ids) | {r["id"] for r in state.get("ledger", [])
                            if ledger.user_closed(r)}
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
    m = res.get("meta") or {}
    if m:                                   # o objetivo e para ser atingido (diretriz do Rui)
        L.append(f"🎯 Objetivo da equipa: {m['marco']:,} USDC (faltam {m['falta_marco']:.2f}).".replace(",", " "))
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
    pb = (res.get("paper_bounce") or {}).get("G0")
    if pb and (pb["n"] or pb["open"]):
        L.append(f"📝 Papel Oversold Bounce (não validada): {pb['n']} fechadas, "
                 f"{pb['total_r']:+.2f}R"
                 + (f"; abertas: {', '.join(pb['open'])}" if pb["open"] else "")
                 + ".")
    if watch:
        L.append("A vigiar:\n" + "\n".join(
            f"• {r['asset']} ({STR.get(r['decision']['strategy'])}): "
            f"{r['decision']['reason']}" for r in watch[:5]))
    if res["status_global"] != "OK":
        bad = [n for n, s in res["sources"].items() if not s["ok"]]
        L.append("⚠️ Dados degradados: " + (", ".join(bad) or "Bybit UE"))
    return "\n".join(L)


def lessons(state, now):
    """Licoes da semana tiradas dos factos: perdas em cadeia na mesma hora,
    stops tocados e recuperados, etc. Frases curtas, so com dados."""
    led = [r for r in state.get("ledger") or [] if r.get("status") == "CLOSED"
           and r.get("kind") != "1D" and r.get("closed_at") and now - r["closed_at"] < 7 * 86400 and r.get("result_r") is not None]
    out = []
    loss = sorted((r for r in led if r["result_r"] < 0), key=lambda r: r["closed_at"])
    for i, r in enumerate(loss):                 # 3+ stops na mesma hora = a mesma aposta
        grp = [x for x in loss if 0 <= x["closed_at"] - r["closed_at"] < 3600]
        if len(grp) >= 3:
            out.append(f"{len(grp)} stops na mesma hora ({', '.join(x['asset'] for x in grp)}): era uma só "
                       "aposta no mercado. Desde 15/10 sinais da mesma família na mesma vela dividem o risco.")
            break
    wins = [r for r in led if r["result_r"] > 0]
    if led:
        out.append(f"Acerto dos sinais da semana: {len(wins)} em {len(led)}.")
    return out


def weekly(state, now, arena_summary=None, res=None):
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
    nu = (res or {}).get("nucleo") or {}
    if nu.get("pos") or nu.get("resultado_fechado_usdc"):
        L.append(f"🧱 Núcleo (BTC/ETH/SOL com a média de 200 dias): {nu.get('valor_usdc', 0):.2f} USDC em carteira, "
                 f"{nu.get('resultado_aberto_usdc', 0):+.2f} USDC em aberto, {nu.get('resultado_fechado_usdc', 0):+.2f} USDC fechados.")
    rv = (res or {}).get("reais") or {}
    if rv.get("n"):
        L.append(f"🧾 Resultado REAL na Bybit (execuções e comissões): {rv['n']} operações, "
                 f"{rv['pnl_usdc']:+.2f} USDC ({rv['real_r']:+.2f}R reais contra {rv['sinal_r']:+.2f}R do sinal; "
                 f"comissões {rv['comissoes_usdc']:.2f} USDC).")
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
    res = res or {}
    for x in lessons(state, now):
        L.append("💡 " + x)
    d = res.get("diretor") or {}
    if d:
        av = d.get("avaliacao") or {}
        L.append(f"🧭 Diretor: rejeições seguidas em papel — {av.get('evitou_perda', 0)} evitaram perda, "
                 f"{av.get('custou_ganho', 0)} custaram ganho.")
        sb = [t for t in d.get("departamentos") or [] if t.get("n")]
        if sb:
            L.append("Quem acerta: " + ", ".join(f"{t['dep']} {t['taxa']:.0f}% ({t['n']})" for t in sb[:4]))
    cr = (res.get("promo") or {}).get("crescimento") or []
    if cr:
        L.append("Quem nos leva mais depressa (combate): " + ", ".join(
            f"{x['persona']} {x['r_mes']:+.1f}R/mês" for x in cr[:3]))
    m = res.get("meta") or {}
    if m:
        L.append(f"🏁 Meta: {m['capital']:.2f} USDC; próximo marco {m['marco']:,} USDC "
                 f"(faltam {m['falta_marco']:.2f}).".replace(",", " "))
    board = (arena_summary or {}).get("classificacao") or []
    if board:
        ico = {"SOBE": "🏆", "A COMPETIR": "⚔️", "MORTA": "💀"}
        L.append("Arena (todas as estratégias contra o acaso):")
        board = sorted((b for b in board if b.get("avg_r") is not None),
                       key=lambda b: -b["avg_r"])
        for b in board[:8]:
            avg = "sem operações" if b["avg_r"] is None else \
                f"{b['n']} op., {b['avg_r']:+.2f}R"
            L.append(f"{ico.get(b['estado'], '•')} {b['name']}: {avg}")
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

    # relatorio semanal ao domingo a partir das 20h (decisao do Rui, 2026-10-15)
    if loc.weekday() == 6 and loc.hour >= 20 and rep.get("weekly") != day:
        rep["weekly"] = day
        out.append(("weekly", weekly(state, now, res.get("arena"), res)))
    # liga semanal: resumo ao domingo a partir das 20h (uma vez por semana)
    if loc.weekday() == 6 and loc.hour >= 20 and res.get("liga") and \
            rep.get("liga") != res["liga"].get("semana"):
        from . import liga
        txt = liga.text(res["liga"])
        rep["liga"] = res["liga"].get("semana")
        if txt:
            out.append(("liga", txt))
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
