import datetime
import html
import json
import os
import sys
from zoneinfo import ZoneInfo

from . import (alerts, config, consultas, europa, execucao, inbox, ledger, paper_bounce, paper_trend,
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
    L.append(f"EUROPA {res.get('europa')} CONTA "
             f"{ {k: v for k, v in (res.get('conta') or {}).items() if k != 'trades'} }")
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
    if k == "SUSPENSO":
        return (f"⏸️ PROVA REAL — {e['nome']} perde a vez: {e['motivo']}. Deixa de dar sinais "
                "reais até o resultado real voltar a acompanhar o combate. As operações abertas "
                "continuam a ser acompanhadas.")
    if k == "RETOMADO":
        return f"▶️ PROVA REAL — {e['nome']} volta a dar sinais reais: o resultado real recuperou."
    if k == "ARENA_REGRESSO":
        return (f"🔄 ARENA — regresso: o mercado mudou para {e['regime']}. "
                f"A estratégia de {e['antes']} volta ao ringue com um nome novo, "
                f"{e['nome']}, e registo limpo. Só conta o que fizer a partir de "
                "agora; se falhar, volta a morrer pelas mesmas regras.")
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
    if k == "HALT":
        quando = (datetime.datetime.fromtimestamp(e["until"], ZoneInfo("Europe/Lisbon"))
                  .strftime("%d/%m às %H:%M") if e.get("until") else "quando o resultado recuperar")
        d, w = (e.get("loss") or [0, 0])
        return (f"⛔ TRAVÃO DE PERDAS ATIVO\n{e['reason']}.\n"
                f"Dinheiro real: {d:+.2f}R nas últimas 24h, {w:+.2f}R em 7 dias.\n"
                f"Sem entradas novas até {quando} (se não fechar mais nenhuma operação). "
                "As operações abertas continuam protegidas pelos stops.")
    if k == "HALT_OFF":
        return ("✅ TRAVÃO DESLIGADO — o programa volta a emitir sinais reais. "
                "Risco e regras de sempre; o Diretor revê cada entrada.")
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
    if k == "ISSUED" and s.get("diretor"):
        note = diretor_lines(s["diretor"]) + note
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
                + ((f"🔗 Uma só aposta: {p['cluster']['n']} sinais da família «{p['cluster']['familia']}» "
                    "nesta vela; ficou só este, o melhor, inteiro, para proteger o lucro no TP1.\n")
                   if (p.get("cluster") or {}).get("melhor") else
                   (f"🔗 Uma só aposta: {p['cluster']['n']} sinais da família «{p['cluster']['familia']}» "
                    "nesta vela dividem o risco de uma operação.\n") if p.get("cluster") else "")
                + f"Stop: {_px(p['stop'])} (-{p['stop_pct']}%)\n"
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


def diretor_lines(v):
    """Parecer do Diretor de Trading no alerta de entrada."""
    ed = {"valido": "válidos", "atrasado": "atrasados", "indisponivel": "indisponíveis"}
    L = [f"🧭 Diretor de Trading: {v.get('decisao', '–')} (dados {ed.get(v.get('estado_dados'), '–')})"]
    for x in (v.get("a_favor") or [])[:3]:
        L.append(f"  ✔ {x}")
    for x in (v.get("contra") or [])[:3]:
        L.append(f"  ✖ {x}")
    if v.get("esperado"):
        L.append("  (contra mas esperado pela estratégia: " + ", ".join(v["esperado"]) + ")")
    if v.get("historico"):
        L.append("  📚 " + v["historico"])
    if v.get("invalidacao"):
        L.append("  Invalida se: " + "; ".join(v["invalidacao"][:2]))
    return "\n".join(L) + "\n"


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
    if not (oid and real):
        return None
    m = inbox.buttons(oid)
    # um toque: compras com o teste da compra; vendas a descoberto so depois
    # do teste real da venda a descoberto (decisao do Rui, 2026-10-15)
    short = s.get("direction") == "SHORT" or (s.get("plan") or {}).get("side") == "SHORT"
    if e.get("event") == "ISSUED" and not e.get("auto") and (execucao.READY_SHORT if short else execucao.READY):
        m["inline_keyboard"].insert(0, [execucao.button(oid)])
    if e.get("asset"):
        m["inline_keyboard"].append(consultas.why_buttons(e["asset"]))
    return m


def op_id(e):
    """Id da operacao no registo, para os botoes de confirmacao."""
    if e["event"] == "ISSUED":
        return e["id"]
    if e["event"] == "PAPER_BUY":
        return f"{e['id']}-{e['t']}"
    return None


def process_inbox(state, res=None):
    """Le respostas do Telegram, aplica-as ao registo e responde as
    perguntas (/porque, /ringue, ...) com o ultimo scan (res)."""
    chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not alerts.configured():
        return False
    ups = inbox.fetch(state)
    inbox.reply(inbox.apply(state, ups, chat, res), alerts.send)
    return bool(ups)


ADMIN = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "admin.json")


