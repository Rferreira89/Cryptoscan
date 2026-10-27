"""Maquina do tempo (27/10, pedido do Rui; ideia do day-trader-skill, MIT, adaptada a cripto).

Para cada sinal novo, antes de entrar:
  - 10 000 percursos simulados da propria moeda: blocos de 1 dia (6 velas de 4H) tirados ao
    acaso dos ultimos 180 dias, com os pavios de cada vela (maximo e minimo relativos ao fecho
    anterior). Semente fixa: o mesmo sinal da sempre o mesmo resultado.
  - repeticao real: a mesma distancia de stop e de alvo aplicada em cada vela dos ultimos
    180 dias.
Conta quantas vezes o preco chegou ao 1.o objetivo antes do stop, ao stop antes do objetivo,
ou a nenhum dentro do prazo maximo da operacao. Vela com os dois niveis conta como stop.

O que mede: se o stop e o alvo fazem sentido para a volatilidade desta moeda. NAO mede a
vantagem da estrategia (isso e a arena, contra 95% do acaso). So informa: nao bloqueia nem
autoriza entradas. Simulacao historica nao e previsao.
"""
import random

N, BLOCO, JANELA = 10_000, 6, 1080          # 180 dias de velas de 4H
H4 = 14400


def _rel(c4):
    b = [x for x in (c4 or [])[-(JANELA + 1):] if x.get("c")]
    return [(b[i]["h"] / b[i - 1]["c"], b[i]["l"] / b[i - 1]["c"], b[i]["c"] / b[i - 1]["c"])
            for i in range(1, len(b))]


def _passo(lado, h, l, stop, alvo):
    if lado == "SHORT":
        return "stop" if h >= stop else "alvo" if l <= alvo else None
    return "stop" if l <= stop else "alvo" if h >= alvo else None


def simular(c4, lado, entrada, stop, alvo, hold_s, n=N, seed=7):
    rel = _rel(c4)
    hold = max(1, int((hold_s or 20 * 86400) // H4))
    if len(rel) < 300 or not entrada or not stop or not alvo:
        return None
    risco = abs(entrada - stop)
    rng, cont, r_fim = random.Random(seed), {"alvo": 0, "stop": 0, "nenhum": 0}, 0.0
    sinal = -1 if lado == "SHORT" else 1
    rr = abs(alvo - entrada) / risco
    for _ in range(n):
        px, k, fim = entrada, 0, None
        while k < hold and not fim:
            i0 = rng.randrange(0, len(rel) - BLOCO + 1)
            for rh, rl, rc in rel[i0:i0 + BLOCO]:
                fim = _passo(lado, px * rh, px * rl, stop, alvo)
                px *= rc
                k += 1
                if fim or k >= hold:
                    break
        cont[fim or "nenhum"] += 1
        r_fim += rr if fim == "alvo" else -1.0 if fim == "stop" else sinal * (px - entrada) / risco
    # repeticao real nos ultimos 180 dias, com as mesmas distancias relativas
    real = {"alvo": 0, "stop": 0, "nenhum": 0}
    fs, fa = stop / entrada, alvo / entrada
    b = [x for x in c4[-(JANELA + hold + 1):] if x.get("c")]
    for i in range(0, max(0, len(b) - hold - 1), 3):            # uma entrada a cada 12 horas
        e, fim = b[i]["c"], None
        for x in b[i + 1:i + 1 + hold]:
            fim = _passo(lado, x["h"], x["l"], e * fs, e * fa)
            if fim:
                break
        real[fim or "nenhum"] += 1
    nr = sum(real.values()) or 1
    pct = lambda v, t: round(100 * v / t, 1)
    return {"n": n, "dias": round(hold / 6, 1), "lado": lado, "rr": round(rr, 2),
            "alvo_pct": pct(cont["alvo"], n), "stop_pct": pct(cont["stop"], n),
            "nenhum_pct": pct(cont["nenhum"], n), "r_medio": round(r_fim / n, 2),
            "real": {"n": nr, "alvo_pct": pct(real["alvo"], nr), "stop_pct": pct(real["stop"], nr),
                     "nenhum_pct": pct(real["nenhum"], nr)}}


def para_sinal(sig, c4):
    """Corre a maquina para um sinal com plano (1.o objetivo como alvo)."""
    p = (sig or {}).get("plan") or {}
    tps = [t for t in (p.get("tp") or []) if t]
    if not tps or not p.get("stop"):
        return None
    lado = "SHORT" if (p.get("side") or sig.get("direction")) == "SHORT" else "LONG"
    return simular(c4, lado, p.get("entry_ref") or p["entry_zone"][0], p["stop"], tps[0], p.get("max_hold_s"))


def linha(mt):
    """Linha curta para o Telegram e para a app."""
    if not mt:
        return ""
    r = mt["real"]
    n = f"{mt['n']:,}".replace(",", " ")
    return (f"🕰️ Máquina do tempo ({n} simulações, {mt['dias']:g} dias): 1.º objetivo antes do stop "
            f"{mt['alvo_pct']:g}% · stop antes {mt['stop_pct']:g}% · nenhum {mt['nenhum_pct']:g}% · "
            f"média {mt['r_medio']:+.2f}R. Últimos 180 dias reais: {r['alvo_pct']:g}% / {r['stop_pct']:g}% / "
            f"{r['nenhum_pct']:g}%. Só mede stop e alvo contra a volatilidade da moeda; a vantagem "
            f"da estratégia é a arena.")


def registar(state, events, c4s, now):
    """Corre a maquina em cada sinal novo e guarda-a no sinal (Telegram e app) e num registo
    para medir ao vivo o filtro em papel (sinais com menos de 8% seriam os cortados)."""
    log = state.setdefault("maquina_tempo", [])
    for e in events or []:
        s = e.get("signal") if e.get("event") == "ISSUED" else None
        if not s or s.get("maquina_tempo"):
            continue
        try:
            mt = para_sinal(s, (c4s or {}).get(e.get("asset")))
        except Exception:
            mt = None
        if mt:
            s["maquina_tempo"] = mt
            log.append({"id": s["id"], "asset": s["asset"], "t": int(now), "alvo_pct": mt["alvo_pct"],
                        "stop_pct": mt["stop_pct"], "r_medio": mt["r_medio"], "corte_papel": mt["alvo_pct"] < 8})
    del log[:-200]
    return log[-20:]
