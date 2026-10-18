"""Nivel de risco por operacao (decisao do Rui, 2026-10-18 12:56: "avancamos
com a que recomendas").

  - risco REDUZIDO (metade: 1,5% do capital) ate as primeiras PROVA_N
    operacoes dos campeoes com dinheiro real, fechadas depois da decisao,
    somarem resultado positivo;
  - depois, risco NORMAL (3% do capital);
  - travao: se o capital cair TRAVAO_DD desde o maximo, volta ao reduzido
    ate o capital recuperar esse maximo... ou ate o Rui decidir outra coisa;
  - a regra de 13/10 continua por cima: 2 perdas seguidas = metade ate um ganho.
"""
from . import ledger

DESDE = 1792324560            # 2026-10-18 12:56 (Lisboa)
PROVA_N = 5
TRAVAO_DD = 0.10
CLASSICAS = {"PULLBACK", "BREAKOUT", "LIQUIDITY_SWEEP", "RANGE", "RANGE_SHORT", "TREND_DAILY"}


def prova(led):
    """(n, soma em R) das operacoes de campeoes executadas e fechadas desde DESDE."""
    rs = []
    for r in led or []:
        quando = r.get("user_closed_at") or r.get("closed_at") or 0
        fechou = r.get("status") == "CLOSED" or ledger.user_closed(r)
        # so operacoes abertas depois da decisao (Rui, 18/10: "a da PUMP ja nao devia contar")
        if r.get("executed") is True and fechou and (r.get("issued_at") or 0) >= DESDE \
                and r.get("kind") == "4H" and r.get("strategy") not in CLASSICAS:
            R = ledger.user_r(r)
            if R is not None:
                rs.append((quando, R))
    rs.sort()
    rs = [x for _, x in rs[:PROVA_N]]
    return len(rs), round(sum(rs), 2)


def nivel(state, capital):
    """Devolve {"reduzido": bool, "motivo": str, ...} e atualiza o pico."""
    st = state.setdefault("risco", {})
    if capital:
        st["pico"] = round(max(st.get("pico") or 0, capital), 2)
    pico = st.get("pico") or capital or 0
    dd = 1 - capital / pico if capital and pico else 0.0
    n, soma = prova(state.get("ledger"))
    provado = n >= PROVA_N and soma > 0
    if dd >= TRAVAO_DD:
        red, why = True, f"travão: capital {dd:.0%} abaixo do máximo ({pico:.2f} USDC)"
    elif not provado:
        red, why = True, (f"à espera da prova: {n}/{PROVA_N} operações dos campeões fechadas "
                          f"({soma:+.2f}R)" if n < PROVA_N else
                          f"prova falhou: {soma:+.2f}R nas primeiras {PROVA_N} — fica reduzido")
    else:
        red, why = False, f"prova feita: {soma:+.2f}R nas primeiras {PROVA_N} operações"
    antes = st.get("reduzido")
    st.update(reduzido=red, motivo=why, prova_n=n, prova_r=soma, dd=round(dd, 3))
    st["mudou"] = antes is not None and antes != red
    return dict(st)


def aviso(st):
    if not st.get("mudou"):
        return None
    if st["reduzido"]:
        return f"🛡️ Risco por operação passa a REDUZIDO (metade). Motivo: {st['motivo']}."
    return (f"🚀 Risco por operação passa a NORMAL (3% do capital). {st['motivo'].capitalize()}. "
            f"Travão: volta a metade se o capital cair {TRAVAO_DD:.0%} desde o máximo.")