FIAT_OU_ESTAVEL = ("USDC", "USDT", "EUR", "USD", "FDUSD", "DAI")


def funding_alert(state, conta, now):
    """Deposito parado na conta Funding (18/10: "o programa nao esta a assumir
    capital novo"): a Bybit poe os depositos na Funding e o programa so ve a
    Conta Unificada. Avisa uma vez por valor novo (e de 12 em 12 horas)."""
    fundo = (conta or {}).get("fundo") or {}
    est = {k: v for k, v in fundo.items() if k in FIAT_OU_ESTAVEL and v >= 1}
    a = state.setdefault("fundo_aviso", {})
    if not est:
        a.clear()
        return None
    chave = ",".join(f"{k}:{v:.2f}" for k, v in sorted(est.items()))
    if a.get("chave") == chave and now - (a.get("t") or 0) < 12 * 3600:
        return None
    a.update(chave=chave, t=int(now))
    tot = " + ".join(f"{v:.2f} {k}" for k, v in sorted(est.items()))
    return (f"💶 Tens {tot} parado na conta <b>Funding</b> da Bybit. O programa só opera com a "
            "<b>Conta Unificada (Trading)</b>, por isso ainda não conta como capital.\n\n"
            "Na app da Bybit: Ativos → Transferir → de Funding para Conta Unificada. Em 15 minutos "
            "o programa assume o novo capital sozinho.\n\nEu não consigo transferir por ti: a chave "
            "não tem permissão de transferências nem de levantamentos, como pediste.")


def stop_watch(state, conta, now):
    """Fase 0 da contra-auditoria (Rui, 20/10): a conta e lida a cada 15
    minutos e diz se cada posicao do programa tem stop na Bybit
    (account.check_trades, stop_found). Ate aqui ninguem olhava para isso.
    Posicao com moedas e sem stop: aviso imediato (repetido de hora a hora
    enquanto durar) e o modo automatico desliga-se. Devolve os avisos."""
    from . import auto
    if not conta:
        return []
    vistos = state.setdefault("stop_watch", {})
    sem = [t for t in conta.get("trades") or [] if t.get("held") and not t.get("stop_found")]
    ids = {t["id"] for t in sem}
    for k in list(vistos):
        if k not in ids:
            vistos.pop(k)
    out = []
    for t in sem:
        if now - (vistos.get(t["id"]) or 0) < 3600:
            continue
        vistos[t["id"]] = int(now)
        txt = (f"🚨 <b>{t['asset']} SEM STOP na Bybit.</b> Tens moedas mas não encontrei a ordem de stop "
               f"(plano: {t.get('plan_stop'):.6g}). Põe o stop na app da Bybit agora ou fecha a posição.")
        a = state.get("auto") or {}
        if a.get("ligado"):
            auto.turn(state, False, now)
            (state.get("auto") or {})["motivo"] = f"posição sem stop em {t['asset']}"
            txt += " O modo automático foi desligado; volta a ligar com /auto forcar quando estiver resolvido."
        out.append(txt)
    return out


