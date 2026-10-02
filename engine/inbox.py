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
            out.append((f"Registado: entrada em {asset} a {px:g}.", None))
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
