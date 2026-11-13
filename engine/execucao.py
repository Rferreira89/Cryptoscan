"""Lado do scanner da execucao com um toque (engine/executor.py corre na
Europa). Aqui: pedidos do Telegram, ganchos do acompanhamento (volta a
entrada depois do TP1, tempo, sem reacao -> fechar) e leitura do resultado
(exec.json no ramo "execucoes") para marcar o registo."""
import json
import os
import time

READY = False                   # a chave de negociacao foi validada na Europa
READY_SHORT = False             # e o teste real da venda a descoberto passou
RETRY_S = 300


def load():
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not repo:
        return None
    import urllib.request
    try:
        url = f"https://raw.githubusercontent.com/{repo}/execucoes/exec.json?t={int(time.time())}"
        with urllib.request.urlopen(url, timeout=10) as r:
            d = json.loads(r.read().decode())
        from . import cifra                  # (28/10) exec.json cifrado no repositorio publico
        return cifra.abrir_obj(d)
    except Exception:
        return None


def apply(state, ex):
    """Marca no registo as compras feitas pela Europa e limpa a fila."""
    global READY, READY_SHORT
    if not ex:
        READY = bool(state.get("exec_ready"))
        READY_SHORT = bool(state.get("exec_ready_short"))
        return
    # (23/10, SEI) um pedido de compra/venda que acabou em erro da Bybit sem registo da operacao
    # (ex.: IOC sem execucao) conta como recusado: nao ocupa a familia, a moeda nem o limite do dia.
    # "erro inesperado" fica de fora: ai pode ter havido execucao e a app tem de ser confirmada.
    ops = ex.setdefault("ops", {})
    for x in ex.get("log") or []:
        acao, res = x.get("acao"), str(x.get("res") or "")
        if acao in ("comprar", "vender", "panico_ordem") and res.startswith("erro: "):
            op = str(x.get("id") or "")[len(acao) + 1:].rsplit("-", 1)[0]
            if op and op not in ops:
                ops[op] = {"asset": op.split("-")[0], "status": "recusada", "motivo": res[6:], "t": x.get("t"),
                           "sintetico": True}
    # botao so depois do teste real de 5 USDC ter passado (decisao do Rui)
    passos = (ex.get("teste") or {}).get("passos") or []
    teste_ok = bool(passos) and not any("ERRO" in p for p in passos) and \
        any(p.startswith("venda") for p in passos)
    READY = bool(ex.get("pronto")) and teste_ok
    state["exec_ready"] = READY
    # vendas a descoberto: so depois do teste real (vender, recomprar e devolver) passar
    ps = (ex.get("teste_short") or {}).get("passos") or []
    # e, se a protecao veio anexada, ela tem de ter sido encontrada e cancelada
    # (15/10: o primeiro teste nao a encontrava e deixou-a aberta)
    anexada = any("(anexo: sim)" in p for p in ps)
    READY_SHORT = READY and bool(ps) and not any("ERRO" in p for p in ps) and \
        any(p.startswith("recompra") for p in ps) and \
        (not anexada or any(p.startswith("cancelar proteção") for p in ps))
    state["exec_ready_short"] = READY_SHORT
    try:                                     # prova do modo automatico (engine/auto.py)
        from . import auto
        auto.observe(state, ex)
    except Exception as e:
        print("auto:", e)
    try:                                     # nucleo da carteira (engine/nucleo.py)
        from . import nucleo
        nucleo.sync(state, ex)
    except Exception as e:
        print("nucleo:", e)
    done = set(ex.get("feitos") or [])
    state["exec_req"] = [r for r in state.get("exec_req") or [] if r["id"] not in done]
    led = {r["id"]: r for r in state.get("ledger") or []}
    auto = state.setdefault("auto_ops", {})
    pend = state.setdefault("auto_be", {})
    import time as _t
    now = max(int(_t.time()), int(ex.get("t") or 0))   # hora atual (o "t" do ficheiro e o da ultima corrida)
    rl = (state.get("papel_panico") or {}).get("real") or {}
    for k, o in (ex.get("ops") or {}).items():
        auto[k] = o.get("status")
        if k in rl and isinstance(o, dict):         # (31/10) compra no panico real: dados para o fecho e a analise
            rl[k]["exec"] = {c: o.get(c) for c in ("entrada", "stop", "alvo", "saida", "status", "criado", "fechado",
                                                   "motivo", "alavancagem", "sair_em", "lim") if o.get(c) is not None}
        rec = led.get(k)
        # (23/10) ordem recusada pela Bybit (ICP, 22/10: moeda sem margem): nada entrou, por isso a
        # operacao deixa de contar como aberta (vaga, familia e moeda); continua seguida em papel
        if rec and o.get("status") == "recusada" and rec.get("executed") is None and not o.get("entrada"):
            rec.update(executed=False, recusada=str(o.get("motivo") or o.get("erro") or "recusada pela Bybit")[:140])
        state.setdefault("auto_be_flag", {})[k] = bool(o.get("be_pendente")) and o.get("status") == "aberta"
        if o.get("status") == "aberta":
            # TP1 do sinal sem venda na Bybit: volta a pedir de 15 em 15 minutos (20/10)
            if o.get("be_pendente"):
                if now - (pend.get(k) or 0) >= 900:
                    pend[k] = now
                    request(state, "breakeven", k, now)
            # o sinal ja fechou (stop, tempo...) e a operacao continua "aberta" no
            # registo da Europa (a PUMP de 18/10): o fecho limpa as ordens e o estado
            elif rec and rec.get("status") in ("CLOSED", "CANCELLED") and now - (pend.get("f" + k) or 0) >= 900:
                pend["f" + k] = now
                request(state, "fechar", k, now)
        else:
            pend.pop(k, None)
            pend.pop("f" + k, None)
        if rec and o.get("status") in ("aberta", "fechada") and o.get("entrada"):
            if not rec.get("auto_exec"):
                rec.update(executed=True, exec_price=round(o["entrada"], 10), auto_exec=True)
            if o.get("status") == "fechada" and o.get("saida") and rec.get("user_result_r") is None:
                from . import ledger
                sig = (state.get("signals") or {}).get(k) or {}
                parts = rec.get("partials") or (sig.get("plan") or {}).get("partials")
                try:
                    from .inbox import _fee_pct
                    rec.update(user_exit=o["saida"], user_closed_at=o.get("fechado"),
                               user_result_r=ledger.user_close_r(rec, o["saida"], parts, _fee_pct()))
                except Exception:
                    pass
    try:                                     # (13/11, A3) estados das ordens; recusadas sem execucao saem de OPEN
        reconciliar_ordens(state, ex, now)
    except Exception as e:
        print("reconciliar ordens:", e)


