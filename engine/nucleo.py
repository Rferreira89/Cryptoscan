"""Nucleo da carteira (decisao do Rui, 2026-10-20).

Unica regra com prova nos dois periodos testados (2021-24 e 2024-26, ver a
Auditoria das Estrategias): ter a moeda quando o fecho diario esta acima da
media de 200 dias e passar a USDC quando fica abaixo. BTC, ETH e SOL, cada
uma independente, em spot, SEM alavancagem e SEM emprestimo.

- Decide com velas diarias fechadas (o scanner so usa velas fechadas).
- Entrada: fracao (70%) do capital a dividir pelas moedas, no maximo o USDC livre.
- Saida: vende a quantidade do nucleo quando o fecho diario fica abaixo da media.
- Nao conta para o travao, a prova do risco, as familias ou o modo automatico.
- So envia ordens com config "nucleo_ligado" (OK final do Rui).
Simulacao historica nao e garantia de resultado futuro.
"""
FRACAO = 0.70
MOEDAS = ("BTC", "ETH", "SOL")
DIAS = 200
REPETIR_S = 6 * 3600          # pedido recusado: volta a tentar ao fim de 6 horas
MIN_USDC = 5.0


def _st(state):
    return state.setdefault("nucleo", {"pos": {}, "plano": {}, "pedidos": {}})


def sinal(daily):
    """(acima, fecho, media) com as ultimas DIAS velas diarias fechadas, ou None."""
    if not daily or len(daily) < DIAS:
        return None
    c = [x["c"] for x in daily[-DIAS:]]
    m = sum(c) / DIAS
    return c[-1] > m, c[-1], m


def decidir(state, daily, precos, capital, livre, cfg, now):
    """Atualiza o plano e devolve os pedidos [(acao, op)] para o executor.
    Sem "nucleo_ligado" so calcula (para o painel), nao pede nada."""
    st = _st(state)
    moedas = tuple(cfg.get("nucleo_moedas") or MOEDAS)
    fr = float(cfg.get("nucleo_fracao") or FRACAO)
    alvo = round((capital or 0) * fr / len(moedas), 2)
    ligado = bool(cfg.get("nucleo_ligado"))
    pedidos, livre_rest = [], max(0.0, (livre or 0) * 0.98)
    for a in moedas:
        s = sinal(daily.get(a))
        pos = (st.get("pos") or {}).get(a)
        p = {"acima": None, "fecho": None, "media": None, "alvo_usdc": alvo, "preco": precos.get(a)}
        if s:
            p.update(acima=s[0], fecho=round(s[1], 8), media=round(s[2], 8))
        if pos and precos.get(a):
            p["valor_usdc"] = round(pos["qty"] * precos[a], 2)
            p["resultado_usdc"] = round(pos["qty"] * (precos[a] - pos["entrada"]), 2)
        st["plano"][a] = p
        if not ligado or not s:
            continue
        ultimo = (st.get("pedidos") or {}).get(a) or 0
        if now - ultimo < REPETIR_S:
            continue
        if s[0] and not pos:
            usdc = round(min(alvo, livre_rest), 2)
            if usdc >= MIN_USDC:
                p["comprar_usdc"] = usdc
                livre_rest -= usdc
                st["pedidos"][a] = int(now)
                pedidos.append(("nucleo_comprar", f"NUCLEO-{a}"))
        elif not s[0] and pos:
            st["pedidos"][a] = int(now)
            pedidos.append(("nucleo_vender", f"NUCLEO-{a}"))
    st["ligado"] = ligado
    return pedidos


def sync(state, ex):
    """Posicoes do nucleo vindas da execucao na Europa (exec.json)."""
    st = _st(state)
    st["pos"] = dict((ex or {}).get("nucleo") or {})
    st["historico"] = list((ex or {}).get("nucleo_hist") or [])[-50:]


def resumo(state):
    st = _st(state)
    pos = st.get("pos") or {}
    plano = st.get("plano") or {}
    val = sum((plano.get(a) or {}).get("valor_usdc") or 0 for a in pos)
    res = sum((plano.get(a) or {}).get("resultado_usdc") or 0 for a in pos)
    fechado = sum(h.get("pnl_usdc") or 0 for h in st.get("historico") or [])
    return {"ligado": bool(st.get("ligado")), "plano": plano, "pos": pos,
            "valor_usdc": round(val, 2), "resultado_aberto_usdc": round(res, 2),
            "resultado_fechado_usdc": round(fechado, 2)}
