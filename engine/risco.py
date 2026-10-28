"""Nivel de risco por operacao (decisao do Rui, 2026-10-18 12:56: "avancamos
com a que recomendas").

  - risco REDUZIDO (metade do normal) ate as primeiras PROVA_N
    operacoes dos campeoes com dinheiro real, fechadas depois da decisao,
    somarem resultado positivo;
  - depois, risco NORMAL: config "risk_pct_of_capital" (0,5% do capital em config.json;
    o 3% deste comentario estava desatualizado, auditoria de 28/10);
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
        from . import promo                   # (28/10) a prova so conta estrategias autorizadas
        if promo.AUTORIZADOS is not None and r.get("strategy") not in promo.AUTORIZADOS:
            continue
        if r.get("executed") is True and fechou and not r.get("fora_programa") and (r.get("issued_at") or 0) >= DESDE \
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
    # (28/10, auditoria F1) a queda mede-se num indice da carteira que ignora depositos e levantamentos
    # (engine/evolucao.nav_queda). A regra de 27/10 descontava do pico todos os "fluxos", incluindo
    # perdas grandes mal classificadas, e o travao ficava cego a elas.
    from . import evolucao
    q = evolucao.nav_queda(state.get("evolucao"), capital)
    if capital:
        st["pico"] = round(max(st.get("pico") or 0, capital), 2)
    if q is not None:
        dd, base = q[0], "do máximo da carteira, sem contar depósitos e levantamentos"
    else:
        pico = st.get("pico") or capital or 0
        dd, base = (1 - capital / pico if capital and pico else 0.0), f"do máximo ({pico:.2f} USDC)"
    n, soma = prova(state.get("ledger"))
    provado = n >= PROVA_N and soma > 0
    if dd >= TRAVAO_DD:
        red, why = True, f"travão: carteira {dd:.0%} abaixo {base}"
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
