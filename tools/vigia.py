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
  - (18/11, incidente RENDER) o piloto real da OKX (piloto_publico.json, processo e estado proprios, que este vigia nao
    via): sem volta ha mais de 2 h; posicao com o stop por confirmar na OKX (logo, se a OKX disse que falta ou nao cobre;
    com 2 voltas seguidas, se a OKX so nao respondeu); fecho pedido ha mais de 3 h e por confirmar (o piloto nao volta a
    pedir o fecho); ordem de entrada que ja devia ter sido cancelada.
Cada aviso repete no maximo de 6 em 6 horas (ficheiro local do ciclo)."""
import json, os, sys, time, urllib.request

URL = "https://raw.githubusercontent.com/Rferreira89/Cryptoscan/okx/okx.json"
URL_BYBIT = "https://raw.githubusercontent.com/Rferreira89/Cryptoscan/data/state.json"
URL_PILOTO = "https://raw.githubusercontent.com/Rferreira89/Cryptoscan/piloto-okx/piloto_publico.json"
EUROPA_S = 45 * 60
MEM = os.environ.get("VIGIA_MEM", "/tmp/vigia.json")
LIMITE_S, REPETE_S, ATRASO_SAIDA_S, STOP_OK_S = 9000, 6 * 3600, 7200, 3 * 3600
PILOTO_PARADO_S, PILOTO_FECHO_S, PILOTO_PRAZO_S, PILOTO_SEM_RESPOSTA_S = 7200, 3 * 3600, 900, 5400


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
    scan = max((st or {}).get("scan_times") or [0])
    if scan and now - scan > EUROPA_S:
        # (14/11) se o proprio scanner parou de publicar, a culpa nao e do servidor europeu: o aviso diz o certo
        m = int((now - scan) // 60)
        return [("europa", f"⚠️ Vigia: o scanner não publica um ciclo há {m // 60} h {m % 60} min (ver erros.txt no "
                           "ramo data). Sem ciclos o programa não abre operações nem executa ordens; os stops já "
                           "colocados continuam na Bybit.")]
    if t and now - t > EUROPA_S:
        m = int((now - t) // 60)
        return [("europa", f"⚠️ Vigia: o servidor europeu não lê a conta da Bybit há {m // 60} h {m % 60} min. Sem "
                           "essa leitura o programa não abre operações nem executa ordens; os stops já colocados "
                           "continuam na Bybit.")]
    return []


def problemas_piloto(st, now):
    """Piloto real da OKX, so pelo ficheiro publico (estados, precos e horas; sem valores da conta)."""
    t = (st or {}).get("t") or 0
    if not t:
        return []
    vivas = [o for o in st.get("ops") or [] if o.get("estado") in ("pendente", "aberta", "a fechar")]
    if now - t > PILOTO_PARADO_S:
        if not vivas and not st.get("operacional"):
            return []                                    # piloto desligado e sem posicao: nada a vigiar
        m = int((now - t) // 60)
        extra = (f" Tem {vivas[0].get('base')} em curso: o stop fica na OKX, mas a saída por tempo e o espelho do papel "
                 "não correm.") if vivas else ""
        return [("piloto-batimento", f"⚠️ Vigia: o piloto da OKX não corre há {m // 60} h {m % 60} min.{extra}")]
    out = []
    ev = st.get("eventos") or []
    for o in vivas:
        a, est = o.get("base"), o.get("estado")
        if est == "pendente":
            if o.get("t_ordem") and now - o["t_ordem"] > PILOTO_PRAZO_S + ATRASO_SAIDA_S:
                out.append((f"piloto-presa-{a}", f"⚠️ Vigia: a ordem de entrada do piloto em {a} já devia ter sido cancelada "
                                                 "e continua pendente. Confirma na app da OKX."))
            continue
        if o.get("stop_confirmado") is not True:
            se = o.get("stop_estado")
            if se in (None, "sem_resposta"):             # a OKX nao respondeu: uma volta isolada nao chega para avisar
                n = sum(1 for e in ev if str(e.get("txt", "")).startswith("STOP POR CONFIRMAR")
                        and now - (e.get("t") or 0) <= PILOTO_SEM_RESPOSTA_S)
                if n >= 2:
                    out.append((f"piloto-stop-{a}", f"⚠️ Vigia: a OKX não responde sobre o stop de {a} (piloto, {n} voltas "
                                                    "seguidas). Confirma na app da OKX que o stop está ativo."))
            else:
                out.append((f"piloto-stop-{a}", f"🚨 Vigia: {a} (piloto) sem stop confirmado na OKX: {se}. "
                                                "Verifica já na app da OKX."))
        if est == "a fechar":
            ts = [e.get("t") or 0 for e in ev if (str(e.get("txt", "")).startswith("fecho pedido") and e.get("op") == o.get("id"))
                  or str(e.get("txt", "")).startswith(("LIMITE ATINGIDO", "stop falhou"))]
            ref = max(ts) if ts else o.get("t_execucao")
            if ref and now - ref > PILOTO_FECHO_S:
                h = int((now - ref) // 3600)
                out.append((f"piloto-fecho-{a}", f"⚠️ Vigia: o fecho de {a} (piloto) foi pedido há {h} h e continua por "
                                                 "confirmar. Vê na app da OKX se a posição ainda está aberta."))
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
    lista = problemas(st, now)
    try:
        lista += problemas_bybit(json.loads(urllib.request.urlopen(URL_BYBIT + f"?t={int(now)}", timeout=20).read()), now)
    except Exception as e:
        print("vigia: sem estado da Bybit", type(e).__name__)
    try:
        lista += problemas_piloto(json.loads(urllib.request.urlopen(URL_PILOTO + f"?t={int(now)}", timeout=20).read()), now)
    except Exception as e:
        print("vigia: sem estado do piloto", type(e).__name__)
    for chave, msg in lista:
        if now - mem.get(chave, 0) >= REPETE_S:
            telegram(msg); mem[chave] = now
            print("vigia:", chave)
    json.dump(mem, open(MEM, "w"))
    print("vigia ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