def ordens_watch(state, conta, ex, now):
    """D1 da auditoria (Rui, 21/10; caso XPL): uma vez por dia, cada posicao
    real tem de ter stop E objetivo. Objetivo na Bybit (tp_n) ou, quando a
    Bybit recusou o anexo, o programa sabe que e ele a vender (partes com
    anexo False no exec.json). Devolve os avisos (um por posicao por dia)."""
    if not conta:
        return []
    ops = (ex or {}).get("ops") or {}
    vistos = state.setdefault("ordens_watch", {})
    out = []
    # (24/10) um short nao tem moedas na conta (tem divida): conta como posicao se a entrada foi vista
    pos = lambda t: bool(t.get("held") or t.get("fill_px"))
    for t in conta.get("trades") or []:
        if not pos(t):
            continue
        op = ops.get(t["id"]) or {}
        partes = op.get("partes") or []
        prog = op.get("status") == "aberta" and partes and all(not p.get("anexo") for p in partes)
        falta = []
        if not t.get("stop_found"):
            falta.append("stop")
        if not t.get("tp_n") and not prog:
            falta.append("objetivo")
        if not falta or (t["id"] in vistos and now - vistos[t["id"]] < 86400):
            continue
        vistos[t["id"]] = int(now)
        quem = ("o programa não tem registo desta operação" if not op else
                "a Bybit devia ter o objetivo anexado e não o encontro")
        out.append(f"🔎 <b>Verificação das ordens: {t['asset']}</b> sem {' nem '.join(falta)} na Bybit ({quem}). "
                   "Confirma na app (Ordens → TP/SL).")
    state["ordens_ok"] = {"t": int(now), "posicoes": sum(1 for t in conta.get("trades") or [] if pos(t)),
                          "avisos": len(out)}
    return out


def estudo_aviso(state, paper):
    """(22/10) Aviso quando um lutador em papel de estudo muda de estado pela
    regra fixada (aprovado: pede o OK do Rui / chumbado). Nao mexe em dinheiro."""
    from . import arena
    vis = state.setdefault("estudo_estado", {})
    out = []
    for k, v in (paper or {}).items():
        pv = v.get("prova") if isinstance(v, dict) else None
        if not pv:
            continue
        e, ant = pv.get("estado"), vis.get(k)
        vis[k] = e
        if ant is None or e == ant or e == "a medir":
            continue
        if e.startswith("aprovado"):
            out.append(f"🧪 <b>{arena.persona(k)} ({k})</b> passou a regra em papel na {pv['fase']}: {pv['n']} operações, "
                       f"{pv['r']:+.2f}R de média, metades {pv['metades']}. Só vai a dinheiro real com o teu OK.")
        else:
            out.append(f"🧪 <b>{arena.persona(k)} ({k})</b> chumbou em papel na {pv['fase']}: {pv['n']} operações, {pv['r']:+.2f}R de média. Sai do estudo.")
    return out


def campeoes_aviso(state, campeoes, now):
    """(21/10) Aviso quando um campeao sai do dinheiro real, com o motivo:
    clone de outro lutador, suspensao pelo resultado real ou mudanca de fase.
    Guarda a lista anterior em state["campeoes_ant"]. Devolve os avisos."""
    from . import promo, arena
    ant = state.get("campeoes_ant")
    atual = list(campeoes or [])
    state["campeoes_ant"] = atual
    if ant is None:
        return []
    lg = ((state.get("arena") or {}).get("longo") or {})
    cl, sus = lg.get("clones") or {}, promo.suspended(state, contas_mes=False)
    fase = (state.get("mercado") or {}).get("regime")
    out = []
    for k in ant:
        if k in atual:
            continue
        nome = arena.persona(k)
        if k in (state.get("so_papel") or {}):
            motivo = state["so_papel"][k] + "; continua a ser medido em papel"
        elif k in cl:
            de = cl[k]
            motivo = (f"é clone de {arena.persona(de['de'])} ({de['de']}, resultados diários correlacionados "
                      f"{de['corr']:.2f}); fica {arena.persona(de['de'])}")
        elif k in sus:
            motivo = sus[k]
        else:
            motivo = f"deixou de provar na fase atual ({fase or '–'}) no ringue de 1 ano"
        out.append(f"🔁 <b>Campeão saiu do dinheiro real: {nome} ({k})</b> — {motivo}. "
                   f"Agora operam: {', '.join(atual) or 'só o núcleo'}.")
    for k in atual:
        if k not in ant:
            out.append(f"🏆 <b>Novo campeão no dinheiro real: {arena.persona(k)} ({k})</b> — provou na fase {fase or '–'} no ringue de 1 ano.")
    return out


LONGO_HORA_UTC = 4                # a partir das 4h UTC (5h de Lisboa no inverno)


