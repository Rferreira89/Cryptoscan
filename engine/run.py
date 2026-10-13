import datetime
import html
import json
import os
import sys
from zoneinfo import ZoneInfo

from . import (alerts, config, inbox, ledger, paper_bounce, paper_trend,
               reports, scanner,
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
        ds = r.get("decision_short")
        if ds and ds.get("plan"):
            ps = ds["plan"]
            L.append(f"  {r['asset']:8s} SHORT? {ds['decision']:9s} "
                     f"{ds.get('strategy')} {ds.get('state')} score "
                     f"{ds.get('score')} | zona {ps['entry_zone']} stop "
                     f"{ps['stop']} tp {ps['tp']} rr {ps['rr']} risco "
                     f"{ps.get('risk_usdc')} | {ds.get('reason')}")
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
    order = (f"NA BYBIT: liga a Margem e escreve {usdc:.2f} USDC no valor "
             "da ordem. É esse o valor certo, haja ou não empréstimo: a "
             "Bybit só empresta o que faltar no teu saldo livre. Não "
             "aumentes a ordem para forçar um empréstimo. Se o par não "
             f"tiver Margem e o saldo não chegar, entra com "
             f"{usdc / lev['use']:.2f} USDC, com o mesmo stop e objetivos\n"
             if usdc else "")
    return (f"Alavancagem: {lev['use']:g}x{why}\n"
            f"Posição: {amt}{position_pct}% do capital, {mine} "
            f"(risco {risk_pct}%)\n{order}"
            f"Liquidação estimada perto de {_px(lev['liquidation_est'])} "
            "(confirma na Bybit)")


def warn_line(s):
    """Avisos so informativos (nao mudam a decisao): quebras de estrutura
    recentes contra a operacao."""
    w = s.get("warnings") or []
    return ("⚠️ Atenção: " + "; ".join(w) + ". Não muda o sinal, mas aumenta "
            "o risco de falhar.\n") if w else ""


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


def short_text(e, s, head, note):
    """Alertas de short: vender emprestado, recomprar mais baixo."""
    p, k = s["plan"], e["event"]
    lev = p.get("leverage") or {}
    if k == "ISSUED":
        parts = p.get("partials", [50, 30, 20])
        buys = " · ".join(f"TP{i + 1} {_px(p['tp'][i])} (recomprar {parts[i]}%)"
                          for i in range(3) if parts[i] > 0)
        if parts[0] == 0:
            buys += (f"\nAo chegar a {_px(p['tp'][0])}, desce o stop para o "
                     "preço de entrada (sem recomprar)")
        usdc = p.get("position_usdc")
        amt = f"{usdc:.2f} USDC" if usdc else f"{p['position_pct']}% do capital"
        why = f" — {lev['reason']}" if lev.get("reason") else ""
        liq = (f"\nLiquidação estimada perto de {_px(lev['liquidation_est'])} "
               "(confirma na Bybit)" if lev.get("liquidation_est") else "")
        return (f"🔻 SHORT — {head}\n"
                f"{s['strategy']} · {s['timeframe']} · score {s['score']}/100\n"
                f"Margem spot: pedir {s['asset']} emprestado e VENDER, com "
                f"ordem limite entre {_px(p['entry_zone'][0])} e "
                f"{_px(p['entry_zone'][1])}\n"
                f"Alavancagem: {lev.get('use', 1):g}x{why}\n"
                f"Posição: vender o equivalente a {amt} (risco {p['risk_pct']}%)"
                f"{liq}\n"
                f"Stop (recompra): {_px(p['stop'])} (+{p['stop_pct']}%), ACIMA "
                "da entrada\n"
                f"{buys}\n"
                f"R:R 1:{p['rr']} · válido 12h\n{warn_line(s)}{note}")
    if k == "TRIGGERED":
        return (f"🔵 ENTRADA (short) — {head}\nPreço entrou na zona de venda "
                f"({_px(e['price'])}). Coloca o stop de recompra em "
                f"{_px(p['stop'])}.")
    if k in ("TP1", "TP2", "TP3"):
        if "r" in e:
            return (f"🟢 RECOMPRA FINAL — {head}\n{k} atingido em "
                    f"{_px(e['price'])}: recomprar o resto e devolver o "
                    f"empréstimo. Resultado: {e['r']:+.2f}R.")
        if not e["sold_pct"]:
            return (f"🟠 STOP PARA A ENTRADA — {head}\n{k} atingido em "
                    f"{_px(e['price'])}: não recompres, desce só o stop para "
                    "o teu preço de entrada.")
        extra = " Desce o stop para o preço de entrada." if k == "TP1" else ""
        return (f"🟠 RECOMPRA PARCIAL — {head}\n{k} atingido em "
                f"{_px(e['price'])}: recomprar {e['sold_pct']:.0f}% da "
                f"posição.{extra}")
    if k in ("STOP", "BREAKEVEN", "TIME", "NOREACT"):
        hold = (p.get("max_hold_s") or 30 * 86400) // 86400
        txt = {"STOP": "Stop atingido", "BREAKEVEN": "Stop atingido (acima ou na entrada)",
               "TIME": f"Tempo máximo ({hold:g} dias) atingido",
               "NOREACT": f"Sem reação em {(p.get('no_react_s') or 43200) // 3600:g} horas: o ressalto não arrancou"}[k]
        return (f"🔴 RECOMPRA — {head}\n{txt} em {_px(e['price'])}: recomprar "
                "tudo e devolver o empréstimo. "
                f"Resultado: {e['r']:+.2f}R.")
    if k in ("EXPIRED", "INVALIDATED"):
        return (f"⚪ CANCELAR — {head}\n{e['reason']}. Cancela a ordem de "
                "venda se ainda estiver aberta.")
    return None


CHAMP_PREFIX = ("BOUNCE_", "DIP_TREND", "CAPITULACAO")


def champ_name(k):
    from . import arena
    return f"{arena.persona(k)} · {arena._name(k).replace(' (papel)', '')}"


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
        tag = "PREPARA (short)" if e.get("side") == "SHORT" else "PREPARA"
        return (f"👀 {tag} — {e['asset']} ({e['pair']}) · {e['strategy']}\n"
                f"Ainda não é sinal. Gatilho: {e['trigger']}.\n"
                f"Se acontecer: entrada {_px(e['entry'][0])} a "
                f"{_px(e['entry'][1])}, stop {_px(e['stop'])}, "
                f"1.º objetivo {_px(e['tp1'])}.")
    if k == "REWARD":
        return (f"🎉 ESCRITÓRIO — desbloqueaste: {e['name']}! "
                f"Conquista real: {e['cond']}. Vai ver ao escritório 3D.")
    if k == "ARENA_OFF":
        nm = {"BREAKOUT": "Quebra (Bruno)", "PULLBACK": "Recuo (Rita)",
              "LIQUIDITY_SWEEP": "Sweep (Simão)", "RANGE": "Range (Raquel)",
              "TREND_DAILY": "Tendência diária (Teodoro)"}
        lst = ", ".join(nm.get(x.replace("_SHORT", ""), x) +
                        (" short" if x.endswith("_SHORT") else "")
                        for x in e["strategies"])
        return ("⚙️ ARENA — morte automática: desliguei " + lst + ". Morreram "
                "na arena e deixam de emitir sinais reais; as operações já "
                "abertas continuam a ser acompanhadas até fecharem. Não "
                "precisas de fazer nada.")
    if k == "ARENA":
        if e["estado"] == "MORTA":
            cmd = {"BREAKOUT": "quebra", "PULLBACK": "recuo",
                   "LIQUIDITY_SWEEP": "sweep", "RANGE": "range",
                   "TREND_DAILY": "tendencia"}.get(e.get("strategy"))
            if e["live"] and e.get("desligada"):
                extra = (" Desligada automaticamente: deixa de emitir sinais "
                         "reais. As operações já abertas continuam a ser "
                         "acompanhadas até fecharem. Só volta como sucessor "
                         "da investigação, se bater o acaso.")
            elif e["live"] and cmd:
                extra = (" Para a desligar responde: /desliga " + cmd)
            elif e["live"]:
                extra = ""
            else:
                extra = " Deixa de abrir operações."
            onde = (f" na {e['motivo']}" if e.get("motivo") and
                    e["motivo"].startswith("forma") else "")
            r_ = e["avg_r"] if e.get("avg_r") is not None else 0
            return (f"💀 ARENA — {e['name']} morreu{onde}: {e['n']} operações, "
                    f"{r_:+.2f}R em média, sem vantagem sobre o "
                    f"acaso.{extra}")
        return (f"🏆 ARENA — {e['name']} ganhou o direito a ser proposta para "
                f"dinheiro real: {e['n']} operações, {e['avg_r']:+.2f}R em "
                "média, acima de 95% das entradas ao acaso. A decisão é tua.")
    if k == "BOUNCE_PAPER_BUY":
        tps = " / ".join(_px(x) for x in e["tp"])
        return (f"📝 PAPEL — Oversold Bounce · {e['asset']} ({e['pair']})\n"
                f"Compra simulada a {_px(e['price'])} (RSI 4H {e['rsi']}). "
                f"Stop {_px(e['stop'])}, objetivos {tps}, saída em 3 dias.\n"
                f"{paper_bounce.RECORD}")
    if k == "BOUNCE_PAPER_SELL":
        why = {"STOP": "stop", "BREAKEVEN": "stop na entrada", "TIME":
               "fim dos 3 dias"}.get(e["reason"], "objetivo")
        return (f"📝 PAPEL — Oversold Bounce · {e['asset']} fechada ({why}): "
                f"{e['r']:+.2f}R. {paper_bounce.RECORD}")
    if k == "EVENT_OPEN":
        quando = datetime.datetime.fromtimestamp(
            e["event_t"], ZoneInfo("Europe/Lisbon")).strftime("%d/%m às %H:%M")
        stop = f" O teu stop está em {_px(e['stop'])}: confirma que está colocado na Bybit." if e.get("stop") else ""
        return (f"⚠️ EVENTO NUMA OPERAÇÃO ABERTA — {e['asset']}\n"
                f"{e['name']}, {quando} (hora de Lisboa).\n"
                "Desbloqueios trazem muitas vezes pressão de venda e saltos de "
                f"preço.{stop} Decisão tua: manter, reduzir ou sair; o sistema "
                "não mexe no plano.")
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
    if s.get("direction") == "SHORT":
        return short_text(e, s, head, note)
    if k == "ISSUED" and str(s["strategy"]).startswith(CHAMP_PREFIX):
        hold = p.get("max_hold_s")
        return (f"🟢 COMPRA — {head}\n"
                f"🏆 Campeão da arena: {champ_name(s['strategy'])}\n"
                f"Ordem limite perto de {_px(p['entry_zone'][1])} (já, na zona "
                f"{_px(p['entry_zone'][0])} a {_px(p['entry_zone'][1])})\n"
                f"{invest_line(p['position_pct'], p['risk_pct'], p.get('leverage'), p.get('position_usdc'))}\n"
                f"Stop: {_px(p['stop'])} (-{p['stop_pct']}%)\n"
                f"{targets_line(p)}\n"
                + (f"Saída obrigatória ao fim de {hold // 86400:g} dia(s), se não "
                   "tiver fechado antes.\n" if hold else "")
                + (f"Se ao fim de {p['no_react_s'] // 3600:g} horas não houver reação "
                   "(preço abaixo da entrada), o programa avisa para sair.\n"
                   if p.get("no_react_s") else "")
                + ("Depois do 1.º objetivo o stop sobe com o preço; segue os avisos.\n"
                   if p.get("trail_r") else "")
                + ("⚠️ Risco reduzido para metade depois de 2 perdas seguidas.\n"
                   if p.get("risk_reduced") else "")
                + f"{note}")
    if k == "ISSUED":
        return (f"🟢 COMPRA — {head}\n"
                f"{s['strategy']} · {s['timeframe']} · score {s['score']}/100\n"
                f"Ordem limite: {_px(p['entry_zone'][0])} a {_px(p['entry_zone'][1])}\n"
                f"{invest_line(p['position_pct'], p['risk_pct'], p.get('leverage'), p.get('position_usdc'))}\n"
                f"Stop: {_px(p['stop'])} (-{p['stop_pct']}%)\n"
                f"{targets_line(p)}\n"
                f"R:R 1:{p['rr']} · válido 12h\n{warn_line(s)}{note}")
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
    if k in ("STOP", "BREAKEVEN", "TIME", "NOREACT"):
        hold = (p.get("max_hold_s") or 30 * 86400) // 86400
        txt = {"STOP": "Stop atingido", "BREAKEVEN": "Stop atingido (acima ou na entrada)",
               "TIME": f"Tempo máximo ({hold:g} dias) atingido",
               "NOREACT": f"Sem reação em {(p.get('no_react_s') or 43200) // 3600:g} horas: o ressalto não arrancou"}[k]
        return (f"🔴 VENDA — {head}\n{txt} em {_px(e['price'])}: vender o "
                f"resto da posição. Resultado: {e['r']:+.2f}R.")
    if k in ("EXPIRED", "INVALIDATED"):
        return (f"⚪ CANCELAR — {head}\n{e['reason']}. Cancela a ordem de "
                "compra se ainda estiver aberta.")
    return None


def bybit_url(pair):
    """Pagina do par na Bybit UE (no iPhone pode abrir a app)."""
    base, _, quote = (pair or "").partition("/")
    return f"https://www.bybit.eu/en-EU/trade/spot/{base}/{quote or 'USDC'}"


def order_block(s):
    """Valores da ordem prontos a copiar (HTML do Telegram: <code> copia
    com um toque). Pontos decimais, como a Bybit aceita."""
    p = s["plan"]
    sh = s.get("direction") == "SHORT"
    usdc = p.get("position_usdc")
    ref = p.get("entry_ref") or p["entry_zone"][1]
    c = lambda x: f"<code>{_px(x)}</code>"
    L = ["📋 ORDEM PRONTA — toca num valor para o copiar"]
    if usdc:
        L.append(f"Valor da ordem: <code>{usdc:.2f}</code> USDC")
        L.append(f"(ou quantidade: <code>{float(f'{usdc / ref:.4g}'):g}</code> "
                 f"{html.escape(s['asset'])})")
    L.append(f"Preço limite de {'venda' if sh else 'compra'}: {c(ref)}")
    L.append(f"Stop-loss: {c(p['stop'])}")
    parts = p.get("partials", [50, 30, 20])
    for i in range(3):
        if i == 0 or parts[i] > 0:
            L.append(f"TP{i + 1}: {c(p['tp'][i])}")
    return "\n".join(L)


def markup_for(e, s, real):
    """Botoes do alerta: executei / nao executei. (O link para a Bybit foi
    retirado: no iPhone o Telegram abre o site e nao a app.)"""
    oid = op_id(e)
    return inbox.buttons(oid) if oid and real else None


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


ADMIN = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "admin.json")


