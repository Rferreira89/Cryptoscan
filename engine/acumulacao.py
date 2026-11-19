"""(19/11, decisao do Rui) Carteira de ACUMULACAO da Bybit UE: a Bybit deixou de fazer trading e passa a acumular BTC e
algumas altcoins com o dinheiro que la entra (depositos do salario ou lucros do trading da OKX, transferidos pelo
Rui: o programa nunca transfere nem levanta).

Regras (config "acumulacao"; estudo de 19/11 com depositos mensais e custos reais da Bybit UE, 2021-2026):
  - pesos-alvo: BTC 70%, ETH 15%, altcoins 15% (SOL, LINK, XRP, AVAX, max. 5% cada); so moedas com par USDC
    negociavel na Bybit UE; uma moeda sem preco na Bybit fica de fora e o seu peso vai para o BTC;
  - COMPRAS: o USDC livre e investido no ativo mais abaixo do peso, em ordens de pelo menos ordem_min_usdc;
  - VENDAS: so quando um ativo passa banda_pp pontos acima do peso; o excesso vendido compra o que esta em falta;
  - sem vendas por tendencia, sem alavancagem, sem emprestimos, sem vendas a descoberto;
  - enquanto houver posicoes de TRADING abertas na Bybit (a XLM ate fechar pelas suas regras) nada e investido: o
    USDC e a garantia dessa posicao.
Modos: "sombra" (calcula e avisa, nao executa), "real" (pede as ordens ao executor), "desligado".
Este modulo so PLANEIA: nao fala com a corretora."""
import time

MODOS = ("desligado", "sombra", "real")
AVISO_S = 20 * 3600                 # no maximo um aviso da sombra por dia (ou quando o plano muda)
SEMANA_S = 7 * 86400
RESUMO_DIA, RESUMO_HORA = 6, 19     # resumo semanal: domingo, primeira volta depois das 19:00 UTC


def _px(tickers, a):
    v = (tickers or {}).get(a)
    if isinstance(v, (list, tuple)) and v:
        try:
            ask = float(v[2]) if len(v) > 2 and v[2] else float(v[0])
            return ask if ask > 0 else None
        except (TypeError, ValueError):
            return None
    try:
        return float(v) if v else None
    except (TypeError, ValueError):
        return None


def pesos_efetivos(cfg_ac, tickers):
    """Pesos-alvo so com moedas que tem preco na Bybit UE; o peso das que faltam vai para o BTC. Normaliza a 1."""
    pesos = dict((cfg_ac or {}).get("pesos") or {})
    out, fora = {}, []
    for a, w in pesos.items():
        if _px(tickers, a):
            out[a] = float(w)
        else:
            fora.append(a)
            out["BTC"] = out.get("BTC", 0.0)
            if _px(tickers, "BTC"):
                out["BTC"] = out.get("BTC", 0.0) + float(w)
    tot = sum(out.values())
    return ({a: w / tot for a, w in out.items() if w > 0} if tot > 0 else {}), fora


def plano(cfg_ac, saldos, tickers, usdc_livre, posicoes_trading_abertas=0):
    """Devolve {"estado", "motivo", "valor_carteira", "pesos_atuais", "desvios_pp", "ordens": [{ativo, lado, valor}]}.
    saldos: {moeda: quantidade} (so as moedas da carteira contam); valores em USDC (privados: nunca publicar)."""
    c = cfg_ac or {}
    modo = c.get("modo") or "desligado"
    alvo, fora = pesos_efetivos(c, tickers)
    minimo = float(c.get("ordem_min_usdc") or 5.0)
    banda = float(c.get("banda_pp") or 5.0) / 100
    px = {a: _px(tickers, a) for a in alvo}
    val = {a: float((saldos or {}).get(a) or 0) * (px[a] or 0) for a in alvo}
    caixa = max(0.0, float(usdc_livre or 0))
    out = {"t": int(time.time()), "modo": modo, "pesos_alvo": {a: round(w, 4) for a, w in alvo.items()},
           "fora_da_bybit": fora, "ordens": []}
    if modo == "desligado" or not alvo:
        out.update(estado="desligado", motivo="acumulação desligada" if modo == "desligado" else "sem preços da Bybit")
        return out
    if posicoes_trading_abertas:
        caixa = 0.0                                   # o USDC e a garantia das posicoes de trading que ainda estao abertas
        out["motivo_caixa"] = f"{posicoes_trading_abertas} posição(ões) de trading ainda aberta(s) na Bybit: USDC reservado"
    total = sum(val.values()) + caixa
    out["valor_carteira"] = round(sum(val.values()), 2)
    out["caixa_investivel"] = round(caixa, 2)
    if total <= 0:
        out.update(estado="reservado" if posicoes_trading_abertas else "sem_saldo",
                   motivo=out.get("motivo_caixa") or "sem saldo para investir", pesos_atuais={}, desvios_pp={})
        return out
    ordens = []
    # 1) vendas: so o excesso acima da banda (e so se o valor vendido chegar ao minimo)
    for a, w in alvo.items():
        if val[a] / total - w > banda:
            x = val[a] - total * w
            if x >= minimo:
                ordens.append({"ativo": a, "lado": "vender", "valor": round(x, 2)})
                val[a] -= x
                caixa += x
    # 2) compras: o dinheiro livre vai para o mais abaixo do peso, em ordens >= minimo
    guarda = 0
    while caixa >= minimo and guarda < 50:
        guarda += 1
        falta = {a: total * w - val[a] for a, w in alvo.items()}
        a = max(falta, key=lambda k: falta[k])
        x = min(caixa, max(minimo, falta[a])) if falta[a] > 0 else caixa
        if caixa - x < minimo:                       # nao deixa um resto abaixo da ordem minima
            x = caixa
        prev = next((o for o in ordens if o["ativo"] == a and o["lado"] == "comprar"), None)
        if prev:
            prev["valor"] = round(prev["valor"] + x, 2)
        else:
            ordens.append({"ativo": a, "lado": "comprar", "valor": round(x, 2)})
        val[a] += x
        caixa -= x
    out["ordens"] = ordens
    out["pesos_atuais"] = {a: round(100 * v / total, 2) for a, v in val.items()}  # depois das ordens
    out["desvios_pp"] = {a: round(100 * (v / total - alvo[a]), 2) for a, v in val.items()}
    out["estado"] = "ordens" if ordens else "equilibrada"
    out["motivo"] = (f"{len(ordens)} ordem(ns)" if ordens else
                     out.get("motivo_caixa") or "carteira dentro das bandas e sem dinheiro novo")
    return out