def longo_disparo(state, now, correr=None):
    """(22/10, OK do Rui) A agenda do GitHub tem lancado o ringue de 1 ano com
    5 a 6 horas de atraso. Se a partir das LONGO_HORA_UTC ainda nao houve ronda
    nesse dia (UTC), o scanner lanca-a uma vez (gh workflow run). Devolve True
    se lancou."""
    import subprocess, time as _t
    dia = int(now) // 86400
    feito = ((state.get("arena") or {}).get("longo") or {}).get("atualizado") or 0
    if int(feito) // 86400 >= dia or state.get("longo_disparo") == dia:
        return False
    if _t.gmtime(now).tm_hour < LONGO_HORA_UTC:
        return False
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not repo and correr is None:
        return False
    state["longo_disparo"] = dia
    if correr is None:                       # ja ha uma ronda a correr ou na fila: nao lanca outra
        for st_ in ("in_progress", "queued"):
            try:
                r = subprocess.run(["gh", "run", "list", "--repo", repo, "--workflow", "arena-longo.yml", "--status", st_,
                                    "-L", "1", "--json", "databaseId"], capture_output=True, text=True, timeout=30)
                if "databaseId" in (r.stdout or ""):
                    return False
            except Exception:
                pass
    cmd = ["gh", "workflow", "run", "arena-longo.yml", "--repo", repo or "", "--ref", "main"]
    try:
        (correr or (lambda c: subprocess.run(c, timeout=30, check=False)))(cmd)
        return True
    except Exception as e:
        print("longo_disparo:", e)
        return False


def key_alert(state, keys, now, dias=14):
    """Aviso quando uma chave da Bybit esta a menos de `dias` de expirar
    (Rui, 20/10). keys = {nome: expiredAt da Bybit}. Uma vez por dia por chave.
    Sem data (chave com IP fixo nao expira) = nada a avisar."""
    import datetime as _dt
    st = state.setdefault("chave_aviso", {})
    out = []
    for nome, exp in (keys or {}).items():
        if not exp:
            continue
        try:
            t = _dt.datetime.fromisoformat(str(exp).replace("Z", "+00:00")).timestamp()
        except ValueError:
            continue
        if t < 946684800:            # 1970-01-01 = a Bybit diz "sem validade" (chave com IP fixo)
            continue
        falta = (t - now) / 86400
        if falta > dias or now - (st.get(nome) or 0) < 86400:
            continue
        st[nome] = int(now)
        out.append(f"🔑 A chave {nome} da Bybit expira {'HOJE' if falta < 1 else f'daqui a {falta:.0f} dias'} "
                   f"({str(exp)[:10]}). Sem ela, " + ("o programa deixa de ler a conta (stops, resultado real)."
                   if nome == "de leitura" else "o programa deixa de executar operações.") +
                   " Renova-a na Bybit e atualiza o segredo no GitHub.")
    return out


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
        out += [x[0] for x in res]
    del done[:-200]
    if send:
        for txt in out:
            try:
                send("✍️ " + txt)
            except Exception:
                pass
    return out


def capital_warning(state, plan):
    """Aviso quando o USDC livre na Bybit nao chega para a margem da operacao."""
    cl = state.get("conta_livre") or {}
    free, need = cl.get("usdc"), plan.get("collateral_usdc") or plan.get("position_usdc")
    if free is None or not need or free >= need * 1.02:
        return None
    return (f"⚠️ Capital: tens {free:.2f} USDC livres e esta operação precisa de "
            f"{need:.2f} USDC de margem própria. Para a abrir tens de libertar capital "
            "(fechar ou reduzir uma operação) ou usar a margem da Bybit.")


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
        if e.get("auto") and e["event"] == "ISSUED":
            txt = ("🤖 EXECUTADO AUTOMATICAMENTE (modo automático): o programa está a abrir esta operação "
                   "na Bybit; confirmação em 1 a 2 minutos. /parar fecha tudo e desliga.\n\n" + txt)
        if (state.get("auto_ops") or {}).get(e.get("id")) == "aberta" and e["event"] in ("TP1", "BREAKEVEN") \
                and "r" not in e:
            # operacao executada pelo programa: ele proprio sobe o stop na Bybit
            txt = (f"🟢 TP1 — {s.get('asset', e.get('asset'))}: objetivo 1 atingido a {_px(e.get('price'))}. "
                   "O programa está a mover o stop para a entrada na Bybit (1 a 2 minutos): "
                   "não precisas de fazer nada. Recebes a confirmação a seguir.")
        real = s.get("mode") != "PAPER" and e.get("real", True)
        try:                                   # a missao em cada operacao (Rui, 2026-10-16)
            if real and e["event"] == "ISSUED" and s.get("plan"):
                txt += "\n" + mission_line(state, s["plan"])
            elif real and "r" in e and e["event"] in CLOSE_EVENTS:
                txt += "\n\n" + autopsy(state, e, s)
        except Exception as err:
            print("missao:", err)
        html_mode = False
        if real and e["event"] == "ISSUED" and s.get("plan"):
            txt = html.escape(txt) + "\n\n" + order_block(s)
            html_mode = True
            warn = capital_warning(state, s["plan"])
            if warn:
                txt += "\n\n" + html.escape(warn)
        try:
            alerts.send(txt, markup_for(e, s, real), html=html_mode)
        except alerts.AlertError as err:
            print("ALERTA FALHOU", err)


