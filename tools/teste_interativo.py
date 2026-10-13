"""Teste real das funcoes interativas (corre no GitHub, nunca no scan).

  velas <dir>            (servidor europeu) pede as velas como a pagina faz,
                         com Origin do GitHub Pages: estado, CORS e numero de
                         velas; guarda as velas reais da SOL; versao da pagina
  telegram <scan> <state> envia ao Telegram as respostas reais dos comandos
                         e um alerta de teste com os botoes Porque e Grafico
"""
import json
import os
import re
import sys
import time
import urllib.request

ORIGIN = "https://rferreira89.github.io"
PAGE = ORIGIN + "/Cryptoscan/scanner/"


def get(url):
    req = urllib.request.Request(url, headers={"Origin": ORIGIN, "User-Agent": "Mozilla/5.0 (iPhone) cryptoscan-teste"})
    t = time.time()
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, dict(r.headers), r.read().decode(), round((time.time() - t) * 1000)
    except Exception as e:
        return getattr(e, "code", None), dict(getattr(e, "headers", {}) or {}), str(e)[:200], None


def velas(dest):
    os.makedirs(dest, exist_ok=True)
    now = int(time.time())
    t0, out = now - 120 * 14400, {"t": now, "testes": {}}
    for a in ("SOL", "ETH", "PENGU"):
        u = (f"https://api.bybit.eu/v5/market/kline?category=spot&interval=240&limit=200"
             f"&start={t0 * 1000}&end={now * 1000}&symbol={a}USDC")
        st, h, body, ms = get(u)
        n = None
        try:
            j = json.loads(body)
            n = len(j["result"]["list"]) if j.get("retCode") == 0 else None
            if a == "SOL" and n:
                open(os.path.join(dest, "velas_SOL.json"), "w").write(body)
        except Exception:
            pass
        out["testes"][f"bybit_eu_{a}"] = {"http": st, "ms": ms, "velas": n,
                                          "cors": h.get("Access-Control-Allow-Origin") or h.get("access-control-allow-origin")}
        u2 = (f"https://data-api.binance.vision/api/v3/klines?interval=4h&limit=200"
              f"&startTime={t0 * 1000}&endTime={now * 1000}&symbol={a}USDT")
        st, h, body, ms = get(u2)
        try:
            n2 = len(json.loads(body))
        except Exception:
            n2 = None
        out["testes"][f"binance_{a}"] = {"http": st, "ms": ms, "velas": n2,
                                         "cors": h.get("Access-Control-Allow-Origin") or h.get("access-control-allow-origin")}
    st, _, body, _ = get(PAGE + "?t=" + str(now))
    m = re.search(r'PAGE_V="(\w+)"', body or "")
    out["pagina"] = {"http": st, "versao": m.group(1) if m else None,
                     "explorador": "s-explorar" in (body or ""), "cartao": "fcard" in (body or "")}
    json.dump(out, open(os.path.join(dest, "teste.json"), "w"), indent=1)
    print(json.dumps(out, indent=1))


def telegram(scan_path, state_path):
    from engine import alerts, consultas
    res = json.load(open(scan_path))
    state = json.load(open(state_path)) if os.path.exists(state_path) else {}
    log = []
    alerts.send("🧪 Teste das perguntas ao Cryptoscan: seguem as respostas reais de "
                "/porque SOL, /ringue, /macro, /conta e /hoje.")
    for cmd in ("/porque SOL", "/ringue", "/macro", "/conta", "/hoje"):
        try:
            alerts.send(consultas.answer(cmd, res, state), html=True)
            log.append(f"{cmd}: enviado")
        except Exception as e:
            log.append(f"{cmd}: ERRO {e}")
    try:
        alerts.send("🧪 Teste dos botões dos alertas. Toca em ❓ Porquê (o programa responde "
                    "em cerca de 1 minuto) e em 📊 Gráfico (abre o explorador na SOL).",
                    markup={"inline_keyboard": [consultas.why_buttons("SOL")]})
        log.append("botoes: enviado")
    except Exception as e:
        log.append(f"botoes: ERRO {e}")
    print("\n".join(log))
    if any("ERRO" in x for x in log):
        sys.exit(1)


if __name__ == "__main__":
    {"velas": velas, "telegram": telegram}[sys.argv[1]](*sys.argv[2:])