def apply_admin(state, path=ADMIN, now=None, send=None):
    """Comandos pedidos pelo Rui numa sessao (admin.json na raiz do main),
    com o mesmo texto e efeito dos comandos do Telegram (/capital,
    /fechei, /preco, /desliga, /liga). Cada id so e aplicado uma vez."""
    try:
        with open(path) as f:
            cmds = json.load(f).get("comandos", [])
    except (OSError, ValueError):
        return []
    done = state.setdefault("admin_done", [])
    t = int(now or __import__("time").time())
    out = []
    for c in cmds:
        if c.get("id") in done or not c.get("texto"):
            continue
        ups = [{"message": {"chat": {"id": "admin"}, "date": t, "text": c["texto"]}}]
        res = inbox.apply(state, ups, "admin")
        done.append(c["id"])
        out += [txt for txt, _ in res]
    del done[:-200]
    if send:
        for txt in out:
            try:
                send("✍️ " + txt)
            except Exception:
                pass
    return out


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
        real = s.get("mode") != "PAPER" and e.get("real", True)
        html_mode = False
        if real and e["event"] == "ISSUED" and s.get("plan"):
            txt = html.escape(txt) + "\n\n" + order_block(s)
            html_mode = True
        try:
            alerts.send(txt, markup_for(e, s, real), html=html_mode)
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