ESTADOS_ORDEM = ("SINAL", "ORDEM_ENVIADA", "EXECUTADA", "RECUSADA", "FALHOU", "EXPIRADA", "CANCELADA")


def estado_ordem(rec, op, pedidos):
    """(13/11, A3) Estado inequivoco da ordem de uma operacao REAL, so a partir de factos: o registo do executor
    (op) e os pedidos ainda por executar. Nunca deduz uma execucao que o executor nao confirmou."""
    if op:
        st = op.get("status")
        if st in ("aberta", "fechada") and op.get("entrada"):
            return "EXECUTADA"
        if st in ("pendente", "verificar"):
            return "ORDEM_ENVIADA"
        if st == "cancelada" and not op.get("entrada"):
            return "CANCELADA"
        if st == "recusada" and not op.get("entrada"):
            txt = f"{op.get('motivo') or ''} {op.get('erro') or ''}".lower()
            return "FALHOU" if ("inesperado" in txt or "falhou" in txt and "bybit" not in txt) else "RECUSADA"
    if rec.get("executed") is True:
        return "EXECUTADA"
    if rec.get("executed") is False and rec.get("recusada"):
        return "RECUSADA"
    if rec.get("id") in pedidos:
        return "ORDEM_ENVIADA"
    if rec.get("status") == "CANCELLED":
        return "EXPIRADA"
    return "SINAL"


