"""(04/11) Verificacao da chave da OKX (so leitura). Corre no servidor europeu (IP autorizado na chave).
Repositorio PUBLICO: o log so mostra estado e permissoes, nunca valores. Os saldos vao so para o Telegram."""
import base64, datetime, hashlib, hmac, json, os, sys, urllib.request, urllib.error

K, S, P = (os.environ.get(v, "").strip() for v in ("OKX_API_KEY", "OKX_API_SECRET", "OKX_PASSPHRASE"))
BASES = ("https://www.okx.com", "https://eea.okx.com", "https://my.okx.com")


def pedido(base, path):
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + \
        f"{datetime.datetime.now(datetime.timezone.utc).microsecond // 1000:03d}Z"
    sig = base64.b64encode(hmac.new(S.encode(), (ts + "GET" + path).encode(), hashlib.sha256).digest()).decode()
    req = urllib.request.Request(base + path, headers={"OK-ACCESS-KEY": K, "OK-ACCESS-SIGN": sig, "OK-ACCESS-TIMESTAMP": ts,
                                                       "OK-ACCESS-PASSPHRASE": P, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read())
        except Exception:
            return {"code": str(e.code), "msg": "HTTP"}
    except Exception as e:
        return {"code": "rede", "msg": str(e)[:80]}


def telegram(txt):
    t, c = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not t or not c:
        return
    data = json.dumps({"chat_id": c, "text": txt}).encode()
    try:
        urllib.request.urlopen(urllib.request.Request(f"https://api.telegram.org/bot{t}/sendMessage", data=data,
                                                      headers={"Content-Type": "application/json"}), timeout=20)
    except Exception as e:
        print("telegram falhou:", str(e)[:60])


def main():
    falta = [n for n, v in (("OKX_API_KEY", K), ("OKX_API_SECRET", S), ("OKX_PASSPHRASE", P)) if not v]
    if falta:
        print("FALTAM SEGREDOS:", ", ".join(falta))
        telegram("⚠️ OKX: faltam segredos no GitHub: " + ", ".join(falta))
        return 1
    for base in BASES:
        r = pedido(base, "/api/v5/account/config")
        print(base, "->", r.get("code"), (r.get("msg") or "")[:80])
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