SCAN_HISTORY_SECONDS = 7 * 86400


def record_scan(state, t):
    """Guarda a hora de cada scan dos ultimos 7 dias em state["scan_times"],
    para que paragens passadas fiquem visiveis (a auditoria procura
    intervalos acima de 30 minutos)."""
    times = [x for x in state.get("scan_times", [])
             if isinstance(x, int) and t - SCAN_HISTORY_SECONDS <= x < t]
    state["scan_times"] = times + [int(t)]
    return state["scan_times"]


def load_forma():
    """Ultima forma recente da arena (tools/arena_ringue.py, ramo arena).
    So no GitHub Actions; falha de rede -> None (a arena usa a guardada)."""
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not repo:
        return None
    import urllib.request
    try:
        url = f"https://raw.githubusercontent.com/{repo}/arena/forma.json"
        with urllib.request.urlopen(url, timeout=10) as r:
            return json.loads(r.read().decode())
    except Exception:
        return None


def main():
    os.makedirs(OUT, exist_ok=True)
    state = _load("state.json", {})
    process_inbox(state)
    apply_admin(state, send=alerts.send if alerts.configured() else None)
    res, state, events = scanner.run(state=state, forma=load_forma())
    extra = reports.due(res, state, res["generated_at"]) if res["universe"] else []
    res["journal"] = ledger.view(state.get("ledger", []))
    if res["universe"]:             # so conta scans com dados
        record_scan(state, res["generated_at"])
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
