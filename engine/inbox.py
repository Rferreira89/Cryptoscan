"""Respostas do utilizador no Telegram: confirmacao de execucoes.

Botoes em cada alerta de compra:  executei / nao executei.
Comando de texto:  /preco LINK 14.25   (preco real de entrada)
So sao aceites mensagens do chat configurado em TELEGRAM_CHAT_ID.
"""
import json
import os
import re
import urllib.parse
import urllib.request

CMD = re.compile(r"^/?pre[cç]o\s+([A-Za-z0-9]+)\s+([0-9]+(?:[.,][0-9]+)?)\s*$",
                 re.I)


CAP = re.compile(r"^/?capital\s+([0-9]+(?:[.,][0-9]+)?)\s*$", re.I)


SLIP_WARN_PCT = 0.3        # entrada pior do que isto face ao sinal: avisar


def _fee_pct():
    try:
        from . import config
        return config.load()["fee_pct"]
    except Exception:
        return 0.25


def slip_note(rec, px, fee_pct=None):
    """Se a entrada real for pior do que o sinal, diz quanto se perde de
    facto no stop (com a mesma quantidade) e quanto vender para voltar a
    perda planeada. Texto vazio quando a diferenca e pequena."""
    fee = (_fee_pct() if fee_pct is None else fee_pct) / 100
    long = rec.get("side", "LONG") != "SHORT"
    zone = rec.get("entry_zone") or [None, None]
    ref = rec.get("entry") or (zone[1] if long else zone[0])
    stop, usdc = rec.get("stop"), rec.get("position_usdc")
    if not (ref and stop and usdc and px > 0):
        return ""
    if (px <= stop) if long else (px >= stop):
        return (f" Atenção: com entrada a {px:g} o stop ({stop:g}) já ficou "
                "do lado errado do preço. Fecha a posição ou confirma o stop.")
    worse = (px / ref - 1) * 100 * (1 if long else -1)
    if worse <= SLIP_WARN_PCT:
        return ""
    qty = usdc / ref
    unit = (px - stop if long else stop - px) + fee * (px + stop)
    plan_unit = (ref - stop if long else stop - ref) + fee * (ref + stop)
    if plan_unit <= 0:
        return ""
    plan_risk = qty * plan_unit                 # perda no stop prevista no sinal
    real = qty * unit
    keep = plan_risk / unit
    cut = qty - keep
    side = "vender" if long else "recomprar"
    return (f" Atenção: entraste {worse:.2f}% {'acima' if long else 'abaixo'} "
            f"do sinal. Com a quantidade do sinal ({qty:.4g}), o stop custa "
            f"cerca de {real:.2f} USDC em vez de {plan_risk:.2f}. Para voltar "
            f"à perda planeada, {side} {cut:.4g} agora e mantém o stop em "
            f"{stop:g}.")


def buttons(op_id):
    return {"inline_keyboard": [[
        {"text": "✅ Executei", "callback_data": f"x|1|{op_id}"},
        {"text": "❌ Não executei", "callback_data": f"x|0|{op_id}"}]]}


def _api(method, params):
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    body = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/{method}", data=body)
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode())


def fetch(state):
    """Novas mensagens desde a ultima leitura. Falha de rede -> []."""
    if not os.environ.get("TELEGRAM_BOT_TOKEN"):
        return []
    try:
        d = _api("getUpdates", {"offset": state.get("tg_offset", 0),
                                "timeout": 0,
                                "allowed_updates": '["message","callback_query"]'})
    except Exception:
        return []
    ups = d.get("result", []) if d.get("ok") else []
    if ups:
        state["tg_offset"] = ups[-1]["update_id"] + 1
    return ups


def apply(state, updates, chat_id):
    """Aplica as respostas ao registo. Devolve [(texto, callback_id)]."""
    led = state.get("ledger", [])
    by_id = {r["id"]: r for r in led}
    out = []
    for u in updates:
        cq, msg = u.get("callback_query"), u.get("message")
        if cq:
            if str(cq.get("message", {}).get("chat", {}).get("id")) != str(chat_id):
                continue
            parts = (cq.get("data") or "").split("|", 2)
            rec = by_id.get(parts[2]) if len(parts) == 3 and parts[0] == "x" else None
            if not rec:
                out.append(("Operação não encontrada no registo.", cq["id"]))
                continue
            rec["executed"] = parts[1] == "1"
            if rec["executed"]:
                out.append((f"Registado: executaste {rec['asset']}. Se o preço "
                            f"foi diferente do sinal, envia: /preco "
                            f"{rec['asset']} <preço>", cq["id"]))
            else:
                out.append((f"Registado: não executaste {rec['asset']}. Não "
                            "recebes mais avisos desta operação.", cq["id"]))
        elif msg:
            if str(msg.get("chat", {}).get("id")) != str(chat_id):
                continue
            text = (msg.get("text") or "").strip()
            c = CAP.match(text)
            if c:
                val = float(c.group(1).replace(",", "."))
                if 5 <= val <= 1_000_000:
                    state["capital"] = val
                    # ponto de partida do capital composto: so contam os
                    # resultados fechados a partir de agora
                    state["capital_t"] = int(msg.get("date") or 0)
                    out.append((f"Capital de trading atualizado para {val:g} "
                                "USDC. Aplica-se aos próximos sinais.", None))
                else:
                    out.append(("Valor de capital fora dos limites.", None))
                continue
            m = CMD.match(text)
            if not m:
                continue
            asset, px = m.group(1).upper(), float(m.group(2).replace(",", "."))
            rec = next((r for r in reversed(led) if r["asset"] == asset
                        and r["status"] in ("WAITING", "OPEN")), None)
            if not rec or px <= 0:
                out.append((f"Não encontrei operação em curso para {asset}.", None))
                continue
            rec.update(executed=True, exec_price=px)
            out.append((f"Registado: entrada em {asset} a {px:g}."
                        + slip_note(rec, px), None))
    return out


def reply(items, send):
    for text, cb in items:
        try:
            if cb:
                _api("answerCallbackQuery", {"callback_query_id": cb})
            send(text)
        except Exception:
            pass


def muted(state, event):
    """True se o evento pertence a uma operacao marcada como nao executada."""
    led = state.get("ledger", [])
    k = event["event"]
    if k == "PAPER_SELL":
        rec = next((r for r in reversed(led) if r["kind"] == "1D"
                    and r["asset"] == event.get("asset")), None)
    else:
        rec = next((r for r in led if r["id"] == event.get("id")), None)
    return bool(rec) and rec.get("executed") is False and \
        k not in ("ISSUED", "PAPER_BUY")