def publico(p):
    """Resumo SEM dinheiro para o scan publico: pesos em %, desvios em pontos, contagem de ordens por lado."""
    p = p or {}
    return {"modo": p.get("modo"), "estado": p.get("estado"), "motivo": "reservado" if p.get("motivo_caixa") else p.get("motivo"),
            "posicoes_de_trading_por_fechar": bool(p.get("motivo_caixa")),
            "pesos_alvo_pct": {a: round(100 * w, 2) for a, w in (p.get("pesos_alvo") or {}).items()},
            "desvios_pp": p.get("desvios_pp") or {}, "fora_da_bybit": p.get("fora_da_bybit") or [],
            "ordens": {"comprar": sum(o["lado"] == "comprar" for o in p.get("ordens") or []),
                       "vender": sum(o["lado"] == "vender" for o in p.get("ordens") or [])},
            "t": p.get("t")}


def texto_aviso(p):
    """Mensagem privada (Telegram) com as ordens que a sombra faria."""
    linhas = [f"🧺 Acumulação Bybit ({'SOMBRA: nada foi executado' if p.get('modo') == 'sombra' else p.get('modo')})"]
    if p.get("motivo_caixa"):
        linhas.append(f"• {p['motivo_caixa']}")
    for o in p.get("ordens") or []:
        linhas.append(f"• {o['lado']} {o['ativo']}: {o['valor']:.2f} USDC")
    if not p.get("ordens"):
        linhas.append(f"• sem ordens ({p.get('motivo')})")
    if p.get("desvios_pp"):
        linhas.append("• desvios: " + ", ".join(f"{a} {d:+.1f} pp" for a, d in p["desvios_pp"].items()))
    return "\n".join(linhas)


def pesos_agora(cfg_ac, saldos, tickers, usdc_livre):
    """Valor de cada ativo da carteira, caixa e pesos atuais em % (ANTES de ordens). Privado: tem dinheiro."""
    alvo, _ = pesos_efetivos(cfg_ac, tickers)
    val = {a: float((saldos or {}).get(a) or 0) * (_px(tickers, a) or 0) for a in alvo}
    caixa = max(0.0, float(usdc_livre or 0))
    tot = sum(val.values()) + caixa
    pes = {a: (100 * v / tot if tot > 0 else 0.0) for a, v in val.items()}
    return alvo, val, caixa, pes


