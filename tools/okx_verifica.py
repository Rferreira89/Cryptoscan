"""(04/11) Verificacao da chave da OKX (so leitura). Corre no servidor europeu (IP autorizado na chave).
Repositorio PUBLICO: o log so mostra estado e permissoes, nunca valores. Os saldos vao so para o Telegram."""
import base64, datetime, hashlib, hmac, json, os, sys, urllib.request, urllib.error

K, S, P = (os.environ.get(v, "").strip() for v in ("OKX_API_KEY", "OKX_API_SECRET", "OKX_PASSPHRASE"))
BASES = ("https://eea.okx.com", "https://my.okx.com", "https://www.okx.com")   # a conta do Rui e da OKX EEA

# (04/11) o servidor europeu tem IPv6 e a OKX via o IPv6 (fora da lista da chave): forcar IPv4 (2.28.62.236)
import socket as _socket
_gai = _socket.getaddrinfo
_socket.getaddrinfo = lambda host, port, family=0, *a, **k: _gai(host, port, _socket.AF_INET, *a, **k)


def pedido(base, path):
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + \
        f"{datetime.datetime.now(datetime.timezone.utc).microsecond // 1000:03d}Z"
    sig = base64.b64encode(hmac.new(S.encode(), (ts + "GET" + path).encode(), hashlib.sha256).digest()).decode()
    req = urllib.request.Request(base + path, headers={"OK-ACCESS-KEY": K, "OK-ACCESS-SIGN": sig, "OK-ACCESS-TIMESTAMP": ts,
                                                       "OK-ACCESS-PASSPHRASE": P, "Content-Type": "application/json",
                                                       "User-Agent": "cryptoscan/1.0", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        corpo = e.read()
        try:
            return json.loads(corpo)
        except Exception:
            import re as _re
            t_ = corpo.decode("utf-8", "replace")
            m_ = _re.search(r"(Error\s*\d{3,4}|error code:?\s*\d+|cf-error-code[^<]{0,40}|<title>[^<]{0,80})", t_, _re.I)
            txt = (m_.group(0) if m_ else t_[:120]).replace("\n", " ")
            return {"code": str(e.code), "msg": f"HTTP sem JSON | servidor={e.headers.get('Server')} | {txt}"}
    except Exception as e:
        return {"code": "rede", "msg": type(e).__name__}


def telegram(txt):
    t, c = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip(), (os.environ.get("TELEGRAM_CHAT_ID") or "").strip()
    if not t or not c:
        return
    data = json.dumps({"chat_id": c, "text": txt}).encode()
    try:
        urllib.request.urlopen(urllib.request.Request(f"https://api.telegram.org/bot{t}/sendMessage", data=data,
                                                      headers={"Content-Type": "application/json"}), timeout=20)
    except Exception as e:                       # nunca imprimir a mensagem: pode conter o URL com o token
        print("telegram falhou:", type(e).__name__)


def publico():
    """Pedido publico (sem chave): distingue bloqueio do servidor/regiao de problema da chave."""
    try:
        req = urllib.request.Request("https://www.okx.com/api/v5/public/time", headers={"User-Agent": "cryptoscan/1.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            print("pedido publico OKX: OK", r.status)
    except urllib.error.HTTPError as e:
        print("pedido publico OKX:", e.code, e.headers.get("Server"), e.read()[:120].decode("utf-8", "replace"))
    except Exception as e:
        print("pedido publico OKX: falhou", type(e).__name__)
    try:                                         # privado SEM chave: deve dar JSON 401 se o Cloudflare deixar passar
        req = urllib.request.Request("https://www.okx.com/api/v5/account/config", headers={"User-Agent": "cryptoscan/1.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            print("privado sem chave:", r.status, r.read()[:120])
    except urllib.error.HTTPError as e:
        print("privado sem chave:", e.code, e.read()[:120].decode("utf-8", "replace").replace("\n", " "))
    print("formato dos segredos: chave", len(K), "carateres; segredo", len(S), "; frase", len(P),
          "| so ASCII normal -> chave:", all(c.isascii() and c.isprintable() for c in K),
          "segredo:", all(c.isascii() and c.isprintable() for c in S), "frase:", all(c.isascii() and c.isprintable() for c in P),
          "| posicoes estranhas na frase:", [i + 1 for i, c in enumerate(P) if not (c.isascii() and c.isprintable())])
    try:
        with urllib.request.urlopen("https://api.ipify.org", timeout=15) as r:
            print("IP de saida do servidor:", r.read().decode()[:40])
    except Exception as e:
        print("IP de saida: nao lido", type(e).__name__)


def main():
    publico()
    falta = [n for n, v in (("OKX_API_KEY", K), ("OKX_API_SECRET", S), ("OKX_PASSPHRASE", P)) if not v]
    if falta:
        print("FALTAM SEGREDOS:", ", ".join(falta))
        telegram("⚠️ OKX: faltam segredos no GitHub: " + ", ".join(falta))
        return 1
    for base in BASES:
        r = pedido(base, "/api/v5/account/config")
        print(base, "->", r.get("code"), (r.get("msg") or "")[:220])
        if r.get("code") == "0":
            cfg = (r.get("data") or [{}])[0]
            perm = cfg.get("perm", "")
            print("permissoes:", perm, "| modo da conta (acctLv):", cfg.get("acctLv"), "| posicoes:", cfg.get("posMode"),
                  "| IP preso:", "sim" if cfg.get("ip") else "nao")
            levantar = "withdraw" in perm.lower()
            b = pedido(base, "/api/v5/account/balance")
            linhas = []
            if b.get("code") == "0":
                for d in (b.get("data") or [{}])[0].get("details") or []:
                    if float(d.get("eq") or 0) > 0:
                        linhas.append(f"{d.get('ccy')} {float(d.get('eq')):.2f}")
            print("saldo lido:", "sim" if b.get("code") == "0" else "nao", "| moedas com saldo:", len(linhas))
            telegram("✅ OKX ligada ao Cryptoscan (" + base.split('//')[1] + ").\nPermissões: " + perm +
                     ("\n🚨 A CHAVE TEM PERMISSÃO DE LEVANTAR: apaga-a e cria outra sem 'Levantar'." if levantar else
                      "\nSem permissão de levantar ✅") + "\nSaldo na conta de negociação: " +
                     (", ".join(linhas) if linhas else "vazio (deposita USDT/USDC para começar)"))
            return 2 if levantar else 0
    telegram("⚠️ OKX: a chave não foi aceite (ver o registo da verificação no GitHub). Confirma a chave, o segredo, a frase e o IP 2.28.62.236.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
