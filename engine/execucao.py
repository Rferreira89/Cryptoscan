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
            return json.loads(r.read().decode())
    except Exception:
        return None


def apply(state, ex):
    """Marca no registo as compras feitas pela Europa e limpa a fila."""
    global READY, READY_SHORT
    if not ex:
        READY = bool(state.get("exec_ready"))
        READY_SHORT = bool(state.get("exec_ready_short"))
        return
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
    for k, o in (ex.get("ops") or {}).items():
        auto[k] = o.get("status")
        rec = led.get(k)
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


def request(state, acao, op, now):
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
