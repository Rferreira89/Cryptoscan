"""Alert Engine: envio de mensagens por Telegram.

Credenciais so por variaveis de ambiente (secrets do GitHub). Nunca
aparecem no codigo nem nos logs.
"""
import json
import os
import sys
import urllib.parse
import urllib.request


class AlertError(Exception):
    pass


def configured():
    return bool(os.environ.get("TELEGRAM_BOT_TOKEN")
                and os.environ.get("TELEGRAM_CHAT_ID"))


def send(text):
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token:
        raise AlertError("falta o secret TELEGRAM_BOT_TOKEN")
    if not chat:
        raise AlertError("falta o secret TELEGRAM_CHAT_ID")
    body = urllib.parse.urlencode({"chat_id": chat, "text": text[:4000],
                                   "disable_web_page_preview": "true"}).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage", data=body)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            d = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        # 401 = token errado; 400 = chat id errado; 403 = falta carregar Iniciar
        try:
            desc = json.loads(e.read().decode()).get("description", "")
        except Exception:
            desc = ""
        raise AlertError(f"Telegram HTTP {e.code}: {desc}") from None
    except Exception as e:
        raise AlertError(f"Telegram: {type(e).__name__}") from None
    if not d.get("ok"):
        raise AlertError(f"Telegram: {d.get('description')}")


if __name__ == "__main__":
    try:
        send(sys.argv[1] if len(sys.argv) > 1 else "Teste")
        print("ALERTA ENVIADO")
    except AlertError as e:
        print("ERRO", e)
        sys.exit(1)
