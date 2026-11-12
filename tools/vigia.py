"""(04/11) Vigia (Missao 1M, ponto 12: heartbeats, watchdogs, alertas de falha, verificacao de stops).
Corre de hora a hora dentro do ciclo do scanner da Bybit (um processo diferente do agente da OKX, para que uma
falha de um seja vista pelo outro). So le o estado publico (precos e ids, sem valores da conta) e avisa no Telegram:
  - o agente da OKX nao corre ha mais de 2,5 h (batimento parado);
  - uma operacao real aberta na OKX sem stop registado;
  - uma operacao real que ja passou da saida por tempo (72 h) ha mais de 2 h e continua aberta;
  - (05/11) uma ordem limite real que ja caducou (8 h) ha mais de 2 h e continua pendente (ordem presa: se a
    consulta ou o cancelamento falharem, o agente fica a espera em silencio e a ordem pode executar fora da regra);
  - (11/11) uma operacao real aberta cujo stop nao e confirmado NA OKX ha mais de 3 h (stop_ok, gravado pelo
    confirmar_stops do agente) com o agente a correr: a consulta a OKX esta a falhar em silencio ou o stop nao cobre a
    posicao, e o registo do stop no estado ja nao prova que a protecao existe.
  - (12/11) o servidor europeu da Bybit nao le a conta ha mais de 45 min (margem_bybit.t, escrito pelo ciclo Europa a
    cada 15 min): sem leitura da conta nao ha entradas novas nem execucao (a recolha OKX de 12/11 07:31 prendeu-o
    100 min sem aviso).
Cada aviso repete no maximo de 6 em 6 horas (ficheiro local do ciclo)."""
import json, os, sys, time, urllib.request

URL = "https://raw.githubusercontent.com/Rferreira89/Cryptoscan/okx/okx.json"
URL_BYBIT = "https://raw.githubusercontent.com/Rferreira89/Cryptoscan/data/state.json"
EUROPA_S = 45 * 60
MEM = os.environ.get("VIGIA_MEM", "/tmp/vigia.json")
LIMITE_S, REPETE_S, ATRASO_SAIDA_S, STOP_OK_S = 9000, 6 * 3600, 7200, 3 * 3600


def problemas(st, now):
    out = []
    t = (st.get("resumo") or {}).get("t") or 0
    parado = now - t > LIMITE_S
    if parado:
        out.append(("batimento", f"⚠️ Vigia: o agente da OKX não corre há {int((now - t) // 3600)} h "
                                  f"{int((now - t) % 3600 // 60)} min. Posições continuam protegidas pelo stop na OKX."))
    for a, o in ((st.get("real") or {}).get("ops") or {}).items():
        if o.get("estado") == "pendente":
            if o.get("valido_ate") and now - o["valido_ate"] > ATRASO_SAIDA_S:
                h = int((now - o["valido_ate"]) // 3600)
                out.append((f"presa-{a}", f"⚠️ Vigia: a ordem limite de {a} na OKX caducou há {h} h e o programa ainda a "
                                          "tem como pendente. Confirma na app da OKX se ficou presa e cancela-a se for o caso."))
            continue
        if o.get("estado") != "aberta":
            continue
        if not o.get("stop"):
            out.append((f"stop-{a}", f"🚨 Vigia: {a} está aberta na OKX sem stop registado. Verifica já na app da OKX."))
        # stop confirmado na OKX: referencia = ultima confirmacao, ou a execucao (o agente confirma na volta seguinte).
        # Com o agente parado o aviso de batimento ja cobre a causa; registos antigos sem nenhuma data nao avisam.
        ref = o.get("stop_ok") or o.get("t_fill") or o.get("criado")
        if o.get("stop") and ref and not parado and now - float(ref) > STOP_OK_S:
            h = int((now - float(ref)) // 3600)
            out.append((f"stopok-{a}", f"⚠️ Vigia: o stop de {a} não é confirmado na OKX há {h} h (o agente corre, mas a "
                                       "confirmação falha). Confirma na app da OKX que o stop está ativo."))
        if o.get("sair_em") and now - o["sair_em"] > ATRASO_SAIDA_S:
            out.append((f"tempo-{a}", f"⚠️ Vigia: {a} já devia ter fechado por tempo (72 h) e continua aberta."))
    return out


def problemas_bybit(st, now):
    t = ((st or {}).get("margem_bybit") or {}).get("t") or 0
    if t and now - t > EUROPA_S:
        m = int((now - t) // 60)
        return [("europa", f"⚠️ Vigia: o servidor europeu não lê a conta da Bybit há {m // 60} h {m % 60} min. Sem "
                           "essa leitura o programa não abre operações nem executa ordens; os stops já colocados "
                           "continuam na Bybit.")]
    return []


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
    lista = problemas(st, now)
    try:
        lista += problemas_bybit(json.loads(urllib.request.urlopen(URL_BYBIT + f"?t={int(now)}", timeout=20).read()), now)
    except Exception as e:
        print("vigia: sem estado da Bybit", type(e).__name__)
    for chave, msg in lista:
        if now - mem.get(chave, 0) >= REPETE_S:
            telegram(msg); mem[chave] = now
            print("vigia:", chave)
    json.dump(mem, open(MEM, "w"))
    print("vigia ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
