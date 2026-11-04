"""(04/11) Vigia (Missao 1M, ponto 12: heartbeats, watchdogs, alertas de falha, verificacao de stops).
Corre de hora a hora dentro do ciclo do scanner da Bybit (um processo diferente do agente da OKX, para que uma
falha de um seja vista pelo outro). So le o estado publico (precos e ids, sem valores da conta) e avisa no Telegram:
  - o agente da OKX nao corre ha mais de 2,5 h (batimento parado);
  - uma operacao real aberta na OKX sem stop registado;
  - uma operacao real que ja passou da saida por tempo (72 h) ha mais de 2 h e continua aberta.
Cada aviso repete no maximo de 6 em 6 horas (ficheiro local do ciclo)."""
import json, os, sys, time, urllib.request

URL = "https://raw.githubusercontent.com/Rferreira89/Cryptoscan/okx/okx.json"
MEM = os.environ.get("VIGIA_MEM", "/tmp/vigia.json")
LIMITE_S, REPETE_S, ATRASO_SAIDA_S = 9000, 6 * 3600, 7200


def problemas(st, now):
    out = []
    t = (st.get("resumo") or {}).get("t") or 0
    if now - t > LIMITE_S:
        out.append(("batimento", f"⚠️ Vigia: o agente da OKX não corre há {int((now - t) // 3600)} h "
                                  f"{int((now - t) % 3600 // 60)} min. Posições continuam protegidas pelo stop na OKX."))
    for a, o in ((st.get("real") or {}).get("ops") or {}).items():
        if o.get("estado") != "aberta":
            continue
        if not o.get("stop"):
            out.append((f"stop-{a}", f"🚨 Vigia: {a} está aberta na OKX sem stop registado. Verifica já na app da OKX."))
        if o.get("sair_em") and now - o["sair_em"] > ATRASO_SAIDA_S:
            out.append((f"tempo-{a}", f"⚠️ Vigia: {a} já devia ter fechado por tempo (72 h) e continua aberta."))
    return out


def telegram(txt):
    t, c = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip(), (os.environ.get("TELEGRAM_CHAT_ID") or "").strip()
    if not t or not c:
        return
    try:
        urllib.request.urlopen(urllib.request.Request(f"https://api.telegram.org/bot{t}/sendMessage",
                               data=json.dumps({"chat_id": c, "text": txt}).encode(),
                               headers={"Content-Type": "application/json"}), timeout=20)
    except Exception as e:                       # nunca imprimir a mensagem do erro: pode conter o token
        print("telegram falhou:", type(e).__name__)


def main():
    now = time.time()
    try:
        st = json.loads(urllib.request.urlopen(URL + f"?t={int(now)}", timeout=20).read())
    except Exception as e:
        print("vigia: sem estado da OKX", type(e).__name__)
        return 0
    try:
        mem = json.load(open(MEM))
    except Exception:
        mem = {}
    for chave, msg in problemas(st, now):
        if now - mem.get(chave, 0) >= REPETE_S:
            telegram(msg); mem[chave] = now
            print("vigia:", chave)
    json.dump(mem, open(MEM, "w"))
    print("vigia ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