def reconciliar_ordens(state, ex, now):
    """(13/11, A3) Marca estado_ordem em todas as operacoes REAIS e tira de OPEN as que a corretora recusou ou que
    falharam SEM nenhuma execucao (BNB de 12/11): passam a CANCELLED com o motivo, o sinal deixa de ser seguido como
    se tivesse entrado e o resultado contrafactual passa para a sombra das rejeitadas (filtro "execução").
    So mexe em registos com executed=False e sem preco de execucao: nunca fecha nem altera uma posicao real."""
    ops = (ex or {}).get("ops") or {}
    pedidos = {r.get("op") for r in state.get("exec_req") or []} | {r.get("id") for r in state.get("exec_req") or []}
    sigs = state.get("signals") or {}
    feitas = []
    for rec in state.get("ledger") or []:
        if rec.get("mode") != "REAL":
            continue
        op = ops.get(rec.get("id")) if isinstance(ops.get(rec.get("id")), dict) else None
        e = estado_ordem(rec, op, pedidos)
        rec["estado_ordem"] = e
        if e in ("RECUSADA", "FALHOU") and rec.get("executed") is False and not rec.get("exec_price") \
                and not (op or {}).get("entrada") and rec.get("status") in ("WAITING", "OPEN", "ACTIVE", "TRIGGERED"):
            motivo = rec.get("recusada") or (op or {}).get("motivo") or "recusada pela Bybit"
            rec.update(status="CANCELLED", closed_at=int(now), reason="NAO_EXECUTADA")
            s = sigs.get(rec["id"])
            if s and s.get("status") in ("ACTIVE", "TRIGGERED"):
                s.update(status="CANCELLED", closed_at=int(now), close_reason="ordem não executada: " + str(motivo)[:100])
            try:
                from . import sombra_rejeitadas
                pl = (s or {}).get("plan") or {}
                t_sig = int((rec.get("issued_at") or now) // 14400 * 14400)
                sig = {"side": rec.get("side") or "LONG", "stop": rec.get("stop"), "tp": rec.get("tp"),
                       "partials": rec.get("partials") or pl.get("partials"), "t_sig": t_sig,
                       "hold_s": pl.get("max_hold_s"), "breakeven": pl.get("breakeven", True)}
                px = rec.get("entry") or (sum(rec["entry_zone"]) / 2 if rec.get("entry_zone") else None)
                sombra_rejeitadas.registar(state, rec.get("opened_at") or rec.get("issued_at") or now, rec["asset"],
                                           rec.get("strategy"), f"execução: {str(motivo)[:120]}", sig, px,
                                           {"risk_pct": rec.get("risk_pct"), "position_pct": rec.get("position_pct")})
            except Exception as er:
                print("sombra execucao:", er)
            feitas.append(rec["id"])
    return feitas


def abertas(ex):
    """(24/10, Rui: "o lucro nao aparece na corretora") Operacoes reais abertas na Bybit, com o
    lado, a quantidade e a entrada, para a app mostrar o resultado ao vivo ao preco de fecho."""
    out = []
    for oid, o in ((ex or {}).get("ops") or {}).items():
        if not isinstance(o, dict) or o.get("status") != "aberta" or not o.get("entrada") or not o.get("qty"):
            continue
        tps = [p.get("tp") for p in o.get("partes") or [] if p.get("tp")]
        out.append({"id": oid, "asset": o.get("asset"), "lado": o.get("lado") or "LONG",
                    "entrada": o["entrada"], "qty": o["qty"], "usdc": o.get("usdc"),
                    "stop": o.get("stop"), "tp": tps[0] if tps else None, "desde": o.get("t") or o.get("criado")})
    return out


# (05/11, S2, OK do Rui: fail-closed) acoes que abrem posicao: so com o saldo real da conta confirmado nesta volta
ENTRADAS = {"comprar", "vender", "nucleo_comprar", "nucleo_reforcar", "panico_comprar", "panico_ordem", "panico_refazer"}


def sem_capital(state):
    """True se nesta volta nao ha saldo real confirmado da Bybit (leitura fresca do servidor europeu)."""
    return not state.get("capital_confirmado")


def request(state, acao, op, now):
    if acao in ENTRADAS and sem_capital(state):
        b = state.setdefault("entradas_bloqueadas", [])
        b.append({"t": int(now), "acao": acao, "op": str(op)[-40:], "motivo": "sem saldo real confirmado"})
        del b[:-50]
        return None                                   # nunca abre com capital de reserva; fechos e saidas passam sempre
    q = state.setdefault("exec_req", [])
    if any(r["acao"] == acao and r.get("op") == op for r in q):
        return None
    r = {"id": f"{acao}-{op[-40:]}-{int(now)}", "acao": acao, "op": op, "t": int(now)}
    q.append(r)
    return r


def hooks(state, events, now):
    """Eventos do acompanhamento sobre operacoes executadas pelo programa."""
    auto = state.get("auto_ops") or {}
    for e in events:
        if auto.get(e.get("id")) != "aberta":
            continue
        # A Bybit UE nao deixa alterar a protecao anexada (TP + stop numa so
        # ordem, provado a 2026-10-13). O stop original fica sempre na Bybit
        # como rede de seguranca; o "stop na entrada" depois do TP1 (e o stop
        # que sobe da Tania) e feito pelo programa: quando o acompanhamento ve
        # o preco voltar a entrada, vende o resto. Idem tempo / sem reacao.
        if e["event"] == "BREAKEVEN" and (state.get("auto_be_flag") or {}).get(e["id"]):
            continue                          # o TP1 ainda nao vendeu na Bybit: ficam as ordens da Bybit
        if e["event"] in ("BREAKEVEN", "NOREACT", "TIME"):
            request(state, "fechar", e["id"], now)
        # objetivo final atingido: se a Bybit nao aceitou o TP anexado (15/10,
        # ENA), e o programa que vende. Se o TP anexado ja vendeu, o fecho so
        # cancela o stop e nao vende nada (le o saldo antes).
        elif e["event"] in ("TP1", "TP2", "TP3") and "r" in e:
            request(state, "fechar", e["id"], now)
        # TP1 sem ser o fim: o stop sobe para a entrada na propria Bybit
        elif e["event"] == "TP1":
            request(state, "breakeven", e["id"], now)


def due(state, now):
    """True se ha pedidos por enviar a Europa (ou a repetir)."""
    out = False
    for r in state.get("exec_req") or []:
        if now - (r.get("enviado") or 0) >= RETRY_S:
            r["enviado"] = int(now)
            out = True
    return out


def button(op_id):
    return {"text": "⚡ Executar", "callback_data": f"e|{op_id}"[:64]}
