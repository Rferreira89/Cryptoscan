"""Modo automatico (fase 3, decisao do Rui em 2026-10-16): construido mas
DESLIGADO ate a prova estar feita.

Liga-se so quando TODOS os criterios estiverem cumpridos E o Rui disser
"/auto ligar" no Telegram:
  1. 20 operacoes executadas pelo botao sem nenhuma falha de execucao;
  2. resultado real positivo dos campeoes nessas operacoes;
  3. o travao disparou e funcionou pelo menos uma vez;
  4. o stop subiu para a entrada sozinho (TP1) pelo menos uma vez;
  5. o OK do Rui.

Ligado, tem limites:
  - so compras de campeoes autorizadas pelo Diretor (vendas a descoberto
    continuam com o toque do Rui nas primeiras duas semanas);
  - no maximo MAX_DIA operacoes automaticas por dia;
  - o travao, o risco e todas as regras de sempre;
  - cada operacao automatica e avisada no Telegram;
  - /parar fecha tudo E desliga o modo automatico.
A chave da Bybit so negoceia: nao pode levantar nem transferir.
"""
MIN_OPS = 20
MAX_DIA = 2
SHORT_APOS_S = 14 * 86400        # vendas a descoberto automaticas so 2 semanas depois de ligar


def _st(state):
    return state.setdefault("auto", {"ligado": False, "prova": {}})


def observe(state, ex=None, events=()):
    """Atualiza a prova com o que aconteceu: operacoes do botao (com ou sem
    falha), breakeven feito pela Bybit, travao disparado."""
    a = _st(state)
    pv = a.setdefault("prova", {})
    ops = pv.setdefault("ops", {})
    for k, o in ((ex or {}).get("ops") or {}).items():
        if o.get("status") not in ("aberta", "fechada") or not o.get("entrada"):
            continue
        falha = bool(o.get("erro") or o.get("stop_erro") or
                     any(p.get("stop_erro") for p in o.get("partes") or []))
        ops[k] = {"falha": falha or bool((ops.get(k) or {}).get("falha"))}
    for x in (ex or {}).get("log") or []:
        if x.get("acao") == "breakeven" and str(x.get("res")).startswith(("ok", "stop já")):
            pv["breakeven"] = True
    for e in events or ():
        if e.get("event") == "HALT":
            pv["travao"] = True


def criteria(state):
    """[(nome, cumprido, detalhe)] dos criterios para ligar."""
    pv = _st(state).get("prova") or {}
    ops = pv.get("ops") or {}
    ok_ops = sum(1 for v in ops.values() if not v.get("falha"))
    falhas = sum(1 for v in ops.values() if v.get("falha"))
    rs = [r["user_result_r"] if r.get("user_result_r") is not None else r.get("result_r")
          for r in state.get("ledger") or []
          if r.get("auto_exec") and r.get("status") == "CLOSED"]
    rs = [x for x in rs if x is not None]
    tot = round(sum(rs), 2)
    return [("execuções sem falha", ok_ops >= MIN_OPS and not falhas,
             f"{ok_ops}/{MIN_OPS}" + (f", {falhas} com falha" if falhas else "")),
            ("resultado real positivo", bool(rs) and tot > 0, f"{tot:+.2f}R em {len(rs)} fechadas"),
            ("travão provado", bool(pv.get("travao")), "já disparou" if pv.get("travao") else "ainda não disparou"),
            ("stop na entrada provado", bool(pv.get("breakeven")),
             "já feito pela Bybit" if pv.get("breakeven") else "ainda não aconteceu")]


def ready(state):
    return all(c[1] for c in criteria(state))


def active(state):
    return bool(_st(state).get("ligado")) and ready(state)


def turn(state, on, now):
    """Liga (so com os criterios cumpridos) ou desliga. Devolve o texto."""
    a = _st(state)
    if not on:
        was = a.get("ligado")
        a.update(ligado=False, desligado=int(now))
        return "🤖 Modo automático desligado." if was else "🤖 O modo automático já estava desligado."
    falta = [f"{n} ({d})" for n, ok, d in criteria(state) if not ok]
    if falta:
        return "🤖 Ainda não posso ligar o modo automático. Falta: " + "; ".join(falta) + "."
    a.update(ligado=True, ligado_t=int(now))
    return ("🤖 Modo automático LIGADO. Só compras de campeões autorizadas pelo Diretor, no máximo "
            f"{MAX_DIA} por dia, com o risco e o travão de sempre. /parar fecha tudo e desliga.")


def pick(state, events, now):
    """Pede a execucao automatica dos sinais elegiveis. Devolve os ids."""
    if not active(state):
        return []
    from . import execucao
    a = _st(state)
    hoje = [t for t in a.get("feitos") or [] if now - t < 86400]
    out = []
    sigs = state.get("signals") or {}
    for e in events:
        if e.get("event") != "ISSUED" or len(hoje) >= MAX_DIA:
            continue
        s = sigs.get(e["id"]) or e.get("signal") or {}
        short = s.get("direction") == "SHORT" or (s.get("plan") or {}).get("side") == "SHORT"
        if s.get("mode") == "PAPER" or (s.get("diretor") or {}).get("decisao") != "AUTORIZADO":
            continue
        if s.get("score_label") != "campeão da arena":
            continue
        if short and (now - (a.get("ligado_t") or now) < SHORT_APOS_S or not execucao.READY_SHORT):
            continue
        if not short and not execucao.READY:
            continue
        if execucao.request(state, "vender" if short else "comprar", e["id"], now):
            hoje.append(now)
            out.append(e["id"])
            e["auto"] = True
    a["feitos"] = hoje
    return out


def text(state):
    a = _st(state)
    L = [f"🤖 <b>Modo automático: {'LIGADO' if active(state) else 'desligado'}</b>", "",
         "Critérios para ligar (todos):"]
    for n, ok, d in criteria(state):
        L.append(f"{'✅' if ok else '⬜'} {n}: {d}")
    L.append(f"{'✅' if a.get('ligado') else '⬜'} o teu OK (/auto ligar)")
    L += ["", f"Ligado: só compras de campeões autorizadas pelo Diretor, máximo {MAX_DIA} por dia, risco e "
          "travão de sempre; vendas a descoberto automáticas só 2 semanas depois. A chave não pode "
          "levantar nem transferir. /auto desligar ou /parar desligam."]
    return "\n".join(L)


def summary(state):
    return {"ligado": active(state), "pedido": bool(_st(state).get("ligado")),
            "criterios": [{"nome": n, "ok": ok, "detalhe": d} for n, ok, d in criteria(state)]}