CLOSE_EVENTS = ("STOP", "BREAKEVEN", "TP1", "TP2", "TP3", "TIME", "NOREACT")


def _goal(state):
    from . import meta
    cap = state.get("capital") or config.load().get("capital_usdc")
    return meta.progress(None, cap) if cap else None


def mission_line(state, p):
    """Cada entrada lembra a missao: quanto arrisca, quanto pode ganhar e
    quanto falta para o objetivo. Multiplicar sem perder."""
    risk = p.get("risk_usdc")
    m = _goal(state)
    L = "🎯 Missão: multiplicar o capital sem o perder."
    if risk:
        L += f" Esta operação arrisca {risk:.2f} USDC (stop) para ganhar até {risk * (p.get('rr') or 0):.2f} USDC."
    if m:
        L += f" Objetivo da equipa: {m['marco']:,} USDC (faltam {m['falta_marco']:.2f}).".replace(",", " ")
    return L + " Lucro protegido no TP1."


def autopsy(state, e, s):
    """Licao de cada operacao fechada, tirada dos factos (sem desculpas)."""
    r, k, p = e.get("r") or 0.0, e["event"], s.get("plan") or {}
    usd = r * (p.get("risk_usdc") or 0)
    tp1 = int(s.get("tp_hit") or 0) >= 1 or k in ("BREAKEVEN", "TP1", "TP2", "TP3")
    if k in ("TP1", "TP2", "TP3"):
        lic = "Plano cumprido: objetivo atingido e lucro no bolso."
    elif k == "BREAKEVEN":
        lic = ("Chegou ao TP1 e voltou: o stop na entrada protegeu o capital. "
               "Não é perda; o lucro do TP1 fica quando a operação dá para dividir.")
    elif k == "STOP" and not tp1:
        lic = ("A entrada não confirmou e o stop cortou a perda como planeado (princípio 5). "
               "Perda pequena, capital protegido; o ringue e a prova real contam esta operação.")
    elif k == "STOP":
        lic = "Stop depois do TP1: a parte vendida no objetivo reduziu a perda."
    else:
        lic = "Sem reação no tempo previsto: saída disciplinada em vez de esperar e arriscar mais."
    m = _goal(state)
    falta = f" Faltam {m['falta_marco']:.2f} USDC para {m['marco']:,} USDC.".replace(",", " ") if m else ""
    return f"📓 Lição: {lic} Resultado {r:+.2f}R ({usd:+.2f} USDC).{falta}"


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


def exec_after(state, events, now):
    """Ganchos da execucao: TP1 / tempo / sem reacao em operacoes executadas
    pelo programa, e aviso ao ciclo para lancar o servidor europeu."""
    try:
        execucao.hooks(state, events, now)
        if execucao.due(state, now):
            open(os.path.join(OUT, ".exec"), "w").close()
            return True
    except Exception as e:                    # nunca para o scanner
        print("execucao:", e)
    return False


def load_longo():
    """Ringue longo (365 dias, por regime): ramo arena-longo. None se falhar."""
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not repo:
        return None
    import urllib.request
    try:
        url = f"https://raw.githubusercontent.com/{repo}/arena-longo/longo.json"
        with urllib.request.urlopen(url, timeout=15) as r:
            return json.loads(r.read().decode())
    except Exception:
        return None