def texto_resumo(cfg_ac, saldos, tickers, usdc_livre, log, now):
    """(19/11, desenho da acumulacao) Resumo semanal para o Telegram: valor da carteira, caixa, pesos atuais vs alvo e o
    que foi comprado/vendido nos ultimos 7 dias. So mensagem privada; nunca vai para ficheiros publicos."""
    alvo, val, caixa, pes = pesos_agora(cfg_ac, saldos, tickers, usdc_livre)
    lin = ["🧺 Acumulação Bybit — resumo semanal",
           f"• carteira: {sum(val.values()):.2f} USDC em moedas + {caixa:.2f} USDC em caixa"]
    if alvo:
        lin.append("• pesos (atual / alvo): " + ", ".join(
            f"{a} {pes[a]:.1f}%/{100 * w:.1f}%" for a, w in sorted(alvo.items(), key=lambda x: -x[1])))
    sem = [x for x in log or [] if now - int(x.get("t") or 0) <= SEMANA_S and x.get("qty")]
    if sem:
        por = {}
        for x in sem:
            k = (x.get("lado"), x.get("ativo"))
            por[k] = por.get(k, 0.0) + float(x.get("usdc") or 0)
        lin.append("• últimos 7 dias: " + ", ".join(f"{l} {a} {v:.2f} USDC" for (l, a), v in sorted(por.items())))
    else:
        lin.append("• últimos 7 dias: sem compras nem vendas")
    tot = sum(float(x.get("usdc") or 0) * (1 if x.get("lado") == "comprar" else -1) for x in log or [] if x.get("qty"))
    lin.append(f"• aplicado desde o início (compras − vendas): {tot:.2f} USDC")
    if caixa >= float((cfg_ac or {}).get("ordem_min_usdc") or 5.0):
        lin.append("• a caixa será investida na próxima volta com leitura nova da conta")
    lin.append("Sem alavancagem, sem empréstimos. O programa nunca transfere nem levanta.")
    return "\n".join(lin)


def resumo_semanal(state, c, now, enviar):
    """Uma vez por semana: primeira volta de domingo depois das 19:00 UTC (no maximo um por semana)."""
    if not enviar or c.get("modo") != "real":
        return False
    g = time.gmtime(now)
    ult = int((state.get("acumulacao_resumo") or {}).get("t") or 0)
    if not (g.tm_wday == RESUMO_DIA and g.tm_hour >= RESUMO_HORA) or now - ult < 5 * 86400:
        return False
    sal = ((state.get("conta_saldos") or {}).get("m")) or {}
    tk = ((state.get("bybit_tickers") or {}).get("m")) or {}
    if not tk:
        return False
    try:
        enviar(texto_resumo(c, sal, tk, (state.get("conta_livre") or {}).get("usdc"), state.get("acumulacao_log"), now))
        state["acumulacao_resumo"] = {"t": int(now)}
        return True
    except Exception as e:
        state["acumulacao_resumo"] = {"t": ult, "erro": type(e).__name__}
        return False


def atualizar(state, cfg, now, enviar=None):
    """Chamado pelo scanner em cada volta. Guarda o plano no estado (privado) e o resumo publico; na sombra avisa no
    maximo uma vez por dia, ou quando as ordens mudam. Nunca pede ordens (a execucao real tem o seu proprio passo)."""
    c = (cfg or {}).get("acumulacao") or {}
    if (cfg or {}).get("bybit_modo") != "acumulacao":
        state.pop("acumulacao_plano", None)
        return None
    sal = ((state.get("conta_saldos") or {}).get("m")) or {}
    tk = ((state.get("bybit_tickers") or {}).get("m")) or {}
    livre = (state.get("conta_livre") or {}).get("usdc")
    # trading aberto: pelo registo E pelo executor (uma operacao que o executor ainda tem aberta conta, mesmo que o
    # registo ja a tenha fechado; uma que o executor ja fechou na corretora nao conta)
    ops = state.get("auto_ops") or {}
    abertas = sum(1 for r in state.get("ledger") or [] if r.get("mode") == "REAL" and r.get("executed") is True
                  and r.get("status") == "OPEN" and ops.get(r.get("id")) not in ("fechada", "cancelada", "recusada"))
    abertas += sum(1 for k, v in ops.items() if v in ("aberta", "pendente", "verificar")
                   and not any(r.get("id") == k and r.get("status") == "OPEN" for r in state.get("ledger") or []))
    p = plano(c, sal, tk, livre, abertas)
    p["t"] = int(now)
    state["acumulacao_plano"] = p
    conta_t = int((state.get("conta_livre") or {}).get("t") or 0)
    ped = state.get("acumulacao_pedido") or {}
    # so com uma leitura da conta POSTERIOR ao ultimo pedido (as compras anteriores ja la estao)
    if p.get("modo") == "real" and p.get("ordens") and not abertas and state.get("capital_confirmado") \
            and conta_t > int(ped.get("t") or 0):
        ass = [(o["ativo"], o["lado"], round(o["valor"])) for o in p["ordens"]]
        from . import execucao
        if execucao.request(state, "acumular", f"acumulacao-{int(now)}", now):
            state["acumulacao_pedido"] = {"t": int(now), "assinatura": ass}
    ant = state.get("acumulacao_aviso") or {}
    assinatura = [(o["ativo"], o["lado"]) for o in p.get("ordens") or []]
    mudou = assinatura != ant.get("assinatura")
    if enviar and p.get("modo") == "sombra" and (p.get("ordens") or mudou) and \
            (mudou or now - int(ant.get("t") or 0) >= AVISO_S):
        try:
            enviar(texto_aviso(p))
            state["acumulacao_aviso"] = {"t": int(now), "assinatura": assinatura}
        except Exception as e:
            state["acumulacao_aviso"] = dict(ant, erro=type(e).__name__)
    resumo_semanal(state, c, now, enviar)
    return publico(p)
