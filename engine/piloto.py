"""(11/11, PREPARACAO; NAO LIGADO a nada) Guarda de um piloto experimental com dinheiro real.

Funcoes puras sobre as operacoes REAIS fechadas da estrategia do piloto (executadas na corretora: executed=True),
desde o inicio do piloto. Nao abre, nao fecha e nao muda ordens; so diz se o piloto pode continuar a abrir
operacoes novas e compara o real com o esperado. So pode REDUZIR exposicao (bloquear entradas novas).

Regras (fixadas antes do piloto; os numeros vem da validacao de 11/11, SHORT_TURTLE na fase lateral, so moedas
com margem na Bybit UE, juro de referencia 0,03%/dia, teto de 3 abertas):
  - perda acumulada <= PERDA_MAX_R  -> suspende (com 0,5% de risco por operacao: -10R = -5% do capital);
  - perda num dia <= PERDA_DIA_R    -> suspende ate revisao;
  - juro real medio por operacao > JURO_MAX_R -> suspende (o custo do emprestimo invalida a validacao);
  - ao fim de N_DECISAO operacoes: continua se a media >= 0 e dentro da banda esperada; termina se a media < 0;
  - uma operacao sem execucao confirmada na corretora nunca conta (o registo AVAX/ICP de 10/2026)."""

ESPERADO = {"r_op": 0.33, "p05_soma_30": -8.4, "p50_soma_30": 8.7}
PERDA_MAX_R = -10.0
PERDA_DIA_R = -3.0
JURO_MAX_R = 0.06
N_DECISAO = 30
DAY = 86400


def operacoes(rows, estrategia, inicio):
    """So operacoes reais, fechadas, com execucao confirmada, da estrategia, desde o inicio do piloto."""
    out = []
    for r in rows or []:
        if (r.get("strategy") == estrategia and r.get("mode") == "REAL" and r.get("status") == "CLOSED"
                and r.get("executed") is True and r.get("result_r") is not None
                and (r.get("closed_at") or r.get("opened_at") or 0) >= inicio):
            out.append(r)
    return sorted(out, key=lambda r: r.get("closed_at") or 0)


def avaliar(rows, estrategia, inicio, juros_r=None):
    """{"pode_abrir": bool, "estado": ..., "motivos": [...], "n", "soma_r", "media_r", "vs_esperado"}."""
    ops = operacoes(rows, estrategia, inicio)
    rs = [float(r["result_r"]) for r in ops]
    soma = sum(rs)
    motivos = []
    if soma <= PERDA_MAX_R:
        motivos.append(f"perda acumulada {soma:+.2f}R no limite de {PERDA_MAX_R:+.0f}R")
    dias = {}
    for r in ops:
        d = int(r.get("closed_at") or 0) // DAY
        dias[d] = dias.get(d, 0.0) + float(r["result_r"])
    if dias and min(dias.values()) <= PERDA_DIA_R:
        motivos.append(f"perda de {min(dias.values()):+.2f}R num dia (limite {PERDA_DIA_R:+.0f}R)")
    if juros_r:
        jm = sum(juros_r) / len(juros_r)
        if jm > JURO_MAX_R:
            motivos.append(f"juro real medio {jm:.3f}R por operacao acima de {JURO_MAX_R}R")
    estado = "a correr"
    if len(rs) >= N_DECISAO:
        media = soma / len(rs)
        if media < 0:
            motivos.append(f"{len(rs)} operacoes com media {media:+.3f}R: termina")
            estado = "terminar"
        else:
            estado = "decidir (continuar ou alterar com o Rui)"
    if motivos and estado != "terminar":
        estado = "suspenso"
    media = soma / len(rs) if rs else None
    vs = None
    if rs:
        vs = {"media_real": round(media, 3), "media_esperada": ESPERADO["r_op"],
              "soma_real": round(soma, 2), "soma_esperada": round(ESPERADO["r_op"] * len(rs), 2),
              "abaixo_do_p05_esperado": len(rs) >= N_DECISAO and soma < ESPERADO["p05_soma_30"]}
    return {"pode_abrir": not motivos, "estado": estado, "motivos": motivos, "n": len(rs),
            "soma_r": round(soma, 3), "media_r": None if media is None else round(media, 3), "vs_esperado": vs}