def keep_longo(state, lg):
    """Guarda so o essencial do ringue longo: por lutador e por regime."""
    if not lg or not lg.get("lutadores"):
        return
    comp = {}
    for k, v in lg["lutadores"].items():
        comp[k] = {"n": v.get("n"), "avg_r": v.get("avg_r"),
                   "por_regime": {rg: {x: r.get(x) for x in ("n", "avg_r", "acaso_p95", "veredicto", "metades",
                                                             "qualidade", "passa_atual", "passa_novo", "acaso_pk")}
                                  for rg, r in (v.get("por_regime") or {}).items()},
                   "recentes": v.get("recentes") or []}
    state.setdefault("arena", {})["longo"] = {"atualizado": lg.get("atualizado"), "lutadores": comp,
                                              "clones": lg.get("clones") or {}, "acaso_filtro": lg.get("acaso_filtro") or {},
                                              "hipoteses": lg.get("hipoteses") or {}}


def main():
    os.makedirs(OUT, exist_ok=True)
    state = _load("state.json", {})
    ex_now = execucao.load()
    state["chave_negociacao_expira"] = (ex_now or {}).get("expira")
    execucao.apply(state, ex_now)
    try:
        keep_longo(state, load_longo())
    except Exception as e:
        print("ringue longo:", e)
    process_inbox(state, _load("scan.json", None))
    apply_admin(state, send=alerts.send if alerts.configured() else None)
    res, state, events = scanner.run(state=state, forma=load_forma(),
                                     eu=europa.load())
    try:                                      # modo automatico (desligado ate a prova estar feita)
        from . import auto
        auto.observe(state, None, events)
        auto.pick(state, events, res["generated_at"])
        res["auto"] = auto.summary(state)
        aviso = auto.pop_aviso(state)
        if aviso and alerts.configured():
            alerts.send(aviso)
        for txt in auto.pop_nao_entrou(state):
            if alerts.configured():
                alerts.send(txt, html=True)
    except Exception as e:
        print("auto:", e)
    try:
        for txt in key_alert(state, {"de leitura": (res.get("conta") or {}).get("expira"),
                                     "de negociação": state.get("chave_negociacao_expira")},
                             res["generated_at"]):
            if alerts.configured():
                alerts.send(txt)
    except Exception as e:
        print("chave:", e)
    try:
        for txt in stop_watch(state, res.get("conta"), res["generated_at"]):
            if alerts.configured():
                alerts.send(txt, html=True)
    except Exception as e:
        print("stop_watch:", e)
    try:                                     # (22/10) ringue de 1 ano sem esperar pela agenda do GitHub
        if longo_disparo(state, res["generated_at"]):
            print("ringue longo lançado pelo scanner")
    except Exception as e:
        print("longo_disparo:", e)
    try:                                     # (21/10) troca automatica do filtro (engine/troca.py)
        from . import troca
        troca.registar(state, res.get("filtro_novo"), (state.get("mercado") or {}).get("regime"), res["generated_at"])
        msg = troca.decidir(state, res["generated_at"])
        if msg and alerts.configured():
            alerts.send(msg, html=True)
        tf = state.get("troca_filtro") or {}
        res["troca_filtro"] = {"ativo": tf.get("ativo"), "desde": tf.get("desde"), "dias": len(tf.get("dias") or {}),
                               "medicao": tf.get("medicao"), "regra": {"min_dias": troca.MIN_DIAS, "min_ops": troca.MIN_OPS,
                                                                        "margem_r": troca.MARGEM_R}}
    except Exception as e:
        print("troca:", e)
    try:                                     # (21/10) aviso quando um campeao entra ou sai
        for txt in campeoes_aviso(state, (res.get("promo") or {}).get("campeoes"), res["generated_at"]):
            if alerts.configured():
                alerts.send(txt, html=True)
    except Exception as e:
        print("campeoes_aviso:", e)
    try:                                     # (22/10) estudo em papel (TURTLE_FORTES na subida)
        for txt in estudo_aviso(state, res.get("paper_ring")):
            if alerts.configured():
                alerts.send(txt, html=True)
    except Exception as e:
        print("estudo_aviso:", e)
    try:                                     # D1: verificacao diaria das ordens (stop e objetivo)
        for txt in ordens_watch(state, res.get("conta"), ex_now, res["generated_at"]):
            if alerts.configured():
                alerts.send(txt, html=True)
        res["ordens_ok"] = state.get("ordens_ok")
    except Exception as e:
        print("ordens_watch:", e)
    try:
        from . import amplitude
        am = amplitude.aviso(res.get("amplitude"))
        if am and alerts.configured():
            alerts.send(am, html=True)
    except Exception as e:
        print("amplitude:", e)
    try:                                     # historico diario da liquidez da Bybit UE
        from . import liquidez
        lq = liquidez.atualizar(_load("liquidez.json", {}), res.pop("liquidez_bybit", None), res["generated_at"])
        with open(os.path.join(OUT, "liquidez.json"), "w") as f:
            json.dump(lq, f, separators=(",", ":"))
    except Exception as e:
        print("liquidez:", e)
    try:
        from . import risco
        ra = risco.aviso(state.get("risco") or {})
        if ra and alerts.configured():
            alerts.send(ra)
    except Exception as e:
        print("risco:", e)
    try:
        fa = funding_alert(state, res.get("conta"), res["generated_at"])
        if fa and alerts.configured():
            alerts.send(fa, html=True)
    except Exception as e:
        print("fundo:", e)
    try:                                     # nucleo da carteira (engine/nucleo.py)
        from . import nucleo, promo
        conta = res.get("conta") or {}
        precos = {r["asset"]: ((r.get("venue") or {}).get("last") or r.get("price")) for r in res.get("universe") or []}
        cfg_n = dict(config.load(), **{k: v for k, v in (res.get("config") or {}).items() if k.startswith("nucleo")})
        for acao, op in nucleo.decidir(state, promo.DAILY or {}, precos, conta.get("equity") or (res.get("config") or {}).get("capital_usdc"),
                                       conta.get("usdc_free"), cfg_n, res["generated_at"]):
            execucao.request(state, acao, op, res["generated_at"])
        res["nucleo"] = nucleo.resumo(state)
    except Exception as e:
        print("nucleo:", e)
    try:                                     # pos-morte das operacoes reais (engine/posmortem.py)
        from . import posmortem
        rel = posmortem.relatorio(state.get("ledger"), ((state.get("arena") or {}).get("longo") or {}).get("lutadores"),
                                  (res.get("promo") or {}).get("campeoes") or ())
        res["posmortem"] = rel
        for m in posmortem.novos(state, rel):
            if alerts.configured():
                alerts.send(m, html=True)
        for m in posmortem.custo_aviso(state, rel, res["generated_at"]):   # (22/10) custo real por estrategia
            if alerts.configured():
                alerts.send(m, html=True)
    except Exception as e:
        print("posmortem:", e)
    try:                                     # historico de derivados (engine/derivhist.py)
        from . import derivhist
        dh = derivhist.atualizar(_load("derivados.json", {}), res.get("universe"), res["generated_at"])
        with open(os.path.join(OUT, "derivados.json"), "w") as f:
            json.dump(dh, f, separators=(",", ":"))
        res["derivados_hist"] = derivhist.resumo(dh)
    except Exception as e:
        print("derivados:", e)
    try:                                     # evolucao real da carteira (engine/evolucao.py)
        from . import evolucao
        c = res.get("conta") or {}
        if c.get("equity"):
            evolucao.atualizar(state, c["equity"], res["generated_at"], state.get("ledger"), res.get("nucleo"))
        res["evolucao"] = evolucao.resumo(state.get("evolucao"), c.get("equity"), res["generated_at"])
    except Exception as e:
        print("evolucao:", e)
    try:                                     # (23/10) caminho para a liberdade: resumo e mensagem de domingo
        from . import liberdade
        res["liberdade"] = liberdade.resumo((res.get("conta") or {}).get("equity") or (res.get("config") or {}).get("capital_usdc"),
                                            res.get("evolucao"), (res.get("config") or {}).get("liberdade"))
        txt = liberdade.semanal(state, res, res["generated_at"])
        if txt and alerts.configured():
            alerts.send(txt, html=True)
    except Exception as e:
        print("liberdade:", e)
    exec_after(state, events, res["generated_at"])
    res["execucao"] = {"pronto": execucao.READY, "pedidos": len(state.get("exec_req") or [])}
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
